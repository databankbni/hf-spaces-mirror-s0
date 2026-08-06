from underdog_lab.domain import Forecast
from underdog_lab.forecasting.draw_adjustment import apply_draw_logit_adjustment


def _forecast() -> Forecast:
    return Forecast(
        lambda_home=1.4,
        lambda_away=1.0,
        p_home=0.5,
        p_draw=0.3,
        p_away=0.2,
        most_likely_score="1-0",
    )


def test_draw_adjustment_preserves_home_away_ratio():
    adjusted = apply_draw_logit_adjustment(_forecast(), 0.5)

    assert adjusted.p_draw > 0.3
    assert abs((adjusted.p_home / adjusted.p_away) - 2.5) < 1e-9


def test_zero_draw_adjustment_is_probability_identity():
    forecast = _forecast()
    adjusted = apply_draw_logit_adjustment(forecast, 0.0)

    assert abs(adjusted.p_home - forecast.p_home) < 1e-9
    assert abs(adjusted.p_draw - forecast.p_draw) < 1e-9
    assert abs(adjusted.p_away - forecast.p_away) < 1e-9
