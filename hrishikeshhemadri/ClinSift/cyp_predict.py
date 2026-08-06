"""
ClinSift DDI mechanism layer — TIER 1b: CYP450 inhibition PREDICTION (QSAR).

Closes the gap Tier 1 (curated lookup) is blind to: a truly NOVEL compound has
no entry in the CYP knowledge base, so no CYP interaction can fire for it. Here we
PREDICT a novel compound's CYP-inhibition profile from structure (Morgan
fingerprint -> gradient-boosted classifier, one per enzyme), then feed the same
interaction logic used by the curated layer.

HONEST SCOPE — read before trusting output:
  * These models predict INHIBITION only (trained on Veith CYP-inhibition data,
    ~12-13k molecules/enzyme). They do NOT predict whether a compound is a
    SUBSTRATE or INDUCER. Consequence:
      - novel x KNOWN  : we can flag "novel INHIBITS E -> known SUBSTRATE of E rises".
                         We CANNOT flag "known inhibitor -> novel substrate" (novel
                         substrate role is unknown).
      - novel x novel  : neither side's substrate role is knowable, so NO CYP DDI
                         can be asserted. We surface both predicted inhibition
                         profiles for context and stop there. (Least-validated case.)
  * Every predicted flag is labelled  predicted (p=X, model AUC Y)  and is visibly
    separate from curated ("established") flags. Predicted flags never reach the
    "high" severity reserved for established strong-inhibitor interactions.
  * CYP2D6 is the weakest model (AUPRC 0.69, class-imbalanced). Any 2D6 flag
    carries an extra low-reliability note.

Held-out test AUC / AUPRC (this build):
  CYP1A2 0.923/0.915  CYP2C9 0.882/0.778  CYP2C19 0.879/0.845
  CYP2D6 0.863/0.693  CYP3A4 0.889/0.863
"""

import os, functools
import numpy as np

def _find_models_path():
    """Locate the CYP model file. The HF uploader sometimes appends '-2', so we
    accept either name (repo may carry cyp_models.joblib OR cyp_models-2.joblib)."""
    here = os.path.dirname(__file__)
    for name in ("cyp_models.joblib", "cyp_models-2.joblib"):
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    return os.path.join(here, "cyp_models.joblib")  # default (for clear error)

_MODELS_PATH = _find_models_path()

# thresholds (Q1: tiered bands, not a single cutoff)
BAND_LIKELY   = 0.70   # p >= 0.70  -> "likely inhibitor"  (flag, moderate confidence)
BAND_POSSIBLE = 0.50   # 0.50-0.70  -> "possible inhibitor" (flag, low confidence)
                       # p < 0.50   -> no flag

# enzymes we consider less reliable (extra caveat when they fire)
LOW_RELIABILITY = {"CYP2D6"}


@functools.lru_cache(maxsize=1)
def _load():
    """Lazy-load models once. Returns (models_dict, auc_map, fp_params) or None."""
    try:
        import joblib
        d = joblib.load(_MODELS_PATH)
        models = d["models"]
        auc = {e: d["report"][e]["auc"] for e in models}
        auprc = {e: d["report"][e]["auprc"] for e in models}
        return models, auc, auprc, d.get("fp", {"n_bits": 2048, "radius": 2})
    except Exception as e:
        # model file missing or unloadable -> predictor is simply unavailable
        return None


@functools.lru_cache(maxsize=1)
def _generator():
    from rdkit.Chem import rdFingerprintGenerator
    loaded = _load()
    fp = loaded[3] if loaded else {"n_bits": 2048, "radius": 2}
    return rdFingerprintGenerator.GetMorganGenerator(
        radius=fp["radius"], fpSize=fp["n_bits"])


def available():
    """True if the QSAR models loaded successfully."""
    return _load() is not None


def _fingerprint(smiles):
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    return np.array(_generator().GetFingerprint(m), dtype=np.int8)


def predict_inhibition(smiles):
    """
    Raw per-enzyme inhibition probabilities for a SMILES.
    Returns {enzyme: prob} or None if models unavailable / SMILES invalid.
    """
    loaded = _load()
    if loaded is None:
        return None
    models, _auc, _auprc, _fp = loaded
    f = _fingerprint(smiles)
    if f is None:
        return None
    return {e: round(float(mo.predict_proba([f])[0, 1]), 3) for e, mo in models.items()}


def _band(p):
    if p >= BAND_LIKELY:
        return "likely"
    if p >= BAND_POSSIBLE:
        return "possible"
    return None


def predicted_profile(smiles):
    """
    Predicted INHIBITOR roles for a novel compound, above the 'possible' band.
    Returns list of dicts: {enzyme, prob, band, auc, low_reliability}.
    Empty list if nothing crosses threshold; None if models unavailable.
    """
    probs = predict_inhibition(smiles)
    if probs is None:
        return None
    loaded = _load()
    _models, auc, _auprc, _fp = loaded
    out = []
    for enzyme, p in probs.items():
        b = _band(p)
        if b is None:
            continue
        out.append({
            "enzyme": enzyme, "prob": p, "band": b, "auc": auc[enzyme],
            "low_reliability": enzyme in LOW_RELIABILITY,
        })
    # strongest first
    out.sort(key=lambda d: d["prob"], reverse=True)
    return out


def cyp_interactions_predicted(novel_smiles, known_drug):
    """
    Predicted CYP interactions between a NOVEL compound (by SMILES) and a KNOWN
    drug (by name, looked up in the curated KB).

    Logic: novel is PREDICTED to inhibit enzyme E, and the known drug is a curated
    SUBSTRATE or PRODRUG of E  ->  known drug's level/activation is affected.
    (We cannot use the reverse direction, since the novel compound's substrate
    role is not predictable — see module docstring.)

    Returns list of mechanism dicts, each tagged source='predicted'.
    """
    from cyp_ddi import _profile, _norm  # curated side

    prof = predicted_profile(novel_smiles)
    if not prof:
        return []

    known_roles = {e: r for e, r in _profile(known_drug)}
    if not known_roles:
        return []

    kname = _norm(known_drug)
    band_sev = {"likely": "mod", "possible": "low"}  # predicted never reaches 'high'
    out = []
    for pred in prof:
        E = pred["enzyme"]
        brole = known_roles.get(E)
        if brole not in ("substrate", "prodrug"):
            continue
        sev = band_sev[pred["band"]]
        conf = f"predicted: novel p={pred['prob']} ({pred['band']} inhibitor), model AUC {pred['auc']}"
        if brole == "substrate":
            effect = (f"novel compound predicted to inhibit {E} → "
                      f"{kname} (established {E} substrate) levels may rise → toxicity risk")
        else:  # prodrug
            effect = (f"novel compound predicted to inhibit {E} → "
                      f"{kname} (established {E} prodrug) under-activated → possible loss of efficacy")
        note = f"{conf}; {kname} substrate role is established (curated)."
        if pred["low_reliability"]:
            note += " NOTE: CYP2D6 predictions are less reliable (AUPRC 0.69)."
        out.append({
            "enzyme": E, "mechanism": "CYP inhibition (predicted)",
            "effect": effect, "severity": sev, "source": "predicted",
            "prob": pred["prob"], "band": pred["band"], "auc": pred["auc"],
            "note": note, "direction": f"novel⊣{E}→{'↑'+kname if brole=='substrate' else '↓active '+kname}",
        })
    return out
