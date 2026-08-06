from __future__ import annotations

import math

from underdog_lab.forecasting.calibration import apply_temperature
from underdog_lab.forecasting.dixon_coles import (
    DixonColesEloModel,
    rescale_matrix_to_outcomes,
    scoreline_matrix,
)
from underdog_lab.world_cup.models import TournamentFixture, TournamentTeam

# Fit by scripts/fit_elo_dixon_coles.py on 11,094 real matches (2015-01-03 to
# 2026-06-12, eloratings.net) via time-decayed MLE with a 180-day half-life
# -- see models/elo_fit_report.json. The 180-day half-life was selected by
# scripts/upgrade_evaluation.py over the previous 1095-day (3 year) setting:
# it beats the 1095-day fit on mean log loss across 2018-2025 selection
# folds AND on the held-out 2026 confirmation fold, both overall and on the
# neutral-venue subset (models/upgrade_evaluation.json). Walk-forward
# backtested in scripts/backtest_walk_forward.py
# (models/backtest_report.json): beats both the uniform baseline and the
# previous hand-set model on log loss, Brier, and RPS across 2018-2026.
# home_advantage_elo has no effect on World Cup group fixtures, which are
# always neutral_venue=True.
MODEL = DixonColesEloModel(
    intercept=0.15344112308888175,
    elo_scale=0.0020741972184725598,
    home_advantage_elo=65.62880408367505,
    rho=-0.09976156493949083,
)

# Post-hoc temperature scaling (forecasting/calibration.py) selected by
# scripts/recalibration_evaluation.py over the T=1 (no-op) baseline: it beats
# T=1 on mean log loss across 2018-2025 selection folds AND on the held-out
# 2026 confirmation fold, both overall and on the neutral-venue subset
# (models/recalibration_evaluation.json). T<1 sharpens MODEL's forecasts.
CALIBRATION_TEMPERATURE = 0.8857253661047012


def match_forecast(
    fixture: TournamentFixture,
    team_by_name: dict[str, TournamentTeam],
):
    home = team_by_name[fixture.home]
    away = team_by_name[fixture.away]
    forecast = MODEL.forecast(home.rating, away.rating, neutral_venue=True)
    return apply_temperature(forecast, CALIBRATION_TEMPERATURE)


def knockout_advance_probability(
    home: str,
    away: str,
    team_by_name: dict[str, TournamentTeam],
) -> float:
    """Probability that `home` advances from a knockout tie.

    Regulation 1X2 comes from the calibrated Dixon-Coles model; a regulation
    draw is resolved by an Elo-weighted extra-time/penalties split (the same
    rule the tournament simulation uses).
    """
    home_team = team_by_name[home]
    away_team = team_by_name[away]
    forecast = apply_temperature(
        MODEL.forecast(home_team.rating, away_team.rating, neutral_venue=True),
        CALIBRATION_TEMPERATURE,
    )
    elo_probability = 1.0 / (
        1.0 + math.pow(10.0, (away_team.rating - home_team.rating) / 400.0)
    )
    # 0.35 is a stated prior, not a fitted value: favorites convert less of
    # their regulation edge once a tie reaches extra time and penalties
    # (shootouts are close to a coin flip), so the Elo edge is damped rather
    # than applied at full strength. Fitting this on historical knockout
    # resolutions is tracked as post-tournament work.
    draw_resolution = 0.5 + 0.35 * (elo_probability - 0.5)
    return forecast.p_home + forecast.p_draw * draw_resolution


def calibrated_scoreline_matrix(forecast) -> list[list[float]]:
    """Scoreline distribution rescaled to agree with the forecast's 1X2.

    Temperature calibration adjusts p_home/p_draw/p_away after the score
    matrix is built, so the raw Dixon-Coles scorelines no longer sum to the
    displayed outcome probabilities. Rescaling each win/draw/loss region to
    the calibrated mass restores that consistency without disturbing the
    ranking of scorelines within a region.
    """
    matrix = scoreline_matrix(forecast.lambda_home, forecast.lambda_away, MODEL.rho)
    return rescale_matrix_to_outcomes(
        matrix, forecast.p_home, forecast.p_draw, forecast.p_away
    )


def top_scorelines(forecast, limit: int = 3) -> list[tuple[str, float]]:
    matrix = calibrated_scoreline_matrix(forecast)
    scorelines = [
        (f"{i}-{j}", probability)
        for i, row in enumerate(matrix)
        for j, probability in enumerate(row)
    ]
    scorelines.sort(key=lambda item: item[1], reverse=True)
    return scorelines[:limit]
