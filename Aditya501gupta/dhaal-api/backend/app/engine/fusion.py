"""DHAAL fusion layer — combines the deterministic rules engine, the Forensic
Agent (live URL threat-intel), and the LLM into one calibrated verdict.

Design contract (this is the anti-'GPT-wrapper' architecture):
0. Forensic runs on every message. If an AUTHORITATIVE feed (Google Safe
   Browsing / URLhaus) confirms a link is malicious, that is decisive — the
   message is a SCAM even if its wording is bland. No model can out-vote a
   confirmed-malware URL.
1. Rules run ALWAYS — free, <1 ms, explainable, works offline.
2. Decisive rules SCAM (score >= FASTPATH_T) short-circuits: no LLM needed
   to know a digital-arrest script is a scam. LLM adds nothing but latency.
3. Ambiguous zone -> LLM reasons over India-specific context.
4. Disagreements are handled honestly:
   - one-step gap  -> higher severity wins, confidence damped
   - SAFE vs SCAM  -> verdict SUSPICIOUS + needs_review flag (never silently
     trust either model at the extremes)
5. LLM unavailable (no key / quota / outage) -> rules verdict, clearly tagged.
6. Offline forensic heuristics only ever ADVISE (they enrich the explanation);
   they never flip a verdict on their own, so they cannot create a false
   positive. Only a live feed can escalate. This is what keeps FPR at zero.
"""
from __future__ import annotations

import time

from . import llm as llm_mod
from .forensic import analyze as forensic_analyze
from .rules import analyze as rules_analyze

RANK = {"SAFE": 0, "SUSPICIOUS": 1, "SCAM": 2}
FASTPATH_T = 6.0
_VRANK = {"CLEAN": 0, "SUSPICIOUS": 1, "MALICIOUS": 2}


def _worst_url(forensic: dict) -> dict | None:
    details = forensic.get("details") or []
    if not details:
        return None
    return max(details, key=lambda d: (_VRANK.get(d["verdict"], 0), d["score"]))


def _enrich_with_forensic(out: dict, forensic: dict) -> None:
    """Attach forensic evidence WITHOUT changing the verdict. Offline heuristics
    advise caution; they never condemn on their own (FPR protection)."""
    if forensic.get("worst_verdict") == "SUSPICIOUS":
        w = _worst_url(forensic)
        if w and out.get("explanation"):
            reason = w["findings"][0]["detail"] if w["findings"] else "unverified link"
            out["explanation"] += f" Link note: {w['host']} looks risky — {reason}"
        out["needs_review"] = out.get("needs_review", False) or out["verdict"] != "SCAM"


def _forensic_scam(r: dict, forensic: dict, t0: float) -> dict:
    """A live feed confirmed a malicious link — decisive SCAM verdict."""
    w = _worst_url(forensic) or {}
    critical = next((f for f in w.get("findings", []) if f.get("severity") == "critical"), None)
    lead = critical["detail"] if critical else "A link in this message is a confirmed malicious URL."
    scam_type = r["scam_type"] if r["scam_type"] not in ("none", "unknown") else "phishing_link"
    out = dict(r)
    out.update({
        "verdict": "SCAM",
        "scam_type": scam_type,
        "confidence": max(round(r.get("confidence", 0.6), 2), 0.96),
        "needs_review": False,
        "forensic": forensic,
        "engine": "hybrid-v1 (forensic-confirmed link)",
        "explanation": f"{lead} Do not open it, pay, or share any OTP. "
                       f"Report at 1930 / cybercrime.gov.in. "
                       f"(Text signals: {out.get('explanation', '')})",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    })
    return out


def analyze_hybrid(text: str, llm_fn=None, allow_llm: bool = True, forensic_fn=None) -> dict:
    t0 = time.perf_counter()
    r = rules_analyze(text)
    r["needs_review"] = False

    # Forensic pass — offline heuristics always; live feeds only if keys are set.
    forensic = (forensic_fn or forensic_analyze)(text)
    r["forensic"] = forensic

    # 0) forensic decisive — an authoritative feed confirmed a malicious link
    if forensic.get("worst_verdict") == "MALICIOUS":
        return _forensic_scam(r, forensic, t0)

    # 1) decisive rules scam — fast path
    if r["score"] >= FASTPATH_T:
        r["engine"] = "hybrid-v1 (rules fast-path)"
        _enrich_with_forensic(r, forensic)
        r["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return r

    # 2) LLM pass
    fn = llm_fn or llm_mod.llm_classify
    l = fn(text) if (allow_llm and (llm_fn or llm_mod.available())) else None
    if l is None:
        r["engine"] = "rules-v0 (llm unavailable)"
        _enrich_with_forensic(r, forensic)
        r["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return r

    rv, lv = RANK[r["verdict"]], RANK[l["verdict"]]

    # 3) fuse
    if rv == lv:
        verdict = r["verdict"]
        confidence = min(0.99, max(r["confidence"], l["confidence"]) + 0.05)
        needs_review = False
    elif abs(rv - lv) == 1:
        verdict = r["verdict"] if rv > lv else l["verdict"]
        confidence = round(min(r["confidence"], l["confidence"]) * 0.9, 2)
        needs_review = confidence < 0.65
    else:  # SAFE vs SCAM — maximal disagreement
        verdict = "SUSPICIOUS"
        confidence = 0.55
        needs_review = True

    scam_type = r["scam_type"] if r["scam_type"] not in ("none", "unknown") else l["scam_type"]
    if verdict == "SAFE":
        scam_type = "none"

    llm_extra_tactics = [t for t in l.get("tactics", []) if t not in r["tactics"]]

    out = dict(r)
    out.update({
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "scam_type": scam_type,
        "needs_review": needs_review,
        "forensic": forensic,
        "llm": {
            "verdict": l["verdict"], "confidence": l["confidence"],
            "rationale": l.get("rationale", ""), "provider": l.get("provider", ""),
            "extra_tactics": llm_extra_tactics, "cached": l.get("cached", False),
        },
        "engine": "hybrid-v1",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    })
    if l.get("rationale") and verdict != "SAFE":
        out["explanation"] = f"{out['explanation']} AI analysis: {l['rationale']}"
    if needs_review:
        out["explanation"] += " (Models disagreed — flagged for human review. Verify via 1930 before acting.)"
    _enrich_with_forensic(out, forensic)
    return out
