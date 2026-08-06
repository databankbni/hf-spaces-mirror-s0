"""Dense semantic retrieval via ChromaDB cosine similarity."""

from __future__ import annotations

import logging
from typing import Any

import chromadb

from src.embedding.config import CHROMA_PATH, COLLECTION_NAME
from src.embedding.embedder import BGEEmbedder
from src.retrieval.config import DENSE_TOP_K

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Query the ChromaDB index with BGE-small embeddings."""

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str = COLLECTION_NAME,
        embedder: BGEEmbedder | None = None,
    ) -> None:
        path = str(chroma_path or CHROMA_PATH)
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_collection(collection_name)
        self.embedder = embedder or BGEEmbedder()
        logger.info("DenseRetriever ready (%d vectors)", self.collection.count())

    def embed_query(self, query: str) -> list[float]:
        try:
            vector = self.embedder.model.encode(
                [query],
                normalize_embeddings=True,
                prompt_name="query",
            )
        except TypeError:
            vector = self.embedder.model.encode([query], normalize_embeddings=True)
        return vector[0].tolist()

    def search(self, query: str, top_k: int = DENSE_TOP_K) -> list[dict[str, Any]]:
        query_embedding = self.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "text": document,
                    "metadata": metadata or {},
                    "dense_distance": distance,
                    "dense_similarity": 1.0 - distance,
                }
            )
        return hits
