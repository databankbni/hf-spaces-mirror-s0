"""Orchestrator for the curriculum outline / navigation read (GRO-158).

The companion to :func:`get_topic_slice`: before a module can ask for a topic, it
needs to *see* the topics. This returns the book's whole curriculum as a navigable
outline (syllabus order, page spans, per-node chunk counts, coverage) — the map an
LLM agent reads to decide what to pull.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.curriculum.domain.models import CurriculumOutline, TopicSliceError
from app.curriculum.infrastructure.postgres_curriculum_reader import (
    count_document_chunks,
    fetch_outline_nodes,
    resolve_document,
)
from app.query.domain.subject_selector import retrieval_subject

_DB_CONNECT_TIMEOUT_SECONDS = 5


def get_curriculum_outline(
    *,
    database_url: str,
    subject: str | None = None,
    source_id: str | None = None,
) -> CurriculumOutline:
    """Resolve a book (by ``source_id`` or canonical ``subject``) and map its tree."""
    if not (source_id or subject):
        raise TopicSliceError("get_curriculum_outline requires source_id or subject")

    canonical = retrieval_subject(subject) if subject else None

    try:
        connection_cm = psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=_DB_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.OperationalError as exc:
        raise TopicSliceError(f"database connection failed: {exc.__class__.__name__}") from exc

    with connection_cm as connection:
        document = resolve_document(connection, source_id=source_id, subject=canonical)
        nodes = fetch_outline_nodes(connection, document_id=document["id"])
        total_chunks, tagged_chunks = count_document_chunks(connection, document_id=document["id"])

    return CurriculumOutline(
        source_id=document["source_id"],
        subject=document["subject"],
        nodes=tuple(nodes),
        node_count=len(nodes),
        max_depth=max((n.level for n in nodes), default=0),
        total_chunks=total_chunks,
        tagged_chunks=tagged_chunks,
    )
