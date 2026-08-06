"""Reciprocal Rank Fusion for hybrid retrieval."""

from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_ids: list[list[str]],
    *,
    rrf_k: int = 60,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked chunk-id lists using RRF.

    Returns chunk IDs sorted by descending fused score.
    """
    scores: dict[str, float] = {}

    for ranking in ranked_ids:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)

    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if top_k is not None:
        fused = fused[:top_k]
    return fused
