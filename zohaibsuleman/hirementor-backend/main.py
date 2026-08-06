import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import SERVER_HOST, SERVER_PORT, CORS_ORIGINS
from api.cv import router as cv_router
from api.interview import router as interview_router
from api.recommendations import router as recommendations_router
from api.skill_match import router as skill_router
from api.cover_letter import router as cover_letter_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SPB Backend starting up...")
    from core.gemini import gemini
    if gemini.is_available():
        logger.info("Gemini AI client configured (model: %s)", gemini.model)
    else:
        logger.warning("GEMINI_API_KEY not set — AI features will fall back to NLP")
    try:
        from spb_nlp import __version__ as nlp_ver
        logger.info("spb_nlp module v%s available", nlp_ver)
    except ImportError:
        logger.warning("spb_nlp module not installed — some fallbacks disabled")
    yield
    logger.info("SPB Backend shutting down.")


app = FastAPI(
    title="SPB Backend API",
    description="Student Placement Bridge — AI-powered CV parsing, interview scoring, job matching & recommendations",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cv_router)
app.include_router(interview_router)
app.include_router(recommendations_router)
app.include_router(skill_router)
app.include_router(cover_letter_router)


@app.get("/")
def root():
    return {
        "app": "SPB Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "cv": "/api/cv/parse | /api/cv/match",
            "interview": "/api/interview/score | /api/interview/questions",
            "skill": "/api/skill/match | /api/skill/analyze",
            "mcq": "/api/skill/mcq/generate | /api/skill/mcq/parse",
            "recommendations": "/api/recommendations/jobs | /api/recommendations/learning",
            "cover_letter": "/api/cover-letter/generate",
        },
    }


@app.get("/health")
def health():
    from core.gemini import gemini
    try:
        from spb_nlp import __version__
        nlp_ok = True
    except ImportError:
        nlp_ok = False
    return {
        "status": "ok",
        "gemini_available": gemini.is_available(),
        "nlp_available": nlp_ok,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
