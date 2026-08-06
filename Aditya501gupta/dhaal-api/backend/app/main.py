"""DHAAL API — FastAPI service.

Endpoints:
  GET  /health   — liveness (used by keep-warm pinger)
  POST /analyze  — {"text": "..."} -> full verdict JSON (rules-v0 engine;
                   LLM/forensics/classifier fusion lands here in L1/L2)

Runs anywhere: `uvicorn app.main:app --reload` locally, Docker on HF Spaces.
The engine itself (app/engine/rules.py) is dependency-free by design.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, Field

from app.engine.forensic import analyze as forensic_analyze
from app.engine.fusion import analyze_hybrid
from app.engine.rules import analyze

app = FastAPI(title="DHAAL API", version="0.1.0",
              description="Digital Harm Analysis & Alert Layer — scam verdict engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the frontend origin before judging window
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

DEMO = Path(__file__).resolve().parents[2] / "frontend" / "demo.html"


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000, description="Message text to analyse")
    channel: str = Field(default="paste", description="paste | sms | whatsapp | email | call_transcript")
    mode: str = Field(default="hybrid", description="hybrid | rules")
    language_hint: str | None = None


@app.get("/health")
def health() -> dict:
    from app.engine.llm import available as llm_available
    from app.engine.forensic import available as forensic_available
    return {
        "status": "ok",
        "engine": "hybrid-v2",
        "llm_configured": llm_available(),
        "forensic_feeds": forensic_available(),
    }


@app.post("/analyze")
def analyze_text(req: AnalyzeRequest) -> dict:
    if req.mode == "rules":
        result = analyze(req.text)
    else:
        result = analyze_hybrid(req.text)
    result["channel"] = req.channel
    return result


class ForensicRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000,
                      description="Message or URL(s) to forensically analyse")


@app.post("/forensic")
def forensic_text(req: ForensicRequest) -> dict:
    """Run only the Forensic Agent (live URL threat-intel) over the input.
    Never fetches the URLs — only queries trusted threat databases about them."""
    return forensic_analyze(req.text)


@app.get("/")
def root():
    if DEMO.exists():
        return FileResponse(DEMO)
    return {"service": "DHAAL API", "docs": "/docs"}
