# Sunday Submission Checklist

_Updated: June 13, 2026_

Run the complete machine gate:

```bash
make sunday
```

The generated source of truth is `results/submission_preflight.json`.

## Machine-Verified

- [x] 48 teams and 72 group fixtures load.
- [x] Snapshot integrity and immutable forecast eligibility are tested.
- [x] One exact-kickoff live forecast is frozen with a verified SHA-256
  manifest before kickoff.
- [x] Dixon-Coles model passes the 2018-2026 walk-forward ship gate.
- [x] QLoRA decision is closed and reproducible: **NO-SHIP**.
- [x] Base model plus deterministic fallback is the selected runtime.
- [x] Round-of-32 matches 73-88 match the published schedule.
- [x] All 495 Annex C third-place combinations reproduce the official table.
- [x] Knockout progression through match 104 is fixed and tested.
- [x] Dataset audit reports zero normalized overlap across splits.
- [x] Code license is MIT; base model license is Apache-2.0.
- [x] Runtime model is 360M parameters, below the 32B limit.
- [x] GitHub source repository is public and anonymously reachable.
- [x] Space, source, adapter, dataset, field notes, and social draft URLs exist.

## Claim Boundary

- [x] Do not claim the QLoRA adapter improved the product.
- [x] Do not claim extraction benchmark accuracy; labels are synthetic and
  review-pending.
- [x] Forecasting evidence is the no-lookahead walk-forward backtest, not one
  correct or incorrect match.
- [x] Do not market the Space as betting advice or a guaranteed predictor.

## Human Actions Before Submission

- [x] Open a cold Space session and record the verification timestamp in
  `release/submission.json`.
- [x] Complete one mobile-width smoke test and record its timestamp.
- [ ] Record and publish the 60-90 second demo; add `demo_video_url`.
- [ ] Publish the public social post; add `social_post_url`.
- [ ] Submit on the hackathon platform; add `hackathon_submission_url`.
- [ ] Re-run `make release-preflight`; it must print `READY_TO_SUBMIT`.
- [ ] Record the final GitHub and Space revision in the submission form.
- [ ] Tag the accepted revision:

```bash
git tag hackathon-submission
git push origin hackathon-submission
```

## Published URLs

- Space: https://huggingface.co/spaces/sammoftah/World-Cup-2026-prediction
- Source: https://github.com/OsamaMoftah/World-Cup-2026-predicition
- Base model: https://huggingface.co/bartowski/SmolLM2-360M-Instruct-GGUF
- Evaluated adapter: https://huggingface.co/sammoftah/underdog-lab-smollm2-360m-lora
- Dataset: https://huggingface.co/datasets/sammoftah/underdog-lab-scenarios
