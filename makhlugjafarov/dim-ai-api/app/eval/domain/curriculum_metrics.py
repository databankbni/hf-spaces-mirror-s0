"""Structural quality metrics for the GRO-156 TOC curriculum tree.

v4's thesis is a queryable curriculum tree, so the eval that gates it measures
the TREE, not just citation-page coverage. These are pure functions over simple
typed inputs (no DB, no network) so they unit-test cleanly; the CLI in
scripts/eval_curriculum_tree.py sources the inputs from Postgres.

Headline metrics:
  * named_pct        — title-keep-rate: share of nodes with a real, non-garble
                       title. The v4 program's central quality number (v3 prose
                       sections stored 25–62% real titles; the tree lifts this).
  * chunk_tagged_pct — share of retrieval units that resolve to a curriculum node
                       (i.e. carry a breadcrumb into the answer context).
  * nested_pct       — share of nodes with a parent: proves real hierarchy, not a
                       flat list (the defect that got the old table dropped, GRO-141).
  * page_coverage    — share of book pages claimed by some node's span.
  * l1_childless     — top-level nodes with no children: a smell for OCR title
                       fragments / cover echoes (e.g. a split chapter heading).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Placeholder the builder emits when it cannot recover a title at all.
_UNNAMED_PLACEHOLDER = "(adsız)"
# A real heading is mostly letters; OCR garble lines are punctuation/digit soup.
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass(frozen=True)
class TreeNode:
    level: int
    title: str
    has_parent: bool
    has_children: bool
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class CurriculumTreeMetrics:
    book: str
    nodes: int
    max_depth: int
    nested_pct: float
    named_pct: float
    section_tagged_pct: float
    chunk_tagged_pct: float
    breadcrumb_depth_avg: float
    page_coverage_pct: float
    l1_childless: int
    verdict: str
    reasons: list[str] = field(default_factory=list)


def is_named_title(title: str | None) -> bool:
    """A node title 'counts' as named when it is present, not the unnamed
    placeholder, and carries enough letters to be a real heading (not OCR soup)."""
    if not title:
        return False
    stripped = title.strip()
    if not stripped or stripped == _UNNAMED_PLACEHOLDER:
        return False
    letters = len(_LETTER.findall(stripped))
    # at least 3 letters and a majority of non-space chars are letters
    dense = stripped.replace(" ", "")
    return letters >= 3 and bool(dense) and letters / len(dense) >= 0.5


def _page_coverage_pct(nodes: list[TreeNode], page_count: int) -> float:
    if page_count <= 0:
        return 0.0
    intervals = sorted(
        (n.page_start, n.page_end)
        for n in nodes
        if n.page_start is not None and n.page_end is not None and n.page_end >= n.page_start
    )
    covered = 0
    cur_start = cur_end = None
    for start, end in intervals:
        if cur_end is None or start > cur_end + 1:
            if cur_end is not None:
                covered += cur_end - cur_start + 1
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        covered += cur_end - cur_start + 1
    return min(covered, page_count) / page_count


def _verdict(named_pct: float, chunk_tagged_pct: float, page_coverage: float, l1_childless: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    verdict = "PASS"
    if named_pct < 0.70:
        verdict = "FAIL"
        reasons.append(f"named_pct {named_pct:.0%} < 70% (titles unusable)")
    elif named_pct < 0.90:
        verdict = "WARN"
        reasons.append(f"named_pct {named_pct:.0%} < 90%")
    if chunk_tagged_pct < 0.50:
        verdict = "FAIL"
        reasons.append(f"chunk_tagged_pct {chunk_tagged_pct:.0%} < 50% (most chunks orphaned)")
    elif chunk_tagged_pct < 0.70 and verdict != "FAIL":
        verdict = "WARN"
        reasons.append(f"chunk_tagged_pct {chunk_tagged_pct:.0%} < 70%")
    if page_coverage < 0.80 and verdict != "FAIL":
        verdict = "WARN"
        reasons.append(f"page_coverage {page_coverage:.0%} < 80%")
    if l1_childless > 0 and verdict != "FAIL":
        verdict = "WARN"
        reasons.append(f"{l1_childless} top-level node(s) have no children (possible OCR fragments)")
    return verdict, reasons


def compute_tree_metrics(
    *,
    book: str,
    nodes: list[TreeNode],
    sections_total: int,
    sections_tagged: int,
    chunks_total: int,
    chunks_tagged: int,
    breadcrumb_depths: list[int],
    page_count: int,
) -> CurriculumTreeMetrics:
    n = len(nodes)
    max_depth = max((node.level for node in nodes), default=0)
    nested_pct = (sum(1 for node in nodes if node.has_parent) / n) if n else 0.0
    named_pct = (sum(1 for node in nodes if is_named_title(node.title)) / n) if n else 0.0
    section_tagged_pct = (sections_tagged / sections_total) if sections_total else 0.0
    chunk_tagged_pct = (chunks_tagged / chunks_total) if chunks_total else 0.0
    breadcrumb_depth_avg = (sum(breadcrumb_depths) / len(breadcrumb_depths)) if breadcrumb_depths else 0.0
    page_coverage = _page_coverage_pct(nodes, page_count)
    l1_childless = sum(1 for node in nodes if node.level == 1 and not node.has_children)
    verdict, reasons = _verdict(named_pct, chunk_tagged_pct, page_coverage, l1_childless)
    return CurriculumTreeMetrics(
        book=book,
        nodes=n,
        max_depth=max_depth,
        nested_pct=nested_pct,
        named_pct=named_pct,
        section_tagged_pct=section_tagged_pct,
        chunk_tagged_pct=chunk_tagged_pct,
        breadcrumb_depth_avg=breadcrumb_depth_avg,
        page_coverage_pct=page_coverage,
        l1_childless=l1_childless,
        verdict=verdict,
        reasons=reasons,
    )
