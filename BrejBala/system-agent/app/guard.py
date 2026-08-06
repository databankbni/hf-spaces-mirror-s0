"""Request validation, sanitization, and rate limiting.

Everything from the client is untrusted. This module enforces the frontend
contract (role whitelist, 12-message cap, 500-char cap), strips content that
could smuggle instructions past the delimiters, and applies per-IP and global
rate limits.

Known limitation (documented in README): the rate limiter is in-memory and
single-process — it resets on restart and does not share state across workers.
That is an accepted tradeoff for a free single-container Space.
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGES = 12
MAX_CHARS = 500

# Sliding-window per-IP limit
RATE_WINDOW_SECONDS = 5 * 60
RATE_MAX_REQUESTS = 20
# Global daily budget across all visitors
DAILY_CAP = int(os.environ.get("DAILY_CAP", "1000"))

# Characters that can hide or forge instructions: C0/C1 controls (except
# newline and tab), zero-width chars, bidi overrides, invisible operators.
_CONTROL_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    "\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\ufeff]"
)
# Delimiter forgery: the visitor must not be able to close/open our data tags.
_TAG_RE = re.compile(r"</?\s*visitor_query\s*>", re.IGNORECASE)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHARS)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)

    @field_validator("messages")
    @classmethod
    def first_and_last_are_user(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if v[0].role != "user":
            raise ValueError("conversation must start with a user message")
        if v[-1].role != "user":
            raise ValueError("conversation must end with a user message")
        return v


class ChatResponse(BaseModel):
    reply: str


def sanitize(text: str) -> str:
    """Normalize and strip characters that could smuggle instructions."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub("", text)
    text = _TAG_RE.sub("[removed]", text)
    return text.strip()[:MAX_CHARS]


def wrap_user_content(text: str) -> str:
    """Delimit visitor text so the model treats it as data, not instructions."""
    return f"<visitor_query>\n{sanitize(text)}\n</visitor_query>"


class RateLimiter:
    """In-memory sliding window per IP + global daily cap. Thread-safe."""

    def __init__(
        self,
        window: int = RATE_WINDOW_SECONDS,
        max_requests: int = RATE_MAX_REQUESTS,
        daily_cap: int = DAILY_CAP,
    ):
        self.window = window
        self.max_requests = max_requests
        self.daily_cap = daily_cap
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day = self._today()
        self._day_count = 0
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> int:
        return int(time.time() // 86400)

    def check(self, ip: str) -> tuple[bool, str]:
        """Returns (allowed, reason). Counts the request if allowed."""
        now = time.time()
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day = today
                self._day_count = 0

            if self._day_count >= self.daily_cap:
                return False, "daily capacity reached"

            q = self._hits[ip]
            cutoff = now - self.window
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                return False, "rate limit exceeded"

            q.append(now)
            self._day_count += 1

            # Opportunistic cleanup so the map cannot grow unbounded.
            if len(self._hits) > 10_000:
                for key in [k for k, dq in self._hits.items() if not dq or dq[-1] < cutoff]:
                    del self._hits[key]
            return True, ""


def client_ip(headers, fallback: str) -> str:
    """First hop of X-Forwarded-For (HF Spaces runs behind a proxy)."""
    xff = headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return fallback
