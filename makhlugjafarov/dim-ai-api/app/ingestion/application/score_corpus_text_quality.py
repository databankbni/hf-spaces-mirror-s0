"""CLI module to rescore the corpus for text quality against the DB."""

import json
import os
import datetime
from pathlib import Path

import psycopg

from app.ingestion.domain.models import (
    Chunk,
    ParsedDocument,
    ManifestSource,
    ExpectedConfig,
    SectionBlock,
)
from app.ingestion.domain.readiness import evaluate_source_readiness

DB_URI = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


def fetch_from_db():
    sources_data = []

    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, source_id, subject, title
                FROM documents
            """)
            for row in cur.fetchall():
                doc_id, source_id, subject, title = row
                page_count = 100  # Default fallback, not critical for text quality

                cur.execute(
                    "SELECT content, section_block_id FROM chunks WHERE document_id = %s",
                    (doc_id,),
                )
                chunks_raw = cur.fetchall()
                chunks = [
                    Chunk(
                        source_id=source_id,
                        chunk_index=i,
                        page_start=1,
                        page_end=1,
                        content=c[0],
                        content_hash="",
                        subject=subject,
                        language="az",
                        source_category="test",
                        section_block_id=str(c[1]) if c[1] else None,
                        metadata={},
                    )
                    for i, c in enumerate(chunks_raw)
                ]

                cur.execute(
                    "SELECT section_title FROM section_blocks WHERE document_id = %s",
                    (doc_id,),
                )
                sections_raw = cur.fetchall()
                sections = [
                    SectionBlock(
                        document_id=str(doc_id),
                        ordinal=i,
                        section_title=s[0],
                        page_start=1,
                        page_end=1,
                        content="",
                        content_hash="",
                        extraction_method="test",
                    )
                    for i, s in enumerate(sections_raw)
                ]

                cur.execute(
                    "SELECT max(page_number) FROM document_pages WHERE document_id = %s",
                    (doc_id,),
                )
                max_page = cur.fetchone()[0] or 0

                from app.ingestion.domain.models import ParsedPage

                pages = [
                    ParsedPage(page_number=i + 1, text="") for i in range(max_page)
                ]

                source = ManifestSource(
                    id=source_id,
                    source_id=source_id,
                    subject=subject,
                    title=title,
                    source_type="pdf",
                    source_category="test",
                    path=Path("."),
                    legal_status="licensed",
                    source_version="v1",
                    citation_label="label",
                    expected=ExpectedConfig(page_count=page_count),
                )

                doc = ParsedDocument(
                    source=source,
                    pages=pages,  # type: ignore
                    sections=sections,
                )

                sources_data.append((doc, chunks))

    return sources_data


def main():
    docs_and_chunks = fetch_from_db()

    output_rows = []

    print(
        f"{'Source':<30} | {'Verdict':<7} | {'Garble':<7} | {'Dirty%':<7} | {'Runs/100':<8} | {'TitleKeep':<9} | {'PPS':<5}"
    )
    print("-" * 85)

    for doc, chunks in docs_and_chunks:
        readiness = evaluate_source_readiness(doc, chunks)

        garble = f"{readiness.garble_token_pct:.2%}"
        dirty = f"{readiness.dirty_chunk_pct:.1%}"
        runs = f"{readiness.spaced_letter_runs_per_100pp:.1f}"
        keep = f"{readiness.title_keep_rate:.1%}"
        pps = f"{readiness.pages_per_section:.1f}"

        print(
            f"{readiness.source_id:<30} | {readiness.verdict:<7} | {garble:<7} | {dirty:<7} | {runs:<8} | {keep:<9} | {pps:<5}"
        )

        row = {
            "date": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "corpus_version": "v2_textquality_2026-06-10",
            "source_id": readiness.source_id,
            "subject": readiness.subject,
            "family": readiness.family,
            "sections": readiness.sections,
            "chunks": readiness.chunks,
            "chunks_per_page": (
                round(readiness.chunk_density, 1) if readiness.chunk_density else 0.0
            ),
            "orphan_pct": round(readiness.orphan_pct, 2),
            "garble_token_pct": round(readiness.garble_token_pct, 4),
            "dirty_chunk_pct": round(readiness.dirty_chunk_pct, 4),
            "title_keep_rate": round(readiness.title_keep_rate, 4),
            "pages_per_section": round(readiness.pages_per_section, 1),
            "spaced_letter_runs_per_100pp": round(
                readiness.spaced_letter_runs_per_100pp, 1
            ),
            "verdict": readiness.verdict,
        }

        if readiness.reasons:
            row["note"] = "; ".join(readiness.reasons)

        output_rows.append(row)

    output_path = (
        Path(__file__).parent.parent.parent.parent.parent.parent
        / "data"
        / "evals"
        / "ingestion_readiness.jsonl"
    )
    with open(output_path, "a") as f:
        for row in output_rows:
            f.write(json.dumps(row) + "\n")

    print(f"\nAppended {len(output_rows)} rows to {output_path.name}")


if __name__ == "__main__":
    main()
