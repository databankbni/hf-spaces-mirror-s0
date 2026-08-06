from underdog_lab.forecasting.self_elo import START_RATING, compute_self_elo


def test_first_match_uses_start_rating_for_both_teams():
    matches = [
        {"home_team": "AA", "away_team": "BB", "home_goals": 1, "away_goals": 0},
    ]
    pre_match = compute_self_elo(matches)
    assert pre_match == [(START_RATING, START_RATING)]


def test_winner_rating_increases_for_next_match():
    matches = [
        {"home_team": "AA", "away_team": "BB", "home_goals": 2, "away_goals": 0},
        {"home_team": "AA", "away_team": "CC", "home_goals": 0, "away_goals": 0},
    ]
    pre_match = compute_self_elo(matches)
    # AA won match 1, so its rating going into match 2 should have risen
    # above the starting rating, while CC (unplayed) is still at start.
    assert pre_match[1][0] > START_RATING
    assert pre_match[1][1] == START_RATING


def test_rating_changes_are_zero_sum():
    matches = [
        {"home_team": "AA", "away_team": "BB", "home_goals": 3, "away_goals": 1},
        {"home_team": "BB", "away_team": "AA", "home_goals": 1, "away_goals": 1},
    ]
    pre_match = compute_self_elo(matches)
    # After match 1, AA gained exactly what BB lost.
    aa_after_1 = pre_match[1][1]  # AA is away in match 2
    bb_after_1 = pre_match[1][0]  # BB is home in match 2
    assert (aa_after_1 - START_RATING) == -(bb_after_1 - START_RATING)


def test_blowout_moves_rating_more_than_narrow_win():
    narrow = [
        {"home_team": "AA", "away_team": "BB", "home_goals": 1, "away_goals": 0},
        {"home_team": "AA", "away_team": "CC", "home_goals": 0, "away_goals": 0},
    ]
    blowout = [
        {"home_team": "AA", "away_team": "BB", "home_goals": 4, "away_goals": 0},
        {"home_team": "AA", "away_team": "CC", "home_goals": 0, "away_goals": 0},
    ]
    narrow_rating = compute_self_elo(narrow)[1][0]
    blowout_rating = compute_self_elo(blowout)[1][0]
    assert blowout_rating > narrow_rating
