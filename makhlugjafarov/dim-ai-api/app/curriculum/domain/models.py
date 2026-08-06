"""Read-side models for the curriculum topic-slice contract (GRO-158).

This bounded context answers a different question than retrieval. Retrieval asks
"which chunks are *semantically* nearest this query?"; the curriculum read asks
"give me topic X *as it is structured in the book* — its place in the syllabus,
its sub-topics, and the text that belongs to it." It is the read half of the apex
intent: the TOC-spine tree (GRO-156) is built and stored, and this turns a topic
selector into an LLM-ready slice any module can hand to a model.
"""

from __future__ import annotations

from dataclasses import dataclass


class TopicSliceError(Exception):
    """Raised when a topic slice cannot be resolved (no book / no node)."""


@dataclass(frozen=True)
class NodeView:
    """A single curriculum node as seen by a consuming module (no DB internals)."""

    node_id: str
    node_path: str
    level: int
    title: str
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True)
class BlockView:
    """A typed non-prose artefact (table / figure / formula) attached to a node.

    The read-side projection of an ingestion ``content_block`` (GRO-79). Held as
    its own curriculum type — not an import from the ingestion context — so the two
    bounded contexts stay decoupled: ingestion *writes* blocks, curriculum *reads*
    them. ``caption`` is the printed textbook caption (authoritative when present);
    ``description`` is the best-effort VLM text (low-trust enrichment); ``markdown``
    is the rendered table grid.
    """

    node_path: str
    kind: str                              # data_table | figure | formula | exercise_template
    page: int | None
    caption: str | None
    description: str | None                # VLM best-effort (figures)
    markdown: str | None                   # rendered grid (tables)
    n_rows: int | None
    n_cols: int | None
    fill_ratio: float | None


@dataclass(frozen=True)
class TopicSlice:
    """A self-contained, LLM-ready view of one curriculum topic and its subtree.

    ``content`` is the assembled, breadcrumb-headed text ready to drop into a
    prompt; the structured fields (``node``/``ancestors``/``descendants``) let a
    module reason about the slice (navigation, follow-up questions, coverage)
    without re-parsing the prose.
    """

    source_id: str
    subject: str | None
    node: NodeView
    breadcrumb: tuple[str, ...]            # titles, root → node inclusive
    ancestors: tuple[NodeView, ...]        # root → parent (node excluded)
    descendants: tuple[NodeView, ...]      # subtree below node, syllabus order
    page_start: int | None                 # min over node + included descendants
    page_end: int | None                   # max over node + included descendants
    chunk_count: int                       # chunks rendered into ``content``
    content: str
    truncated: bool                        # True if max_chars clipped the body
    omitted_node_paths: tuple[str, ...]    # subtree nodes whose text didn't fit
    block_count: int = 0                   # typed blocks rendered into ``content``
    blocks: tuple[BlockView, ...] = ()     # those blocks, structured (for native UI)


@dataclass(frozen=True)
class OutlineNode:
    """A node as seen when *navigating* the curriculum (counts, not text)."""

    node_path: str
    level: int
    title: str
    page_start: int | None
    page_end: int | None
    chunk_count: int                       # chunks directly tagged to this node
    has_children: bool
    block_count: int = 0                   # typed blocks (tables/figures/formulas) on this node


# Source types whose curriculum tree is clean enough to navigate in-app. The
# OCR-scanned ("pdf") books *do* carry curriculum_nodes (the v4 program built
# trees for every book), but those trees are noisy, so the two-road strategy
# keeps them out of the browsable Learn surface — they remain chat-only. Only the
# official DİM HTML e-textbooks (exact pages, clean spine) are browsable.
BROWSABLE_SOURCE_TYPES: frozenset[str] = frozenset({"dim_html"})


def is_browsable(source_type: str | None, node_count: int) -> bool:
    """Whether a book should be offered as a navigable course (outline/reader).

    True only for a clean-source book that actually has a curriculum tree, so the
    mobile app never opens an outline for an ask-only book or an empty one.
    """
    return source_type in BROWSABLE_SOURCE_TYPES and node_count > 0


@dataclass(frozen=True)
class CatalogEntry:
    """One ingested book in the catalog — what the Home screen lists.

    ``browsable`` distinguishes a *course* (a clean HTML-road book with a
    navigable curriculum tree) from an *ask-only* subject (a book that powers
    ``/query`` retrieval but whose tree is too noisy to navigate). The mobile app
    groups cards on this flag, so it never offers an outline for an ask-only book.
    ``source_type`` is exposed too so the client can explain the difference.
    """

    source_id: str
    title: str
    subject: str | None
    grade: int | None
    language: str | None
    source_type: str | None                # 'dim_html' (clean) vs 'pdf' (OCR)
    node_count: int                        # curriculum_nodes for this book
    chunk_count: int                       # retrievable chunks for this book
    browsable: bool                        # clean tree → outline/reader/flashcards/quiz


@dataclass(frozen=True)
class CurriculumOutline:
    """The navigable map of a book's curriculum — what a module reads to choose.

    ``get_topic_slice`` answers "give me topic X"; an agent first needs to *see*
    the topics. This is that map: every node in syllabus order with its page span
    and how much text hangs off it, plus a coverage read so a caller knows how
    much of the book the tree actually accounts for.
    """

    source_id: str
    subject: str | None
    nodes: tuple[OutlineNode, ...]         # syllabus order (natural node_path sort)
    node_count: int
    max_depth: int
    total_chunks: int
    tagged_chunks: int                     # chunks attached to any node

    def render(self) -> str:
        """Indented text outline, directly feedable to an LLM as a syllabus."""
        lines = [f"# {self.subject or self.source_id} — curriculum outline"]
        for n in self.nodes:
            indent = "  " * (n.level - 1)
            pages = f" (p.{n.page_start}–{n.page_end})" if n.page_start else ""
            count = f"  [{n.chunk_count} chunks]" if n.chunk_count else ""
            blocks = f"  [{n.block_count} blocks]" if n.block_count else ""
            lines.append(f"{indent}{n.node_path}  {n.title}{pages}{count}{blocks}")
        return "\n".join(lines)
