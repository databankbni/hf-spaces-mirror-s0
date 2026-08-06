from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalQuestion:
    id: str
    question: str
    subject: str | None
    grade: int | None
    language: str
    expected_source_id: str | None
    type: str = "factual"
    expected_source_label: str | None = None
    expected_page: int | None = None
    expected_pages: list[int] | None = None
    expected_answer: str | None = None  # GRO-89: canonical short answer for math grading
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    question_id: str
    question: str
    latency_ms: float
    confidence: float | None
    citations: list[dict[str, Any]]
    answer_snippet: str
    error: str | None = None
    answer_correct: bool | None = None  # GRO-89: None = not graded (no expected_answer)

    def pages_coverage_at_k(self, expected_keys: set[str], expected_pages: list[int] | None, k: int, tolerance: int = 1) -> float:
        if not expected_pages:
            return 1.0 if self.hit_at_k(expected_keys, k) else 0.0
        retrieved_pages = set()
        for citation in self.citations[:k]:
            in_book = citation.get("sourceId") in expected_keys or citation.get("source") in expected_keys
            page = citation.get("page")
            if in_book and isinstance(page, int):
                retrieved_pages.add(page)
        
        covered = 0
        for ep in expected_pages:
            if any(abs(rp - ep) <= tolerance for rp in retrieved_pages):
                covered += 1
        return covered / len(expected_pages)

    def fully_covered_at_k(self, expected_keys: set[str], expected_pages: list[int] | None, k: int, tolerance: int = 1) -> bool:
        if not expected_pages:
            return self.hit_at_k(expected_keys, k)
        return self.pages_coverage_at_k(expected_keys, expected_pages, k, tolerance) >= 1.0

    def hit_at_k(self, expected_keys: set[str], k: int) -> bool:
        """True if any of the top-k citations matches an expected source key.

        Matches against the stable manifest `sourceId` (preferred) exposed by
        the API as CitationOut.sourceId. Falls back to the public `source`
        citation label so the eval still works against a deployed API that
        predates the sourceId field. `expected_keys` therefore holds both the
        stable source_id and its public citation label.
        """
        if not expected_keys:
            return True  # no ground-truth yet — don't penalise
        for citation in self.citations[:k]:
            if citation.get("sourceId") in expected_keys:
                return True
            if citation.get("source") in expected_keys:
                return True
        return False

    def page_hit_at_k(self, expected_keys: set[str], expected_page: int | None, k: int, tolerance: int = 1) -> bool:
        """True if a top-k citation is from the expected book AND the expected page.

        This is the strict, meaningful signal: source-level matching is trivially
        satisfied when retrieval is subject-filtered (every chunk is from the same
        book), so it cannot distinguish good retrieval from bad. Page-level
        matching checks we surfaced the chunk that actually answers the question.
        A small *tolerance* allows for topics that straddle a page boundary.
        """
        if expected_page is None:
            return self.hit_at_k(expected_keys, k)  # fall back when no page ground-truth
        for citation in self.citations[:k]:
            in_book = citation.get("sourceId") in expected_keys or citation.get("source") in expected_keys
            page = citation.get("page")
            if in_book and isinstance(page, int) and abs(page - expected_page) <= tolerance:
                return True
        return False


@dataclass
class ReviewItem:
    question_id: str
    question: str
    reasons: list[str]
    priority: str
    confidence: float | None
    latency_ms: float
    citation_count: int
    tags: list[str]
    answer_snippet: str
    suggested_action: str


def _normalize_answer(text: str) -> str:
    """Normalize a math answer string for loose comparison.

    Rules (in order):
    1. Strip surrounding whitespace.
    2. Replace Unicode minus (\u2212) with ASCII dash.
    3. Replace decimal comma (,) with decimal point (.) — but only when inside
       a purely numeric token (avoids mangling interval separators).
    4. Unify interval separators: semicolons and commas inside bracketed
       intervals are both accepted.
    5. Collapse internal whitespace.
    6. Lowercase.
    """
    import re as _re
    t = text.strip()
    # Unicode minus → ASCII
    t = t.replace("\u2212", "-")
    # Decimal comma → decimal point when flanked by digits (e.g., 1,24 → 1.24)
    t = _re.sub(r"(\d),(\d)", r"\1.\2", t)
    # Collapse whitespace
    t = _re.sub(r"\s+", " ", t).strip()
    t = t.lower()
    return t


def check_answer(response_text: str, expected_answer: str) -> bool:
    """Heuristic: does *response_text* contain *expected_answer* as the stated result?

    Strategy (documented, no prompt-less magic):
    1. Normalize both strings (see ``_normalize_answer``).
    2. Look for the expected answer in the last 5 lines of the response
       (final result / "Cavab:" block).
    3. Also search the last line specifically (most LLMs state the final answer
       at the very end).
    4. Search after an explicit "Cavab" marker anywhere in text.

    Returns ``True`` if the expected answer appears in one of those regions,
    ``False`` otherwise.

    Design notes:
    - NO full-text search fallback: the problem statement may repeat the
      expected number (e.g. "x² − mx + 11 > 0" when expected answer is "11"),
      which would cause false positives.
    - This is deliberately conservative so that wrong answers (e.g. "12" vs "11")
      are always flagged wrong even when the correct number appears in the question
      restatement inside the response.
    """
    if not response_text or not expected_answer:
        return False

    norm_expected = _normalize_answer(expected_answer)
    if not norm_expected:
        return False

    lines = [line.strip() for line in response_text.splitlines() if line.strip()]

    # Region 1: last 5 lines — but only when response is long enough (≥ 6 lines).
    # Short responses include the problem restatement, which may repeat the expected
    # number and cause false positives (e.g. "x² − mx + 11" when answer is "11").
    if len(lines) >= 6:
        tail = lines[-5:]
        tail_text = _normalize_answer(" ".join(tail))
        if norm_expected in tail_text:
            return True

    # Region 2: last line alone — the most reliable signal.
    if lines:
        last_line = _normalize_answer(lines[-1])
        if norm_expected in last_line:
            return True

    # Region 3: after explicit "Cavab" marker anywhere in text.
    # The LLM is instructed to end with [N] citations; "Cavab:" often precedes the
    # final numeric result. Match is bounded to 300 chars to stay near the answer.
    import re as _re2
    cavab_match = _re2.search(r"cavab[:\s]+(.+)", response_text, _re2.IGNORECASE | _re2.DOTALL)
    if cavab_match:
        cavab_region = _normalize_answer(cavab_match.group(1)[:300])
        if norm_expected in cavab_region:
            return True

    return False


def _expected_keys(q: EvalQuestion) -> set[str]:
    """Ground-truth match keys: stable source_id plus public citation label.

    The label is a transitional fallback for APIs that do not yet emit
    sourceId; hit_at_k accepts a match on either key.
    """
    keys: set[str] = set()
    if q.expected_source_id and q.expected_source_id != "TBD":
        keys.add(q.expected_source_id)
    if q.expected_source_label and q.expected_source_label != "TBD":
        keys.add(q.expected_source_label)
    return keys


def _confidence_value(confidence: float | None) -> float | None:
    """Normalize confidence to the 0-1 scale used by the current API."""
    if confidence is None:
        return None
    return confidence / 100 if confidence > 1 else confidence


def _confidence_label(confidence: float | None) -> str:
    normalized = _confidence_value(confidence)
    if normalized is None:
        return "null"
    return f"{normalized:.2%}"
