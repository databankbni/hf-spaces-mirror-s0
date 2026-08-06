"""
CodeSleuth AI — FastAPI application entry point.
"""
import os
from contextlib import asynccontextmanager

# Use the OS certificate store for TLS — required on machines whose network
# uses an intercepting proxy cert that Python's bundled CA list doesn't trust.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from utils.logger import get_logger
from api import ingest, overview, graph, flow, risk, query, explain
from api import impact, onboarding, critical_files, where_used

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # Ensure storage directories exist
    for path in [
        settings.storage_path,
        settings.chroma_persist_dir,
        settings.disk_cache_dir,
    ]:
        os.makedirs(path, exist_ok=True)
    logger.info("CodeSleuth AI backend starting up ✓")
    yield
    logger.info("CodeSleuth AI backend shutting down.")


app = FastAPI(
    title="CodeSleuth AI",
    description=(
        "Multi-agent code intelligence platform. "
        "Ingest a GitHub repository and understand it through "
        "dependency visualization, execution flow tracing, "
        "risk detection, and natural language Q&A."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest.router,   prefix="/api", tags=["Ingest"])
app.include_router(overview.router, prefix="/api", tags=["Overview"])
app.include_router(graph.router,    prefix="/api", tags=["Graph"])
app.include_router(flow.router,     prefix="/api", tags=["Flow"])
app.include_router(risk.router,     prefix="/api", tags=["Risk"])
app.include_router(query.router,    prefix="/api", tags=["Query"])
app.include_router(explain.router,       prefix="/api", tags=["Explain"])
app.include_router(impact.router,        prefix="/api", tags=["Impact"])
app.include_router(onboarding.router,    prefix="/api", tags=["Onboarding"])
app.include_router(critical_files.router,prefix="/api", tags=["CriticalFiles"])
app.include_router(where_used.router,    prefix="/api", tags=["WhereUsed"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "CodeSleuth AI", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


def _friendly_error(exc: Exception) -> tuple[int, str]:
    """Map internal exceptions to messages a user can act on — never leak
    raw reprs like 'RetryError[<Future at 0x…>]' into the UI."""
    # tenacity wraps the real failure — unwrap it first
    last = getattr(getattr(exc, "last_attempt", None), "exception", None)
    if callable(last):
        try:
            exc = last() or exc
        except Exception:
            pass
    name = type(exc).__name__
    if name in ("APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout"):
        return 503, ("Could not reach the AI service. Check your internet "
                     "connection / API base URL and try again.")
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return 502, "The AI service rejected the API key. Check OPENAI_API_KEY in backend/.env."
    if name == "RateLimitError":
        return 429, "The AI service rate limit was hit. Wait a moment and retry."
    return 500, f"Internal server error ({name})."


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    status_code, detail = _friendly_error(exc)
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )
    origin = request.headers.get("origin")
    if origin in settings.cors_origins_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
