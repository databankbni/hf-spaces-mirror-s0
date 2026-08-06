"""
Sentinel backend — real-world drug-safety screening API.

Serves the actual pipeline outputs (EHR-derived signals) for KNOWN drugs, and
runs the trained models live for NOVEL compounds:
  - SSI-DDI (uploaded checkpoint)  -> drug-drug interaction + substructure attribution
  - MoLFormer-XL (loaded at runtime) -> structural similarity to 380 known drugs,
        bridged to their observed EHR reactions (the real-world-evidence layer)

Endpoints:
  GET  /health
  POST /screen         {drug} | {drug_a, drug_b}   -> observed evidence (known drugs)
  POST /screen_smiles  {smiles, name?}             -> predicted signals (novel compound)
"""
import os, json, numpy as np, torch, warnings
from functools import lru_cache
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ssiddi_model import load_ssiddi, smiles_to_graph
from torch_geometric.data import Batch
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D
warnings.filterwarnings("ignore")

DATA = os.path.join(os.path.dirname(__file__), "data")
DEVICE = "cpu"

# ---------------------------------------------------------------- SMILES map
# canonical SMILES for drugs that appear in the vocab / demos, so DDI (SSI-DDI)
# runs for named pairs. Novel compounds bring their own SMILES.
SMILES = {
 "warfarin":"CC(=O)CC(c1ccccc1)C1=C(O)c2ccccc2OC1=O","coumadin":"CC(=O)CC(c1ccccc1)C1=C(O)c2ccccc2OC1=O",
 "aspirin":"CC(=O)Oc1ccccc1C(=O)O","asa":"CC(=O)Oc1ccccc1C(=O)O",
 "penicillin":"CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O","penicillins":"CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O",
 "amoxicillin":"CC1(C)SC2C(NC(=O)C(N)c3ccc(O)cc3)C(=O)N2C1C(=O)O",
 "cephalexin":"CC1=C(C(=O)O)N2C(=O)C(NC(=O)C(N)c3ccccc3)C2SC1","keflex":"CC1=C(C(=O)O)N2C(=O)C(NC(=O)C(N)c3ccccc3)C2SC1",
 "ciprofloxacin":"OC(=O)C1=CN(C2CC2)c2cc(N3CCNCC3)c(F)cc2C1=O","cipro":"OC(=O)C1=CN(C2CC2)c2cc(N3CCNCC3)c(F)cc2C1=O",
 "simvastatin":"CCC(C)(C)C(=O)OC1CC(C)C=C2C=CC(C)C(CCC3CC(O)CC(=O)O3)C12",
 "atorvastatin":"CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O",
 "lipitor":"CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O",
 "metoprolol":"CC(C)NCC(O)COc1ccc(CCOC)cc1","atenolol":"CC(C)NCC(O)COc1ccc(CC(N)=O)cc1",
 "labetalol":"CC(CCc1ccccc1)NCC(O)c1ccc(O)c(C(N)=O)c1","carvedilol":"COc1ccccc1OCCNCC(O)COc1cccc2[nH]c3ccccc3c12",
 "imatinib":"Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
 "dasatinib":"Cc1nc(Nc2ncc(C(=O)Nc3c(C)cccc3Cl)s2)cc(N2CCN(CCO)CC2)n1",
 "metformin":"CN(C)C(=N)NC(N)=N","clopidogrel":"COC(=O)C(c1ccccc1Cl)N1CCc2sccc2C1","plavix":"COC(=O)C(c1ccccc1Cl)N1CCc2sccc2C1",
 "ibuprofen":"CC(C)Cc1ccc(C(C)C(=O)O)cc1","naproxen":"COc1ccc2cc(C(C)C(=O)O)ccc2c1",
 "amiodarone":"CCCCc1oc2ccccc2c1C(=O)c1cc(I)c(OCCN(CC)CC)c(I)c1",
 "fluoxetine":"CNCCC(Oc1ccc(C(F)(F)F)cc1)c1ccccc1",
 "omeprazole":"COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1",
}

# ---------------------------------------------------------------- load data
print("[clinsift] loading pipeline data ...")
_emb = np.load(os.path.join(DATA, "molformer_embeddings.npz"))
EMB = {k: _emb[k].astype(np.float32) for k in _emb.keys()}
EMB_KEYS = list(EMB.keys())
EMB_MAT = np.stack([EMB[k] for k in EMB_KEYS])
EMB_NORM = EMB_MAT / (np.linalg.norm(EMB_MAT, axis=1, keepdims=True) + 1e-9)

def _load(fn, default):
    p = os.path.join(DATA, fn)
    try:
        return json.load(open(p))
    except FileNotFoundError:
        print(f"[clinsift] {fn} not present — related signals disabled (expected for public build)")
        return default

XR = _load("crossreactivity_similarity.json", [])
SE = _load("sideeffect_cohesion.json", [])
PA = _load("patient_allergies.json", {})          # patient-level: absent in public build
PCR = _load("patient_crossreactivity_refined.json", {})  # patient-level: absent in public build
PATIENT_DATA = bool(PA) and bool(PCR)

# indices ---------------------------------------------------------
IMMUNE = ["rash","hives","anaphyl","angioedema","urticaria","hypersensitiv","eruption","pruritus","allerg"]
def is_immune(s): return any(k in s.lower() for k in IMMUNE)

# drug -> cross-reactivity partners (observed, from EHR)
XR_BY_DRUG = {}
for r in XR:
    for a,b in ((r["drug_a"],r["drug_b"]),(r["drug_b"],r["drug_a"])):
        XR_BY_DRUG.setdefault(a,[]).append({"to":b,"sim":r["similarity"],"reactions":r["shared_reactions"]})

# drug -> side-effect clusters it belongs to (observed)
BASELINE = 0.656
SE_BY_DRUG = {}
for e in SE:
    if is_immune(e["reaction"]): continue      # immune handled as allergy
    for d in e["drugs"]:
        SE_BY_DRUG.setdefault(d,[]).append({"reaction":e["reaction"],"cohesion":e["cohesion"],"n":e["n_drugs"]})

# drug -> allergy cross-reactions (immune-filtered, patient-anchored)
ALL_BY_DRUG = {}
for rec in PCR.get("true_cross_reactivity", []):
    if not is_immune(rec["reaction"]): continue
    if rec["similarity"] < 0.70: continue
    a, b, rx, sim = rec["known_allergen"], rec["reacted_to"], rec["reaction"], rec["similarity"]
    ALL_BY_DRUG.setdefault(a,[]).append({"to":b,"reaction":rx,"sim":sim})
    ALL_BY_DRUG.setdefault(b,[]).append({"to":a,"reaction":rx,"sim":sim})

# allergen prevalence (patient counts) for provenance
ALLERGEN_COUNT = {}
for v in PA.values():
    for a in v.get("allergies", []):
        if a and a != "___": ALLERGEN_COUNT[a] = ALLERGEN_COUNT.get(a,0)+1

print(f"[clinsift] {len(EMB_KEYS)} embeddings | {len(XR_BY_DRUG)} xreact drugs | "
      f"{len(SE_BY_DRUG)} sidefx drugs | {len(ALL_BY_DRUG)} allergy drugs")

# ---------------------------------------------------------------- models
SSI = load_ssiddi(os.path.join(DATA, "ssiddi_best.pth"), DEVICE)
print("[clinsift] SSI-DDI checkpoint loaded")

MOLFORMER = None
MOLFORMER_LOCAL = os.path.join(os.path.dirname(__file__), "molformer_cache")

def get_molformer():
    global MOLFORMER
    if MOLFORMER == "unavailable": return None
    if MOLFORMER is not None: return MOLFORMER
    try:
        from transformers import AutoModel, AutoTokenizer
        # Try local cache first (avoids runtime download in HF Spaces)
        cache = MOLFORMER_LOCAL if os.path.exists(MOLFORMER_LOCAL) else None
        tok = AutoTokenizer.from_pretrained(
            "ibm/MoLFormer-XL-both-10pct",
            trust_remote_code=True,
            cache_dir=cache
        )
        mdl = AutoModel.from_pretrained(
            "ibm/MoLFormer-XL-both-10pct",
            deterministic_eval=True,
            trust_remote_code=True,
            cache_dir=cache
        ).eval()
        MOLFORMER = (tok, mdl)
        print("[clinsift] MoLFormer-XL loaded")
        return MOLFORMER
    except Exception as e:
        print(f"[clinsift] MoLFormer unavailable ({str(e)[:120]})")
        MOLFORMER = "unavailable"
        return None

def embed_smiles(smiles):
    m = get_molformer()
    if m is None: return None
    tok, mdl = m
    with torch.no_grad():
        inp = tok([smiles], padding=True, return_tensors="pt")
        out = mdl(**inp)
        return out.pooler_output[0].cpu().numpy().astype(np.float32)

def nearest_known(vec, k=6):
    v = vec / (np.linalg.norm(vec)+1e-9)
    sims = EMB_NORM @ v
    idx = np.argsort(-sims)[:k]
    return [(EMB_KEYS[i], float(sims[i])) for i in idx]

def ddi_smiles(sa, sb):
    ga, gb = smiles_to_graph(sa), smiles_to_graph(sb)
    if ga is None or gb is None: return None
    with torch.no_grad():
        return torch.sigmoid(SSI(Batch.from_data_list([ga]), Batch.from_data_list([gb]))).item()

def attribution_svg(smiles_a, smiles_b):
    """Heat-map the query molecule by which atoms drive the predicted interaction."""
    attr = SSI.attribution(smiles_a, smiles_b)
    if attr is None: return None
    mol = Chem.MolFromSmiles(smiles_a)
    imp = np.array(attr["a_atom_importance"], dtype=float)
    imp = (imp - imp.min()) / (imp.max() - imp.min() + 1e-9)
    hi, radii = {}, {}
    for i in range(mol.GetNumAtoms()):
        w = float(imp[i])
        hi[i] = (1.0, 1.0-0.55*w, 0.85-0.85*w) if w > 0.15 else (0.90, 0.96, 0.95)
        radii[i] = 0.3 + 0.35*w
    d = rdMolDraw2D.MolDraw2DSVG(340, 250)
    d.drawOptions().clearBackground = False
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol, highlightAtoms=list(range(mol.GetNumAtoms())),
        highlightAtomColors=hi, highlightAtomRadii=radii)
    d.FinishDrawing()
    top = int(np.argmax(imp))
    return {"prob": round(attr["prob"], 3), "svg": d.GetDrawingText(),
            "top_atoms": [{"idx": int(i), "symbol": mol.GetAtomWithIdx(int(i)).GetSymbol(),
                           "importance": round(float(imp[i]), 2)}
                          for i in np.argsort(-imp)[:5]]}

# ---------------------------------------------------------------- severity
def sev_xr(sim):        return "high" if sim>=0.85 else "mod" if sim>=0.70 else "none"
def sev_se(coh):        return "high" if coh>=0.80 else "mod" if coh>=BASELINE+0.05 else "none"
def sev_allergy(rx,sim):
    if any(w in rx.lower() for w in ["anaphyl","angioedema","severe"]): return "crit"
    return "high" if sim>=0.78 else "mod"
def sev_ddi(p):         return "high" if p>=0.70 else "mod" if p>=0.50 else "none"
RANK={"none":0,"mod":1,"high":2,"crit":3}
SEVN={"none":"Clear","mod":"Monitor","high":"Warning","crit":"Contraindication"}

def verdict_from(maxr):
    if maxr>=3: return "HOLD","block_pending_review","Contraindication-level signal — route for manual review before advancing."
    if maxr==2: return "FLAG","proceed_with_warning","Warning-level signal — proceed only with mitigation noted."
    if maxr==1: return "FLAG","monitor","Monitor-level signal — advance with monitoring."
    return "PASS","advance","No adverse signal above threshold in the evidence base."

def cat(key,name,sub,api,items): return {"key":key,"name":name,"sub":sub,"api":api,"items":items}
def catsev(items): return max([0]+[RANK[i["sev"]] for i in items])

# ---------------------------------------------------------------- assemble
def known_drug(name):
    n = name.lower().strip()
    # cross-reactivity (observed)
    xr=[]
    seen=set()
    for r in sorted(XR_BY_DRUG.get(n,[]), key=lambda x:-x["sim"]):
        if r["to"] in seen: continue
        seen.add(r["to"])
        s=sev_xr(r["sim"])
        if s=="none": continue
        xr.append({"find":"Structural cross-reactivity","to":r["to"],
                   "note":"Shares reaction ("+", ".join(r["reactions"][:2])+") with a structurally similar drug.",
                   "ev":"observed","pt":ALLERGEN_COUNT.get(r["to"],ALLERGEN_COUNT.get(n,0)),
                   "conf":round(r["sim"],2),"src":"MoLFormer + EHR","sev":s})
    # side effects (observed)
    se=[]
    for r in sorted(SE_BY_DRUG.get(n,[]), key=lambda x:-x["cohesion"])[:5]:
        s=sev_se(r["cohesion"])
        if s=="none": continue
        se.append({"find":r["reaction"].capitalize(),"to":None,
                   "note":f"Structurally cohesive class effect (cohesion {r['cohesion']:.2f} vs {BASELINE:.2f} baseline, n={r['n']}).",
                   "ev":"observed","pt":r["n"],"conf":round(r["cohesion"],2),"src":"cohesion analysis","sev":s})
    # allergy (observed, patient-anchored, immune)
    al=[]; seen=set()
    for r in sorted(ALL_BY_DRUG.get(n,[]), key=lambda x:-x["sim"]):
        if r["to"] in seen: continue
        seen.add(r["to"])
        s=sev_allergy(r["reaction"],r["sim"])
        al.append({"find":"Immune cross-reaction","to":r["to"],
                   "note":f"Patient allergic to one reacted to the other ({r['reaction']}).",
                   "ev":"observed","pt":ALLERGEN_COUNT.get(n,ALLERGEN_COUNT.get(r["to"],1)),
                   "conf":round(r["sim"],2),"src":"patient history + MoLFormer","sev":s})
    cats=[cat("ddi","Drug–drug interactions","co-administration risk","drug_drug_interaction",[]),
          cat("xreact","Cross-reactivity","structural / class","cross_reactivity",xr),
          cat("side","Adverse effects","class & dose-driven","adverse_effect",se),
          cat("allergy","Allergy cross-reaction","patient immune history","allergy_cross_reaction",al)]
    meta = "in EHR evidence base"
    return finalize({"name":name,"meta":meta,"pair":False}, cats, "known")

def pair(a,b):
    A,B=a.lower().strip(),b.lower().strip()
    ddi=[]
    if A in SMILES and B in SMILES:
        p=ddi_smiles(SMILES[A],SMILES[B])
        if p is not None:
            s=sev_ddi(p)
            if s!="none":
                ddi.append({"find":"Predicted interaction","to":B,
                            "note":"SSI-DDI substructure-interaction model score.",
                            "ev":"predicted","pt":0,"conf":round(p,2),"src":"SSI-DDI (AUC~0.79)","sev":s})
    # allergy / xreact between the specific pair (observed)
    al=[]
    for r in ALL_BY_DRUG.get(A,[]):
        if r["to"]==B:
            al.append({"find":"Immune cross-reaction","to":B,"note":f"Patient-anchored: {r['reaction']}.",
                       "ev":"observed","pt":ALLERGEN_COUNT.get(A,1),"conf":round(r["sim"],2),
                       "src":"patient history","sev":sev_allergy(r["reaction"],r["sim"])})
    xr=[]
    for r in XR_BY_DRUG.get(A,[]):
        if r["to"]==B:
            s=sev_xr(r["sim"])
            if s!="none":
                xr.append({"find":"Structural cross-reactivity","to":B,
                           "note":"Shares reaction ("+", ".join(r["reactions"][:2])+").",
                           "ev":"observed","pt":0,"conf":round(r["sim"],2),"src":"MoLFormer + EHR","sev":s})
    cats=[cat("ddi","Drug–drug interactions","co-administration risk","drug_drug_interaction",ddi),
          cat("xreact","Cross-reactivity","structural / class","cross_reactivity",xr),
          cat("side","Adverse effects","class & dose-driven","adverse_effect",[]),
          cat("allergy","Allergy cross-reaction","patient immune history","allergy_cross_reaction",al)]
    return finalize({"name":f"{a} + {b}","meta":"co-administration","pair":True}, cats, "pair")

def novel(smiles, name=None):
    vec = embed_smiles(smiles)
    xr=[]; se=[]; analogs=[]
    molformer_ok = vec is not None
    if molformer_ok:
        analogs = nearest_known(vec, k=6)
        top = analogs[0]
        for kn, sim in analogs:
            if sim < 0.70: continue
            # bridge to that analog's observed reactions
            for r in SE_BY_DRUG.get(kn, [])[:2]:
                se.append({"find":r["reaction"].capitalize(),"to":None,
                           "note":f"Resembles {kn} (sim {sim:.2f}), which shows this as a class effect.",
                           "ev":"predicted","pt":0,"conf":round(sim,2),"src":"MoLFormer analog bridge",
                           "sev":sev_se(r["cohesion"]) if sev_se(r["cohesion"])!="none" else "mod"})
            for r in XR_BY_DRUG.get(kn, [])[:1]:
                xr.append({"find":"Predicted cross-reactivity","to":f"{kn}-class",
                           "note":f"Structurally near {kn} (sim {sim:.2f}); inherits its cross-reactivity profile.",
                           "ev":"predicted","pt":0,"conf":round(sim,2),"src":"MoLFormer","sev":sev_xr(sim)})
            break  # top analog only for xreact headline
    # DDI vs a few common known drugs (predicted)
    ddi=[]
    for partner in ["warfarin","aspirin","simvastatin","clopidogrel"]:
        p=ddi_smiles(smiles, SMILES[partner])
        if p is None: continue
        s=sev_ddi(p)
        if s=="none": continue
        ddi.append({"find":"Predicted interaction","to":partner,
                    "note":"SSI-DDI score against a common co-medication.",
                    "ev":"predicted","pt":0,"conf":round(p,2),"src":"SSI-DDI (AUC~0.79)","sev":s})
    ddi.sort(key=lambda x:-x["conf"]); ddi=ddi[:3]
    # substructure attribution for the top predicted interaction
    attribution=None
    if ddi:
        top_partner=ddi[0]["to"]
        attribution=attribution_svg(smiles, SMILES[top_partner])
        if attribution: attribution["partner"]=top_partner
    # allergy unavailable for novel compounds
    allergy_note=[{"find":"Requires patient history","to":None,
                   "note":"Allergy cross-reactivity is patient-anchored and unavailable for a compound not yet in the clinical record.",
                   "ev":"predicted","pt":0,"conf":0.0,"src":"—","sev":"none"}]
    cats=[cat("ddi","Drug–drug interactions","predicted (SSI-DDI)","drug_drug_interaction",ddi),
          cat("xreact","Cross-reactivity","structural analog","cross_reactivity",xr),
          cat("side","Adverse effects","analog class effects","adverse_effect",se),
          cat("allergy","Allergy cross-reaction","patient immune history","allergy_cross_reaction",
              [] if molformer_ok else [])]
    label = name or "Novel compound"
    meta = (f"nearest known: {analogs[0][0]} ({analogs[0][1]:.2f})" if analogs else "structural screen")
    res = finalize({"name":label,"meta":meta,"pair":False}, cats, "novel")
    res["molformer_available"]=molformer_ok
    res["allergy_status"]="unavailable_novel_compound"
    res["attribution"]=attribution
    return res

def finalize(subject, cats, mode):
    maxr=max([0]+[catsev(c["items"]) for c in cats])
    v,action,reason=verdict_from(maxr)
    # flat signal list for API
    signals=[]
    for c in cats:
        for it in c["items"]:
            if it["sev"]=="none": continue
            signals.append({"category":c["api"],"severity":it["sev"],
                            "finding":it["find"]+(" → "+it["to"] if it["to"] else ""),
                            "evidence":it["ev"],"patient_support":it["pt"] if it["ev"]=="observed" else 0,
                            "confidence":it["conf"]})
    return {"query":subject["name"],"mode":mode,"subject":subject,
            "verdict":v,"gate_action":action,"max_severity":["none","mod","high","crit"][maxr],
            "reason":reason,"categories":cats,"signals":signals,
            "provenance":"patient-level RWE · MIMIC clinical notes","molformer_available":True,
            "allergy_available":PATIENT_DATA}

# ---------------------------------------------------------------- API
app = FastAPI(title="ClinSift")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ScreenReq(BaseModel):
    drug: str | None = None
    drug_a: str | None = None
    drug_b: str | None = None
class SmilesReq(BaseModel):
    smiles: str
    name: str | None = None

@app.get("/health")
def health(): return {"ok":True,"drugs":len(EMB_KEYS),"molformer":MOLFORMER not in (None,"unavailable"),
                      "patient_data":PATIENT_DATA}

@app.post("/screen")
def screen(r: ScreenReq):
    if r.drug_a and r.drug_b: return pair(r.drug_a, r.drug_b)
    if r.drug: return known_drug(r.drug)
    return {"error":"provide drug or drug_a+drug_b"}

@app.post("/screen_smiles")
def screen_smiles(r: SmilesReq):
    if smiles_to_graph(r.smiles) is None:
        return {"error":f"invalid SMILES: {r.smiles}"}
    return novel(r.smiles, r.name)

class PairReq(BaseModel):
    a: str
    b: str

from cyp_ddi import cyp_interactions, known_to_cyp

def _resolve(tok):
    """Return (smiles_or_None, label, is_known). Known drug w/o SMILES still resolves
    (label kept) so CYP (name-based) can fire even when structural DDI can't."""
    t = tok.strip()
    if t.lower() in SMILES:
        return SMILES[t.lower()], t.lower(), True
    if smiles_to_graph(t) is not None:
        return t, "novel compound", False
    if known_to_cyp(t):                 # known drug we lack a SMILES for -> CYP-only
        return None, t.lower(), True
    return None, t, False

def _sevrank(s): return {"none":0,"mod":1,"high":2,"crit":3}.get(s,0)

@app.post("/screen_pair")
def screen_pair(r: PairReq):
    sa, la, ka = _resolve(r.a)
    sb, lb, kb = _resolve(r.b)
    if la in (None,"") or (sa is None and not ka):
        return {"error": f"unrecognized (not a SMILES or known drug): {r.a}"}
    if lb in (None,"") or (sb is None and not kb):
        return {"error": f"unrecognized (not a SMILES or known drug): {r.b}"}

    # --- mechanism 1: structural (SSI-DDI), only if both have SMILES ---
    structural = None; attribution = None
    if sa is not None and sb is not None:
        p = ddi_smiles(sa, sb)
        if p is not None:
            ssev = "high" if p>=0.70 else "mod" if p>=0.50 else "none"
            structural = {"prob": round(p,3), "severity": ssev,
                          "note": "SSI-DDI structural interaction model (~0.79 AUC)"}
            attribution = attribution_svg(sa, sb)

    # --- mechanism 2: CYP450 (PK), name-based ---
    cyp = cyp_interactions(r.a, r.b)
    cyp_sev = max([_sevrank(h["severity"]) for h in cyp], default=0)

    # --- mechanism 3: CYP450 inhibition PREDICTED (QSAR) for novel compounds ---
    predicted_cyp = []; predicted_profiles = None
    try:
        import cyp_predict
        if cyp_predict.available():
            if (not ka) and kb and sa is not None:          # novel a x known b
                predicted_cyp = cyp_predict.cyp_interactions_predicted(sa, lb)
            elif ka and (not kb) and sb is not None:        # known a x novel b
                predicted_cyp = cyp_predict.cyp_interactions_predicted(sb, la)
            elif (not ka) and (not kb):                     # novel x novel: profiles only
                predicted_profiles = {
                    "a": cyp_predict.predicted_profile(sa) if sa is not None else None,
                    "b": cyp_predict.predicted_profile(sb) if sb is not None else None,
                }
    except Exception:
        predicted_cyp = []; predicted_profiles = None
    pred_sev = max([_sevrank(h["severity"]) for h in predicted_cyp], default=0)

    # --- combine: verdict = worst mechanism ---
    struct_rank = _sevrank(structural["severity"]) if structural else 0
    overall = max(struct_rank, cyp_sev, pred_sev)
    verdict = ["PASS","FLAG","FLAG","HOLD"][overall]
    action  = ["advance","monitor","proceed_with_warning","block_pending_review"][overall]
    mechs = []
    if structural and structural["severity"]!="none": mechs.append("structural")
    if cyp: mechs.append("pharmacokinetic (CYP450)")
    if predicted_cyp: mechs.append("pharmacokinetic (CYP450, predicted)")

    both_novel = (not ka) and (not kb)
    return {
        "compound_a": la, "compound_b": lb, "a_known": ka, "b_known": kb,
        "verdict": verdict, "gate_action": action,
        "max_severity": ["none","mod","high","crit"][overall],
        "mechanisms": mechs or ["none above threshold"],
        "structural": structural,          # SSI-DDI score (or null if a compound lacked SMILES)
        "cyp_interactions": cyp,           # list of enzyme-mediated PK interactions
        "predicted_cyp_interactions": predicted_cyp,   # QSAR-predicted (novel compounds)
        "predicted_cyp_profiles": predicted_profiles,  # novel x novel: inhibition profiles only
        "attribution": attribution,
        "note": ("novel×novel is the least-validated case — treat as directional"
                 if both_novel else "mechanism-aware: structural (SSI-DDI) + CYP450 (PK)"),
        "model": "SSI-DDI + CYP450 knowledge base",
    }

# serve the UI at "/" (same-origin: the page talks to this same backend)
from fastapi.responses import FileResponse, HTMLResponse
@app.get("/", response_class=HTMLResponse)
def home():
    p = os.path.join(os.path.dirname(__file__), "ui.html")
    return FileResponse(p) if os.path.exists(p) else HTMLResponse("<h1>ClinSift API</h1>")
