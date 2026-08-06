"""Pydantic models for Critical Files Dashboard."""
from typing import Literal
from pydantic import BaseModel


class CriticalFileItem(BaseModel):
    file_path: str
    file_name: str
    criticality_score: float
    risk_level: Literal["low", "medium", "high", "critical"]
    reasons: list[str]
    risk_categories: list[str]
    impact_score: float


class CriticalFilesResponse(BaseModel):
    session_id: str
    items: list[CriticalFileItem]
