# IndiaScam-Bench report — engine `hybrid`
_Generated 2026-07-05 04:08:43 · 103 samples (73 scam / 30 benign)_

| Metric | Value | Target |
|---|---|---|
| Scam recall | **100.0%** | >= 90% |
| Scam precision | **100.0%** | >= 95% |
| Benign false-positive rate | **0.0%** | < 2% |
| Accuracy | 100.0% | — |
| Latency p50 / max (ms) | 0.5 / 9.9 | p90 < 3000 |
| Samples that used the LLM | 0 | fast-path + fallback keep this low |

## Per-class recall

| Scam type | Samples | Recall |
|---|---|---|
| digital_arrest | 12 | 100% |
| impersonation | 8 | 100% |
| investment_task | 10 | 100% |
| kyc_bank | 10 | 100% |
| parcel_courier | 9 | 100% |
| phishing_link | 8 | 100% |
| upi_request | 8 | 100% |
| utility | 8 | 100% |

## Errors

None. All samples classified on the correct side.
