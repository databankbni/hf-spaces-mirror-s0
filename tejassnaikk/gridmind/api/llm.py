"""
LLM synthesis layer for GridMind.

Calls an OpenAI-compatible chat/completions endpoint (e.g. Gemini via
its OpenAI-compatible API) and returns a grounded answer with inline
chunk citations.

Required env vars (loaded by api/main.py before this module is imported):
  LLM_BASE_URL    — base URL, e.g. https://generativelanguage.googleapis.com/v1beta/openai
  LLM_MODEL       — model name, e.g. gemini-2.5-flash
  GEMINI_API_KEY  — bearer token
"""

from __future__ import annotations

import os
import time

import httpx

_RETRYABLE = {429, 503}


class LLMUnavailable(Exception):
    """Raised when the LLM backend cannot be reached or returns a non-200 status."""


def _build_prompt(question: str, chunks: list[dict]) -> str:
    context_lines = []
    for c in chunks:
        cid = c["chunk_id"][:8]
        req = c.get("requirement_id") or "—"
        context_lines.append(
            f"[{cid}] {c['standard_id']}-{c['version']} {req}: {c['body']}"
        )
    context = "\n\n".join(context_lines)
    return (
        "Answer ONLY from the provided context. "
        "Cite chunk IDs inline in square brackets using the first 8 characters "
        "of the chunk_id, like [56594b09]. "
        "If the context does not contain the answer, reply exactly: "
        '"The retrieved standards do not cover this question."\n\n'
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )


def synthesize(question: str, chunks: list[dict]) -> dict:
    """
    Call the LLM and return {"answer": str, "usage": dict}.

    Raises LLMUnavailable on network errors or non-200 responses.
    """
    base_url = os.environ["LLM_BASE_URL"].rstrip("/")
    model    = os.environ["LLM_MODEL"]
    api_key  = os.environ["GEMINI_API_KEY"]

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": _build_prompt(question, chunks)},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    url     = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(str(exc)) from exc

        if resp.status_code == 200:
            break
        if resp.status_code not in _RETRYABLE or attempt == 1:
            raise LLMUnavailable(
                f"LLM returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        time.sleep(2)

    body = resp.json()
    answer = body["choices"][0]["message"]["content"].strip()
    usage  = body.get("usage", {})
    return {"answer": answer, "usage": usage}
