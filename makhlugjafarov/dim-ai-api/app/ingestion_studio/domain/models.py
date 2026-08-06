from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal[
    "created",
    "profiling",
    "awaiting_confirmation",
    "extracting",
    "needs_gpu_artifact",
    "segmenting",
    "chunking",
    "embedding",
    "loading",
    "completed",
    "blocked",
    "failed"
]

class StageProgress(BaseModel):
    status: Literal["queued", "running", "done", "failed"]
    pct: float
    detail: str
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None

class JobStats(BaseModel):
    pages: int = 0
    blocks: int = 0
    sections: int = 0
    chunks: int = 0
    embedded: int = 0

class IngestionJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    filename: str
    content_hash: str
    status: JobStatus
    profile: dict | None = None
    overrides: dict | None = None
    stage_progress: dict[str, StageProgress] = Field(default_factory=dict)
    readiness: dict | None = None  # SourceReadiness verdict + metrics (GRO-129)
    stats: JobStats | None = None
    error: str | None = None
    document_id: str | None = None
    created_at: datetime
    updated_at: datetime
