"""
GridMind Retrieval API.

Endpoints:
  POST /retrieve  — retrieve top-K chunks for a compliance question
  POST /answer    — retrieve + LLM synthesis with inline citations
  GET  /health    — liveness probe; exercises the connection pool

Run with:
  uvicorn api.main:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg_pool import ConnectionPool

from ingestion.embed import _get_model
from retrieval.crossref_expand import query_with_expansion
from retrieval.query import query
from retrieval.retrievers import register_vector
from api.llm import LLMUnavailable, synthesize

load_dotenv()

logger = logging.getLogger("gridmind.api")


# ---------------------------------------------------------------------------
# Lifespan — pool + embedder warm-up
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
        open=True,
    )
    _get_model()            # warm the BGE embedder; first request won't pay ~1 s load
    app.state.pool = pool
    yield {"pool": pool}
    pool.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan, title="GridMind Retrieval API")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    k: int = Field(5, ge=1, le=10)
    expand: bool = False


class RetrieveResult(BaseModel):
    rank: int
    chunk_id: str
    standard_id: str
    version: str
    requirement_id: str | None
    page_number: int | None
    score: float
    body: str
    from_crossref: bool = False


class RetrieveResponse(BaseModel):
    question: str
    expand: bool
    count: int
    results: list[RetrieveResult]


class AnswerRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    k: int = Field(5, ge=1, le=8)
    expand: bool = False


class AnswerResponse(BaseModel):
    question: str
    grounded: bool
    answer: str
    sources: list[RetrieveResult]
    usage: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: Request, body: RetrieveRequest) -> RetrieveResponse:
    with request.app.state.pool.connection() as conn:
        register_vector(conn)
        if body.expand:
            raw = query_with_expansion(
                body.question, k=body.k, conn=conn,
                prior_column="obligation_strength_v2",
            )
        else:
            raw = query(
                body.question, k=body.k, conn=conn,
                prior_column="obligation_strength_v2",
            )

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
            from_crossref=r.get("from_crossref", False),
        )
        for r in raw
    ]

    return RetrieveResponse(
        question=body.question,
        expand=body.expand,
        count=len(results),
        results=results,
    )


@app.post("/answer", response_model=AnswerResponse)
def answer(request: Request, body: AnswerRequest) -> AnswerResponse | JSONResponse:
    # Retrieve chunks — pool connection released before the LLM call
    with request.app.state.pool.connection() as conn:
        register_vector(conn)
        if body.expand:
            raw = query_with_expansion(
                body.question, k=body.k, conn=conn,
                prior_column="obligation_strength_v2",
            )
        else:
            raw = query(
                body.question, k=body.k, conn=conn,
                prior_column="obligation_strength_v2",
            )

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
            from_crossref=r.get("from_crossref", False),
        )
        for r in raw
    ]

    # Guard: no retrieval signal → skip LLM entirely
    if not results or results[0].score < 0.015:
        return AnswerResponse(
            question=body.question,
            grounded=False,
            answer="The retrieved standards do not cover this question.",
            sources=[],
            usage={},
        )

    # LLM synthesis — DB connection already released above
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
    try:
        with request.app.state.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "error": str(exc)[:200]},
        )
