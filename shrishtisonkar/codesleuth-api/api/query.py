"""
Query API — POST /api/query
Powers the Ask Repo Anything + Graph Highlighting feature.
"""
from fastapi import APIRouter, HTTPException

from agents.query_agent import QueryAgent
from services.cache_service import get_cache_service
from models.query import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_repo(body: QueryRequest):
    """
    Answer a natural language question about the repository.
    Returns the answer, source attributions, and graph node IDs to highlight.
    """
    cache = get_cache_service()
    status = cache.get_status(body.session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found.")
    if status["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {status.get('error')}")
    if status["status"] != "ready":
        raise HTTPException(
            status_code=202,
            detail=f"Still processing ({status['status']}, {status['progress']}%)",
        )

    if not body.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    agent = QueryAgent()
    return await agent.run(body)
