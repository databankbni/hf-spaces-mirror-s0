"""Build ParsedPages from a pre-OCR'd per-page JSON artifact.

The GOT-OCR-2.0 math batch runs on a remote free GPU (Kaggle) and emits one
JSON file: ``{"source_id": ..., "pages": [{"page_number": N, "text": "..."}]}``.
This module turns that artifact into the same ``ParsedPage`` list the in-process
``got_ocr`` parser produces, so the rest of the pipeline (chunking with
``page_offset``, embedding, loading) is reused unchanged — no duplicated logic.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ingest.models import ManifestSource, ParsedDocument, ParsedPage
from app.ingest.sanitize import sanitize_ocr_text  # GRO-88


class PagesJsonError(RuntimeError):
    """Raised when the pages-JSON artifact is malformed."""


def parsed_document_from_pages_json(source: ManifestSource, json_path: Path) -> ParsedDocument:
    """Load a per-page JSON artifact into a ParsedDocument for *source*."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PagesJsonError(f"Could not read pages JSON {json_path}: {exc}") from exc

    raw_pages = data.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise PagesJsonError(f"{json_path} has no 'pages' list")

    pages: list[ParsedPage] = []
    for entry in raw_pages:
        page_number = entry.get("page_number")
        text = entry.get("text", "")
        if not isinstance(page_number, int) or page_number < 1:
            raise PagesJsonError(f"invalid page_number in {json_path}: {page_number!r}")
        pages.append(
            ParsedPage(
                page_number=page_number,
                text=sanitize_ocr_text(text),  # GRO-88: clean OCR artifacts before ingestion
                layout_json={"parser": "got-ocr-2.0", "source": "remote_batch"},
            )
        )

    return ParsedDocument(source=source, pages=pages)

