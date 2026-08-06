"""
GridMind Space App — embedded (database-free) FastAPI service for Hugging Face Spaces.

Mirrors api/main.py endpoints and response contracts exactly, backed by
EmbeddedRetriever instead of Postgres.  Pydantic models and the LLM layer are
imported from the main API to keep the contract in one place.

Endpoints:
  GET  /          — browser UI (serving/static/index.html)
  GET  /info      — service description JSON
  POST /retrieve  — retrieve top-K chunks (BM25 + dense, no Postgres)
  POST /answer    — retrieve + LLM synthesis with inline citations
  GET  /health    — liveness probe; confirms chunk count == 96
"""

from __future__ import annotations

import collections
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from api.llm import LLMUnavailable, synthesize
# Shared request/response models — imported so the API contract stays in one place.
from api.main import (
    AnswerRequest,
    AnswerResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrieveResult,
)
from ingestion.embed import _get_model
from serving.embedded_retriever import EmbeddedRetriever

load_dotenv()

logger = logging.getLogger("gridmind.space")

_EXPECTED_CHUNKS = 96
_STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Rate limiter — per-IP, in-memory, no dependencies
# ---------------------------------------------------------------------------
_RATE_LIMIT_REQUESTS = 10
_RATE_LIMIT_WINDOW   = 60   # seconds (rolling)
_rate_store: dict[str, collections.deque] = {}


def _client_ip(request: Request) -> str:
    """Prefer X-Forwarded-For (HF proxy sets this) over socket address."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str) -> bool:
    """Return True and do NOT record the request if the limit is exceeded."""
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW
    if ip not in _rate_store:
        _rate_store[ip] = collections.deque()
    dq = _rate_store[ip]
    while dq and dq[0] < cutoff:      # prune timestamps outside the window
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_REQUESTS:
        return True
    dq.append(now)
    return False


# ---------------------------------------------------------------------------
# Lifespan — retriever + embedder warm-up
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [v for v in ("GEMINI_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    retriever = EmbeddedRetriever(prior_column="obligation_strength_v2")
    _get_model()   # warm the BGE embedder so the first request doesn't pay ~1 s load
    app.state.retriever = retriever
    yield
    # EmbeddedRetriever holds no external connections; nothing to close.


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan, title="GridMind Space API")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")


@app.get("/info")
def info():
    return {
        "name": "GridMind",
        "description": (
            "Energy compliance RAG over NERC CIP standards. "
            "Plain-English question in; cited, version-aware answer out."
        ),
        "endpoints": {
            "POST /retrieve": "Return top-K relevant chunks for a compliance question.",
            "POST /answer":   "Retrieve + LLM synthesis with inline chunk citations.",
            "GET  /health":   "Liveness probe.",
        },
        "note": (
            "/answer calls an external LLM and may take a moment on first use after "
            "a free-tier cold start."
        ),
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: Request, body: RetrieveRequest) -> RetrieveResponse:
    # `expand` (cross-reference expansion) requires Postgres and is not available
    # in the embedded path; the field is accepted for model compatibility but ignored.
    retriever: EmbeddedRetriever = request.app.state.retriever
    raw = retriever.query(body.question, k=body.k)

    results = [
        RetrieveResult(
            rank=r["rank"],
            chunk_id=r["_chunk_id"],
            standard_id=r["standard_id"],
            version=str(r["version"]),
            requirement_id=r.get("requirement_id"),
            page_number=r.get("page_number"),
            score=r["score"],
            body=r["body"],
            from_crossref=False,
        )
        for r in raw
    ]

    return RetrieveResponse(
        question=body.question,
        expand=False,
        count=len(results),
        results=results,
    )


@app.post("/answer", response_model=AnswerResponse)
def answer(request: Request, body: AnswerRequest) -> AnswerResponse | JSONResponse:
    if _is_rate_limited(_client_ip(request)):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded — try again in a minute."},
        )

    retriever: EmbeddedRetriever = request.app.state.retriever
    # Retrieval is in-process (no DB connection to release), but we still
    # finish it before calling synthesize() to keep the structure clear.
    raw = retriever.query(body.question, k=body.k)

    results = [
        RetrieveResult(
            rank=r["rank"],
            chunk_id=r["_chunk_id"],
            standard_id=r["standard_id"],
            version=str(r["version"]),
            requirement_id=r.get("requirement_id"),
            page_number=r.get("page_number"),
            score=r["score"],
            body=r["body"],
            from_crossref=False,
        )
        for r in raw
    ]

    # Guard: no retrieval signal → skip LLM entirely
    # calibrated for embedded-backend RRF score scale; real-question top-1 scores observed >= 0.0225, garbage <= 0.0205, n=8
    if not results or results[0].score < 0.021:
        return AnswerResponse(
            question=body.question,
            grounded=False,
            answer="The retrieved standards do not cover this question.",
            sources=[],
            usage={},
        )

    chunks_for_llm = [r.model_dump() for r in results]
    try:
        llm_result = synthesize(body.question, chunks_for_llm)
    except LLMUnavailable as exc:
        logger.warning("LLM synthesis failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "LLM backend unavailable"},
        )

    return AnswerResponse(
        question=body.question,
        grounded=True,
        answer=llm_result["answer"],
        sources=results,
        usage=llm_result["usage"],
    )


@app.get("/health")
def health(request: Request):
    retriever: EmbeddedRetriever = request.app.state.retriever
    n = len(retriever._chunk_ids)
    if n == _EXPECTED_CHUNKS:
        return {"status": "ok", "chunks": n}
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "chunks": n, "expected": _EXPECTED_CHUNKS},
    )
