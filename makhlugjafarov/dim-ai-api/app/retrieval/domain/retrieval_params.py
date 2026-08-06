"""Pinned retrieval tuning constants (GRO-226 / S6).

Defaults match the pre-sweep serving path. S6 replaces hand-tuned values with
data-backed choices documented in BENCHMARKS; this module is the single source
of truth for runtime defaults and sweep baselines.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalParams:
    default_top_k: int = 8
    candidate_count: int = 30
    min_score: float = 0.62
    max_context_chars: int = 12_000
    lexical_candidate_count: int = 50
    rrf_k: int = 60
    enable_lexical: bool = True


DEFAULT_RETRIEVAL_PARAMS = RetrievalParams()
