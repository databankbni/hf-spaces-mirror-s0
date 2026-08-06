import argparse
from pathlib import Path

from app.platform.config import Settings
from app.ingestion.domain.chunking import chunk_pages_with_stats
from app.ingestion.application.load_ingestion import load_ingestion_to_postgres
from app.ingestion.domain.manifest import load_manifest
from app.ingestion.infrastructure.pages_json import parsed_document_from_pages_json
from app.platform.embeddings import BgeM3Embedder


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a per-page OCR JSON artifact into Postgres.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--database-url")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest, require_files=False)
    source = next((s for s in manifest.sources if s.source_id == args.source_id), None)
    if source is None:
        raise SystemExit(f"source_id {args.source_id!r} not found in {args.manifest}")

    document = parsed_document_from_pages_json(source, args.json)
    chunking = chunk_pages_with_stats(source, document.pages)

    database_url = args.database_url or Settings().database_url
    if not database_url:
        raise SystemExit("database url required (--database-url or DIM_AI_API_DATABASE_URL)")

    result = load_ingestion_to_postgres(
        database_url=database_url,
        manifest_path=args.manifest,
        manifest=manifest,
        documents=[document],
        chunks_by_source={source.source_id: chunking.chunks},
        duplicate_chunks_skipped=chunking.duplicate_chunks_skipped,
        embedder=BgeM3Embedder(),
    )
    print(
        f"loaded source={args.source_id} pages={len(document.pages)} "
        f"chunks={result.chunks_created} embedded={result.chunks_embedded} "
        f"warnings={result.warnings_total}"
    )

