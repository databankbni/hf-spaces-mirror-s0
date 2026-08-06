"""
Critical Files API — GET /api/critical-files
Top Critical Files Dashboard: highest-risk files ranked by combined score.
"""
from fastapi import APIRouter, HTTPException, Query
from agents.critical_files_agent import CriticalFilesAgent
from models.critical_files import CriticalFilesResponse
from services.cache_service import get_cache_service

router = APIRouter()


def _require_ready(session_id: str):
    cache = get_cache_service()
    status = cache.get_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found.")
    if status["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {status.get('error')}")
    if status["status"] != "ready":
        raise HTTPException(status_code=202, detail=f"Still processing ({status['status']}, {status['progress']}%)")


@router.get("/critical-files", response_model=CriticalFilesResponse)
async def get_critical_files(
    session_id: str = Query(..., description="Session ID from /api/ingest"),
    top_n: int = Query(10, ge=1, le=25, description="Number of files to return"),
):
    """
    Return the top N most critical/risky files in the repository.
    """
    _require_ready(session_id)
    agent = CriticalFilesAgent()
    return agent.run(session_id=session_id, top_n=top_n)
