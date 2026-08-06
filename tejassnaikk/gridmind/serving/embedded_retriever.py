"""
Database-free retrieval using pre-exported artifact files.

EmbeddedRetriever is a drop-in for retrieval.query.query():
  - Dense:  cosine similarity via normalised numpy matmul (embeddings are already L2-normalised)
  - Sparse: BM25 (rank_bm25) over chunk bodies; index built once at load time
  - Fusion + priors: delegates entirely to retrieval.scorer — no local reimplementation

Artifact files expected at serving/artifact/:
  chunks.parquet    — metadata + body rows, one per chunk
  embeddings.npz    — float32 matrix (N, 384) + chunk_ids alignment array
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from ingestion.embed import _get_model
from retrieval.config import RETRIEVAL_CONFIG
from retrieval.scorer import rank_candidates

_ARTIFACT_DIR = Path(__file__).parent / "artifact"

# Identical to retrieval/query.py — BGE asymmetric: queries use this prefix, passages do not.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_PRIOR_ALLOWLIST = {"obligation_strength", "obligation_strength_v2"}


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, drop empty tokens."""
    return [t for t in re.split(r"\W+", text.lower()) if t]


def _to_python(v):
    """Convert pandas/numpy NA or NaN to Python None; leave other values unchanged."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass
    return v


class EmbeddedRetriever:
    """
    Load the exported corpus once and serve retrieval queries without Postgres.

    prior_column controls which obligation label is used as the scoring prior.
    Allowed: 'obligation_strength' or 'obligation_strength_v2' (default).
    The selected column is always stored internally as 'obligation_strength' in
    the meta dicts — identical to the AS alias in fetch_chunk_meta's SQL — so
    retrieval.scorer.apply_priors works without modification.
    """

    def __init__(
        self,
        artifact_dir: Path | None = None,
        prior_column: str = "obligation_strength_v2",
    ) -> None:
        if prior_column not in _PRIOR_ALLOWLIST:
            raise ValueError(
                f"prior_column {prior_column!r} not in allowlist {sorted(_PRIOR_ALLOWLIST)}"
            )

        art = Path(artifact_dir) if artifact_dir else _ARTIFACT_DIR
        df = pd.read_parquet(art / "chunks.parquet")
        npz = np.load(art / "embeddings.npz", allow_pickle=True)

        # Verify row alignment between the two files
        parquet_ids = df["chunk_id"].to_numpy()
        npz_ids = npz["chunk_ids"]
        if not np.array_equal(parquet_ids, npz_ids):
            raise ValueError(
                "chunk_id alignment mismatch between chunks.parquet and embeddings.npz — "
                "re-run serving/export_artifact.py"
            )

        self._chunk_ids: list[str] = list(parquet_ids)
        self._embeddings: np.ndarray = npz["embeddings"].astype("float32")  # (N, 384)

        # Build BM25 index over all chunk bodies (done once)
        bodies = df["body"].tolist()
        self._bm25 = BM25Okapi([_tokenize(b) for b in bodies])

        # Precompute meta dicts for all chunks (96 rows — negligible memory)
        df_idx = df.set_index("chunk_id")
        self._meta_by_id: dict[str, dict] = {}
        for cid in self._chunk_ids:
            row = df_idx.loc[cid]
            self._meta_by_id[cid] = {
                "body": row["body"],
                "requirement_id": _to_python(row["requirement_id"]),
                "page_number": _to_python(row["page_number"]),
                "standard_id": row["standard_id"],
                "version": str(row["version"]),
                "is_current": bool(row["is_current"]),
                # Always keyed as "obligation_strength" — mirrors fetch_chunk_meta AS alias
                "obligation_strength": _to_python(row[prior_column]),
            }

    # ------------------------------------------------------------------
    # Internal search methods
    # ------------------------------------------------------------------

    def _dense_top(self, question: str, pool: int) -> list[str]:
        """Top-pool chunk ids by cosine similarity (dot product on normalised vectors)."""
        model = _get_model()
        qvec = model.encode(
            _QUERY_PREFIX + question,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        sims = self._embeddings @ qvec          # (N,) cosine similarities
        top_idx = np.argsort(sims)[::-1][:pool]
        return [self._chunk_ids[int(i)] for i in top_idx]

    def _sparse_top(self, question: str, pool: int) -> list[str]:
        """Top-pool chunk ids by BM25 score."""
        scores = self._bm25.get_scores(_tokenize(question))
        top_idx = np.argsort(scores)[::-1][:pool]
        return [self._chunk_ids[int(i)] for i in top_idx]

    # ------------------------------------------------------------------
    # Public API — same return shape as retrieval.query.query()
    # ------------------------------------------------------------------

    def query(self, question: str, k: int = 5) -> list[dict]:
        """
        Return top-k results.  Dict keys match retrieval.query.query() exactly:
          rank, _chunk_id, standard_id, version, requirement_id, page_number, score, body
        """
        cfg = {**RETRIEVAL_CONFIG, "final_k": k}
        pool = cfg["candidate_pool"]

        dense_ids  = self._dense_top(question, pool)
        sparse_ids = self._sparse_top(question, pool)

        # Union of candidates in appearance order (same as retrieval/query.py)
        all_ids = list(dict.fromkeys(dense_ids + sparse_ids))
        meta_by_id = {cid: self._meta_by_id[cid] for cid in all_ids if cid in self._meta_by_id}

        ranked = rank_candidates(dense_ids, sparse_ids, meta_by_id, cfg)

        results: list[dict] = []
        for rank, (chunk_id, score) in enumerate(ranked, start=1):
            m = meta_by_id[chunk_id]
            results.append({
                "rank": rank,
                "_chunk_id": chunk_id,
                "standard_id": m["standard_id"],
                "version": m["version"],
                "requirement_id": m["requirement_id"],
                "page_number": m["page_number"],
                "score": score,
                "body": m["body"],
            })
        return results
