"""Content-coverage metrics for retrieval — does the retrieved context actually
contain the *exact* things a question demands?

Motivation
----------
The production retriever (`app.retrieval`) is a single dense-vector nearest-
neighbour search: the raw question is embedded into one 1024-d vector and the
globally-closest chunks (by cosine) are returned, subject only to
subject/grade/language filters. Nothing in that path guarantees that a question
demanding a *specific enumerated list* ("which exact khanates were ceded by the
Gülüstan treaty") or a *specific fact* ("the treaty's naval clause") has that
content present in the returned chunks. A page-overlap check cannot see this,
because a chunk can overlap the right page yet omit the enumeration (chunking
splits it). So we measure the *content* instead.

Each question carries `coverage_requirements`: named, typed demands, each with a
set of keywords whose presence in the retrieved text is objectively checkable by
substring. This module is the pure, DB-free, network-free scoring core; the CLI
in `scripts/eval_retrieval_coverage.py` sources the retrieved chunks from the
live pipeline and feeds their text in.

This module deliberately renders **no verdict about the retriever's adequacy** —
it reports which required keywords are present in the selected context vs the
wider candidate pool vs nowhere. A downstream reasoning pass (Fable 5) interprets
the gaps. Keeping judgement out of here keeps the metric objective and stable.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# --- text normalisation -----------------------------------------------------
# Azerbaijani has dotted/dotless i (İ/i, I/ı); OCR also introduces stray
# whitespace and line breaks mid-word. We casefold, collapse whitespace, and
# strip combining marks so a keyword match reflects "the concept surfaced in the
# text", not an accident of OCR spacing or letter-case. We do NOT stem or
# translate — a keyword must genuinely appear.
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lower-case (locale-agnostic), NFKC-fold, and collapse whitespace."""
    folded = unicodedata.normalize("NFKC", text)
    # Map the Azerbaijani dotted capital İ and dotless ı to a common 'i' so
    # keyword casing never causes a false miss.
    folded = folded.replace("İ", "i").replace("I", "ı")
    folded = folded.casefold()
    return _WHITESPACE.sub(" ", folded).strip()


def keyword_present(keyword: str, normalized_haystack: str) -> bool:
    """True when `keyword` (after the same normalisation) is a substring."""
    needle = normalize_text(keyword)
    if not needle:
        return False
    return needle in normalized_haystack


# --- requirement model ------------------------------------------------------

RequirementKind = str  # "exact_enumeration" | "specific_fact" | "concept"
Grounding = str  # "source" (pulled from the book) | "topical" (authored)


@dataclass(frozen=True)
class CoverageRequirement:
    """One demand a question places on the retrieved context.

    match_mode governs when the requirement is satisfied:
      * "all"          — every keyword must be present
      * "any"          — at least one keyword present
      * "threshold:N"  — at least N distinct keywords present
    """

    id: str
    kind: RequirementKind
    description: str
    grounded: Grounding
    match_mode: str
    keywords: tuple[str, ...]

    def required_hits(self) -> int:
        mode = self.match_mode.strip().lower()
        if mode == "all":
            return len(self.keywords)
        if mode == "any":
            return 1
        if mode.startswith("threshold:"):
            n = int(mode.split(":", 1)[1])
            return max(1, min(n, len(self.keywords)))
        raise ValueError(f"unknown match_mode: {self.match_mode!r}")


@dataclass(frozen=True)
class RequirementCoverage:
    requirement_id: str
    kind: RequirementKind
    grounded: Grounding
    match_mode: str
    keywords_total: int
    required_hits: int
    found_in_selected: tuple[str, ...]
    found_in_candidates: tuple[str, ...]
    missing_everywhere: tuple[str, ...]
    satisfied_in_selected: bool
    satisfied_in_candidates: bool


def evaluate_requirement(
    requirement: CoverageRequirement,
    *,
    selected_text: str,
    candidate_text: str,
) -> RequirementCoverage:
    """Score one requirement against the selected context and candidate pool.

    `selected_text` is the concatenation of the chunks that actually reached the
    model (the top_k after context-packing); `candidate_text` is the full
    pre-cutoff candidate pool. Scoring both tells apart "the retriever never
    surfaced it" from "it was surfaced but ranked/packed out".
    """
    selected_norm = normalize_text(selected_text)
    candidate_norm = normalize_text(candidate_text)

    found_selected = tuple(k for k in requirement.keywords if keyword_present(k, selected_norm))
    found_candidates = tuple(k for k in requirement.keywords if keyword_present(k, candidate_norm))
    missing = tuple(
        k for k in requirement.keywords if not keyword_present(k, candidate_norm)
    )

    required = requirement.required_hits()
    return RequirementCoverage(
        requirement_id=requirement.id,
        kind=requirement.kind,
        grounded=requirement.grounded,
        match_mode=requirement.match_mode,
        keywords_total=len(requirement.keywords),
        required_hits=required,
        found_in_selected=found_selected,
        found_in_candidates=found_candidates,
        missing_everywhere=missing,
        satisfied_in_selected=len(found_selected) >= required,
        satisfied_in_candidates=len(found_candidates) >= required,
    )


@dataclass(frozen=True)
class QuestionCoverage:
    question_id: str
    requirements: tuple[RequirementCoverage, ...]

    @property
    def all_satisfied_in_selected(self) -> bool:
        return bool(self.requirements) and all(
            r.satisfied_in_selected for r in self.requirements
        )

    @property
    def all_satisfied_in_candidates(self) -> bool:
        return bool(self.requirements) and all(
            r.satisfied_in_candidates for r in self.requirements
        )

    @property
    def satisfied_selected_count(self) -> int:
        return sum(1 for r in self.requirements if r.satisfied_in_selected)


def evaluate_question(
    question_id: str,
    requirements: list[CoverageRequirement],
    *,
    selected_text: str,
    candidate_text: str,
) -> QuestionCoverage:
    return QuestionCoverage(
        question_id=question_id,
        requirements=tuple(
            evaluate_requirement(
                r, selected_text=selected_text, candidate_text=candidate_text
            )
            for r in requirements
        ),
    )


# --- Enumeration Item Coverage (EIC) ----------------------------------------
# CCR (question-level) asks "did *every* requirement pass?"; a complete-
# enumeration requirement can fail that while still surfacing most of its items.
# EIC exposes that partial coverage: for the `exact_enumeration` requirements it
# is the mean, over requirements, of the fraction of demanded keywords present.
# It is computed over the SAME RequirementCoverage the question scoring produced,
# so it needs no extra retrieval or DB work — it is a ratio over existing fields.
#
# Honesty note carried from the probe design: substring presence is *necessary,
# not sufficient*. A keyword can nest inside another (`arktik` ⊂ `Arktika`) or
# sit in OCR-garbled text; EIC inherits both leniencies. It is a context-presence
# metric, never a proof of answer sufficiency (see PRD §9.1/§9.4).

EXACT_ENUMERATION: RequirementKind = "exact_enumeration"


@dataclass(frozen=True)
class EnumerationItemCoverage:
    """Aggregate item-level coverage over `exact_enumeration` requirements.

    `requirements_counted` is how many such requirements contributed; the two
    rates are means of per-requirement (present ÷ `keywords_total`) over the
    selected context and the wider candidate pool respectively. When no
    `exact_enumeration` requirement is present the metric is undefined; we report
    it as 0 counted with 0.0 rates so callers can detect the empty case rather
    than divide by zero.
    """

    requirements_counted: int
    eic_selected: float
    eic_candidates: float


def enumeration_item_coverage(
    questions: Iterable[QuestionCoverage],
) -> EnumerationItemCoverage:
    """Mean per-requirement item coverage over all `exact_enumeration` demands.

    A requirement with `keywords_total == 0` cannot express a ratio and is
    skipped (it should never occur in a valid set, but the guard keeps the
    metric total-function rather than raising on malformed data).
    """
    selected_ratios: list[float] = []
    candidate_ratios: list[float] = []
    for question in questions:
        for requirement in question.requirements:
            if requirement.kind != EXACT_ENUMERATION:
                continue
            if requirement.keywords_total <= 0:
                continue
            total = requirement.keywords_total
            selected_ratios.append(len(requirement.found_in_selected) / total)
            candidate_ratios.append(len(requirement.found_in_candidates) / total)

    if not selected_ratios:
        return EnumerationItemCoverage(
            requirements_counted=0, eic_selected=0.0, eic_candidates=0.0
        )

    counted = len(selected_ratios)
    return EnumerationItemCoverage(
        requirements_counted=counted,
        eic_selected=sum(selected_ratios) / counted,
        eic_candidates=sum(candidate_ratios) / counted,
    )


# --- Run-level summary + regression comparison (the gate math) --------------
# The regression gate (PRD §8) compares a fresh run to a pinned baseline. The
# metric math and the comparison rules live here — pure and unit-testable — so
# the CLI in `scripts/ci_retrieval_gate.py` is only an IO shell (parse JSON,
# call these, format, set the exit code).

# EIC is a mean of exact ratios recomputed by identical code on identically
# shaped data; when nothing changed the two runs are bit-equal. We still compare
# with a tiny tolerance so floating-point summation order can never manufacture
# a spurious regression.
_EIC_EPSILON = 1e-9


@dataclass(frozen=True)
class SubjectCoverage:
    subject: str
    covered_in_selected: int
    total: int


@dataclass(frozen=True)
class CoverageSummary:
    """Everything the regression gate compares, derived purely from scored
    questions labelled with their subject."""

    questions_total: int
    covered_in_selected: int  # CCR numerator
    covered_in_candidates: int  # PCR numerator
    eic: EnumerationItemCoverage
    per_subject: tuple[SubjectCoverage, ...]
    covered_selected_ids: frozenset[str]

    @property
    def ccr(self) -> float:
        return self.covered_in_selected / self.questions_total if self.questions_total else 0.0

    @property
    def pcr(self) -> float:
        return self.covered_in_candidates / self.questions_total if self.questions_total else 0.0


def summarize_coverage(
    labelled_questions: Iterable[tuple[str, QuestionCoverage]],
) -> CoverageSummary:
    """Aggregate scored questions (each tagged with a subject) into the summary
    the gate pins and compares. Pure: no IO, deterministic ordering."""
    questions: list[tuple[str, QuestionCoverage]] = list(labelled_questions)

    covered_selected_ids: set[str] = set()
    covered_in_candidates = 0
    subject_covered: dict[str, int] = {}
    subject_total: dict[str, int] = {}

    for subject, question in questions:
        subject_total[subject] = subject_total.get(subject, 0) + 1
        if question.all_satisfied_in_selected:
            covered_selected_ids.add(question.question_id)
            subject_covered[subject] = subject_covered.get(subject, 0) + 1
        if question.all_satisfied_in_candidates:
            covered_in_candidates += 1

    per_subject = tuple(
        SubjectCoverage(
            subject=subject,
            covered_in_selected=subject_covered.get(subject, 0),
            total=subject_total[subject],
        )
        for subject in sorted(subject_total)
    )

    return CoverageSummary(
        questions_total=len(questions),
        covered_in_selected=len(covered_selected_ids),
        covered_in_candidates=covered_in_candidates,
        eic=enumeration_item_coverage(q for _, q in questions),
        per_subject=per_subject,
        covered_selected_ids=frozenset(covered_selected_ids),
    )


@dataclass(frozen=True)
class CoverageRegression:
    """One way a candidate run is worse than the pinned baseline."""

    metric: str
    detail: str
    baseline_value: float
    candidate_value: float


def compare_summaries(
    baseline: CoverageSummary, candidate: CoverageSummary
) -> tuple[CoverageRegression, ...]:
    """Return every way `candidate` regresses against `baseline` (empty = pass).

    A regression is any drop in CCR, PCR, EIC (selected or candidates), any
    per-subject CCR drop (including a subject that vanishes from the candidate),
    or any individual question going covered→uncovered in the selected context.
    Improvements are never flagged; the gate only guards against going backwards.
    """
    regressions: list[CoverageRegression] = []

    if candidate.covered_in_selected < baseline.covered_in_selected:
        regressions.append(
            CoverageRegression(
                "CCR",
                "questions fully covered in selected context dropped",
                baseline.covered_in_selected,
                candidate.covered_in_selected,
            )
        )
    if candidate.covered_in_candidates < baseline.covered_in_candidates:
        regressions.append(
            CoverageRegression(
                "PCR",
                "questions fully covered in candidate pool dropped",
                baseline.covered_in_candidates,
                candidate.covered_in_candidates,
            )
        )
    if candidate.eic.eic_selected < baseline.eic.eic_selected - _EIC_EPSILON:
        regressions.append(
            CoverageRegression(
                "EIC(selected)",
                "enumeration item coverage in selected context dropped",
                baseline.eic.eic_selected,
                candidate.eic.eic_selected,
            )
        )
    if candidate.eic.eic_candidates < baseline.eic.eic_candidates - _EIC_EPSILON:
        regressions.append(
            CoverageRegression(
                "EIC(candidates)",
                "enumeration item coverage in candidate pool dropped",
                baseline.eic.eic_candidates,
                candidate.eic.eic_candidates,
            )
        )

    candidate_subjects = {s.subject: s for s in candidate.per_subject}
    for base_subject in baseline.per_subject:
        cand_subject = candidate_subjects.get(base_subject.subject)
        cand_covered = cand_subject.covered_in_selected if cand_subject else 0
        if cand_covered < base_subject.covered_in_selected:
            regressions.append(
                CoverageRegression(
                    f"CCR[{base_subject.subject}]",
                    "per-subject coverage dropped"
                    if cand_subject
                    else "subject missing from candidate run",
                    base_subject.covered_in_selected,
                    cand_covered,
                )
            )

    for question_id in sorted(
        baseline.covered_selected_ids - candidate.covered_selected_ids
    ):
        regressions.append(
            CoverageRegression(
                "question",
                f"'{question_id}' went covered→uncovered in selected context",
                1.0,
                0.0,
            )
        )

    return tuple(regressions)
