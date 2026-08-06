import math

from underdog_lab.forecasting.dixon_coles import (
    DixonColesEloModel,
    dc_tau,
    forecast_from_lambdas_dc,
    match_probability,
    top_scorelines_dc,
)
from underdog_lab.forecasting.poisson import forecast_from_lambdas


def test_dc_tau_is_identity_when_rho_is_zero():
    for home_goals, away_goals in [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2)]:
        assert dc_tau(home_goals, away_goals, 1.3, 1.1, 0.0) == 1.0


def test_dc_tau_only_adjusts_low_scores():
    assert dc_tau(2, 0, 1.3, 1.1, 0.1) == 1.0
    assert dc_tau(0, 2, 1.3, 1.1, 0.1) == 1.0
    assert dc_tau(2, 2, 1.3, 1.1, 0.1) == 1.0


def test_forecast_from_lambdas_dc_matches_independent_poisson_when_rho_is_zero():
    dc = forecast_from_lambdas_dc(1.4, 1.1, 0.0)
    independent = forecast_from_lambdas(1.4, 1.1)
    assert math.isclose(dc.p_home, independent.p_home, abs_tol=1e-9)
    assert math.isclose(dc.p_draw, independent.p_draw, abs_tol=1e-9)
    assert math.isclose(dc.p_away, independent.p_away, abs_tol=1e-9)


def test_negative_rho_increases_one_one_draw_probability():
    # tau(1, 1) = 1 - rho, so a negative rho (as fitted on real data, capturing
    # the well-known excess of low-scoring draws) raises P(1-1) above the
    # independent-Poisson baseline.
    independent = match_probability(1, 1, 1.2, 1.1, 0.0)
    correlated = match_probability(1, 1, 1.2, 1.1, -0.1)
    assert correlated > independent


def test_forecast_from_lambdas_dc_probabilities_sum_to_one():
    dc = forecast_from_lambdas_dc(1.4, 1.1, -0.05)
    assert math.isclose(dc.p_home + dc.p_draw + dc.p_away, 1.0, abs_tol=1e-9)


def test_dixon_coles_model_matches_independent_poisson_when_rho_is_zero():
    model = DixonColesEloModel(rho=0.0)
    forecast = model.forecast(1800, 1750, neutral_venue=True)
    lambda_home, lambda_away = model.lambdas(1800, 1750, neutral_venue=True)
    independent = forecast_from_lambdas(lambda_home, lambda_away)
    assert math.isclose(forecast.p_home, independent.p_home, abs_tol=1e-9)
    assert math.isclose(forecast.p_draw, independent.p_draw, abs_tol=1e-9)


def test_dixon_coles_model_log_likelihood_is_finite():
    model = DixonColesEloModel(rho=-0.08)
    log_likelihood = model.match_log_likelihood(1, 1, 1800, 1750, neutral_venue=False)
    assert math.isfinite(log_likelihood)
    assert log_likelihood < 0


def test_top_scorelines_are_ranked_and_normalized_to_score_grid():
    scorelines = top_scorelines_dc(1.4, 1.1, -0.08, limit=3)

    assert len(scorelines) == 3
    assert scorelines[0][1] >= scorelines[1][1] >= scorelines[2][1]
    assert all(0.0 < probability < 1.0 for _, probability in scorelines)


def test_most_likely_score_is_global_score_matrix_mode():
    forecast = forecast_from_lambdas_dc(1.4, 1.1, -0.08)
    scorelines = top_scorelines_dc(1.4, 1.1, -0.08, limit=3)

    assert forecast.most_likely_score == scorelines[0][0]
    assert forecast.most_likely_score == "1-1"
