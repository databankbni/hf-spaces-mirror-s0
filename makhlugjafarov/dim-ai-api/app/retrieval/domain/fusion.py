"""Reciprocal Rank Fusion (RRF) for hybrid retrieval (GRO-218 / S3a, PRD §3.2).

Pure domain: no IO, no DB, no embedder. Fuses several *ranked* candidate lists
(dense cosine, lexical FTS, …) into one ranking by RRF, which combines by rank
position — not raw scores — so channels on incomparable scales (cosine vs
``ts_rank_cd``) never need calibration. The PRD (§6.1) starts here deliberately:
RRF is rank-based and parameter-light; a tuned score blend is revisited only if a
measured gap remains.

RRF score of an item = Σ over the channels that rank it of ``1 / (k + rank)``,
with ``rank`` 1-based. A larger ``k`` flattens the contribution of top ranks
(the standard default is 60). Ties break on the item id so fusion is fully
deterministic — required for a stable regression baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.domain.models import RetrievedChunk

# Cormack et al. (2009); the value the Supabase/pgvector hybrid guide also uses.
_DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]], *, k: int = _DEFAULT_RRF_K
) -> list[tuple[str, float]]:
    """Fuse ranked id-lists into one ``(id, score)`` ranking, best first.

    Each inner list is ordered best-first; the item at 0-based position ``i`` has
    rank ``i + 1`` and contributes ``1 / (k + i + 1)``. An id repeated inside one
    channel is counted once (defensive — a well-formed channel never repeats).
    Ties break on the id (ascending) for determinism.
    """
    if k <= 0:
        raise ValueError(f"RRF k must be positive, got {k}")

    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        seen_in_channel: set[str] = set()
        for position, item_id in enumerate(ranked):
            if item_id in seen_in_channel:
                continue
            seen_in_channel.add(item_id)
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + position + 1)

    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def fuse_retrieved_chunks(
    channels: Sequence[Sequence[RetrievedChunk]],
    *,
    k: int = _DEFAULT_RRF_K,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse per-channel ``RetrievedChunk`` lists into one RRF-ordered list.

    When the same chunk surfaces in more than one channel, the instance from the
    *earliest* channel is kept — so callers that pass ``[dense, lexical]`` preserve
    the dense object (and its calibrated cosine ``score``) for a fused chunk, while
    a lexical-only chunk keeps its lexical instance. ``limit`` trims the fused pool.
    """
    ranked_lists = [[chunk.chunk_id for chunk in channel] for channel in channels]
    fused = reciprocal_rank_fusion(ranked_lists, k=k)

    # First-seen wins → earlier channels (dense) take precedence for shared chunks.
    instance_by_id: dict[str, RetrievedChunk] = {}
    for channel in channels:
        for chunk in channel:
            instance_by_id.setdefault(chunk.chunk_id, chunk)

    ordered = [instance_by_id[chunk_id] for chunk_id, _ in fused if chunk_id in instance_by_id]
    return ordered if limit is None else ordered[:limit]
