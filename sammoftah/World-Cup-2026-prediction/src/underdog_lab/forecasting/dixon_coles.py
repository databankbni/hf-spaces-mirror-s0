from __future__ import annotations

import math
from dataclasses import dataclass

from underdog_lab.config import MAX_SCORE
from underdog_lab.domain import Forecast
from underdog_lab.forecasting.elo_goals import EloGoalModel
from underdog_lab.forecasting.poisson import poisson_probability


def dc_tau(home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    """Dixon-Coles (1997) low-score correlation correction.

    Adjusts the independent-Poisson joint probability for the four
    lowest-scoring outcomes, where draws and 1-0/0-1 results are
    systematically more (or less) common than independence implies.
    """
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def match_probability(home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    tau = dc_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
    return tau * poisson_probability(home_goals, lambda_home) * poisson_probability(away_goals, lambda_away)


def scoreline_matrix(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_score: int = MAX_SCORE,
) -> list[list[float]]:
    """Joint scoreline distribution, normalized over the truncated score grid."""
    matrix = [
        [max(0.0, match_probability(i, j, lambda_home, lambda_away, rho)) for j in range(max_score + 1)]
        for i in range(max_score + 1)
    ]
    total = sum(sum(row) for row in matrix) or 1.0
    return [[cell / total for cell in row] for row in matrix]


def rescale_matrix_to_outcomes(
    matrix: list[list[float]],
    p_home: float,
    p_draw: float,
    p_away: float,
) -> list[list[float]]:
    """Rescale a scoreline matrix so its win/draw/loss regions sum to the
    given outcome probabilities. Keeps within-region scoreline ratios intact,
    which lets a post-hoc calibrated 1X2 forecast stay consistent with the
    scoreline distribution shown next to it."""
    size = len(matrix)
    raw = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for i in range(size):
        for j in range(size):
            region = "home" if i > j else "draw" if i == j else "away"
            raw[region] += matrix[i][j]
    target = {"home": p_home, "draw": p_draw, "away": p_away}
    return [
        [
            matrix[i][j]
            * (
                target["home" if i > j else "draw" if i == j else "away"]
                / (raw["home" if i > j else "draw" if i == j else "away"] or 1.0)
            )
            for j in range(size)
        ]
        for i in range(size)
    ]


def forecast_from_lambdas_dc(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_score: int = MAX_SCORE,
) -> Forecast:
    matrix = scoreline_matrix(lambda_home, lambda_away, rho, max_score)

    p_home = sum(
        matrix[i][j]
        for i in range(max_score + 1)
        for j in range(max_score + 1)
        if i > j
    )
    p_draw = sum(matrix[i][i] for i in range(max_score + 1))
    p_away = 1.0 - p_home - p_draw

    best_i, best_j = max(
        (
            (i, j)
            for i in range(max_score + 1)
            for j in range(max_score + 1)
        ),
        key=lambda score: matrix[score[0]][score[1]],
    )

    return Forecast(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        most_likely_score=f"{best_i}-{best_j}",
    )


def top_scorelines_dc(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    *,
    max_score: int = MAX_SCORE,
    limit: int = 3,
) -> list[tuple[str, float]]:
    matrix = scoreline_matrix(lambda_home, lambda_away, rho, max_score)
    scorelines = [
        (f"{i}-{j}", matrix[i][j])
        for i in range(max_score + 1)
        for j in range(max_score + 1)
    ]
    scorelines.sort(key=lambda item: item[1], reverse=True)
    return scorelines[:limit]


@dataclass(frozen=True)
class DixonColesEloModel(EloGoalModel):
    """EloGoalModel plus a Dixon-Coles low-score correlation term."""

    rho: float = 0.0

    def match_log_likelihood(
        self,
        home_goals: int,
        away_goals: int,
        home_elo: float,
        away_elo: float,
        *,
        neutral_venue: bool,
    ) -> float:
        lambda_home, lambda_away = self.lambdas(home_elo, away_elo, neutral_venue=neutral_venue)
        probability = match_probability(home_goals, away_goals, lambda_home, lambda_away, self.rho)
        return math.log(max(probability, 1e-12))

    def forecast(self, home_elo: float, away_elo: float, *, neutral_venue: bool) -> Forecast:
        lambda_home, lambda_away = self.lambdas(home_elo, away_elo, neutral_venue=neutral_venue)
        return forecast_from_lambdas_dc(lambda_home, lambda_away, self.rho)
