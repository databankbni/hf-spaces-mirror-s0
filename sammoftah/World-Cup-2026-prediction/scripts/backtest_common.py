"""Shared walk-forward backtest helpers.

Used by both ``backtest_walk_forward.py`` (the official ship-gated backtest
for the currently shipped MODEL) and ``upgrade_evaluation.py`` (the
half-life / ensemble experiments). Keeping the fold-fitting and scoring
logic in one place means an experiment and the official backtest can never
silently diverge in how a fold is built or scored.
"""

from __future__ import annotations

from datetime import date

from underdog_lab.domain import Outcome
from underdog_lab.forecasting.dixon_coles import DixonColesEloModel
from underdog_lab.forecasting.scoring import brier_score, log_loss, rank_probability_score
from underdog_lab.forecasting.self_elo import compute_self_elo

from fit_elo_dixon_coles import DEFAULT_BOUNDS, DEFAULT_X0, fit_params, load_matches, time_decay_weights


def load_matches_with_self_elo(cutoff: date) -> list[dict]:
    """Load matches and attach pre-match self-computed Elo ratings.

    ``self_home_elo``/``self_away_elo`` are independent of the eloratings.net
    ``home_elo``/``away_elo`` columns -- see ``forecasting/self_elo.py``.
    """
    matches = load_matches(cutoff)
    for match, (self_home, self_away) in zip(matches, compute_self_elo(matches)):
        match["self_home_elo"] = self_home
        match["self_away_elo"] = self_away
    return matches


def observed_outcome(home_goals: int, away_goals: int) -> Outcome:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def score_candidate(forecast, outcome: str) -> dict[str, float]:
    return {
        "log_loss": log_loss(forecast, outcome),
        "brier": brier_score(forecast, outcome),
        "rps": rank_probability_score(forecast, outcome),
    }


def fit_dixon_coles(
    train_matches: list[dict],
    train_cutoff: date,
    half_life_days: float,
    elo_keys: tuple[str, str] = ("home_elo", "away_elo"),
) -> DixonColesEloModel:
    """Fit a DixonColesEloModel on ``train_matches`` using the given Elo
    source columns and time-decay half-life. Same MLE procedure as
    ``fit_elo_dixon_coles.py``."""
    weights = time_decay_weights(train_matches, train_cutoff, half_life_days)
    if elo_keys != ("home_elo", "away_elo"):
        train_matches = [
            {**m, "home_elo": m[elo_keys[0]], "away_elo": m[elo_keys[1]]}
            for m in train_matches
        ]
    result = fit_params(train_matches, weights, DEFAULT_X0, DEFAULT_BOUNDS)
    intercept, elo_scale, home_adv_logshift, rho = result.x
    return DixonColesEloModel(
        intercept=float(intercept),
        elo_scale=float(elo_scale),
        home_advantage_elo=float(home_adv_logshift / elo_scale),
        rho=float(rho),
    )


def calibration_table(rows: list[tuple[float, bool]]) -> list[dict]:
    """Bucket predicted home-win probability into deciles and compare to
    the realized home-win frequency in each bucket (basic calibration)."""
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(10)]
    for p_home, was_home in rows:
        index = min(9, int(p_home * 10))
        buckets[index].append((p_home, was_home))

    table = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        table.append(
            {
                "predicted_range": [index / 10, (index + 1) / 10],
                "n": len(bucket),
                "predicted_mean": sum(row[0] for row in bucket) / len(bucket),
                "observed_home_win_rate": (
                    sum(row[1] for row in bucket) / len(bucket)
                ),
            }
        )
    return table
