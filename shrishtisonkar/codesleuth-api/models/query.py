from typing import Literal
from pydantic import BaseModel


class QueryRequest(BaseModel):
    session_id: str
    question: str
    mode: Literal["intern", "engineer", "architect"] = "engineer"
    max_context_chunks: int = 5


class SourceChunk(BaseModel):
    file_path: str
    content_snippet: str
    relevance_score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    highlighted_nodes: list[str]   # node IDs to highlight in Graph Explorer
    confidence: float              # 0.0–1.0
    mode: str
    tokens_used: int | None = None
