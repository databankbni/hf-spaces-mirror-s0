"""DHAAL rules engine v0 — deterministic, explainable, dependency-free.

First pass of the hybrid verdict pipeline. Returns a full verdict dict with
matched tactic spans (for scam-anatomy highlighting), URL forensics, scam-type
guess, citations to official advisories, and latency. No network, no ML —
this exact module must keep working if every API on earth is down.
"""
from __future__ import annotations
import re
import time

# ---------------------------------------------------------------- tactics ---
# Each tactic: list of case-insensitive regex patterns (English / Hindi / Hinglish).
TACTIC_PATTERNS: dict[str, list[str]] = {
    "authority": [
        r"\b(cbi|police|customs?|rbi|trai|income tax|enforcement directorate|\bed\b|cyber ?crime|crime branch|narcotics|interpol|supreme court|high court)\b",
        r"\b(officer|inspector|sub-?inspector|constable|dcp|acp|ips|magistrate|jawan|army)\b",
        r"\bbank('s)? (fraud|security) (department|dept|team|officer|cell)\b",
        r"(पुलिस|सीबीआई|कस्टम|अदालत|वारंट|अधिकारी|आर्मी|सेना)",
    ],
    "ivr_robocall": [
        r"\bpress \d\b",
    ],
    "malware_bait": [
        r"\b\w+\.apk\b",
        r"\b(anydesk|teamviewer|quick ?support|screen ?shar(e|ing))\b",
        r"\b(download|install)\b.{0,40}\b(apk|remote (access|desktop))\b",
    ],
    "fear": [
        r"\b(arrest|warrant|seized?|illegal|drugs?|mdma|narcotic|money laundering|case (has been |is )?registered|fir\b|non-?bailable|jail|legal action|crim(e|inal)|blocked|suspend(ed)?|deactivat(ed?|ion)|disconnect(ed|ion)?|frozen|freeze|suspicious transaction|unauthori[sz]ed (transaction|access)|hacker)\b",
        r"\b(power (supply )?will be cut|electricity will be disconnected)\b",
        r"\b(band|kat) ho jayega\b|\bband ho (jayega|jaayega)\b",
        r"(गिरफ्तार|वारंट|ड्रग्स|केस|जेल|बंद हो जाएगा|कट जाएगा|खाता बंद)",
    ],
    "urgency": [
        r"\b(immediately|urgent(ly)?|right now|act (now|fast)|within \d+ (hours?|minutes?)|today|tonight|midnight|last (date|reminder|warning)|final (reminder|warning|notice)|expir(es?|ing)|asap|only \d+ (slots?|seats?) left)\b",
        r"\b(turant|abhi|jaldi|aaj (hi|raat)?)\b",
        r"(तुरंत|अभी|आज ही|आज रात|अंतिम)",
    ],
    "secrecy": [
        r"\b(do not (tell|share|inform|disclose|discuss)|don'?t tell|confidential|secret|between us|do not move|do not take (any )?other calls?)\b",
        r"\b(kisi ko mat batana|mat batana)\b",
        r"(किसी को मत बता|गोपनीय|मत बताइए)",
    ],
    "payment_pressure": [
        r"\b(transfer|pay(ment)? (now|immediately|here)?|deposit|processing (fee|tax)|verification fee|clearance fee|re-?delivery fee|refundable|fine|penalty|advance|token (amount|money)?|settle)\b",
        r"\b(upi|gpay|google pay|phonepe|paytm|neft|imps|rtgs)\b.{0,60}\b(send|pay|bhejo|transfer|approve|return)\b",
        r"\b(send|return|bhejo|transfer)\b.{0,60}\b(upi|gpay|google pay|phonepe|paytm)\b",
        r"\b(sandbox account|secret account|rbi account|safe(ty)? account|designated account)\b",
        r"\bcollect request\b",
        r"\b(jama kar|file (charge|fee)|gift ?cards?)\b",
        r"(भेजो|भुगतान|जुर्माना|फीस|जमा|शुल्क)",
    ],
    "credential_ask": [
        r"\b(share|tell|enter|update|verify|confirm|provide|batao|bataye).{0,40}\b(otp|pin|cvv|password|upi pin|aadhaar|pan|card number|debit card|credit card)\b",
        r"\b(otp|pin|cvv|password|card number)\b.{0,30}\b(share|tell|bata|verify|confirm)\b",
        r"\b(approve|enter|daal(o|iye)?).{0,40}\b(upi )?pin\b",
        r"\b(otp|aadhaar|pan)\b.{0,25}\bready\b|\bready rakh",
        r"(ओटीपी बताकर|ओटीपी बता)",
    ],
    "sympathy_bait": [
        r"\b(by mistake|galti se|sent .{0,20}(wrong|mistake))\b",
        r"\b(hospital|accident|emergency|surgery)\b.{0,60}\b(send|return|pay|help|urgent)",
        r"\b(please (sir|madam|return|help)|it is (an )?emergency)\b",
    ],
    "too_good": [
        r"\b(earn|kamao|profit|guaranteed|assured) .{0,40}\b(daily|per (day|review|task|hour)|monthly|returns?|income)\b",
        r"\b(guaranteed|assured|100%) (profit|returns?|allotment|gain)\b",
        r"\b(work from home|no investment|liking (youtube )?videos|rate .{0,20}(products|hotels)|simple tasks?|part ?time job)\b",
        r"\b(lottery|prize|jackpot|lucky draw|congratulations!? you (have )?(been selected|won|received))\b",
        r"\b(double (your )?money|(double|triple|[23]x) in \d+ (days?|weeks?|months?)|watch it (double|grow)|\d{1,3}% (monthly|weekly|listing) (returns?|gains?)|paisa double)\b",
        r"\b(lakh|crore|लाख)\b.{0,25}\b(ghar|milega|prize|inaam|lottery)\b",
    ],
    "link_bait": [
        r"\b(click|tap|visit|open|update|verify|complete|pay) .{0,30}(link|here|below|now)\b",
        r"\b(download|install) .{0,25}\bapp\b",
        r"(इस लिंक पर|लिंक पर क्लिक|ऐप डाउनलोड)",
    ],
    "video_call_coercion": [
        r"\b(video (call|camera)|skype|whatsapp video|whatsapp call).{0,60}(verification|arrest|court|statement|interrogation|turn on|join|aayiye|police)\b",
        r"\b(turn on your (video )?camera|stay on (this|the) call)\b",
        r"(वीडियो कॉल पर)",
    ],
}

TACTIC_WEIGHTS = {
    "authority": 1.6, "fear": 1.6, "urgency": 1.0, "secrecy": 2.2,
    "payment_pressure": 1.8, "credential_ask": 2.4, "too_good": 2.2,
    "link_bait": 1.0, "video_call_coercion": 2.2, "sympathy_bait": 1.6,
    "ivr_robocall": 1.2, "malware_bait": 2.6,
}

# Tactics that are dangerous even when they appear alone.
STRONG_ALONE = {"credential_ask", "too_good", "video_call_coercion", "malware_bait"}

# ------------------------------------------------------------- scam types ---
SCAM_TYPE_SIGNALS: dict[str, list[str]] = {
    "digital_arrest": [
        r"\b(digital arrest|video (call|camera).{0,40}(police|cbi|verification|arrest))\b",
        r"\b(cbi|police|customs|crime branch|narcotics|trai)\b",
        r"\b(parcel|courier|package)\b.{0,60}\b(seized|illegal|drugs?|intercepted|customs)\b",
        r"\b(arrest|warrant|money laundering|non-?bailable)\b",
        r"(गिरफ्तार|वारंट|पुलिस|सीबीआई)",
    ],
    "kyc_bank": [
        r"\b(kyc|re-?kyc|pan card|aadhaar)\b.{0,60}\b(update|suspend|block|expire|verify|band)\b",
        r"\b(account|khata|net ?banking|yono|paytm)\b.{0,50}\b(suspend(ed)?|blocked?|frozen|deactivat|band ho)\b",
        r"(केवाईसी|खाता.{0,20}बंद)",
    ],
    "parcel_courier": [
        r"\b(parcel|shipment|package|courier|awb|consignment)\b.{0,80}\b(held|pending|fee|customs|address|re-?delivery|return)\b",
        r"\b(india post|bluedart|blue dart|fedex|dtdc|delhivery)\b",
    ],
    "utility": [
        r"\b(electricity|power supply|bijli)\b.{0,60}\b(disconnect|cut|band)\b",
        r"\b(bses|adani electricity|tata ?power|discom)\b",
        r"(बिजली.{0,30}(कट|बंद))",
    ],
    "investment_task": [
        r"\b(earn|kamao|profit|returns?|trading|invest(ment)?)\b",
        r"\b(task|liking videos|rate products|telegram)\b",
        r"\b(withdraw|withdrawal)\b.{0,40}\b(fee|tax|pay)\b",
    ],
    "upi_request": [
        r"\b(collect request|upi request|approve.{0,30}(pin|request))\b",
        r"\b(sent|transferred).{0,30}by mistake\b",
        r"\b(refund|return).{0,30}(money|amount|upi)\b",
    ],
    "phishing_link": [
        r"\b(refund|cashback|installment|yojana|subsidy)\b.{0,60}\b(verify|claim|update|link)\b",
        r"\b(income tax|pm ?kisan|epfo|uidai)\b",
    ],
    "impersonation": [
        r"\b(nephew|relative|friend'?s number|new number|phone (is )?broken|hospital|accident)\b.{0,80}\b(send|transfer|pay|urgent)",
        r"\b(army|jawan|cisf|crpf)\b.{0,60}\b(selling|bike|car|canteen|advance|token)\b",
    ],
}

# ------------------------------------------------------- benign guardrails ---
# Signals of legitimate messages. Negative weight — the FPR defence.
BENIGN_GUARDS: list[tuple[str, str, float]] = [
    ("safety_warning", r"\b(do not share (this )?otp|never (calls?|asks?) (you )?(for|to share)|bank never)\b", -2.5),
    ("appointment_notice", r"\b((is|has been) scheduled|please be available|appointment (is )?confirmed)\b", -1.5),
    ("no_action_needed", r"\b(no action (is )?required|verified successfully|has been resolved|is confirmed)\b", -3.0),
    ("official_domain", r"\b(sbi\.co\.in|onlinesbi\.sbi|hdfcbank\.com|icicibank\.com|amazon\.in|flipkart\.com|bsesdelhi\.com|tatapower\.com|irctc\.co\.in|myvi\.in|jio\.com|airtel\.in|bluedart\.com)\b|\.gov\.in\b|\.nic\.in\b", -2.5),
    ("otp_with_delivery_agent", r"\botp\b.{0,20}\bwith (the )?(delivery|pickup) (partner|boy|agent|executive|person)\b", -2.0),
    ("standard_alert", r"\b(avl bal|available balance|a/c xx\d+|debited from|credited to)\b", -1.5),
    ("official_helpline", r"\b(1800[ -]?\d{3,4}[ -]?\d{3,4}|19123|1930)\b", -1.0),
    ("otp_delivery", r"\b(otp for delivery|delivery otp)\b", -1.5),
]

# --------------------------------------------------------------- URL rules ---
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9\-\.]*\.[a-z]{2,})(/[^\s]*)?", re.I)
OFFICIAL_DOMAINS = {
    "sbi.co.in", "onlinesbi.sbi", "hdfcbank.com", "icicibank.com", "axisbank.com",
    "amazon.in", "flipkart.com", "bsesdelhi.com", "tatapower.com", "adanielectricity.com",
    "irctc.co.in", "indiapost.gov.in", "incometax.gov.in", "uidai.gov.in", "epfindia.gov.in",
    "pmkisan.gov.in", "cybercrime.gov.in", "sancharsaathi.gov.in", "myvi.in", "jio.com", "airtel.in",
    "fedex.com", "bluedart.com", "t.me",
}
BRAND_WORDS = [
    "sbi", "yono", "hdfc", "icici", "axis", "paytm", "phonepe", "gpay", "bses", "adani", "tata",
    "tatapower", "indiapost", "bluedart", "fedex", "amazon", "flipkart", "incometax", "pmkisan",
    "irctc", "epfo", "uidai", "kyc",
]
RISKY_TLDS = {".xyz", ".top", ".online", ".site", ".live", ".click", ".link", ".icu", ".buzz", ".rest", ".net"}
SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "t.co", "is.gd", "rb.gy"}

ADVISORY_CITATIONS = {
    "digital_arrest": [
        {"source": "I4C / MHA public advisory", "point": "There is no provision for 'digital arrest' in Indian law. Police/CBI/ED never conduct arrests or interrogations over video calls, and never demand money to cancel a warrant.", "ref": "https://cybercrime.gov.in"},
        {"source": "PIB Fact Check", "point": "TRAI does not call users about disconnecting mobile numbers; such calls are fraudulent.", "ref": "https://pib.gov.in"},
    ],
    "kyc_bank": [
        {"source": "RBI public awareness", "point": "Banks never ask for OTP, PIN, CVV or passwords, and never send KYC links by SMS. KYC updates happen via official app/branch.", "ref": "https://rbi.org.in"},
    ],
    "parcel_courier": [
        {"source": "India Post / PIB advisory", "point": "India Post does not request fees or address confirmation via SMS links.", "ref": "https://pib.gov.in"},
    ],
    "utility": [
        {"source": "Discom advisories (BSES/Tata Power)", "point": "Electricity boards send bills from registered DLT headers with official payment domains; disconnection never happens via personal-number SMS the same night.", "ref": "https://scantotal.net/blog/electricity-disconnect-scam-india/"},
    ],
    "investment_task": [
        {"source": "SEBI investor alerts", "point": "Guaranteed-return schemes and pay-to-withdraw 'profits' are hallmark frauds; SEBI-registered entities never guarantee returns.", "ref": "https://sebi.gov.in"},
    ],
    "upi_request": [
        {"source": "NPCI / RBI awareness", "point": "You never need to enter your UPI PIN or approve a request to RECEIVE money.", "ref": "https://npci.org.in"},
    ],
    "phishing_link": [
        {"source": "CERT-In advisories", "point": "Government refunds/subsidies are never disbursed via SMS links asking for bank details.", "ref": "https://cert-in.org.in"},
    ],
    "impersonation": [
        {"source": "State police advisories", "point": "Relative-in-distress and 'army buyer/seller' scripts are documented frauds; always verify by calling the known number.", "ref": "https://cybercrime.gov.in"},
    ],
}

# ---------------------------------------------------------------- scoring ---
SCAM_T, SUSP_T = 4.0, 2.0


def _find_spans(text: str, patterns: list[str]) -> list[dict]:
    spans = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            frag = m.group(0).strip()
            if frag and len(frag) > 1:
                spans.append({"text": frag, "start": m.start(), "end": m.end()})
    # dedupe overlapping
    spans.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    out, last_end = [], -1
    for s in spans:
        if s["start"] >= last_end:
            out.append(s)
            last_end = s["end"]
    return out


def analyze_urls(text: str) -> list[dict]:
    results = []
    for m in URL_RE.finditer(text):
        domain = m.group(1).lower()
        if "@" in m.group(0) or "." not in domain:
            continue
        reasons, risk = [], 0.0
        root = ".".join(domain.split(".")[-2:])
        if domain.endswith(".gov.in") or domain.endswith(".nic.in"):
            results.append({"url": m.group(0), "domain": domain, "risk": 0.0, "reasons": ["official government domain"]})
            continue
        if domain in OFFICIAL_DOMAINS or root in OFFICIAL_DOMAINS:
            results.append({"url": m.group(0), "domain": domain, "risk": 0.0, "reasons": ["official domain"]})
            continue
        if domain in SHORTENERS:
            risk += 1.0; reasons.append("link shortener hides destination")
        for tld in RISKY_TLDS:
            if domain.endswith(tld):
                risk += 1.2; reasons.append(f"risky TLD {tld}")
                break
        for b in BRAND_WORDS:
            if b in domain.replace("-", "").replace(".", " ").split() or b in domain.replace("-", ""):
                risk += 1.8; reasons.append(f"impersonates brand '{b}' on unofficial domain")
                break
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain):
            risk += 2.0; reasons.append("raw IP address")
        if risk == 0:
            reasons.append("unknown domain")
            risk = 0.4
        results.append({"url": m.group(0), "domain": domain, "risk": round(risk, 2), "reasons": reasons})
    return results


def analyze(text: str) -> dict:
    t0 = time.perf_counter()
    tactics = {}
    score = 0.0
    for tactic, pats in TACTIC_PATTERNS.items():
        spans = _find_spans(text, pats)
        if spans:
            tactics[tactic] = spans
            score += TACTIC_WEIGHTS[tactic] * min(len(spans), 2) ** 0.5

    guards = []
    for name, pat, w in BENIGN_GUARDS:
        if re.search(pat, text, re.I):
            guards.append(name)
            score += w

    # A safety warning ("do not share OTP") or a delivery-OTP flow is
    # education/normal commerce, not a credential ask — suppress the
    # credential_ask tactic those messages inevitably pattern-match.
    if ("safety_warning" in guards or "otp_with_delivery_agent" in guards or "otp_delivery" in guards) and "credential_ask" in tactics:
        score -= TACTIC_WEIGHTS["credential_ask"] * min(len(tactics["credential_ask"]), 2) ** 0.5
        del tactics["credential_ask"]

    urls = analyze_urls(text)
    url_risk = sum(u["risk"] for u in urls)
    score += min(url_risk, 3.0)

    type_scores = {}
    for stype, pats in SCAM_TYPE_SIGNALS.items():
        s = sum(1 for p in pats if re.search(p, text, re.I))
        if s:
            type_scores[stype] = s
    scam_type = max(type_scores, key=type_scores.get) if type_scores else "unknown"

    # multi-tactic bonus: 3+ manipulation levers together is the scam signature
    if len(tactics) >= 3:
        score += 1.2
    if len(tactics) >= 5:
        score += 1.0

    # Scams are COMBINATIONS of manipulation levers. A single weak signal
    # (authority alone, urgency alone...) with no risky URL is normal life,
    # not a scam — the structural false-positive defence.
    weak_single = (
        len(tactics) == 1
        and next(iter(tactics)) not in STRONG_ALONE
        and url_risk < 1.0
    )

    if weak_single:
        verdict = "SAFE"
    elif score >= SCAM_T:
        verdict = "SCAM"
    elif score >= SUSP_T:
        verdict = "SUSPICIOUS"
    else:
        verdict = "SAFE"

    confidence = max(0.5, min(0.99, 0.5 + abs(score - SUSP_T) / 10)) if verdict != "SCAM" else max(0.6, min(0.99, 0.55 + score / 14))
    citations = ADVISORY_CITATIONS.get(scam_type, []) if verdict != "SAFE" else []

    explanation = _explain(verdict, tactics, urls, scam_type, guards)
    return {
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "score": round(score, 2),
        "scam_type": scam_type if verdict != "SAFE" else "none",
        "tactics": tactics,
        "urls": urls,
        "benign_guards": guards,
        "citations": citations,
        "explanation": explanation,
        "engine": "rules-v0",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def _explain(verdict, tactics, urls, scam_type, guards) -> str:
    if verdict == "SAFE":
        base = "No scam pattern detected."
        if guards:
            base += " Message carries legitimate-communication signals (" + ", ".join(guards) + ")."
        return base + " Stay alert: verify sender identity for any money or OTP request."
    lever_names = {
        "authority": "claims of authority", "fear": "fear/threat pressure", "urgency": "artificial urgency",
        "secrecy": "isolation & secrecy demands", "payment_pressure": "payment pressure",
        "credential_ask": "OTP/credential harvesting", "too_good": "too-good-to-be-true offer",
        "link_bait": "link/download bait", "video_call_coercion": "video-call coercion",
        "sympathy_bait": "sympathy/emergency manipulation",
        "ivr_robocall": "robocall menu pressure", "malware_bait": "malware/remote-access bait",
    }
    levers = [lever_names[k] for k in tactics]
    msg = f"This matches the pattern of a {scam_type.replace('_', ' ')} scam. Manipulation levers detected: {', '.join(levers)}."
    bad_urls = [u for u in urls if u["risk"] >= 1]
    if bad_urls:
        msg += f" Suspicious link: {bad_urls[0]['domain']} ({bad_urls[0]['reasons'][0]})."
    if verdict == "SCAM":
        msg += " Do not pay, share OTP, or stay on the call. Report at 1930 / cybercrime.gov.in."
    else:
        msg += " Treat with caution and verify through official channels before acting."
    return msg


if __name__ == "__main__":
    import json, sys
    demo = sys.argv[1] if len(sys.argv) > 1 else "This is FedEx, your parcel with drugs was seized. CBI will arrest you today. Transfer Rs 50,000 now and do not tell anyone."
    print(json.dumps(analyze(demo), indent=2, ensure_ascii=False))
