"""SSI-DDI model + featurizer, reconstructed exactly from the training code
so the uploaded checkpoint loads into it. Used by the Sentinel backend to
predict drug-drug interactions (with substructure attention) for NOVEL SMILES."""
import numpy as np, torch
import torch.nn as nn, torch.nn.functional as F
from torch_geometric.data import Data, Batch
from torch_geometric.nn import GATConv, global_mean_pool
from rdkit import Chem

ATOM_FEATURES = 37

def atom_features(atom):
    return np.array([
        atom.GetAtomicNum(), atom.GetDegree(), atom.GetFormalCharge(),
        int(atom.GetHybridization()), int(atom.GetIsAromatic()),
        atom.GetTotalNumHs(), atom.GetNumRadicalElectrons(), int(atom.IsInRing()),
    ] + [int(atom.IsInRingSize(r)) for r in range(3, 9)] + [0]*23, dtype=np.float32)[:ATOM_FEATURES]

def smiles_to_graph(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    node_feats = torch.tensor(np.array([atom_features(a) for a in mol.GetAtoms()]), dtype=torch.float)
    edges = []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        edges += [[i, j], [j, i]]
    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous() if edges else torch.zeros((2, 0), dtype=torch.long)
    return Data(x=node_feats, edge_index=edge_index)

class DrugEncoder(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim, heads=4):
        super().__init__()
        self.gat1 = GATConv(in_dim, hidden_dim, heads=heads, concat=True, dropout=0.2)
        self.gat2 = GATConv(hidden_dim*heads, out_dim, heads=1, concat=False, dropout=0.2)
    def forward(self, x, edge_index, batch):
        x = F.elu(self.gat1(x, edge_index))
        x = F.elu(self.gat2(x, edge_index))
        return x, global_mean_pool(x, batch)

class SubstructureAttention(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.scale = dim ** -0.5
        self.q = nn.Linear(dim, dim); self.k = nn.Linear(dim, dim); self.v = nn.Linear(dim, dim)
    def forward(self, atoms_a, atoms_b, return_attn=False):
        Q, K, V = self.q(atoms_a), self.k(atoms_b), self.v(atoms_b)
        attn = torch.softmax(Q @ K.T * self.scale, dim=-1)
        out = attn @ V
        return (out, attn) if return_attn else out

class SSIDDI(nn.Module):
    def __init__(self, atom_dim=ATOM_FEATURES, hidden=64, out=128):
        super().__init__()
        self.encoder = DrugEncoder(atom_dim, hidden, out)
        self.ssi_ab = SubstructureAttention(out)
        self.ssi_ba = SubstructureAttention(out)
        self.classifier = nn.Sequential(
            nn.Linear(out*4, 256), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(256, 64), nn.ReLU(),
            nn.Linear(64, 1),
        )
    def forward(self, batch_a, batch_b):
        atoms_a, drug_a = self.encoder(batch_a.x, batch_a.edge_index, batch_a.batch)
        atoms_b, drug_b = self.encoder(batch_b.x, batch_b.edge_index, batch_b.batch)
        feats = []
        for i in range(batch_a.num_graphs):
            aa = atoms_a[batch_a.batch == i]; bb = atoms_b[batch_b.batch == i]
            ab = self.ssi_ab(aa, bb).mean(0); ba = self.ssi_ba(bb, aa).mean(0)
            feats.append(torch.cat([ab, ba], dim=-1))
        ssi = torch.stack(feats)
        combined = torch.cat([drug_a, drug_b, ssi], dim=-1)
        return self.classifier(combined).squeeze(-1)

    @torch.no_grad()
    def attribution(self, smiles_a, smiles_b):
        """Return interaction prob + per-atom attention weights (substructure attribution)."""
        self.eval()
        ga, gb = smiles_to_graph(smiles_a), smiles_to_graph(smiles_b)
        if ga is None or gb is None:
            return None
        ba, bb = Batch.from_data_list([ga]), Batch.from_data_list([gb])
        atoms_a, drug_a = self.encoder(ba.x, ba.edge_index, ba.batch)
        atoms_b, drug_b = self.encoder(bb.x, bb.edge_index, bb.batch)
        ab, attn_ab = self.ssi_ab(atoms_a, atoms_b, return_attn=True)
        ba_, attn_ba = self.ssi_ba(atoms_b, atoms_a, return_attn=True)
        ssi = torch.cat([ab.mean(0), ba_.mean(0)], dim=-1).unsqueeze(0)
        combined = torch.cat([drug_a, drug_b, ssi], dim=-1)
        prob = torch.sigmoid(self.classifier(combined).squeeze(-1)).item()
        # atom importance = how much attention each atom receives, aggregated
        a_importance = attn_ab.mean(0).cpu().numpy()   # attention drug B atoms get from A? -> use column/row means
        return {
            "prob": prob,
            "a_atom_importance": attn_ba.mean(0).cpu().numpy().tolist(),  # A atoms attended by B
            "b_atom_importance": attn_ab.mean(0).cpu().numpy().tolist(),  # B atoms attended by A
        }

def load_ssiddi(ckpt_path, device="cpu"):
    model = SSIDDI().to(device)
    sd = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(sd)
    model.eval()
    return model
