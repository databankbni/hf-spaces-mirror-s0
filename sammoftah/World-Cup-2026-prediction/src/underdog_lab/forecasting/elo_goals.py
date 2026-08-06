from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EloGoalModel:
    """Maps pre-match Elo ratings to independent Poisson scoring rates.

    The coefficients are deliberately explicit. They can be fitted by
    scripts/prepare_matches.py on historical results while excluding the
    challenge set. The checked-in defaults are plausible bootstrap values,
    not claimed as a market-calibrated model.
    """

    intercept: float = math.log(1.18)
    elo_scale: float = 0.00175
    home_advantage_elo: float = 70.0
    neutral_home_multiplier: float = 1.0

    def lambdas(
        self,
        home_elo: float,
        away_elo: float,
        *,
        neutral_venue: bool,
    ) -> tuple[float, float]:
        home_edge = 0.0 if neutral_venue else self.home_advantage_elo
        effective_diff = home_elo + home_edge - away_elo
        lambda_home = math.exp(self.intercept + self.elo_scale * effective_diff)
        lambda_away = math.exp(self.intercept - self.elo_scale * effective_diff)
        if neutral_venue:
            lambda_home *= self.neutral_home_multiplier
        return self._clamp(lambda_home), self._clamp(lambda_away)

    @staticmethod
    def _clamp(value: float) -> float:
        return min(4.0, max(0.15, value))
