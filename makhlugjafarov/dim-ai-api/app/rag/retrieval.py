from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.rag.embeddings import TextEmbedder, validate_embedding
from app.platform.embeddings_contract import _assert_embedding_contract, EmbeddingContractError
from app.platform.vectors import _vector_literal
from app.retrieval.domain.context_packer import _pack_context, PackedContext
from app.retrieval.domain.tier_conflict import _detect_tier_conflict


ChatMode = Literal["subject_tutor", "dim_coach"]

# Seconds to wait for a DB connection before giving up. Keeps the query path
# fail-fast so an unreachable database returns 503 rather than hanging a worker.
_DB_CONNECT_TIMEOUT_SECONDS = 5

# Empirical threshold for weak-context detection. Scores from the 2026-06-06
# math eval showed bad/hallucinated answers at 0.53–0.54 and good answers at
# ≥0.70. 0.62 sits cleanly between those clusters — queries with no real corpus
# match fall below it and are declined honestly instead of generating a
# hallucinated "textbook-grounded" answer.
_WEAK_CONTEXT_THRESHOLD = 0.62


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot safely run."""


@dataclass(frozen=True)
class RetrievalFilters:
    subject: str | None = None
    grade: int | None = None
    language: str | None = None

    @property
    def has_filters(self) -> bool:
        return bool(self.subject or self.grade is not None or self.language)


@dataclass(frozen=True)
class Citation:
    document_id: str
    source_id: str
    title: str
    page_start: int
    page_end: int
    citation_label: str
    source_tier: int = 3  # 1=official_textbook … 5=student_telemetry


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    subject: str
    grade: int | None
    language: str
    citation: Citation
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    weak_context: bool
    filters: RetrievalFilters
    filters_relaxed: bool = False
    tier_conflict: bool = False  # True when chunks span both tier ≤2 and tier ≥3 sources
    candidates: list[RetrievedChunk] = field(default_factory=list)
    query_embedding_model_id: str = ""

    @property
    def citations(self) -> list[Citation]:
        seen: set[tuple[str, int, int]] = set()
        citations: list[Citation] = []
        for chunk in self.chunks:
            key = (
                chunk.citation.document_id,
                chunk.citation.page_start,
                chunk.citation.page_end,
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(chunk.citation)
        return citations



def retrieve_context(
    *,
    database_url: str,
    query: str,
    embedder: TextEmbedder,
    filters: RetrievalFilters | None = None,
    mode: ChatMode = "subject_tutor",
    top_k: int = 8,
    candidate_count: int = 30,
    min_score: float = _WEAK_CONTEXT_THRESHOLD,
    max_context_chars: int = 12000,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> RetrievalResult:
    filters = filters or RetrievalFilters()
    if mode == "subject_tutor" and not filters.subject:
        raise ValueError(
            "retrieve_context: mode='subject_tutor' requires filters.subject to be set"
        )
    query_embedding = validate_embedding(
        embedder.embed_query(query),
        expected_dimension=embedder.spec.dimension,
    )

    # Bound the connect attempt so an unreachable DB fails fast (→ RetrievalError →
    # HTTP 503) instead of hanging a threadpool worker indefinitely. Without this,
    # repeated hung queries starve the worker pool and even /health stops responding
    # (observed on the HF Space when DIM_AI_API_DATABASE_URL pointed at the IPv6-only
    # direct host that HF's IPv4-only egress cannot reach).
    try:
        connection_cm = psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=_DB_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.OperationalError as exc:
        # Unreachable / unauthenticated DB — surface as RetrievalError so the query
        # use-case returns 503, not a 500 or an indefinite hang.
        raise RetrievalError(f"database connection failed: {exc.__class__.__name__}") from exc

    with connection_cm as connection:
        try:
            _assert_embedding_contract(connection, embedder)
        except EmbeddingContractError as exc:
            raise RetrievalError(str(exc)) from exc
        chunks = _search_chunks(
            connection,
            query_embedding=query_embedding,
            embedder=embedder,
            filters=filters,
            limit=candidate_count,
        )
        filters_relaxed = False
        if not chunks and filters.has_filters:
            relaxed_filters = RetrievalFilters(
                subject=filters.subject,    # keep subject
                language=filters.language,  # keep language
                # grade is intentionally dropped
            )
            chunks = _search_chunks(
                connection,
                query_embedding=query_embedding,
                embedder=embedder,
                filters=relaxed_filters,
                limit=candidate_count,
            )
            filters_relaxed = True

        selected = _pack_context(chunks[:top_k], max_chars=max_context_chars).chunks
        weak_context = not selected or selected[0].score < min_score
        tier_conflict = _detect_tier_conflict(selected)
        result = RetrievalResult(
            query=query,
            chunks=selected,
            weak_context=weak_context,
            filters=filters,
            filters_relaxed=filters_relaxed,
            tier_conflict=tier_conflict,
            candidates=chunks,
            query_embedding_model_id=embedder.spec.id,
        )

    return result



def _search_chunks(
    connection,
    *,
    query_embedding: list[float],
    embedder: TextEmbedder,
    filters: RetrievalFilters,
    limit: int,
) -> list[RetrievedChunk]:
    clauses = [
        "ce.embedding_model_id = %s",
        "d.status = 'ready'",
        "d.legal_status != 'do_not_ingest'",
        "coalesce((c.metadata->>'quarantined')::boolean, false) = false",
    ]
    params: list[object] = [embedder.spec.id]
    if filters.subject:
        clauses.append("c.subject = %s")
        params.append(filters.subject)
    if filters.grade is not None:
        clauses.append("c.grade = %s")
        params.append(filters.grade)
    if filters.language:
        clauses.append("c.language = %s")
        params.append(filters.language)

    vector = _vector_literal(query_embedding)
    params = [vector, *params, vector, limit]
    where_sql = " and ".join(clauses)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            select
              c.id as chunk_id,
              c.content,
              c.page_start,
              c.page_end,
              c.subject,
              c.grade,
              c.language,
              c.metadata,
              d.id as document_id,
              d.source_id,
              d.title,
              d.citation_label,
              d.source_tier,
              1 - (ce.embedding <=> %s::vector) as score
            from public.chunk_embeddings ce
            join public.chunks c on c.id = ce.chunk_id
            join public.documents d on d.id = c.document_id
            where {where_sql}
            order by ce.embedding <=> %s::vector asc, d.source_tier asc
            limit %s
            """,
            params,
        )
        rows = cursor.fetchall()

    return [
        RetrievedChunk(
            chunk_id=str(row["chunk_id"]),
            content=row["content"],
            score=float(row["score"]),
            subject=row["subject"],
            grade=row["grade"],
            language=row["language"],
            metadata=row["metadata"] or {},
            citation=Citation(
                document_id=str(row["document_id"]),
                source_id=row["source_id"],
                title=row["title"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                citation_label=row["citation_label"],
                source_tier=int(row["source_tier"]),
            ),
        )
        for row in rows
    ]
