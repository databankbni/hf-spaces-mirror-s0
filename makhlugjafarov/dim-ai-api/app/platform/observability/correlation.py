"""Request correlation: contextvars, middleware, and log filters."""

import logging
import uuid
from contextvars import ContextVar

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

# The request_id context var
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Automatically injects `request_id` into all log records if available."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class RequestCorrelationMiddleware:
    """Mints a request ID or reads X-Request-Id, stores it, and echoes it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        # Accept inbound X-Request-Id or generate a new UUID4
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        # Set the contextvar for the duration of this request
        token = request_id_ctx.set(req_id)

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                # Ensure headers exist as a mutable list of tuples
                headers = message.setdefault("headers", [])
                # Echo the X-Request-Id header back to the client
                headers.append((b"x-request-id", req_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(token)
