"""FastAPI application factory."""
from __future__ import annotations

import pathlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import inspect

class CompatibleJinja2Templates(Jinja2Templates):
    def TemplateResponse(self, name: str, context: dict, *args, **kwargs):
        sig = inspect.signature(super().TemplateResponse)
        params = list(sig.parameters.values())
        
        # Check if first parameter is request or self (in case self is unbound)
        is_new_signature = False
        if params:
            if params[0].name == "request":
                is_new_signature = True
            elif params[0].name == "self" and len(params) > 1 and params[1].name == "request":
                is_new_signature = True
                
        if is_new_signature:
            request = context.get("request")
            return super().TemplateResponse(request, name, context, *args, **kwargs)
        else:
            return super().TemplateResponse(name, context, *args, **kwargs)

from mktbook.web.websocket import WSManager

_WEB_DIR = pathlib.Path(__file__).parent
TEMPLATES = CompatibleJinja2Templates(directory=str(_WEB_DIR / "templates"))


def create_app(ws: WSManager) -> FastAPI:
    app = FastAPI(title="MktBook Bot Marketplace")

    # WebSocket endpoint — register FIRST before routers
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await ws.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws.disconnect(websocket)

    app.mount("/static", StaticFiles(directory=str(_WEB_DIR / "static")), name="static")

    # Store shared objects on app state
    app.state.ws = ws
    app.state.fleet = None       # set by main.py
    app.state.scheduler = None   # set by main.py
    app.state.openai = None      # set by main.py

    # Register routes
    from mktbook.lti.routes import router as lti_router
    from mktbook.web.routes_api import router as api_router
    from mktbook.web.routes_pages import router as pages_router

    app.include_router(lti_router)
    app.include_router(api_router)
    app.include_router(pages_router)

    return app
