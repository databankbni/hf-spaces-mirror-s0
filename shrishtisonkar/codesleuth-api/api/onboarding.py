"""
Onboarding API — GET /api/onboarding
New Developer Onboarding Mode: beginner-friendly repo guide.
"""
from fastapi import APIRouter, HTTPException, Query
from agents.onboarding_agent import OnboardingAgent
from models.onboarding import OnboardingResponse
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


@router.get("/onboarding", response_model=OnboardingResponse)
async def get_onboarding(session_id: str = Query(..., description="Session ID from /api/ingest")):
    """
    Generate a beginner-friendly onboarding guide for the analysed repository.
    """
    _require_ready(session_id)
    agent = OnboardingAgent()
    return agent.run(session_id=session_id)
