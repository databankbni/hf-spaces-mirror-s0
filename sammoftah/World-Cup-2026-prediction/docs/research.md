# Football Forecasting Research Synthesis

_Date: June 12, 2026_

## Research Question

The weak question is:

> Which AI correctly names the World Cup winner?

A single champion provides almost no statistical power. The stronger questions are:

1. Which system produces the best calibrated match-level probabilities?
2. How much incremental value comes from structured data, retrieval, language-model extraction, and agent-built pipelines?
3. Can a model add information beyond strong statistical and market baselines at a fixed pre-match horizon?

## Recommended Experimental Tracks

### Direct LLM Forecasting

Compare the same language model under controlled information conditions:

- closed-book;
- frozen structured dataset;
- frozen structured dataset plus a timestamped news corpus;
- tool-enabled analysis.

Require structured probabilities rather than categorical picks.

### Agent-Built Pipelines

Give coding agents such as Codex and other comparable coding systems the same repository, training data, hidden evaluation interface, compute allowance, token budget, and wall-clock limit.

Each agent must build and validate a complete forecasting pipeline. Evaluate the resulting software, not only its written answer.

Recommended measures:

- forecast log loss and Brier score;
- calibration;
- data leakage and backtest correctness;
- reproducibility across independent builds;
- runtime and API cost;
- code correctness and test quality.

### Human-Designed Accuracy Engine

Build a reference system that is independent of the language-model benchmark:

- Elo or similar dynamic team-strength rating;
- Poisson or Dixon-Coles goal model;
- time decay;
- venue and home advantage;
- competition importance;
- squad and lineup strength when reliable data is available;
- calibrated ensemble;
- optional market-augmented variant.

This reference is the benchmark agents must beat.

## Evaluation

### Primary Metric

Use multiclass log loss for home-win, draw, and away-win probabilities:

```text
log_loss = -log(probability assigned to the observed outcome)
```

Log loss strongly penalizes unjustified certainty and is a proper scoring rule.

### Secondary Metrics

- Multiclass Brier score
- Reliability diagrams and expected calibration error
- Sharpness, reported together with calibration
- Ranked probability score as an optional football-specific measure
- Tournament advancement Brier scores
- Runtime and cost

Accuracy and betting profit may be shown, but neither should be the primary scientific endpoint.

### Statistical Testing

Report paired differences between systems on the same matches. Use bootstrap confidence intervals with resampling units chosen to respect dependence, such as match days or tournaments rather than assuming every observation is fully independent.

A World Cup alone is too small to prove broad superiority. Use historical walk-forward evaluation for evidence and the tournament as a prospective showcase.

## Information and Leakage Controls

Every prediction record should contain:

```text
forecast_id
model_id
model_version
prompt_hash
code_commit
dataset_hash
information_cutoff
forecast_generated_at
match_kickoff
p_home
p_draw
p_away
```

Enforce `p_home + p_draw + p_away = 1` within numerical tolerance.

Use append-only prediction records, signed manifests, or Git commits created before kickoff. Dated filenames alone are not sufficient evidence.

## Market Comparison

The market is a demanding public baseline, but comparisons must be timestamp-aligned.

Define horizons such as:

- 24 hours before kickoff;
- 6 hours before kickoff;
- before confirmed lineups;
- after confirmed lineups;
- closing price.

At each horizon, compare only information and market prices available at that time. Remove bookmaker margin using a documented method.

Maintain two distinct forecasts:

1. **Independent model:** no odds as model inputs.
2. **Market-augmented model:** includes market probabilities as features.

A market-augmented model can be useful, but it must not be presented as an independent market-beating forecast.

## Feature Strategy

Begin with features that can be reconstructed historically without leakage:

- pre-match Elo difference;
- attack and defence strengths;
- recent results with time decay;
- goals and expected goals where coverage is consistent;
- neutral venue and host status;
- rest and travel;
- competition type and match importance;
- squad continuity and lineup strength.

Do not assume expected goals, player values, textual news, or any other feature improves predictions. Add each through an out-of-sample ablation study.

## Role of Language Models

Language models should initially be used for tasks where language is genuinely required:

- extracting injuries and suspensions from timestamped text;
- mapping lineup news into structured availability flags;
- identifying source-backed scenario variables;
- explaining forecasts without changing the underlying numbers;
- generating and validating code under a controlled agent benchmark.

Do not ask the language model to fabricate numerical probabilities from prose. Numerical forecasts should be produced by a reproducible statistical component or a separately calibrated learned model.

## Relevant Prior Work

- Groll et al., hybrid random-forest forecasting and simulation for the 2018 World Cup: https://arxiv.org/abs/1806.03208
- Gilch and Mueller, Elo-based Poisson modeling for the 2018 World Cup: https://arxiv.org/abs/1806.01930
- Gilch, generalized Poisson forecasting for the 2022 World Cup: https://arxiv.org/abs/2205.04173
- ForecastBench, continuously updated evaluation of language-model forecasting: https://arxiv.org/abs/2409.19839
- Prophet Arena, retrieval and actionability-oriented language-model forecasting: https://arxiv.org/abs/2510.17638
- Football forecast scoring-rule analysis: https://arxiv.org/abs/1908.08980
- StatsBomb Open Data: https://github.com/statsbomb/open-data
- International football results dataset: https://github.com/martj42/international_results
- World Football Elo Ratings: https://eloratings.net/

## Defensible Project Claim

A good initial claim is:

> We measure the incremental predictive value of statistical models, small language-model scenario extraction, and agent-built pipelines under fixed information cutoffs.

Do not claim to be the most accurate system in the market until the system wins a preregistered, held-out, timestamp-matched comparison with confidence intervals.
