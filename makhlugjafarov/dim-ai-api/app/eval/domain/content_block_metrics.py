"""Structural quality metrics for the GRO-79 typed content-block layer.

Phase B of the v4 program attaches typed non-prose artefacts (tables / figures /
formulas / exercise templates) to the curriculum tree. Phase 5 made the curriculum
read-contract *consume* them. This module is the regression gate that proves the
layer is real and usable — the content-block companion to
``curriculum_metrics`` (which scores the tree itself).

It deliberately scores the layer the way the app actually reads it: a block only
"counts" as usable when it passes the same ``is_renderable`` judgement the
read-contract applies (printed caption ≫ VLM, literature tables demoted, empty
formulas dropped). So a low ``renderable_pct`` is the quality filter working, not
a failure — the gate fails only when the layer is *dark* (unattached) or the tree
gains *no* typed enrichment at all.

These are pure functions over simple typed inputs (no DB, no network) so they
unit-test cleanly; the CLI in ``scripts/eval_content_blocks.py`` sources the inputs
from Postgres and applies the real ``is_renderable`` rules from the curriculum
domain before handing primitives here.

Headline metrics:
  * attached_pct   — share of blocks linked to a curriculum node. The dark-data
                     check: an unattached block can never reach an answer. The
                     corpus load is 100%; any drop is a page-semantics regression.
  * renderable_pct — share of blocks that pass the read-contract's quality filter.
                     Reported, not hard-gated (formulas/literature tables are
                     legitimately dropped).
  * nodes_enriched — count (and %) of curriculum nodes that carry >=1 renderable
                     block. This is the "the tree actually gains structure" number
                     and the GRO-79 acceptance signal for table/figure topics.
  * figure_caption_pct — share of figures with a trustworthy printed caption (vs
                     relying on the low-trust VLM description).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BlockStat:
    """One content block, reduced to the facts the metrics need.

    ``renderable`` is computed by the caller using the *real* read-contract rule
    (``app.curriculum.domain.block_render.is_renderable``) so the eval scores the
    exact code path the app uses.
    """

    kind: str
    attached: bool
    renderable: bool
    has_caption: bool = False  # only meaningful for figures


@dataclass(frozen=True)
class ContentBlockMetrics:
    book: str
    subject: str | None
    blocks_total: int
    attached_pct: float
    renderable_total: int
    renderable_pct: float
    by_kind: dict[str, int]
    renderable_by_kind: dict[str, int]
    nodes_total: int
    nodes_enriched: int
    nodes_enriched_pct: float
    figures_total: int
    figure_caption_pct: float
    verdict: str
    reasons: list[str] = field(default_factory=list)


def _verdict(
    *,
    blocks_total: int,
    attached_pct: float,
    renderable_total: int,
    renderable_pct: float,
    nodes_enriched: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    verdict = "PASS"

    if blocks_total == 0:
        return verdict, reasons  # a book with no typed layer is neutral, not a failure

    # 1. Dark-data check: blocks that aren't attached can never reach an answer.
    if attached_pct < 0.90:
        verdict = "FAIL"
        reasons.append(f"attached_pct {attached_pct:.0%} < 90% (most blocks orphaned, unreachable)")
    elif attached_pct < 0.99:
        verdict = "WARN"
        reasons.append(f"attached_pct {attached_pct:.0%} < 99% (some blocks orphaned)")

    # 2. Usable payload must exist at all.
    if renderable_total == 0 and blocks_total > 0:
        verdict = "FAIL"
        reasons.append("0 renderable blocks (typed layer present but entirely unusable)")

    # 3. The tree must actually gain typed structure.
    if nodes_enriched == 0 and blocks_total > 0 and verdict != "FAIL":
        verdict = "FAIL"
        reasons.append("0 nodes enriched (no topic gains a table/figure/formula)")

    # 4. Soft signal: a content-rich book whose layer is almost all filtered out.
    if blocks_total >= 100 and renderable_pct < 0.20 and verdict == "PASS":
        verdict = "WARN"
        reasons.append(f"renderable_pct {renderable_pct:.0%} < 20% (most of the typed layer is filtered out)")

    return verdict, reasons


def compute_content_block_metrics(
    *,
    book: str,
    subject: str | None,
    blocks: list[BlockStat],
    nodes_total: int,
    enriched_node_ids: set,
) -> ContentBlockMetrics:
    """Score one book's typed content-block layer.

    ``enriched_node_ids`` is the set of curriculum-node ids that carry at least one
    *renderable* block — computed by the caller from the DB so node identity stays
    out of this pure layer.
    """
    n = len(blocks)
    attached = sum(1 for b in blocks if b.attached)
    renderable = [b for b in blocks if b.renderable]

    by_kind: dict[str, int] = {}
    renderable_by_kind: dict[str, int] = {}
    for b in blocks:
        by_kind[b.kind] = by_kind.get(b.kind, 0) + 1
    for b in renderable:
        renderable_by_kind[b.kind] = renderable_by_kind.get(b.kind, 0) + 1

    figures = [b for b in blocks if b.kind == "figure"]
    figures_with_caption = sum(1 for b in figures if b.has_caption)

    attached_pct = attached / n if n else 0.0
    renderable_pct = len(renderable) / n if n else 0.0
    nodes_enriched = len(enriched_node_ids)
    nodes_enriched_pct = nodes_enriched / nodes_total if nodes_total else 0.0
    figure_caption_pct = figures_with_caption / len(figures) if figures else 0.0

    verdict, reasons = _verdict(
        blocks_total=n,
        attached_pct=attached_pct,
        renderable_total=len(renderable),
        renderable_pct=renderable_pct,
        nodes_enriched=nodes_enriched,
    )

    return ContentBlockMetrics(
        book=book,
        subject=subject,
        blocks_total=n,
        attached_pct=attached_pct,
        renderable_total=len(renderable),
        renderable_pct=renderable_pct,
        by_kind=by_kind,
        renderable_by_kind=renderable_by_kind,
        nodes_total=nodes_total,
        nodes_enriched=nodes_enriched,
        nodes_enriched_pct=nodes_enriched_pct,
        figures_total=len(figures),
        figure_caption_pct=figure_caption_pct,
        verdict=verdict,
        reasons=reasons,
    )
