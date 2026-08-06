from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.retrieval.domain.models import RetrievedChunk

def _detect_tier_conflict(chunks: list[RetrievedChunk]) -> bool:
    """Return True when selected chunks mix authoritative (tier ≤ 2) and lower-tier (tier ≥ 3) sources.

    A conflict means the LLM should be told to favour the official source, because the supplementary
    material may contain outdated or simplified content that contradicts the curriculum textbook.
    """
    tiers = {chunk.citation.source_tier for chunk in chunks}
    has_authoritative = any(t <= 2 for t in tiers)
    has_supplementary = any(t >= 3 for t in tiers)
    return has_authoritative and has_supplementary
