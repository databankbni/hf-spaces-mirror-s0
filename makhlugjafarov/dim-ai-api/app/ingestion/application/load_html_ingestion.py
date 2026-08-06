"""Persist an HTML-road :class:`HtmlIngestion` to Postgres.

By default this writer lands the document, pages, clean curriculum tree and
node-tagged chunks (everything Learning needs to navigate and render). Pass an
embedder when the same load must also make the HTML book visible to ``/chat``.

Re-running is idempotent per document (``_clear_document_derived_data`` wipes the
prior chunks/sections/tree first). Because deleting chunks cascades to
``chunk_embeddings``, callers that need chat coverage should embed in the same
load call.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.ingestion.application.html_ingestion import HtmlIngestion
from app.ingestion.application.load_ingestion import (
    IngestionLoadError,
    _clear_document_derived_data,
    _finish_ingestion_run,
    _mark_document_ready,
    _upsert_embeddings,
    _upsert_chunks,
    _upsert_curriculum_nodes,
    _upsert_document,
    _upsert_pages,
)
from app.platform.embeddings import TextEmbedder
from app.platform.embeddings_contract import _assert_embedding_contract, EmbeddingContractError

_CHUNKING_POLICY_ID = "dim-page-section-v1"


@dataclass(frozen=True)
class HtmlLoadResult:
    run_id: str
    document_id: str
    source_id: str
    nodes_total: int
    chunks_total: int
    chunks_embedded: int
    pages_total: int


def _create_html_run(
    connection,
    *,
    corpus_version: str,
    ingestion: HtmlIngestion,
    embedder: TextEmbedder | None,
) -> str:
    source_id = ingestion.document.source.source_id
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.ingestion_runs (
              corpus_version, status, embedding_model_id, chunking_policy_id,
              documents_total, pages_total, chunks_created, duplicate_chunks_skipped,
              metadata
            )
            values (%s, 'running', %s, %s, 1, %s, %s, 0, %s)
            returning id
            """,
            (
                corpus_version,
                embedder.spec.id if embedder else None,
                _CHUNKING_POLICY_ID,
                len(ingestion.document.pages),
                len(ingestion.chunks),
                Jsonb(
                    {
                        "road": "dim_html",
                        "source_id": source_id,
                        "embeddings": "loaded" if embedder else "deferred",
                    }
                ),
            ),
        )
        return str(cursor.fetchone()["id"])


def load_html_ingestion_to_postgres(
    *,
    database_url: str,
    ingestion: HtmlIngestion,
    corpus_version: str,
    embedder: TextEmbedder | None = None,
) -> HtmlLoadResult:
    document = ingestion.document
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            if embedder is not None:
                try:
                    _assert_embedding_contract(connection, embedder)
                except EmbeddingContractError as exc:
                    raise IngestionLoadError(str(exc)) from exc
            with connection.transaction():
                run_id = _create_html_run(
                    connection,
                    corpus_version=corpus_version,
                    ingestion=ingestion,
                    embedder=embedder,
                )
                document_id = _upsert_document(connection, document)
                _upsert_pages(connection, document_id=document_id, document=document)
                _clear_document_derived_data(connection, document_id=document_id)
                node_path_to_uuid = _upsert_curriculum_nodes(
                    connection, document_id=document_id, nodes=document.curriculum_nodes
                )
                chunk_ids = _upsert_chunks(
                    connection,
                    document_id=document_id,
                    chunks=ingestion.chunks,
                    node_path_to_uuid=node_path_to_uuid,
                )
                chunks_embedded = 0
                if embedder is not None:
                    chunks_embedded = _upsert_embeddings(
                        connection,
                        chunk_ids=chunk_ids,
                        chunks=ingestion.chunks,
                        embedder=embedder,
                    )
                _mark_document_ready(connection, document_id=document_id)
                _finish_ingestion_run(
                    connection, run_id=run_id, chunks_embedded=chunks_embedded
                )
    except psycopg.Error as exc:
        raise IngestionLoadError(f"Could not load HTML ingestion into Postgres: {exc}") from exc

    return HtmlLoadResult(
        run_id=run_id,
        document_id=document_id,
        source_id=document.source.source_id,
        nodes_total=len(document.curriculum_nodes),
        chunks_total=len(ingestion.chunks),
        chunks_embedded=chunks_embedded,
        pages_total=len(document.pages),
    )
