"""
Answer infrastructure — LLM provider adapters.

Each adapter is a pure function: (question, context_text, api_key, model, history,
system_prompt, max_tokens) → str.  ``call_provider`` is the single dispatch point
that ``generate_answer`` calls through the port; no business logic lives here.

Adding a new provider in the future:
1. Write ``_call_<name>`` following the existing pattern.
2. Add the ProviderName key → function mapping in ``_PROVIDER_ADAPTERS``.
Nothing else changes.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

import httpx

from app.answer.domain.errors import GenerationError
from app.answer.domain.provider_policy import ProviderName

logger = logging.getLogger(__name__)

# Gemini 2.5+ models enable internal "thinking" by default. Those tokens share the
# maxOutputTokens budget, which truncates visible answers (GRO-111-style symptom:
# intro sentence then stop). Flash/Lite can disable thinking; Pro cannot.
_GEMINI_THINKING_MODEL = re.compile(r"gemini-(?:2\.5|3)", re.IGNORECASE)
_GEMINI_FLASH_MODEL = re.compile(
    r"gemini-(?:2\.5-flash(?:-[\w.-]+)?|2\.5-flash-lite(?:-[\w.-]+)?|3-flash(?:-[\w.-]+)?)",
    re.IGNORECASE,
)
# Gemini 2.5 Flash may still spend output budget on reasoning even with thinkingBudget=0
# (known API inconsistency). Keep a generous floor so tutor prose is not clipped.
_GEMINI_MIN_OUTPUT_TOKENS = 2048
_GEMINI_ENUM_OUTPUT_TOKENS = 4096
_GEMINI_RETRY_OUTPUT_TOKENS = 8192


# ---------------------------------------------------------------------------
# Provider adapter type
# ---------------------------------------------------------------------------

ProviderAdapter = Callable[
    [str, str, str, str, list[dict[str, str]], str, int],
    str,
]
"""(question, context_text, api_key, model, history, system_prompt, max_tokens) → answer"""


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

def _effective_gemini_output_tokens(*, model: str, max_tokens: int, enumeration: bool) -> int:
    if not _GEMINI_THINKING_MODEL.search(model):
        return max_tokens
    floor = _GEMINI_ENUM_OUTPUT_TOKENS if enumeration else _GEMINI_MIN_OUTPUT_TOKENS
    return max(max_tokens, floor)


def _gemini_generation_config(*, model: str, max_tokens: int, enumeration: bool = False) -> dict:
    """Build generationConfig for generateContent.

    Gemini 2.5 Flash spends most of a low maxOutputTokens on thinking, leaving
    almost no room for the tutor answer. Disable thinking on Flash/Lite; cap
    thinking on Pro where it cannot be turned off.
    """
    output_tokens = _effective_gemini_output_tokens(
        model=model,
        max_tokens=max_tokens,
        enumeration=enumeration,
    )
    config: dict = {"maxOutputTokens": output_tokens, "temperature": 0.2}
    if not _GEMINI_THINKING_MODEL.search(model):
        return config
    if _GEMINI_FLASH_MODEL.search(model):
        config["thinkingConfig"] = {"thinkingBudget": 0, "includeThoughts": False}
    else:
        # Pro / other 2.5+ models: keep thinking minimal so prose answers fit.
        config["thinkingConfig"] = {"thinkingBudget": 128, "includeThoughts": False}
    return config


def _looks_truncated_answer(text: str) -> bool:
    """Heuristic for list-intro answers that stop before enumerating."""
    trimmed = text.rstrip()
    if len(trimmed) > 400:
        return False
    if trimmed.endswith(":"):
        return True
    return bool(re.search(r"\bbunlardır\s*:?\s*$", trimmed, flags=re.IGNORECASE))


def _extract_gemini_text(data: dict) -> str:
    """Return visible answer text from a generateContent response."""
    candidates = data.get("candidates") or []
    if not candidates:
        raise KeyError("candidates")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    for part in parts:
        if part.get("thought"):
            continue
        text = part.get("text")
        if text:
            texts.append(text)
    if not texts:
        raise KeyError("text parts")
    answer = "".join(texts).strip()
    if finish_reason == "MAX_TOKENS":
        logger.warning(
            "Gemini response hit MAX_TOKENS (len=%s); consider raising max_tokens",
            len(answer),
        )
    return answer


# ---------------------------------------------------------------------------
# Concrete adapters — byte-equivalent to rag/generation.py implementations
# ---------------------------------------------------------------------------

def _call_anthropic(
    question: str,
    context_text: str,
    api_key: str,
    model: str,
    history: list[dict[str, str]],
    system_prompt: str,
    max_tokens: int,
) -> str:
    messages: list[dict[str, str]] = list(history[-6:])
    messages.append({"role": "user", "content": f"Kontekst:\n{context_text}\n\nSual: {question}"})
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except httpx.HTTPStatusError as exc:
        raise GenerationError(f"Anthropic API returned status {exc.response.status_code}") from exc
    except (httpx.RequestError, KeyError, IndexError) as exc:
        raise GenerationError(f"Anthropic call failed: {exc}") from exc


def _call_gemini(
    question: str,
    context_text: str,
    api_key: str,
    model: str,
    history: list[dict[str, str]],
    system_prompt: str,
    max_tokens: int,
    *,
    enumeration: bool = False,
) -> str:
    contents: list[dict] = []
    for msg in history[-6:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({
        "role": "user",
        "parts": [{"text": f"Kontekst:\n{context_text}\n\nSual: {question}"}],
    })
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    token_budgets = [
        _effective_gemini_output_tokens(
            model=model,
            max_tokens=max_tokens,
            enumeration=enumeration,
        ),
    ]
    if _GEMINI_THINKING_MODEL.search(model):
        token_budgets.append(max(token_budgets[0] * 2, _GEMINI_RETRY_OUTPUT_TOKENS))

    last_error: Exception | None = None
    last_answer = ""
    try:
        for attempt, output_tokens in enumerate(token_budgets):
            resp = httpx.post(
                url,
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": _gemini_generation_config(
                        model=model,
                        max_tokens=output_tokens,
                        enumeration=enumeration,
                    ),
                },
                timeout=90.0,
            )
            if resp.status_code == 429:
                return (
                    "⚠️ AI modeli hazırda məşğuldur (rate limit). "
                    "Bir neçə saniyə gözləyib yenidən cəhd edin."
                )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usageMetadata") or {}
            thoughts = usage.get("thoughtsTokenCount")
            try:
                answer = _extract_gemini_text(data)
            except KeyError as exc:
                last_error = exc
                continue
            finish_reason = (data.get("candidates") or [{}])[0].get("finishReason")
            last_answer = answer
            should_retry = (
                attempt + 1 < len(token_budgets)
                and (
                    finish_reason == "MAX_TOKENS"
                    or _looks_truncated_answer(answer)
                )
            )
            if should_retry:
                logger.warning(
                    "Gemini answer truncated (finish=%s, len=%s, thoughts=%s); retrying with %s tokens",
                    finish_reason,
                    len(answer),
                    thoughts,
                    token_budgets[attempt + 1],
                )
                continue
            return answer
        if last_answer:
            return last_answer
        if last_error:
            raise last_error
        raise KeyError("text parts")
    except httpx.HTTPStatusError as exc:
        raise GenerationError(f"Gemini API returned status {exc.response.status_code}") from exc
    except (httpx.RequestError, KeyError, IndexError) as exc:
        raise GenerationError(f"Gemini call failed: {exc}") from exc


def _call_openai(
    question: str,
    context_text: str,
    api_key: str,
    model: str,
    history: list[dict[str, str]],
    system_prompt: str,
    max_tokens: int,
) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": f"Kontekst:\n{context_text}\n\nSual: {question}"})
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": messages,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        raise GenerationError(f"OpenAI API returned status {exc.response.status_code}") from exc
    except (httpx.RequestError, KeyError, IndexError) as exc:
        raise GenerationError(f"OpenAI call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Provider port — single dispatch table
# ---------------------------------------------------------------------------

_PROVIDER_ADAPTERS: dict[ProviderName, ProviderAdapter] = {
    "anthropic": _call_anthropic,
    "google": _call_gemini,
    "openai": _call_openai,
}


def call_provider(
    *,
    provider: ProviderName,
    question: str,
    context_text: str,
    api_key: str,
    model: str,
    history: list[dict[str, str]],
    system_prompt: str,
    max_tokens: int,
    enumeration: bool = False,
) -> str:
    """
    Dispatch a generation request to the correct provider adapter.

    ``generate_answer`` calls this instead of the private ``_call_*`` functions
    directly, satisfying the Dependency Inversion Principle.
    """
    if provider == "google":
        return _call_gemini(
            question,
            context_text,
            api_key,
            model,
            history,
            system_prompt,
            max_tokens,
            enumeration=enumeration,
        )
    adapter = _PROVIDER_ADAPTERS[provider]
    return adapter(question, context_text, api_key, model, history, system_prompt, max_tokens)
