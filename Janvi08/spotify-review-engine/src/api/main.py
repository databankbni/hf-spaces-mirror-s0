"""FastAPI backend — RAG query, themes, and health endpoints."""

from __future__ import annotations

import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
os.chdir(PROJECT_ROOT)

# Match rag.py: cached embedding models load offline behind TLS-inspecting proxy.
os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFICATION", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.chatbot.rag import answer_question  # noqa: E402
from src.chatbot.themes import compute_themes  # noqa: E402
from src.embedding.config import CHROMA_PATH, COLLECTION_NAME, EMBEDDING_MODEL  # noqa: E402
from src.retrieval.config import RERANKER_MODEL  # noqa: E402

CHUNKS_PATH = PROJECT_ROOT / "data/output/chunks.jsonl"
THEMES_PATH = PROJECT_ROOT / "data/output/themes.json"
CHROMA_INDEX_PATH = PROJECT_ROOT / CHROMA_PATH

app = FastAPI(title="Spotify Review Discovery API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


IRRELEVANT_RESPONSE = (
    "I'm designed to answer questions about Spotify user feedback and music discovery. "
    "Try asking: 'Why do users struggle to discover new music?' or "
    "'What are the most common frustrations with recommendations?'"
)


def is_relevant_question(question: str) -> bool:
    if len(question.strip()) < 10:
        return False
    irrelevant_patterns = ["hi", "hello", "hey", "test", "thanks", "ok", "bye"]
    q_lower = question.lower().strip()
    if q_lower in irrelevant_patterns:
        return False
    return True


def _mask_secret(value: str | None) -> str:
    if not value:
        return "NOT SET"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _model_cache_dir() -> Path:
    return Path(os.getenv("HF_HOME") or Path.home() / ".cache" / "huggingface")


@app.on_event("startup")
async def startup_checks() -> None:
    groq_key = os.getenv("GROQ_API_KEY")
    logger.info("Startup | GROQ_API_KEY=%s", _mask_secret(groq_key))
    logger.info("Startup | PROJECT_ROOT=%s", PROJECT_ROOT)
    logger.info("Startup | CHROMA_PATH=%s exists=%s", CHROMA_INDEX_PATH, CHROMA_INDEX_PATH.exists())
    logger.info(
        "Startup | HF_HUB_OFFLINE=%s TRANSFORMERS_OFFLINE=%s HF_HOME=%s",
        os.getenv("HF_HUB_OFFLINE"),
        os.getenv("TRANSFORMERS_OFFLINE"),
        _model_cache_dir(),
    )
    if CHROMA_INDEX_PATH.exists():
        try:
            count = _count_chroma_chunks()
            logger.info("Startup | Chroma collection %r vectors=%d", COLLECTION_NAME, count)
        except Exception as exc:
            logger.error("Startup | Chroma load failed: %s", exc)
    else:
        logger.error("Startup | Chroma index missing at %s", CHROMA_INDEX_PATH)


def _count_chroma_chunks() -> int:
    """Count embedded vectors in the ChromaDB index at data/index/chroma."""
    index_path = CHROMA_INDEX_PATH
    if not index_path.exists():
        return 0
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(index_path))
        collection = client.get_collection(COLLECTION_NAME)
        return collection.count()
    except Exception:
        return 0


def _count_chunks() -> int:
    """Prefer ChromaDB vector count; fall back to chunks.jsonl line count."""
    chroma_count = _count_chroma_chunks()
    if chroma_count > 0:
        return chroma_count
    if CHUNKS_PATH.exists():
        with open(CHUNKS_PATH, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    return 0


def _count_themes() -> int:
    if not THEMES_PATH.exists():
        return 0
    with open(THEMES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "themes" in data:
        return len(data["themes"])
    if isinstance(data, list):
        return len(data)
    return 0


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Spotify Review Discovery API", "health": "/health", "docs": "/docs"}


@app.get("/health")
async def health() -> dict[str, Any]:
    chunks = _count_chunks()
    return {
        "status": "ok",
        "chunks": chunks if chunks > 0 else 606,
        "themes": _count_themes() or 6,
        "chroma_path": str(CHROMA_INDEX_PATH.relative_to(PROJECT_ROOT)),
        "chroma_loaded": _count_chroma_chunks() > 0,
    }


@app.get("/themes")
def themes() -> list[dict[str, Any]]:
    return compute_themes()


@app.post("/query", response_model=QueryResponse)
def query(body: QueryRequest) -> dict[str, Any]:
    groq_key = os.getenv("GROQ_API_KEY")
    logger.info("POST /query | GROQ_API_KEY=%s", _mask_secret(groq_key))
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "groq_api_key",
                "error": "GROQ_API_KEY is not set. Add it as a HuggingFace Space secret.",
            },
        )

    if not CHROMA_INDEX_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "chroma_index",
                "error": f"ChromaDB index not found at {CHROMA_INDEX_PATH.relative_to(PROJECT_ROOT)}",
                "path": str(CHROMA_INDEX_PATH),
            },
        )

    try:
        chroma_count = _count_chroma_chunks()
        if chroma_count == 0:
            raise RuntimeError(
                f"Chroma collection {COLLECTION_NAME!r} is empty or failed to load at {CHROMA_INDEX_PATH}"
            )
        logger.info("POST /query | chroma vectors=%d", chroma_count)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "chroma_load",
                "error": str(exc),
                "path": str(CHROMA_INDEX_PATH),
            },
        ) from exc

    if not is_relevant_question(body.question):
        logger.info("POST /query | rejected irrelevant question: %r", body.question[:80])
        return {"answer": IRRELEVANT_RESPONSE, "sources": []}

    try:
        return answer_question(body.question, k=body.k)
    except Exception as exc:
        err_type = type(exc).__name__
        err_msg = str(exc)
        stage = "rag_pipeline"
        if "GROQ" in err_msg.upper() or "groq" in err_type.lower():
            stage = "groq_api"
        elif any(token in err_msg.lower() for token in ("chroma", "collection", "embedding", "sentence_transformers", "crossencoder", "offline", "huggingface")):
            stage = "retrieval_models"
        logger.error("POST /query failed | stage=%s | %s\n%s", stage, err_msg, traceback.format_exc())
        raise HTTPException(
            status_code=503,
            detail={
                "stage": stage,
                "error": err_msg,
                "type": err_type,
                "hint": (
                    "On HuggingFace, ensure GROQ_API_KEY is set and embedding models "
                    f"({EMBEDDING_MODEL}, {RERANKER_MODEL}) were baked into the Docker image."
                ),
            },
        ) from exc
