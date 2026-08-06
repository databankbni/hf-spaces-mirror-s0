from typing import Literal
from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str                   # unique — usually relative file path or "file::function"
    label: str                # display name
    type: Literal["file", "function", "class", "module", "external"]
    language: str
    lines: int = 0
    complexity: float = 0.0   # cyclomatic complexity if calculated
    highlighted: bool = False  # set true by query agent results
    x: float | None = None    # optional layout hint
    y: float | None = None
    # ── Heatmap / risk metadata ──────────────────────────────────────────────
    risk_level: Literal["safe", "low", "medium", "high", "critical"] = "safe"
    criticality_score: float = 0.0
    heat_score: float = 0.0   # normalised 0–1
    risk_categories: list[str] = []


class GraphEdge(BaseModel):
    id: str                   # "source→target"
    source: str
    target: str
    type: Literal["imports", "calls", "extends", "implements", "uses", "exports"]
    weight: float = 1.0
    label: str | None = None


class GraphResponse(BaseModel):
    session_id: str
    graph_type: Literal["dependency", "call"]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: dict[str, int]     # {"nodes": N, "edges": M, "components": K}
