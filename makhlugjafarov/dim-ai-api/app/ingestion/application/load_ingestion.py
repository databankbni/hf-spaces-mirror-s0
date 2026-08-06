from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.ingestion.domain.curriculum import CURRICULUM_NODE_PATH_KEY
from app.ingestion.domain.models import (
    Chunk,
    CorpusManifest,
    CurriculumNode,
    IngestionWarning,
    ParsedDocument,
    SectionBlock,
)
from app.ingestion.domain.section_network import remap_section_network_ids
from app.platform.embeddings import EmbeddingError, TextEmbedder, validate_embedding
from app.platform.embeddings_contract import _assert_embedding_contract, EmbeddingContractError
from app.platform.vectors import _vector_literal


class IngestionLoadError(RuntimeError):
    """Raised when parsed corpus content cannot be loaded into Postgres."""


@dataclass(frozen=True)
class LoadedIngestion:
    run_id: str
    documents_total: int
    pages_total: int
    chunks_created: int
    chunks_embedded: int
    duplicate_chunks_skipped: int
    warnings_total: int


def load_ingestion_to_postgres(
    *,
    database_url: str,
    manifest_path: Path,
    manifest: CorpusManifest,
    documents: list[ParsedDocument],
    chunks_by_source: dict[str, list[Chunk]],
    duplicate_chunks_skipped: int,
    embedder: TextEmbedder,
) -> LoadedIngestion:
    if manifest.embedding_policy_id != embedder.spec.id:
        raise IngestionLoadError(
            f"Manifest embedding policy {manifest.embedding_policy_id!r} does not match "
            f"embedder contract {embedder.spec.id!r}"
        )

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            return load_ingestion_with_connection(
                connection=connection,
                manifest_path=manifest_path,
                manifest=manifest,
                documents=documents,
                chunks_by_source=chunks_by_source,
                duplicate_chunks_skipped=duplicate_chunks_skipped,
                embedder=embedder,
            )
    except psycopg.Error as exc:
        raise IngestionLoadError(f"Could not load ingestion into Postgres: {exc}") from exc


def load_ingestion_with_connection(
    *,
    connection: Connection,
    manifest_path: Path,
    manifest: CorpusManifest,
    documents: list[ParsedDocument],
    chunks_by_source: dict[str, list[Chunk]],
    duplicate_chunks_skipped: int,
    embedder: TextEmbedder,
) -> LoadedIngestion:
    try:
        _assert_embedding_contract(connection, embedder)
    except EmbeddingContractError as exc:
        raise IngestionLoadError(str(exc)) from exc

    documents_total = len(documents)
    pages_total = sum(len(document.pages) for document in documents)
    chunks_total = sum(len(chunks) for chunks in chunks_by_source.values())
    warnings = [warning for document in documents for warning in document.warnings]

    with connection.transaction():
        run_id = _create_ingestion_run(
            connection,
            manifest_path=manifest_path,
            manifest=manifest,
            embedder=embedder,
            documents_total=documents_total,
            pages_total=pages_total,
            chunks_total=chunks_total,
            duplicate_chunks_skipped=duplicate_chunks_skipped,
        )

        document_ids: dict[str, str] = {}
        chunks_embedded = 0
        for document in documents:
            document_id = _upsert_document(connection, document)
            document_ids[document.source.source_id] = document_id
            _upsert_pages(connection, document_id=document_id, document=document)

            # Clean-slate the document's derived rows before reload. Chunk indices,
            # section ordinals and content hashes all shift when the chunker changes
            # (e.g. page-based → v2 section-based), so a pure upsert would leave a
            # stale tail and could violate the chunks (document_id, content_hash)
            # unique constraint. Deleting first makes re-ingestion idempotent.
            _clear_document_derived_data(connection, document_id=document_id)

            # Segmentation v4 (GRO-156): persist the TOC curriculum tree first so
            # the section/chunk node FKs can be resolved by node_path at insert.
            node_path_to_uuid = _upsert_curriculum_nodes(
                connection, document_id=document_id, nodes=document.curriculum_nodes
            )

            section_hex_to_uuid = _upsert_section_blocks(
                connection,
                document_id=document_id,
                sections=document.sections,
                node_path_to_uuid=node_path_to_uuid,
            )

            doc_chunks = chunks_by_source.get(document.source.source_id, [])
            # Resolve each chunk's section FK from the domain hex id to the DB UUID.
            # chunks.section_block_id is a uuid column, so an unresolved hex would
            # crash the insert; an unmappable id degrades safely to NULL (orphan).
            _resolve_chunk_section_references(doc_chunks, section_hex_to_uuid)

            chunk_ids = _upsert_chunks(
                connection,
                document_id=document_id,
                chunks=doc_chunks,
                node_path_to_uuid=node_path_to_uuid,
            )
            chunks_embedded += _upsert_embeddings(
                connection,
                chunk_ids=chunk_ids,
                chunks=doc_chunks,
                embedder=embedder,
            )
            _mark_document_ready(connection, document_id=document_id)

        _insert_warnings(
            connection,
            run_id=run_id,
            document_ids=document_ids,
            warnings=warnings,
        )
        _finish_ingestion_run(
            connection,
            run_id=run_id,
            chunks_embedded=chunks_embedded,
        )

    return LoadedIngestion(
        run_id=run_id,
        documents_total=documents_total,
        pages_total=pages_total,
        chunks_created=chunks_total,
        chunks_embedded=chunks_embedded,
        duplicate_chunks_skipped=duplicate_chunks_skipped,
        warnings_total=len(warnings),
    )



def _create_ingestion_run(
    connection: Connection,
    *,
    manifest_path: Path,
    manifest: CorpusManifest,
    embedder: TextEmbedder,
    documents_total: int,
    pages_total: int,
    chunks_total: int,
    duplicate_chunks_skipped: int,
) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.ingestion_runs (
              corpus_version,
              manifest_path,
              status,
              embedding_model_id,
              chunking_policy_id,
              documents_total,
              pages_total,
              chunks_created,
              duplicate_chunks_skipped
            )
            values (%s, %s, 'running', %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                manifest.corpus_version,
                str(manifest_path),
                embedder.spec.id,
                manifest.chunking_policy_id,
                documents_total,
                pages_total,
                chunks_total,
                duplicate_chunks_skipped,
            ),
        )
        return str(cursor.fetchone()["id"])


def _upsert_document(connection: Connection, document: ParsedDocument) -> str:
    source = document.source
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.documents (
              source_id,
              title,
              subject,
              grade,
              language,
              curriculum,
              source_type,
              source_category,
              legal_status,
              source_tier,
              review_status,
              source_uri,
              source_version,
              citation_label,
              status,
              metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'processing', %s)
            on conflict (source_id) do update set
              title = excluded.title,
              subject = excluded.subject,
              grade = excluded.grade,
              language = excluded.language,
              curriculum = excluded.curriculum,
              source_type = excluded.source_type,
              source_category = excluded.source_category,
              legal_status = excluded.legal_status,
              source_tier = excluded.source_tier,
              review_status = excluded.review_status,
              source_uri = excluded.source_uri,
              source_version = excluded.source_version,
              citation_label = excluded.citation_label,
              status = 'processing',
              metadata = excluded.metadata
            returning id
            """,
            (
                source.source_id,
                source.title,
                source.subject,
                source.grade,
                source.language,
                source.curriculum,
                source.source_type,
                source.source_category,
                source.legal_status,
                source.source_tier,
                source.review_status,
                source.source_uri,
                source.source_version,
                source.citation_label,
                Jsonb({"notes": source.notes, "owner": source.owner, "publisher": source.publisher}),
            ),
        )
        return str(cursor.fetchone()["id"])


def _upsert_pages(connection: Connection, *, document_id: str, document: ParsedDocument) -> None:
    with connection.cursor() as cursor:
        for page in document.pages:
            cursor.execute(
                """
                insert into public.document_pages (
                  document_id,
                  page_number,
                  text,
                  ocr_confidence,
                  layout_json,
                  content_hash
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (document_id, page_number) do update set
                  text = excluded.text,
                  ocr_confidence = excluded.ocr_confidence,
                  layout_json = excluded.layout_json,
                  content_hash = excluded.content_hash
                """,
                (
                    document_id,
                    page.page_number,
                    page.text,
                    page.ocr_confidence,
                    Jsonb(page.layout_json),
                    _page_content_hash(document.source.source_id, page.page_number, page.text),
                ),
            )


def _clear_document_derived_data(connection: Connection, *, document_id: str) -> None:
    """Remove a document's existing chunks and section_blocks so a re-ingestion
    writes a clean slate. Deleting chunks cascades to chunk_embeddings
    (FK ON DELETE CASCADE). Pages are intentionally left to upsert — their numbering
    is stable across runs, so they carry no stale tail.
    """
    with connection.cursor() as cursor:
        cursor.execute("delete from public.chunks where document_id = %s", (document_id,))
        cursor.execute("delete from public.section_blocks where document_id = %s", (document_id,))
        # curriculum_nodes last: chunks/section_blocks reference it (ON DELETE SET
        # NULL), so they are already gone — this clears the previous tree wholesale.
        cursor.execute("delete from public.curriculum_nodes where document_id = %s", (document_id,))


def _upsert_curriculum_nodes(
    connection: Connection, *, document_id: str, nodes: list[CurriculumNode]
) -> dict[str, str]:
    """Insert the TOC curriculum tree and return a ``node_path → DB UUID`` map.

    Nodes arrive in document order, where a parent always precedes its children
    (the builder appends a chapter before the topics beneath it), so resolving
    ``parent_id`` from the running map needs no second pass. The returned map lets
    the caller wire ``section_blocks``/``chunks`` curriculum FKs by node_path.
    """
    path_to_uuid: dict[str, str] = {}
    if not nodes:
        return path_to_uuid
    with connection.cursor() as cursor:
        for node in nodes:
            parent_id = path_to_uuid.get(node.parent_path) if node.parent_path else None
            cursor.execute(
                """
                insert into public.curriculum_nodes (
                  document_id,
                  parent_id,
                  level,
                  ordinal,
                  title,
                  node_path,
                  page_start,
                  page_end,
                  extraction_method,
                  extraction_confidence,
                  metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (document_id, node_path) do update set
                  parent_id = excluded.parent_id,
                  level = excluded.level,
                  ordinal = excluded.ordinal,
                  title = excluded.title,
                  page_start = excluded.page_start,
                  page_end = excluded.page_end,
                  extraction_method = excluded.extraction_method,
                  extraction_confidence = excluded.extraction_confidence,
                  metadata = excluded.metadata
                returning id
                """,
                (
                    document_id,
                    parent_id,
                    node.level,
                    node.ordinal,
                    node.title,
                    node.node_path,
                    node.page_start,
                    node.page_end,
                    node.extraction_method,
                    node.extraction_confidence,
                    Jsonb(node.metadata),
                ),
            )
            path_to_uuid[node.node_path] = str(cursor.fetchone()["id"])
    return path_to_uuid


def _upsert_section_blocks(
    connection: Connection,
    *,
    document_id: str,
    sections: list[SectionBlock],
    node_path_to_uuid: dict[str, str] | None = None,
) -> dict[str, str]:
    """Insert/update section_blocks and backfill the DB-generated UUID onto each
    SectionBlock.id. Returns a map from the domain hex id (e.g. "sec-abc123…") to
    the DB UUID so chunk.section_block_id FKs can be resolved before chunk insert.

    ``curriculum_node_id`` (GRO-156) is resolved from the section's
    ``curriculum_node_path`` metadata; an absent/unmappable path degrades to NULL.
    """
    node_path_to_uuid = node_path_to_uuid or {}
    hex_to_uuid: dict[str, str] = {}
    if not sections:
        return hex_to_uuid
    with connection.cursor() as cursor:
        for section in sections:
            old_id = section.id
            curriculum_node_id = _curriculum_node_id_for(section.metadata, node_path_to_uuid)
            cursor.execute(
                """
                insert into public.section_blocks (
                  document_id,
                  curriculum_node_id,
                  ordinal,
                  section_title,
                  page_start,
                  page_end,
                  content,
                  content_hash,
                  image_uri,
                  extraction_method,
                  extraction_confidence,
                  metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (document_id, content_hash) do update set
                  curriculum_node_id = excluded.curriculum_node_id,
                  ordinal = excluded.ordinal,
                  section_title = excluded.section_title,
                  page_start = excluded.page_start,
                  page_end = excluded.page_end,
                  content = excluded.content,
                  image_uri = excluded.image_uri,
                  extraction_method = excluded.extraction_method,
                  extraction_confidence = excluded.extraction_confidence,
                  metadata = excluded.metadata
                returning id
                """,
                (
                    document_id,
                    curriculum_node_id,
                    section.ordinal,
                    section.section_title,
                    section.page_start,
                    section.page_end,
                    section.content,
                    section.content_hash,
                    section.image_uri,
                    section.extraction_method,
                    section.extraction_confidence,
                    Jsonb(section.metadata),
                ),
            )
            new_uuid = str(cursor.fetchone()["id"])
            if old_id:
                hex_to_uuid[old_id] = new_uuid
            section.id = new_uuid

        for section in sections:
            remap_section_network_ids(section.metadata, hex_to_uuid)
            cursor.execute(
                """
                update public.section_blocks
                   set metadata = %s
                 where id = %s
                """,
                (Jsonb(section.metadata), section.id),
            )
    return hex_to_uuid


def _resolve_chunk_section_references(chunks: list[Chunk], section_id_map: dict[str, str]) -> None:
    for chunk in chunks:
        remap_section_network_ids(chunk.metadata, section_id_map)
        if chunk.section_block_id:
            chunk.section_block_id = section_id_map.get(chunk.section_block_id)


def _curriculum_node_id_for(
    metadata: dict[str, object], node_path_to_uuid: dict[str, str]
) -> str | None:
    """Resolve a section/chunk's ``curriculum_node_path`` metadata to a DB UUID."""
    node_path = metadata.get(CURRICULUM_NODE_PATH_KEY)
    if isinstance(node_path, str):
        return node_path_to_uuid.get(node_path)
    return None


def _upsert_chunks(
    connection: Connection,
    *,
    document_id: str,
    chunks: list[Chunk],
    node_path_to_uuid: dict[str, str] | None = None,
) -> list[str]:
    node_path_to_uuid = node_path_to_uuid or {}
    chunk_ids: list[str] = []
    with connection.cursor() as cursor:
        for chunk in chunks:
            curriculum_node_id = _curriculum_node_id_for(chunk.metadata, node_path_to_uuid)
            cursor.execute(
                """
                insert into public.chunks (
                  document_id,
                  page_start,
                  page_end,
                  chunk_index,
                  content,
                  content_hash,
                  subject,
                  grade,
                  language,
                  source_category,
                  section_block_id,
                  curriculum_node_id,
                  chunking_policy_id,
                  metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (document_id, chunk_index) do update set
                  page_start = excluded.page_start,
                  page_end = excluded.page_end,
                  content = excluded.content,
                  content_hash = excluded.content_hash,
                  subject = excluded.subject,
                  grade = excluded.grade,
                  language = excluded.language,
                  source_category = excluded.source_category,
                  section_block_id = excluded.section_block_id,
                  curriculum_node_id = excluded.curriculum_node_id,
                  chunking_policy_id = excluded.chunking_policy_id,
                  metadata = excluded.metadata
                returning id
                """,
                (
                    document_id,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.content_hash,
                    chunk.subject,
                    chunk.grade,
                    chunk.language,
                    chunk.source_category,
                    chunk.section_block_id,
                    curriculum_node_id,
                    chunk.chunking_policy_id,
                    Jsonb(chunk.metadata),
                ),
            )
            chunk_ids.append(str(cursor.fetchone()["id"]))
    return chunk_ids


def _upsert_embeddings(
    connection: Connection,
    *,
    chunk_ids: list[str],
    chunks: list[Chunk],
    embedder: TextEmbedder,
) -> int:
    texts = [chunk.content for chunk in chunks]
    vectors = embedder.embed_documents(texts) if texts else []
    if len(vectors) != len(chunk_ids):
        raise EmbeddingError(f"Embedder returned {len(vectors)} vectors for {len(chunk_ids)} chunks")

    with connection.cursor() as cursor:
        for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
            clean_vector = validate_embedding(vector, expected_dimension=embedder.spec.dimension)
            cursor.execute(
                """
                insert into public.chunk_embeddings (chunk_id, embedding_model_id, embedding)
                values (%s, %s, %s::vector)
                on conflict (chunk_id, embedding_model_id) do update set
                  embedding = excluded.embedding,
                  created_at = now()
                """,
                (chunk_id, embedder.spec.id, _vector_literal(clean_vector)),
            )
    return len(vectors)


def _insert_warnings(
    connection: Connection,
    *,
    run_id: str,
    document_ids: dict[str, str],
    warnings: list[IngestionWarning],
) -> None:
    with connection.cursor() as cursor:
        for warning in warnings:
            cursor.execute(
                """
                insert into public.ingestion_warnings (
                  ingestion_run_id,
                  document_id,
                  page_number,
                  severity,
                  code,
                  message,
                  metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    document_ids.get(warning.source_id),
                    warning.page_number,
                    warning.severity,
                    warning.code,
                    warning.message,
                    Jsonb(warning.metadata),
                ),
            )


def _mark_document_ready(connection: Connection, *, document_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "update public.documents set status = 'ready' where id = %s",
            (document_id,),
        )


def _finish_ingestion_run(connection: Connection, *, run_id: str, chunks_embedded: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update public.ingestion_runs
            set status = 'succeeded',
                chunks_embedded = %s,
                completed_at = now()
            where id = %s
            """,
            (chunks_embedded, run_id),
        )


def _page_content_hash(source_id: str, page_number: int, text: str) -> str:
    normalized = " ".join(text.split())
    return sha256(f"{source_id}:page:{page_number}:{normalized}".encode("utf-8")).hexdigest()
