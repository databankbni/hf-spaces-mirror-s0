from underdog_lab.domain import UserForecast
from underdog_lab.forecasting.scoring import brier_score, log_loss


def test_better_probability_gets_lower_log_loss():
    good = UserForecast(p_home=0.8, p_draw=0.1, p_away=0.1)
    bad = UserForecast(p_home=0.2, p_draw=0.4, p_away=0.4)
    assert log_loss(good, "home") < log_loss(bad, "home")


def test_perfect_brier_is_zero():
    perfect = UserForecast(p_home=1.0, p_draw=0.0, p_away=0.0)
    assert brier_score(perfect, "home") == 0.0
