from typing import Literal
from pydantic import BaseModel


class RiskItem(BaseModel):
    id: str
    category: Literal[
        "circular_dependency",
        "hardcoded_secret",
        "oversized_file",
        "tight_coupling",
        "single_point_of_failure",
        "dead_code",
        "missing_error_handling",
        "high_complexity",
    ]
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    description: str
    affected_files: list[str]
    suggestion: str
    line_numbers: list[int] | None = None
    metric_value: float | None = None  # e.g. betweenness centrality score


class RiskSummary(BaseModel):
    critical: int
    high: int
    medium: int
    low: int


class RiskResponse(BaseModel):
    session_id: str
    total_risks: int
    risk_score: float          # 0.0 = clean, 10.0 = worst
    summary: RiskSummary
    items: list[RiskItem]
    scanned_files: int
    secret_pattern_matches: int
