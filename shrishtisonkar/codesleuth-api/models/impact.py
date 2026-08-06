"""
Pydantic models for the Change Impact Analyzer feature.
"""
from typing import Literal
from pydantic import BaseModel


class AffectedFile(BaseModel):
    id: str
    label: str
    reason: str


class ImpactRequest(BaseModel):
    session_id: str
    target: str
    target_type: Literal["file", "module", "node"] = "file"


class ImpactResponse(BaseModel):
    target: str
    target_type: str
    impact_score: float
    summary: str
    affected_files: list[AffectedFile]
    affected_modules: list[str]
    affected_flows: list[str]
    graph_highlights: list[str]
    confidence: float
