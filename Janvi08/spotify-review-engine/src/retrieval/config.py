"""Centralised constants for Phase 4 retrieval and ranking."""

from pathlib import Path

from src.embedding.config import CHROMA_PATH, COLLECTION_NAME, EMBEDDING_MODEL

# Retrieval pool sizes
DENSE_TOP_K = 10
SPARSE_TOP_K = 10
FUSION_TOP_K = 10

# Reciprocal Rank Fusion constant (standard default)
RRF_K = 60

# Re-ranker
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_FINAL_K = 5

# Paths (read-only — Phase 3 outputs are not modified)
CHUNKS_PATH = Path("data/output/chunks.jsonl")
