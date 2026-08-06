from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite, sqrt
from typing import Protocol


class EmbeddingError(RuntimeError):
    """Raised when embedding generation or validation fails."""


@dataclass(frozen=True)
class EmbeddingModelSpec:
    id: str = "bge-m3-dim-v1"
    provider: str = "BAAI"
    model_name: str = "BAAI/bge-m3"
    dimension: int = 1024
    normalize_embeddings: bool = True


class TextEmbedder(Protocol):
    spec: EmbeddingModelSpec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per document/chunk text."""

    def embed_query(self, text: str) -> list[float]:
        """Return an embedding for a runtime user query."""


def normalize_vector(vector: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise EmbeddingError("Embedding vector has zero norm")
    return [value / norm for value in vector]


def validate_embedding(vector: list[float], *, expected_dimension: int) -> list[float]:
    if len(vector) != expected_dimension:
        raise EmbeddingError(
            f"Embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}"
        )
    if not all(isfinite(value) for value in vector):
        raise EmbeddingError("Embedding vector contains non-finite values")
    return vector


class BgeM3Embedder:
    """Sentence-transformers backed embedder for the canonical DIM v1 contract."""

    spec = EmbeddingModelSpec()

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "Install ingestion extras to embed with BAAI/bge-m3: "
                "cd apps/api && pip install -e '.[ingestion]'"
            ) from exc
        self._model = SentenceTransformer(self.spec.model_name, device="cpu")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        raw_embeddings = self._model.encode(
            texts,
            normalize_embeddings=self.spec.normalize_embeddings,
            show_progress_bar=False,
        )
        vectors = [
            [float(value) for value in embedding]
            for embedding in raw_embeddings
        ]
        if self.spec.normalize_embeddings:
            vectors = [normalize_vector(vector) for vector in vectors]
        return [
            validate_embedding(vector, expected_dimension=self.spec.dimension)
            for vector in vectors
        ]


@lru_cache(maxsize=1)
def get_bge_m3_embedder() -> BgeM3Embedder:
    return BgeM3Embedder()
