"""
Where-Used API — POST /api/where-used
Find Where Used: incoming references for any file, module, or function.
"""
from fastapi import APIRouter, HTTPException
from agents.where_used_agent import WhereUsedAgent
from models.where_used import WhereUsedRequest, WhereUsedResponse
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


@router.post("/where-used", response_model=WhereUsedResponse)
async def where_used(body: WhereUsedRequest):
    """
    Find all files/modules that import or call the given target.
    """
    _require_ready(body.session_id)
    agent = WhereUsedAgent()
    return agent.run(
        session_id=body.session_id,
        target=body.target,
        target_type=body.target_type,
    )
