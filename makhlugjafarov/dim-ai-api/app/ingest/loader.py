"""
app/ingest/loader.py — thin re-export shim (CP5).

All logic has moved to the Ingestion bounded context:
  - load_ingestion_to_postgres -> app.ingestion.application.load_ingestion

This shim preserves back-compat for any code that still imports from app.ingest.loader.
Do not add new logic here.
"""
from __future__ import annotations

from app.ingestion.application.load_ingestion import (
    IngestionLoadError as IngestionLoadError,
    LoadedIngestion as LoadedIngestion,
    load_ingestion_to_postgres as load_ingestion_to_postgres,
    load_ingestion_with_connection as load_ingestion_with_connection,
    _create_ingestion_run as _create_ingestion_run,
    _upsert_document as _upsert_document,
    _upsert_pages as _upsert_pages,
    _upsert_chunks as _upsert_chunks,
    _upsert_embeddings as _upsert_embeddings,
    _insert_warnings as _insert_warnings,
    _mark_document_ready as _mark_document_ready,
    _finish_ingestion_run as _finish_ingestion_run,
    _page_content_hash as _page_content_hash,
)

__all__ = [
    "IngestionLoadError",
    "LoadedIngestion",
    "load_ingestion_to_postgres",
    "load_ingestion_with_connection",
]
