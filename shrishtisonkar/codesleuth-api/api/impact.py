"""
Impact API — POST /api/impact
Change Impact Analyzer: blast radius for a file/module/node.
"""
from fastapi import APIRouter, HTTPException
from agents.impact_agent import ImpactAgent
from models.impact import ImpactRequest, ImpactResponse
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


@router.post("/impact", response_model=ImpactResponse)
async def analyze_impact(body: ImpactRequest):
    """
    Compute the change impact (blast radius) for a target file, module, or node.
    """
    _require_ready(body.session_id)
    agent = ImpactAgent()
    return agent.run(
        session_id=body.session_id,
        target=body.target,
        target_type=body.target_type,
    )
