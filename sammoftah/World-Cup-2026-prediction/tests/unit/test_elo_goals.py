from underdog_lab.forecasting.elo_goals import EloGoalModel


def test_equal_teams_are_equal_on_neutral_ground():
    home, away = EloGoalModel().lambdas(1800, 1800, neutral_venue=True)
    assert home == away


def test_home_advantage_changes_equal_match():
    home, away = EloGoalModel().lambdas(1800, 1800, neutral_venue=False)
    assert home > away


def test_stronger_team_gets_higher_rate():
    home, away = EloGoalModel().lambdas(2100, 1700, neutral_venue=True)
    assert home > away
