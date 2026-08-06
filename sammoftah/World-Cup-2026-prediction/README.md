---
title: World Cup 2026 Forecaster
emoji: ⚽
colorFrom: blue
colorTo: red
sdk: gradio
sdk_version: 6.18.0
python_version: 3.12
app_file: app.py
pinned: false
license: mit
models:
  - HuggingFaceTB/SmolLM2-360M-Instruct
---

# World Cup 2026 Forecaster

A football forecasting project built around one idea: a probability is only useful if it's calibrated, so the model is judged on the full distribution over home win, draw, and away win, not on whether it picked the "right" team.

The 2026 World Cup is over. Spain won the final 1-0 after extra time against Argentina. The app now shows the finished tournament and its full track record instead of live predictions, since there's nothing left to forecast.

## How it works

- A four-parameter Elo-to-goals Dixon-Coles model (`intercept`, `elo_scale`, `home_advantage_elo`, `rho`), fit on real match history with time-decay weighting and validated with a strict walk-forward backtest, 2018 through 2026.
- A Monte Carlo tournament simulator built on top of it, covering all 48 teams, the 72 group fixtures, FIFA's Round-of-32 slots, and all 495 official third-place bracket mappings.
- A small local language model (SmolLM2-360M) that reads a sentence describing a scenario, such as an injury, and extracts a typed factor with team, severity, and certainty. It never invents a probability. A deterministic ruleset turns its output into a bounded adjustment, and the statistical model owns every number.
- A QLoRA fine-tune of that extraction model was trained and evaluated against a pre-declared gate. It failed the gate (marginal F1 gain, regressed team attribution, higher fallback rate) and was not shipped. See `results/ship_decision.json`.

## Track record

Every prediction is saved before its match is played, hashed, and never rewritten. The app's Track Record tab scores each one against what actually happened, including the final: the model gave Spain 40.6%, a draw 30.1%, and Argentina 29.3% about 44 hours before kickoff, and Spain won. One match doesn't prove calibration on its own, which is why the backtest across thousands of matches is the real evidence, but the call is there, unedited, next to the result.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app downloads and runs a Q8 quantization of SmolLM2-360M-Instruct through `llama-cpp-python` on first boot. To skip that:

```bash
UNDERDOG_EXTRACTOR=mock python app.py
```

## Reproduce the core

```bash
PYTHONPATH=src python scripts/prepare_matches.py
PYTHONPATH=src pytest
UNDERDOG_EXTRACTOR=mock PYTHONPATH=src python scripts/evaluate_extractor.py
make sunday
```

## Evaluation principles

- Primary metric is multiclass log loss. Secondary metrics are Brier score, calibration, sharpness, and RPS.
- Historical validation is strictly walk-forward: a model never sees its own test year.
- Live predictions are immutable, timestamped, and locked before kickoff.
- Prospective results (real predictions scored on real outcomes) are never mixed with retrospective replays of the current model against old matches.

## Result and deployment automation

`.github/workflows/result-check.yml` polls every three hours, pulls results from football-data.org or ESPN's public feed, and opens a pull request if anything changed. A human reviews and merges it. Automation never writes results directly to `main`. `.github/workflows/deploy-space.yml` then pushes the merged revision to the Space and confirms it's actually running before the workflow succeeds.

## Claim boundary

This is an experimental forecasting lab, not a claim to be the most accurate model in football. An accuracy claim would require a frozen benchmark, held-out evaluation, uncertainty intervals, and comparison against de-margined market odds at matched timestamps. What's here instead is a documented model, an honest backtest, and a track record that includes the losses.

## Links

- Live Space: https://huggingface.co/spaces/sammoftah/World-Cup-2026-prediction
- Source: https://github.com/OsamaMoftah/World-Cup-2026-prediction
