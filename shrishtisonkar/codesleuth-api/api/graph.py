"""
Graph API — GET /api/graph
Powers the Graph Explorer page.
Supports dependency and call graph types,
and optional graph highlighting via highlighted_nodes query param.
"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query

from agents.graph_agent import GraphAgent
from services.cache_service import get_cache_service
from models.graph import GraphResponse

router = APIRouter()


def _require_ready(session_id: str):
    cache = get_cache_service()
    status = cache.get_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found.")
    if status["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {status.get('error')}")
    if status["status"] != "ready":
        raise HTTPException(
            status_code=202,
            detail=f"Still processing ({status['status']}, {status['progress']}%)",
        )


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    session_id: str = Query(...),
    graph_type: Literal["dependency", "call"] = Query("dependency"),
    highlighted_nodes: str = Query(
        "",
        description="Comma-separated list of node IDs to highlight (from /api/query response)"
    ),
):
    """
    Return the dependency or call graph for the Graph Explorer.
    Pass highlighted_nodes from a previous /api/query result to show highlights.
    """
    _require_ready(session_id)

    highlights = [n.strip() for n in highlighted_nodes.split(",") if n.strip()]

    agent = GraphAgent()
    return agent.build_response(
        session_id=session_id,
        graph_type=graph_type,
        highlighted_nodes=highlights,
    )
