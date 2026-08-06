"""Custom ASGI middlewares for abuse control."""

import time
from collections import deque
from threading import Lock

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BodySizeLimitMiddleware:
    """Reject requests whose body exceeds *max_bytes* before the route handler
    reads it.  Returns 413 immediately so large uploads never touch app logic."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    content_length = int(value)
                except ValueError:
                    pass
                break

        if content_length is not None and content_length > self.max_bytes:
            response = JSONResponse(
                {"detail": f"Request body too large (max {self.max_bytes // 1024} KB)."},
                status_code=413,
            )
            await response(scope, receive, send)
            return

        # Also guard streaming bodies where Content-Length is absent.
        total = 0
        body_chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                response = JSONResponse(
                    {"detail": f"Request body too large (max {self.max_bytes // 1024} KB)."},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            body_chunks.append(chunk)
            more = message.get("more_body", False)

        # Reconstruct a receive callable: serve the buffered body on first call,
        # then delegate to the original receive for disconnect detection during
        # streaming responses.
        full_body = b"".join(body_chunks)
        consumed = False

        async def buffered_receive() -> dict:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)


class _SlidingWindow:
    """Thread-safe sliding-window counter for a single IP."""

    __slots__ = ("_lock", "_window", "_limit", "_period")

    def __init__(self, limit: int, period: float) -> None:
        self._lock = Lock()
        self._window: deque[float] = deque()
        self._limit = limit
        self._period = period

    def is_allowed(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._period
        with self._lock:
            while self._window and self._window[0] < cutoff:
                self._window.popleft()
            if len(self._window) >= self._limit:
                return False
            self._window.append(now)
            return True


class IPRateLimitMiddleware:
    """Sliding-window rate limiter keyed by client IP.

    Returns 429 when a single IP exceeds *requests_per_minute* requests
    within any rolling 60-second window.  State is in-memory and resets on
    restart — suitable for single-instance deployments (HF Spaces, single
    Uvicorn worker).
    """

    def __init__(self, app: ASGIApp, requests_per_minute: int) -> None:
        self.app = app
        self._rpm = requests_per_minute
        self._windows: dict[str, _SlidingWindow] = {}
        self._map_lock = Lock()

    def _get_window(self, ip: str) -> _SlidingWindow:
        with self._map_lock:
            if ip not in self._windows:
                self._windows[ip] = _SlidingWindow(self._rpm, 60.0)
            return self._windows[ip]

    def _client_ip(self, scope: Scope) -> str:
        # Prefer X-Forwarded-For when behind a reverse proxy/CDN.
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                return value.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ip = self._client_ip(scope)
        window = self._get_window(ip)
        if not window.is_allowed():
            response = JSONResponse(
                {"detail": "Too many requests. Please slow down."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
