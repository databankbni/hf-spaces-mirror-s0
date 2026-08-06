---
title: ClinSift
emoji: 🧪
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# ClinSift — real-world drug-safety filter

Screens a drug or a novel compound against adverse-event signals and returns a
single **gate decision** (PASS / FLAG / HOLD) for a drug-development pipeline.
The UI and the API are one deployment: open the Space and it talks to its own backend.

- **Known drug** → observed cross-reactivity & class side-effects (from EHR-derived signals)
- **Novel compound (SMILES)** → SSI-DDI interaction prediction + **substructure attribution**
  (which atoms drive the interaction) + nearest known drugs via MoLFormer-XL
- Every response is also a JSON contract a pipeline can gate on programmatically

The interaction model is a proof-of-concept (SSI-DDI, ~0.79 AUC on a public
BIOSNAP subset). Outputs are predictions, not clinical advice.

---

## ⚠️ DATA-USE COMPLIANCE — read before making this public

This public build ships **only** non-patient artifacts:
`molformer_embeddings.npz`, `ssiddi_best.pth`, and the aggregate
`crossreactivity_similarity.json` / `sideeffect_cohesion.json` (population-level,
no patient identifiers).

It **excludes** the patient-level MIMIC-derived files
(`patient_allergies.json`, `patient_crossreactivity_refined.json`, which contain
note IDs). MIMIC's PhysioNet Data Use Agreement **prohibits public redistribution**
of patient-level derivatives. `.gitignore` blocks these from being committed.

- **Public Space:** leave those files out. Allergy cross-reactivity shows
  "requires patient data" — that is correct and expected.
- **Private Space (only if your DUA permits):** set the Space to *private*, then
  add the two files to `data/`. Confirm with your PhysioNet DUA / data steward first.

---

## Run locally
```bash
pip install -r requirements.txt
uvicorn app:app --port 8000
# open http://localhost:8000
```

## Deploy to your HuggingFace account
You run these (they need your HF login; never share your token):
```bash
pip install huggingface_hub
huggingface-cli login            # paste your WRITE token when prompted

# create a Docker Space under your account
huggingface-cli repo create clinsift --type space --space_sdk docker

# push this folder
git init && git lfs install
git lfs track "*.npz" "*.pth"
git add .gitignore .gitattributes
git add Dockerfile requirements.txt README.md app.py ssiddi_model.py ui.html data/
git commit -m "ClinSift: real-world drug-safety filter"
git remote add origin https://huggingface.co/spaces/<your-username>/clinsift
git push origin main
```
Large files (`.npz`, `.pth`) go through Git LFS — the `git lfs track` step above
handles that. First screen of a SMILES downloads MoLFormer-XL (~200 MB) once.

## API
```
GET  /health
POST /screen         {"drug":"penicillin"}
POST /screen         {"drug_a":"warfarin","drug_b":"clopidogrel"}
POST /screen_smiles  {"smiles":"CC1=C(...)","name":"CWR-001"}
```
