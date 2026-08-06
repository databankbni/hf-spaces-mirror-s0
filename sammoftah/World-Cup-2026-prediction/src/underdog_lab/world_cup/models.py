from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TournamentTeam(BaseModel):
    group: str
    position: int
    team: str
    rank: int
    elo: float
    host: bool = False

    @property
    def rating(self) -> float:
        return self.elo


class TournamentFixture(BaseModel):
    fixture_id: str
    group: str
    matchday: int
    date: date
    kickoff_utc: datetime | None = None
    home: str
    away: str
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)

    @property
    def played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


class KnockoutFixture(BaseModel):
    fixture_id: str
    match_number: int = Field(ge=73, le=104)
    stage: str
    date: date
    kickoff_utc: datetime | None = None
    home: str
    away: str
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)
    winner: str | None = None
    provider_match_id: str | None = None
    provider_status: str | None = None

    @property
    def played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    @property
    def resolved(self) -> bool:
        return self.home not in {"TBD", "Semifinal 2 Winner", "Semifinal 2 Loser"} and self.away not in {
            "TBD",
            "Semifinal 2 Winner",
            "Semifinal 2 Loser",
        }


class Standing(BaseModel):
    team: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against
