# IndiaScam-Bench — source log

Every sample in `samples.jsonl` carries a `source` field. Rules of the corpus:

1. **Public sources only** — official advisories (I4C, RBI, TRAI, PIB, SEBI, CERT-In), press coverage quoting scam scripts, documented awareness material.
2. **Zero victim PII** — no names, numbers, accounts of real victims; scammer-side artefacts anonymised to patterns.
3. **Synthetic is labelled** — constructed variants set `"synthetic": true` and name the documented pattern they model.
4. **Benign hard negatives** are constructed to mirror the exact formats scammers imitate (bank alerts, OTP messages, courier updates, genuine police communications) — these are the false-positive tests that matter.

## Verbatim-derived sources (v0)

| IDs | Source |
|---|---|
| da-001..004, da-007 | https://csnr.in/cyber-awareness-digital-arrest-scam-real-story-fedex-police/ (first-person documented digital-arrest script) |
| ut-001..003 | https://scantotal.net/blog/electricity-disconnect-scam-india/ (documented discom smishing texts) |

## Pattern references for constructed samples

- I4C / MHA digital-arrest advisories — https://cybercrime.gov.in
- PIB Fact Check (TRAI impersonation, India Post smishing, PM-Kisan phishing) — https://pib.gov.in
- RBI public awareness (KYC fraud, never-share-OTP) — https://rbi.org.in
- SEBI investor alerts (guaranteed returns, pay-to-withdraw) — https://sebi.gov.in
- NPCI UPI safety (collect-request fraud) — https://npci.org.in
- The420.in case reporting (BHEL digital-arrest case, 2026) — https://the420.in

## Growth plan

- Day 2: → 100 samples (all 8 classes ≥ 10)
- Day 4: → 300 (6 languages ≥ 30 each, LLM-augmented, labelled)
- Day 8: → 450 (+ call-transcript set from public news recordings)
- Day 13 (Gate G4): → 600+, temporal hold-out (last-collected 20% test-only), dual annotation on 100-sample subset with agreement stats. Headline metrics come ONLY from this frozen split.
