"""Post-hoc temperature scaling for Dixon-Coles Elo forecasts.

For temperature ``T``, each outcome probability is raised to the power
``1/T`` and the result renormalized:

    p_i' = p_i ** (1/T) / sum_j (p_j ** (1/T))

``T < 1`` sharpens a forecast (pushes probabilities away from uniform),
``T > 1`` flattens it (pulls probabilities toward uniform), and ``T == 1``
is the identity transform. ``lambda_home``, ``lambda_away``, and
``most_likely_score`` are derived from the underlying score matrix, not from
``p_home``/``p_draw``/``p_away``, so they are carried through unchanged.

``fit_temperature`` chooses ``T`` to minimize mean log loss on a set of
(forecast, observed outcome) pairs -- the same selection/confirmation
discipline used elsewhere in this project (see
``scripts/recalibration_evaluation.py``) decides whether the fitted value is
ever applied to the shipped model.
"""

from __future__ import annotations

from underdog_lab.domain import Forecast, Outcome
from underdog_lab.forecasting.optimization import bounded_minimize
from underdog_lab.forecasting.scoring import log_loss


def apply_temperature(forecast: Forecast, temperature: float) -> Forecast:
    """Return a copy of ``forecast`` with its outcome probabilities rescaled
    by ``temperature``. ``temperature == 1.0`` returns an equivalent forecast."""
    if temperature <= 0:
        raise ValueError("temperature must be greater than zero")
    if temperature == 1.0:
        return forecast

    inverse = 1.0 / temperature
    raw = {
        "p_home": forecast.p_home**inverse,
        "p_draw": forecast.p_draw**inverse,
        "p_away": forecast.p_away**inverse,
    }
    total = sum(raw.values())
    data = forecast.model_dump()
    data.update({key: value / total for key, value in raw.items()})
    return Forecast(**data)


def fit_temperature(rows: list[tuple[Forecast, Outcome]]) -> float:
    """Choose the temperature that minimizes mean log loss over ``rows``."""
    if not rows:
        raise ValueError("at least one forecast row is required")

    def mean_log_loss(temperature: float) -> float:
        total = 0.0
        for forecast, outcome in rows:
            total += log_loss(apply_temperature(forecast, temperature), outcome)
        return total / len(rows)

    return bounded_minimize(mean_log_loss, 0.05, 20.0)
