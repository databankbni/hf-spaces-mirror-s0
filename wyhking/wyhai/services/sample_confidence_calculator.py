from __future__ import annotations

import math
from typing import Any

from .selection_score_config import get_selection_score_config


def calculate_sample_confidence(
    *,
    candidate_count: Any = 0,
    acquired_count: Any = 0,
    sold_count: Any = 0,
    sample_count: Any = None,
    data_coverage: Any = 1.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return sample confidence for selection ranking.

    The sold-count bands are configurable.  The output is intentionally separate
    from business quality so a tiny but lucky historical sample cannot become a
    strong recommendation by itself.
    """

    cfg = config or get_selection_score_config()
    sample_cfg = cfg.get("sample_confidence") or {}
    candidate = _num(candidate_count)
    acquired = _num(acquired_count)
    sold = _num(sold_count if sold_count is not None else sample_count)
    coverage = max(float(sample_cfg.get("coverage_floor", 0.45)), min(1.0, _num(data_coverage, 1.0)))
    level = _level_for_counts(sold=sold, acquired=acquired, levels=sample_cfg.get("levels") or [])
    cap = float(level.get("confidence_cap", 0.5))
    acquired_reference = max(1.0, float(sample_cfg.get("acquired_support_reference", 50)))
    candidate_reference = max(1.0, float(sample_cfg.get("candidate_support_reference", 80)))
    acquired_support = min(1.0, math.sqrt(max(acquired, 0.0) / acquired_reference))
    candidate_support = min(1.0, math.sqrt(max(candidate, 0.0) / candidate_reference))
    support = 0.68 + 0.22 * acquired_support + 0.10 * candidate_support
    confidence = max(0.0, min(cap, cap * coverage * support))
    sample_level = str(level.get("name") or "unknown")
    note = str(level.get("note") or "")
    if acquired > 0 and sold > acquired:
        note = _join_note(note, "有效经营证据覆盖不完整，置信度已下调")
        confidence *= 0.85
    if coverage < 0.8:
        note = _join_note(note, "行情/经营字段覆盖不足，置信度已折减")
    return {
        "confidence_score": round(max(0.0, min(cap, confidence)), 4),
        "confidence_cap": round(cap, 4),
        "sample_level": sample_level,
        "data_quality_note": note or f"样本等级：{sample_level}",
        "candidate_count": int(candidate),
        "acquired_count": int(acquired),
        "sold_count": int(sold),
        "data_coverage": round(coverage, 4),
    }


def _level_for_counts(*, sold: float, acquired: float, levels: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = {"name": "unknown", "confidence_cap": 0.45, "note": "样本等级未知"}
    for level in levels:
        min_sold = level.get("min_sold_count")
        max_sold = level.get("max_sold_count")
        min_acquired = level.get("min_acquired_count")
        if min_sold is not None and sold < float(min_sold):
            continue
        if max_sold is not None and sold > float(max_sold):
            continue
        if min_acquired is not None and acquired < float(min_acquired):
            continue
        return level
    if sold >= 30:
        high_levels = [item for item in levels if str(item.get("name")) == "high"]
        return high_levels[0] if high_levels else fallback
    return fallback


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _join_note(left: str, right: str) -> str:
    return f"{left}；{right}" if left else right
