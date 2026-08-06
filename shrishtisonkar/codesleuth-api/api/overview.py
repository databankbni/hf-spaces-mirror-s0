"""
Overview API — GET /api/overview
Powers the Overview Dashboard page.
"""
from fastapi import APIRouter, HTTPException, Query
from services.cache_service import get_cache_service
from models.overview import OverviewResponse

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(session_id: str = Query(..., description="Session ID from /api/ingest")):
    """Return full repository metadata for the Overview Dashboard."""
    cache = get_cache_service()

    # Guard: session must be ready
    status = cache.get_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found.")
    if status["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {status.get('error')}")
    if status["status"] != "ready":
        raise HTTPException(
            status_code=202,
            detail=f"Repository still being processed. Status: {status['status']} ({status['progress']}%)",
        )

    overview = cache.get_overview(session_id)
    if not overview:
        raise HTTPException(status_code=404, detail="Overview data not found. Try re-ingesting.")

    return OverviewResponse(**overview)
