from __future__ import annotations

import math
from typing import Any

from .selection_score_config import get_selection_score_config


FIELD_SAMPLE_SIZE_KEYS = {
    "avg_gross_profit": "profit_observed_count",
    "median_gross_profit": "profit_observed_count",
    "loss_rate": "profit_observed_count",
    "avg_turnover_days": "turnover_observed_count",
    "median_turnover_days": "turnover_observed_count",
    "turnover_efficiency_index": "turnover_observed_count",
    "sale_conversion_rate": "listed_conversion_denominator",
    "acquisition_conversion_rate": "acquired_conversion_denominator",
    "sold_from_acquired_rate": "acquired_sellthrough_denominator",
}


def smooth_metric(raw: Any, baseline: Any, sample_size: Any, strength: Any = 20) -> float | None:
    current = _num(raw)
    base = _num(baseline)
    if current is None and base is None:
        return None
    if current is None:
        return base
    if base is None:
        return current
    n = max(0.0, _num(sample_size, 0.0) or 0.0)
    k = max(0.0, _num(strength, 20.0) or 20.0)
    if k <= 0:
        return current
    return (n * current + k * base) / (n + k)


def smooth_business_metrics(
    history: dict[str, Any],
    baseline: dict[str, Any],
    *,
    sample_size: Any = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or get_selection_score_config()
    smoothing = cfg.get("metric_smoothing") or {}
    strength = smoothing.get("strength", 20)
    fields = smoothing.get("fields") or []
    fallback_sample_size = sample_size if sample_size is not None else history.get("sold_count_90d", history.get("sold_count"))
    out = dict(history or {})
    for field in fields:
        sample_key = FIELD_SAMPLE_SIZE_KEYS.get(field)
        field_sample_size = (history or {}).get(sample_key) if sample_key else None
        if field_sample_size is None:
            field_sample_size = fallback_sample_size
        out[field] = _round(smooth_metric((history or {}).get(field), (baseline or {}).get(field), field_sample_size, strength))
        out[f"raw_{field}"] = (history or {}).get(field)
        out[f"{field}_smoothing_sample_size"] = int(_num(field_sample_size, 0) or 0)
    out["smoothing_strength"] = strength
    out["smoothing_sample_size"] = int(_num(fallback_sample_size, 0) or 0)
    return out


def smooth_business_metrics_hierarchical(
    history: dict[str, Any],
    parent_history: dict[str, Any],
    baseline: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shrink a local group to its national series parent, then baseline_all."""
    cfg = config or get_selection_score_config()
    parent_smoothed = smooth_business_metrics(parent_history or {}, baseline or {}, config=cfg)
    local_smoothed = smooth_business_metrics(history or {}, parent_smoothed, config=cfg)
    local_smoothed["smoothing_hierarchy"] = "local_to_national_series_to_baseline"
    local_smoothed["smoothing_parent_scope"] = (parent_history or {}).get("history_scope") or "national_series"
    for field in (cfg.get("metric_smoothing") or {}).get("fields") or []:
        local_smoothed[f"{field}_parent_prior"] = parent_smoothed.get(field)
    return local_smoothed


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None
