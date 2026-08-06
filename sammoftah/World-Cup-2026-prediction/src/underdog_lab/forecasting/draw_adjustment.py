from __future__ import annotations

import math

from underdog_lab.domain import Forecast, Outcome
from underdog_lab.forecasting.optimization import bounded_minimize
from underdog_lab.forecasting.scoring import log_loss


def apply_draw_logit_adjustment(forecast: Forecast, adjustment: float) -> Forecast:
    """Adjust draw odds while preserving the home-to-away probability ratio."""
    draw = min(1.0 - 1e-15, max(1e-15, forecast.p_draw))
    adjusted_odds = (draw / (1.0 - draw)) * math.exp(adjustment)
    adjusted_draw = adjusted_odds / (1.0 + adjusted_odds)
    non_draw = 1.0 - adjusted_draw
    home_away_total = forecast.p_home + forecast.p_away
    data = forecast.model_dump()
    data.update(
        {
            "p_home": non_draw * forecast.p_home / home_away_total,
            "p_draw": adjusted_draw,
            "p_away": non_draw * forecast.p_away / home_away_total,
        }
    )
    return Forecast(**data)


def fit_draw_logit_adjustment(rows: list[tuple[Forecast, Outcome]]) -> float:
    if not rows:
        raise ValueError("at least one forecast row is required")

    def objective(adjustment: float) -> float:
        return sum(
            log_loss(apply_draw_logit_adjustment(forecast, adjustment), outcome)
            for forecast, outcome in rows
        ) / len(rows)

    return bounded_minimize(objective, -3.0, 3.0)
