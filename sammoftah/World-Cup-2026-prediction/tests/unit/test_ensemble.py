from types import SimpleNamespace

import pytest

from underdog_lab.forecasting.ensemble import blend_forecasts


def _forecast(p_home, p_draw, p_away, lambda_home=1.2, lambda_away=1.0, score="1-0"):
    return SimpleNamespace(
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        most_likely_score=score,
    )


def test_blend_probabilities_sum_to_one():
    first = _forecast(0.5, 0.3, 0.2)
    second = _forecast(0.3, 0.3, 0.4)
    blended = blend_forecasts(first, second, weight=0.4)
    total = blended.p_home + blended.p_draw + blended.p_away
    assert total == pytest.approx(1.0)


def test_weight_one_recovers_first_forecast():
    first = _forecast(0.5, 0.3, 0.2)
    second = _forecast(0.1, 0.1, 0.8)
    blended = blend_forecasts(first, second, weight=1.0)
    assert blended.p_home == pytest.approx(first.p_home)
    assert blended.p_draw == pytest.approx(first.p_draw)
    assert blended.p_away == pytest.approx(first.p_away)


def test_weight_zero_recovers_second_forecast():
    first = _forecast(0.5, 0.3, 0.2)
    second = _forecast(0.1, 0.1, 0.8)
    blended = blend_forecasts(first, second, weight=0.0)
    assert blended.p_home == pytest.approx(second.p_home)
    assert blended.p_draw == pytest.approx(second.p_draw)
    assert blended.p_away == pytest.approx(second.p_away)


def test_invalid_weight_raises():
    first = _forecast(0.5, 0.3, 0.2)
    second = _forecast(0.1, 0.1, 0.8)
    with pytest.raises(ValueError):
        blend_forecasts(first, second, weight=1.5)
