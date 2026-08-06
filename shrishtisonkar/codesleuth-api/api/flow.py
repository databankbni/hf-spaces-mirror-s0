"""
Flow API — GET /api/flow
Powers the Execution Flow Visualizer page.
"""
from fastapi import APIRouter, HTTPException, Query

from agents.flow_agent import FlowAgent
from services.cache_service import get_cache_service
from models.flow import FlowResponse

router = APIRouter()


@router.get("/flow", response_model=FlowResponse)
async def get_flow(
    session_id: str = Query(...),
    entry_point: str = Query(
        "main",
        description=(
            "Entry point to trace. Can be a file path (e.g. 'src/app.py'), "
            "a function name (e.g. 'main'), or a combined 'file.py::function_name'."
        ),
    ),
):
    """
    Trace execution flow from a given entry point.
    Returns an ordered graph of function calls for the Flow Visualizer.
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

    agent = FlowAgent()
    return await agent.run(session_id=session_id, entry_point=entry_point)


@router.get("/flow/entry-points", response_model=list[str])
async def list_entry_points(session_id: str = Query(...)):
    """Return detected entry points for the repository (for the dropdown selector)."""
    cache = get_cache_service()
    overview = cache.get_overview(session_id)
    if not overview:
        raise HTTPException(status_code=404, detail="Session not found or not ready.")
    return overview.get("entry_points", [])
