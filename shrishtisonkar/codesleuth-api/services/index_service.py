"""
Index Service — chunk code by AST boundaries, embed with sentence-transformers,
store in a pure-numpy/pickle vector store (no C++ build tools needed).
Disk-persistent per session_id.
"""
import os
import pickle
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer

from config import get_settings
from services.parser_service import FileAST
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Singleton embedding model ─────────────────────────────────────────────────
_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        try:
            # Prefer the local HF cache — avoids network calls (and SSL failures)
            # when the model has already been downloaded.
            _embedder = SentenceTransformer(settings.embedding_model, local_files_only=True)
        except Exception:
            logger.info("Model not in local cache, downloading…")
            _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class CodeChunk:
    chunk_id: str
    file_path: str
    content: str
    language: str
    chunk_type: str    # "function" | "class" | "file_header" | "block"
    line_start: int
    line_end: int


@dataclass
class RetrievedChunk:
    chunk_id: str
    file_path: str
    content: str
    language: str
    relevance_score: float
    line_start: int
    line_end: int


# ── On-disk vector store ──────────────────────────────────────────────────────

class NumpyVectorStore:
    """
    Minimal vector store: embeddings stored as (N, D) float32 numpy array,
    metadata as a list of dicts. Both are pickled to disk.
    Cosine similarity computed via numpy dot product on L2-normalised vectors.
    """

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.vec_file   = store_path / "vectors.npy"
        self.meta_file  = store_path / "metadata.pkl"
        self._vectors:  np.ndarray | None = None     # shape (N, D)
        self._metadata: list[dict] = []

    def _ensure_loaded(self):
        if self._vectors is None:
            self._load()

    def _load(self):
        if self.vec_file.exists() and self.meta_file.exists():
            self._vectors  = np.load(str(self.vec_file))
            with open(self.meta_file, "rb") as f:
                self._metadata = pickle.load(f)
        else:
            self._vectors  = None
            self._metadata = []

    def _save(self):
        self.store_path.mkdir(parents=True, exist_ok=True)
        np.save(str(self.vec_file), self._vectors)
        with open(self.meta_file, "wb") as f:
            pickle.dump(self._metadata, f)

    def upsert(self, embeddings: np.ndarray, metadatas: list[dict]):
        """Add or replace all vectors (full overwrite for simplicity)."""
        # L2-normalise so dot product == cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._vectors  = (embeddings / norms).astype(np.float32)
        self._metadata = metadatas
        self._save()

    def search(self, query_vec: np.ndarray, top_k: int) -> list[tuple[float, dict]]:
        """Returns list of (score, metadata) sorted descending."""
        self._ensure_loaded()
        if self._vectors is None or len(self._metadata) == 0:
            return []

        # Normalise query vector
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm

        # Cosine similarity = dot product of normalised vectors
        scores = self._vectors.dot(query_vec.astype(np.float32))   # shape (N,)
        top_k  = min(top_k, len(scores))
        top_idx = np.argpartition(scores, -top_k)[-top_k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]       # sort descending

        return [(float(scores[i]), self._metadata[i]) for i in top_idx]

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._metadata)


# ── Index service ─────────────────────────────────────────────────────────────

class IndexService:
    def _store_path(self, session_id: str) -> Path:
        return Path(settings.chroma_persist_dir) / session_id

    def _get_store(self, session_id: str) -> NumpyVectorStore:
        return NumpyVectorStore(self._store_path(session_id))

    # ── Chunking ──────────────────────────────────────────────────────────────

    def _chunk_file(self, ast: FileAST, content: str) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        lines = content.splitlines()

        # Function-level chunks
        for func in ast.functions:
            chunk_lines = lines[func.line_start - 1: func.line_end]
            chunk_content = "\n".join(chunk_lines)
            if len(chunk_content.strip()) < 20:
                continue
            chunks.append(CodeChunk(
                chunk_id=f"{ast.path}::func::{func.name}",
                file_path=ast.path,
                content=chunk_content[:2000],
                language=ast.language,
                chunk_type="function",
                line_start=func.line_start,
                line_end=func.line_end,
            ))

        # Class-level chunks
        for cls in ast.classes:
            chunk_lines = lines[cls.line_start - 1: cls.line_end]
            chunk_content = "\n".join(chunk_lines)
            if len(chunk_content.strip()) < 20:
                continue
            chunks.append(CodeChunk(
                chunk_id=f"{ast.path}::class::{cls.name}",
                file_path=ast.path,
                content=chunk_content[:2000],
                language=ast.language,
                chunk_type="class",
                line_start=cls.line_start,
                line_end=cls.line_end,
            ))

        # File header (first ~60 lines) when no functions/classes parsed
        if not chunks:
            header = "\n".join(lines[:min(60, len(lines))])
            if header.strip():
                chunks.append(CodeChunk(
                    chunk_id=f"{ast.path}::header",
                    file_path=ast.path,
                    content=header[:2000],
                    language=ast.language,
                    chunk_type="file_header",
                    line_start=1,
                    line_end=min(60, len(lines)),
                ))

        # Sliding-window fallback for large files with no parsed structure
        if not chunks and len(lines) > 60:
            for i in range(0, len(lines), 50):
                block = "\n".join(lines[i: i + 50])
                if not block.strip():
                    continue
                chunks.append(CodeChunk(
                    chunk_id=f"{ast.path}::block::{i}",
                    file_path=ast.path,
                    content=block[:2000],
                    language=ast.language,
                    chunk_type="block",
                    line_start=i + 1,
                    line_end=min(i + 50, len(lines)),
                ))

        return chunks

    # ── Index session ─────────────────────────────────────────────────────────

    def index_session(
        self,
        session_id: str,
        asts: list[FileAST],
        file_contents: dict[str, str],
    ) -> int:
        """
        Chunk all files, embed with sentence-transformers,
        and persist to the numpy vector store.
        Returns total chunk count.
        """
        all_chunks: list[CodeChunk] = []
        for ast in asts:
            content = file_contents.get(ast.path, "")
            if not content.strip():
                continue
            all_chunks.extend(self._chunk_file(ast, content))

        if not all_chunks:
            return 0

        embedder = _get_embedder()
        texts = [c.content for c in all_chunks]
        logger.info(f"[{session_id}] Embedding {len(texts)} chunks…")
        embeddings: np.ndarray = embedder.encode(
            texts,
            show_progress_bar=False,
            batch_size=32,
            convert_to_numpy=True,
        )

        metadatas = [
            {
                "chunk_id":   c.chunk_id,
                "file_path":  c.file_path,
                "content":    c.content,
                "language":   c.language,
                "chunk_type": c.chunk_type,
                "line_start": c.line_start,
                "line_end":   c.line_end,
            }
            for c in all_chunks
        ]

        store = self._get_store(session_id)
        store.upsert(embeddings, metadatas)

        logger.info(f"[{session_id}] Indexed {len(all_chunks)} chunks ✓")
        return len(all_chunks)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
        filter_language: str | None = None,
    ) -> list[RetrievedChunk]:
        embedder = _get_embedder()
        query_vec: np.ndarray = embedder.encode([query], convert_to_numpy=True)[0]

        store = self._get_store(session_id)
        raw_results = store.search(query_vec, top_k=top_k * 3)  # over-fetch for filter

        results: list[RetrievedChunk] = []
        for score, meta in raw_results:
            if filter_language and meta.get("language") != filter_language:
                continue
            results.append(RetrievedChunk(
                chunk_id=meta["chunk_id"],
                file_path=meta["file_path"],
                content=meta["content"],
                language=meta.get("language", ""),
                relevance_score=round(float(score), 4),
                line_start=int(meta.get("line_start", 0)),
                line_end=int(meta.get("line_end", 0)),
            ))
            if len(results) >= top_k:
                break

        return results


# ── Singleton ─────────────────────────────────────────────────────────────────

_index_service: IndexService | None = None


def get_index_service() -> IndexService:
    global _index_service
    if _index_service is None:
        _index_service = IndexService()
    return _index_service
