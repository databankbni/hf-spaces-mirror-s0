from __future__ import annotations

import math

from underdog_lab.domain import Forecast, Outcome, UserForecast


def probabilities(forecast: Forecast | UserForecast) -> dict[Outcome, float]:
    return {
        "home": forecast.p_home,
        "draw": forecast.p_draw,
        "away": forecast.p_away,
    }


def log_loss(forecast: Forecast | UserForecast, observed: Outcome) -> float:
    probability = min(1.0 - 1e-15, max(1e-15, probabilities(forecast)[observed]))
    return -math.log(probability)


def brier_score(forecast: Forecast | UserForecast, observed: Outcome) -> float:
    probs = probabilities(forecast)
    return sum(
        (probability - (1.0 if outcome == observed else 0.0)) ** 2
        for outcome, probability in probs.items()
    )


# Conventional ordering for the Rank Probability Score: away win, draw, home
# win. RPS treats outcomes as ordered categories (a forecast that confuses
# "away win" for "draw" is penalised less than one that confuses it for
# "home win"), which is standard practice for 1X2 football forecasts.
_RPS_ORDER: tuple[Outcome, ...] = ("away", "draw", "home")


def rank_probability_score(forecast: Forecast | UserForecast, observed: Outcome) -> float:
    probs = probabilities(forecast)
    cumulative_forecast = 0.0
    cumulative_observed = 0.0
    total = 0.0
    for outcome in _RPS_ORDER:
        cumulative_forecast += probs[outcome]
        cumulative_observed += 1.0 if outcome == observed else 0.0
        total += (cumulative_forecast - cumulative_observed) ** 2
    return total / (len(_RPS_ORDER) - 1)
