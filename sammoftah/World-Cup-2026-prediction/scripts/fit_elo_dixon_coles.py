from __future__ import annotations

"""Fit the Elo-to-goals Dixon-Coles model via MLE on real historical matches.

Usage:
  python scripts/fit_elo_dixon_coles.py [--cutoff 2026-06-12] [--half-life-days 1095]

Writes models/elo_fit_report.json with the fitted parameters and basic
fit diagnostics. Does not modify src/underdog_lab/world_cup/forecasting.py
-- that swap only happens after scripts/backtest_forecasts.py confirms the
fitted model beats the current model and baselines out of sample
(see predictions/README.md-style ship-gate discipline).
"""

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from underdog_lab.config import DATA_DIR, MODEL_DIR
from underdog_lab.forecasting.dixon_coles import DixonColesEloModel, match_probability

MATCHES_PATH = DATA_DIR / "historical" / "matches.csv"
REPORT_PATH = MODEL_DIR / "elo_fit_report.json"


def load_matches(cutoff: date) -> list[dict]:
    rows = []
    with MATCHES_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            match_date = date.fromisoformat(row["date"])
            if match_date > cutoff:
                continue
            rows.append(
                {
                    "date": match_date,
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "home_goals": int(row["home_goals"]),
                    "away_goals": int(row["away_goals"]),
                    "home_elo": float(row["home_elo"]),
                    "away_elo": float(row["away_elo"]),
                    "neutral": row["neutral"] == "True",
                    "tournament": row["tournament"],
                }
            )
    return rows


def time_decay_weights(matches: list[dict], cutoff: date, half_life_days: float) -> np.ndarray:
    days_ago = np.array([(cutoff - m["date"]).days for m in matches], dtype=float)
    return 0.5 ** (days_ago / half_life_days)


def negative_log_likelihood(params: np.ndarray, matches: list[dict], weights: np.ndarray) -> float:
    """NLL parameterized by (intercept, elo_scale, home_adv_logshift, rho).

    ``home_adv_logshift`` is the direct additive shift to the home team's
    log scoring rate for non-neutral matches -- i.e.
    ``elo_scale * home_advantage_elo`` in EloGoalModel terms. Fitting this
    log-shift directly (rather than the raw Elo-point bonus) keeps all four
    parameters on a comparable ~0.001-1 scale, which L-BFGS-B's default
    finite-difference gradient needs to make progress. A raw
    ``home_advantage_elo`` of ~100 only changes the log-rate by
    ``elo_scale * 100`` ~ 0.2, so fitting it directly under-resolves the
    gradient and the optimizer barely moves it from its starting value.
    """
    intercept, elo_scale, home_adv_logshift, rho = params
    total = 0.0
    for match, weight in zip(matches, weights):
        diff = match["home_elo"] - match["away_elo"]
        home_shift = 0.0 if match["neutral"] else home_adv_logshift
        log_lambda_home = intercept + elo_scale * diff + home_shift
        log_lambda_away = intercept - elo_scale * diff - home_shift
        lambda_home = min(4.0, max(0.15, math.exp(log_lambda_home)))
        lambda_away = min(4.0, max(0.15, math.exp(log_lambda_away)))
        probability = match_probability(
            match["home_goals"], match["away_goals"], lambda_home, lambda_away, rho
        )
        total -= weight * math.log(max(probability, 1e-12))
    return total


# Start from the current hand-set coefficients (forecasting.py MODEL), with
# home_adv_logshift=0 and rho=0 (independent Poisson, no home advantage
# applied -- the current shipped configuration).
DEFAULT_X0 = np.array([0.09531017980432493, 0.00165, 0.0, 0.0])
DEFAULT_BOUNDS = [
    (-1.0, 1.0),    # intercept
    (0.0, 0.01),    # elo_scale
    (-1.0, 1.0),    # home_adv_logshift
    (-0.15, 0.15),  # rho
]


def fit_params(matches: list[dict], weights: np.ndarray, x0: np.ndarray = DEFAULT_X0, bounds=DEFAULT_BOUNDS):
    """Fit (intercept, elo_scale, home_adv_logshift, rho) via L-BFGS-B.

    Returns the ``scipy.optimize.OptimizeResult``. Used both by this
    script's CLI and by the walk-forward backtest, which refits on each
    fold's training window.
    """
    return minimize(
        negative_log_likelihood,
        x0,
        args=(matches, weights),
        method="L-BFGS-B",
        bounds=bounds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the Elo-to-goals Dixon-Coles model.")
    parser.add_argument("--cutoff", default="2026-06-12", help="Last match date to train on (inclusive).")
    parser.add_argument("--half-life-days", type=float, default=180.0, help="Time-decay half-life in days (default 180, selected by scripts/upgrade_evaluation.py).")
    args = parser.parse_args()

    cutoff = date.fromisoformat(args.cutoff)
    matches = load_matches(cutoff)
    weights = time_decay_weights(matches, cutoff, args.half_life_days)

    x0 = DEFAULT_X0
    result = fit_params(matches, weights, x0, DEFAULT_BOUNDS)

    intercept, elo_scale, home_adv_logshift, rho = result.x
    home_advantage_elo = home_adv_logshift / elo_scale

    baseline_nll = negative_log_likelihood(x0, matches, weights)
    fitted_nll = result.fun

    report = {
        "fitted_at": cutoff.isoformat(),
        "information_cutoff": args.cutoff,
        "training_matches": len(matches),
        "training_date_range": [matches[0]["date"].isoformat(), matches[-1]["date"].isoformat()],
        "half_life_days": args.half_life_days,
        "optimizer": {
            "method": "L-BFGS-B",
            "converged": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
        },
        "starting_params": {
            "intercept": float(x0[0]),
            "elo_scale": float(x0[1]),
            "home_adv_logshift": float(x0[2]),
            "home_advantage_elo": 0.0,
            "rho": float(x0[3]),
            "weighted_nll": float(baseline_nll),
        },
        "fitted_params": {
            "intercept": float(intercept),
            "elo_scale": float(elo_scale),
            "home_adv_logshift": float(home_adv_logshift),
            "home_advantage_elo": float(home_advantage_elo),
            "rho": float(rho),
            "weighted_nll": float(fitted_nll),
            "implied_base_goal_rate": math.exp(intercept),
        },
        "notes": [
            "home_advantage_elo is fitted on real matches where the listed "
            "home team plays on its own soil (neutral=False). World Cup "
            "2026 group fixtures are all treated as neutral_venue=True in "
            "match_forecast. The host's +50 Elo bonus "
            "(TournamentTeam.rating) is a separate, transparent heuristic and "
            "was not estimated by this fit, so host-specific World Cup "
            "forecasts retain that limitation.",
            "rho is the Dixon-Coles low-score correlation term; rho=0 "
            "recovers the independent-Poisson model shipped before this fit.",
        ],
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps(report["fitted_params"], indent=2))


if __name__ == "__main__":
    main()
