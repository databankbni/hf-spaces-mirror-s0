from __future__ import annotations

import math
from typing import Any, Dict, Tuple


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    return value


def ground_report_claims(report: Dict[str, Any], source_facts: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """Lightweight guardrail before the report is serialized.

    Numeric grounding is enforced at the LLM copy boundary. This guard catches
    non-finite values and leaves an audit trail for downstream inspection.
    """
    clean_report = sanitize_for_json(report)
    warnings: list[str] = []
    if clean_report != report:
        warnings.append("non_finite_value_sanitized")
    if not source_facts.get("point_price_yuan"):
        warnings.append("missing_point_price_source")
    if warnings:
        clean_report["claim_grounding_warnings"] = warnings
    return clean_report, warnings

