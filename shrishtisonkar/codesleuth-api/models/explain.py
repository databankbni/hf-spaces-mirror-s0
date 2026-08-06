from typing import Literal
from pydantic import BaseModel


class ExplainResponse(BaseModel):
    session_id: str
    target: str                    # file path or "file::function_name"
    mode: Literal["intern", "engineer", "architect"]
    title: str
    summary: str                   # short 1-sentence summary
    explanation: str               # full multi-paragraph explanation
    key_concepts: list[str]        # bullet points for intern / engineer
    dependencies: list[str]        # files this target imports
    dependents: list[str]          # files that import this target
    complexity_score: float
    line_count: int
    language: str
