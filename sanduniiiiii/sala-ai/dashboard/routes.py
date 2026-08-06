"""
Sala AI - Admin Dashboard API Routes
Handles wiki/FAQ content uploads (text and PDF) into the wiki vector DB,
exposes API quota usage for Groq / Gemini / OpenRouter,
exposes chat analytics summaries and AI-generated insights,
exposes Google Search brand/competitor monitoring,
and allows re-syncing the product database from WooCommerce.

All endpoints in this router are protected with HTTP Basic Auth (verify_admin).
"""

import os
import logging
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from chatbot.rag import (
    add_wiki_text,
    add_wiki_pdf,
    list_wiki_documents,
    delete_wiki_document,
    refresh_product_db,
)
from chatbot.auth import verify_admin
from core.quota_tracker import get_quota_summary
from analytics.aggregator import get_analytics_summary
from analytics.insights import generate_insights
from analytics.email_digest import send_daily_digest
from data_sources.google_search import monitor_keywords

log = logging.getLogger("SalaAI")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class WikiTextRequest(BaseModel):
    title: str
    content: str
    # When true, this entry is proactively shown to every user the moment
    # they open the chat widget (e.g. "Today's discounted products"),
    # before they ask anything - see chatbot/rag.get_active_announcement().
    is_announcement: bool = False


class WikiUploadResponse(BaseModel):
    status: str
    title: str
    total_chunks: int
    is_announcement: bool = False


class SearchMonitorRequest(BaseModel):
    keywords: list[str]
    results_per_keyword: int = 5


@router.post("/wiki/text", response_model=WikiUploadResponse)
async def upload_wiki_text(request: WikiTextRequest, username: str = Depends(verify_admin)):
    """Add a wiki/FAQ entry from raw text (e.g. from a dashboard text box)."""
    title = request.title.strip()
    content = request.content.strip()

    if not title or not content:
        raise HTTPException(status_code=422, detail="Both title and content are required")

    try:
        count = add_wiki_text(
            title=title, content=content, is_announcement=request.is_announcement
        )
    except Exception as e:
        log.error(f"Wiki text upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return WikiUploadResponse(
        status="success",
        title=title,
        total_chunks=count,
        is_announcement=request.is_announcement,
    )


@router.post("/wiki/pdf", response_model=WikiUploadResponse)
async def upload_wiki_pdf(file: UploadFile = File(...), username: str = Depends(verify_admin)):
    """Add a wiki/FAQ entry from an uploaded PDF file (e.g. product manual)."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported")

    original_name = file.filename
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        count = add_wiki_pdf(tmp_path, display_name=original_name)
    except Exception as e:
        log.error(f"Wiki PDF upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return WikiUploadResponse(status="success", title=original_name, total_chunks=count)


@router.get("/wiki/list")
async def list_wiki_files(username: str = Depends(verify_admin)):
    """List all uploaded wiki documents (grouped by title) with their chunk counts."""
    return {"documents": list_wiki_documents()}


@router.delete("/wiki/{title}")
async def delete_wiki_file(title: str, username: str = Depends(verify_admin)):
    """Delete a specific uploaded wiki document by title/filename."""
    try:
        deleted = delete_wiki_document(title)
    except Exception as e:
        log.error(f"Wiki delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "title": title, "chunks_removed": deleted}


@router.get("/quota")
async def quota_status(username: str = Depends(verify_admin)):
    """Returns today's API usage and remaining quota estimate for each provider."""
    return get_quota_summary()


@router.get("/analytics")
async def analytics_summary(days: int = 7, username: str = Depends(verify_admin)):
    """Returns a chat activity summary for the last `days` days (default 7)."""
    return get_analytics_summary(days=days)


@router.get("/insights")
async def insights(days: int = 7, username: str = Depends(verify_admin)):
    """Returns the analytics summary plus AI-generated actionable suggestions."""
    return generate_insights(days=days)


@router.post("/send-digest")
async def send_digest(days: int = 1, recipient: str | None = None, username: str = Depends(verify_admin)):
    """Manually trigger the daily email digest (also usable via a scheduled cron hit)."""
    result = send_daily_digest(recipient_email=recipient, days=days)
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/search-monitor")
async def search_monitor(request: SearchMonitorRequest, username: str = Depends(verify_admin)):
    """
    Runs Google Search monitoring for the given keywords (brand name,
    product names, competitor names) and returns AI-classified, relevance-
    filtered public mentions.
    """
    if not request.keywords:
        raise HTTPException(status_code=422, detail="At least one keyword is required")

    data = monitor_keywords(
        keywords=request.keywords,
        results_per_keyword=request.results_per_keyword,
    )
    results = data.get("results", [])
    return {"count": len(results), "results": results}


@router.post("/products/resync")
async def resync_products(username: str = Depends(verify_admin)):
    """Re-fetch all products from WooCommerce and rebuild the product vector DB."""
    try:
        store = refresh_product_db()
        if store is None:
            raise HTTPException(status_code=500, detail="No products fetched from WooCommerce")
        count = store._collection.count()
        return {"status": "success", "total_products": count}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Product resync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))