"""
Risk API — GET /api/risk
Powers the Risk Intelligence page.
"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query

from services.cache_service import get_cache_service
from models.risk import RiskResponse

router = APIRouter()


@router.get("/risk", response_model=RiskResponse)
async def get_risk(
    session_id: str = Query(...),
    category: str = Query(
        "",
        description="Filter by category (optional). E.g. 'hardcoded_secret,circular_dependency'",
    ),
    min_severity: Literal["low", "medium", "high", "critical"] = Query("low"),
):
    """
    Return all detected risks for the Risk Intelligence page.
    Supports filtering by category and minimum severity.
    """
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

    risk_data = cache.get_risk(session_id)
    if not risk_data:
        raise HTTPException(status_code=404, detail="Risk data not found. Try re-ingesting.")

    risk = RiskResponse(**risk_data)

    # Apply filters
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    min_rank = severity_rank.get(min_severity, 0)
    categories = [c.strip() for c in category.split(",") if c.strip()]

    filtered_items = [
        item for item in risk.items
        if severity_rank.get(item.severity, 0) >= min_rank
        and (not categories or item.category in categories)
    ]

    risk.items = filtered_items
    risk.total_risks = len(filtered_items)
    return risk
