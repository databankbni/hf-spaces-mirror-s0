"""
Radiant Revive — Knowledge Library retrieval for the Provider Portal demo.
Mirrors the production cPanel endpoints:
  match-research-library.php  -> papers   (+5 tag, +4 fitzpatrick, +3 topic/finding, +priority bonus)
  match-cases.php             -> case memory (+5 body_region, +5 distribution, +3 tag, +2 high severity)
Grounds AI reasoning in published literature and in prior clinician corrections.
"""
import os, json, re

_HERE = os.path.dirname(os.path.abspath(__file__))
_KB = {"papers": [], "reference_conditions": [], "library_docs": []}
try:
    with open(os.path.join(_HERE, "knowledge_library.json"), encoding="utf-8") as f:
        _KB = json.load(f)
except Exception:
    pass

def kb_counts():
    return {k: len(v) for k, v in _KB.items() if isinstance(v, list)}

def _low(x):
    if isinstance(x, list): return [str(i).lower() for i in x]
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):        # tags stored as stringified list
            try: return [str(i).lower() for i in json.loads(s.replace("'", '"'))]
            except Exception: pass
        return [s.lower()]
    return []

ROMAN = {1:"i",2:"ii",3:"iii",4:"iv",5:"v",6:"vi"}

# ---------------- palmoplantar / systemic safety rule (from clinician case memory) -------------
def distribution_flags(location, notes):
    """Detect bilateral palmoplantar involvement — the tell that collapses an occupational story."""
    t = f"{location or ''} {notes or ''}".lower()
    foot = any(k in t for k in ["plantar","sole","soles","foot","feet","heel","toe"])
    hand = any(k in t for k in ["palm","palms","palmar","hand","hands","finger","thumb","digit"])
    palmoplantar = ("palmoplantar" in t) or (foot and hand)
    return {"foot": foot, "hand": hand, "palmoplantar": palmoplantar}

# Established clinical decision rules (textbook dermatology knowledge — contains no patient data).
CLINICAL_RULES = {
    "palmoplantar": {
        "condition": "Secondary syphilis",
        "pearl": ("Bilateral palmoplantar involvement is a classic presentation of secondary syphilis. "
                  "Pressure or friction cannot explain palmar lesions, so a purely occupational or "
                  "mechanical explanation does not account for hands and feet together."),
        "workup": ["RPR (rapid plasma reagin) serology",
                   "VDRL (Venereal Disease Research Laboratory) test",
                   "FTA-ABS confirmatory testing if RPR is reactive",
                   "Physician referral for treatment if serology is positive"],
        "urgency": "Urgent — untreated infection carries risk of late systemic complications.",
        "basis": "Standard dermatology reference knowledge.",
    }
}

def systemic_alert(location, notes):
    """Distribution-driven systemic screen. Uses published clinical rules only."""
    f = distribution_flags(location, notes)
    if not f["palmoplantar"]:
        return None
    r = CLINICAL_RULES["palmoplantar"]
    return {"pearl": r["pearl"], "correct_dx": r["condition"], "workup": r["workup"],
            "urgency": r["urgency"], "basis": r["basis"]}

# ---------------- retrieval ----------------
def match_papers(tags=None, fitzpatrick=None, topics=None, findings=None, limit=3):
    tags = _low(tags or []); topics = _low(topics or []); findings = _low(findings or [])
    fp = (fitzpatrick or "").lower()
    scored = []
    for p in _KB.get("papers", []):
        score, why = 0, []
        ptags = _low(p.get("tags", []))
        for t in tags:
            if t in ptags: score += 5; why.append("tag:" + t)
        aw = p.get("applies_when", {}) or {}
        if isinstance(aw, str):
            try: aw = json.loads(aw.replace("'", '"'))
            except Exception: aw = {}
        if fp and fp in _low(aw.get("fitzpatrick_any_of", [])):
            score += 4; why.append("fitzpatrick:" + fp)
        for coll, keys, pts, lbl in ((topics, "any_topic", 3, "topic"), (findings, "any_finding", 3, "finding")):
            pv = _low(aw.get(keys, []))
            hit = False
            for q in coll:
                for v in pv:
                    if q and (q in v or v in q): score += pts; why.append(f"{lbl}:{q}"); hit = True; break
                if hit: break
        try: score += int(p.get("priority_score_bonus", 0) or 0)
        except Exception: pass
        if score > 0: scored.append({"item": p, "score": score, "why": why})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]

def match_case_memory(location=None, notes=None, tags=None, limit=2):
    """Retired: the demo library holds no patient records."""
    return []

def match_library(dx_terms=None, fitzpatrick=None, location=None, limit=3):
    """Match curated SOC cases + docs (treatment ladders, FDA safety alerts)."""
    terms = _low(dx_terms or []); fp = (fitzpatrick or "").lower(); loc = (location or "").lower()
    scored = []
    for c in _KB.get("reference_conditions", []):
        score, why = 0, []
        blob = " ".join([str(c.get("diagnosis","")), str(c.get("context","")), " ".join(_low(c.get("tags",[])))]).lower()
        for q in terms:
            if q and q in blob: score += 5; why.append("dx:" + q)
        if fp and str(c.get("fitz","")).lower() == fp: score += 4; why.append("fitzpatrick:" + fp)
        if loc and any(w in str(c.get("location","")).lower() for w in loc.split() if len(w) > 3):
            score += 3; why.append("location")
        if score > 0: scored.append({"item": c, "kind": "case", "score": score, "why": why})
    for d in _KB.get("library_docs", []):
        score, why = 0, []
        blob = " ".join([str(d.get("title","")), str(d.get("summary","")), " ".join(_low(d.get("tags",[])))]).lower()
        for q in terms:
            if q and q in blob: score += 4; why.append("dx:" + q)
        if "safety alert" in blob or "recall" in blob: score += 2; why.append("safety")
        if score > 0: scored.append({"item": d, "kind": "doc", "score": score, "why": why})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]

# ---------------- clinical spell-check / autocorrect ----------------
_CORRECTIONS = {
 "melanona":"melanoma","melanomia":"melanoma","melenoma":"melanoma","psorisis":"psoriasis",
 "psoriasus":"psoriasis","eczama":"eczema","eczama.":"eczema","excema":"eczema","exzema":"eczema",
 "sebborheic":"seborrheic","seborrhic":"seborrheic","sebhorreic":"seborrheic","keloyd":"keloid",
 "keloids":"keloids","cellulits":"cellulitis","celulitis":"cellulitis","dermatits":"dermatitis",
 "dermitis":"dermatitis","hyperpigmantation":"hyperpigmentation","hyperpigmenation":"hyperpigmentation",
 "hypopigmentaion":"hypopigmentation","verucca":"verruca","verruca.":"verruca","warts":"warts",
 "tinia":"tinea","tenia":"tinea","hyperkeratosis.":"hyperkeratosis","hyperkaratosis":"hyperkeratosis",
 "hyperkeratotic.":"hyperkeratotic","xerosis.":"xerosis","zerosis":"xerosis","callous":"callus",
 "callouses":"calluses","fissue":"fissure","fissurs":"fissures","alopecia.":"alopecia","alopecha":"alopecia",
 "acanthosis":"acanthosis","nevis":"nevus","nevous":"nevus","biopsey":"biopsy","biospy":"biopsy",
 "dermascopy":"dermoscopy","dermatascopy":"dermoscopy","referal":"referral","refferal":"referral",
 "refered":"referred","reccomend":"recommend","recomend":"recommend","recomended":"recommended",
 "patinet":"patient","pateint":"patient","diagnosies":"diagnosis","diagnosos":"diagnosis",
 "diagnsis":"diagnosis","sypilis":"syphilis","syphillis":"syphilis","siphilis":"syphilis",
 "infalmmation":"inflammation","inflamation":"inflammation","erythmea":"erythema","erythmia":"erythema",
 "pruritis":"pruritus","lesionn":"lesion","lesons":"lesions","folliculits":"folliculitis",
 "vitilago":"vitiligo","vitaligo":"vitiligo","rosecea":"rosacea","rosacia":"rosacea",
}

def autocorrect(text):
    """Return (corrected_text, [(before, after), ...]) — transparent, never silent."""
    if not text or not text.strip():
        return text, []
    changes = []
    def fix(m):
        w = m.group(0); low = w.lower()
        rep = _CORRECTIONS.get(low)
        if not rep or rep == low: return w
        out = rep.capitalize() if w[:1].isupper() else rep
        changes.append((w, out)); return out
    corrected = re.sub(r"[A-Za-z]+", fix, text)
    return corrected, changes


# ---------------- clinical vocabulary for live spelling suggestions ----------------
_CURATED = [
 "syphilis","secondary syphilis","treponema pallidum","RPR","VDRL","FTA-ABS",
 "hyperkeratosis","hyperkeratotic","keratoderma","palmoplantar keratoderma","tyloma","callus","calluses","heloma","corn",
 "melanoma","acral lentiginous melanoma","basal cell carcinoma","squamous cell carcinoma","actinic keratosis",
 "seborrheic keratosis","dysplastic nevus","melanocytic nevus","nevus","dermatofibroma","dermoscopy","biopsy",
 "psoriasis","eczema","atopic dermatitis","contact dermatitis","seborrheic dermatitis","stasis dermatitis",
 "lichen planus","lichen simplex chronicus","prurigo nodularis","urticaria","granuloma annulare",
 "tinea pedis","tinea corporis","tinea capitis","tinea versicolor","onychomycosis","candidiasis",
 "verruca","plantar verruca","condyloma","molluscum contagiosum","herpes zoster","herpes simplex",
 "cellulitis","impetigo","folliculitis","furuncle","abscess","scabies","pediculosis",
 "keloid","hypertrophic scar","post-inflammatory hyperpigmentation","postinflammatory hyperpigmentation",
 "hyperpigmentation","hypopigmentation","melasma","vitiligo","acanthosis nigricans","dermatosis papulosa nigra",
 "alopecia areata","central centrifugal cicatricial alopecia","traction alopecia","androgenetic alopecia",
 "pseudofolliculitis barbae","acne vulgaris","acne keloidalis nuchae","rosacea","hidradenitis suppurativa",
 "xerosis","ichthyosis","fissure","fissuring","desquamation","lichenification","excoriation","erosion","ulceration",
 "erythema","erythematous","edema","induration","macule","papule","plaque","nodule","vesicle","bulla","pustule",
 "pruritus","pruritic","scaling","crusting","atrophy","telangiectasia","petechiae","purpura",
 "sarcoidosis","lupus","discoid lupus","morphea","scleroderma","dermatomyositis","vasculitis",
 "pityriasis rosea","pityriasis versicolor","erythema multiforme","Stevens-Johnson syndrome","drug eruption",
 "diabetes","peripheral neuropathy","peripheral vascular disease","venous insufficiency","lymphedema",
 "Fitzpatrick","Monk skin tone","referral","referred","dermatology","physician","serology","culture","KOH prep",
 "emollient","keratolytic","urea","salicylic acid","hydroquinone","tretinoin","azelaic acid","corticosteroid",
 "triamcinolone","clobetasol","antifungal","terbinafine","ketoconazole","mupirocin","doxycycline","benzoyl peroxide",
 "silicone gel","intralesional","cryotherapy","debridement","offloading","sunscreen","photoprotection",
]

def vocabulary():
    """Clinical terms offered as live spelling suggestions (library-derived + curated)."""
    vocab = set()
    for t in _CURATED:
        vocab.add(t)
    for c in _KB.get("reference_conditions", []):
        d = str(c.get("diagnosis", "")).strip()
        if d:
            vocab.add(re.split(r"[—\-(]", d)[0].strip()[:60])
        for tg in _low(c.get("tags", [])):
            if 3 < len(tg) < 40: vocab.add(tg)
    for p in _KB.get("papers", []):
        for tg in _low(p.get("tags", [])):
            if 3 < len(tg) < 40: vocab.add(tg)
    for doc in _KB.get("library_docs", []):
        for tg in _low(doc.get("tags", [])):
            if 3 < len(tg) < 40: vocab.add(tg)
    for w in _CORRECTIONS.values():
        vocab.add(w)
    def ok(s):
        s = s.strip()
        if not (3 < len(s) <= 45): return False
        if any(ch.isdigit() for ch in s): return False          # drop stats like "12.1% vs 7.6%"
        if any(ch in s for ch in "'\"%()[]{}<>/|"): return False # drop quoted/odd fragments
        if not s[0].isalpha(): return False
        letters = sum(ch.isalpha() for ch in s)
        return letters >= max(4, int(len(s) * 0.7))              # mostly letters
    out = sorted({v.strip() for v in vocab if ok(v)}, key=lambda s: s.lower())
    return out


# ---------------- acral / subungual melanoma safety rules (published clinical knowledge) ----------------
NAIL_KEYS = ["nail", "subungual", "nailbed", "nail bed", "toenail", "fingernail", "melanonychia", "cuticle"]

def nail_involved(location, notes):
    t = f"{location or ''} {notes or ''}".lower()
    return any(k in t for k in NAIL_KEYS)

ACRAL_CANCER_RULE = {
    "condition": "Acral lentiginous melanoma (ALM)",
    "why": ("Acral lentiginous melanoma is the most common melanoma subtype in Black and Asian patients and arises on "
            "palms, soles and nail units — surfaces that are not sun-exposed. It is not explained by UV, and the ABCDE "
            "criteria developed for superficial spreading melanoma perform poorly on it. A diffuse pressure callus and a "
            "discrete pigmented acral lesion can occupy the same surface and must not be conflated."),
    "discriminators": [
        "Is there a DISCRETE pigmented lesion, as opposed to diffuse pressure-related thickening?",
        "Is the pigment asymmetric, irregularly bordered, or variegated in colour?",
        "Has it changed, enlarged, ulcerated, bled, or failed to heal?",
        "Is it solitary and in a non-pressure-bearing area (arch, instep, interdigital)?",
        "Is there any amelanotic (pink/flesh-coloured) nodule that behaves like a non-healing wound?",
    ],
    "action": "Any 'yes' → refer to dermatology for dermoscopy and biopsy. Do not treat as callus.",
}

NAIL_CANCER_RULE = {
    "condition": "Subungual melanoma",
    "why": ("Longitudinal melanonychia in a single digit is the classic presentation of subungual melanoma. Benign "
            "melanonychia is more often multiple, symmetric and stable; a solitary, widening or irregular band is the "
            "one that must be excluded."),
    "abcdef": [
        "A — Age (peak 5th-7th decade) and African/Asian/Native American ancestry",
        "B — Band: brown-black, breadth >=3 mm, irregular or blurred borders",
        "C — Change: rapid increase in size or a band that fails to improve despite adequate treatment",
        "D — Digit involved: thumb > hallux > index finger; single digit more concerning than multiple",
        "E — Extension of pigment onto the proximal or lateral nail fold (Hutchinson's sign)",
        "F — Family or personal history of melanoma or dysplastic naevus",
    ],
    "action": "Solitary band with any ABCDEF feature → dermatology referral for nail-unit biopsy.",
}

def acral_cancer_check(location, notes):
    """Return the can't-miss acral cancer prompt for any acral site (palms, soles, nails)."""
    f = distribution_flags(location, notes)
    if not (f["foot"] or f["hand"] or nail_involved(location, notes)):
        return None
    out = {"rule": ACRAL_CANCER_RULE, "nail": None}
    if nail_involved(location, notes):
        out["nail"] = NAIL_CANCER_RULE
    return out


# ---------------- keloid-prone anatomy (published clinical knowledge) ----------------
# Keloids and hypertrophic scars cluster at high-tension sites: sternum/chest, shoulders,
# deltoid, earlobes, jawline, upper back and neck. They are RARE on palms and soles.
# Keloid formation is markedly more common in skin of color.
KELOID_SITES = ["chest", "sternum", "breastbone", "shoulder", "deltoid", "upper back",
                "back", "clavicle", "collarbone", "ear", "earlobe", "jaw", "jawline",
                "neck", "beard", "chin", "presternal"]

_KELOID_RE = re.compile(r"\b(" + "|".join([
    "chest", "sternum", "presternal", "breastbone", "shoulders?", "deltoid",
    "upper back", "back", "clavicle", "collarbone", "ears?", "earlobes?",
    "jaw", "jawline", "neck", "beard", "chin"]) + r")\b")

def keloid_prone(location, notes=""):
    """High-tension sites where keloids cluster. Word-boundary matched so
    'forearm' does not match 'ear'. Palms/soles are explicitly excluded."""
    t = f"{location or ''} {notes or ''}".lower()
    if any(k in t for k in ["palm", "sole", "plantar", "forearm"]):
        return False
    return bool(_KELOID_RE.search(t))
