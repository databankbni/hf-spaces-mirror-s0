"""RAG pipeline — retrieve review chunks then generate a cited answer via Groq/Llama."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# The embedding/cross-encoder models used by Phase 4 retrieval are already
# cached locally. huggingface_hub>=1.x ignores HF_HUB_DISABLE_SSL_VERIFICATION
# for its online metadata HEAD checks, which fail behind this machine's
# TLS-inspecting proxy. Force offline so the cached models load directly.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.retrieval.retriever import retrieve  # noqa: E402  (after offline env setup)

logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are an analyst for Spotify's product team specialising in music discovery.
You have been given a set of real user reviews and community posts retrieved from the Spotify review corpus.

Rules you MUST follow:
1. Answer ONLY using the evidence in the provided review chunks. Do not speculate, invent details, or draw on general knowledge about Spotify.
2. Every factual claim must be followed by an inline citation in the exact format: [source, date].
3. Keep your answer concise: 3-5 sentences plus citations.
4. If the retrieved chunks do not contain enough evidence to answer the question, say so explicitly — do not guess.
5. Do not start with phrases like "Based on the reviews" — dive straight into the finding."""


def _insecure_http_client() -> httpx.Client:
    """httpx client with TLS verification disabled.

    This machine sits behind a TLS-inspecting proxy whose root CA is not in
    certifi's bundle, so outbound HTTPS to the LLM APIs fails certificate
    verification. We mirror the project's existing posture
    (HF_HUB_DISABLE_SSL_VERIFICATION=1, ADR-022) by disabling verification for
    Groq calls as well.
    """
    return httpx.Client(verify=False)


def _build_context_block(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk.get("source", "unknown")
        date = (chunk.get("date") or "unknown date")[:10]
        text = (chunk.get("text") or "").strip()
        score = chunk.get("similarity", 0.0)
        lines.append(f"[{i}] source={source} | date={date} | relevance={score:.3f}\n{text}")
    return "\n\n".join(lines)


def answer_question(query: str, k: int = 5) -> dict[str, Any]:
    """Retrieve relevant review chunks then generate a cited answer.

    Returns:
        {
            "answer": str,
            "sources": [{"source", "date", "text", "url", "score"}]
        }
    """
    api_key = os.getenv("GROQ_API_KEY")
    logger.info("GROQ_API_KEY loaded: %s", "yes" if api_key else "NO")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from environment variables.")

    chunks = retrieve(query, k=k)
    if not chunks:
        return {"answer": "No relevant reviews found for this query.", "sources": []}

    context = _build_context_block(chunks)
    user_message = f"""Retrieved review chunks:

{context}

---
Question: {query}

Answer (cite every claim with [source, date], 3-5 sentences):"""

    client = Groq(api_key=api_key, http_client=_insecure_http_client())
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        model=_GROQ_MODEL,
        temperature=0.0,
        max_tokens=512,
    )
    answer_text = (response.choices[0].message.content or "").strip()
    tokens_used = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)

    sources = [
        {
            "source": chunk.get("source"),
            "date": (chunk.get("date") or "")[:10],
            "text": (chunk.get("text") or "")[:300],
            "url": chunk.get("url"),
            "score": round(chunk.get("similarity", 0.0), 4),
        }
        for chunk in chunks
    ]

    logger.info(
        "answer_question completed | model=%s | query=%r | chunks=%d | tokens_used=%d",
        _GROQ_MODEL,
        query,
        len(chunks),
        tokens_used,
    )

    return {"answer": answer_text, "sources": sources}
