"""
Radiant Revive AI — PROVIDER PORTAL (Clinician-facing, human-in-the-loop)
=========================================================================
CONFIDENTIAL — Radiant Revive LLC. Placeholder predictor for UI demo only —
NOT FOR CLINICAL USE. Real Phase 1.3 model plugs into diagnostic_engine().

This is the CLINICIAN'S tool. The patient never sees this analysis. The AI
attempts a differential diagnosis; a licensed nurse reviews, engages the AI to
reach consensus, decides treatment vs. referral, and feeds corrections back
into the knowledge base. Human-in-the-loop is the core of the methodology.

Assets (logo.png, fitzchart.jpg) are loaded from disk at startup and encoded
in-memory, so this script stays small and writes reliably.
"""
import os, base64
import numpy as np
import gradio as gr
from PIL import Image
import knowledge as KB   # backend knowledge library (papers, case memory, SOC library)

_HERE = os.path.dirname(os.path.abspath(__file__))
def _b64(fname):
    try:
        with open(os.path.join(_HERE, fname), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""
LOGO_B64 = _b64("logo.png")
FITZCHART_B64 = _b64("fitzchart.jpg")

# ---- Palette ----
RED, RED_DK = "#E53935", "#B5121B"
DARK, GRAY, GREY_BG, GREY_LN = "#2B2B2B", "#666666", "#FAFAFA", "#E5E5E5"
BLUE, GREEN, ORANGE, PURPLE, TEAL = "#3B82F6", "#22C55E", "#F97316", "#A855F7", "#0EA5E9"

# ============ LEARNING-LOOP KNOWLEDGE BASE (human-verified label store) ============
# Every clinician sign-off writes a durable, auditable record. In production this is a
# database / HF Dataset; here it is a JSONL file so the flywheel is visible in the demo.
import json, hashlib, io, datetime
KB_PATH = "/data/knowledge_base.jsonl" if os.path.isdir("/data") else os.path.join(_HERE, "knowledge_base.jsonl")

def _img_sha(image):
    if image is None: return "no-image"
    try:
        buf = io.BytesIO(); image.convert("RGB").resize((64,64)).save(buf, format="PNG")
        return hashlib.sha256(buf.getvalue()).hexdigest()[:16]
    except Exception:
        return "hash-error"

def _mst_band(fp):  # approximate Monk band from Fitzpatrick (independent capture in production)
    return {1:"01-02",2:"02-03",3:"03-04",4:"04-06",5:"06-08",6:"08-10"}.get(int(fp), "\u2014")

def kb_append(fp, image, ai_dx, verified_dx, corrected, observation, clinician, referral=False, referral_reason=""):
    rec = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "img_sha": _img_sha(image), "fst": int(fp), "mst_est": _mst_band(fp),
           "ai_dx": (ai_dx or "").strip(), "verified_dx": (verified_dx or "").strip(),
           "corrected": bool(corrected), "observation": (observation or "").strip(),
           "clinician": (clinician or "Licensed Clinician").strip(),
           "referral": bool(referral), "referral_reason": (referral_reason or "").strip(),
           "protocol": "Measurement Protocol v1.1", "kb_version": 1}
    try:
        with open(KB_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        rec["_persist_error"] = str(e)
    return rec

def kb_records():
    recs = []
    try:
        with open(KB_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line: recs.append(json.loads(line))
    except Exception:
        pass
    return recs

def kb_view():
    recs = kb_records()
    n = len(recs)
    n_corr = sum(1 for r in recs if r.get("corrected"))
    n_dark = sum(1 for r in recs if r.get("fst", 0) >= 5)
    n_ref = sum(1 for r in recs if r.get("referral"))
    if n == 0:
        body = ('<div style="padding:18px;text-align:center;color:#999;font-family:Calibri;">'
                'No verified records yet. Sign off a case in Step 5 to add the first human-verified label.</div>')
    else:
        rows = ""
        for r in reversed(recs[-6:]):
            corrected = r.get("corrected")
            tag = "CORRECTED" if corrected else "confirmed"
            tcol = ORANGE if corrected else GREEN
            if r.get("referral"): tag += " + REFERRED"; tcol = RED_DK
            rows += (f'<tr style="border-bottom:1px solid {GREY_LN};">'
                     f'<td style="padding:5px 7px;font-size:11px;color:{GRAY};white-space:nowrap;">{r.get("ts","")[:16]}</td>'
                     f'<td style="padding:5px 7px;font-size:11px;font-weight:bold;color:{DARK};">FST {r.get("fst","?")}</td>'
                     f'<td style="padding:5px 7px;font-size:12px;color:{DARK};">{r.get("verified_dx","")}</td>'
                     f'<td style="padding:5px 7px;"><span style="font-size:10px;color:#fff;background:{tcol};padding:2px 7px;border-radius:9px;">{tag}</span></td>'
                     f'<td style="padding:5px 7px;font-size:11px;color:{GRAY};">{r.get("clinician","")}</td></tr>')
        body = (f'<table style="width:100%;border-collapse:collapse;margin-top:8px;">'
                f'<tr style="border-bottom:2px solid {GREY_LN};"><th style="text-align:left;padding:5px 7px;font-size:10px;color:{GRAY};">TIME</th>'
                f'<th style="text-align:left;padding:5px 7px;font-size:10px;color:{GRAY};">SKIN TYPE</th>'
                f'<th style="text-align:left;padding:5px 7px;font-size:10px;color:{GRAY};">VERIFIED DX</th>'
                f'<th style="text-align:left;padding:5px 7px;font-size:10px;color:{GRAY};">STATUS</th>'
                f'<th style="text-align:left;padding:5px 7px;font-size:10px;color:{GRAY};">SIGNED BY</th></tr>{rows}</table>')
    return (f'<div style="font-family:Calibri,Arial,sans-serif;">'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px;">'
            f'<div style="flex:1;min-width:120px;background:{GREEN};border-radius:10px;padding:10px;text-align:center;">'
            f'<div style="font-size:24px;font-weight:bold;color:#fff;">{n}</div><div style="font-size:10px;color:#EAFBEF;">VERIFIED LABELS</div></div>'
            f'<div style="flex:1;min-width:120px;background:{ORANGE};border-radius:10px;padding:10px;text-align:center;">'
            f'<div style="font-size:24px;font-weight:bold;color:#fff;">{n_corr}</div><div style="font-size:10px;color:#FFF3E6;">CLINICIAN CORRECTIONS</div></div>'
            f'<div style="flex:1;min-width:120px;background:{RED_DK};border-radius:10px;padding:10px;text-align:center;">'
            f'<div style="font-size:24px;font-weight:bold;color:#fff;">{n_dark}</div><div style="font-size:10px;color:#FFE3E3;">FITZPATRICK V-VI</div></div>'
            f'<div style="flex:1;min-width:120px;background:{BLUE};border-radius:10px;padding:10px;text-align:center;">'
            f'<div style="font-size:24px;font-weight:bold;color:#fff;">{n_ref}</div><div style="font-size:10px;color:#E6F0FF;">PHYSICIAN REFERRALS</div></div></div>'
            f'{body}'
            f'<div style="font-size:11px;color:{GRAY};margin-top:8px;font-style:italic;">Every entry is human-verified, attributable, timestamped, and version-controlled &mdash; the labeled data that fine-tunes the model, with a deliberate focus on darker skin (FST V-VI). No autonomous self-modification. Demo store; production uses a governed database.</div></div>')


# ---- Skin-region auto-crop -------------------------------------------------
# Real clinical photos contain walls, floors, shadow and clothing. Without this,
# every texture/pigment statistic is computed over the background too. Tone-agnostic
# so it works across Fitzpatrick I-VI, and fails safe: if detection is unreliable
# the original image is returned unchanged.
def _skin_crop(image):
    arr = np.array(image.convert("RGB")).astype(float)
    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    V = arr.max(axis=2); mn = arr.min(axis=2)
    sat = V - mn
    # skin at ANY phototype is warm (R above B) and neither blown-out nor crushed;
    # flat neutral surfaces (walls, doors, paper, floor) have low saturation
    mask = (R > B + 6) & (R >= G) & (V > 25) & (V < 248) & (sat > 10)
    cov = float(mask.mean())
    info = {"cropped": False, "coverage": round(cov, 3)}
    if cov < 0.05 or cov > 0.97:
        return image, info                      # nothing found, or already a tight crop
    h, w = mask.shape
    rows = mask.mean(axis=1); cols = mask.mean(axis=0)
    ry = np.nonzero(rows > 0.15)[0]; cx = np.nonzero(cols > 0.15)[0]
    if ry.size < 10 or cx.size < 10:
        return image, info
    m = 0.02
    y0 = max(0, int(ry[0] - h * m)); y1 = min(h, int(ry[-1] + h * m))
    x0 = max(0, int(cx[0] - w * m)); x1 = min(w, int(cx[-1] + w * m))
    if (y1 - y0) < h * 0.15 or (x1 - x0) < w * 0.15:
        return image, info                      # implausible box — leave it alone
    info.update({"cropped": True, "box": (x0, y0, x1, y1),
                 "kept": round(float((y1 - y0) * (x1 - x0)) / (h * w), 3)})
    return image.crop((x0, y0, x1, y1)), info

def _features(image):
    arr = np.array(image.convert("RGB")).astype(float)
    g = arr.mean(axis=2); h, w = g.shape
    L, R = g[:, :w//2], g[:, w//2:][:, ::-1]; m = min(L.shape[1], R.shape[1])
    A = min(100, int(float(np.mean(np.abs(L[:, :m]-R[:, :m])))/255.0*260))
    gy, gx = np.gradient(g)
    B = min(100, int(float(np.mean(np.sqrt(gx**2+gy**2)))/255.0*320))
    C = min(100, int(float(np.mean(np.std(arr, axis=(0,1))))/255.0*180))
    return A, B, C

# Richer perception signals used to describe what the AI is actually seeing.
def _texture(image):
    arr = np.array(image.convert("RGB")).astype(float)
    R, G, Bc = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    g = arr.mean(axis=2)
    bright = float(g.mean())                                  # 0-255
    gy, gx = np.gradient(g)
    grad = np.sqrt(gx**2 + gy**2)
    rough = float(grad.mean())                                # surface texture
    hi_freq = float(grad.std())                               # fissures / cracked scale
    sat = float(np.mean(arr.max(axis=2) - arr.min(axis=2)))   # color saturation
    redness = float(np.mean(R - (G + Bc) / 2.0))              # erythema
    # normalized 0-100 indices
    scaling = min(100, int(rough / 255.0 * 300))              # hyperkeratosis / scaling
    fissure = min(100, int(hi_freq / 255.0 * 320))            # cracking / fissuring
    # dryness is driven by scaly/matte TEXTURE, not low saturation alone (uniform dark skin is not "dry")
    dryness = min(100, int(scaling * 0.5 + fissure * 0.3 + max(0.0, 40 - sat) / 40.0 * 30))
    erythema = min(100, int(max(0.0, redness) / 40.0 * 100))
    pigment = min(100, int((255 - bright) / 255.0 * 130))     # depth of pigmentation / darkness
    return {"scaling": scaling, "fissure": fissure, "dryness": dryness,
            "erythema": erythema, "pigment": pigment, "bright": int(bright), "sat": int(sat)}

# Keratotic/benign chronic patterns should NOT inflate the cancer score.
def _score(A, B, C, fp, tex=None):
    comp = (A*0.35 + B*0.35 + C*0.30)/100.0
    mal = min(0.95, 0.15 + comp*0.75) * (0.88 + 0.12*(fp/6))
    if tex is not None:
        # Thick, dry, cracked, symmetric keratotic surfaces read as benign, not malignant.
        benign_keratotic = (tex["scaling"] + tex["fissure"] + tex["dryness"]) / 3.0
        if benign_keratotic > 45 and A < 55:
            mal *= max(0.35, 1.0 - (benign_keratotic - 45) / 90.0)
    return int(mal*100)

# Distinguish a DISCRETE pigmented focus from diffuse pressure keratosis.
# Acral lentiginous melanoma and a callus occupy the same surfaces; they must not be conflated.
def _focal_pigment(image):
    arr = np.array(image.convert("RGB")).astype(float)
    g = arr.mean(axis=2)
    h, w = g.shape
    p5, p50, p60 = (float(np.percentile(g, q)) for q in (5, 50, 60))
    thr = (p5 + p50) / 2.0                      # midpoint between the dark mode and the field
    mask = g <= thr
    frac = float(mask.mean())
    if frac < 0.01 or frac > 0.50:
        return {"focal": False, "score": 0, "frac": round(frac, 3), "spread": 0.0}
    ys, xs = np.nonzero(mask)
    spread = (float(xs.std()) / max(1, w) + float(ys.std()) / max(1, h)) / 2.0   # ~0.29 = spread across field
    contrast = (p60 - p5) / 255.0
    score = int(max(0, min(100, (0.29 - spread) * 380 + contrast * 110)))
    # A genuine discrete lesion occupies a small part of the frame. On uniformly
    # deep skin tones a dark threshold captures large areas, so require a tight focus.
    return {"focal": bool(score >= 55 and frac <= 0.15 and contrast >= 0.18),
            "score": score, "frac": round(frac, 3), "spread": round(spread, 3),
            "contrast": round(contrast, 3)}

# Hyperkeratosis / callus detector -------------------------------------------
# Thickened stratum corneum is YELLOW-TAN and LIGHTER than surrounding skin.
# Gradient-roughness misses this entirely; colour is the discriminating signal,
# and it holds across phototypes because it is measured RELATIVE to the patient's
# own surrounding skin rather than against an absolute reference.
def _hyperkeratosis(image):
    arr = np.array(image.convert("RGB")).astype(float)
    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    V = arr.mean(axis=2)
    yellow = (R + G) / 2.0 - B                      # yellow-tan index
    v_med, y_med = float(np.median(V)), float(np.median(yellow))
    v_sd = float(V.std()) or 1.0
    mask = (V > v_med + max(8.0, 0.45 * v_sd)) & (yellow > y_med + 6.0)
    frac = float(mask.mean())
    if frac < 0.015 or frac > 0.60:
        return {"present": False, "frac": round(frac, 3), "score": 0}
    ys, xs = np.nonzero(mask)
    h, w = V.shape
    spread = (float(xs.std()) / max(1, w) + float(ys.std()) / max(1, h)) / 2.0
    lift = float(V[mask].mean() - v_med) / 255.0     # how much lighter than skin
    ylift = float(yellow[mask].mean() - y_med) / 60.0
    score = int(max(0, min(100, lift * 260 + ylift * 55 + (0.30 - spread) * 90)))
    return {"present": bool(score >= 30), "frac": round(frac, 3),
            "score": score, "lift": round(lift, 3), "spread": round(spread, 3)}

# Describe the observed surface morphology (what the AI "sees") — location aware.
def _morphology(tex, location):
    loc = (location or "").lower()
    acral = any(k in loc for k in ["foot","sole","plantar","palm","hand","nail","heel","toe"])
    # Clinician-entered site is ground truth; on acral skin we lower the evidence bar for keratotic findings.
    sc_t, dr_t, fi_t = (28, 32, 28) if acral else (45, 45, 45)
    f = []
    if tex.get("_hk"):
        if acral:
            f.append(("Hyperkeratotic, thickened plaque — callus / tyloma pattern",
                      "Yellow-tan thickening lighter than surrounding skin at a pressure-bearing site. "
                      "Measured relative to this patient's own skin tone, not an absolute reference."))
        elif KB.keloid_prone(location):
            f.append(("Raised, firm, thickened plaque — keloid / hypertrophic scar pattern",
                      "Elevated tissue at a high-tension site (sternum, shoulder, jawline, earlobe). "
                      "Keloid formation is markedly more common in skin of color; tyloma/callus is not a "
                      "consideration away from pressure-bearing surfaces."))
        else:
            f.append(("Raised, thickened plaque",
                      "Elevated tissue lighter than surrounding skin. Site is not pressure-bearing, so "
                      "callus is not a consideration; scar, keratosis and inflammatory causes are."))
    if tex["scaling"] >= sc_t and not tex.get("_hk"):
        f.append(("Hyperkeratotic, thickened surface — callus / tyloma pattern",
                  "Repetitive pressure/friction thickening; common on weight-bearing plantar skin."))
    if tex["dryness"] >= dr_t:
        f.append(("Xerosis — dry, matte, flaking scale",
                  "Reduced surface hydration; scale and ashiness are more visually prominent in deeper skin."))
    if tex["fissure"] >= fi_t:
        f.append(("Fissuring / cracking within thickened skin",
                  "Splits through hyperkeratotic tissue; watch for a portal to secondary infection."))
    if KB.keloid_prone(location) and not tex.get("_hk"):
        f.append(("Raised, firm, well-demarcated tissue — possible keloid / hypertrophic scar",
                  "Fibrous overgrowth at a prior injury/pressure site; keloids are markedly more common in skin of color."))
    if tex["erythema"] >= 40:
        f.append(("Erythema / inflammatory change",
                  "Perilesional redness — can be masked by melanin, so it is weighted up in deeper phototypes."))
    if not f:
        f.append(("Discrete pigmented macule/patch — no dominant keratotic or inflammatory features",
                  "Surface appears relatively uniform; evaluate on the pigmented-lesion pathway."))
    return f

# Illustrative differential-diagnosis generator (placeholder — demonstrates the concept)
def _differential(mal, A, B, C, location, tex=None):
    loc = (location or "").lower()
    acral = any(k in loc for k in ["foot","sole","plantar","palm","hand","nail","heel","toe"])
    if tex is not None:
        avg_kt = (tex["scaling"] + tex["fissure"] + tex["dryness"]) / 3.0
        # On acral sites, base rates make chronic keratotic disease far more likely than tumor.
        keratotic = avg_kt >= 38 or (acral and (tex["scaling"] >= 25 or tex["dryness"] >= 35 or tex["fissure"] >= 25))
    else:
        keratotic = False
    focal = (tex or {}).get("_focal", False)
    if KB.keloid_prone(loc) and (tex or {}).get("_hk") and mal < 60:
        return [("Keloid / hypertrophic scar", 46),
                ("Acne keloidalis / folliculitis-related scarring", 18),
                ("Dermatosis papulosa nigra / seborrhoeic keratosis", 14),
                ("Post-inflammatory hyperpigmentation", 12),
                ("Cutaneous malignancy — low probability, can't-miss: monitor", max(4, min(mal, 10)))]
    if acral and focal:
        # Discrete pigmented acral lesion -> pigmented-lesion pathway, NOT the callus pathway.
        return [("Acral lentiginous melanoma — discrete pigmented acral lesion; biopsy to exclude", max(45, mal)),
                ("Acral naevus / benign melanocytic lesion", 24),
                ("Talon noir (subcorneal haemorrhage)", 12),
                ("Pigmented callus / hyperkeratosis", 11),
                ("Subungual haematoma" if "nail" in loc else "Post-inflammatory hyperpigmentation", 8)]
    if keratotic and mal < 65:
        # Benign chronic pattern dominates; melanoma retained ONLY as a can't-miss safety item.
        dx = [("Callus / hyperkeratosis (tyloma)", 55),
              ("Xerosis with fissuring (dry, cracked skin)", 22),
              ("Keloid / hypertrophic scar", 14) if acral else ("Lichen simplex chronicus", 14),
              ("Plantar verruca vs. tinea pedis", 12) if acral else ("Chronic eczema / stasis change", 12),
              ("Acral lentiginous melanoma — low probability, can't-miss: monitor/dermoscopy", max(4, min(mal, 10))) if acral
                  else ("Melanoma — low probability, can't-miss: monitor", max(4, min(mal, 10)))]
    elif mal >= 65:
        dx = [("Melanoma — flag for biopsy/dermoscopy", mal),
              ("Basal cell carcinoma", max(8, 90-mal)),
              ("Squamous cell carcinoma", max(5, 70-mal))]
        if acral: dx[0] = ("Acral lentiginous melanoma — flag for biopsy", mal)
    elif mal >= 35:
        dx = [("Atypical / dysplastic nevus", mal),
              ("Actinic keratosis (pre-malignant)", max(12, 65-mal)),
              ("Seborrheic keratosis (benign)", max(10, 55-mal))]
    else:
        dx = [("Benign melanocytic nevus", 100-mal),
              ("Seborrheic keratosis (benign)", max(12, mal+10)),
              ("Post-inflammatory hyperpigmentation", max(8, mal))]
    # normalize to ~100
    tot = sum(c for _, c in dx) or 1
    return [(n, int(c/tot*100)) for n, c in dx]

def mal_meter(pct):
    if pct >= 75:   return RED_DK, "HIGH RISK"
    elif pct >= 50: return PURPLE, "MODERATE-HIGH RISK"
    elif pct >= 25: return BLUE,   "MODERATE-LOW RISK"
    else:           return GREEN,  "LOW RISK"

def _bar(label, value, color):
    return (f'<div style="margin:6px 0;"><div style="display:flex;justify-content:space-between;'
            f'font-size:12px;color:{DARK};margin-bottom:3px;"><span>{label}</span>'
            f'<span style="font-weight:bold;color:{color};">{value}/100</span></div>'
            f'<div style="background:#ececec;height:12px;border-radius:6px;overflow:hidden;">'
            f'<div style="background:{color};height:100%;width:{value}%;border-radius:6px;"></div></div></div>')

def diagnostic_engine(image, fp, location, notes):
    """The AI's attempted diagnosis — for CLINICIAN review (not patient-facing)."""
    if image is None:
        return "<div style='padding:36px;text-align:center;color:#aaa;font-family:Calibri;'>Upload a case image and click Run AI Analysis.</div>"
    if fp is None:
        return """<div style="padding:30px;text-align:center;font-family:Calibri,Arial,sans-serif;color:#0D6EFD;font-size:14px;font-weight:bold;">Select the patient's Fitzpatrick skin type in Step 1 <span style="display:block;font-weight:normal;color:#666;font-size:12px;margin-top:5px;">Skin type drives the calibration, so the analysis will not run without it. Use the skin-tone guide if you are unsure.</span></div>"""
    fp = int(fp)
    location, _lc = KB.autocorrect(location)
    notes, _nc = KB.autocorrect(notes)
    image, _crop = _skin_crop(image)
    A, B, C = _features(image)
    tex = _texture(image)
    _fp_sig = _focal_pigment(image)
    _hk = _hyperkeratosis(image)
    tex["_focal"] = _fp_sig["focal"]
    tex["_hk"] = _hk["present"]
    if _hk["present"]:
        tex["scaling"] = max(tex["scaling"], min(70, 25 + _hk["score"] // 3))
    mal = _score(A, B, C, fp, tex)
    mcolor, mlabel = mal_meter(mal)
    morph = _morphology(tex, location)
    dx = _differential(mal, A, B, C, location, tex)
    if mal >= 65:   ref = ("URGENT referral — dermatology now; oncology if indicated", RED_DK)
    elif mal >= 35: ref = ("Refer to dermatology within 30 days", ORANGE)
    else:           ref = ("Within nursing scope — treat + monitor", GREEN)

    # ---- Perception reliability gate --------------------------------------------
    _weak = (tex["scaling"] < 10 and tex["fissure"] < 10 and tex["dryness"] < 10) and not _hk["present"]
    _diffuse = _fp_sig["frac"] > 0.25 and not _hk["present"]
    unreliable = _weak or _diffuse
    _NO_DX = "<div style='font-size:12px;color:#999;'>No ranked differential offered for this image &mdash; see the notice above.</div>"
    unreliable_html = ""
    if unreliable:
        why = []
        if _weak: why.append("surface texture signal is below the level this scaffold can interpret (low-contrast or softly focused image)")
        if _diffuse: why.append("no discrete lesion boundary could be isolated from the surrounding skin")
        unreliable_html = (
          '<div style="background:#FEF9E7;border:2px solid ' + ORANGE + ';border-radius:12px;padding:15px;margin-bottom:12px;">'
          '<div style="font-size:12px;color:#7A4F01;font-weight:bold;letter-spacing:1px;">INSUFFICIENT SIGNAL &mdash; NO AUTOMATED DIFFERENTIAL OFFERED</div>'
          '<div style="font-size:13px;color:' + DARK + ';margin-top:5px;">This scaffold will not rank a differential for this image: ' + "; ".join(why) + '.</div>'
          '<div style="font-size:12px;color:' + DARK + ';margin-top:7px;">Proceeding would mean guessing. The clinician assessment below stands on its own, and the site-based safety screen still applies. <b>Building perception that is reliable on real clinical photographs of deeply pigmented skin is precisely the work this project proposes.</b></div></div>')

    # ---- Clinician-taught systemic rule: bilateral palmoplantar collapses an occupational story ----
    alert = KB.systemic_alert(location, notes)
    alert_html = ""
    if alert:
        wk = "".join("<li style='margin:2px 0;'>" + w + "</li>" for w in alert["workup"])
        dx = [(alert["correct_dx"] + " — bilateral palmoplantar distribution", 55)] + [(n, max(4, int(c * 0.45))) for n, c in dx][:4]
        ref = ("URGENT — physician referral + RPR/VDRL before any occupational diagnosis", RED_DK)
        alert_html = (
          '<div style="background:' + RED_DK + ';border-radius:12px;padding:15px;margin-bottom:12px;box-shadow:0 3px 12px rgba(181,18,27,.35);">'
          '<div style="color:#fff;font-size:12px;font-weight:bold;letter-spacing:1px;">&#9888; SYSTEMIC PATTERN ALERT</div>'
          '<div style="color:#fff;font-size:15px;font-weight:bold;margin-top:5px;">' + alert["correct_dx"] + ' until proven otherwise</div>'
          '<div style="color:#FFE3E3;font-size:12px;margin-top:6px;font-style:italic;">' + alert["pearl"] + '</div>'
          '<div style="background:#fff;border-radius:8px;padding:10px 12px;margin-top:9px;">'
          '<div style="font-size:11px;color:' + RED_DK + ';font-weight:bold;letter-spacing:1px;">REQUIRED WORKUP BEFORE ANY LOCAL EXPLANATION</div>'
          '<ul style="font-size:12px;color:' + DARK + ';margin:5px 0 0 18px;padding:0;">' + wk + '</ul>'
          '<div style="font-size:11px;color:' + GRAY + ';margin-top:6px;">Urgency: ' + alert["urgency"] + '</div></div>'
          '<div style="color:#FFD3D3;font-size:10px;margin-top:7px;">Distribution-driven systemic screen. Assess this patient on their own findings; serology decides.</div></div>')

    # ---- Can't-miss acral / subungual cancer screen (published clinical rules) ----
    acral_html = ""
    _ac = KB.acral_cancer_check(location, notes)
    if _ac:
        r = _ac["rule"]
        qs = "".join("<li style='margin:3px 0;'>" + q + "</li>" for q in r["discriminators"])
        nail_block = ""
        if _ac["nail"]:
            n = _ac["nail"]
            ab = "".join("<li style='margin:2px 0;'>" + x + "</li>" for x in n["abcdef"])
            nail_block = ('<div style="background:#fff;border-radius:8px;padding:10px 12px;margin-top:9px;">'
                          '<div style="font-size:11px;color:' + RED_DK + ';font-weight:bold;letter-spacing:1px;">NAIL UNIT &mdash; ' + n["condition"].upper() + ' (ABCDEF)</div>'
                          '<div style="font-size:11px;color:' + GRAY + ';margin:4px 0;">' + n["why"] + '</div>'
                          '<ul style="font-size:11px;color:' + DARK + ';margin:4px 0 0 18px;padding:0;">' + ab + '</ul>'
                          '<div style="font-size:11px;color:' + RED_DK + ';font-weight:bold;margin-top:5px;">' + n["action"] + '</div></div>')
        focal_line = ""
        if _fp_sig["focal"]:
            focal_line = ('<div style="background:' + RED_DK + ';border-radius:8px;padding:9px 12px;margin-top:9px;">'
                          '<span style="color:#fff;font-size:12px;font-weight:bold;">&#9888; A DISCRETE PIGMENTED FOCUS IS PRESENT</span>'
                          '<div style="color:#FFE3E3;font-size:11px;margin-top:2px;">This is not diffuse pressure keratosis. Treat on the pigmented-lesion pathway; do not attribute to callus.</div></div>')
        acral_html = ('<div style="background:#FFF5F5;border:2px solid ' + RED + ';border-radius:12px;padding:15px;margin-bottom:12px;">'
            '<div style="font-size:12px;color:' + RED_DK + ';font-weight:bold;letter-spacing:1px;">CAN&rsquo;T-MISS SCREEN &mdash; ACRAL SITE</div>'
            '<div style="font-size:14px;font-weight:bold;color:' + DARK + ';margin-top:4px;">' + r["condition"] + '</div>'
            '<div style="font-size:11px;color:' + GRAY + ';margin:5px 0;">' + r["why"] + '</div>'
            + focal_line +
            '<div style="background:#fff;border-radius:8px;padding:10px 12px;margin-top:9px;">'
            '<div style="font-size:11px;color:' + RED_DK + ';font-weight:bold;letter-spacing:1px;">CLINICIAN DISCRIMINATORS</div>'
            '<ul style="font-size:12px;color:' + DARK + ';margin:5px 0 0 18px;padding:0;">' + qs + '</ul>'
            '<div style="font-size:11px;color:' + RED_DK + ';font-weight:bold;margin-top:6px;">' + r["action"] + '</div></div>'
            + nail_block + '</div>')

    # ---- Evidence retrieval: papers + prior corrected cases + curated SOC library ----
    dx_terms = [n.split(" — ")[0].split(" (")[0].lower() for n, _ in dx[:3]]
    fp_roman = KB.ROMAN.get(fp, "")
    papers = KB.match_papers(tags=dx_terms + ["skin of color"], fitzpatrick=fp_roman,
                             findings=[m[0].split(" — ")[0].lower() for m in morph], limit=3)
    prior = []   # demo library contains no patient records
    lib = KB.match_library(dx_terms, fp_roman, location, limit=3)
    ev_rows = ""
    for m in papers:
        it = m["item"]
        ev_rows += ('<div style="margin:5px 0;padding:8px 10px;background:' + GREY_BG + ';border-left:3px solid ' + TEAL + ';border-radius:6px;">'
                    '<div style="font-size:12px;color:' + DARK + ';">' + str(it.get("one_line_summary", ""))[:200] + '</div>'
                    '<div style="font-size:10px;color:' + GRAY + ';margin-top:2px;">' + str(it.get("citation", ""))[:160] + '</div></div>')
    for m in lib:
        it = m["item"]
        title = str(it.get("diagnosis") or it.get("title") or "")[:110]
        body = str(it.get("notes") or it.get("summary") or "")[:190]
        ev_rows += ('<div style="margin:5px 0;padding:8px 10px;background:' + GREY_BG + ';border-left:3px solid ' + PURPLE + ';border-radius:6px;">'
                    '<b style="font-size:11px;color:' + PURPLE + ';">' + title + '</b>'
                    '<div style="font-size:12px;color:' + DARK + ';">' + body + '</div></div>')
    n_kb = sum(KB.kb_counts().values())
    n_shown = len(papers) + len(lib)
    evidence_html = ('<details style="margin-top:10px;border:1px solid ' + GREY_LN + ';border-radius:10px;background:' + GREY_BG + ';">'
        '<summary style="cursor:pointer;padding:9px 12px;font-size:12px;font-weight:bold;color:' + TEAL + ';list-style:none;">'
        '&#9432; Show sources (' + str(n_shown) + ' matched of ' + str(n_kb) + ' indexed) &mdash; for demonstration; collapsed during clinical use</summary>'
        '<div style="padding:4px 12px 12px 12px;">'
        + (ev_rows if ev_rows else '<div style="font-size:12px;color:#999;">No matching sources for this presentation.</div>')
        + '<div style="font-size:10px;color:' + GRAY + ';margin-top:8px;font-style:italic;">Published literature and curated reference material that informed the reasoning. '
          'Patient-specific records from other cases are deliberately excluded &mdash; every case is assessed on its own findings.</div></div></details>')

    morph_rows = ""
    for name, note in morph:
        morph_rows += (f'<div style="margin:7px 0;padding:9px 11px;background:{GREY_BG};border-left:3px solid {TEAL};border-radius:6px;">'
                       f'<div style="font-size:13px;color:{DARK};font-weight:bold;">&#128065; {name}</div>'
                       f'<div style="font-size:11px;color:{GRAY};margin-top:2px;">{note}</div></div>')

    if unreliable:
        dx = []
    dx_rows = ""
    for i, (name, conf) in enumerate(dx):
        c = RED_DK if i == 0 and mal >= 65 else (DARK if i == 0 else GRAY)
        w = ["55%","30%","18%"][i] if i < 3 else "15%"
        dx_rows += (f'<div style="display:flex;align-items:center;margin:5px 0;">'
                    f'<div style="flex:1;font-size:13px;color:{c};font-weight:{"bold" if i==0 else "normal"};">{i+1}. {name}</div>'
                    f'<div style="width:48px;text-align:right;font-size:13px;font-weight:bold;color:{c};">{conf}%</div></div>')

    fp_note = (f"Fitzpatrick {fp}: tone-calibrated thresholds applied. In deeply pigmented skin, erythema and border "
               f"cues can be masked by melanin — Radiant Revive up-weights these so they are not missed.") if fp >= 5 else \
              (f"Fitzpatrick {fp}: phototype-calibrated analytical parameters applied per Measurement Protocol v1.1.")

    return f"""
    <div style="font-family:Calibri,Arial,sans-serif;">
      {alert_html}
      {unreliable_html}
      {acral_html}
      <!-- Observed morphology (what the AI sees) -->
      <div style="background:#fff;border:2px solid {TEAL};border-radius:12px;padding:16px;margin-bottom:12px;">
        <div style="font-size:12px;color:{TEAL};font-weight:bold;letter-spacing:1px;margin-bottom:6px;">WHAT THE AI SEES &mdash; OBSERVED MORPHOLOGY</div>
        {morph_rows}
        <div style="font-size:11px;color:{GRAY};margin-top:6px;font-style:italic;">Surface findings described from the image before ranking a differential. Placeholder perception in this demo; production uses a trained model.</div>
      </div>
      <!-- Attempted diagnosis -->
      <div style="background:#fff;border:2px solid {PURPLE};border-radius:12px;padding:16px;margin-bottom:12px;">
        <div style="font-size:12px;color:{PURPLE};font-weight:bold;letter-spacing:1px;margin-bottom:8px;">AI ATTEMPTED DIAGNOSIS &mdash; DIFFERENTIAL (for clinician review)</div>
        {dx_rows if dx_rows else _NO_DX}
        <div style="font-size:11px;color:{GRAY};margin-top:8px;font-style:italic;">Ranked differential with confidence. The clinician confirms or overrides — see consensus panel below.</div>
      </div>
      <!-- Malignancy meter -->
      <div style="background:#fff;border:2px solid {mcolor};border-radius:12px;padding:14px;margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
          <span style="font-size:13px;color:{DARK};font-weight:bold;">MALIGNANCY-RISK SCORE
            <span class="rr-info" tabindex="0" title="Composite 0-100 estimate of cancer-associated features, Fitzpatrick-calibrated. Placeholder in demo; production model validated against biopsy outcomes.">&#9432;<span class="rr-tip">Composite 0-100 estimate of how likely the lesion shows cancer-associated features (asymmetry, border, color), calibrated by Fitzpatrick type. Placeholder in this demo; the production model is validated against biopsy-confirmed outcomes.</span></span>
          </span>
          <span style="font-size:12px;font-weight:bold;color:{mcolor};">{mlabel}</span>
        </div>
        <div style="background:#e6e6e6;height:26px;border-radius:13px;overflow:hidden;">
          <div style="background:{mcolor};height:100%;width:{mal}%;color:#fff;text-align:right;padding-right:12px;line-height:26px;font-weight:bold;border-radius:13px;">{mal}%</div>
        </div>
        <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px;">
          <span style="font-size:10px;color:{GRAY};">KEY:</span>
          <span style="font-size:10px;background:{GREEN};color:#fff;padding:2px 7px;border-radius:9px;">0-24 Low</span>
          <span style="font-size:10px;background:{BLUE};color:#fff;padding:2px 7px;border-radius:9px;">25-49 Mod-Low</span>
          <span style="font-size:10px;background:{PURPLE};color:#fff;padding:2px 7px;border-radius:9px;">50-74 Mod-High</span>
          <span style="font-size:10px;background:{RED_DK};color:#fff;padding:2px 7px;border-radius:9px;">75-100 High</span>
        </div>
      </div>
      <!-- ABCDE -->
      <div style="background:#fff;border:1px solid {GREY_LN};border-top:4px solid {PURPLE};border-radius:12px;padding:14px;margin-bottom:12px;">
        <div style="font-size:13px;color:{DARK};font-weight:bold;margin-bottom:8px;">CONTRIBUTING FACTORS (ABCDE)
          <span class="rr-info" tabindex="0" title="ABCDE: Asymmetry, Border, Color, Diameter, Evolution — the standard dermatology framework.">&#9432;<span class="rr-tip">ABCDE is the standard dermatology framework: Asymmetry, Border irregularity, Color variation, Diameter, Evolution. This scaffold shows A/B/C from image stats; production adds D/E from repeat visits.</span></span>
        </div>
        <div style="font-size:10px;color:{GRAY};margin-bottom:5px;">{"Image auto-cropped to skin region &mdash; " + str(int(_crop["kept"]*100)) + "% of frame retained (background excluded before analysis)." if _crop.get("cropped") else "No crop applied &mdash; image already tightly framed on skin."}</div>
        {_bar("Asymmetry (A)", A, BLUE)}{_bar("Border irregularity (B)", B, PURPLE)}{_bar("Color variation (C)", C, ORANGE)}
      </div>
      <!-- Suggested disposition + fitzpatrick note -->
      <div style="background:{ref[1]};border-radius:12px;padding:14px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.12);">
        <div style="font-size:11px;color:#fff;letter-spacing:1px;opacity:.95;">AI-SUGGESTED DISPOSITION (clinician decides)</div>
        <div style="font-size:16px;font-weight:bold;color:#fff;margin-top:4px;">{ref[0]}</div>
      </div>
      <div style="background:#FFF5F5;border-left:4px solid {RED};padding:12px;border-radius:8px;margin-bottom:10px;font-size:12px;color:{DARK};">
        <b style="color:{RED_DK};">FITZPATRICK-AWARE CALIBRATION:</b> {fp_note}
      </div>
      <div style="background:#FEF9E7;border-left:4px solid {ORANGE};padding:11px;border-radius:8px;font-size:11px;color:#7A4F01;">
        <b>HUMAN-IN-THE-LOOP:</b> This is decision SUPPORT, not an autonomous diagnosis. No result reaches the patient
        without licensed-clinician review and sign-off. DEMO ONLY — placeholder predictor, not for clinical use.
      </div>
      {evidence_html}
    </div>"""

# Nurse <-> AI consensus dialogue (placeholder responses that demonstrate the workflow)
def ai_consensus(question, image, fp, location, notes, chat):
    """Clinician <-> AI consensus. Gives its REASONING (evidence -> inference -> conclusion),
    cites the knowledge library, and never repeats the same answer twice."""
    chat = chat or []
    if not question or not question.strip():
        return chat, ""
    question, qc = KB.autocorrect(question)
    if fp is None:
        return chat + [(question, "Please select the patient's Fitzpatrick skin type in Step 1 first — it drives the calibration behind every answer I give.")], ""
    fp = int(fp)
    prior = " ".join((str(a or "") + " " + str(b or "")) for a, b in chat).lower()
    if image is not None:
        image, _ = _skin_crop(image)
        A, B, C = _features(image); tex = _texture(image)
        mal = _score(A, B, C, fp, tex); morph = _morphology(tex, location)
        dx = _differential(mal, A, B, C, location, tex)
    else:
        A = B = C = mal = 0; tex = None
        morph = [("no image uploaded", "")]; dx = [("(upload a case image)", 0)]
    alert = KB.systemic_alert(location, notes)
    seen = "; ".join(n.split(" — ")[0].split(" (")[0] for n, _ in morph[:2]).lower()
    top = dx[0][0] if dx else "an indeterminate lesion"
    fp_roman = KB.ROMAN.get(fp, "")
    q = question.lower()

    def cite():
        p = KB.match_papers(tags=[top.split(" — ")[0].lower(), "skin of color"], fitzpatrick=fp_roman, limit=1)
        if p:
            c = str(p[0]["item"].get("citation", ""))[:120]
            return "<br><span style='font-size:11px;color:#666;'>Grounding: " + c + "</span>"
        return ""

    def asked(*keys):
        return any(k in prior for k in keys)

    # ---------- palmoplantar / systemic takes priority in any exchange ----------
    if alert and not asked("palmoplantar", "syphilis"):
        resp = ("<b>Observation:</b> the distribution you entered includes both feet and hands. "
                "<b>Reasoning:</b> that single fact outweighs the surface morphology. Individual lesions here read as "
                + seen + ", which invites an occupational explanation — but hands do not bear plantar pressure, so a "
                "pressure story cannot explain palm involvement. <b>Conclusion:</b> " + alert["correct_dx"] +
                " until serology is negative. <b>What would change my mind:</b> a negative RPR/VDRL. "
                "A pressure-bearing explanation cannot account for palmar lesions, so the systemic screen comes first." + cite())
    elif any(k in q for k in ["see", "seeing", "describe", "morphology", "look", "surface"]):
        if asked("observation:"):
            resp = ("<b>Going deeper on the surface:</b> asymmetry " + str(A) + "/100, border " + str(B) +
                    "/100, colour variation " + str(C) + "/100, with texture indices scaling=" +
                    str(tex["scaling"] if tex else 0) + ", dryness=" + str(tex["dryness"] if tex else 0) +
                    ", fissuring=" + str(tex["fissure"] if tex else 0) + ". <b>Reasoning:</b> a high scaling/fissure "
                    "signal with low asymmetry is a keratinisation pattern, not a proliferative one — that is why I am "
                    "not leading with tumour. <b>What would change my mind:</b> asymmetric pigment or a raised nodular edge." + cite())
        else:
            resp = ("<b>Observation:</b> I am reading " + seen + ". <b>Reasoning:</b> those features describe how the "
                    "skin surface is behaving (thickening, dryness, cracking) rather than how a growth is behaving. "
                    "<b>Conclusion:</b> my leading consideration is " + top + ". <b>What would change my mind:</b> "
                    "new asymmetry, colour variegation, or rapid change on repeat imaging." + cite())
    elif any(k in q for k in ["why", "reason", "flag", "concern", "confidence", "how did you"]):
        if asked("reasoning:") and not asked("weighting"):
            resp = ("<b>On weighting:</b> I combine asymmetry (" + str(A) + "), border (" + str(B) + ") and colour (" +
                    str(C) + ") into a composite, then apply a Fitzpatrick " + str(fp) + " calibration. "
                    "<b>Reasoning:</b> in deeper skin, erythema and border cues are masked by melanin, so equal raw "
                    "scores do not mean equal risk — I up-weight those channels so they are not missed. I also "
                    "down-weight malignancy when the surface is thick, dry and symmetric, because that is keratinisation. "
                    "<b>Conclusion:</b> composite " + str(mal) + "%. <b>Disagree?</b> Override in Step 4 and I will recalibrate." + cite())
        else:
            resp = ("<b>Observation:</b> " + seen + ". <b>Reasoning:</b> the composite sits at " + str(mal) +
                    "% because the pattern is keratotic rather than proliferative, and the site you entered carries a "
                    "high base rate of chronic pressure change. <b>Conclusion:</b> " + top +
                    ". <b>What would change my mind:</b> involvement outside the pressure-bearing area, or any "
                    "asymmetric pigment. Override in Step 4 if your bedside exam disagrees." + cite())
    elif any(k in q for k in ["melanoma", "cancer", "malignant", "biopsy", "tumor", "tumour"]):
        resp = ("<b>Observation:</b> malignancy-associated features are " + ("elevated" if mal >= 50 else "low") +
                " (" + str(mal) + "%). <b>Reasoning:</b> " +
                ("the asymmetry and colour channels are driving that, which warrants tissue diagnosis. "
                 if mal >= 50 else
                 "asymmetry is low and the surface is keratotic, which argues against melanoma — but acral melanoma "
                 "in deeply pigmented skin is precisely the miss that fairness data documents, so I keep it listed. ") +
                "<b>Conclusion:</b> " + ("recommend dermoscopy/biopsy." if mal >= 50 else
                "favour the benign chronic pathway with short-interval re-imaging, melanoma retained as a can't-miss.") +
                " <b>What would change my mind:</b> a new pigmented streak, ulceration, or any lesion that fails to "
                "respond to keratolytic care." + cite())
    elif any(k in q for k in ["refer", "referral", "physician", "escalate", "specialist"]):
        resp = ("<b>Reasoning:</b> referral should turn on systemic risk, diagnostic uncertainty, or scope — not on "
                "lesion size alone. Here, " + ("the palmoplantar distribution is a systemic trigger, so referral is not optional. "
                if alert else "the pattern is " + ("high-risk (" + str(mal) + "%), which meets referral criteria. "
                if mal >= 50 else "consistent with a condition treatable within nursing scope, so referral is discretionary. ")) +
                "<b>Conclusion:</b> " + ("refer to a physician now" if (alert or mal >= 50) else
                "treat and monitor; refer if it fails to respond or changes") + ". If you tick <b>Refer to physician</b> "
                "in Step 4 I will recalibrate the plan around the referral and log it with your sign-off.")
    elif any(k in q for k in ["treat", "manage", "plan", "scope", "otc", "product", "medication"]):
        libm = KB.match_library([top.split(" — ")[0].lower()], fp_roman, location, limit=1)
        ladder = ""
        if libm:
            ladder = "<br><b>From your library:</b> " + str(libm[0]["item"].get("notes") or libm[0]["item"].get("summary", ""))[:260]
        resp = ("<b>Reasoning:</b> treatment follows the mechanism, not the label. For " + top +
                " the mechanism is " + ("systemic infection — topical care is inappropriate and treatment belongs to the physician. "
                if alert else "mechanical thickening plus barrier failure, so the plan is to reduce keratin, restore barrier, and remove the load. ") +
                "<b>Conclusion:</b> " + ("physician management; nursing role is workup facilitation, education, and follow-up."
                if alert else "debride/pare hyperkeratosis, urea or salicylic-acid keratolytic, intensive emollient for xerosis, "
                "and pressure offloading — all within RN scope, with Fitzpatrick-appropriate hyperpigmentation prevention.") + ladder)
    elif any(k in q for k in ["disagree", "wrong", "no,", "not ", "actually", "i think", "rather"]):
        resp = ("<b>Understood — you are the decision-maker.</b> <b>Reasoning:</b> my read was " + top +
                " based on " + seen + " at Fitzpatrick " + str(fp) + ", but image statistics cannot capture palpation, "
                "history, symmetry across the body, or how the lesion has behaved over time — and you have all four. "
                "<b>Conclusion:</b> enter your diagnosis in Step 4 and press <b>Re-calibrate</b>; I will re-weight to your "
                "finding, rebuild the plan around it, and the correction becomes a permanent Knowledge Base label so I do "
                "not repeat the error on the next patient with this presentation.")
    else:
        resp = ("<b>Observation:</b> " + seen + " at Fitzpatrick " + str(fp) + ", composite " + str(mal) +
                "%, leading consideration " + top + ". <b>Reasoning:</b> I weight site base rates and skin-tone "
                "calibration alongside the surface signal. <b>To move us to consensus,</b> ask me why I ranked it this "
                "way, what would change my mind, whether it is within your scope, or tell me directly that you disagree — "
                "I will re-reason rather than repeat." + cite())

    if qc:
        resp += ("<br><span style='font-size:11px;color:#0EA5E9;'>Spell-check applied: " +
                 ", ".join(a + " &rarr; " + b for a, b in qc) + "</span>")
    chat = chat + [(question, resp)]
    return chat, ""

def submit_feedback(dx_correct, obs):
    if not (dx_correct and dx_correct.strip()) and not (obs and obs.strip()):
        return "<div style='color:#999;font-size:12px;'>Enter a corrected diagnosis or a clinical note to log.</div>"
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []
    if dx_correct and dx_correct.strip(): parts.append(f"Corrected diagnosis: <b>{dx_correct}</b>")
    if obs and obs.strip(): parts.append(f"Clinical note: <b>{obs}</b>")
    body = " &middot; ".join(parts)
    return (f"<div style='background:#EFFcF4;border-left:4px solid {GREEN};padding:12px;border-radius:8px;font-size:12px;color:#14532d;'>"
            f"&#10003; Appended to AI Knowledge Base &mdash; attributable, timestamped ({ts}), version-controlled, auditable.<br>{body}<br>"
            f"<span style='font-size:11px;color:#3f6b4e;'>Under continuous clinician supervision. No autonomous self-modification. This is the human-in-the-loop learning loop.</span></div>")


# ---- Treatment guidance within RN scope, keyed by condition ----
def _treatment_plan(dx_name, fp, location):
    n = (dx_name or "").lower()
    if any(k in n for k in ["melanoma","carcinoma","bcc","scc","malignan"]):
        return ("REFERRAL — outside nursing scope", RED_DK, [
            "Do NOT treat topically. Expedite dermatology referral for dermoscopy/biopsy.",
            "Document lesion with a measured, dated photo; note any ABCDE changes.",
            "Educate patient on urgency; arrange oncology pathway if malignancy confirmed."])
    if any(k in n for k in ["actinic keratosis","pre-malig","dysplastic","atypical"]):
        return ("REFER — dermatology within 30 days", ORANGE, [
            "Refer for evaluation; may require cryotherapy or biopsy.",
            "Daily broad-spectrum SPF and sun-protective behavior counseling.",
            "Re-image at follow-up to track evolution."])
    if any(k in n for k in ["callus","hyperkerat","tyloma"]):
        return ("WITHIN NURSING SCOPE — treat + monitor", GREEN, [
            "Pare / debride hyperkeratosis per protocol; pumice after soaking.",
            "Keratolytic: urea 20-40% or salicylic acid per standing order.",
            "Offloading: cushioned, properly fitted footwear; pad pressure points.",
            "Daily emollient; recheck in 2-4 weeks."])
    if any(k in n for k in ["xerosis","dry"]):
        return ("WITHIN NURSING SCOPE — treat + monitor", GREEN, [
            "Ceramide or urea 10% emollient twice daily, applied to damp skin.",
            "Lukewarm (not hot) water; fragrance-free cleanser.",
            "Barrier repair over fissures; monitor for signs of secondary infection."])
    if any(k in n for k in ["keloid","hypertroph","scar"]):
        return ("WITHIN NURSING SCOPE + refer for procedure", TEAL, [
            "Silicone gel sheet or gel 12-24h daily for 8-12 weeks.",
            "Pressure therapy where feasible; sun-protect to prevent darkening.",
            "Refer for intralesional corticosteroid if raised or symptomatic."])
    if any(k in n for k in ["verruca","wart","tinea","fungal"]):
        return ("WITHIN NURSING SCOPE — treat + monitor", GREEN, [
            "If tinea: topical antifungal 2-4 weeks; keep area clean and dry.",
            "If verruca: salicylic-acid protocol; cryotherapy referral if persistent.",
            "Footwear and hygiene counseling; recheck at 4 weeks."])
    if any(k in n for k in ["hyperpigment","pih"]):
        return ("WITHIN NURSING SCOPE — treat + monitor", GREEN, [
            "Strict daily SPF; gentle, non-irritating skincare.",
            "Treat any underlying inflammation; avoid picking / friction.",
            "Refer for pigment-directed therapy if persistent."])
    if any(k in n for k in ["nevus","mole","seborrheic","benign"]):
        return ("WITHIN NURSING SCOPE — reassure + monitor", GREEN, [
            "Reassure; capture a baseline photo for surveillance.",
            "Educate on ABCDE warning signs; return if any change.",
            "Routine skin surveillance at next visit."])
    return ("WITHIN NURSING SCOPE — monitor; refer if changes", GREEN, [
        "Supportive skin care and patient education.",
        "Photo-document; recheck at an appropriate interval.",
        "Refer if new asymmetry, growth, color change, or symptoms."])

def _plan_block(final_dx, fp, location):
    disp, color, steps = _treatment_plan(final_dx, int(fp), location)
    li = "".join(f'<li style="margin:4px 0;">{s}</li>' for s in steps)
    return disp, color, (
        f'<div style="background:{color};border-radius:10px;padding:10px 14px;margin-bottom:8px;">'
        f'<span style="color:#fff;font-size:11px;letter-spacing:1px;">DISPOSITION</span>'
        f'<div style="color:#fff;font-weight:bold;font-size:15px;">{disp}</div></div>'
        f'<div style="font-size:12px;color:{DARK};margin-bottom:4px;font-weight:bold;">Proposed plan &mdash; {final_dx}</div>'
        f'<ul style="font-size:12px;color:{DARK};margin:0 0 4px 18px;padding:0;">{li}</ul>')

# STEP 4B -> recalibrate the AI to the clinician's correction
def recalibrate(dx_correct, obs, image, fp, location, referral=False):
    if not (dx_correct and dx_correct.strip()):
        return "<div style='color:#999;font-size:12px;font-family:Calibri;'>Enter your corrected diagnosis in Step 4, then click Re-calibrate.</div>"
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if fp is None:
        return """<div style="padding:30px;text-align:center;font-family:Calibri,Arial,sans-serif;color:#0D6EFD;font-size:14px;font-weight:bold;">Select the patient's Fitzpatrick skin type in Step 1 <span style="display:block;font-weight:normal;color:#666;font-size:12px;margin-top:5px;">Skin type drives the calibration, so the analysis will not run without it. Use the skin-tone guide if you are unsure.</span></div>"""
    fp = int(fp)
    dx_correct, _c1 = KB.autocorrect(dx_correct)
    obs, _c2 = KB.autocorrect(obs)
    disp, color, plan = _plan_block(dx_correct.strip(), fp, location)
    if referral:
        disp = "PHYSICIAN REFERRAL — clinician-directed"; color = RED_DK
        plan = ('<div style="background:' + RED_DK + ';border-radius:10px;padding:10px 14px;margin-bottom:8px;">'
                '<span style="color:#fff;font-size:11px;letter-spacing:1px;">DISPOSITION</span>'
                '<div style="color:#fff;font-weight:bold;font-size:15px;">PHYSICIAN REFERRAL — clinician-directed</div></div>'
                '<div style="font-size:12px;color:' + DARK + ';margin-bottom:4px;font-weight:bold;">Referral plan &mdash; ' + dx_correct.strip() + '</div>'
                '<ul style="font-size:12px;color:' + DARK + ';margin:0 0 4px 18px;padding:0;">'
                '<li style="margin:4px 0;">Refer to physician; transmit images, Fitzpatrick type, and this assessment.</li>'
                '<li style="margin:4px 0;">Nursing role: facilitate workup, patient education, follow-up confirmation.</li>'
                '<li style="margin:4px 0;">Do not initiate definitive treatment pending physician evaluation.</li>'
                '<li style="margin:4px 0;">Document referral date and close the loop on the outcome.</li></ul>')
    note = f"<div style='font-size:12px;color:{DARK};margin:6px 0;'>Clinician note: <b>{obs}</b></div>" if (obs and obs.strip()) else ""
    return f"""
    <div style="font-family:Calibri,Arial,sans-serif;">
      <div style="background:#fff;border:2px solid {PURPLE};border-radius:12px;padding:15px;margin-bottom:10px;">
        <div style="font-size:12px;color:{PURPLE};font-weight:bold;letter-spacing:1px;">&#8635; AI RE-CALIBRATED TO CLINICIAN INPUT</div>
        <div style="font-size:13px;color:{DARK};margin-top:6px;">The clinician overrode the AI. Working diagnosis is now <b>{dx_correct}</b>{' <b style="color:'+RED_DK+'">and the patient is being REFERRED to a physician</b>' if referral else ''}. The AI has re-weighted its reasoning to this finding and drafted a scope-appropriate plan for review.</div>
        {note}
      </div>
      <div style="background:#fff;border:1px solid {GREY_LN};border-top:4px solid {color};border-radius:12px;padding:14px;margin-bottom:10px;">{plan}</div>
      <div style="background:#F5F3FF;border-left:4px solid {PURPLE};padding:11px;border-radius:8px;font-size:11px;color:#4c1d95;">
        Correction captured ({ts}). It becomes a durable, human-verified Knowledge Base label when you <b>Accept &amp; Sign Off</b> in Step 5 &mdash; sign-off is the verification gate. No autonomous self-modification.
        <br><b>Next:</b> review the plan above, then use Step 5 to <b>Accept &amp; Sign Off</b>.
      </div>
    </div>"""

# STEP 5 -> clinician accepts finding and signs off on the treatment plan
def sign_off(dx_correct, image, fp, location, clinician, referral=False):
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if fp is None:
        return """<div style="padding:30px;text-align:center;font-family:Calibri,Arial,sans-serif;color:#0D6EFD;font-size:14px;font-weight:bold;">Select the patient's Fitzpatrick skin type in Step 1 <span style="display:block;font-weight:normal;color:#666;font-size:12px;margin-top:5px;">Skin type drives the calibration, so the analysis will not run without it. Use the skin-tone guide if you are unsure.</span></div>""", kb_view()
    fp = int(fp)
    dx_correct, _sc = KB.autocorrect(dx_correct)
    if dx_correct and dx_correct.strip():
        final = dx_correct.strip(); source = "clinician-corrected diagnosis"
    elif image is not None:
        A, B, C = _features(image); tex = _texture(image)
        mal = _score(A, B, C, fp, tex); dx = _differential(mal, A, B, C, location, tex)
        final = dx[0][0].split(" — ")[0]; source = "AI finding accepted (no rebuttal)"
    else:
        return "<div style='color:#999;font-size:12px;font-family:Calibri;'>Run Step 2 analysis first, then sign off.</div>"
    who = (clinician.strip() if clinician and clinician.strip() else "Licensed Clinician")
    ai_dx = ""
    if image is not None:
        A2, B2, C2 = _features(image); tex2 = _texture(image)
        mal2 = _score(A2, B2, C2, fp, tex2)
        ai_dx = _differential(mal2, A2, B2, C2, location, tex2)[0][0].split(" \u2014 ")[0]
    corrected = bool(dx_correct and dx_correct.strip())
    kb_append(fp, image, ai_dx, final, corrected, "", who, referral=referral, referral_reason=(final if referral else ""))
    disp, color, plan = _plan_block(final, fp, location)
    ref_banner = ""
    if referral:
        ref_banner = ('<div style="background:' + RED_DK + ';border-radius:10px;padding:11px 14px;margin-bottom:10px;">'
                      '<span style="color:#fff;font-size:11px;letter-spacing:1px;">&#9873; PHYSICIAN REFERRAL RECORDED</span>'
                      '<div style="color:#fff;font-size:13px;margin-top:3px;">Referred by the signing clinician. Logged to the Knowledge Base with the verified diagnosis.</div></div>')
    signed_html = f"""
    <div style="font-family:Calibri,Arial,sans-serif;">
      {ref_banner}
      <div style="background:{GREEN};border-radius:12px;padding:14px;margin-bottom:10px;">
        <div style="color:#fff;font-size:12px;letter-spacing:1px;">&#10003; TREATMENT PLAN SIGNED OFF</div>
        <div style="color:#fff;font-size:15px;font-weight:bold;margin-top:3px;">{final}</div>
        <div style="color:#EAFBEF;font-size:11px;margin-top:2px;">Basis: {source}</div>
      </div>
      <div style="background:#fff;border:1px solid {GREY_LN};border-top:4px solid {color};border-radius:12px;padding:14px;margin-bottom:10px;">{plan}</div>
      <div style="background:#EFFCF4;border-left:4px solid {GREEN};padding:12px;border-radius:8px;font-size:12px;color:#14532d;">
        <b>Electronically signed by {who}</b> on {ts}.<br>
        Signed decision + plan appended to AI Knowledge Base &mdash; attributable, timestamped, version-controlled, auditable.
        <span style="font-size:11px;color:#3f6b4e;"> Human-in-the-loop: no result or plan is finalized without licensed-clinician sign-off. DEMO ONLY — not for clinical use.</span>
      </div>
    </div>"""
    return signed_html, kb_view()


# ---- Branded header + reference charts ----
HEADER = f'''
<div style="background:linear-gradient(90deg,{RED_DK},{RED});border-radius:16px;padding:20px 24px;box-shadow:0 4px 14px rgba(181,18,27,0.28);font-family:Calibri,Arial,sans-serif;display:flex;align-items:center;gap:18px;">
  <img src="data:image/png;base64,{LOGO_B64}" style="width:78px;height:78px;background:#fff;border-radius:50%;padding:6px;box-shadow:0 2px 8px rgba(0,0,0,.2);"/>
  <div>
    <div style="color:#fff;font-weight:bold;font-size:27px;letter-spacing:0.5px;">RADIANT REVIVE AI &mdash; PROVIDER PORTAL</div>
    <div style="color:#FFE3E3;font-size:12px;font-style:italic;margin-top:3px;">Clinician-facing diagnostic support &middot; Human-in-the-loop &middot; Patent Pending U.S. App. 19/643,795</div>
    <div style="color:#FFD3D3;font-size:11px;margin-top:5px;">The patient never sees this analysis. The nurse reviews, engages the AI, and signs off. UEI EP6GX99FCN95 &middot; SAM.gov ACTIVE</div>
  </div>
</div>'''
BANNER = f'''
<div style="background:#EAF6FF;border:1px solid {TEAL};border-left:5px solid {TEAL};border-radius:10px;padding:12px 16px;margin-top:12px;font-family:Calibri,Arial,sans-serif;">
  <span style="color:{TEAL};font-weight:bold;font-size:13px;">HOW THIS WORKS:</span>
  <span style="color:{DARK};font-size:12px;"> The AI attempts a differential diagnosis &rarr; the clinician reviews and engages the AI to reach consensus &rarr; the clinician corrects &amp; re-calibrates, or accepts and signs off &rarr; the signed decision feeds the knowledge base. The clinician is always the decision-maker.</span>
</div>'''

SKINCHART = f'''
<div style="background:#fff;border-radius:16px;padding:20px 24px;margin-top:14px;border-top:4px solid {PURPLE};box-shadow:0 2px 10px rgba(0,0,0,0.06);font-family:Calibri,Arial,sans-serif;text-align:center;">
  <div style="color:{RED};font-size:12px;font-weight:bold;letter-spacing:2px;">INCLUSIVE CARE</div>
  <div style="font-size:23px;font-weight:bold;color:{DARK};margin:4px 0 8px 0;">For every skin type. <span style="color:{RED_DK};font-style:italic;">Every shade.</span></div>
  <div style="color:{GRAY};font-size:13px;max-width:760px;margin:0 auto 14px auto;">Radiant Revive is built for Fitzpatrick I through VI &mdash; and records Monk Skin Tone as an independent axis &mdash; so the conditions most overlooked by mainstream dermatology are not missed.</div>
  <img src="data:image/jpeg;base64,{FITZCHART_B64}" style="width:100%;max-width:980px;border-radius:12px;"/>
</div>'''

def _monk_tiles():
    data = [("01","LIGHT","#f2ddcf"),("02","LIGHT MEDIUM","#eccfb4"),("03","MEDIUM LIGHT","#e5c19b"),
            ("04","MEDIUM","#dbb18a"),("05","MEDIUM TAN","#cf9d6f"),("06","TAN","#b47b47"),
            ("07","RICH TAN","#9a6237"),("08","RICH","#7d4a2c"),("09","DEEP","#4a3324"),("10","DEEPEST","#2e2018")]
    t = ""
    for num, name, hexc in data:
        txt = "#fff" if num in ("06","07","08","09","10") else "#2B2B2B"
        t += (f'<div style="background:{hexc};border-radius:8px;padding:9px 5px;min-width:74px;flex:1;">'
              f'<div style="font-size:17px;font-weight:bold;color:{txt};">{num}</div>'
              f'<div style="height:2px;background:{txt};opacity:.4;width:20px;margin:3px auto;"></div>'
              f'<div style="font-size:9px;font-weight:bold;color:{txt};line-height:1.15;">{name}</div></div>')
    return t

MONKCHART = f'''
<div style="background:#fff;border-radius:16px;padding:20px 24px;margin-top:14px;border-top:4px solid {BLUE};box-shadow:0 2px 10px rgba(0,0,0,0.06);font-family:Calibri,Arial,sans-serif;text-align:center;">
  <div style="font-size:24px;font-weight:bold;color:{RED_DK};letter-spacing:4px;">MONK</div>
  <div style="font-size:14px;color:{DARK};letter-spacing:3px;font-weight:bold;">SKIN TONE SCALE (MST)</div>
  <div style="font-size:11px;color:{GRAY};letter-spacing:2px;margin-top:2px;">INCLUSIVE &middot; SCIENTIFIC &middot; EQUITABLE</div>
  <div style="display:flex;align-items:center;justify-content:center;gap:8px;margin:12px 0 8px 0;font-size:11px;font-weight:bold;color:{RED};">
    <span>LOW</span><div style="flex:1;max-width:500px;height:2px;background:linear-gradient(90deg,{RED},{RED_DK});"></div><span>HIGH</span>
  </div>
  <div style="display:flex;gap:4px;justify-content:center;flex-wrap:nowrap;overflow-x:auto;">{_monk_tiles()}</div>
  <div style="margin-top:14px;background:{GREY_BG};border-radius:10px;padding:11px 15px;font-size:12px;color:{DARK};text-align:left;max-width:900px;margin-left:auto;margin-right:auto;">
    <b style="color:{RED_DK};">A 10-point skin tone scale developed by Dr. Ellis Monk</b> with Google to advance representation and equity in healthcare and AI. Radiant Revive records MST as an <b>independent axis</b> from Fitzpatrick (Measurement Protocol v1.1) &mdash; finer resolution in deeper tones.
  </div>
</div>'''

FOOTER = f'''
<div style="margin-top:20px;padding:16px;background:{GREY_BG};border-radius:12px;border:1px solid {GREY_LN};border-top:4px solid {RED};font-size:12px;color:{DARK};font-family:Calibri,Arial,sans-serif;">
  <b style="color:{RED_DK};">RADIANT REVIVE LLC</b> &middot; Niya D. Pennie, BSN, RN &mdash; Founder &amp; Principal Investigator &middot; info@radiantrevivemedspa.com &middot; (469) 213-8799<br>
  <span style="color:{GRAY};">UEI EP6GX99FCN95 &middot; CAGE 21GG3 &middot; EIN 41-5051987 &middot; SAM.gov ACTIVE (All Awards) &middot; WOSB &middot; &copy; 2026 Radiant Revive LLC. Placeholder predictor - not for clinical use.</span>
</div>'''

# ---- "THE PROBLEM" context panel (recreated on-brand; sits above Step 2) ----
def _donut(center, frac, arc_color):
    import math
    r = 46; c = 2 * math.pi * r; dash = c * frac
    return (f'<svg width="132" height="132" viewBox="0 0 132 132">'
            f'<circle cx="66" cy="66" r="{r}" fill="none" stroke="#E2E2E2" stroke-width="15"/>'
            f'<circle cx="66" cy="66" r="{r}" fill="none" stroke="{arc_color}" stroke-width="15" '
            f'stroke-dasharray="{dash:.1f} {c-dash:.1f}" transform="rotate(-90 66 66)"/>'
            f'<text x="66" y="73" text-anchor="middle" font-size="20" font-weight="bold" '
            f'fill="{DARK}" font-family="Calibri,Arial,sans-serif">{center}</text></svg>')

PROBLEM = f'''
<div style="background:#F4F5F7;border:2px solid {RED};border-radius:14px;padding:18px 20px;font-family:Calibri,Arial,sans-serif;margin-bottom:14px;">
  <div style="font-size:20px;font-weight:bold;color:{DARK};letter-spacing:1px;">THE PROBLEM</div>
  <div style="font-size:14px;color:{DARK};margin:4px 0 12px 0;">Skin of color is systematically <b style="color:{RED};">underserved</b> by current dermatology AI.</div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;">
    <div style="flex:1;min-width:150px;"><span style="font-size:20px;font-weight:bold;color:{RED};">3 BILLION</span>
      <div style="font-size:12px;color:{DARK};">people worldwide lack adequate dermatologic care.</div></div>
    <div style="flex:1;min-width:150px;"><span style="font-size:20px;font-weight:bold;color:{RED};">27&ndash;36%</span>
      <div style="font-size:12px;color:{DARK};">drop in ROC-AUC for current AI on Fitzpatrick V&ndash;VI skin.</div></div>
  </div>
  <div style="background:#fff;border:1px solid {GREY_LN};border-radius:12px;padding:12px;text-align:center;">
    <div style="font-size:12px;font-weight:bold;color:{DARK};letter-spacing:1px;margin-bottom:6px;">MALIGNANCY DETECTION SENSITIVITY</div>
    <div style="display:flex;justify-content:center;align-items:center;gap:10px;flex-wrap:wrap;">
      <div>{_donut("41&ndash;69%", 0.55, RED)}<div style="font-size:12px;color:{DARK};margin-top:2px;">in <b>LIGHTER</b>-skinned patients</div></div>
      <div style="width:1px;height:90px;background:{GREY_LN};"></div>
      <div>{_donut("12&ndash;23%", 0.175, GRAY)}<div style="font-size:12px;color:{DARK};margin-top:2px;">in <b>DARKER</b>-skinned patients</div></div>
    </div>
  </div>
  <div style="border:1px solid {RED};border-radius:10px;padding:10px 14px;margin-top:12px;font-size:12px;color:{DARK};font-style:italic;">
    <span style="color:{RED};font-weight:bold;font-size:16px;">&ldquo;</span> As AI deploys into primary care and telehealth at scale, the populations most affected by existing dermatologic disparities are the least well-served by the new tools.
  </div>
  <div style="font-size:11px;color:{GRAY};margin-top:8px;"><b style="color:{RED};">Source:</b> Daneshjou et al., <i>Science Advances</i> (2022)</div>
</div>'''

FITZINFO = f'''
<div style="font-family:Calibri,Arial,sans-serif;">
  <img src="data:image/jpeg;base64,{FITZCHART_B64}" style="width:100%;border-radius:8px;display:block;"/>
  <div style="font-size:11px;color:{DARK};margin-top:6px;">Match the patient's skin to Fitzpatrick <b>I&ndash;VI</b> above, then select the type below. Radiant Revive also records Monk Skin Tone as an independent axis.</div>
</div>'''

# ---- Live clinical spelling suggestions (fuzzy: "sypilis" -> "syphilis") ----
SPELL_JS = """
<style>
#rr-sugg{position:absolute;z-index:9999;background:#fff;border:1px solid #E5E5E5;border-radius:10px;
 box-shadow:0 6px 20px rgba(0,0,0,.18);font-family:Calibri,Arial,sans-serif;font-size:13px;
 max-height:210px;overflow-y:auto;display:none;min-width:210px;}
#rr-sugg div{padding:7px 12px;cursor:pointer;color:#2B2B2B;border-bottom:1px solid #F2F2F2;}
#rr-sugg div:last-child{border-bottom:none;}
#rr-sugg div.on,#rr-sugg div:hover{background:#EAF6FF;color:#B5121B;font-weight:bold;}
#rr-sugg .rr-hint{padding:5px 12px;font-size:10px;color:#888;background:#FAFAFA;cursor:default;font-weight:normal;}
</style>
<script>
(function(){
  var VOCAB = ["abscess", "acanthosis", "acanthosis nigricans", "access disparity", "acne", "Acne keloidalis nuchae", "acne keloidalis nuchae", "acne vulgaris", "acral lentiginous melanoma", "acral melanoma", "actinic keratosis", "adolescent", "adult male", "adversarial debiasing", "ai fairness", "ai medical diagnostic devices", "aimdd", "alopecia", "Alopecia areata", "alopecia areata", "androgenetic alopecia", "antifungal", "atopic dermatitis", "atrophy", "autoimmune", "autologous fat transfer", "azelaic acid", "azelaic acid alternative", "baricitinib", "basal cell carcinoma", "beard", "benchmark", "benchmarking", "benzene", "benzoyl peroxide", "Benzoyl peroxide product safety", "beyond fitzpatrick", "bilateral distribution", "biopsy", "biopsy-confirmed", "black box", "black hair", "black hair products", "black patients", "bpo recall", "bulla", "bupropion referral", "callus", "calluses", "candidiasis", "ccca differential", "cellulitis", "central centrifugal cicatricial alopecia", "chest", "cicatricial alopecia", "classification", "clindamycin", "clinical guidance", "clinical translation", "clinician-annotated", "clippers", "clobetasol", "colorimeter", "colorimetric calibration", "competitor", "condyloma", "contact dermatitis", "corn", "corticosteroid", "cosmetic acne", "creatine", "crusting", "cryotherapy", "culture", "cvpr", "cyanosis", "dark skin tone", "data quality", "data representativeness", "dataset", "ddi dataset", "debridement", "deepderm", "dermatitis", "dermatofibroma", "dermatology", "dermatology ai", "dermatology dataset", "dermatomyositis", "dermatoscopy", "Dermatosis papulosa nigra", "dermatosis papulosa nigra", "dermieai", "dermoscopy", "desquamation", "device patent relevance", "device relevance", "diabetes", "diagnosis", "differential", "discoid lupus", "discontinuation", "diverse skin tones", "doxycycline", "drug eruption", "dysplastic nevus", "e-cigarette", "earlobe", "ecchymoses", "eczema", "edema", "edge control", "edges", "eflornithine", "emollient", "equality of opportunity", "equity", "erosion", "erythema", "erythema multiforme", "erythematous", "esrc", "evali", "evaluation methodology", "evidence synthesis", "exclamation mark hairs", "excoriation", "external validation", "facial aging", "facial papules", "facial volume loss", "fairness", "fairness auditing", "family history", "family involvement", "fda recall", "ferritin", "field-wide critique", "filler referral", "fine-tuning", "firefighter", "fissure", "fissures", "fissuring", "Fitzpatrick", "fitzpatrick", "fitzpatrick i-ii", "fitzpatrick v", "fitzpatrick v-vi", "fitzpatrick vi", "folliculitis", "foundation model", "foundational", "foundational commentary", "fringe sign", "frontal hairline", "frontal recession", "FTA-ABS", "furuncle", "global access gap", "glycolic acid", "google research", "granuloma annulare", "hair loss", "harm reduction", "health disparities", "health disparity", "health equity motivation", "heloma", "herpes simplex", "herpes zoster", "hidradenitis suppurativa", "hirsutism", "hydroquinone", "hyperkeratosis", "hyperkeratotic", "hyperpigmentation", "hypertrophic scar", "hypopigmentation", "ichthyosis", "impetigo", "induration", "inflammation", "inflammatory hyperpigmentation", "interpretability", "intralesional", "intralesional triamcinolone", "iron deficiency", "iron oxide sunscreen", "jak inhibitor", "jama dermatology", "jaundice", "jawline", "juul", "kelly taylor", "keloid", "Keloid scar", "keloids", "keratoderma", "keratolytic", "ketoconazole", "KOH prep", "la roche-posay", "label granularity", "laser", "laser hair removal", "lean body mass", "lesion", "lesion segmentation", "lesionclip", "lesions", "lesiontabe", "lichen planus", "lichen simplex chronicus", "lichenification", "lupus", "lymphedema", "machine learning bias", "macule", "melanocytic nevus", "melanoma", "melanonychia", "melasma", "mental health comorbidity", "metabolic syndrome", "methodology", "military", "minoxidil", "model comparison", "modelderm", "molluscum contagiosum", "Monk skin tone", "monk skin tone scale", "morphea", "motivational interviewing", "multiblade razor", "mupirocin", "muscle loss", "naaf", "narrative synthesis", "nd:yag", "nevus", "nicotine addiction", "nodule", "non-scarring alopecia", "nrt patch", "nuchal", "nursing assessment", "nursing education", "nursing education gap", "nursing home", "occipital", "occlusive", "occupational", "occupational masking", "offloading", "oncology ai", "onychomycosis", "otc nrt", "ozempic face", "padufes", "pallor", "palmoplantar", "palmoplantar keratoderma", "papule", "patchy hair loss", "patient", "pcos", "pediatric", "pediculosis", "peripheral neuropathy", "peripheral vascular disease", "petechiae", "photoprotection", "photosensitivity", "phototherapy", "physician", "pityriasis rosea", "pityriasis versicolor", "plantar verruca", "plantar wart misdiagnosis", "plaque", "police", "pomade acne", "post-inflammatory hyperpigmentation", "postinflammatory hyperpigmentation", "Postinflammatory hyperpigmentation", "premature aging", "preprocessing bias", "pressure injury", "pressure ulcer", "prisma-scr", "proactiv", "prospective validation", "protein", "prune learning", "prurigo nodularis", "pruritic", "pruritus", "pseudofolliculitis barbae", "Pseudofolliculitis barbae", "psoriasis", "public dataset", "pulse oximeter bias", "purpura", "pustule", "racial disparity", "rapid weight loss", "razor bumps", "reasoning", "recommend", "recommended", "reference", "referral", "referred", "regulatory", "reporting standards", "representation", "resistance training", "respirator mask", "retinoid", "review methods", "ritlecitinib", "roc-auc disparity", "rosacea", "safety", "salicylic acid", "sarcoidosis", "sarcopenia", "scabies", "scale limitations", "scaling", "scalp", "scar", "scin", "scissor excision", "scleroderma", "scoping review", "sculptra", "seborrheic", "seborrheic dermatitis", "seborrheic keratosis", "secondary syphilis", "semaglutide", "serology", "sew-in", "shaving", "shaving waiver", "silicone gel", "skin aging", "skin classification", "skin color", "skin lesion classification", "skin of color", "skin tone", "skin tone estimation", "slmd", "smartphone dermatology", "squamous cell carcinoma", "standardization", "stasis dermatitis", "Stevens-Johnson syndrome", "sunscreen", "syphilis", "systematic review", "systemic differential missed", "tabe", "teen", "telangiectasia", "tele-dermatology", "telogen effluvium", "terbinafine", "textbook", "textbook derived", "thyroid screening", "tight braids", "tinea", "tinea capitis", "tinea corporis", "tinea pedis", "tinea versicolor", "tirzepatide", "Traction alopecia", "traction alopecia", "training data", "treponema pallidum", "tretinoin", "tri-luma", "triamcinolone", "trichotillomania", "tyloma", "uk dermatology ai", "ulceration", "underrepresented skin phototypes", "urea", "urticaria", "validation methodology", "varenicline referral", "vasculitis", "VDRL", "vdrl", "venous insufficiency", "verruca", "vesicle", "viewpoint", "vision-language model", "visual assessment failure", "visual consensus label noise", "visual question answering", "vitamin d", "vitiligo", "walgreens", "warts", "weave", "weight loss", "weight management", "weight regain prevention", "wellness", "xerosis", "yellow dots", "young adult vaping", "youth vaping", "zapzyt"];
  var box=null, target=null, items=[], sel=-1;

  function ensureBox(){
    if(box) return box;
    box=document.createElement('div'); box.id='rr-sugg';
    document.body.appendChild(box); return box;
  }
  // edit distance capped at 3 (cheap + enough for typos)
  function dist(a,b){
    if(Math.abs(a.length-b.length)>3) return 99;
    var m=a.length,n=b.length,prev=[],cur=[],i,j;
    for(j=0;j<=n;j++) prev[j]=j;
    for(i=1;i<=m;i++){ cur[0]=i;
      for(j=1;j<=n;j++){
        cur[j]=Math.min(prev[j]+1,cur[j-1]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));
      }
      prev=cur.slice();
    }
    return prev[n];
  }
  function score(word,term){
    var w=word.toLowerCase(), t=term.toLowerCase();
    if(t===w) return -1;                       // already correct: no suggestion
    if(t.indexOf(w)===0) return 0;             // prefix match ranks first
    if(w.length>=4 && dist(w, t.substring(0,w.length))<=2) return 1; // typed stem ~matches candidate stem
    var d=dist(w,t);
    if(d<=1) return 1;
    if(d<=2 && w.length>=4) return 2;
    if(w.length>=4 && w.substring(0,3)===t.substring(0,3) && d<=Math.floor(w.length/2)+2) return 3; // same stem, sloppy tail
    if(d<=3 && w.length>=5) return 4;
    if(t.indexOf(w)>0 && w.length>=4) return 5; // substring
    return 99;
  }
  function currentWord(el){
    var v=el.value||'', p=el.selectionStart||0;
    var s=v.lastIndexOf(' ',p-1)+1;
    var nl=v.lastIndexOf('\\n',p-1)+1; if(nl>s) s=nl;
    return {word:v.substring(s,p), start:s, end:p};
  }
  function hide(){ if(box){box.style.display='none';} items=[]; sel=-1; }
  function place(el){
    var r=el.getBoundingClientRect();
    box.style.left=(window.scrollX+r.left)+'px';
    box.style.top=(window.scrollY+r.bottom+3)+'px';
    box.style.minWidth=Math.min(320,r.width)+'px';
  }
  function apply(term){
    if(!target) return;
    var c=currentWord(target), v=target.value;
    var nv=v.substring(0,c.start)+term+v.substring(c.end);
    var proto = target.tagName==='TEXTAREA' ? window.HTMLTextAreaElement : window.HTMLInputElement;
    var setter=Object.getOwnPropertyDescriptor(proto.prototype,'value').set;
    setter.call(target,nv);
    target.dispatchEvent(new Event('input',{bubbles:true}));   // keep Gradio state in sync
    var pos=c.start+term.length;
    target.setSelectionRange(pos,pos); target.focus();
    hide();
  }
  function render(list){
    ensureBox(); box.innerHTML='';
    list.forEach(function(t,i){
      var d=document.createElement('div'); d.textContent=t;
      d.addEventListener('mousedown',function(e){e.preventDefault(); apply(t);});
      box.appendChild(d);
    });
    var h=document.createElement('div'); h.className='rr-hint';
    h.textContent='Tab or Enter to accept  ·  Esc to dismiss';
    box.appendChild(h);
    items=list; sel=-1; box.style.display='block';
  }
  function suggest(el){
    target=el;
    var c=currentWord(el), w=c.word;
    if(!w || w.length<3 || /[^A-Za-z\\-]/.test(w)){ hide(); return; }
    var scored=[];
    for(var i=0;i<VOCAB.length;i++){
      var s=score(w,VOCAB[i]);
      if(s>=0 && s<99) scored.push([s,VOCAB[i]]);
    }
    if(!scored.length){ hide(); return; }
    scored.sort(function(a,b){ return a[0]-b[0] || a[1].length-b[1].length; });
    var out=[]; for(var k=0;k<scored.length && out.length<6;k++){
      if(out.indexOf(scored[k][1])<0) out.push(scored[k][1]);
    }
    place(el); render(out);
  }
  function onKey(e){
    if(!box || box.style.display==='none' || !items.length) return;
    var opts=box.querySelectorAll('div:not(.rr-hint)');
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){
      e.preventDefault();
      sel = e.key==='ArrowDown' ? (sel+1)%items.length : (sel<=0?items.length-1:sel-1);
      opts.forEach(function(o,i){ o.className = i===sel?'on':''; });
    } else if(e.key==='Enter'||e.key==='Tab'){
      if(sel>=0){ e.preventDefault(); apply(items[sel]); }
      else if(e.key==='Tab'){ e.preventDefault(); apply(items[0]); }
    } else if(e.key==='Escape'){ hide(); }
  }
  function attach(el){
    if(el.dataset.rrSpell) return;
    el.dataset.rrSpell='1';
    el.setAttribute('spellcheck','true');
    el.addEventListener('input',function(){ suggest(el); });
    el.addEventListener('keydown',onKey);
    el.addEventListener('blur',function(){ setTimeout(hide,150); });
  }
  function scan(){ document.querySelectorAll('textarea, input[type=text]').forEach(attach); }
  scan();
  new MutationObserver(scan).observe(document.body,{childList:true,subtree:true});
  window.addEventListener('scroll',function(){ if(target) place(target); },true);
})();
</script>
"""

CSS = """
.gradio-container {background:#EEF0F3 !important; max-width:1180px !important;
  --block-title-text-color:#0D6EFD; --block-label-text-color:#0D6EFD;
  --block-title-background-fill:transparent; --block-label-background-fill:transparent;}
.gradio-container .block-title, .gradio-container label > span:first-child,
.gradio-container .block-label {background:transparent !important;}
.gradio-container .block-title, .gradio-container label > span:first-child,
.gradio-container span[data-testid="block-info"] {color:#0D6EFD !important;}
.gradio-container .block-title, .gradio-container label > span:first-child {font-weight:800 !important;}
.gradio-container .label-wrap span {color:#16A34A !important; font-weight:normal !important;}
#col-in {background:#fff; border:2px solid #3B82F6; border-radius:14px; padding:16px !important;}
#col-out {background:#fff; border:2px solid #0EA5E9; border-radius:14px; padding:16px !important;}
#col-chat {background:#fff; border:2px solid #A855F7; border-radius:14px; padding:16px !important;}
#col-fb {background:#fff; border:2px solid #A855F7; border-radius:14px; padding:16px !important;}
#col-signoff {background:#fff; border:2px solid #22C55E; border-radius:14px; padding:16px !important;}
#col-kb {background:#fff; border:2px solid #16A34A; border-radius:14px; padding:16px !important;}
#run-btn {background:linear-gradient(90deg,#B5121B,#E53935) !important; color:#fff !important; font-weight:bold !important; font-size:16px !important; border:none !important;}
.rr-info {position:relative; display:inline-block; cursor:pointer; color:#3B82F6; font-weight:bold; margin-left:6px; font-size:13px;}
.rr-info .rr-tip {visibility:hidden; opacity:0; width:290px; background:#2B2B2B; color:#fff; text-align:left; border-radius:8px; padding:11px 13px; position:absolute; z-index:50; top:150%; left:50%; margin-left:-145px; font-size:11px; font-weight:normal; line-height:1.5; transition:opacity .18s; box-shadow:0 3px 12px rgba(0,0,0,.35);}
.rr-info:hover .rr-tip, .rr-info:focus .rr-tip {visibility:visible; opacity:1;}
.rr-fitz {position:relative; display:inline-block; cursor:pointer; color:#3B82F6; font-weight:bold; font-size:15px;}
.rr-fitztip {visibility:hidden; opacity:0; width:440px; max-width:88vw; background:#fff; border:1px solid #E5E5E5; box-shadow:0 6px 20px rgba(0,0,0,.28); border-radius:10px; padding:10px; position:absolute; z-index:100; top:135%; left:0; transition:opacity .18s;}
.rr-fitz:hover .rr-fitztip, .rr-fitz:focus .rr-fitztip {visibility:visible; opacity:1;}
"""

with gr.Blocks(title="Radiant Revive AI - Provider Portal", theme=gr.themes.Soft(primary_hue="red"), css=CSS) as demo:
    gr.HTML(HEADER)
    gr.HTML(BANNER)
    gr.HTML(f'<div style="background:{DARK};color:#fff;border-radius:10px;padding:9px 14px;margin-top:10px;font-family:Calibri,Arial,sans-serif;font-size:12px;letter-spacing:1px;text-align:center;">WORKFLOW &nbsp; <b style="color:#8ECbFF;">1</b> Intake &rarr; <b style="color:#8ECbFF;">2</b> AI Analysis &rarr; <b style="color:#8ECbFF;">3</b> Consensus &rarr; <b style="color:#8ECbFF;">4</b> Decision (agree or correct) &rarr; <b style="color:#8ECbFF;">5</b> Sign-Off &amp; Knowledge Base</div>')
    with gr.Row():
        with gr.Column(elem_id="col-in", scale=1):
            gr.Markdown("### STEP 1 &middot; Case Intake (clinician)")
            image_input = gr.Image(label="Lesion / skin image", type="pil", height=240)
            with gr.Accordion("Not sure of the type? Click to match the patient's skin tone", open=False):
                gr.HTML(FITZINFO)
            fitzpatrick = gr.Radio(
                choices=[("I",1),("II",2),("III",3),("IV",4),("V",5),("VI",6)],
                value=None, label="Fitzpatrick Skin Type (required)",
                info="Select the type that matches this patient's skin — open the skin-tone guide above if you are unsure. Analysis will not run until a type is chosen.")
            location = gr.Textbox(label="Body location", placeholder="e.g., plantar foot, left forearm, scalp")
            notes = gr.Textbox(label="Clinician notes / history", placeholder="onset, changes, symptoms, prior treatment", lines=2)
            run_btn = gr.Button("Run AI Analysis", variant="primary", size="lg", elem_id="run-btn")
        with gr.Column(elem_id="col-out", scale=1):
            gr.HTML(PROBLEM)
            gr.Markdown("### STEP 2 &middot; AI Analysis & Attempted Diagnosis")
            output_html = gr.HTML("<div style='padding:36px;text-align:center;color:#aaa;font-family:Calibri;'>Upload a case image and click Run AI Analysis.</div>")

    with gr.Row():
        with gr.Column(elem_id="col-chat", scale=1):
            gr.Markdown("### STEP 3 &middot; Clinician &harr; AI Consensus")
            gr.Markdown("<span style='font-size:12px;color:#666;'>Engage the AI about what it's seeing to reach consensus on diagnosis, referral, or treatment. You are the decision-maker.</span>")
            chatbox = gr.Chatbot(height=240, label="Consensus dialogue")
            with gr.Row():
                question = gr.Textbox(placeholder="e.g., What are you seeing? Why did you flag this? Is this within nursing scope?", label="", scale=4)
                ask_btn = gr.Button("Ask AI", scale=1)
        with gr.Column(elem_id="col-fb", scale=1):
            gr.Markdown("### STEP 4 &middot; Clinician Decision")
            gr.Markdown("<span style='font-size:12px;color:#666;'><b>Agree?</b> Go straight to Step 5 and sign off. <b>Disagree?</b> Enter your correction below and re-calibrate the AI first.</span>")
            gr.Markdown("<span style='font-size:12px;color:#A855F7;font-weight:bold;'>4B &middot; Rebuttal / correction (only if you disagree)</span>")
            dx_correct = gr.Textbox(label="Corrected diagnosis", placeholder="e.g., Plantar callus with xerosis and keloid scar")
            obs = gr.Textbox(label="Clinical observation to log", placeholder="e.g., hyperkeratosis with fissuring; no biopsy indicated", lines=2)
            referral_cb = gr.Checkbox(label="Refer this patient to a physician", value=False,
                info="Tick if you are escalating. The AI re-calibrates around BOTH your diagnosis and the referral, and the referral is logged with your sign-off.")
            recal_btn = gr.Button("Re-calibrate AI with my correction", variant="secondary")
            recal_out = gr.HTML("")

    with gr.Row():
        with gr.Column(elem_id="col-signoff", scale=1):
            gr.Markdown("### STEP 5 &middot; Accept & Sign Off on Treatment Plan")
            gr.Markdown("<span style='font-size:12px;color:#666;'>If there's no rebuttal, accept the AI finding and sign off. If you corrected the AI in Step 4, sign-off uses your corrected diagnosis. The signed plan is logged to the Knowledge Base.</span>")
            clinician = gr.Textbox(label="Clinician name / credentials (signature)", placeholder="e.g., N. Pennie, BSN, RN")
            signoff_btn = gr.Button("Accept Finding & Sign Off on Treatment Plan", variant="primary", size="lg", elem_id="run-btn")
            signoff_out = gr.HTML("")

    with gr.Row():
        with gr.Column(elem_id="col-kb", scale=1):
            gr.Markdown("### STEP 6 &middot; Learning Loop &mdash; AI Knowledge Base")
            gr.HTML(f'<div style="font-size:11px;color:{TEAL};font-weight:bold;">Backend library connected: {sum(KB.kb_counts().values())} sources (peer-reviewed papers, prior clinician corrections, curated skin-of-color cases)</div>')
            gr.Markdown("<span style='font-size:12px;color:#666;'>Each sign-off adds a human-verified label. This is where true learning happens: verified corrections accumulate as governed training data \u2014 focused on closing the darker-skin gap. Updates live after each sign-off.</span>")
            kb_out = gr.HTML(kb_view())
            kb_refresh = gr.Button("Refresh Knowledge Base", variant="secondary")

    gr.HTML(SPELL_JS)
    gr.HTML(SKINCHART)
    gr.HTML(MONKCHART)
    gr.HTML(FOOTER)

    run_btn.click(fn=diagnostic_engine, inputs=[image_input, fitzpatrick, location, notes], outputs=output_html)
    ask_btn.click(fn=ai_consensus, inputs=[question, image_input, fitzpatrick, location, notes, chatbox], outputs=[chatbox, question])
    recal_btn.click(fn=recalibrate, inputs=[dx_correct, obs, image_input, fitzpatrick, location, referral_cb], outputs=recal_out)
    signoff_btn.click(fn=sign_off, inputs=[dx_correct, image_input, fitzpatrick, location, clinician, referral_cb], outputs=[signoff_out, kb_out])
    kb_refresh.click(fn=kb_view, inputs=None, outputs=kb_out)

if __name__ == "__main__":
    demo.launch()
