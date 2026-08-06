"""
ClinSift DDI mechanism layer — TIER 1: CYP450 (pharmacokinetic interactions).

Closes the gap the structural SSI-DDI model is blind to: enzyme-mediated PK
interactions (one drug inhibits/induces a CYP enzyme that clears another).

This is a CURATED knowledge base of well-established CYP relationships (the kind
in the FDA "Substrates / Inhibitors / Inducers" table). It is NOT exhaustive —
production would ingest DrugBank / FDA / PharmGKB for full coverage. Every entry
here is a well-documented, textbook relationship.

Interaction logic:
  - A inhibits enzyme E, B is a substrate of E   -> B levels RISE  -> toxicity risk
  - A induces  enzyme E, B is a substrate of E   -> B levels FALL  -> loss of efficacy
  - B is a PRODRUG activated by E, A inhibits E   -> B loses efficacy (less activation)
Checked in BOTH directions (A->B and B->A).

Scope (honest): works by DRUG IDENTITY (a lookup). For a KNOWN drug or a known
co-medication panel it is reliable. For a truly NOVEL compound you must first
PREDICT its CYP profile (QSAR) — that is Tier 1b, noted as the extension.
"""

# role ∈ {substrate, prodrug (activated by E), inhibitor, strong_inhibitor, inducer}
# Only well-established relationships are encoded.
CYP_KB = {
    # --- inhibitors (raise levels of co-administered substrates) ---
    "amiodarone":   [("CYP2C9","strong_inhibitor"),("CYP3A4","inhibitor"),("CYP2D6","inhibitor")],
    "fluconazole":  [("CYP2C9","strong_inhibitor"),("CYP3A4","inhibitor"),("CYP2C19","inhibitor")],
    "ketoconazole": [("CYP3A4","strong_inhibitor")],
    "clarithromycin":[("CYP3A4","strong_inhibitor")],
    "erythromycin": [("CYP3A4","inhibitor")],
    "ritonavir":    [("CYP3A4","strong_inhibitor")],
    "diltiazem":    [("CYP3A4","inhibitor")],
    "verapamil":    [("CYP3A4","inhibitor")],
    "grapefruit":   [("CYP3A4","strong_inhibitor")],
    "fluoxetine":   [("CYP2D6","strong_inhibitor"),("CYP2C19","inhibitor")],
    "paroxetine":   [("CYP2D6","strong_inhibitor")],
    "bupropion":    [("CYP2D6","strong_inhibitor")],
    "quinidine":    [("CYP2D6","strong_inhibitor")],
    "fluvoxamine":  [("CYP1A2","strong_inhibitor"),("CYP2C19","inhibitor")],
    "ciprofloxacin":[("CYP1A2","strong_inhibitor")],
    "metronidazole":[("CYP2C9","inhibitor")],
    "omeprazole":   [("CYP2C19","inhibitor")],
    "cimetidine":   [("CYP2D6","inhibitor"),("CYP3A4","inhibitor")],
    # --- inducers (lower levels of substrates -> loss of efficacy) ---
    "rifampin":     [("CYP3A4","inducer"),("CYP2C9","inducer"),("CYP2C19","inducer")],
    "carbamazepine":[("CYP3A4","inducer")],
    "phenytoin":    [("CYP3A4","inducer"),("CYP2C9","substrate"),("CYP2C19","substrate")],
    "st john's wort":[("CYP3A4","inducer")],
    "rifabutin":    [("CYP3A4","inducer")],
    # --- substrates (their levels are affected by inhibitors/inducers) ---
    "warfarin":     [("CYP2C9","substrate"),("CYP3A4","substrate")],   # S-warfarin via 2C9 (active)
    "simvastatin":  [("CYP3A4","substrate")],
    "atorvastatin": [("CYP3A4","substrate")],
    "lovastatin":   [("CYP3A4","substrate")],
    "metoprolol":   [("CYP2D6","substrate")],
    "carvedilol":   [("CYP2D6","substrate")],
    "midazolam":    [("CYP3A4","substrate")],
    "tacrolimus":   [("CYP3A4","substrate")],
    "cyclosporine": [("CYP3A4","substrate")],
    "sildenafil":   [("CYP3A4","substrate")],
    "glipizide":    [("CYP2C9","substrate")],
    "glyburide":    [("CYP2C9","substrate")],
    "glimepiride":  [("CYP2C9","substrate")],
    "losartan":     [("CYP2C9","substrate")],   # also a prodrug (2C9 activates) — nuance below
    "diazepam":     [("CYP2C19","substrate"),("CYP3A4","substrate")],
    "theophylline": [("CYP1A2","substrate")],
    "clozapine":    [("CYP1A2","substrate")],
    "olanzapine":   [("CYP1A2","substrate")],
    "tamoxifen":    [("CYP2D6","prodrug")],      # activated to endoxifen by 2D6
    "codeine":      [("CYP2D6","prodrug")],      # activated to morphine by 2D6
    "clopidogrel":  [("CYP2C19","prodrug")],     # activated by 2C19 (Plavix)
    "tramadol":     [("CYP2D6","prodrug")],
}
# aliases -> canonical
ALIAS = {"plavix":"clopidogrel","coumadin":"warfarin","lipitor":"atorvastatin",
         "zocor":"simvastatin","cipro":"ciprofloxacin","prozac":"fluoxetine",
         "seroquel":"quetiapine"}

STRONG = {"strong_inhibitor"}
def _norm(name): 
    n=name.lower().strip(); return ALIAS.get(n,n)

def _profile(drug):
    return CYP_KB.get(_norm(drug), [])

def _directional(a, b):
    """Effect of drug A on drug B via CYP. Returns list of mechanism dicts."""
    out=[]
    a_roles={e:r for e,r in _profile(a)}
    for enzyme, brole in _profile(b):
        arole=a_roles.get(enzyme)
        if arole is None: continue
        if arole in ("inhibitor","strong_inhibitor"):
            strong = arole in STRONG
            if brole=="substrate":
                out.append({"enzyme":enzyme,"mechanism":"CYP inhibition",
                    "effect":f"{a} inhibits {enzyme} → {b} levels rise → toxicity risk",
                    "severity":"high" if strong else "mod","direction":f"{a}⊣{enzyme}→↑{b}"})
            elif brole=="prodrug":
                out.append({"enzyme":enzyme,"mechanism":"CYP inhibition of prodrug activation",
                    "effect":f"{a} inhibits {enzyme} → {b} (prodrug) under-activated → loss of efficacy",
                    "severity":"high" if strong else "mod","direction":f"{a}⊣{enzyme}→↓active {b}"})
        elif arole=="inducer":
            if brole in ("substrate","prodrug"):
                out.append({"enzyme":enzyme,"mechanism":"CYP induction",
                    "effect":f"{a} induces {enzyme} → {b} cleared faster → loss of efficacy",
                    "severity":"mod","direction":f"{a}⇈{enzyme}→↓{b}"})
    return out

def cyp_interactions(drug_a, drug_b):
    """All CYP-mediated interactions between two drugs (both directions)."""
    hits = _directional(drug_a, drug_b) + _directional(drug_b, drug_a)
    # de-dup identical mechanisms
    seen=set(); uniq=[]
    for h in hits:
        k=(h["enzyme"],h["mechanism"],h["direction"])
        if k in seen: continue
        seen.add(k); uniq.append(h)
    return uniq

def known_to_cyp(drug):
    """Is this drug in the CYP knowledge base at all?"""
    return _norm(drug) in CYP_KB
