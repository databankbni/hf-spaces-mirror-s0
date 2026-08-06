"""STEM data-fidelity metric (GRO-219 / S8a, PRD §9.5, §11).

The content-presence probe (`retrieval_coverage`) is **blind to garble**: it asks
whether a keyword's characters appear *somewhere*, so it cannot see that OCR turned
`Nyutonun I qanunu` into `NYUTONUN | QANUNU`, `III` into `Ili`, or a chemical
formula's subscripts into commas. This module measures that second failure layer —
*character/token integrity* over a labelled STEM fixture set — so the OCR ceiling is
quantified **before** S8b tries to correct it.

Pure domain: no IO. Two reused signals from the ingestion `garble%` machinery
(`app.platform.text_quality`) plus two label-driven signals:

* **garble_token_ratio** — share of Cyrillic-garbled tokens (Azerbaijani is Latin;
  Cyrillic is OCR noise). Catches `Ҹ`/`Л`-contaminated formulae and node titles.
* **spaced_run_count** — `Q a l i l e o`-style letter-spray runs.
* **expected-token integrity** — of the canonical tokens a correct extraction MUST
  contain (`Nyutonun I qanunu`, `CH₂`, `Türkmənçay`), how many survive intact. This
  is what exposes `I`→`|`, which no garble ratio can see.
* **forbidden-token presence** — labelled known corruptions (`NYUTONUN |`,
  `Lurkmoncay`) that a corrected extraction must NOT contain.

Matching is over a casefolded, whitespace-collapsed view so ordinary spacing never
counts as corruption, while the specific mangles (a pipe for `I`, a Cyrillic letter,
a collapsed subscript) are detected exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.platform.text_quality import cyrillic_garble_token_ratio, spaced_letter_run_count

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Casefold and collapse whitespace runs to single spaces for token matching."""
    return _WHITESPACE.sub(" ", text).casefold().strip()


@dataclass(frozen=True)
class FidelityFixture:
    """One labelled STEM text sample and the integrity claims made about it."""

    id: str
    subject: str
    category: str  # law_numbering | formula | node_title | figure_placement
    text: str
    expected_tokens: tuple[str, ...] = ()
    forbidden_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class FidelityScore:
    fixture_id: str
    subject: str
    category: str
    garble_token_ratio: float
    spaced_run_count: int
    expected_total: int
    expected_present: tuple[str, ...]
    expected_missing: tuple[str, ...]
    forbidden_present: tuple[str, ...]

    @property
    def expected_integrity(self) -> float:
        """Fraction of canonical tokens that survived intact (1.0 if none claimed)."""
        if self.expected_total == 0:
            return 1.0
        return len(self.expected_present) / self.expected_total

    @property
    def clean(self) -> bool:
        """No missing canonical token, no known corruption, no letter-spray run.

        Deliberately strict: garble_token_ratio is reported but not part of `clean`
        because a low Cyrillic ratio can coexist with a fatal single-glyph mangle
        (`I`→`|`) — the expected/forbidden labels are the authoritative check.
        """
        return (
            not self.expected_missing
            and not self.forbidden_present
            and self.spaced_run_count == 0
        )


def score_fixture(fixture: FidelityFixture) -> FidelityScore:
    normalized = _normalize(fixture.text)
    present, missing = [], []
    for token in fixture.expected_tokens:
        (present if _normalize(token) in normalized else missing).append(token)
    forbidden_present = [
        token for token in fixture.forbidden_tokens if _normalize(token) in normalized
    ]
    return FidelityScore(
        fixture_id=fixture.id,
        subject=fixture.subject,
        category=fixture.category,
        garble_token_ratio=cyrillic_garble_token_ratio(fixture.text),
        spaced_run_count=spaced_letter_run_count(fixture.text),
        expected_total=len(fixture.expected_tokens),
        expected_present=tuple(present),
        expected_missing=tuple(missing),
        forbidden_present=tuple(forbidden_present),
    )


@dataclass(frozen=True)
class CategorySummary:
    category: str
    count: int
    mean_expected_integrity: float
    mean_garble_ratio: float
    clean_rate: float
    forbidden_hits: int


@dataclass(frozen=True)
class FidelitySummary:
    fixtures_total: int
    mean_expected_integrity: float
    clean_rate: float
    per_category: tuple[CategorySummary, ...]

    def category(self, name: str) -> CategorySummary | None:
        return next((c for c in self.per_category if c.category == name), None)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 1.0


def summarize_fidelity(scores: list[FidelityScore]) -> FidelitySummary:
    categories = sorted({s.category for s in scores})
    per_category = []
    for name in categories:
        group = [s for s in scores if s.category == name]
        per_category.append(
            CategorySummary(
                category=name,
                count=len(group),
                mean_expected_integrity=_mean([s.expected_integrity for s in group]),
                mean_garble_ratio=_mean([s.garble_token_ratio for s in group]),
                clean_rate=_mean([1.0 if s.clean else 0.0 for s in group]),
                forbidden_hits=sum(len(s.forbidden_present) for s in group),
            )
        )
    return FidelitySummary(
        fixtures_total=len(scores),
        mean_expected_integrity=_mean([s.expected_integrity for s in scores]),
        clean_rate=_mean([1.0 if s.clean else 0.0 for s in scores]),
        per_category=tuple(per_category),
    )


@dataclass(frozen=True)
class ThresholdBreach:
    category: str
    metric: str
    threshold: float
    measured: float


def check_thresholds(
    summary: FidelitySummary, thresholds: dict[str, float]
) -> list[ThresholdBreach]:
    """Compare per-category `mean_expected_integrity` against pinned thresholds.

    Returns the breaches (empty ⇒ pass). A category named in `thresholds` but absent
    from the run is itself a breach (`measured = 0.0`) so a silently-dropped fixture
    category cannot pass the gate. Intended to be wired **non-fatal** until S8b.
    """
    breaches: list[ThresholdBreach] = []
    for category, minimum in sorted(thresholds.items()):
        found = summary.category(category)
        measured = found.mean_expected_integrity if found else 0.0
        if measured < minimum:
            breaches.append(
                ThresholdBreach(
                    category=category,
                    metric="mean_expected_integrity",
                    threshold=minimum,
                    measured=measured,
                )
            )
    return breaches
