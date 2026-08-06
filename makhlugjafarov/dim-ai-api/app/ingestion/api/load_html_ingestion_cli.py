"""CLI: ingest a DİM HTML e-textbook (clean tree + prose chunks) into Postgres.

Usage:
    python -m app.ingestion.api.load_html_ingestion_cli \
        --source umumi_tarix_9_az_html_v1 [--embed] [--dry-run]

Builds the document, curriculum tree and node-tagged chunks from the bundle
declared in the manifest. ``--embed`` also writes canonical BGE-M3 vectors so
the book is retrievable by ``/chat``. ``--dry-run`` prints the build summary
without writing to the DB.
"""

import argparse
from pathlib import Path

from app.ingestion.application.html_ingestion import build_html_ingestion
from app.ingestion.application.load_html_ingestion import load_html_ingestion_to_postgres
from app.ingestion.domain.manifest import load_manifest
from app.platform.config import Settings
from app.platform.embeddings import BgeM3Embedder

_DEFAULT_MANIFEST = Path(__file__).resolve().parents[5] / "data" / "books" / "manifest.yaml"
_DEFAULT_CORPUS_VERSION = "html-v1-2026-06-28"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a DİM HTML book into Postgres.")
    parser.add_argument("--source", required=True, help="manifest source_id of the HTML book")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--corpus-version", default=_DEFAULT_CORPUS_VERSION)
    parser.add_argument("--database-url")
    parser.add_argument("--embed", action="store_true", help="also write BGE-M3 chunk embeddings")
    parser.add_argument("--dry-run", action="store_true", help="build + print summary, no DB write")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    source = next((s for s in manifest.sources if s.source_id == args.source), None)
    if source is None:
        raise SystemExit(f"source_id {args.source!r} not found in {args.manifest}")
    if source.source_type != "dim_html":
        raise SystemExit(f"source {args.source!r} is source_type={source.source_type!r}, not dim_html")

    ingestion = build_html_ingestion(source, source.path)
    m = ingestion.tree_metrics
    print(
        f"built source={source.source_id} pages={len(ingestion.document.pages)} "
        f"chunks={len(ingestion.chunks)} nodes_kept={ingestion.kept_nodes} "
        f"nodes_dropped={ingestion.dropped_nodes} "
        f"(tree: nodes={m.node_count} max_depth={m.max_depth} "
        f"named={m.named_pct:.0f}% page_cov={m.page_coverage_pct:.0f}%)"
    )

    if args.dry_run:
        print("dry-run: no DB write")
        return

    database_url = args.database_url or Settings().database_url
    if not database_url:
        raise SystemExit("database url required (--database-url or DIM_AI_API_DATABASE_URL)")

    embedder = BgeM3Embedder() if args.embed else None
    result = load_html_ingestion_to_postgres(
        database_url=database_url,
        ingestion=ingestion,
        corpus_version=args.corpus_version,
        embedder=embedder,
    )
    print(
        f"loaded source={result.source_id} doc={result.document_id} run={result.run_id} "
        f"nodes={result.nodes_total} chunks={result.chunks_total} pages={result.pages_total} "
        f"embeddings={result.chunks_embedded}"
    )


if __name__ == "__main__":
    main()
