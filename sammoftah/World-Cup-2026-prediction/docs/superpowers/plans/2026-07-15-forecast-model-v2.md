# Forecast Model V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a better-calibrated World Cup match model without tuning on the same 2026 prospective results used to advertise its improvement.

**Architecture:** Preserve the shipped Elo + Dixon-Coles model as `v1` and build candidates behind a versioned forecasting interface. Select hyperparameters only with leave-one-tournament-out historical validation, treat the now-viewed 2026 group stage as a diagnostic audit rather than training data, and run the winner in shadow mode until it earns a fresh prospective promotion gate.

**Tech Stack:** Python 3.12, Pydantic 2, SciPy, pytest, JSON forecast artifacts, Gradio.

## Global Constraints

- Never refit a candidate on the 65 scored 2026 forecasts and then describe its 2026 replay as out-of-sample evidence.
- Primary metric is multiclass log loss; Brier, RPS, calibration error, accuracy, and outcome-conditional log loss are secondary diagnostics.
- Keep market-assisted forecasts separately labeled from independent-model forecasts.
- Promotion requires an immutable model version, data cutoff, feature hash, calibration parameters, and a fresh prospective confirmation window.
- Retain V1 predictions and reports unchanged.

## Observed V1 Diagnostic

- 65 verified 2026 group forecasts: 42 correct, 64.6% accuracy, log loss 0.914, and +16.8% skill versus equal odds.
- Long-range slice: 60 matches, 66.7% accuracy, log loss 0.879, and +20.0% skill.
- Actual outcomes were 46.2% home, 27.7% draw, and 26.2% away; mean forecasts were 46.1% home, 20.8% draw, and 33.1% away.
- V1 never made draw its top-probability outcome. Draw log loss was 1.742 versus 0.596 for non-draws.
- These numbers motivate draw and away calibration research; they do not authorize fitting directly to 2026.

---

### Task 1: Freeze the V1 diagnostic artifact

**Files:**
- Create: `results/wc2026_v1_prospective_scorecard.json`
- Modify: `scripts/track_record_summary.py`
- Test: `tests/unit/test_prediction_scorecard.py`

**Interfaces:**
- Produces: `build_track_record_report(repository) -> dict` and `--output PATH`.

- [ ] Add a failing test asserting the output records model version, artifact count, fixture coverage, score metrics, outcome frequencies, and a SHA-256 digest of the eligible manifests.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/unit/test_prediction_scorecard.py -q` and verify RED.
- [ ] Extract report construction from `main()`, add deterministic JSON output, and preserve stdout behavior.
- [ ] Run the focused test and verify GREEN.
- [ ] Generate and commit the immutable V1 diagnostic artifact.

### Task 2: Build a tournament-edition evaluation dataset

**Files:**
- Create: `src/underdog_lab/forecasting/tournament_dataset.py`
- Create: `scripts/build_tournament_evaluation.py`
- Create: `data/processed/world_cup_evaluation.jsonl`
- Test: `tests/unit/test_tournament_editions.py`

**Interfaces:**
- Produces: `TournamentMatch` rows with edition, stage, neutral flag, pre-match ratings, result, rest days, rating gap, and source cutoff.

- [ ] Write failing tests for edition separation, strictly pre-match features, group/knockout stage labels, and no 2026 rows in the selection pool.
- [ ] Verify RED.
- [ ] Build 2010, 2014, 2018, and 2022 rows from checked sources; use 2010-2018 for selection and 2022 as the untouched confirmation edition.
- [ ] Add leakage guards that reject a feature timestamp at or after kickoff.
- [ ] Verify GREEN and write a coverage report by edition and outcome.

### Task 3: Evaluate draw-aware calibration candidates

**Files:**
- Create: `src/underdog_lab/forecasting/draw_calibration.py`
- Create: `scripts/evaluate_draw_calibration.py`
- Create: `models/draw_calibration_evaluation.json`
- Test: `tests/unit/test_draw_calibration_v2.py`

**Interfaces:**
- Produces: `apply_draw_calibration(forecast, rating_gap, parameters) -> Forecast`.

- [ ] Write failing normalization and monotonicity tests: probabilities sum to one, remain in `[0,1]`, and a draw adjustment cannot reverse home/away ordering.
- [ ] Evaluate only three pre-registered candidates: global draw logit offset, rating-gap-dependent draw offset, and tournament-group-stage-specific Dixon-Coles `rho`.
- [ ] Select parameters with leave-one-edition-out validation on 2010-2018.
- [ ] Gate once on 2022 using paired bootstrap log-loss confidence intervals; reject if log loss improves but Brier, RPS, or calibration materially deteriorates.
- [ ] Report 2026 as a viewed diagnostic only, with no parameter changes after viewing it.

### Task 4: Evaluate stronger team-strength signals

**Files:**
- Create: `src/underdog_lab/forecasting/team_strength_v2.py`
- Create: `scripts/evaluate_strength_ensemble.py`
- Create: `models/strength_ensemble_evaluation.json`
- Test: `tests/unit/test_strength_ensemble_v2.py`

**Interfaces:**
- Produces: timestamped `TeamStrengthSnapshot` and a versioned log-opinion pool.

- [ ] Add pre-match FIFA ranking points and recent competitive-match form as timestamped inputs; exclude post-kickoff values and unlicensed player data.
- [ ] Compare Elo-only against FIFA-only and fixed candidate pool weights selected on 2010-2018.
- [ ] Confirm on 2022 and reject any ensemble whose paired log-loss interval crosses zero.
- [ ] Keep the simpler V1 strength signal if no candidate clears the gate.

### Task 5: Add market and naive baselines

**Files:**
- Modify: `scripts/market_blend_evaluation.py`
- Create: `results/wc2026_baseline_comparison.json`
- Test: `tests/unit/test_market_evaluation.py`

**Interfaces:**
- Produces: matched-horizon comparisons against equal odds, Elo-only, FIFA rank heuristic, and de-margined closing/opening market probabilities when licensed data exists.

- [ ] Require identical fixture sets and timestamps for every comparison.
- [ ] Report independent-model performance separately from any market blend.
- [ ] Refuse to calculate a market claim when odds provenance or capture time is missing.

### Task 6: Shadow deploy and promote only on fresh evidence

**Files:**
- Modify: `src/underdog_lab/world_cup/forecasting.py`
- Modify: `src/underdog_lab/world_cup/provenance.py`
- Modify: `src/underdog_lab/ui/app.py`
- Create: `models/v2_promotion_gate.json`
- Test: `tests/unit/test_prediction_eligibility.py`

**Interfaces:**
- Produces: `forecast_v1(...)`, `forecast_v2_shadow(...)`, and versioned immutable artifacts.

- [ ] Generate V1 and V2 side-by-side for future internationals without exposing V2 as the primary forecast.
- [ ] Accumulate at least 50 fresh, frozen, pre-kickoff matches or one pre-registered tournament edition.
- [ ] Promote only if V2 improves paired log loss with a bootstrap interval below zero, does not worsen Brier/RPS materially, and passes calibration and provenance gates.
- [ ] If the gate fails, publish the negative result and retain V1.
