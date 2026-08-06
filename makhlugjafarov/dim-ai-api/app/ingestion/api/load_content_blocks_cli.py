"""CLI: load a Kaggle content-block extraction artifact into Postgres (GRO-79).

Usage:
    python -m app.ingestion.api.load_content_blocks_cli \
        --artifact geo_content_blocks.json [--source-id ...] [--database-url ...]

The artifact is produced by ``dim-geo-blocks-ingest-kernel``. Loading is additive
(no chunk/embedding/corpus_version change) and idempotent per document.
"""

import argparse
import json
from pathlib import Path

from app.ingestion.application.load_content_blocks import (
    content_blocks_from_artifact,
    load_content_blocks_to_postgres,
)
from app.platform.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Load content-block artifact into Postgres.")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--source-id", help="override the artifact's source_id")
    parser.add_argument("--database-url")
    parser.add_argument("--no-replace", action="store_true",
                        help="append instead of replacing this document's existing blocks")
    args = parser.parse_args()

    payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    source_id, blocks = content_blocks_from_artifact(payload)
    if args.source_id:
        source_id = args.source_id
        for b in blocks:
            b.source_id = source_id

    database_url = args.database_url or Settings().database_url
    if not database_url:
        raise SystemExit("database url required (--database-url or DIM_AI_API_DATABASE_URL)")

    result = load_content_blocks_to_postgres(
        database_url=database_url, source_id=source_id, blocks=blocks,
        replace=not args.no_replace,
    )
    by_kind: dict[str, int] = {}
    for b in blocks:
        by_kind[b.kind] = by_kind.get(b.kind, 0) + 1
    print(
        f"loaded source={source_id} doc={result.document_id} "
        f"inserted={result.blocks_inserted} attached={result.blocks_attached} "
        f"orphaned={result.blocks_orphaned} nodes={result.nodes_available} by_kind={by_kind}"
    )


if __name__ == "__main__":
    main()
