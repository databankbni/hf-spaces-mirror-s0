"""
Explain API — GET /api/explain
Powers the File / Module Detail Page with multi-level explanations.
"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query

from agents.explain_agent import ExplainAgent
from services.cache_service import get_cache_service
from models.explain import ExplainResponse

router = APIRouter()


@router.get("/explain", response_model=ExplainResponse)
async def explain_target(
    session_id: str = Query(...),
    target: str = Query(
        ...,
        description=(
            "File path (e.g. 'src/auth.py') or file::function "
            "(e.g. 'src/auth.py::verify_token')"
        ),
    ),
    mode: Literal["intern", "engineer", "architect"] = Query("engineer"),
):
    """
    Return a mode-specific explanation of a file or function for the Detail Page.
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

    agent = ExplainAgent()
    return await agent.run(session_id=session_id, target=target, mode=mode)


@router.get("/explain/files", response_model=list[dict])
async def list_explainable_files(session_id: str = Query(...)):
    """
    Return a list of all files available for explanation.
    Used to populate the file picker on the Detail Page.
    """
    cache = get_cache_service()
    asts = cache.get_asts(session_id)
    if not asts:
        raise HTTPException(status_code=404, detail="Session not found or not ready.")

    return [
        {
            "path": a["path"],
            "language": a["language"],
            "line_count": a.get("line_count", 0),
            "functions": [f["name"] for f in a.get("functions", [])],
            "classes":   [c["name"] for c in a.get("classes",   [])],
        }
        for a in asts
    ]
