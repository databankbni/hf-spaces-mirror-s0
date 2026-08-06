"""Market-implied probabilities and a gated market-assisted forecast.

Odds are an optional, separately reported signal. They never replace the
independent Dixon-Coles forecast, and this module performs no network access.
Callers must supply timestamped decimal odds captured before kickoff.
"""

from __future__ import annotations

from collections.abc import Iterable

from underdog_lab.domain import Forecast, Outcome, UserForecast
from underdog_lab.forecasting.ensemble import blend_probabilities
from underdog_lab.forecasting.optimization import bounded_minimize
from underdog_lab.forecasting.scoring import log_loss

MarginMethod = str


def _implied(decimal_odds: Iterable[float]) -> tuple[float, float, float]:
    odds = tuple(float(value) for value in decimal_odds)
    if len(odds) != 3:
        raise ValueError("exactly three decimal odds are required")
    if any(value <= 1.0 for value in odds):
        raise ValueError("decimal odds must be greater than 1.0")
    return tuple(1.0 / value for value in odds)


def _as_forecast(probabilities: tuple[float, float, float]) -> UserForecast:
    return UserForecast(
        p_home=probabilities[0],
        p_draw=probabilities[1],
        p_away=probabilities[2],
    )


def proportional_probabilities(decimal_odds: Iterable[float]) -> UserForecast:
    implied = _implied(decimal_odds)
    total = sum(implied)
    return _as_forecast(tuple(value / total for value in implied))


def power_probabilities(decimal_odds: Iterable[float]) -> UserForecast:
    """Remove margin by finding ``k`` such that ``sum(implied**k) == 1``."""
    implied = _implied(decimal_odds)
    low, high = 0.01, 100.0
    for _ in range(100):
        exponent = (low + high) / 2.0
        total = sum(value**exponent for value in implied)
        if total > 1.0:
            low = exponent
        else:
            high = exponent
    exponent = (low + high) / 2.0
    probabilities = tuple(value**exponent for value in implied)
    total = sum(probabilities)
    return _as_forecast(tuple(value / total for value in probabilities))


def shin_probabilities(decimal_odds: Iterable[float]) -> UserForecast:
    """Remove margin with Shin's insider-trading parameterization."""
    implied = _implied(decimal_odds)
    implied_total = sum(implied)

    def probabilities(z: float) -> tuple[float, float, float]:
        if z >= 1.0:
            z = 1.0 - 1e-12
        return tuple(
            (
                (z * z + 4.0 * (1.0 - z) * value * value / implied_total)
                ** 0.5
                - z
            )
            / (2.0 * (1.0 - z))
            for value in implied
        )

    low, high = 0.0, 1.0 - 1e-12
    for _ in range(100):
        z = (low + high) / 2.0
        if sum(probabilities(z)) > 1.0:
            low = z
        else:
            high = z
    result = probabilities((low + high) / 2.0)
    total = sum(result)
    return _as_forecast(tuple(value / total for value in result))


def market_probabilities(
    decimal_odds: Iterable[float],
    method: MarginMethod = "proportional",
) -> UserForecast:
    methods = {
        "proportional": proportional_probabilities,
        "power": power_probabilities,
        "shin": shin_probabilities,
    }
    try:
        converter = methods[method]
    except KeyError as error:
        raise ValueError(f"unknown margin-removal method: {method}") from error
    return converter(decimal_odds)


def market_assisted_forecast(
    independent: Forecast,
    market: UserForecast,
    market_weight: float,
) -> Forecast:
    """Blend market probabilities into an independent forecast.

    Score-grid fields remain those of the independent model. The market only
    changes the displayed 1X2 distribution.
    """
    blended = blend_probabilities(independent, market, 1.0 - market_weight)
    return Forecast(
        lambda_home=independent.lambda_home,
        lambda_away=independent.lambda_away,
        p_home=blended["home"],
        p_draw=blended["draw"],
        p_away=blended["away"],
        most_likely_score=independent.most_likely_score,
    )


def fit_market_weight(
    rows: list[tuple[Forecast, UserForecast, Outcome]],
) -> float:
    """Fit the single market weight by minimizing mean log loss."""
    if not rows:
        raise ValueError("at least one forecast row is required")

    def objective(weight: float) -> float:
        return sum(
            log_loss(market_assisted_forecast(independent, market, weight), outcome)
            for independent, market, outcome in rows
        ) / len(rows)

    return bounded_minimize(objective, 0.0, 1.0)
