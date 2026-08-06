# Runtime model

The application defaults to an automatic runtime that lazily downloads
`bartowski/SmolLM2-360M-Instruct-GGUF` and runs its Q8_0 quantization
through `llama-cpp-python` (see `src/underdog_lab/config.py`). A 360M
SmolLM2 QLoRA adapter was trained and benchmarked
(`results/ship_decision.json`) but did not clear the ship gate, so it is
not the default. If model loading fails, the challenge remains usable
through a deterministic fallback and records the degraded behavior.

For local llama.cpp inference:

```bash
export UNDERDOG_EXTRACTOR=llama_cpp
export UNDERDOG_LLAMA_CLI=/path/to/llama-cli
export UNDERDOG_MODEL_PATH=/path/to/model-q4_k_m.gguf
python app.py
```

The selected GGUF should be a compatible model at or below 4B parameters.
Test the exact conversion with the pinned llama.cpp revision before publishing
the Space.

To force the in-process runtime with a different model:

```bash
export UNDERDOG_EXTRACTOR=python_llama_cpp
export UNDERDOG_MODEL_REPO=bartowski/SmolLM2-360M-Instruct-GGUF
export UNDERDOG_MODEL_FILENAME=SmolLM2-360M-Instruct-Q8_0.gguf
python app.py
```

# World Cup 2026 forecasting model

`underdog_lab.world_cup.forecasting.MODEL` is a `DixonColesEloModel`
(Elo-to-goals Poisson rates with a Dixon-Coles low-score correlation term)
fit by `scripts/fit_elo_dixon_coles.py` via time-decayed maximum likelihood
on `data/historical/matches.csv` (11,094 real international matches,
2015-01-03 to 2026-06-12, sourced from eloratings.net).

- `elo_fit_report.json` — the final fit (trained on all data through the
  2026 World Cup `information_cutoff`, 180-day time-decay half-life):
  `intercept=0.1534`, `elo_scale=0.00207`, `home_advantage_elo=65.6`,
  `rho=-0.0998`. The negative `rho` reflects the well-documented excess of
  low-scoring draws (0-0, 1-1) versus independent Poisson.
  `home_advantage_elo` has no effect on World Cup group fixtures, which are
  always `neutral_venue=True`.
- `backtest_report.json` — a walk-forward backtest (`scripts/
  backtest_walk_forward.py`): for each test year 2018-2026, the model is
  refit on only the matches strictly before that year (no lookahead) and
  scored on that year's matches. The fitted model beats both the uniform
  baseline and the previous hand-set model (independent Poisson,
  `elo_scale=0.00165`, no home advantage, `rho=0`) on mean log loss, Brier
  score, and RPS across all folds. It also beats the previous model on the
  neutral-venue subset, which better matches World Cup inference, so the
  ship gate (`ship_gate.ship`) passed and `MODEL` was updated to these
  fitted parameters. A basic calibration table using the actual mean
  predicted probability in each decile is included. The model is
  under-confident through much of the middle range, so calibration remains
  an explicit follow-up rather than a completed claim.
- `upgrade_evaluation.json` (`scripts/upgrade_evaluation.py`) — two further
  changes evaluated with a selection (2018-2025) / confirmation (2026)
  split, so neither was chosen by peeking at the held-out year:
  - **Recency half-life (adopted).** The previous fit used a fixed 3-year
    (1095-day) half-life, never tuned. A sweep over {180, 365, 547, 730,
    1095, 1460, 2190} days found 180 days has the lowest mean log loss on
    the 2018-2025 selection folds (0.79417 vs 0.79454 for 1095 days), and
    it also beats the 1095-day fit on the held-out 2026 fold both overall
    (0.80110 vs 0.80406) and on the neutral-venue subset (0.80382 vs
    0.80464). All three checks passed, so `MODEL` and
    `fit_elo_dixon_coles.py`'s default half-life were updated from 1095 to
    180 days.
  - **Ensemble with a second, independently-computed Elo rating (not
    adopted).** `forecasting/self_elo.py` computes a from-scratch Elo
    rating (fixed K-factor, goal-difference multiplier, neutral start,
    derived only from `matches.csv` results — independent of
    eloratings.net). A Dixon-Coles model fit on this rating alone scores
    markedly worse than the eloratings-Elo model on the 2018-2025 selection
    folds, and every blend weight tested (a logarithmic opinion pool,
    `forecasting/ensemble.py`, weights 0.3-0.9 toward the eloratings model)
    scored worse than the eloratings-only model. The ensemble failed all
    three gate checks (selection, confirmation, confirmation-neutral) and
    `MODEL` remains a single eloratings-Elo fit. This is an honest negative
    result, not a placeholder: a from-scratch Elo computed over 11 years of
    data starting every team at a neutral 1500 is a weaker signal than
    eloratings.net's long-calibrated ratings, and blending in a weaker
    signal cannot improve a stronger one under a log-odds pool.

Tournament simulation now uses the official matches 73-104 path and the 495
third-place mappings from Annex C. It remains a single fitted statistical
model rather than an ensemble (the ensemble evaluation above did not clear
its gate); refit and re-run the walk-forward gate when new results are
incorporated.

- `recalibration_evaluation.json` (`scripts/recalibration_evaluation.py`,
  adopted) — a post-hoc temperature-scaling correction
  (`forecasting/calibration.py`) evaluated with the same selection
  (2018-2025) / confirmation (2026) split: out-of-fold forecasts from the
  walk-forward folds (180-day half-life, refit per fold, no lookahead) are
  pooled, a single temperature `T` is fit on the 2018-2025 pool by
  minimizing mean log loss, and `T` is then checked against the `T=1` (no-op)
  baseline on the held-out 2026 fold. The fitted `T=0.8857` (mild
  sharpening, since `T<1` pushes probabilities away from uniform) beats
  `T=1` on mean log loss on the 7,914-match 2018-2025 selection pool (0.79179 vs
  0.79417), on the 2026 confirmation fold overall (0.79312 vs 0.80110), and
  on the 143-match confirmation fold neutral-venue subset (0.79164 vs
  0.80382). The overall confirmation fold contains 351 matches. Paired
  bootstrap intervals for fitted-minus-baseline log loss remain below zero
  on all three reported slices. The neutral subset overlaps the overall 2026
  fold, so these are robustness slices rather than three independent
  confirmation samples. The gate passed, so
  `world_cup/forecasting.py::match_forecast` now
  applies `apply_temperature(forecast, CALIBRATION_TEMPERATURE)` to
  `MODEL`'s output before returning it. `lambda_home`, `lambda_away`, and
  `most_likely_score` are unaffected — temperature scaling only rescales
  `p_home`/`p_draw`/`p_away`.

- `vector_calibration_evaluation.json`
  (`scripts/vector_calibration_evaluation.py`, not adopted) evaluates a
  regularized five-parameter multiclass vector scaling layer on top of the
  shipped global temperature. Regularization is selected by rolling-origin
  validation across 2021-2025, rather than by the viewed 2026 slice. The
  candidate improves log loss, Brier, and RPS on the selection pool and the
  viewed 2026 robustness slices, but neutral-match ECE worsens from `0.1025`
  to `0.1612`. It therefore fails the research gate and is not wired into
  `match_forecast`. More importantly, 2026 has already been viewed during
  prior model decisions, so even a clean diagnostic pass would still require
  a future pre-registered confirmation period before production adoption.

## Market-assisted experiment

`forecasting/market.py` implements proportional, power, and Shin margin
removal plus a one-parameter logarithmic pool between the independent model
and timestamped market probabilities. `scripts/market_blend_evaluation.py`
fits that single weight on 2018-2025 and gates it on 2026 overall and neutral
matches, with minimum sample sizes and a paired bootstrap interval.
All three reported paired intervals must remain below zero before adoption.

The market-assisted path is not active because no licensed, timestamped odds
dataset is checked in. It must remain separately labeled from the independent
forecast even if it later passes the gate; incorporating market consensus is
not evidence that the independent model beats the market. See
`data/market/README.md` for the required input contract.

## Tournament-specific experiments

- `host_adjustment_evaluation.json`
  (`scripts/host_adjustment_evaluation.py`, not adopted) evaluates no host
  boost, fixed `+25`/`+50` Elo boosts, and a fitted one-parameter boost on
  explicitly identified host-team matches. Models are refit before each
  tournament edition and host effects are isolated from generic home
  advantage. Mean log loss improves for positive boosts, but the completed
  confirmation-edition cluster-bootstrap interval crosses zero. The previous
  ungated `+50` World Cup host heuristic was therefore removed from
  `TournamentTeam.rating`.

- `opener_draw_evaluation.json` (`scripts/opener_draw_evaluation.py`) is a
  research-only draw-specific experiment. Opener labels are inferred because
  the historical source lacks official stage and matchday fields. The
  experiment excludes 2026, validates by completed tournament edition, and
  can never activate production code automatically.
