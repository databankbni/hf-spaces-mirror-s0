"""ChromaDB vector store for review chunk embeddings."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

import chromadb

from src.embedding.config import CHROMA_PATH, COLLECTION_NAME

logger = logging.getLogger(__name__)

_METADATA_STRING_FIELDS = ("source", "date", "url", "thread_or_context", "parent_id", "chunk_id", "lang")
_METADATA_INT_FIELDS = ("chunk_index", "chunk_total")
_METADATA_FLOAT_FIELDS = ("rating", "relevance_confidence")
_METADATA_BOOL_FIELDS = ("relevant",)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """ChromaDB metadata values must be scalar types; nulls are omitted."""
    clean: dict[str, str | int | float | bool] = {}

    for key in _METADATA_STRING_FIELDS:
        value = metadata.get(key)
        if value is not None and value != "":
            clean[key] = str(value)

    for key in _METADATA_INT_FIELDS:
        value = metadata.get(key)
        if value is not None:
            clean[key] = int(value)

    for key in _METADATA_FLOAT_FIELDS:
        value = metadata.get(key)
        if value is not None:
            clean[key] = float(value)

    for key in _METADATA_BOOL_FIELDS:
        value = metadata.get(key)
        if value is not None:
            clean[key] = bool(value)

    return clean


class ReviewVectorStore:
    """Persistent ChromaDB collection for embedded review chunks."""

    def __init__(
        self,
        persist_path: Path | str = CHROMA_PATH,
        collection_name: str = COLLECTION_NAME,
        reset: bool = False,
    ) -> None:
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        if reset:
            logger.info("Resetting collection: %s", collection_name)
            try:
                self.client.delete_collection(collection_name)
            except Exception:
                pass

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.collection_name = collection_name

    def upsert_chunks(
        self,
        chunk_records: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        if len(chunk_records) != len(embeddings):
            raise ValueError("chunk_records and embeddings length mismatch")

        if not chunk_records:
            return 0

        ids = [record["chunk_id"] for record in chunk_records]
        documents = [record.get("text", "") for record in chunk_records]
        metadatas = [_sanitize_metadata(record) for record in chunk_records]

        self.collection.upsert(
            ids=ids,
            embeddings=list(embeddings),
            documents=documents,
            metadatas=metadatas,
        )
        return len(ids)

    def count(self) -> int:
        return self.collection.count()
