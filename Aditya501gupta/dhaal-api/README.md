---
title: DHAAL API
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Real-time AI shield against digital-arrest and UPI scams
---

# 🛡️ DHAAL — Digital Harm Analysis & Alert Layer

**Real-time AI shield against digital-arrest & UPI fraud — for every phone, every channel, in the two minutes the scam is actually happening.**

Built for **ET AI Hackathon 2.0** (Problem Statement 6 — AI for Digital Public Safety).

> **Judge quickstart (60 seconds):** open the live demo → paste any scam SMS from your own phone → watch the verdict, the highlighted manipulation tactics, and the official-advisory citation appear in under 3 seconds.

## Hub (single link to everything)

| Artifact | Link |
|---|---|
| Live citizen app | _(Vercel URL — day 1 of build)_ |
| Live API + dev demo | _(HF Space URL — day 1 of build)_ |
| 3-min demo video | _(day 15)_ |
| Presentation deck | _(day 14)_ |
| Benchmark report | [`eval/report_v0.md`](eval/report_v0.md) |
| Architecture diagram | `docs/architecture.png` |

## Current status — Day 3 (hybrid engine live, CI green)

- ✅ **Rules engine** (`backend/app/engine/rules.py`): dependency-free, explainable; detects 8 scam classes via manipulation-lever combinations (authority, fear, urgency, secrecy, payment pressure, credential harvesting, sympathy bait, video-call coercion, malware/remote-access bait) + URL forensics + benign guardrails.
- ✅ **LLM reasoning layer** (`backend/app/engine/llm.py`): Groq Llama-3.3-70B primary, Gemini Flash fallback, prompt-injection-hardened, schema-validated JSON, sqlite-cached. Degrades to rules if no key/quota/network.
- ✅ **Forensic Agent** (`backend/app/engine/forensic.py`): live URL threat-intel — Google Safe Browsing + URLhaus (abuse.ch), plus offline heuristics (look-alike brands, punycode/homograph, risky TLDs, IP-literal & `@`-trick hosts, credential-harvest paths, defanged links). **SSRF-safe** (never fetches the scammer's URL — only queries trusted databases about it) and **privacy-preserving** (query strings carrying victim PII are stripped before any lookup). A feed-confirmed malicious link is decisive; offline heuristics only advise, never falsely condemn.
- ✅ **Calibrated fusion** (`backend/app/engine/fusion.py`): rules + forensic + LLM combined with honest disagreement handling (max-disagreement → SUSPICIOUS + human-review flag).
- ✅ **IndiaScam-Bench** (`data/samples.jsonl`): 103 labelled samples (73 scam / 30 hard-negative benign, EN/HI/Hinglish) with per-sample source attribution.
- ✅ **Benchmark** (`eval/harness.py`), reproduced in CI on every push: hybrid engine scam recall **100%**, precision **100%**, benign FPR **0%** on the current corpus. _Honest caveat: the seed corpus is small and partly synthetic; it grows toward 600+ with a temporal hold-out split before any headline generalisation claim (Gate G4)._
- ✅ FastAPI service (`/analyze`, `/forensic`, `/health`) + dev demo UI + Dockerfile (HF Spaces-ready) + CI (`.github/workflows/bench.yml`) + keep-warm workflow.
- ⏭️ Next: deploy live (HF Space + Vercel), L2 campaign clustering, L3 command centre.

## Run locally

```bash
# Engine + benchmark: zero dependencies
python3 eval/harness.py
python3 backend/tests/test_rules.py

# API (needs: pip install -r backend/requirements.txt)
cd backend && uvicorn app.main:app --reload
# then open frontend/demo.html (it calls http://localhost:8000)
```

## Architecture (3 layers)

**L1 Citizen Shield** — paste/share/screenshot/audio → hybrid verdict (rules + **Forensic Agent live URL threat-intel** + Llama-3.3-70B on Groq + RAG over RBI/TRAI/I4C advisories) with scam-anatomy highlighting, 6+ languages, guided 1930/NCRP reporting. **Guardian Live Call mode**: on-device speech → red alert < 30 s.
**L2 Intelligence** — PII-redacted reports, HMAC-pseudonymised indicators, script-embedding clustering → fraud-campaign graph, early warning after ≤ 5 reports.
**L3 Command Centre** — geospatial hotspots, campaign explorer, SHA-256 hash-chained evidence dossiers with BSA s.63-style certificates.

## Security & privacy by design

DPDP-mapped consent; PII auto-redaction **before** storage; no raw scammer identifiers in the graph (HMAC only); prompt-injection-hardened LLM calls (content is data, never instructions); velocity limits + probing detection; secrets only in env vars.

**Forensic Agent hardening** — the URL layer treats a message's links as untrusted strings, never endpoints: it **never fetches or resolves** them (closing the SSRF hole a naive "open the link and inspect it" design would open), and hosts pointing at private/loopback/reserved ranges are flagged but never contacted. Before any URL reaches a third-party feed, its **query string and fragment are stripped**, so victim PII (phone numbers, OTPs, session tokens) never leaves the box. A misbehaving or offline feed degrades gracefully to offline heuristics — it can never crash a verdict.

## Data provenance & ethics

Corpus samples come from public official advisories (I4C, RBI, TRAI, PIB, SEBI), press-documented case scripts, and labelled synthetic multilingual variants. **No real victim PII anywhere.** Each sample carries its source. The full benchmark will be open-sourced at submission.

## Team

Team DHAAL — ET AI Hackathon 2.0, Phase 2. Working title pending final branding.

## License

MIT (code). Benchmark data: CC BY 4.0 with source attributions.
