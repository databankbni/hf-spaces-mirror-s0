"""Answer domain — error types."""
from __future__ import annotations


class GenerationError(RuntimeError):
    """Raised when LLM generation fails."""
