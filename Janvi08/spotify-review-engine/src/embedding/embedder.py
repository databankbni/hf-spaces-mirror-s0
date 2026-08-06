"""BGE embedding wrapper using sentence-transformers."""

from __future__ import annotations

import logging
from typing import Sequence

from sentence_transformers import SentenceTransformer

from src.embedding.config import EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class BGEEmbedder:
    """Generate dense embeddings with BAAI/bge-small-en-v1.5."""

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        logger.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.batch_size = EMBEDDING_BATCH_SIZE

    def embed_texts(self, texts: Sequence[str], batch_size: int | None = None) -> list[list[float]]:
        if not texts:
            return []

        batch_size = batch_size or self.batch_size
        logger.info("Embedding %d texts (batch_size=%d)", len(texts), batch_size)

        vectors = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > batch_size,
        )
        return vectors.tolist()
