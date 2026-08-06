"""Build a curriculum tree from heading candidates + compute structural metrics.

Ranking is **per book**: we collect the distinct heading *signatures* that occur,
order them by prominence (see :pyattr:`HeadingCandidate.signature`), and map them
to depth levels 0,1,2,…. A rank-stack then walks the candidates in reading order
to nest them. This is signal-driven — no book-specific or class-name branches.

The spike computes its own lightweight metrics (named%, depth, nested%, page
coverage, image-only%) so it has no dependency on the GRO-156 curriculum-eval
module, which is not yet on ``dev``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.infrastructure.dim_html.extractor import HeadingCandidate, PageExtract

# A heading text repeated on more than this fraction of pages is a running
# header/footer, not a curriculum node.
_RUNNING_HEADER_PAGE_FRACTION = 0.25
_MAX_DEPTH = 4


@dataclass
class CurriculumTreeNode:
    title: str
    level: int
    node_path: str
    page_start: int
    page_end: int | None = None
    children: list["CurriculumTreeNode"] = field(default_factory=list)

    def iter_all(self):
        yield self
        for child in self.children:
            yield from child.iter_all()


@dataclass(frozen=True)
class TreeMetrics:
    node_count: int
    topic_count: int
    max_depth: int
    nested_pct: float
    named_pct: float
    page_count: int
    page_coverage_pct: float
    image_only_pages: int
    image_only_pct: float


def _filter_candidates(
    candidates: list[HeadingCandidate], total_pages: int
) -> list[HeadingCandidate]:
    """Drop running headers, the book-title outlier, and front matter."""
    if not candidates:
        return []

    # Running headers: same text on many pages.
    pages_by_text: dict[str, set[int]] = {}
    for c in candidates:
        pages_by_text.setdefault(c.text, set()).add(c.page)
    header_cutoff = max(2, int(total_pages * _RUNNING_HEADER_PAGE_FRACTION))
    running = {t for t, pgs in pages_by_text.items() if len(pgs) > header_cutoff}

    # Book-title outlier: the single largest font size, occurring once, early.
    max_font = max((c.font_size or 0 for c in candidates), default=0)
    big = [c for c in candidates if (c.font_size or 0) == max_font and max_font > 0]
    title_texts = {c.text for c in big} if len(big) <= 2 else set()

    kept = [c for c in candidates if c.text not in running and c.text not in title_texts]

    # Front matter (cover/title/credits) precedes the curriculum spine. The spine
    # is the top tier of the level map; anything before its first node is front
    # matter and is dropped — generic across books, no page hardcoding.
    front_cutoff = _front_matter_cutoff(kept)
    return [c for c in kept if c.page >= front_cutoff]


def _effective_rank(signature: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Map a heading signature to a depth-ranking key (higher = shallower).

    A leading lesson number is the strongest curriculum signal: numbered headings
    form a single top tier that is *immune to font-size noise* (the DİM HTML
    templates attach ``fsNN`` inconsistently, so the same lesson tier appears with
    and without a detected size). Unnumbered headings rank beneath, ordered by font
    size then caps/bold. Books with no numbers (history) therefore rank purely by
    font; numbered books (biology) put every lesson on one level regardless of size.
    """
    font_size, number, caps, bold = signature
    if number:
        return (1, 0, 0, 0)
    return (0, font_size, caps, bold)


def _level_map(
    candidates: list[HeadingCandidate],
) -> dict[tuple[int, int, int, int], int]:
    ranks = sorted({_effective_rank(c.signature) for c in candidates}, reverse=True)
    level_of_rank = {rank: i for i, rank in enumerate(ranks)}
    return {
        c.signature: min(level_of_rank[_effective_rank(c.signature)], _MAX_DEPTH - 1)
        for c in candidates
    }


def _front_matter_cutoff(candidates: list[HeadingCandidate]) -> int:
    if not candidates:
        return 0
    levels = _level_map(candidates)
    spine_pages = [c.page for c in candidates if levels[c.signature] == 0]
    return min(spine_pages) if spine_pages else 0


def _assign_pages(ordered: list[CurriculumTreeNode], last_page: int) -> None:
    """page_end of a node = (next node at same-or-shallower level).page - 1."""
    for i, node in enumerate(ordered):
        end = last_page
        for j in range(i + 1, len(ordered)):
            if ordered[j].level <= node.level:
                end = max(node.page_start, ordered[j].page_start - 1)
                break
        node.page_end = end


def build_curriculum_tree(
    extracts: list[PageExtract],
) -> tuple[list[CurriculumTreeNode], TreeMetrics]:
    total_pages = len(extracts)
    last_page = max((e.page_number for e in extracts), default=0)

    all_candidates = [h for e in extracts for h in e.headings]
    candidates = _filter_candidates(all_candidates, total_pages)
    candidates.sort(key=lambda c: (c.page, c.reading_order))

    levels = _level_map(candidates)

    roots: list[CurriculumTreeNode] = []
    ordered: list[CurriculumTreeNode] = []
    stack: list[CurriculumTreeNode] = []
    counters: dict[str, int] = {}

    for cand in candidates:
        level = levels[cand.signature]
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        parent_path = parent.node_path if parent else ""
        key = parent_path or "root"
        counters[key] = counters.get(key, 0) + 1
        node_path = f"{parent_path}.{counters[key]}" if parent_path else str(counters[key])

        node = CurriculumTreeNode(
            title=cand.text,
            level=level,
            node_path=node_path,
            page_start=cand.page,
        )
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
        ordered.append(node)
        stack.append(node)

    _assign_pages(ordered, last_page)
    metrics = _compute_metrics(ordered, extracts, total_pages)
    return roots, metrics


def _compute_metrics(
    ordered: list[CurriculumTreeNode], extracts: list[PageExtract], total_pages: int
) -> TreeMetrics:
    node_count = len(ordered)
    topic_count = sum(1 for n in ordered if n.level == 0)
    max_depth = max((n.level for n in ordered), default=-1) + 1
    nested = sum(1 for n in ordered if n.level > 0)
    named = sum(1 for n in ordered if n.title.strip())

    covered: set[int] = set()
    for n in ordered:
        if n.page_end is not None:
            covered.update(range(n.page_start, n.page_end + 1))
    image_only = sum(1 for e in extracts if e.is_image_only)

    def pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    return TreeMetrics(
        node_count=node_count,
        topic_count=topic_count,
        max_depth=max_depth,
        nested_pct=pct(nested, node_count),
        named_pct=pct(named, node_count),
        page_count=total_pages,
        page_coverage_pct=pct(len(covered), total_pages),
        image_only_pages=image_only,
        image_only_pct=pct(image_only, total_pages),
    )
