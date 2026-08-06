from __future__ import annotations
from typing import TYPE_CHECKING
from psycopg.types.json import Jsonb

if TYPE_CHECKING:
    from app.retrieval.domain.models import RetrievedChunk, ChatMode, RetrievalFilters
    from psycopg import Connection

def store_interaction(
    connection: Connection,
    *,
    user_id: str | None,
    conversation_id: str | None,
    query: str,
    mode: ChatMode,
    query_embedding_model_id: str,
    filters: RetrievalFilters,
    candidates: list[RetrievedChunk],
    selected: list[RetrievedChunk],
    weak_context: bool,
    filters_relaxed: bool,
    confidence: float | None,
    answer: str,
    provider: str | None,
    model: str | None,
    latency_retrieve_ms: int,
    latency_pack_ms: int,
    latency_generate_ms: int,
    latency_total_ms: int,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.retrieval_traces (
              user_id,
              conversation_id,
              query,
              mode,
              query_embedding_model_id,
              subject_filter,
              grade_filter,
              language_filter,
              candidates,
              selected_chunks,
              weak_context,
              metadata,
              confidence,
              answer,
              provider,
              model,
              latency_retrieve_ms,
              latency_pack_ms,
              latency_generate_ms,
              latency_total_ms
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                conversation_id,
                query,
                mode,
                query_embedding_model_id,
                filters.subject,
                filters.grade,
                filters.language,
                Jsonb([_chunk_trace(chunk) for chunk in candidates[:30]]),
                Jsonb([_chunk_trace(chunk) for chunk in selected]),
                weak_context,
                Jsonb({"filters_relaxed": filters_relaxed}),
                confidence,
                answer,
                provider,
                model,
                latency_retrieve_ms,
                latency_pack_ms,
                latency_generate_ms,
                latency_total_ms,
            ),
        )
    connection.commit()

def _chunk_trace(chunk: RetrievedChunk) -> dict[str, object]:
    # chunk_id is the stable identifier for a trace row; if per-trace content
    # versioning is ever needed, join chunks.content_hash by chunk_id offline
    # rather than carrying a hash on the retrieval DTO.
    return {
        "chunk_id": chunk.chunk_id,
        "score": chunk.score,
        "document_id": chunk.citation.document_id,
        "source_id": chunk.citation.source_id,
        "page_start": chunk.citation.page_start,
        "page_end": chunk.citation.page_end,
        "subject": chunk.subject,
    }
