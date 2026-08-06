"""
Answer domain — ProviderPolicy.

Centralises provider detection (previously duplicated between rag/generation.py
and api/routes/byok.py).  After CP4:

  - ``detect_provider(model)`` is the single canonical implementation.
  - ``ProviderPolicy.validate(model, provider)`` is the public seam for both
    the query use-case and the BYOK route.
  - Neither route imports ``_detect_provider`` from ``rag.generation`` anymore.
"""
from __future__ import annotations

from typing import Literal

from app.answer.domain.errors import GenerationError

# Concrete set of supported providers — avoids bare ``str`` everywhere
ProviderName = Literal["google", "openai", "anthropic"]

_PROVIDER_PREFIXES: list[tuple[tuple[str, ...], ProviderName]] = [
    (("gemini",), "google"),
    (("gpt-", "o1", "o3"), "openai"),
    (("claude",), "anthropic"),
]


def detect_provider(model: str) -> ProviderName:
    """
    Infer the LLM provider from a model-name prefix.

    Raises :class:`~app.answer.domain.errors.GenerationError` with a safe, key-free
    message when no prefix matches.
    """
    m = model.lower()
    for prefixes, provider in _PROVIDER_PREFIXES:
        if any(m.startswith(p) for p in prefixes):
            return provider
    raise GenerationError(
        f"Cannot detect provider for model '{model}'. "
        "Use a model name starting with 'gemini', 'gpt-', 'o1', 'o3', or 'claude'."
    )


class ProviderPolicy:
    """
    Validates that the claimed provider matches the model-name prefix.

    Raises :class:`~app.answer.domain.errors.GenerationError` on mismatch so callers
    can map it to HTTP 400 without inspecting internals.
    """

    @staticmethod
    def validate(model: str, provider: str) -> ProviderName:
        """
        Detect the real provider from ``model`` and assert it matches ``provider``.

        Returns the canonical :data:`ProviderName` on success.
        """
        detected = detect_provider(model)
        if detected != provider:
            raise GenerationError(
                f"Selected provider does not match model prefix; detected {detected}."
            )
        return detected
