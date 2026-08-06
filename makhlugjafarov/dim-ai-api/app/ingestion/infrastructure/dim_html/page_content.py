"""Per-page readable prose from a DİM HTML (XHTML) bundle page.

The DİM e-textbook template positions every paragraph inside nested *layout*
tables, so the ``<table>`` tags are structure, not data — a flat ``get_text`` over
the page already linearises them into the correct reading order. We then de-wrap
the per-line fragments (each visual line is its own positioned element) into
flowing paragraphs, the same heuristic the frontend OCR sanitiser uses, so the
stored chunk text is clean for *every* downstream consumer (retrieval, lesson
generation, citations) and not just for the browser.

This module is read-only and DB-free. It complements the spike's curriculum
:mod:`~app.ingestion.infrastructure.dim_html.tree` (which detects headings) by
supplying the body prose the tree deliberately omits.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from app.ingestion.infrastructure.dim_html.bundle import BundlePage

# The bundles are XHTML; bs4's lxml-HTML parser handles them fine but emits an
# advisory. We parse with the HTML parser deliberately (consistent with the spike
# extractor) and silence the one warning class.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_WS_RE = re.compile(r"\s+")
_SENTENCE_END = (".", "!", "?", ":", ";", "…", "”", '"')
# A line carrying no letters or digits (a lone ★, bullet glyph, or rule) is layout
# decoration, not prose.
_HAS_ALNUM_RE = re.compile(r"[^\W_]", re.UNICODE)


def _clean_lines(raw_html: str) -> list[str]:
    """Visible text lines, whitespace-collapsed, decoration-only lines dropped."""
    soup = BeautifulSoup(raw_html, "lxml")
    for tag in soup.find_all(["head", "script", "style"]):
        tag.decompose()
    lines: list[str] = []
    for line in soup.get_text("\n").split("\n"):
        collapsed = _WS_RE.sub(" ", line).strip()
        if collapsed and _HAS_ALNUM_RE.search(collapsed):
            lines.append(collapsed)
    return lines


def _dewrap(lines: list[str]) -> str:
    """Join wrapped fragments into paragraphs, breaking on sentence ends.

    A new paragraph starts only after the running text ends with sentence-final
    punctuation; otherwise the next fragment is a soft-wrapped continuation and is
    glued on with a single space. Mirrors ``sanitizeOcrText`` on the frontend so
    server- and client-cleaned text agree.
    """
    paragraphs: list[str] = []
    for line in lines:
        if paragraphs and not paragraphs[-1].rstrip().endswith(_SENTENCE_END):
            paragraphs[-1] = f"{paragraphs[-1]} {line}"
        else:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def extract_page_prose(page: BundlePage) -> str:
    """Clean, de-wrapped reading text for one bundle page.

    Returns ``""`` for an image-only page (the caller skips empty pages so they
    create no chunks).
    """
    raw_html = page.path.read_text(encoding="utf-8", errors="ignore")
    return _dewrap(_clean_lines(raw_html))
