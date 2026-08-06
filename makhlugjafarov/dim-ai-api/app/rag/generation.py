"""
app/rag/generation.py — thin re-export shim (CP4).

All logic has moved to the Answer bounded context:
  - GenerationError  →  app.answer.domain.errors
  - SYSTEM_PROMPT / _TIER_CONFLICT_NOTE  →  app.answer.domain.prompt_policy
  - detect_provider / _detect_provider  →  app.answer.domain.provider_policy
  - _call_anthropic / _call_gemini / _call_openai  →  app.answer.infrastructure.providers
  - generate_answer  →  app.answer.application.generate_answer

This shim preserves back-compat for any code that still imports from rag.generation.
Do not add new logic here; remove this file once all callers are updated to the new paths
(tracked as part of GRO-78 enforcement, CP14).
"""
from __future__ import annotations

# Error type
from app.answer.domain.errors import GenerationError as GenerationError  # noqa: PLC0414

# Prompt constants (re-exported for back-compat)
from app.answer.domain.prompt_policy import (
    _SYSTEM_PROMPT as SYSTEM_PROMPT,
    _TIER_CONFLICT_NOTE as _TIER_CONFLICT_NOTE,
)

# Provider detection (back-compat alias; prefer detect_provider in new code)
from app.answer.domain.provider_policy import detect_provider as _detect_provider  # noqa: PLC0414

# Provider adapters (back-compat; use call_provider in new code)
from app.answer.infrastructure.providers import (
    _call_anthropic as _call_anthropic,
    _call_gemini as _call_gemini,
    _call_openai as _call_openai,
)

# Answer use-case
from app.answer.application.generate_answer import generate_answer as generate_answer  # noqa: PLC0414

__all__ = [
    "GenerationError",
    "SYSTEM_PROMPT",
    "_TIER_CONFLICT_NOTE",
    "_detect_provider",
    "_call_anthropic",
    "_call_gemini",
    "_call_openai",
    "generate_answer",
]
