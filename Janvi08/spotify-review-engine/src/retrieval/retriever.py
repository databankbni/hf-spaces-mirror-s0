"""Hybrid retrieval API — dense + BM25 + RRF + cross-encoder re-ranking."""

from __future__ import annotations

import logging
from typing import Any

from dotenv import load_dotenv

from src.retrieval.config import (
    DEFAULT_FINAL_K,
    DENSE_TOP_K,
    FUSION_TOP_K,
    RRF_K,
    SPARSE_TOP_K,
)
from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.sparse_retriever import SparseRetriever

logger = logging.getLogger(__name__)

_retriever_instance: "HybridRetriever | None" = None


def _normalize_hit(hit: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = hit.get("metadata") or {}
    result: dict[str, Any] = {
        "chunk_id": hit.get("chunk_id"),
        "text": hit.get("text"),
        "source": metadata.get("source"),
        "date": metadata.get("date"),
        "rating": metadata.get("rating"),
        "url": metadata.get("url"),
        "thread_or_context": metadata.get("thread_or_context"),
        "parent_id": metadata.get("parent_id"),
        "chunk_index": metadata.get("chunk_index"),
        "chunk_total": metadata.get("chunk_total"),
        "lang": metadata.get("lang"),
    }
    if extra:
        result.update(extra)
    return result


class HybridRetriever:
    """End-to-end hybrid retriever over the Phase 3 Chroma index."""

    def __init__(self) -> None:
        load_dotenv()
        self.dense = DenseRetriever()
        self.sparse = SparseRetriever()
        self.reranker = CrossEncoderReranker()
        self._chunk_cache: dict[str, dict[str, Any]] = {}
        self._build_chunk_cache()

    def _build_chunk_cache(self) -> None:
        for index, chunk_id in enumerate(self.sparse.chunk_ids):
            self._chunk_cache[chunk_id] = {
                "chunk_id": chunk_id,
                "text": self.sparse.documents[index],
                "metadata": self.sparse.metadatas[index] or {},
            }

    def _hydrate_candidates(
        self,
        fused: list[tuple[str, float]],
        dense_hits: list[dict[str, Any]],
        sparse_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dense_by_id = {hit["chunk_id"]: hit for hit in dense_hits}
        sparse_by_id = {hit["chunk_id"]: hit for hit in sparse_hits}

        candidates: list[dict[str, Any]] = []
        for chunk_id, rrf_score in fused:
            base = self._chunk_cache.get(chunk_id)
            if not base:
                continue

            dense_hit = dense_by_id.get(chunk_id, {})
            sparse_hit = sparse_by_id.get(chunk_id, {})
            candidates.append(
                {
                    "chunk_id": chunk_id,
                    "text": base["text"],
                    "metadata": base["metadata"],
                    "dense_similarity": dense_hit.get("dense_similarity"),
                    "bm25_score": sparse_hit.get("bm25_score"),
                    "rrf_score": rrf_score,
                }
            )
        return candidates

    def retrieve(
        self,
        query: str,
        k: int = DEFAULT_FINAL_K,
        *,
        dense_top_k: int = DENSE_TOP_K,
        sparse_top_k: int = SPARSE_TOP_K,
        fusion_top_k: int = FUSION_TOP_K,
    ) -> list[dict[str, Any]]:
        dense_hits = self.dense.search(query, top_k=dense_top_k)
        sparse_hits = self.sparse.search(query, top_k=sparse_top_k)

        dense_ids = [hit["chunk_id"] for hit in dense_hits]
        sparse_ids = [hit["chunk_id"] for hit in sparse_hits]
        fused = reciprocal_rank_fusion([dense_ids, sparse_ids], rrf_k=RRF_K, top_k=fusion_top_k)

        candidates = self._hydrate_candidates(fused, dense_hits, sparse_hits)
        reranked = self.reranker.rerank(query, candidates, top_k=k)

        results: list[dict[str, Any]] = []
        for item in reranked:
            results.append(
                _normalize_hit(
                    item,
                    extra={
                        "dense_similarity": item.get("dense_similarity"),
                        "bm25_score": item.get("bm25_score"),
                        "rrf_score": item.get("rrf_score"),
                        "rerank_score": item.get("rerank_score"),
                        "similarity": item.get("similarity"),
                    },
                )
            )
        return results


def retrieve(query: str, k: int = DEFAULT_FINAL_K) -> list[dict[str, Any]]:
    """Retrieve top-k review chunks for a natural-language query.

    Pipeline: ChromaDB dense search → BM25 sparse search → RRF fusion →
    cross-encoder re-ranking.

    Returns list of dicts with text, metadata (source, date, rating, url,
    thread_or_context), and similarity scores.
    """
    global _retriever_instance
    if _retriever_instance is None:
        logger.info("Initialising HybridRetriever (first call loads models)")
        _retriever_instance = HybridRetriever()
    return _retriever_instance.retrieve(query, k=k)
