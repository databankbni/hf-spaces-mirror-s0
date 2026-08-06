from __future__ import annotations

import math

from underdog_lab.config import MAX_SCORE
from underdog_lab.domain import Forecast


def poisson_probability(goals: int, rate: float) -> float:
    return math.exp(-rate) * (rate**goals) / math.factorial(goals)


def forecast_from_lambdas(
    lambda_home: float,
    lambda_away: float,
    max_score: int = MAX_SCORE,
) -> Forecast:
    home = [poisson_probability(i, lambda_home) for i in range(max_score + 1)]
    away = [poisson_probability(i, lambda_away) for i in range(max_score + 1)]
    matrix = [[h * a for a in away] for h in home]
    total = sum(sum(row) for row in matrix)

    p_home = sum(
        matrix[i][j]
        for i in range(max_score + 1)
        for j in range(max_score + 1)
        if i > j
    )
    p_draw = sum(matrix[i][i] for i in range(max_score + 1))
    p_away = total - p_home - p_draw

    dominant = max(("home", "draw", "away"), key={"home": p_home, "draw": p_draw, "away": p_away}.get)

    def outcome(home_goals: int, away_goals: int) -> str:
        if home_goals > away_goals:
            return "home"
        if home_goals < away_goals:
            return "away"
        return "draw"

    best_i, best_j = max(
        (
            (i, j)
            for i in range(max_score + 1)
            for j in range(max_score + 1)
            if outcome(i, j) == dominant
        ),
        key=lambda score: matrix[score[0]][score[1]],
    )

    return Forecast(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        p_home=p_home / total,
        p_draw=p_draw / total,
        p_away=p_away / total,
        most_likely_score=f"{best_i}-{best_j}",
    )
