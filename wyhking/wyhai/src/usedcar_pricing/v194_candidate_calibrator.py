"""Candidate-summary residual calibration for v194 quotes.

The calibrator is deliberately small and auditable: it never sees a target
price at inference time.  It receives the already filtered C2B point
candidates, turns their price cloud and six-element match quality into one
row of features, and predicts a bounded log correction on top of the
statistical candidate baseline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .v194_price_policy import weighted_quantile


CATEGORICAL_FEATURES = ["series", "city", "condition", "color", "grade"]

NUMERIC_FEATURES = [
    "year",
    "age",
    "mileage",
    "transfer",
    "count",
    "strict_count",
    "fallback_count",
    "l0_count",
    "l1_count",
    "l2_count",
    "city_match_mean",
    "color_match_mean",
    "condition_match_mean",
    "observable_match_mean",
    "age_gap_min",
    "mileage_gap_min",
    "transfer_gap_min",
    "age_gap_weighted_mean",
    "mileage_gap_weighted_mean",
    "transfer_gap_weighted_mean",
    "days_min",
    "days_weighted_mean",
    "price_min",
    "price_max",
    "price_std",
    "price_weighted_mean",
    "top1_price",
    "baseline_p10",
    "baseline_p20",
    "baseline_p25",
    "baseline_p30",
    "baseline_p40",
    "baseline_p50",
    "baseline_p75",
    "baseline_iqr_ratio",
    "baseline_price",
]

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def _num_series(frame: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    return (
        pd.to_numeric(frame.get(name, pd.Series(default, index=frame.index)), errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(default)
    )


def _query_float(query: dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = query.get(name)
        if value is None or value == "":
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(parsed):
            return parsed
    return default


def _query_text(query: dict[str, Any], *names: str, default: str = "missing") -> str:
    for name in names:
        value = query.get(name)
        if value is not None and str(value).strip():
            return str(value)
    return default


def point_candidate_frame(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return the candidate subset eligible for a C2B point baseline."""

    if candidates.empty:
        return candidates.copy()
    if "used_for_point_baseline" in candidates.columns:
        point = candidates[candidates["used_for_point_baseline"].fillna(False)].copy()
    else:
        point = candidates[candidates.get("retrieval_level", "").isin(["L0", "L1", "L2"])].copy()
    if point.empty:
        return point
    return point


def _candidate_weights(point: pd.DataFrame) -> np.ndarray:
    if "listwise_final_weight" in point.columns:
        weights = pd.to_numeric(point["listwise_final_weight"], errors="coerce")
        if weights.notna().all() and weights.gt(0).any():
            return weights.fillna(0.0).to_numpy(float)
    for column in ("final_retrieval_weight", "rolling_candidate_score", "heuristic_retrieval_weight"):
        if column in point.columns:
            raw = pd.to_numeric(point[column], errors="coerce").fillna(0.0).to_numpy(float)
            if np.isfinite(raw).any() and np.nanmax(raw) > 0:
                return np.exp(np.clip(raw - np.nanmax(raw), -20, 0))
    return np.ones(len(point), dtype=float)


def build_candidate_summary_features(
    candidates: pd.DataFrame,
    query: dict[str, Any],
    *,
    baseline_price: float | None = None,
) -> dict[str, Any]:
    """Build one inference-safe feature row from point candidates."""

    point = point_candidate_frame(candidates)
    row: dict[str, Any] = {
        "series": _query_text(query, "series"),
        "city": _query_text(query, "city"),
        "condition": _query_text(query, "condition_risk_level_strict", "condition_risk_level"),
        "color": _query_text(query, "color", "color_key_v194"),
        "grade": _query_text(query, "inspection_grade_norm"),
        "year": _query_float(query, "model_year"),
        "age": _query_float(query, "age_years"),
        "mileage": _query_float(query, "mileage_wan_km"),
        "transfer": _query_float(query, "transfer_count"),
    }
    if point.empty:
        for name in NUMERIC_FEATURES:
            row.setdefault(name, 0.0)
        row["baseline_price"] = float(baseline_price or 0.0)
        return row

    point = point.copy()
    values = _num_series(point, "price_yuan", 0.0).clip(lower=1000).to_numpy(float)
    weights = _candidate_weights(point)
    if not np.isfinite(weights).any() or np.nansum(weights) <= 0:
        weights = np.ones(len(point), dtype=float)
    weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)

    sorted_by_weight = np.argsort(-weights)
    top1 = float(values[sorted_by_weight[0]]) if len(values) else 0.0
    p10 = weighted_quantile(values, weights, 0.10)
    p20 = weighted_quantile(values, weights, 0.20)
    p25 = weighted_quantile(values, weights, 0.25)
    p30 = weighted_quantile(values, weights, 0.30)
    p40 = weighted_quantile(values, weights, 0.40)
    p50 = weighted_quantile(values, weights, 0.50)
    p75 = weighted_quantile(values, weights, 0.75)
    default_baseline = p25 if pd.notna(point.get("listwise_final_weight", pd.Series(np.nan, index=point.index))).all() else p50

    def mean_flag(name: str) -> float:
        return float(_num_series(point, name, 0.0).mean())

    def min_num(name: str) -> float:
        series = _num_series(point, name, np.nan).replace([np.inf, -np.inf], np.nan).dropna()
        return float(series.min()) if not series.empty else 0.0

    def weighted_mean(name: str) -> float:
        series = _num_series(point, name, 0.0).to_numpy(float)
        return float(np.average(series, weights=weights))

    retrieval = point.get("retrieval_level", pd.Series("", index=point.index)).astype(str)
    row.update(
        {
            "count": int(len(point)),
            "strict_count": int(point.get("strict_point_candidate", pd.Series(True, index=point.index)).fillna(False).sum())
            if "strict_point_candidate" in point.columns
            else int(retrieval.isin(["L0", "L1", "L2"]).sum()),
            "fallback_count": int(point.get("fallback_point_candidate", pd.Series(False, index=point.index)).fillna(False).sum()),
            "l0_count": int(retrieval.eq("L0").sum()),
            "l1_count": int(retrieval.eq("L1").sum()),
            "l2_count": int(retrieval.eq("L2").sum()),
            "city_match_mean": mean_flag("city_match"),
            "color_match_mean": mean_flag("color_match"),
            "condition_match_mean": mean_flag("condition_match"),
            "observable_match_mean": mean_flag("observable_match_count"),
            "age_gap_min": min_num("age_difference"),
            "mileage_gap_min": min_num("mileage_difference"),
            "transfer_gap_min": min_num("transfer_difference"),
            "age_gap_weighted_mean": weighted_mean("age_difference"),
            "mileage_gap_weighted_mean": weighted_mean("mileage_difference"),
            "transfer_gap_weighted_mean": weighted_mean("transfer_difference"),
            "days_min": min_num("days_since_transaction"),
            "days_weighted_mean": weighted_mean("days_since_transaction"),
            "price_min": float(np.nanmin(values)),
            "price_max": float(np.nanmax(values)),
            "price_std": float(np.nanstd(values)),
            "price_weighted_mean": float(np.average(values, weights=weights)),
            "top1_price": top1,
            "baseline_p10": p10,
            "baseline_p20": p20,
            "baseline_p25": p25,
            "baseline_p30": p30,
            "baseline_p40": p40,
            "baseline_p50": p50,
            "baseline_p75": p75,
            "baseline_iqr_ratio": float((p75 - p25) / p50) if p50 else 99.0,
            "baseline_price": float(baseline_price or default_baseline),
        }
    )
    return row


def frame_from_summary_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame.get(column, "missing").fillna("missing").astype(str)
    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0)
    return frame[FEATURES]


def residual_clip_from_summary(summary: dict[str, Any]) -> float:
    count = int(summary.get("baseline_candidate_count") or summary.get("count") or 0)
    iqr = float(summary.get("baseline_iqr_ratio") or 99.0)
    if count >= 8 and iqr <= 0.12:
        return 0.08
    if count >= 5 and iqr <= 0.20:
        return 0.12
    if count >= 2:
        return 0.18
    return 0.0


class V194CandidateCalibrator:
    def __init__(self, artifact_path: Path) -> None:
        artifact = joblib.load(artifact_path)
        self.artifact_path = artifact_path
        self.model = artifact["model"]
        self.version = artifact.get("version", "v194_29_candidate_calibrator")
        self.clip_limit = float(artifact.get("max_abs_log_adjustment", 0.18))

    def adjust(
        self,
        *,
        candidates: pd.DataFrame,
        query: dict[str, Any],
        price_summary: dict[str, Any],
    ) -> dict[str, Any]:
        baseline = float(price_summary.get("statistical_baseline_price") or 0.0)
        if baseline <= 0 or candidates.empty:
            return {"enabled": False, "reason": "NO_BASELINE_OR_CANDIDATES"}
        if not str(price_summary.get("baseline_method") or "").startswith(("LISTWISE_", "WEIGHTED_")):
            return {"enabled": False, "reason": "NON_INTERNAL_C2B_BASELINE"}
        features = build_candidate_summary_features(candidates, query, baseline_price=baseline)
        feature_frame = frame_from_summary_rows([features])
        raw = float(self.model.predict(feature_frame)[0])
        allowed = min(self.clip_limit, residual_clip_from_summary({**features, **price_summary}))
        clipped = float(np.clip(raw, -allowed, allowed)) if allowed > 0 else 0.0
        adjusted = float(baseline * np.exp(clipped))
        return {
            "enabled": True,
            "version": self.version,
            "raw_log_residual_adjustment": raw,
            "allowed_log_residual_adjustment": allowed,
            "applied_log_residual_adjustment": clipped,
            "adjusted_price": adjusted,
            "feature_row": features,
        }
