"""Corpus coverage and legal-status audit logic."""
from __future__ import annotations

from collections import defaultdict
from app.ingestion.domain.models import ManifestSource

RISKY_LEGAL = {"TBD", "do_not_ingest", "permission_requested"}
RISKY_REVIEW = {"flagged"}

TIER_LABELS = {
    1: "official_textbook",
    2: "dim_practice",
    3: "licensed_pedagogy",
    4: "teacher_annotation",
    5: "student_telemetry",
}


def coverage_summary(sources: list[ManifestSource]) -> dict:
    by_subject: dict[str, list[str]] = defaultdict(list)
    by_grade: dict[str | int, list[str]] = defaultdict(list)
    by_language: dict[str, list[str]] = defaultdict(list)
    by_category: dict[str, list[str]] = defaultdict(list)
    by_tier: dict[int, list[str]] = defaultdict(list)
    by_legal: dict[str, list[str]] = defaultdict(list)
    by_review: dict[str, list[str]] = defaultdict(list)

    for source in sources:
        sid = source.source_id
        by_subject[source.subject].append(sid)
        by_grade[source.grade if source.grade is not None else "ungraded"].append(sid)
        by_language[source.language].append(sid)
        by_category[source.source_category].append(sid)
        by_tier[source.source_tier].append(sid)
        by_legal[source.legal_status].append(sid)
        by_review[source.review_status].append(sid)

    return {
        "total_sources": len(sources),
        "by_subject": {k: len(v) for k, v in sorted(by_subject.items())},
        "by_grade": {str(k): len(v) for k, v in sorted(by_grade.items(), key=lambda x: (str(x[0]).isdigit() is False, x[0]))},
        "by_language": {k: len(v) for k, v in sorted(by_language.items())},
        "by_source_category": {k: len(v) for k, v in sorted(by_category.items())},
        "by_source_tier": {f"{k} ({TIER_LABELS.get(k, '?')})": len(v) for k, v in sorted(by_tier.items())},
        "by_legal_status": {k: len(v) for k, v in sorted(by_legal.items())},
        "by_review_status": {k: len(v) for k, v in sorted(by_review.items())},
    }


def risky_sources(sources: list[ManifestSource]) -> list[dict]:
    risky = []
    for source in sources:
        reasons = []
        if source.legal_status in RISKY_LEGAL:
            reasons.append(f"legal_status={source.legal_status!r}")
        if source.review_status in RISKY_REVIEW:
            reasons.append(f"review_status={source.review_status!r}")
        if reasons:
            risky.append({
                "source_id": source.source_id,
                "title": source.title,
                "reasons": reasons,
            })
    return risky
