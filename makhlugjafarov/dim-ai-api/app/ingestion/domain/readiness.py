"""GRO-129 — Readiness Gate.

Promotes the throwaway dry-run audit into a first-class, gating artifact. Every
book parsed in a dry-run yields a :class:`SourceReadiness`: structural metrics
(titled-section %, orphan-chunk %, page-coverage) plus a
PASS / WARN / FAIL verdict measured against per-category thresholds from
``docs/BOOK_POLICY.md`` §7.

Contract:
- **FAIL** on any *structural* threshold miss (no sections, low titled %, high
  orphan %). A FAIL book is never committed live.
- **WARN** when page-coverage trails the manifest's expected page count — the
  book is structurally sound but under-extracted (e.g. an OCR run that only
  reached part of the book). Surfaced loudly, not silently dropped.
- **PASS** otherwise.

The module is pure domain: it reads a parsed document + its chunks and returns
a verdict. No I/O, no DB, no formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.ingestion.domain.models import Chunk, ParsedDocument

ReadinessVerdict = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class ReadinessThresholds:
    """Per-family gate thresholds (docs/BOOK_POLICY.md §7)."""

    titled_pct_min: float  # PASS requires titled-section fraction >= this
    orphan_pct_max: float  # PASS requires orphan-chunk fraction <= this
    page_coverage_warn: float  # WARN when coverage fraction < this
    chunk_density_warn: float = (
        4.0  # WARN when chunks/page > this (catches over-fragmentation)
    )

    # Text-quality gate thresholds
    garble_token_pct_warn: float = 0.01
    garble_token_pct_fail: float = 0.03
    dirty_chunk_pct_warn: float = 0.10
    dirty_chunk_pct_fail: float = 0.25
    title_keep_rate_warn: float = 0.70
    title_keep_rate_fail: float = 0.50
    pages_per_section_warn: float = 6.0
    pages_per_section_fail: float = 12.0
    spaced_letter_runs_per_100pp_warn: float = 50.0
    # Segmentation v3 (GRO-145): WARN when the book's TOC and detected headings
    # disagree on where sections start — one of the two signals is unreliable for
    # this book (e.g. heading detection missed everything, so we lean entirely on
    # the TOC). Only evaluated once the TOC declared at least this many anchors.
    toc_agreement_warn: float = 0.5
    toc_agreement_min_anchors: int = 5


# Per-family gate thresholds (docs/BOOK_POLICY.md §7). Bundled into the category
# policy registry in category_policy.py — the single source of truth.
HUM_THRESHOLDS = ReadinessThresholds(0.90, 0.02, 0.95, 4.0)
STEM_FORMULA_THRESHOLDS = ReadinessThresholds(
    0.80, 0.05, 0.90, 4.0, pages_per_section_warn=8.0, pages_per_section_fail=15.0
)
STEM_DESC_THRESHOLDS = ReadinessThresholds(0.85, 0.03, 0.95, 4.0)


def get_readiness_thresholds(subject: str) -> ReadinessThresholds:
    """Resolves the gate thresholds for a subject via its category family."""
    from app.ingestion.domain.category_policy import get_category_policy

    return get_category_policy(subject).readiness_thresholds


class SourceReadiness(BaseModel):
    """Readiness verdict + structural metrics for one source/book."""

    source_id: str
    subject: str
    family: str
    verdict: ReadinessVerdict
    reasons: list[str] = Field(default_factory=list)

    # structural metrics
    sections: int
    titled_sections: int
    titled_pct: float
    chunks: int
    orphan_chunks: int
    orphan_pct: float
    duplicate_chunks: int

    # coverage metrics
    pages_parsed: int
    expected_pages: int | None
    page_coverage: float | None
    chunk_density: float | None

    # text-quality metrics
    garble_token_pct: float
    dirty_chunk_pct: float
    title_keep_rate: float
    pages_per_section: float
    spaced_letter_runs_per_100pp: float

    # segmentation v3 cross-check (GRO-145)
    toc_anchor_count: int = 0
    toc_detected_agreement: float | None = None

    # section network diagnostics (GRO-156)
    section_network_logical_sections: int = 0
    section_network_root_sections: int = 0
    section_network_parented_sections: int = 0
    section_network_parented_pct: float = 0.0
    section_network_max_depth: int = 0
    section_network_continuation_sections: int = 0


class ReadinessReport(BaseModel):
    """Aggregate readiness across every source in an ingestion run."""

    verdict: ReadinessVerdict  # worst verdict across sources (FAIL > WARN > PASS)
    sources: list[SourceReadiness] = Field(default_factory=list)

    @property
    def has_blocking_failure(self) -> bool:
        """True when any source FAILs — live commit must be blocked."""
        return self.verdict == "FAIL"


_VERDICT_RANK: dict[ReadinessVerdict, int] = {"PASS": 0, "WARN": 1, "FAIL": 2}


def evaluate_source_readiness(
    document: ParsedDocument,
    chunks: list[Chunk],
    duplicate_chunks_skipped: int = 0,
    *,
    toc_anchor_count: int = 0,
    toc_detected_agreement: float | None = None,
) -> SourceReadiness:
    """Computes structural metrics for one parsed book and grades it PASS/WARN/FAIL."""
    source = document.source
    from app.ingestion.domain.category_policy import get_category_policy

    policy = get_category_policy(source.subject)
    family = policy.family
    thr = policy.readiness_thresholds

    n_sections = len(document.sections)
    titled = sum(1 for s in document.sections if s.section_title)
    titled_pct = titled / n_sections if n_sections else 0.0

    n_chunks = len(chunks)
    orphans = sum(1 for c in chunks if c.section_block_id is None)
    orphan_pct = orphans / n_chunks if n_chunks else 0.0

    pages_parsed = len(document.pages)
    expected = source.expected.page_count if source.expected else None
    coverage = pages_parsed / expected if expected else None

    chunk_density = n_chunks / pages_parsed if pages_parsed else 0.0

    # text-quality metrics
    from app.platform.text_quality import (
        cyrillic_garble_token_ratio,
        spaced_letter_run_count,
        title_keep_rate,
    )

    titles = [s.section_title for s in document.sections]
    kept_rate = title_keep_rate(titles)
    pps = pages_parsed / n_sections if n_sections else 0.0

    all_content = "\n".join(c.content for c in chunks)
    garble_pct = cyrillic_garble_token_ratio(all_content)

    dirty_chunks = sum(
        1 for c in chunks if cyrillic_garble_token_ratio(c.content) > 0.05
    )
    dirty_pct = dirty_chunks / n_chunks if n_chunks else 0.0

    runs = sum(spaced_letter_run_count(c.content) for c in chunks)
    runs_per_100pp = runs / (pages_parsed / 100.0) if pages_parsed else 0.0

    reasons: list[str] = []
    verdict: ReadinessVerdict = "PASS"

    def fail(reason: str) -> None:
        nonlocal verdict
        verdict = "FAIL"
        reasons.append(reason)

    def warn(reason: str) -> None:
        nonlocal verdict
        reasons.append(reason)
        if verdict == "PASS":
            verdict = "WARN"

    # --- structural gates (FAIL) ------------------------------------------
    if n_sections == 0:
        fail("no sections produced")
    elif titled_pct < thr.titled_pct_min:
        fail(f"titled-section {titled_pct:.0%} < required {thr.titled_pct_min:.0%}")

    if orphan_pct > thr.orphan_pct_max:
        fail(f"orphan-chunk {orphan_pct:.0%} > allowed {thr.orphan_pct_max:.0%}")

    # --- text-quality gates (FAIL / WARN) ---------------------------------
    if garble_pct > thr.garble_token_pct_fail:
        fail(f"garble token {garble_pct:.2%} > allowed {thr.garble_token_pct_fail:.2%}")
    elif garble_pct > thr.garble_token_pct_warn:
        warn(f"garble token {garble_pct:.2%} > normal {thr.garble_token_pct_warn:.2%}")

    if dirty_pct > thr.dirty_chunk_pct_fail:
        fail(f"dirty chunk {dirty_pct:.0%} > allowed {thr.dirty_chunk_pct_fail:.0%}")
    elif dirty_pct > thr.dirty_chunk_pct_warn:
        warn(f"dirty chunk {dirty_pct:.0%} > normal {thr.dirty_chunk_pct_warn:.0%}")

    if kept_rate < thr.title_keep_rate_fail:
        fail(
            f"title keep rate {kept_rate:.0%} < required {thr.title_keep_rate_fail:.0%}"
        )
    elif kept_rate < thr.title_keep_rate_warn:
        warn(f"title keep rate {kept_rate:.0%} < normal {thr.title_keep_rate_warn:.0%}")

    if pps > thr.pages_per_section_fail:
        fail(f"pages per section {pps:.1f} > allowed {thr.pages_per_section_fail:.1f}")
    elif pps > thr.pages_per_section_warn:
        warn(f"pages per section {pps:.1f} > normal {thr.pages_per_section_warn:.1f}")

    if runs_per_100pp > thr.spaced_letter_runs_per_100pp_warn:
        warn(
            f"spaced-letter runs {runs_per_100pp:.1f}/100pp > normal {thr.spaced_letter_runs_per_100pp_warn:.1f}/100pp"
        )

    # --- segmentation cross-check (WARN only, GRO-145) --------------------
    if (
        toc_detected_agreement is not None
        and toc_anchor_count >= thr.toc_agreement_min_anchors
        and toc_detected_agreement < thr.toc_agreement_warn
    ):
        warn(
            f"TOC/heading agreement {toc_detected_agreement:.0%} < normal "
            f"{thr.toc_agreement_warn:.0%} ({toc_anchor_count} TOC anchors) — "
            f"TOC parse or heading detection unreliable for this book"
        )

    # --- coverage gate (WARN only) ----------------------------------------
    if coverage is not None and coverage < thr.page_coverage_warn:
        warn(
            f"page-coverage {coverage:.0%} < expected {thr.page_coverage_warn:.0%} "
            f"({pages_parsed}/{expected} pages)"
        )

    if chunk_density > thr.chunk_density_warn:
        warn(
            f"chunk density {chunk_density:.1f}/page > normal threshold {thr.chunk_density_warn}"
        )

    from app.ingestion.domain.section_network import summarize_section_network

    network = summarize_section_network(document.sections)

    return SourceReadiness(
        source_id=source.source_id,
        subject=source.subject,
        family=family,
        verdict=verdict,
        reasons=reasons,
        sections=n_sections,
        titled_sections=titled,
        titled_pct=titled_pct,
        chunks=n_chunks,
        orphan_chunks=orphans,
        orphan_pct=orphan_pct,
        duplicate_chunks=duplicate_chunks_skipped,
        pages_parsed=pages_parsed,
        expected_pages=expected,
        page_coverage=coverage,
        chunk_density=chunk_density,
        garble_token_pct=garble_pct,
        dirty_chunk_pct=dirty_pct,
        title_keep_rate=kept_rate,
        pages_per_section=pps,
        spaced_letter_runs_per_100pp=runs_per_100pp,
        toc_anchor_count=toc_anchor_count,
        toc_detected_agreement=toc_detected_agreement,
        section_network_logical_sections=network.logical_sections,
        section_network_root_sections=network.root_sections,
        section_network_parented_sections=network.parented_sections,
        section_network_parented_pct=network.parented_pct,
        section_network_max_depth=network.max_depth,
        section_network_continuation_sections=network.continuation_sections,
    )


def build_readiness_report(sources: list[SourceReadiness]) -> ReadinessReport:
    """Aggregates per-source verdicts into a run-level report (worst-wins)."""
    overall: ReadinessVerdict = "PASS"
    for s in sources:
        if _VERDICT_RANK[s.verdict] > _VERDICT_RANK[overall]:
            overall = s.verdict
    return ReadinessReport(verdict=overall, sources=sources)
