import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.byok import router as byok_router
from app.api.routes.health import router as health_router
from app.api.routes.query import router as query_router
from app.curriculum.api.routes import router as curriculum_router
from app.ingestion_studio.api.routes import router as ingestion_studio_router
from app.platform.config import get_settings
from app.platform.logging import configure_logging
from app.platform.middleware import BodySizeLimitMiddleware, IPRateLimitMiddleware
from app.platform.observability.access_log import AccessLoggingMiddleware
from app.platform.observability.correlation import RequestCorrelationMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Load the BGE-M3 model at startup so the first query has no cold-start delay."""
    try:
        from app.platform.embeddings import get_bge_m3_embedder
        logger.info("Pre-warming BGE-M3 embedding model…")
        get_bge_m3_embedder()
        logger.info("BGE-M3 model ready.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not pre-warm embedder: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.dim_debug)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=app_lifespan,
    )

    # Outermost: rate limiting (runs before any other processing)
    app.add_middleware(IPRateLimitMiddleware, requests_per_minute=settings.rate_limit_requests_per_minute)
    # Body size guard — rejects oversized payloads before route handlers read them
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    # Observability Middlewares
    app.add_middleware(AccessLoggingMiddleware)
    app.add_middleware(RequestCorrelationMiddleware)
    # CORS — origins come from config so production/HF Spaces env can override
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(byok_router)
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(curriculum_router)
    
    if settings.enable_ingestion_studio and settings.environment != "production":
        app.include_router(ingestion_studio_router)

    return app


app = create_app()
