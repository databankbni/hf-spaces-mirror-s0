"""The System — grounded portfolio Q&A agent.

A deliberately small FastAPI proxy with guardrails:
- POST /chat  {"messages":[{"role","content"},...]}  ->  {"reply": "..."}
- GET  /health

Security model: the browser never sees an API key; keys live in HF Space
secrets and are read from the environment. Client input is untrusted data —
validated, sanitized, delimited, rate-limited, and never allowed to override
the server-side system prompt. Interactive docs are disabled to keep the
surface minimal.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .guard import ChatRequest, ChatResponse, RateLimiter, client_ip, wrap_user_content
from .llm import AllProvidersFailed, active_provider, generate_reply

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("system-agent")

# Comma-separated exact origins; no wildcard, ever.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://brej-29.github.io,http://localhost:5500,http://localhost:8321",
    ).split(",")
    if o.strip()
]

MAX_BODY_BYTES = 16_384  # 12 msgs x 500 chars leaves ample headroom

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=3600,
)

limiter = RateLimiter()


@app.middleware("http")
async def hardening(request: Request, call_next):
    started = time.monotonic()

    # Reject oversized payloads before parsing.
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        response = JSONResponse(status_code=413, content={"error": "payload too large"})
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    # Privacy-respecting access log: no message content, no full IPs.
    log.info(
        "method=%s path=%s status=%s latency_ms=%d",
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started) * 1000,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Uniform contract: every failure body is {"error": "..."}; details are
    # intentionally generic so probing reveals nothing about internals.
    return JSONResponse(status_code=422, content={"error": "invalid request format"})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.error("unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "internal error"})


@app.get("/health")
async def health():
    return {"status": "ok", "provider": active_provider()}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    ip = client_ip(request.headers, request.client.host if request.client else "unknown")
    allowed, reason = limiter.check(ip)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": reason})

    # Sanitize + delimit every user turn; assistant turns are echoes of our own
    # prior output but get sanitized anyway (defense in depth).
    messages = [
        {
            "role": m.role,
            "content": wrap_user_content(m.content) if m.role == "user" else m.content[:1600],
        }
        for m in payload.messages
    ]

    try:
        reply = await generate_reply(messages)
    except AllProvidersFailed:
        return JSONResponse(status_code=503, content={"error": "SYSTEM LINK UNSTABLE"})

    return ChatResponse(reply=reply)
