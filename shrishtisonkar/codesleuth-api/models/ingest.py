from typing import Literal
from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    token: str | None = None  # optional GitHub PAT


class IngestResponse(BaseModel):
    session_id: str
    message: str


class IngestStatusResponse(BaseModel):
    session_id: str
    status: Literal["queued", "cloning", "parsing", "indexing", "building_graph",
                    "detecting_risks", "ready", "error"]
    progress: int  # 0–100
    error: str | None = None
    repo_name: str | None = None
    language_breakdown: dict[str, float] | None = None
    total_files: int | None = None
    total_lines: int | None = None
