"""
HF Space entrypoint — wraps server.app with:
  1. Cyberpunk static frontend on GET / (from /static/index.html)
  2. /api/*  →  /*   rewrite (so the existing server.app routes keep working
     unchanged for callers using /api/query, /api/health, /api/context)

Nothing inside server.py is modified — we only add a middleware and mounts
on top of the same FastAPI app instance.
"""
import os

from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Reuse the already-configured FastAPI app from server.py
# (engine singleton, CORS, /health, /query, /context, Web UI route are all there).
import server

app = server.app

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ASSETS_DIR = os.path.join(STATIC_DIR, "assets")
MODELS_DIR = os.path.join(STATIC_DIR, "models")


@app.middleware("http")
async def cyberpunk_ui_and_api_proxy(request: Request, call_next):
    """
    - GET /            → serve static/index.html (cyberpunk SPA)
    - GET /<root_files>→ serve static/favicon.svg, static/icons.svg, etc.
    - /api/<rest>      → strip "/api" prefix so the existing server.app routes
                         answer the request transparently
    - everything else  → pass through to server.app as-is
    """
    path = request.url.path

    # 1. Serve the SPA shell on root
    if path == "/" and request.method == "GET":
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index):
            return FileResponse(index, media_type="text/html")

    # 2. /api/*  →  /* (path rewrite before routing)
    if path.startswith("/api/"):
        new_path = "/" + path[len("/api/"):]
        request.scope["path"] = new_path
        request.scope["raw_path"] = new_path.encode("latin-1")

    return await call_next(request)


# Static mounts. Keep these AFTER the middleware so request.scope still
# carries the user-facing path (e.g. /assets/...) when not proxied.
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="static-assets")
if os.path.isdir(MODELS_DIR):
    app.mount("/models", StaticFiles(directory=MODELS_DIR), name="static-models")


# Direct routes for root-level static files referenced by index.html
from fastapi import HTTPException

@app.get("/favicon.svg", include_in_schema=False)
async def _favicon():
    p = os.path.join(STATIC_DIR, "favicon.svg")
    if not os.path.exists(p):
        raise HTTPException(status_code=404)
    return FileResponse(p)


@app.get("/icons.svg", include_in_schema=False)
async def _icons():
    p = os.path.join(STATIC_DIR, "icons.svg")
    if not os.path.exists(p):
        raise HTTPException(status_code=404)
    return FileResponse(p)


# === Entrypoint ===
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", "7860"))
    host = os.environ.get("API_HOST", "0.0.0.0")
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    print(f"=== IFODA RAG (cyberpunk frontend) on {host}:{port} ===")
    uvicorn.run(app, host=host, port=port, log_level=log_level)