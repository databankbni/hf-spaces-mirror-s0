"""Mandatory miss triage for retrieval coverage eval union (PRD §9.3).

Every failing question on the v1∪v2 union must carry exactly one classification
before merge. `retrieval_defect` blocks merge; the other three are recorded
follow-ups.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TriageClass(str, Enum):
    CORPUS_ABSENCE = "corpus_absence"
    DATA_QUALITY_DEFECT = "data_quality_defect"
    EVAL_KEYWORD_DEFECT = "eval_keyword_defect"
    RETRIEVAL_DEFECT = "retrieval_defect"


@dataclass(frozen=True)
class MissTriageEntry:
    question_id: str
    triage_class: TriageClass
    note: str


def parse_triage_class(raw: str) -> TriageClass:
    try:
        return TriageClass(raw.strip())
    except ValueError as exc:
        valid = ", ".join(c.value for c in TriageClass)
        raise ValueError(f"unknown triage class {raw!r}; expected one of {valid}") from exc


def validate_triage_coverage(
    failed_question_ids: frozenset[str],
    triage_by_id: dict[str, MissTriageEntry],
) -> list[str]:
    """Return human-readable errors; empty list means triage gate passes."""
    errors: list[str] = []
    for qid in sorted(failed_question_ids):
        entry = triage_by_id.get(qid)
        if entry is None:
            errors.append(f"unclassified miss: {qid}")
        elif entry.triage_class is TriageClass.RETRIEVAL_DEFECT:
            errors.append(f"retrieval_defect blocks merge: {qid} — {entry.note}")
    return errors


def triage_from_yaml_rows(rows: list[dict]) -> dict[str, MissTriageEntry]:
    out: dict[str, MissTriageEntry] = {}
    for row in rows:
        qid = row["id"]
        out[qid] = MissTriageEntry(
            question_id=qid,
            triage_class=parse_triage_class(row["triage_class"]),
            note=str(row.get("note", "")).strip(),
        )
    return out
