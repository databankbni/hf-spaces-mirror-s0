from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Outcome = Literal["home", "draw", "away"]


class MatchRecord(BaseModel):
    match_id: str
    kickoff_date: date
    competition: str
    stage: str
    home_team: str
    away_team: str
    venue: str
    neutral_venue: bool
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    pre_match_home_elo: float
    pre_match_away_elo: float
    lambda_home: float = Field(gt=0)
    lambda_away: float = Field(gt=0)
    context: str
    reveal_notes: str | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.home_team} vs {self.away_team} "
            f"({self.competition}, {self.kickoff_date.year})"
        )

    @property
    def observed_outcome(self) -> Outcome:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals < self.away_goals:
            return "away"
        return "draw"


class Forecast(BaseModel):
    lambda_home: float = Field(gt=0)
    lambda_away: float = Field(gt=0)
    p_home: float = Field(ge=0, le=1)
    p_draw: float = Field(ge=0, le=1)
    p_away: float = Field(ge=0, le=1)
    most_likely_score: str

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> "Forecast":
        if abs(self.p_home + self.p_draw + self.p_away - 1.0) > 1e-8:
            raise ValueError("Forecast probabilities must sum to one.")
        return self


class UserForecast(BaseModel):
    p_home: float = Field(ge=0, le=1)
    p_draw: float = Field(ge=0, le=1)
    p_away: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> "UserForecast":
        if abs(self.p_home + self.p_draw + self.p_away - 1.0) > 1e-6:
            raise ValueError("User probabilities must sum to one.")
        return self
