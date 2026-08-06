"""Orchestrator for the curriculum topic-slice read contract (GRO-158).

The single entry point a module calls: give it a subject/book and a node selector
(path, id, or title) and it returns an LLM-ready :class:`TopicSlice`. This is the
read half of the apex intent — the tree is built and stored (GRO-156), and this
turns a topic reference into prompt-ready structure + text.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.curriculum.domain.models import TopicSlice, TopicSliceError
from app.curriculum.domain.slice_builder import build_topic_slice
from app.curriculum.infrastructure.postgres_curriculum_reader import (
    fetch_ancestors,
    fetch_blocks_by_node_path,
    fetch_chunks_by_node_path,
    fetch_subtree,
    resolve_document,
    resolve_node,
)
from app.query.domain.subject_selector import retrieval_subject

_DB_CONNECT_TIMEOUT_SECONDS = 5


def get_topic_slice(
    *,
    database_url: str,
    subject: str | None = None,
    source_id: str | None = None,
    node_path: str | None = None,
    node_id: str | None = None,
    node_title: str | None = None,
    include_descendants: bool = True,
    include_blocks: bool = True,
    max_chars: int = 12000,
    max_blocks: int = 40,
) -> TopicSlice:
    """Resolve and assemble a topic slice.

    Provide a book via ``source_id`` (preferred) or ``subject`` (aliases are
    canonicalised, ambiguous subjects raise), and a node via exactly one of
    ``node_path`` / ``node_id`` / ``node_title``.
    """
    if not (source_id or subject):
        raise TopicSliceError("get_topic_slice requires source_id or subject")
    if not (node_path or node_id or node_title):
        raise TopicSliceError("get_topic_slice requires node_path, node_id, or node_title")

    canonical = retrieval_subject(subject) if subject else None

    try:
        connection_cm = psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=_DB_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.OperationalError as exc:
        raise TopicSliceError(f"database connection failed: {exc.__class__.__name__}") from exc

    with connection_cm as connection:
        document = resolve_document(connection, source_id=source_id, subject=canonical)
        node = resolve_node(
            connection,
            document_id=document["id"],
            node_path=node_path,
            node_id=node_id,
            node_title=node_title,
        )
        ancestors = fetch_ancestors(connection, node_id=node.node_id)
        subtree = fetch_subtree(connection, node_id=node.node_id)
        descendants = [n for n in subtree if n.node_id != node.node_id]

        scope = subtree if include_descendants else [node]
        scope_ids = [n.node_id for n in scope]
        chunks_by_node_path = fetch_chunks_by_node_path(connection, node_ids=scope_ids)
        blocks_by_node_path = (
            fetch_blocks_by_node_path(connection, node_ids=scope_ids) if include_blocks else None
        )

    return build_topic_slice(
        source_id=document["source_id"],
        subject=document["subject"],
        node=node,
        ancestors=ancestors,
        descendants=descendants,
        chunks_by_node_path=chunks_by_node_path,
        blocks_by_node_path=blocks_by_node_path,
        include_descendants=include_descendants,
        max_chars=max_chars,
        max_blocks=max_blocks,
    )
