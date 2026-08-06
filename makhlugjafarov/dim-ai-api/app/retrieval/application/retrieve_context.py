from __future__ import annotations

from typing import TYPE_CHECKING

import psycopg
from psycopg.rows import dict_row

if TYPE_CHECKING:
    from psycopg import Connection

from app.platform.embeddings import TextEmbedder, validate_embedding
from app.platform.embeddings_contract import _assert_embedding_contract, EmbeddingContractError
from app.platform.config import get_settings
from app.retrieval.application.structural_augment import apply_structural_augmentation
from app.retrieval.domain.context_packer import _pack_context
from app.retrieval.domain.fusion import fuse_retrieved_chunks
from app.retrieval.domain.query_intent import enumeration_lexical_query, is_enumeration_intent
from app.retrieval.domain.tier_conflict import _detect_tier_conflict
from app.retrieval.domain.models import ChatMode, RetrievalError, RetrievalFilters, RetrievalResult, RetrievedChunk
from app.retrieval.domain.retrieval_params import DEFAULT_RETRIEVAL_PARAMS
from app.retrieval.infrastructure.postgres_lexical import search_lexical
from app.retrieval.infrastructure.postgres_retriever import _search_chunks

_DB_CONNECT_TIMEOUT_SECONDS = 5
_PARAMS = DEFAULT_RETRIEVAL_PARAMS
_MAX_INJECTED_FOR_PACK = 6

def retrieve_context(
    *,
    database_url: str | None = None,
    query: str,
    embedder: TextEmbedder,
    filters: RetrievalFilters | None = None,
    mode: ChatMode = "subject_tutor",
    top_k: int = _PARAMS.default_top_k,
    candidate_count: int = _PARAMS.candidate_count,
    min_score: float = _PARAMS.min_score,
    max_context_chars: int = _PARAMS.max_context_chars,
    user_id: str | None = None,
    conversation_id: str | None = None,
    enable_lexical: bool = _PARAMS.enable_lexical,
    lexical_candidate_count: int = _PARAMS.lexical_candidate_count,
    rrf_k: int = _PARAMS.rrf_k,
    connection: Connection | None = None,
    verify_embedding_contract: bool = True,
) -> RetrievalResult:
    """Retrieve ranked chunks for ``query``.

    When ``connection`` is supplied the caller owns its lifecycle — used by batch
    eval scripts to avoid opening one connection per question against the pooler.
    """
    # Validate before opening a DB connection so unit tests can assert input errors
    # without a live Postgres (CI: test_subject_tutor_requires_subject).
    resolved_filters = filters or RetrievalFilters()
    if mode == "subject_tutor" and not resolved_filters.subject:
        raise ValueError(
            "retrieve_context: mode='subject_tutor' requires filters.subject to be set"
        )

    if connection is not None:
        return _retrieve_context_on_connection(
            connection,
            query=query,
            embedder=embedder,
            filters=resolved_filters,
            mode=mode,
            top_k=top_k,
            candidate_count=candidate_count,
            min_score=min_score,
            max_context_chars=max_context_chars,
            enable_lexical=enable_lexical,
            lexical_candidate_count=lexical_candidate_count,
            rrf_k=rrf_k,
            verify_embedding_contract=verify_embedding_contract,
        )

    if not database_url:
        raise ValueError("retrieve_context: database_url is required when connection is not supplied")

    try:
        connection_cm = psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=_DB_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.OperationalError as exc:
        raise RetrievalError(f"database connection failed: {exc.__class__.__name__}") from exc

    with connection_cm as owned_connection:
        return _retrieve_context_on_connection(
            owned_connection,
            query=query,
            embedder=embedder,
            filters=resolved_filters,
            mode=mode,
            top_k=top_k,
            candidate_count=candidate_count,
            min_score=min_score,
            max_context_chars=max_context_chars,
            enable_lexical=enable_lexical,
            lexical_candidate_count=lexical_candidate_count,
            rrf_k=rrf_k,
            verify_embedding_contract=verify_embedding_contract,
        )


def _retrieve_context_on_connection(
    connection: Connection,
    *,
    query: str,
    embedder: TextEmbedder,
    filters: RetrievalFilters | None,
    mode: ChatMode,
    top_k: int,
    candidate_count: int,
    min_score: float,
    max_context_chars: int,
    enable_lexical: bool,
    lexical_candidate_count: int,
    rrf_k: int,
    verify_embedding_contract: bool,
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

    if verify_embedding_contract:
        try:
            _assert_embedding_contract(connection, embedder)
        except EmbeddingContractError as exc:
            raise RetrievalError(str(exc)) from exc

    # Dense channel first (unchanged). Its cosine top score is the only
    # calibrated weak-context signal, and it drives the grade-relaxation retry.
    dense_chunks = _search_chunks(
        connection,
        query_embedding=query_embedding,
        embedder=embedder,
        filters=filters,
        limit=candidate_count,
    )
    filters_relaxed = False
    effective_filters = filters
    if not dense_chunks and filters.has_filters:
        effective_filters = RetrievalFilters(
            subject=filters.subject,
            language=filters.language,
        )
        dense_chunks = _search_chunks(
            connection,
            query_embedding=query_embedding,
            embedder=embedder,
            filters=effective_filters,
            limit=candidate_count,
        )
        filters_relaxed = True

    # Lexical channel over the deployed FTS index, fused with dense via RRF
    # (S3a). Same effective filters as dense so the candidate universe matches.
    candidates: list[RetrievedChunk]
    if enable_lexical:
        lexical_chunks = search_lexical(
            connection,
            query=enumeration_lexical_query(query),
            filters=effective_filters,
            limit=lexical_candidate_count,
            variant="fts",
        )
        candidates = fuse_retrieved_chunks([dense_chunks, lexical_chunks], k=rrf_k)
    else:
        candidates = dense_chunks

    pack_pool = candidates[:top_k]
    if get_settings().enable_structural_augmentation and is_enumeration_intent(query):
        augment = apply_structural_augmentation(
            connection,
            query=query,
            candidates=candidates,
            node_policy="document_majority",
        )
        if augment.applied:
            candidates = augment.candidates
            injected = list(augment.injected_chunks[:_MAX_INJECTED_FOR_PACK])
            injected_ids = {chunk.chunk_id for chunk in injected}
            pack_pool = injected + [
                chunk for chunk in candidates if chunk.chunk_id not in injected_ids
            ][:top_k]

    packed = _pack_context(pack_pool, max_chars=max_context_chars)
    selected = packed.chunks
    # Weak-context stays DENSE-gated: `min_score` is a cosine threshold, only
    # meaningful against dense scores. A lexical-only chunk (whose score is a
    # ts_rank, not a cosine) reaching the top of the fused pool must neither
    # silently pass nor fail this gate — so it is judged on the dense top hit,
    # preserving the pre-hybrid refusal/hedge behaviour exactly.
    weak_context = not dense_chunks or dense_chunks[0].score < min_score
    tier_conflict = _detect_tier_conflict(selected)
    return RetrievalResult(
        query=query,
        chunks=selected,
        weak_context=weak_context,
        filters=filters,
        filters_relaxed=filters_relaxed,
        tier_conflict=tier_conflict,
        candidates=candidates,
        query_embedding_model_id=embedder.spec.id,
        packed=packed,
    )
