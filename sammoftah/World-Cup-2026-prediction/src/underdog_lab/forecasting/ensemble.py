"""Combine two probabilistic forecasts via a logarithmic opinion pool.

For each outcome i, the blended probability is proportional to
``p_i_1 ** weight * p_i_2 ** (1 - weight)``, then renormalized so the three
outcomes sum to 1. This is the standard way to combine independently-derived
probability forecasts (the "log-odds" or "logarithmic opinion pool" blend) --
simple, well-precedented, and requires no additional fitting beyond the
blend weight itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def blend_probabilities(first: Any, second: Any, weight: float) -> dict[str, float]:
    """Return a logarithmic pool with ``weight`` assigned to ``first``."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between 0 and 1")

    raw = {
        outcome: (
            getattr(first, f"p_{outcome}") ** weight
            * getattr(second, f"p_{outcome}") ** (1.0 - weight)
        )
        for outcome in ("home", "draw", "away")
    }
    total = sum(raw.values())
    return {outcome: value / total for outcome, value in raw.items()}


def blend_forecasts(first: Any, second: Any, weight: float) -> SimpleNamespace:
    """Blend two forecasts with ``weight`` on ``first`` (0 <= weight <= 1)."""
    blended = blend_probabilities(first, second, weight)

    lambda_home = weight * first.lambda_home + (1.0 - weight) * second.lambda_home
    lambda_away = weight * first.lambda_away + (1.0 - weight) * second.lambda_away
    most_likely_score = first.most_likely_score if weight >= 0.5 else second.most_likely_score

    return SimpleNamespace(
        p_home=blended["home"],
        p_draw=blended["draw"],
        p_away=blended["away"],
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        most_likely_score=most_likely_score,
    )
