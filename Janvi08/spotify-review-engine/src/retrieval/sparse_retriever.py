"""BM25 sparse retrieval over indexed review chunks."""

from __future__ import annotations

import logging
import re
from typing import Any

import chromadb
from rank_bm25 import BM25Okapi

from src.embedding.config import CHROMA_PATH, COLLECTION_NAME
from src.retrieval.config import SPARSE_TOP_K

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class SparseRetriever:
    """BM25 keyword retrieval over the same corpus as the Chroma index."""

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        path = str(chroma_path or CHROMA_PATH)
        client = chromadb.PersistentClient(path=path)
        collection = client.get_collection(collection_name)
        payload = collection.get(include=["documents", "metadatas"])

        self.chunk_ids: list[str] = payload["ids"]
        self.documents: list[str] = payload["documents"]
        self.metadatas: list[dict[str, Any]] = payload["metadatas"]

        corpus_tokens = [tokenize(doc or "") for doc in self.documents]
        self.bm25 = BM25Okapi(corpus_tokens)
        self._id_to_index = {chunk_id: index for index, chunk_id in enumerate(self.chunk_ids)}
        logger.info("SparseRetriever ready (BM25 over %d chunks)", len(self.chunk_ids))

    def search(self, query: str, top_k: int = SPARSE_TOP_K) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        ranked_indices = [index for index in ranked_indices if scores[index] > 0][:top_k]

        hits: list[dict[str, Any]] = []
        for index in ranked_indices:
            hits.append(
                {
                    "chunk_id": self.chunk_ids[index],
                    "text": self.documents[index],
                    "metadata": self.metadatas[index] or {},
                    "bm25_score": float(scores[index]),
                }
            )
        return hits
