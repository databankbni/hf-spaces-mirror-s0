from underdog_lab.domain import Forecast
from underdog_lab.forecasting.vector_calibration import apply_vector_scaling


def test_identity_vector_scaling_preserves_probabilities():
    forecast = Forecast(
        lambda_home=1.2,
        lambda_away=0.9,
        p_home=0.5,
        p_draw=0.3,
        p_away=0.2,
        most_likely_score="1-0",
    )

    result = apply_vector_scaling(forecast, [1.0, 1.0, 1.0, 0.0, 0.0])

    assert abs(result.p_home - forecast.p_home) < 1e-12
    assert abs(result.p_draw - forecast.p_draw) < 1e-12
    assert abs(result.p_away - forecast.p_away) < 1e-12
