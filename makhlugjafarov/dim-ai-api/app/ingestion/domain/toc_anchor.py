"""TOC (Mündəricat) anchors for segmentation v3 (GRO-145).

Every DİM textbook carries one high-signal structure cue — its own table of
contents. Heading detection alone is hostage to OCR: a book whose headings are
recognised (Tarix) segments finely, while one whose headings are missed
(Ədəbiyyat: 13 sections over 212 pages) collapses. The TOC is the book telling
us where its sections begin, in printed-page coordinates.

This module parses the TOC page(s) into ``TocAnchor(printed_page, raw_title,
level)`` triples. The segmenter (``app.ingestion.domain.chunking``) treats these as
authoritative section boundaries; detected headings refine *within* them but
never override them (GRO-91 contract: a book with no parseable TOC degrades to
the heading heuristic — never a hard failure).

Coordinates: TOC page numbers are *printed* pages, the same space the chunker
works in (``block.page - source.page_offset``), so anchors align directly with
section ``page_start`` without extra translation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ingestion.domain.models import ParsedDocument

logger = logging.getLogger(__name__)

# Heuristics for detecting "Mündəricat" (Table of Contents) pages
TOC_TITLE_PATTERNS = [
    re.compile(r"(?i)^\s*MÜNDƏRİCAT\s*$"),
    re.compile(r"(?i)^\s*Mündəricat\s*$"),
    re.compile(r"(?i)^\s*İÇİNDƏKİLƏR\s*$"),
]

# Heuristics for matching ToC rows: Title ....... Page
# Matches patterns like:
# "1. Fəsil adları ............. 12"
# "Some topic . . . . . . . . 45"
TOC_ROW_PATTERN = re.compile(r"^(.*?)(?:\.{3,}|\.\s\.\s\.)\s*(\d+)\s*$")

# A page is a TOC page when it carries at least this many TOC rows (title +
# dot-leader + page number). Heading detection (``MÜNDƏRİCAT``) is unreliable —
# OCR rarely isolates it as a clean first line — so the TOC is identified by its
# row density instead, which survives garbled headings (GRO-145).
_MIN_TOC_ROWS = 3


@dataclass(frozen=True)
class TocAnchor:
    """A section boundary declared by the book's own table of contents."""

    printed_page: int
    raw_title: str  # un-sanitised; the segmenter gates it at write time
    level: int = 1


def _toc_row_count(text: str) -> int:
    """Number of lines on a page that read as TOC rows (``Title .... 42``)."""
    return sum(1 for line in text.split("\n") if TOC_ROW_PATTERN.match(line.strip()))


def _toc_pages(document: ParsedDocument) -> list:
    """Pages that belong to the table of contents.

    A page is a TOC page when its first line is a ``MÜNDƏRİCAT`` heading *or* it
    carries ``_MIN_TOC_ROWS`` dot-leader rows. Real DİM scans rarely OCR the
    heading cleanly (the Ədəbiyyat TOC has no recognisable ``MÜNDƏRİCAT`` line at
    all), so leaning on the heading alone finds nothing — row density is the
    signal that actually survives OCR.
    """
    pages = []
    for page in document.pages:
        text = page.text or ""
        first_line = text.split("\n", 1)[0] if text else ""
        has_heading = any(pat.match(first_line) for pat in TOC_TITLE_PATTERNS)
        if has_heading or _toc_row_count(text) >= _MIN_TOC_ROWS:
            pages.append(page)
    return pages


def extract_toc_anchors(document: ParsedDocument) -> list[TocAnchor]:
    """Parse the TOC into page-ascending, page-deduped section anchors.

    Best-effort: returns ``[]`` on no parseable TOC or any error, so the caller
    degrades to heading-only segmentation rather than failing ingestion.
    """
    try:
        anchors: list[TocAnchor] = []
        for page in _toc_pages(document):
            for line in (page.text or "").split("\n"):
                original_line = line.rstrip()
                stripped_line = original_line.strip()
                if not stripped_line:
                    continue
                match = TOC_ROW_PATTERN.match(stripped_line)
                if not match:
                    continue
                raw_title = match.group(1).strip(" .")
                try:
                    printed_page = int(match.group(2))
                except ValueError:
                    continue
                if printed_page >= 1 and raw_title:
                    anchors.append(
                        TocAnchor(
                            printed_page=printed_page,
                            raw_title=raw_title,
                            level=_infer_toc_level(raw_title, original_line),
                        )
                    )

        # One section boundary per printed page; keep the first title listed for it.
        # ``sorted`` is stable, so the earliest-listed title survives the dedupe.
        seen: set[int] = set()
        unique: list[TocAnchor] = []
        for anchor in sorted(anchors, key=lambda a: a.printed_page):
            if anchor.printed_page in seen:
                continue
            seen.add(anchor.printed_page)
            unique.append(anchor)
        return unique
    except Exception as exc:  # never fail ingestion on a TOC parse error
        logger.warning(
            "TOC anchor extraction failed for %s: %s",
            document.source.source_id,
            exc,
            exc_info=True,
        )
        return []


def _infer_toc_level(raw_title: str, original_line: str) -> int:
    """Best-effort TOC depth from numbering first, indentation second."""
    title = raw_title.strip()

    numeric = re.match(r"^(\d+(?:\.\d+)*)(?:\.|\))?\s+", title)
    if numeric:
        return _clamp_level(numeric.group(1).count(".") + 1)

    roman = re.match(r"^(?i:[IVXLCDM]+)(?:\.|\))\s+", title)
    if roman:
        return 1

    if re.match(r"(?i)^fəsil\s+\d+", title):
        return 1
    if re.match(r"(?i)^(mövzu|§)\s*\d+", title):
        return 2

    leading_spaces = len(original_line) - len(original_line.lstrip(" "))
    if leading_spaces >= 2:
        return _clamp_level(1 + leading_spaces // 2)

    return 1


def _clamp_level(level: int) -> int:
    return max(1, min(level, 6))
