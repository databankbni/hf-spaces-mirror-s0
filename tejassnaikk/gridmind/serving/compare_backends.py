"""
Manual sanity tool: run a question through both backends and compare top-5.

Usage:
  python -m serving.compare_backends "What are the supply chain risk requirements?"
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from retrieval.query import query as postgres_query
from serving.embedded_retriever import EmbeddedRetriever

load_dotenv()


def _row(r: dict) -> str:
    return (
        f"  rank={r['rank']}"
        f"  chunk={r['_chunk_id'][:8]}"
        f"  score={r['score']:.5f}"
        f"  {r['standard_id']}-{r['version']}"
        f"  req={r['requirement_id'] or '—'}"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m serving.compare_backends <question>", file=sys.stderr)
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"Question: {question!r}\n")

    print("=== Postgres backend ===")
    for r in postgres_query(question, k=5):
        print(_row(r))

    print()

    print("=== Embedded backend ===")
    retriever = EmbeddedRetriever()
    for r in retriever.query(question, k=5):
        print(_row(r))


if __name__ == "__main__":
    main()
