"""Cross-encoder re-ranking for fused retrieval candidates."""

from __future__ import annotations

import logging
import math
from typing import Any

from sentence_transformers import CrossEncoder

from src.retrieval.config import RERANKER_MODEL

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Re-score candidate passages with ms-marco-MiniLM-L-6-v2."""

    def __init__(self, model_name: str = RERANKER_MODEL) -> None:
        logger.info("Loading cross-encoder: %s", model_name)
        self.model = CrossEncoder(model_name)
        self.model_name = model_name

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        pairs = [(query, candidate.get("text", "")) for candidate in candidates]
        raw_scores = [float(score) for score in self.model.predict(pairs)]

        max_score = max(raw_scores)
        exp_scores = [math.exp(score - max_score) for score in raw_scores]
        exp_total = sum(exp_scores) or 1.0
        normalized = [exp_score / exp_total for exp_score in exp_scores]

        scored: list[dict[str, Any]] = []
        for candidate, raw_score, similarity in zip(candidates, raw_scores, normalized):
            enriched = dict(candidate)
            enriched["rerank_score"] = raw_score
            enriched["similarity"] = similarity
            scored.append(enriched)

        scored.sort(key=lambda item: item["rerank_score"], reverse=True)
        return scored[:top_k]
