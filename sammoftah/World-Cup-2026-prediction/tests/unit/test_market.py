import pytest

from underdog_lab.forecasting.dixon_coles import forecast_from_lambdas_dc
from underdog_lab.forecasting.market import (
    fit_market_weight,
    market_assisted_forecast,
    market_probabilities,
)


@pytest.mark.parametrize("method", ["proportional", "power", "shin"])
def test_margin_removal_produces_normalized_probabilities(method):
    forecast = market_probabilities((1.8, 3.6, 5.0), method)
    assert forecast.p_home + forecast.p_draw + forecast.p_away == pytest.approx(1.0)
    assert forecast.p_home > forecast.p_draw > forecast.p_away


def test_market_assisted_forecast_preserves_score_grid_fields():
    independent = forecast_from_lambdas_dc(1.4, 1.0, -0.08)
    market = market_probabilities((2.8, 3.2, 2.6))
    blended = market_assisted_forecast(independent, market, market_weight=0.4)

    assert blended.lambda_home == independent.lambda_home
    assert blended.lambda_away == independent.lambda_away
    assert blended.most_likely_score == independent.most_likely_score
    assert blended.p_away > independent.p_away


def test_zero_market_weight_recovers_independent_probabilities():
    independent = forecast_from_lambdas_dc(1.4, 1.0, -0.08)
    market = market_probabilities((5.0, 3.5, 1.7))
    blended = market_assisted_forecast(independent, market, market_weight=0.0)

    assert blended.p_home == pytest.approx(independent.p_home)
    assert blended.p_draw == pytest.approx(independent.p_draw)
    assert blended.p_away == pytest.approx(independent.p_away)


def test_fit_market_weight_favors_informative_market():
    home = forecast_from_lambdas_dc(1.0, 1.0, -0.08)
    away = forecast_from_lambdas_dc(1.0, 1.0, -0.08)
    rows = [
        (home, market_probabilities((1.5, 4.0, 7.0)), "home"),
        (away, market_probabilities((7.0, 4.0, 1.5)), "away"),
    ]
    assert fit_market_weight(rows) > 0.5


def test_unknown_margin_method_is_rejected():
    with pytest.raises(ValueError, match="unknown"):
        market_probabilities((2.0, 3.0, 4.0), "invented")
