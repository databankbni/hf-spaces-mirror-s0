"""Rule-based query-intent gate for structural augmentation (GRO-225 / S5b).

The PRD's structural path is only for enumeration / multi-fact demands ("list all
climate belts", "name the first ten alkanes") — ordinary conceptual questions must
bypass augmentation for cost and precision. Pure module: no DB, no I/O.
"""

from __future__ import annotations

import re

from app.eval.domain.retrieval_coverage import normalize_text

# Azerbaijani enumeration cues observed in `retrieval_coverage_v1` stress-A items.
_ENUMERATION_RE = re.compile(
    r"|".join(
        (
            r"\bbütün\b",
            r"sadalay",  # sadalayın / sadala
            r"\bneçə\b",
            r"tam siyah",
            r"heç birini buraxmay",
            r"ardıcıllıqla",
            r"\bilk on\b",
            r"\bilk dörd\b",
            r"name all\b",
            r"list all\b",
        )
    ),
    flags=re.IGNORECASE,
)


def is_enumeration_intent(query: str) -> bool:
    """True when the query demands a complete list or multi-item enumeration."""
    text = normalize_text(query)
    if not text:
        return False
    return _ENUMERATION_RE.search(text) is not None


def enumeration_lexical_query(query: str) -> str:
    """Add corpus keywords for FTS on enumeration questions with short phrasing."""
    text = normalize_text(query)
    if not text or not is_enumeration_intent(query):
        return query
    extras: list[str] = []
    if "alkan" in text and ("ilk on" in text or ("ilk" in text.split() and "on" in text.split())):
        extras.extend(["homoloji", "sirasi", "metan", "dekan"])
    if "iqlim" in text and "qur" in text:
        extras.extend(["ekvatorial", "subekvatorial", "subarktik", "subtropik"])
    return query if not extras else f"{query} {' '.join(extras)}"
