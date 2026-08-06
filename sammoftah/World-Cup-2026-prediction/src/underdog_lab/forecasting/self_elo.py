from __future__ import annotations

"""A second, independently-computed strength rating.

``home_elo``/``away_elo`` in ``data/historical/matches.csv`` come from
eloratings.net. This module computes a second rating from scratch using only
the match results in that same file: a fixed K-factor, the classic
World Football Elo goal-difference multiplier, and a neutral starting rating
for every team. The algorithm, K-factor, and starting point are all
independent of eloratings.net's methodology, so the resulting rating is a
genuinely different signal -- not a copy with different formatting.

Used by scripts/backtest_walk_forward.py to fit a second Dixon-Coles model
and ensemble it (log-odds blend, see ``ensemble.py``) with the
eloratings.net-based model.
"""

START_RATING = 1500.0
K_FACTOR = 20.0


def _goal_diff_multiplier(goal_diff: int) -> float:
    """Classic World Football Elo multiplier for the margin of victory."""
    if goal_diff <= 1:
        return 1.0
    if goal_diff == 2:
        return 1.5
    return (11 + goal_diff) / 8


def compute_self_elo(matches: list[dict]) -> list[tuple[float, float]]:
    """Return pre-match (home_self_elo, away_self_elo) for each match.

    ``matches`` must be in chronological order. Each entry depends only on
    matches earlier in the list, so it is safe to use directly as a
    walk-forward feature with no lookahead.
    """
    ratings: dict[str, float] = {}
    pre_match: list[tuple[float, float]] = []
    for match in matches:
        home = match["home_team"]
        away = match["away_team"]
        home_rating = ratings.get(home, START_RATING)
        away_rating = ratings.get(away, START_RATING)
        pre_match.append((home_rating, away_rating))

        home_goals = match["home_goals"]
        away_goals = match["away_goals"]
        if home_goals > away_goals:
            actual_home = 1.0
        elif home_goals == away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0

        expected_home = 1.0 / (1.0 + 10 ** ((away_rating - home_rating) / 400.0))
        multiplier = _goal_diff_multiplier(abs(home_goals - away_goals))
        delta = K_FACTOR * multiplier * (actual_home - expected_home)
        ratings[home] = home_rating + delta
        ratings[away] = away_rating - delta
    return pre_match
