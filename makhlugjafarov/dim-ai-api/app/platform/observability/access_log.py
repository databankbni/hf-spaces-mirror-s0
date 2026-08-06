"""Access logging middleware."""

import logging
import time
from typing import cast

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.platform.observability.correlation import request_id_ctx

logger = logging.getLogger("dim.access")


class AccessLoggingMiddleware:
    """Emits a single structured log record per HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        request = Request(scope, receive)
        client_ip = self._client_ip(scope)
        status_code = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Set by the query route after resolving CallerIdentity (CP12).
            # Falls back to "anonymous" for routes that don't inject user identity.
            user_id = scope.get("user_id", "anonymous")

            logger.info(
                f"{request.method} {request.url.path} {status_code} {elapsed_ms}ms",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "latency_ms": elapsed_ms,
                    "client_ip": client_ip,
                    "user_id": user_id,
                    "request_id": request_id_ctx.get(),
                },
            )

    def _client_ip(self, scope: Scope) -> str:
        # Prefer X-Forwarded-For if behind a CDN/Proxy
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                return value.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        if client:
            return cast(str, client[0])
        return "unknown"
