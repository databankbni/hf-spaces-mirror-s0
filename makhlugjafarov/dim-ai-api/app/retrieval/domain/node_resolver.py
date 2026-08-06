"""Node-resolution contract for structural retrieval (GRO-224 / S5a).

Given top-N ranked chunks that carry ``curriculum_node_id``, infer which curriculum
node owns the question. Pure module — no DB I/O. Callers may supply ``node_titles``
and ``parent_by_node`` for title-match and ancestor-expansion fallbacks.

The policy (top-1 vs score-weighted vote vs document-scoped majority) is chosen by
measurement on the labelled slice in ``data/evals/node_resolution_v1.yaml``; this
module implements all candidates so the eval can compare them honestly.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.eval.domain.retrieval_coverage import normalize_text
from app.retrieval.domain.models import RetrievedChunk

NodeResolverPolicy = Literal["top1", "score_weighted_vote", "document_majority"]

POLICIES: tuple[NodeResolverPolicy, ...] = (
    "top1",
    "score_weighted_vote",
    "document_majority",
)

SKIP_NO_FK = "no_chunk_with_curriculum_node_id"
SKIP_BELOW_FLOOR = "confidence_below_floor"
SKIP_TITLE_MISS = "title_match_found_no_node"


@dataclass(frozen=True)
class NodeVote:
    """One curriculum-node candidate with an aggregate weight and supporting chunks."""

    node_id: str
    weight: float
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class NodeResolution:
    """Outcome of resolving which node owns a query (not wired into serving until S5b)."""

    policy: NodeResolverPolicy
    primary_node_id: str | None
    confidence: float
    candidates: tuple[NodeVote, ...]
    skipped_reason: str | None = None
    fallback_method: str | None = None


def resolve_owning_node(
    *,
    query: str,
    chunks: Sequence[RetrievedChunk],
    policy: NodeResolverPolicy = "top1",
    top_n: int = 8,
    confidence_floor: float = 0.15,
    node_titles: Mapping[str, str] | None = None,
    parent_by_node: Mapping[str, str | None] | None = None,
    enable_title_fallback: bool = True,
    enable_ancestor_tiebreak: bool = True,
) -> NodeResolution:
    """Resolve the owning curriculum node from ranked chunks.

    Fallback order when the primary policy cannot produce a confident winner:
    1. Title match — query vs ``node_titles`` using ``normalize_text`` (§9.1).
    2. Ancestor expansion — when the top two votes tie within 5 %, walk up
       ``parent_by_node`` to the deepest common ancestor (sibling de-confusion).
    3. Explicit skip — ``skipped_reason`` records why structural augmentation
       must not run (no FK, low confidence, or title miss).
    """
    pool = list(chunks[:top_n])
    with_fk = [c for c in pool if c.curriculum_node_id]

    if not with_fk:
        if enable_title_fallback and node_titles:
            title_vote = _title_match_vote(query, node_titles)
            if title_vote:
                return NodeResolution(
                    policy=policy,
                    primary_node_id=title_vote.node_id,
                    confidence=title_vote.weight,
                    candidates=(title_vote,),
                    fallback_method="title_match",
                )
        return NodeResolution(
            policy=policy,
            primary_node_id=None,
            confidence=0.0,
            candidates=(),
            skipped_reason=SKIP_NO_FK,
        )

    candidates = _rank_candidates(with_fk, policy=policy)
    if not candidates:
        return NodeResolution(
            policy=policy,
            primary_node_id=None,
            confidence=0.0,
            candidates=(),
            skipped_reason=SKIP_NO_FK,
        )

    total_weight = sum(v.weight for v in candidates) or 1.0
    primary = candidates[0]
    confidence = primary.weight / total_weight
    fallback_method: str | None = None

    if (
        enable_ancestor_tiebreak
        and parent_by_node
        and len(candidates) >= 2
        and abs(candidates[0].weight - candidates[1].weight) / total_weight < 0.05
    ):
        ancestor = _deepest_common_ancestor(
            candidates[0].node_id,
            candidates[1].node_id,
            parent_by_node,
        )
        if ancestor and ancestor != primary.node_id:
            primary = NodeVote(
                node_id=ancestor,
                weight=primary.weight,
                chunk_ids=primary.chunk_ids,
            )
            fallback_method = "ancestor_tiebreak"

    if confidence < confidence_floor:
        if enable_title_fallback and node_titles:
            title_vote = _title_match_vote(query, node_titles)
            if title_vote:
                return NodeResolution(
                    policy=policy,
                    primary_node_id=title_vote.node_id,
                    confidence=title_vote.weight,
                    candidates=(title_vote, *candidates),
                    fallback_method="title_match",
                )
        return NodeResolution(
            policy=policy,
            primary_node_id=None,
            confidence=confidence,
            candidates=tuple(candidates),
            skipped_reason=SKIP_BELOW_FLOOR,
        )

    return NodeResolution(
        policy=policy,
        primary_node_id=primary.node_id,
        confidence=confidence,
        candidates=tuple(candidates),
        fallback_method=fallback_method,
    )


def _rank_candidates(
    chunks: Sequence[RetrievedChunk],
    *,
    policy: NodeResolverPolicy,
) -> list[NodeVote]:
    if policy == "top1":
        first = chunks[0]
        assert first.curriculum_node_id
        return [
            NodeVote(
                node_id=first.curriculum_node_id,
                weight=max(first.score, 0.0),
                chunk_ids=(first.chunk_id,),
            )
        ]

    weights: dict[str, float] = defaultdict(float)
    chunk_ids: dict[str, list[str]] = defaultdict(list)

    if policy == "score_weighted_vote":
        for chunk in chunks:
            assert chunk.curriculum_node_id
            weights[chunk.curriculum_node_id] += max(chunk.score, 0.0)
            chunk_ids[chunk.curriculum_node_id].append(chunk.chunk_id)
    elif policy == "document_majority":
        for chunk in chunks:
            assert chunk.curriculum_node_id
            weights[chunk.curriculum_node_id] += 1.0
            chunk_ids[chunk.curriculum_node_id].append(chunk.chunk_id)
    else:
        raise ValueError(f"unknown policy: {policy!r}")

    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return [
        NodeVote(node_id=nid, weight=weight, chunk_ids=tuple(chunk_ids[nid]))
        for nid, weight in ranked
    ]


def _title_match_vote(
    query: str,
    node_titles: Mapping[str, str],
) -> NodeVote | None:
    """Pick the longest node title that matches the normalised query (broadest topic)."""
    qnorm = normalize_text(query)
    best_id: str | None = None
    best_len = 0
    for node_id, title in node_titles.items():
        tnorm = normalize_text(title)
        if not tnorm:
            continue
        if tnorm in qnorm or any(
            len(token) > 4 and token in tnorm for token in qnorm.split()
        ):
            if len(tnorm) > best_len:
                best_id = node_id
                best_len = len(tnorm)
    if best_id is None:
        return None
    return NodeVote(node_id=best_id, weight=0.5, chunk_ids=())


def _deepest_common_ancestor(
    left_id: str,
    right_id: str,
    parent_by_node: Mapping[str, str | None],
) -> str | None:
    """Walk two node chains upward and return the deepest shared ancestor."""
    left_chain: list[str] = []
    current: str | None = left_id
    while current:
        left_chain.append(current)
        current = parent_by_node.get(current)

    current = right_id
    while current:
        if current in left_chain:
            return current
        current = parent_by_node.get(current)
    return None


def enumeration_node_hint(query: str, node_titles: Mapping[str, str]) -> str | None:
    """Prefer curriculum nodes known to own complete enumeration tables.

    Short student phrasing (e.g. «Alkanların ilk on üzvünü adlandırın») often
    ranks the wrong sibling node under top-1 resolution; title hints recover the
    homologous-series / climate-belt lesson when the query cues match.
    """
    qnorm = normalize_text(query)
    if not qnorm:
        return None

    def _best_title_match(
        title_pattern: re.Pattern[str],
        *,
        required: re.Pattern[str] | None = None,
    ) -> str | None:
        best_id: str | None = None
        best_len = 0
        for node_id, title in node_titles.items():
            tnorm = normalize_text(title)
            if required and not required.search(tnorm):
                continue
            if title_pattern.search(tnorm) and len(tnorm) > best_len:
                best_id = node_id
                best_len = len(tnorm)
        return best_id

    if "alkan" in qnorm and ("ilk on" in qnorm or "homoloji" in qnorm or "sirasi" in qnorm):
        return _best_title_match(
            re.compile(r"homoloj|homoloi", re.IGNORECASE),
            required=re.compile(r"alkan", re.IGNORECASE),
        )
    if "iqlim" in qnorm and ("qursa" in qnorm or "sadal" in qnorm):
        return _best_title_match(re.compile(r"iqlim.*qursa|qursa.*iqlim", re.IGNORECASE))
    return None
