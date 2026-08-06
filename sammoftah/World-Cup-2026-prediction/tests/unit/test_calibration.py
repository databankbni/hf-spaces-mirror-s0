import math

from underdog_lab.forecasting.calibration import apply_temperature, fit_temperature
from underdog_lab.forecasting.dixon_coles import forecast_from_lambdas_dc


def _forecast():
    return forecast_from_lambdas_dc(1.4, 1.1, -0.08)


def test_temperature_one_is_identity():
    forecast = _forecast()
    result = apply_temperature(forecast, 1.0)
    assert result.p_home == forecast.p_home
    assert result.p_draw == forecast.p_draw
    assert result.p_away == forecast.p_away


def test_low_temperature_sharpens_towards_favorite():
    forecast = _forecast()
    sharpened = apply_temperature(forecast, 0.5)
    favorite = max(("p_home", "p_draw", "p_away"), key=lambda attr: getattr(forecast, attr))
    assert getattr(sharpened, favorite) > getattr(forecast, favorite)


def test_high_temperature_flattens_towards_uniform():
    forecast = _forecast()
    flattened = apply_temperature(forecast, 5.0)
    favorite = max(("p_home", "p_draw", "p_away"), key=lambda attr: getattr(forecast, attr))
    assert getattr(flattened, favorite) < getattr(forecast, favorite)


def test_probabilities_still_sum_to_one():
    forecast = _forecast()
    result = apply_temperature(forecast, 0.7)
    assert math.isclose(result.p_home + result.p_draw + result.p_away, 1.0, abs_tol=1e-9)


def test_lambdas_and_most_likely_score_are_preserved():
    forecast = _forecast()
    result = apply_temperature(forecast, 0.6)
    assert result.lambda_home == forecast.lambda_home
    assert result.lambda_away == forecast.lambda_away
    assert result.most_likely_score == forecast.most_likely_score


def test_fit_temperature_does_not_make_mean_log_loss_worse():
    from underdog_lab.forecasting.scoring import log_loss

    rows = [
        (forecast_from_lambdas_dc(1.4, 1.1, -0.08), "home"),
        (forecast_from_lambdas_dc(0.9, 1.6, -0.08), "away"),
        (forecast_from_lambdas_dc(1.0, 1.0, -0.08), "draw"),
        (forecast_from_lambdas_dc(2.1, 0.7, -0.08), "home"),
        (forecast_from_lambdas_dc(1.2, 1.3, -0.08), "draw"),
    ]
    temperature = fit_temperature(rows)

    baseline = sum(log_loss(forecast, outcome) for forecast, outcome in rows) / len(rows)
    fitted = sum(
        log_loss(apply_temperature(forecast, temperature), outcome) for forecast, outcome in rows
    ) / len(rows)
    assert fitted <= baseline + 1e-12
