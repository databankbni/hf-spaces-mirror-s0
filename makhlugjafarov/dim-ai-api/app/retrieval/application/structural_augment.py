"""Structural augmentation: owning-node chunks + content_blocks (GRO-225 / S5b).

On enumeration intent + confident node resolution (S5a contract), fetch the owning
node's corpus material and merge it with the fused retrieval pool before S2 packing.
Reuses the curriculum reader for blocks; loads full chunk rows for dedupe with the
ranked pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.curriculum.domain.block_render import is_renderable, render_block
from app.curriculum.infrastructure.postgres_curriculum_reader import fetch_blocks_by_node_path
from app.retrieval.domain.models import Citation, RetrievedChunk
from app.retrieval.domain.node_resolver import (
    NodeResolverPolicy,
    enumeration_node_hint,
    resolve_owning_node,
)
from app.retrieval.infrastructure.chunk_rows import CHUNK_COLUMNS_SQL, chunk_from_row

if TYPE_CHECKING:
    from psycopg import Connection

# Injected ahead of ranked hits so enumeration content survives packing when possible.
_AUGMENT_SCORE = 1.0
_BLOCK_SCORE = 0.95
_MAX_NODE_INJECT_CHUNKS = 8
_MAX_BLOCK_INJECT = 4


@dataclass(frozen=True)
class StructuralAugmentResult:
    candidates: list[RetrievedChunk]
    applied: bool
    skip_reason: str | None = None
    node_id: str | None = None
    node_path: str | None = None
    node_chunk_count: int = 0
    block_chunk_count: int = 0
    injected_chunks: tuple[RetrievedChunk, ...] = ()


def _load_node_titles(connection: Connection, *, source_id: str) -> dict[str, str]:
    with connection.cursor() as cur:
        cur.execute(
            """
            select n.id, n.title
              from public.curriculum_nodes n
              join public.documents d on d.id = n.document_id
             where d.source_id = %s
            """,
            (source_id,),
        )
        rows = cur.fetchall()
    return {str(r["id"]): r["title"] for r in rows}


def _load_parent_map(connection: Connection, *, source_id: str) -> dict[str, str | None]:
    with connection.cursor() as cur:
        cur.execute(
            """
            select n.id, n.parent_id
              from public.curriculum_nodes n
              join public.documents d on d.id = n.document_id
             where d.source_id = %s
            """,
            (source_id,),
        )
        rows = cur.fetchall()
    return {str(r["id"]): (str(r["parent_id"]) if r["parent_id"] else None) for r in rows}


def _load_node_path(connection: Connection, *, node_id: str) -> str | None:
    with connection.cursor() as cur:
        cur.execute(
            "select node_path from public.curriculum_nodes where id = %s",
            (node_id,),
        )
        row = cur.fetchone()
    return row["node_path"] if row else None


def _load_chunks_for_node(connection: Connection, *, node_id: str) -> list[RetrievedChunk]:
    with connection.cursor() as cur:
        cur.execute(
            f"""
            select
{CHUNK_COLUMNS_SQL},
              %s as score
            from public.chunks c
            join public.documents d on d.id = c.document_id
            left join public.section_blocks sb on sb.id = c.section_block_id
            where c.curriculum_node_id = %s
            order by c.chunk_index
            """,
            (_AUGMENT_SCORE, node_id),
        )
        rows = cur.fetchall()
    return [chunk_from_row(row, score=_AUGMENT_SCORE) for row in rows]


def _blocks_as_chunks(
    *,
    blocks_by_path: dict[str, list],
    node_path: str,
    subject: str | None,
    template: RetrievedChunk,
) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for idx, block in enumerate(blocks_by_path.get(node_path, ())):
        if not is_renderable(block, subject=subject):
            continue
        text = render_block(block)
        out.append(
            RetrievedChunk(
                chunk_id=f"block:{node_path}:{block.page}:{idx}",
                content=text,
                score=_BLOCK_SCORE,
                subject=template.subject,
                grade=template.grade,
                language=template.language,
                curriculum_node_id=template.curriculum_node_id,
                metadata={"synthetic": "content_block", "kind": block.kind},
                citation=Citation(
                    document_id=template.citation.document_id,
                    source_id=template.citation.source_id,
                    title=template.citation.title,
                    page_start=block.page or template.citation.page_start,
                    page_end=block.page or template.citation.page_end,
                    citation_label=template.citation.citation_label,
                    source_tier=template.citation.source_tier,
                ),
            )
        )
    return out


def _merge_pools(
    augmented: list[RetrievedChunk],
    ranked: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """Owning-node material first, then fused rank order; dedupe by chunk_id."""
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for chunk in (*augmented, *ranked):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
    return merged


def apply_structural_augmentation(
    connection: Connection,
    *,
    query: str,
    candidates: list[RetrievedChunk],
    node_policy: NodeResolverPolicy = "top1",
    resolver_top_n: int = 8,
    confidence_floor: float = 0.15,
) -> StructuralAugmentResult:
    """Merge owning-node chunks + blocks into the candidate pool when resolution succeeds."""
    if not candidates:
        return StructuralAugmentResult(candidates=candidates, applied=False, skip_reason="empty_pool")

    source_id = candidates[0].citation.source_id
    subject = candidates[0].subject
    node_titles = _load_node_titles(connection, source_id=source_id)
    parent_by_node = _load_parent_map(connection, source_id=source_id)

    hint_id = enumeration_node_hint(query, node_titles)
    if hint_id:
        node_id = hint_id
    else:
        resolution = resolve_owning_node(
            query=query,
            chunks=candidates,
            policy=node_policy,
            top_n=resolver_top_n,
            confidence_floor=confidence_floor,
            node_titles=node_titles,
            parent_by_node=parent_by_node,
        )
        if resolution.primary_node_id is None:
            return StructuralAugmentResult(
                candidates=candidates,
                applied=False,
                skip_reason=resolution.skipped_reason or "no_resolved_node",
            )
        node_id = resolution.primary_node_id
    node_path = _load_node_path(connection, node_id=node_id)
    node_chunks = _load_chunks_for_node(connection, node_id=node_id)[:_MAX_NODE_INJECT_CHUNKS]
    if not node_chunks and node_path:
        blocks_map = fetch_blocks_by_node_path(connection, node_ids=[node_id])
        template = candidates[0]
        block_chunks = _blocks_as_chunks(
            blocks_by_path=blocks_map,
            node_path=node_path,
            subject=subject,
            template=template,
        )
        if not block_chunks:
            return StructuralAugmentResult(
                candidates=candidates,
                applied=False,
                skip_reason="owning_node_empty",
                node_id=node_id,
                node_path=node_path,
            )
        merged = _merge_pools(block_chunks[:_MAX_BLOCK_INJECT], candidates)
        return StructuralAugmentResult(
            candidates=merged,
            applied=True,
            node_id=node_id,
            node_path=node_path,
            node_chunk_count=0,
            block_chunk_count=len(block_chunks[:_MAX_BLOCK_INJECT]),
            injected_chunks=tuple(block_chunks[:_MAX_BLOCK_INJECT]),
        )

    blocks_map = fetch_blocks_by_node_path(connection, node_ids=[node_id])
    template = node_chunks[0]
    block_chunks = _blocks_as_chunks(
        blocks_by_path=blocks_map,
        node_path=node_path or "",
        subject=subject,
        template=template,
    )
    augmented = [*node_chunks, *block_chunks[:_MAX_BLOCK_INJECT]]
    merged = _merge_pools(augmented, candidates)
    return StructuralAugmentResult(
        candidates=merged,
        applied=True,
        node_id=node_id,
        node_path=node_path,
        node_chunk_count=len(node_chunks),
        block_chunk_count=len(block_chunks[:_MAX_BLOCK_INJECT]),
        injected_chunks=tuple(augmented),
    )
