"""Assemble a clean :class:`ParsedDocument` from a DİM HTML e-textbook bundle.

This is the HTML road's counterpart to the OCR ``segment_document`` path. It is
deliberately *not* the TOC-anchor segmenter: the HTML bundle gives us exact page
numbers and a signal-detected heading tree, so we build the curriculum spine from
:func:`build_curriculum_tree` and the body prose from :func:`extract_page_prose`,
then tag each page chunk with the deepest node that covers it.

Two cleanups make the spine learner-clean (the whole point of the HTML road —
escape the OCR mess):

* **Drop noise leaves.** The heading detector promotes ALL-CAPS marginalia
  (glossary boxes, formula labels) and lowercase soft-wrap fragments to nodes.
  These are always leaves and recognisable by title shape; dropping them reassigns
  their pages to the surviving ancestor, so no prose is lost.
* **Merge soft-wrap continuations.** A lowercase-leading fragment is the tail of a
  heading that wrapped across lines; we append it to the parent title before
  dropping it, recovering the full topic name.

The module is pure (no DB, no embeddings); the writer in
:mod:`app.ingestion.application.load_html_ingestion` persists what it returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ingestion.domain.chunking import chunk_pages_with_stats
from app.ingestion.domain.curriculum import (
    CURRICULUM_NODE_PATH_KEY,
    CURRICULUM_PATH_TITLES_KEY,
    node_title_path,
    resolve_node_for_page,
)
from app.ingestion.domain.models import (
    Chunk,
    CurriculumNode,
    ManifestSource,
    ParsedDocument,
    ParsedPage,
)
from app.ingestion.infrastructure.dim_html.bundle import DimHtmlBundle
from app.ingestion.infrastructure.dim_html.extractor import extract_pages
from app.ingestion.infrastructure.dim_html.page_content import extract_page_prose
from app.ingestion.infrastructure.dim_html.tree import (
    CurriculumTreeNode,
    TreeMetrics,
    build_curriculum_tree,
)

_EXTRACTION_METHOD = "dim_html"


@dataclass(frozen=True)
class HtmlIngestion:
    """Pure output of building one HTML book, ready for the DB writer."""

    document: ParsedDocument
    chunks: list[Chunk]
    tree_metrics: TreeMetrics
    kept_nodes: int
    dropped_nodes: int


def _first_alpha(title: str) -> str | None:
    for ch in title:
        if ch.isalpha():
            return ch
    return None


def _is_all_caps(title: str) -> bool:
    letters = [c for c in title if c.isalpha()]
    return bool(letters) and all(c == c.upper() and c != c.lower() for c in letters)


def _is_continuation_fragment(title: str) -> bool:
    """A soft-wrap tail: starts with a lowercase letter (e.g. ``yaranması``)."""
    first = _first_alpha(title)
    return first is not None and first == first.lower() and first != first.upper()


def _is_noise_leaf_title(title: str) -> bool:
    """True for a non-root leaf title that should not be its own topic node.

    ALL-CAPS titles are marginalia/glossary boxes or OCR'd formula labels;
    lowercase-leading titles are heading soft-wrap tails. Roots are exempt (the
    caller never tests them), so genuine ALL-CAPS chapter titles are preserved.
    """
    stripped = title.strip()
    if not stripped:
        return True
    return _is_all_caps(stripped) or _is_continuation_fragment(stripped)


def _clean_tree(roots: list[CurriculumTreeNode]) -> tuple[list[CurriculumNode], int]:
    """Flatten the tree to clean domain nodes (pre-order); return (nodes, dropped).

    A leaf with a noise title is dropped; if it is a lowercase continuation, its
    text is appended to the parent title first. Nodes with children are always
    kept, so dropping only ever removes leaves and never orphans a survivor —
    ``parent_path`` links stay valid with no renumbering.
    """
    nodes: list[CurriculumNode] = []
    dropped = 0

    def emit(tree_node: CurriculumTreeNode, parent: CurriculumNode | None) -> None:
        nonlocal dropped
        node_path = tree_node.node_path
        is_root = "." not in node_path
        is_leaf = not tree_node.children
        title = tree_node.title.strip()

        if not is_root and is_leaf and _is_noise_leaf_title(title):
            if parent is not None and _is_continuation_fragment(title):
                parent.title = f"{parent.title} {title}".strip()
            dropped += 1
            return

        page_start = tree_node.page_start
        page_end = tree_node.page_end if tree_node.page_end is not None else page_start
        node = CurriculumNode(
            node_path=node_path,
            parent_path=node_path.rsplit(".", 1)[0] if not is_root else None,
            level=node_path.count(".") + 1,
            ordinal=int(node_path.rsplit(".", 1)[-1]),
            title=title or tree_node.title,
            raw_title=tree_node.title,
            page_start=page_start,
            page_end=page_end,
            extraction_method=_EXTRACTION_METHOD,
        )
        nodes.append(node)
        for child in tree_node.children:
            emit(child, node)

    for root in roots:
        emit(root, None)
    return nodes, dropped


def _parsed_pages(bundle: DimHtmlBundle) -> list[ParsedPage]:
    """One ParsedPage per bundle page; image-only pages carry empty text."""
    image_only = {e.page_number for e in extract_pages(bundle.pages) if e.is_image_only}
    pages: list[ParsedPage] = []
    for page in bundle.pages:
        text = "" if page.page_number in image_only else extract_page_prose(page)
        pages.append(ParsedPage(page_number=page.page_number, text=text))
    return pages


def _tag_chunk_nodes(chunks: list[Chunk], nodes: list[CurriculumNode]) -> None:
    """Stamp each chunk with the deepest covering node's path + breadcrumb."""
    for chunk in chunks:
        node = resolve_node_for_page(nodes, chunk.page_start)
        if node is None:
            continue
        chunk.metadata[CURRICULUM_NODE_PATH_KEY] = node.node_path
        chunk.metadata[CURRICULUM_PATH_TITLES_KEY] = node_title_path(nodes, node)


def build_html_ingestion(source: ManifestSource, bundle_root: Path) -> HtmlIngestion:
    """Build a clean :class:`ParsedDocument` + tagged chunks for one HTML book."""
    bundle = DimHtmlBundle.detect(bundle_root)
    if bundle is None:
        raise ValueError(f"{bundle_root} is not a recognizable DİM HTML bundle")

    roots, tree_metrics = build_curriculum_tree(extract_pages(bundle.pages))
    nodes, dropped = _clean_tree(roots)

    pages = _parsed_pages(bundle)
    chunks = chunk_pages_with_stats(source, pages).chunks
    _tag_chunk_nodes(chunks, nodes)

    document = ParsedDocument(source=source, pages=pages, curriculum_nodes=nodes)
    return HtmlIngestion(
        document=document,
        chunks=chunks,
        tree_metrics=tree_metrics,
        kept_nodes=len(nodes),
        dropped_nodes=dropped,
    )
