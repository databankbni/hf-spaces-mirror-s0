"""
Export the GridMind retrieval corpus to local files for database-free serving.

Reads every chunk from Postgres and writes:
  serving/artifact/chunks.parquet   — metadata + body (all scorer-required fields)
  serving/artifact/embeddings.npz   — float32 embedding matrix + chunk_ids alignment array

Usage:
  python -m serving.export_artifact
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

_EXPECTED_ROWS = 96
_ARTIFACT_DIR = Path(__file__).parent / "artifact"

# Columns exported:
#   chunk_id, body                       — identity and text
#   requirement_id, page_number          — provenance
#   standard_id, version                 — document identity
#   obligation_strength                  — scorer: apply_priors reads meta["obligation_strength"]
#   obligation_strength_v2               — A/B prior column
#   is_current                           — scorer: apply_priors reads meta["is_current"]
#                                          (True when superseded_by IS NULL)
_SQL = """
SELECT sc.id::text                       AS chunk_id,
       sc.body,
       sc.requirement_id,
       sc.page_number,
       m.standard_id,
       m.version::text                   AS version,
       sc.obligation_strength,
       sc.obligation_strength_v2,
       (m.superseded_by IS NULL)         AS is_current,
       sc.embedding
FROM   standard_chunks sc
JOIN   standard_document_metadata m ON sc.document_id = m.document_id
ORDER  BY sc.id
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)

    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
    conn.close()

    n = len(rows)
    if n != _EXPECTED_ROWS:
        print(
            f"ERROR: expected {_EXPECTED_ROWS} chunks, got {n}. "
            "Refusing to export from a wrong or partial database.",
            file=sys.stderr,
        )
        sys.exit(1)

    emb_idx = col_names.index("embedding")
    meta_cols = [c for c in col_names if c != "embedding"]

    embeddings = np.array([row[emb_idx] for row in rows], dtype="float32")
    chunk_ids = np.array([row[col_names.index("chunk_id")] for row in rows])

    meta_rows = [
        tuple(v for i, v in enumerate(row) if i != emb_idx)
        for row in rows
    ]
    df = pd.DataFrame(meta_rows, columns=meta_cols)

    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = _ARTIFACT_DIR / "chunks.parquet"
    npz_path = _ARTIFACT_DIR / "embeddings.npz"

    df.to_parquet(parquet_path, index=False)
    np.savez_compressed(npz_path, embeddings=embeddings, chunk_ids=chunk_ids)

    print(f"Rows exported  : {n}")
    print(f"Embedding shape: {embeddings.shape}")
    print(f"chunks.parquet   sha256: {_sha256(parquet_path)}")
    print(f"embeddings.npz   sha256: {_sha256(npz_path)}")


if __name__ == "__main__":
    main()
