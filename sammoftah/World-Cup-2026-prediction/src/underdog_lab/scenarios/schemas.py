from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from underdog_lab.scenarios.taxonomy import FactorType


TeamSide = Literal["home", "away", "both", "unknown"]


class ExtractedFactor(BaseModel):
    factor_type: FactorType
    team: TeamSide
    severity: float = Field(ge=0.0, le=1.0)
    certainty: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=240)


class ScenarioExtraction(BaseModel):
    factors: list[ExtractedFactor] = Field(default_factory=list, max_length=6)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=6)
    ambiguities: list[str] = Field(default_factory=list, max_length=6)


class AppliedAdjustment(BaseModel):
    factor: ExtractedFactor
    applied: bool
    explanation: str
    home_multiplier: float = 1.0
    away_multiplier: float = 1.0


class AdjustmentResult(BaseModel):
    lambda_home: float = Field(gt=0)
    lambda_away: float = Field(gt=0)
    adjustments: list[AppliedAdjustment]
