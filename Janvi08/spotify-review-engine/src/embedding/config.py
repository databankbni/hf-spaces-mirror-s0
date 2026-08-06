"""Centralised constants for Phase 3 embedding and indexing."""

from pathlib import Path

# Chunking (aligned with BGE-small-en-v1.5 context window)
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
MAX_CHUNKS_PER_RECORD = 20

# Embedding model
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_BATCH_SIZE = 32

# Vector store
CHROMA_PATH = Path("data/index/chroma")
COLLECTION_NAME = "spotify_reviews"

# Default I/O paths
DEFAULT_INPUT = Path("data/output/reviews_clean.jsonl")
DEFAULT_CHUNKS_OUTPUT = Path("data/output/chunks.jsonl")
DEFAULT_META_OUTPUT = Path("data/output/phase3_meta.json")


class ConfigError(ValueError):
    """Raised when embedding/indexing configuration is invalid."""


def validate_chunk_config(
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> None:
    if overlap >= chunk_size:
        raise ConfigError(
            f"CHUNK_OVERLAP_TOKENS ({overlap}) must be less than "
            f"CHUNK_SIZE_TOKENS ({chunk_size})"
        )
    if chunk_size <= 0 or overlap < 0:
        raise ConfigError("chunk_size must be positive and overlap must be non-negative")
