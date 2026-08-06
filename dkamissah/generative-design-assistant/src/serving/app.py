"""
FastAPI serving endpoint for the Generative Design Assistant.
"""

import os
import json
import glob
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.design_agent import DesignAgent

agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = DesignAgent()
    yield

app = FastAPI(
    title="Generative Design Assistant",
    description="AI-powered engineering requirements analysis and design generation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class DesignRequest(BaseModel):
    requirements: str

@app.get("/health")
def health():
    return {"status": "healthy", "agent_loaded": agent is not None,
            "tools": ["requirements_parser", "knowledge_retriever", "design_generator", "feasibility_evaluator"]}

@app.post("/design")
def design(request: DesignRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not loaded")
    if not request.requirements.strip():
        raise HTTPException(status_code=400, detail="Requirements cannot be empty")
    return agent.run(request.requirements)

@app.get("/reports")
def list_reports():
    reports = sorted(glob.glob("outputs/reports/*.json"), reverse=True)
    summaries = []
    for path in reports[:20]:
        with open(path) as f:
            r = json.load(f)
        summaries.append({
            "report_id": r.get("report_id"),
            "component": r.get("component"),
            "recommended": r.get("evaluation", {}).get("recommended"),
            "timestamp": r.get("timestamp"),
        })
    return {"reports": summaries, "total": len(reports)}

@app.get("/reports/{report_id}")
def get_report(report_id: str):
    path = f"outputs/reports/{report_id}.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    with open(path) as f:
        return json.load(f)