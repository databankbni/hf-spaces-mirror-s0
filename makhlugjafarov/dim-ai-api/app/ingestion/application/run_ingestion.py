import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

from app.platform.config import Settings
from app.ingestion.application.subject_pipeline import get_subject_pipeline_registry
from app.ingestion.application.load_ingestion import load_ingestion_to_postgres
from app.ingestion.domain.manifest import load_manifest
from app.ingestion.domain.readiness import (
    build_readiness_report,
    evaluate_source_readiness,
)
from app.ingestion.domain.report import build_report
from app.platform.embeddings import BgeM3Embedder


class ReadinessGateError(RuntimeError):
    """Raised when a live ingestion is blocked by a FAIL readiness verdict."""


def run_ingestion(
    manifest_path: Path,
    *,
    dry_run: bool,
    require_files: bool = True,
    database_url: str | None = None,
) -> dict[str, object]:
    manifest = load_manifest(manifest_path, require_files=require_files)

    registry = get_subject_pipeline_registry()

    documents = []
    chunking_results = {}

    for source in manifest.sources:
        t0 = time.time()
        print(f"[parse]   {source.source_id} ...", flush=True, file=sys.stderr)
        pipeline = registry.resolve(source.subject)
        document = pipeline.parse(source)
        print(f"[segment] {source.source_id} ({len(document.pages)}pp) ...", flush=True, file=sys.stderr)
        result = pipeline.segment(document)
        result.chunks[:] = pipeline.enrich(result.chunks)
        print(f"[done]    {source.source_id} — {len(result.chunks)} chunks in {time.time()-t0:.0f}s", flush=True, file=sys.stderr)

        # Propagate v2 section data back onto the document so load_ingestion
        # can persist section_blocks.
        document.sections = result.sections
        # Segmentation v4 (GRO-156): carry the TOC curriculum tree through so the
        # loader can persist curriculum_nodes and wire the section/chunk FKs.
        document.curriculum_nodes = result.curriculum_nodes

        documents.append(document)
        chunking_results[source.source_id] = result

    chunks_by_source = {
        source_id: result.chunks
        for source_id, result in chunking_results.items()
    }
    report = build_report(
        corpus_version=manifest.corpus_version,
        dry_run=dry_run,
        documents=documents,
        chunks_by_source=chunks_by_source,
        duplicate_chunks_skipped=sum(result.duplicate_chunks_skipped for result in chunking_results.values()),
    )

    readiness = build_readiness_report([
        evaluate_source_readiness(
            document,
            chunking_results[document.source.source_id].chunks,
            chunking_results[document.source.source_id].duplicate_chunks_skipped,
            toc_anchor_count=chunking_results[document.source.source_id].toc_anchor_count,
            toc_detected_agreement=chunking_results[document.source.source_id].toc_detected_agreement,
        )
        for document in documents
    ])

    load_result = None
    if not dry_run:
        # Readiness gate: a structurally-broken book is never committed live.
        if readiness.has_blocking_failure:
            failed = [s.source_id for s in readiness.sources if s.verdict == "FAIL"]
            raise ReadinessGateError(
                "Readiness gate FAILED for: "
                + ", ".join(failed)
                + ". Run with --dry-run to inspect the verdict. Live commit blocked."
            )
        resolved_database_url = database_url or Settings().database_url
        if not resolved_database_url:
            raise RuntimeError("DIM_AI_API_DATABASE_URL is required for non-dry-run ingestion.")
        load_result = load_ingestion_to_postgres(
            database_url=resolved_database_url,
            manifest_path=manifest_path,
            manifest=manifest,
            documents=documents,
            chunks_by_source=chunks_by_source,
            duplicate_chunks_skipped=sum(result.duplicate_chunks_skipped for result in chunking_results.values()),
            embedder=BgeM3Embedder(),
        )

    return {
        "report": report.model_dump(mode="json"),
        "readiness": readiness.model_dump(mode="json"),
        "load": load_result.__dict__ if load_result else None,
        "chunks": {
            source_id: [chunk.model_dump(mode="json") for chunk in chunks]
            for source_id, chunks in chunks_by_source.items()
        },
    }


def _format_readiness(readiness: dict[str, Any]) -> str:
    """Renders the readiness verdict as a human-readable CLI gate summary."""
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    lines = [f"Readiness gate: {icon.get(str(readiness['verdict']), '?')} {readiness['verdict']}"]
    for s in readiness["sources"]:
        cov = s["page_coverage"]
        cov_str = f"{cov:.0%}" if cov is not None else "n/a"
        lines.append(
            f"  {icon.get(s['verdict'], '?')} {s['verdict']:4} {s['source_id']} "
            f"[{s['family']}] — sections={s['sections']} "
            f"titled={s['titled_pct']:.0%} orphan={s['orphan_pct']:.0%} "
            f"coverage={cov_str}"
        )
        for reason in s["reasons"]:
            lines.append(f"        - {reason}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DIM AI corpus ingestion.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url")
    args = parser.parse_args()

    result = run_ingestion(args.manifest, dry_run=args.dry_run, database_url=args.database_url)
    print(json.dumps(result["load"] or result["report"], ensure_ascii=False, indent=2))

    readiness = cast(dict[str, Any], result["readiness"])
    print("\n" + _format_readiness(readiness), file=sys.stderr)
    if readiness["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
