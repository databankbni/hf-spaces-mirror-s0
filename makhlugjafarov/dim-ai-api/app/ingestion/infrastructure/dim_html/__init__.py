"""Extractor for official DİM HTML e-textbook bundles (the "HTML road").

A DİM e-textbook is a multi-file HTML5 reader: an entry page (``basla.html`` or
``baslat.html``) plus ``units/unit-*/pageN.xhtml`` — one XHTML file per book page,
each carrying a *clean embedded text layer* and an exact page→file map.

This package is a **read-only spike** (GRO-161): it proves a clean curriculum tree
can be recovered from such a bundle via **signal-driven** heading inference, with
no DB writes and no changes to the OCR pipeline. The signals (relative font-size
rank, leading lesson number, ALL-CAPS, boldness) are deliberately *not* keyed on
CSS class names, which drift between template years and even rotate within a book.

Public surface:
    - :class:`DimHtmlBundle` — detect + enumerate a bundle's pages.
    - :func:`extract_pages` / :class:`HeadingCandidate` — per-page parse.
    - :func:`build_curriculum_tree` / :class:`CurriculumTreeNode` — the tree + metrics.
"""

from app.ingestion.infrastructure.dim_html.bundle import DimHtmlBundle, BundlePage
from app.ingestion.infrastructure.dim_html.extractor import (
    HeadingCandidate,
    PageExtract,
    extract_pages,
)
from app.ingestion.infrastructure.dim_html.tree import (
    CurriculumTreeNode,
    TreeMetrics,
    build_curriculum_tree,
)

__all__ = [
    "DimHtmlBundle",
    "BundlePage",
    "HeadingCandidate",
    "PageExtract",
    "extract_pages",
    "CurriculumTreeNode",
    "TreeMetrics",
    "build_curriculum_tree",
]
