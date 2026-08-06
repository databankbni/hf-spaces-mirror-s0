"""Provider-agnostic LLM wrapper: Groq primary, Gemini fallback.

Keys come from the environment only (HF Space secrets in production).
Generation is tightly capped: max_tokens <= 400, temperature <= 0.4,
20s timeout per provider, one fallback attempt, then give up.
"""

from __future__ import annotations

import logging
import os

import httpx

from .facts import SYSTEM_PROMPT

log = logging.getLogger("system-agent")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

MAX_TOKENS = 400
TEMPERATURE = 0.3
TIMEOUT_SECONDS = 20.0
# Server-side ceiling on what we relay back, regardless of provider behavior.
MAX_REPLY_CHARS = 1600


class ProviderError(Exception):
    pass


class AllProvidersFailed(Exception):
    pass


def active_provider() -> str:
    """Which provider /health should report as primary right now."""
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "none"


async def _call_groq(client: httpx.AsyncClient, messages: list[dict]) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ProviderError("GROQ_API_KEY not set")
    resp = await client.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": GROQ_MODEL,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        },
        timeout=TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise ProviderError(f"groq status {resp.status_code}")
    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        log.info(
            "provider=groq tokens_in=%s tokens_out=%s",
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        return text
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"groq malformed response: {e}") from e


async def _call_gemini(client: httpx.AsyncClient, messages: list[dict]) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY not set")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    resp = await client.post(
        GEMINI_URL,
        headers={"x-goog-api-key": key},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": MAX_TOKENS, "temperature": TEMPERATURE},
        },
        timeout=TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise ProviderError(f"gemini status {resp.status_code}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        log.info(
            "provider=gemini tokens_in=%s tokens_out=%s",
            usage.get("promptTokenCount", "?"),
            usage.get("candidatesTokenCount", "?"),
        )
        if not text:
            raise ProviderError("gemini empty response")
        return text
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"gemini malformed response: {e}") from e


async def generate_reply(messages: list[dict]) -> str:
    """Try Groq, fall back to Gemini once, else raise AllProvidersFailed."""
    async with httpx.AsyncClient() as client:
        for name, call in (("groq", _call_groq), ("gemini", _call_gemini)):
            try:
                text = (await call(client, messages)).strip()
                return text[:MAX_REPLY_CHARS]
            except (ProviderError, httpx.HTTPError) as e:
                log.warning("provider=%s failed: %s", name, type(e).__name__)
    raise AllProvidersFailed()
