"""
Inference Bench - ModelNet10 multi-view CNN + live visual-hull reconstruction.
Hugging Face Space (Gradio 6, PyTorch).

Model: the exported winner from the notebook - the best pretrained baseline
(DenseNet121) with a customised classifier head, fully fine-tuned. The architecture is
rebuilt from the "arch" string inside best_model.pt, so the app tracks whatever was exported.
"""
import os
import glob
import re
import tempfile
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torchvision import models
import gradio as gr

try:
    import trimesh
    _HAS_TRIMESH = True
except Exception:
    _HAS_TRIMESH = False

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MESH_DIR = "meshes"
# Folders scanned for ready-made sample objects (first one that yields results wins).
SAMPLE_DIRS = ["examples", "samples", "example"]
# Light material so the carved hull stands out against the dark viewport.
HULL_RGBA = [173, 196, 255, 255]

ckpt = torch.load("best_model.pt", map_location=DEVICE, weights_only=False)
CLASSES = ckpt["classes"]
IMG_SIZE = ckpt.get("img_size", 224)
ARCH = ckpt.get("arch", "Custom-DenseNet121-FT")
N_CLASSES = len(CLASSES)


# ---------------- model (must match the training notebook) ----------------
def custom_head(feat, n):
    return nn.Sequential(
        nn.Flatten(),
        nn.BatchNorm1d(feat),
        nn.Dropout(0.4),
        nn.Linear(feat, 256), nn.ReLU(inplace=True),
        nn.Dropout(0.3),
        nn.Linear(256, n))


def plain_head(feat, n):
    return nn.Sequential(nn.Dropout(0.3), nn.Linear(feat, n))


def build_model(arch, n):
    is_custom = arch.startswith("Custom")
    head = custom_head if is_custom else plain_head
    if "DenseNet121" in arch:
        m = models.densenet121(weights=None)
        m.classifier = head(m.classifier.in_features, n)
    elif "ResNet50" in arch:
        m = models.resnet50(weights=None)
        m.fc = head(m.fc.in_features, n)
    elif "EfficientNetB0" in arch:
        m = models.efficientnet_b0(weights=None)
        m.classifier = head(m.classifier[1].in_features, n)
    elif "VGG16" in arch:
        m = models.vgg16(weights=None)
        m.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        m.classifier = (custom_head(512, n) if is_custom
                        else nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(512, n)))
    else:
        raise ValueError(f"Unhandled architecture in checkpoint: {arch}")
    return m


model = build_model(ARCH, N_CLASSES)
model.load_state_dict(ckpt["state_dict"])
model.to(DEVICE).eval()
N_PARAMS = sum(p.numel() for p in model.parameters())
print(f"Loaded {ARCH} | {N_PARAMS:,} params | {N_CLASSES} classes | {DEVICE}")

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _open(f):
    return Image.open(f.name if hasattr(f, "name") else f)


def _reference_mesh(cls):
    p = os.path.join(MESH_DIR, f"{cls}.obj")
    return p if os.path.exists(p) else None


def _views_in(dirpath):
    return sorted(glob.glob(os.path.join(dirpath, "*.png")) + glob.glob(os.path.join(dirpath, "*.jpg")))


def find_samples():
    """Discover ready-made sample objects shipped with the Space.

    Supports two layouts:
      examples/<class>/*.png              (one folder per object)
      examples/chair_0925_v0.png ...      (flat, grouped by the name before _v<N>)
    Returns {label: [view paths]} so nothing has to be uploaded by hand.
    """
    for base in SAMPLE_DIRS:
        if not os.path.isdir(base):
            continue
        found = {}

        # layout A - one subfolder per object
        for name in sorted(os.listdir(base)):
            d = os.path.join(base, name)
            if os.path.isdir(d):
                views = _views_in(d)[:4]
                if len(views) >= 2:
                    found[name] = views

        # layout B - flat files grouped by stem before _v<N>
        if not found:
            groups = {}
            for p in _views_in(base):
                stem = re.sub(r"_v\d+$", "", os.path.splitext(os.path.basename(p))[0], flags=re.I)
                groups.setdefault(stem, []).append(p)
            for stem, views in groups.items():
                if len(views) >= 2:
                    found[stem] = sorted(views)[:4]

        if found:
            print(f"Samples: {len(found)} object(s) from '{base}/'")
            return dict(sorted(found.items()))
    print("Samples: none found (add an 'examples/' folder to the Space)")
    return {}


SAMPLES = find_samples()


def load_sample(name):
    """Return a sample object's view paths, ready to drop into the file input."""
    paths = SAMPLES.get(name, [])
    return paths, paths


# ---------------- classification ----------------
def _preprocess(img):
    img = img.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)


@torch.no_grad()
def _softmax(img):
    x = _preprocess(img).to(DEVICE)
    return torch.softmax(model(x), dim=1)[0].cpu().numpy()


def _chip(v, agree):
    colour = "#36c2a0" if agree else "#e0a526"
    return (f"<div class='ib-chip'><div class='ib-chip-k'>{v[0]}</div>"
            f"<div class='ib-chip-v' style='color:{colour}'>{v[1]}</div></div>")


def classify(files):
    if not files:
        return {}, "<div class='ib-muted'>Upload the four azimuth views, or pick a sample.</div>", None
    probs, per_view = [], []
    for f in files:
        p = _softmax(_open(f))
        probs.append(p)
        per_view.append(CLASSES[int(p.argmax())])
    avg = np.mean(probs, axis=0)
    conf = {CLASSES[i]: float(avg[i]) for i in range(N_CLASSES)}
    top = CLASSES[int(np.argmax(avg))]
    n_agree = sum(1 for v in per_view if v == top)

    labels = ["V0-0", "V1-90", "V2-180", "V3-270"]
    chips = "".join(_chip((labels[i] if i < 4 else f"V{i}", per_view[i]), per_view[i] == top)
                    for i in range(len(per_view)))
    html = (f"<div class='ib-sec'>PER-VIEW VOTING"
            f"<span class='ib-right'>{n_agree}/{len(per_view)} agree</span></div>"
            f"<div class='ib-chips'>{chips}</div>"
            f"<div class='ib-muted' style='margin-top:10px'>softmax averaged across "
            f"{len(per_view)} view(s) &middot; predicted <b style='color:#8b8bf7'>{top}</b> "
            f"at {avg.max()*100:.1f}%</div>")
    return conf, html, _reference_mesh(top)


# ---------------- 3D: shape-from-silhouette (visual hull) ----------------
def _silhouette(img, size=128):
    g = np.asarray(img.convert("L").resize((size, size)), dtype=np.float32)
    border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
    bg = np.median(border)
    return np.abs(g - bg) > 18


def _carve(masks, res=64):
    lin = np.linspace(-1, 1, res)
    X, Y, Z = np.meshgrid(lin, lin, lin, indexing="ij")
    occ = np.ones((res, res, res), bool)
    for m, az in zip(masks, [0, 90, 180, 270][:len(masks)]):
        H, W = m.shape
        t = np.radians(az)
        u = X * np.cos(t) + Z * np.sin(t)
        v = Y
        col = np.clip(((u + 1) / 2 * (W - 1)).astype(int), 0, W - 1)
        row = np.clip(((1 - v) / 2 * (H - 1)).astype(int), 0, H - 1)
        occ &= m[row, col]
    return occ


def _occ_to_mesh(occ):
    """Turn the occupancy grid into triangles by keeping only exposed voxel faces."""
    res = occ.shape[0]
    s = 2.0 / res
    verts, tris, vidx = [], [], {}

    def vert(p):
        if p not in vidx:
            vidx[p] = len(verts)
            verts.append(p)
        return vidx[p]

    dirs = [((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
            ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
            ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
            ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
            ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
            ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)])]
    occset = set(map(tuple, np.argwhere(occ)))
    for (i, j, k) in occset:
        for d, corners in dirs:
            if (i + d[0], j + d[1], k + d[2]) in occset:
                continue                                  # interior face, skip
            q = [vert((round(-1 + (i + c[0]) * s, 4),
                       round(-1 + (j + c[1]) * s, 4),
                       round(-1 + (k + c[2]) * s, 4))) for c in corners]
            tris.append([q[0], q[1], q[2]])               # quad -> 2 triangles
            tris.append([q[0], q[2], q[3]])
    return np.array(verts, dtype=float), np.array(tris, dtype=np.int64)


def _export_mesh(occ):
    """Export the hull. GLB carries an explicit light material so it is visible in a dark
    viewport; plain OBJ has no material and renders near-black. OBJ is the fallback."""
    V, F = _occ_to_mesh(occ)
    if _HAS_TRIMESH:
        m = trimesh.Trimesh(vertices=V, faces=F, process=False)
        m.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=HULL_RGBA, metallicFactor=0.0, roughnessFactor=0.55))
        path = tempfile.mktemp(suffix=".glb")
        m.export(path)
        return path, len(F)
    path = tempfile.mktemp(suffix=".obj")
    with open(path, "w") as fh:
        for x, y, z in V:
            fh.write(f"v {x} {y} {z}\n")
        for a, b, c in F:
            fh.write(f"f {a+1} {b+1} {c+1}\n")
    return path, len(F)


def reconstruct_3d(files):
    if not files or len(files) < 2:
        return None, ("<div class='ib-muted'>Need at least 2 views "
                      "(4 works best: azimuth 0/90/180/270).</div>")
    masks = [_silhouette(_open(f)) for f in files[:4]]
    occ = _carve(masks, res=64)
    if int(occ.sum()) < 20:
        return None, ("<div class='ib-muted'>Could not carve a shape - the silhouettes are unclear. "
                      "Works best on clean renders with a plain background.</div>")
    path, nf = _export_mesh(occ)
    stats = (f"<div class='ib-stats'>"
             f"<div class='ib-stat'><span>voxels</span><b>{int(occ.sum()):,}</b></div>"
             f"<div class='ib-stat'><span>faces</span><b>{nf:,}</b></div>"
             f"<div class='ib-stat'><span>grid</span><b>64&sup3;</b></div></div>"
             f"<div class='ib-muted' style='margin-top:8px'>Visual hull from {len(masks)} views. "
             f"Outer shape only &mdash; concavities are not captured.</div>")
    return path, stats


# ---------------- static HTML ----------------
HEADER = f"""
<div class='ib-header'>
  <div class='ib-brand'>
    <div class='ib-logo'>&#9635;</div>
    <div>
      <div class='ib-title'>Inference Bench</div>
      <div class='ib-sub'>ModelNet10 &middot; multi-view CNN + live visual-hull reconstruction</div>
    </div>
  </div>
  <div class='ib-badges'>
    <span class='ib-badge ib-badge-on'>&bull; {ARCH}</span>
    <span class='ib-badge'>{N_PARAMS/1e6:.2f}M params</span>
    <span class='ib-badge'>test acc <b>91.0%</b></span>
    <span class='ib-badge'>device {DEVICE.upper()}</span>
  </div>
</div>
"""

ARCH_STRIP = """
<div class='ib-card ib-arch'>
  <div class='ib-sec'>ARCHITECTURE</div>
  <div class='ib-arch-title'>Custom-DenseNet121 &mdash; pretrained backbone + customised head</div>
  <div class='ib-flow'>
    <div class='ib-blk'><span>INPUT</span><b>Input</b><i>RGB render</i><u>224&middot;224&middot;3</u></div>
    <div class='ib-blk'><span>STEM</span><b>Conv7&times;7</b><i>stride 2 + maxpool</i><u>56&middot;56&middot;64</u></div>
    <div class='ib-blk'><span>DENSE 1</span><b>Block 1</b><i>6 layers, k=32</i><u>56&middot;56&middot;256</u></div>
    <div class='ib-blk'><span>DENSE 2</span><b>Block 2</b><i>12 layers</i><u>28&middot;28&middot;512</u></div>
    <div class='ib-blk'><span>DENSE 3</span><b>Block 3</b><i>24 layers</i><u>14&middot;14&middot;1024</u></div>
    <div class='ib-blk'><span>DENSE 4</span><b>Block 4</b><i>16 layers</i><u>7&middot;7&middot;1024</u></div>
    <div class='ib-blk'><span>POOL</span><b>GAP</b><i>global average</i><u>1024</u></div>
    <div class='ib-blk ib-blk-c'><span>CUSTOM</span><b>BN + FC-256</b><i>drop .4 &rarr; ReLU &rarr; drop .3</i><u>256</u></div>
    <div class='ib-blk ib-blk-c'><span>CUSTOM</span><b>FC-10</b><i>class logits</i><u>10</u></div>
    <div class='ib-blk ib-blk-o'><span>OUTPUT</span><b>Softmax</b><i>voted across views</i><u>10 probs</u></div>
  </div>
</div>
"""

CSS = """
.gradio-container{background:#0b0e17 !important;max-width:1500px !important;}
footer{display:none !important;}
.ib-header{display:flex;justify-content:space-between;align-items:center;gap:16px;
  padding:14px 18px;margin-bottom:6px;background:#111524;border:1px solid #222839;border-radius:14px;}
.ib-brand{display:flex;align-items:center;gap:12px;}
.ib-logo{width:38px;height:38px;border-radius:10px;background:#6366f1;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:18px;}
.ib-title{font-size:17px;font-weight:700;color:#e6ebf5;}
.ib-sub{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#6e7891;margin-top:2px;}
.ib-badges{display:flex;gap:8px;flex-wrap:wrap;}
.ib-badge{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#9aa4bd;
  background:#161b2b;border:1px solid #262d42;border-radius:999px;padding:5px 11px;}
.ib-badge-on{color:#36c2a0;border-color:#1f4d40;}
.ib-badge b{color:#e6ebf5;}
.ib-card{background:#111524 !important;border:1px solid #222839 !important;border-radius:14px !important;
  padding:14px !important;}
.ib-sec{font-family:ui-monospace,Consolas,monospace;font-size:10.5px;letter-spacing:.14em;
  color:#6e7891;text-transform:uppercase;margin-bottom:10px;}
.ib-right{float:right;color:#36c2a0;letter-spacing:0;}
.ib-muted{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:#6e7891;line-height:1.6;}
.ib-chips{display:flex;gap:8px;flex-wrap:wrap;}
.ib-chip{flex:1;min-width:78px;background:#0f1626;border:1px solid #1e2a3f;border-radius:9px;
  padding:9px 8px;text-align:center;}
.ib-chip-k{font-family:ui-monospace,Consolas,monospace;font-size:9.5px;color:#5b6480;letter-spacing:.08em;}
.ib-chip-v{font-size:12.5px;font-weight:700;margin-top:3px;}
.ib-stats{display:flex;gap:8px;}
.ib-stat{flex:1;background:#0f1626;border:1px solid #1e2a3f;border-radius:9px;padding:8px 10px;}
.ib-stat span{display:block;font-family:ui-monospace,Consolas,monospace;font-size:9.5px;color:#5b6480;}
.ib-stat b{color:#e6ebf5;font-size:13px;}
.ib-arch-title{font-size:14px;font-weight:700;color:#e6ebf5;margin-bottom:12px;}
.ib-flow{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;}
.ib-blk{min-width:118px;flex:1;background:#0f1626;border:1px solid #222c42;border-radius:10px;padding:9px;}
.ib-blk span{font-family:ui-monospace,Consolas,monospace;font-size:9px;color:#5b6480;letter-spacing:.1em;}
.ib-blk b{display:block;color:#e6ebf5;font-size:12.5px;margin-top:4px;}
.ib-blk i{display:block;font-style:normal;font-size:10.5px;color:#6e7891;margin-top:3px;line-height:1.4;}
.ib-blk u{display:block;text-decoration:none;font-family:ui-monospace,Consolas,monospace;
  font-size:9.5px;color:#4e88f5;margin-top:7px;border-top:1px solid #1c2437;padding-top:5px;}
.ib-blk-c{border-color:#3b3596;background:#141334;}
.ib-blk-c u{color:#8b8bf7;border-top-color:#2c2a63;}
.ib-blk-o{border-color:#1f4d40;background:#0d2320;}
.ib-blk-o u{color:#36c2a0;border-top-color:#1b3f36;}
"""

DARK = gr.themes.Base(
    primary_hue=gr.themes.Color("#eef0ff", "#dcdffb", "#c3c6f8", "#a5a9f4", "#8b8bf7",
                                "#6366f1", "#4f46e5", "#4338ca", "#3730a3", "#312e81", "#1e1b4b"),
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "Consolas", "monospace"],
).set(
    body_background_fill="#0b0e17",
    body_text_color="#e6ebf5",
    block_background_fill="#111524",
    block_border_color="#222839",
    block_label_text_color="#6e7891",
    block_title_text_color="#9aa4bd",
    input_background_fill="#0f1626",
    border_color_primary="#222839",
    button_primary_background_fill="#6366f1",
    button_primary_text_color="#ffffff",
    button_secondary_background_fill="#10241f",
    button_secondary_text_color="#36c2a0",
    button_secondary_border_color="#1f4d40",
)

# ---------------- UI ----------------
with gr.Blocks(title="Inference Bench - ModelNet10") as demo:
    gr.HTML(HEADER)
    with gr.Row(equal_height=False):
        # ---- INPUT ----
        with gr.Column(scale=3, elem_classes="ib-card"):
            gr.HTML("<div class='ib-sec'>INPUT</div>"
                    "<div style='font-size:14px;font-weight:700;color:#e6ebf5;margin:-4px 0 8px'>"
                    "Four azimuth views</div>")
            files = gr.File(file_count="multiple", file_types=["image"], label="0 / 90 / 180 / 270 deg")
            gallery = gr.Gallery(label="Loaded views", columns=4, height=140, show_label=False)
            if SAMPLES:
                gr.HTML("<div class='ib-sec' style='margin-top:12px'>OR LOAD A SAMPLE OBJECT"
                        "<span class='ib-right'>no upload needed</span></div>")
                sample_dd = gr.Dropdown(choices=list(SAMPLES.keys()),
                                        value=list(SAMPLES.keys())[0],
                                        label="Sample object", filterable=True)
                btn_load = gr.Button("Load sample views", variant="secondary")
            else:
                gr.HTML("<div class='ib-muted' style='margin-top:10px'>No samples found. Add an "
                        "<code>examples/</code> folder to the Space, either as "
                        "<code>examples/chair/*.png</code> or flat files named "
                        "<code>chair_0925_v0.png</code>, and they appear here automatically.</div>")
            btn_cls = gr.Button("Classify object", variant="primary")
            btn_3d = gr.Button("Reconstruct 3D", variant="secondary")

        # ---- PREDICTION ----
        with gr.Column(scale=4, elem_classes="ib-card"):
            gr.HTML("<div class='ib-sec'>PREDICTION<span class='ib-right'>"
                    "softmax &middot; multi-view voted</span></div>")
            label = gr.Label(num_top_classes=3, label="Predicted class")
            vote_html = gr.HTML("<div class='ib-muted'>Upload the four azimuth views, "
                                "or pick a sample.</div>")

        # ---- 3D ----
        with gr.Column(scale=4, elem_classes="ib-card"):
            gr.HTML("<div class='ib-sec'>3D RECONSTRUCTION<span class='ib-right'>"
                    "shape-from-silhouette</span></div>")
            hull3d = gr.Model3D(label="Visual hull (carved from the four views)",
                                clear_color=(0.09, 0.12, 0.18, 1.0), height=300)
            stats_html = gr.HTML("<div class='ib-muted'>Carved live in the backend from the four "
                                 "silhouettes. Press <b>Reconstruct 3D</b>.</div>")
            ref3d = gr.Model3D(label="Reference mesh of predicted class",
                               clear_color=(0.09, 0.12, 0.18, 1.0), height=200)

    gr.HTML(ARCH_STRIP)

    files.change(lambda f: [x.name if hasattr(x, "name") else x for x in f] if f else [],
                 inputs=files, outputs=gallery)
    if SAMPLES:
        btn_load.click(load_sample, inputs=sample_dd, outputs=[files, gallery])
    btn_cls.click(classify, inputs=files, outputs=[label, vote_html, ref3d])
    btn_3d.click(reconstruct_3d, inputs=files, outputs=[hull3d, stats_html])

if __name__ == "__main__":
    demo.launch(theme=DARK, css=CSS)
