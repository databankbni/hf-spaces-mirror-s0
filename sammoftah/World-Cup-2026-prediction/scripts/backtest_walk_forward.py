from __future__ import annotations

"""Walk-forward backtest: fitted Dixon-Coles Elo model vs baselines.

For each test year Y in TEST_YEARS, the Dixon-Coles Elo model is refit (same
MLE procedure as fit_elo_dixon_coles.py) on only the matches strictly before
Y, then scored on every match played during Y. This mirrors how the model
would actually have been used -- no fold sees data from its own future.

Three candidates are scored on each fold's test matches:

  - uniform: 1/3 / 1/3 / 1/3 regardless of teams (no skill baseline).
  - current: the pre-remediation model previously shipped in
    underdog_lab.world_cup.forecasting.MODEL (independent Poisson,
    elo_scale=0.00165, home_advantage_elo=0, rho=0 -- hand-set, never fit).
  - fitted: this fold's freshly-fit Dixon-Coles Elo model (intercept,
    elo_scale, home_advantage_elo, rho all fit on the training window only).

Metrics: mean log loss, Brier score, and Rank Probability Score (RPS) per
candidate, summed/averaged across all test folds. A basic calibration table
for the fitted model's predicted home-win probability is also produced.

Ship gate: the fitted model must beat both "uniform" and "current" on mean
log loss across all test folds combined and beat "current" on the
neutral-venue subset that most closely matches World Cup inference. Writes
models/backtest_report.json with the full breakdown and the gate verdict.
Does not modify
src/underdog_lab/world_cup/forecasting.py -- that swap is a separate,
human-reviewed step gated on this report's verdict.

Usage:
  python scripts/backtest_walk_forward.py
"""

import json
from datetime import date
from types import SimpleNamespace

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.elo_goals import EloGoalModel
from underdog_lab.forecasting.poisson import forecast_from_lambdas

from backtest_common import (
    calibration_table,
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
    score_candidate,
)

REPORT_PATH = MODEL_DIR / "backtest_report.json"
# Selected by scripts/upgrade_evaluation.py: beats the previous 1095-day
# (3 year) half-life on mean log loss across 2018-2025 selection folds AND
# on the held-out 2026 confirmation fold, both overall and on the
# neutral-venue subset. See models/upgrade_evaluation.json.
HALF_LIFE_DAYS = 180.0

# Test years: the dataset starts 2015-01-03, so 2018 onward leaves at least
# three years of training data for the first fold.
TEST_YEARS = list(range(2018, 2027))

UNIFORM_FORECAST = SimpleNamespace(p_home=1 / 3, p_draw=1 / 3, p_away=1 / 3)

# The pre-remediation model previously shipped in world_cup/forecasting.py:
# independent Poisson (rho=0), hand-set elo_scale, no home advantage.
CURRENT_MODEL = EloGoalModel(
    intercept=0.09531017980432493,
    elo_scale=0.00165,
    home_advantage_elo=0.0,
)


def current_model_forecast(home_elo: float, away_elo: float, neutral: bool):
    lambda_home, lambda_away = CURRENT_MODEL.lambdas(home_elo, away_elo, neutral_venue=neutral)
    return forecast_from_lambdas(lambda_home, lambda_away)


def run_fold(test_year: int, all_matches: list[dict]) -> dict:
    train_cutoff = date(test_year - 1, 12, 31)
    train_matches = [m for m in all_matches if m["date"] <= train_cutoff]
    test_matches = [m for m in all_matches if m["date"].year == test_year]
    if not test_matches:
        return {}

    fitted_model = fit_dixon_coles(train_matches, train_cutoff, HALF_LIFE_DAYS)

    totals = {
        scope: {
            name: {"log_loss": 0.0, "brier": 0.0, "rps": 0.0}
            for name in ("uniform", "current", "fitted")
        }
        for scope in ("all", "neutral")
    }
    counts = {"all": 0, "neutral": 0}
    calibration_rows = []
    for match in test_matches:
        outcome = observed_outcome(match["home_goals"], match["away_goals"])

        current_forecast = current_model_forecast(match["home_elo"], match["away_elo"], match["neutral"])
        fitted_forecast = fitted_model.forecast(match["home_elo"], match["away_elo"], neutral_venue=match["neutral"])
        forecasts = {
            "uniform": UNIFORM_FORECAST,
            "current": current_forecast,
            "fitted": fitted_forecast,
        }
        scopes = ["all"] + (["neutral"] if match["neutral"] else [])
        for scope in scopes:
            counts[scope] += 1
            for candidate, forecast in forecasts.items():
                for metric, value in score_candidate(forecast, outcome).items():
                    totals[scope][candidate][metric] += value
        calibration_rows.append((fitted_forecast.p_home, outcome == "home"))

    means = {
        scope: {
            candidate: {
                metric: total / counts[scope]
                for metric, total in metric_totals.items()
            }
            for candidate, metric_totals in scope_totals.items()
        }
        for scope, scope_totals in totals.items()
        if counts[scope]
    }
    return {
        "test_year": test_year,
        "train_matches": len(train_matches),
        "test_matches": len(test_matches),
        "neutral_test_matches": counts["neutral"],
        "fitted_params": {
            "intercept": fitted_model.intercept,
            "elo_scale": fitted_model.elo_scale,
            "home_advantage_elo": fitted_model.home_advantage_elo,
            "rho": fitted_model.rho,
        },
        "mean_scores": means["all"],
        "neutral_mean_scores": means.get("neutral", {}),
        "calibration_rows": calibration_rows,
    }


def main() -> None:
    all_matches = load_matches_with_self_elo(date(2026, 6, 12))

    folds = []
    for test_year in TEST_YEARS:
        fold = run_fold(test_year, all_matches)
        if fold:
            folds.append(fold)

    all_calibration_rows: list[tuple[float, bool]] = []
    for fold in folds:
        all_calibration_rows.extend(fold.pop("calibration_rows"))

    total_test_matches = sum(fold["test_matches"] for fold in folds)
    neutral_test_matches = sum(fold["neutral_test_matches"] for fold in folds)
    overall = {candidate: {"log_loss": 0.0, "brier": 0.0, "rps": 0.0} for candidate in ("uniform", "current", "fitted")}
    neutral_overall = {
        candidate: {"log_loss": 0.0, "brier": 0.0, "rps": 0.0}
        for candidate in ("uniform", "current", "fitted")
    }
    for fold in folds:
        for candidate, metric_means in fold["mean_scores"].items():
            for metric, mean_value in metric_means.items():
                overall[candidate][metric] += mean_value * fold["test_matches"]
        for candidate, metric_means in fold["neutral_mean_scores"].items():
            for metric, mean_value in metric_means.items():
                neutral_overall[candidate][metric] += (
                    mean_value * fold["neutral_test_matches"]
                )
    for candidate, metric_totals in overall.items():
        for metric in metric_totals:
            overall[candidate][metric] /= total_test_matches
    for candidate, metric_totals in neutral_overall.items():
        for metric in metric_totals:
            neutral_overall[candidate][metric] /= neutral_test_matches

    fitted_beats_uniform = overall["fitted"]["log_loss"] < overall["uniform"]["log_loss"]
    fitted_beats_current = overall["fitted"]["log_loss"] < overall["current"]["log_loss"]
    fitted_beats_neutral_current = (
        neutral_overall["fitted"]["log_loss"]
        < neutral_overall["current"]["log_loss"]
    )
    ship = (
        fitted_beats_uniform
        and fitted_beats_current
        and fitted_beats_neutral_current
    )

    report = {
        "test_years": TEST_YEARS,
        "half_life_days": HALF_LIFE_DAYS,
        "total_test_matches": total_test_matches,
        "neutral_test_matches": neutral_test_matches,
        "folds": folds,
        "overall_mean_scores": overall,
        "neutral_mean_scores": neutral_overall,
        "calibration_home_win": calibration_table(all_calibration_rows),
        "ship_gate": {
            "fitted_beats_uniform_log_loss": fitted_beats_uniform,
            "fitted_beats_current_log_loss": fitted_beats_current,
            "fitted_beats_current_neutral_log_loss": (
                fitted_beats_neutral_current
            ),
            "ship": ship,
            "criterion": (
                "The fitted Dixon-Coles Elo model must have a lower mean "
                "log loss than both the uniform baseline and the model "
                "previously shipped in world_cup/forecasting.py, both overall "
                "and on neutral-venue matches, across walk-forward test folds "
                "(2018-2026, no fold trained on its own test data)."
            ),
        },
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps(report["overall_mean_scores"], indent=2))
    print(json.dumps(report["ship_gate"], indent=2))


if __name__ == "__main__":
    main()
