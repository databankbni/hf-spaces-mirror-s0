"""
Dashboard Analytics API — Ethiopia 360 Intelligence Platform
"""

import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Add project root to path so routes can import shared modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from routes import analytics, ethiopia360

app = FastAPI(
    title="Ethiopia 360 Intelligence API",
    description="Real-time intelligence endpoints for the Ethiopia 360 platform",
    version="2.0.0"
)

# CORS — allow all origins so the HF-hosted frontend can reach the HF-hosted backend
# If you deploy the frontend to a fixed domain, change "*" to that domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # Must be False when allow_origins=["*"]
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# Core routes
app.include_router(analytics.router,          prefix="/api/dashboard",    tags=["analytics"])
app.include_router(ethiopia360.router,        prefix="/api/v2",           tags=["ethiopia360"])

# Domain-specific routes
from routes import conflict, trade_economy, weather, economy, infrastructure, currency, global_perspective, environment

app.include_router(conflict.router,           prefix="/api/conflict",      tags=["conflict"])
app.include_router(trade_economy.router,      prefix="/api/trade-economy", tags=["trade-economy"])
app.include_router(weather.router,            prefix="/api/weather",       tags=["weather"])
app.include_router(economy.router,            prefix="/api/economy",       tags=["economy"])
app.include_router(infrastructure.router,     prefix="/api/infrastructure",tags=["infrastructure"])
app.include_router(currency.router,           prefix="/api/currency",      tags=["currency"])
app.include_router(global_perspective.router, prefix="/api/global",        tags=["global"])
app.include_router(environment.router,        prefix="/api/environment",   tags=["environment"])


@app.get("/")
def root():
    return {
        "service": "Ethiopia 360 Intelligence API",
        "version": "2.0.0",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7861"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
