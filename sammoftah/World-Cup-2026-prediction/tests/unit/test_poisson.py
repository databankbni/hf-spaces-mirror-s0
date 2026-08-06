from __future__ import annotations

import pytest

from underdog_lab.forecasting.poisson import forecast_from_lambdas


def test_probabilities_sum_to_one():
    forecast = forecast_from_lambdas(1.6, 0.9)
    assert forecast.p_home + forecast.p_draw + forecast.p_away == pytest.approx(1.0)


def test_increasing_home_rate_increases_home_probability():
    low = forecast_from_lambdas(1.0, 1.0)
    high = forecast_from_lambdas(1.8, 1.0)
    assert high.p_home > low.p_home


def test_forecast_is_finite():
    forecast = forecast_from_lambdas(0.15, 4.0)
    assert 0 <= forecast.p_home <= 1
    assert 0 <= forecast.p_draw <= 1
    assert 0 <= forecast.p_away <= 1
