"""Segmentation v3 benchmark (GRO-145).

Runs a *dry-run* parse → segment → readiness over a manifest (no DB writes, no
embeddings) and renders the per-book structural table the GRO-145 acceptance is
measured on: section count, pages/section, title keep-rate, and the TOC-anchor /
TOC-vs-heading agreement diagnostics added by segmentation v3.

The expensive part is ``pipeline.parse`` (pypdf text extraction over large OCR
PDFs). Two switches keep that cost from being paid twice:

- ``--workers N`` parses books concurrently (one process per book) — the books
  are independent, so this scales nearly linearly to the core count.
- ``--cache-dir DIR`` writes each parsed ``ParsedDocument`` to
  ``{source_id}_parsed.json``. The segmentation work is seconds; only the parse
  is slow, so a cached parse makes every re-run instant. GRO-146 reuses the same
  cache to pin the post-re-ingest numbers without re-parsing.

This measures the *code's* output on the real books without mutating the pinned
corpus, so it is safe to run anywhere (laptop, Kaggle CPU kernel).

    python -m app.ingestion.application.segmentation_benchmark \
        --manifest data/books/manifest.yaml --workers 4 \
        --cache-dir /tmp/parsed --out /tmp/seg_bench_after.md
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from app.ingestion.domain.manifest import load_manifest
from app.ingestion.domain.models import ManifestSource

# Verdict ranking for the worst-wins roll-up. ERROR (a book that failed to
# parse/segment at all) outranks FAIL so a crashed book is never hidden.
_VERDICT_RANK = {"PASS": 0, "WARN": 1, "FAIL": 2, "ERROR": 3}


def _error_row(source: ManifestSource, exc: BaseException) -> dict[str, Any]:
    """A render-able stub for a book whose parse/segment raised.

    Keeps the run alive (one bad book must not discard the others' hours of
    work) while surfacing the failure loudly as an ``ERROR`` verdict.
    """
    return {
        "source_id": source.source_id,
        "subject": source.subject,
        "sections": 0,
        "pages_per_section": 0.0,
        "title_keep_rate": 0.0,
        "toc_anchor_count": 0,
        "toc_detected_agreement": None,
        "verdict": "ERROR",
        "reasons": [f"parse/segment failed: {exc}"],
    }


def _benchmark_one_source(source: ManifestSource, cache_dir: str | None) -> dict[str, Any]:
    """Parse → segment → grade one book. Runs in a worker process.

    Imports live inside the function so the heavy module graph is loaded once per
    worker (and never in the parent), keeping the parent import-light.
    """
    from app.ingestion.application.subject_pipeline import get_subject_pipeline_registry
    from app.ingestion.domain.readiness import evaluate_source_readiness

    pipeline = get_subject_pipeline_registry().resolve(source.subject)
    document = pipeline.parse(source)
    result = pipeline.segment(document)
    result.chunks[:] = pipeline.enrich(result.chunks)

    # Mirror run_ingestion: propagate v2 sections onto the document so
    # readiness sees the same structure the loader would persist.
    document.sections = result.sections

    readiness = evaluate_source_readiness(
        document,
        result.chunks,
        result.duplicate_chunks_skipped,
        toc_anchor_count=result.toc_anchor_count,
        toc_detected_agreement=result.toc_detected_agreement,
    )

    if cache_dir:
        out = Path(cache_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{source.source_id}_parsed.json").write_text(document.model_dump_json())

    return readiness.model_dump(mode="json")


def _fmt_pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "n/a"


def render_table(sources: list[dict[str, Any]]) -> str:
    """Render readiness sources as a Markdown table for the PR before/after."""
    header = (
        "| Book | Subject | Sections | Pages/sec | Title keep | "
        "Net depth | Parented | TOC anchors | TOC/head agree | Verdict |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|---|"
    )
    rows = [header]
    for s in sources:
        rows.append(
            "| {sid} | {subject} | {sections} | {pps:.1f} | {keep} | "
            "{depth} | {parented} | {anchors} | {agree} | {verdict} |".format(
                sid=s["source_id"],
                subject=s["subject"],
                sections=s["sections"],
                pps=s["pages_per_section"],
                keep=_fmt_pct(s["title_keep_rate"]),
                depth=s.get("section_network_max_depth", 0),
                parented=_fmt_pct(s.get("section_network_parented_pct")),
                anchors=s.get("toc_anchor_count", 0),
                agree=_fmt_pct(s.get("toc_detected_agreement")),
                verdict=s["verdict"],
            )
        )
    return "\n".join(rows)


def run_benchmark(
    manifest_path: Path, *, workers: int, cache_dir: str | None
) -> tuple[list[dict[str, Any]], str]:
    """Parse+segment every source (optionally in parallel) and grade readiness.

    Returns the per-source readiness dicts (in manifest order) and the worst-wins
    overall verdict. A book that raises is recorded as an ``ERROR`` row rather
    than aborting the run, so one bad book never discards the rest.
    """
    manifest = load_manifest(manifest_path, require_files=True)
    sources = manifest.sources
    order = {s.source_id: i for i, s in enumerate(sources)}

    results: list[dict[str, Any]] = []

    def _record(source: ManifestSource, started: float, run: Any) -> None:
        try:
            results.append(run())
            status = results[-1]["verdict"]
        except Exception as exc:  # noqa: BLE001 — resilience is the point here
            results.append(_error_row(source, exc))
            status = f"ERROR ({exc})"
        print(
            f">>> {source.source_id}: {status} ({time.time() - started:.0f}s)",
            file=sys.stderr,
            flush=True,
        )

    if workers <= 1 or len(sources) <= 1:
        for source in sources:
            started = time.time()
            _record(source, started, lambda s=source: _benchmark_one_source(s, cache_dir))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            started_at = time.time()
            future_to_source = {
                executor.submit(_benchmark_one_source, s, cache_dir): s
                for s in sources
            }
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                _record(source, started_at, future.result)

    results.sort(key=lambda r: order.get(r["source_id"], len(order)))
    overall = "PASS"
    for row in results:
        if _VERDICT_RANK.get(row["verdict"], 0) > _VERDICT_RANK[overall]:
            overall = row["verdict"]
    return results, overall


def main() -> None:
    parser = argparse.ArgumentParser(description="Segmentation v3 benchmark (dry-run, no DB).")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Parse books concurrently (0 = one per CPU, capped at #books).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Write each parsed ParsedDocument to {source_id}_parsed.json here.",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="Also write the rendered table here."
    )
    args = parser.parse_args()

    workers = args.workers or (os.cpu_count() or 1)
    cache_dir = str(args.cache_dir) if args.cache_dir else None

    results, verdict = run_benchmark(
        args.manifest, workers=workers, cache_dir=cache_dir
    )

    rendered = render_table(results) + f"\n\nOverall verdict: {verdict}\n"
    print(rendered)
    if args.out:
        args.out.write_text(rendered)


if __name__ == "__main__":
    main()
