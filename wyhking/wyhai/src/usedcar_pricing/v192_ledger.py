from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from .v192_pricing import weighted_quantile


def build_v192_ledger(
    query_row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    *,
    statistical_method: str,
    statistical_baseline_price: float,
    raw_model_adjustment: float,
    clipped_model_adjustment: float,
    adjustment_clip: float,
    final_price: float,
    interval_low: float,
    interval_high: float,
    expected_ape: float,
    probability_ape_le_5: float,
    predicted_p90_ape: float,
    conformal_log_radius: float,
    local_regression_trace: dict[str, Any] | None = None,
    residual_model_name: str = "",
    residual_feature_values: dict[str, Any] | None = None,
    evidence_quality: str = "",
) -> dict[str, Any]:
    quote_id = "v192_" + hashlib.sha1(
        f"{query_row['query_id']}|{query_row['query_time']}".encode("utf-8")
    ).hexdigest()[:20]
    selected = [row for row in candidate_rows if float(row.get("normalized_pricing_weight") or 0) > 0]
    rejected = [row for row in candidate_rows if float(row.get("normalized_pricing_weight") or 0) <= 0]
    raw_query = {
        key: query_row.get(key)
        for key in (
            "brand",
            "series",
            "model_year",
            "trim",
            "city",
            "color",
            "age_years",
            "mileage_wan_km",
            "transfer_count",
            "condition_risk_level",
        )
    }
    source_families = {
        str(row.get("source_family") or row.get("cluster_price_type") or "")
        for row in candidate_rows
        if row.get("source_family") or row.get("cluster_price_type")
    }
    lifecycles = {
        str(row.get("lifecycle_id") or row.get("candidate_id") or "")
        for row in candidate_rows
        if row.get("lifecycle_id") or row.get("candidate_id")
    }
    return {
        "quote_id": quote_id,
        "version": "v192",
        "prediction_time": str(query_row["query_time"]),
        "raw_query": raw_query,
        "normalized_query": {
            "brand": query_row.get("brand_key") or query_row.get("brand"),
            "series": query_row.get("series_key") or query_row.get("series"),
            "model_year": query_row.get("model_year"),
            "trim": query_row.get("trim_key") or query_row.get("trim"),
            "city": query_row.get("city_key") or query_row.get("city"),
            "color": query_row.get("color_norm") or query_row.get("color"),
            "age_years": query_row.get("age_years"),
            "mileage_wan_km": query_row.get("mileage_wan_km"),
            "transfer_count": query_row.get("transfer_count"),
            "condition_risk_level": query_row.get("condition_risk_level"),
        },
        "matched_cluster": {
            "best_retrieval_level": query_row.get("best_retrieval_level"),
            "candidate_count": query_row.get("candidate_count"),
            "exact_candidate_count": query_row.get("exact_candidate_count"),
            "source_family_count": query_row.get("source_family_count"),
            "evidence_quality": evidence_quality,
        },
        "source_accounting": {
            "raw_price_component_count": len(candidate_rows),
            "independent_source_family_count": len(source_families),
            "independent_vehicle_lifecycle_count": len(lifecycles),
            "derived_price_component_count": sum(
                str(row.get("cluster_price_type") or "").startswith("DERIVED")
                for row in candidate_rows
            ),
        },
        "retrieval": {
            "candidate_count": len(candidate_rows),
            "top100_candidates": candidate_rows,
            "selected_candidates": selected,
            "rejected_candidates": rejected,
        },
        "statistical_price": {
            "method": statistical_method,
            "baseline_price": statistical_baseline_price,
            "weight_sum": float(sum(float(row.get("normalized_pricing_weight") or 0) for row in selected)),
            "local_regression_trace": local_regression_trace,
        },
        "model_adjustment": {
            "model_name": residual_model_name,
            "target": "log(actual_price / statistical_baseline_price)",
            "feature_values": residual_feature_values or {},
            "evidence_quality": evidence_quality,
            "raw_log_adjustment": raw_model_adjustment,
            "clip_limit": adjustment_clip,
            "clipped_log_adjustment": clipped_model_adjustment,
            "clip_triggered": bool(abs(raw_model_adjustment - clipped_model_adjustment) > 1e-12),
        },
        "final_price": {
            "formula": "statistical_baseline_price * exp(clipped_log_adjustment)",
            "value": final_price,
        },
        "interval": {
            "method": "calibration_log_residual_conformal",
            "low": interval_low,
            "high": interval_high,
            "conformal_log_radius": conformal_log_radius,
            "width_reason": "calibration residual quantile conditioned by evidence quality",
        },
        "confidence": {
            "expected_ape": expected_ape,
            "probability_ape_le_5": probability_ape_le_5,
            "predicted_p90_ape": predicted_p90_ape,
        },
        "business_explanation": {
            "template": (
                "系统从历史时点前的{candidate_count}辆候选中选择{selected_count}辆，"
                "以{method}形成统计基线{baseline:.0f}元；模型在证据约束下调整{adjustment_pct:.2f}%，"
                "最终价格{final:.0f}元，校准区间{low:.0f}-{high:.0f}元。"
            ).format(
                candidate_count=len(candidate_rows),
                selected_count=len(selected),
                method=statistical_method,
                baseline=statistical_baseline_price,
                adjustment_pct=(np.exp(clipped_model_adjustment) - 1.0) * 100,
                final=final_price,
                low=interval_low,
                high=interval_high,
            ),
            "ledger_only": True,
        },
    }


def replay_v192_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    statistical = ledger["statistical_price"]
    selected = ledger["retrieval"]["selected_candidates"]
    method = statistical["method"]
    prices = np.array([float(row["adjusted_candidate_price"]) for row in selected], dtype=float)
    weights = np.array([float(row["normalized_pricing_weight"]) for row in selected], dtype=float)
    if method.startswith("weighted_median"):
        baseline = weighted_quantile(prices, weights, 0.50)
    elif method.startswith("weighted_p40"):
        baseline = weighted_quantile(prices, weights, 0.40)
    elif method.startswith("trimmed_mean"):
        order = np.sort(prices)
        start = int(np.floor(len(order) * 0.10))
        end = max(start + 1, int(np.ceil(len(order) * 0.90)))
        baseline = float(order[start:end].mean())
    elif method.startswith("local_regression"):
        trace = statistical.get("local_regression_trace") or {}
        if "constant_log_price" in trace:
            baseline = float(np.exp(float(trace["constant_log_price"])))
        else:
            features = trace.get("query_features") or {}
            coefficients = trace.get("coefficients") or {}
            prediction_log = float(trace.get("intercept") or 0.0) + sum(
                float(coefficients.get(column, 0.0)) * float(features.get(column, 0.0))
                for column in trace.get("feature_columns") or []
            )
            baseline = float(np.exp(prediction_log))
    else:
        raise ValueError(f"Unsupported statistical method: {method}")
    adjustment = float(ledger["model_adjustment"]["clipped_log_adjustment"])
    raw_adjustment = float(ledger["model_adjustment"]["raw_log_adjustment"])
    clip_limit = float(ledger["model_adjustment"]["clip_limit"])
    recomputed_clipped_adjustment = float(np.clip(raw_adjustment, -clip_limit, clip_limit))
    final = float(baseline * np.exp(adjustment))
    stored = float(ledger["final_price"]["value"])
    conformal_radius = float(ledger["interval"]["conformal_log_radius"])
    interval_low = float(final * np.exp(-conformal_radius))
    interval_high = float(final * np.exp(conformal_radius))
    steps = [
        {
            "step": "statistical_baseline_price",
            "stored_value": float(statistical["baseline_price"]),
            "recomputed_value": baseline,
            "difference": baseline - float(statistical["baseline_price"]),
            "passed": abs(baseline - float(statistical["baseline_price"])) <= 1e-6,
        },
        {
            "step": "clipped_model_adjustment",
            "stored_value": adjustment,
            "recomputed_value": recomputed_clipped_adjustment,
            "difference": recomputed_clipped_adjustment - adjustment,
            "passed": abs(recomputed_clipped_adjustment - adjustment) <= 1e-12,
        },
        {
            "step": "final_price",
            "stored_value": stored,
            "recomputed_value": final,
            "difference": final - stored,
            "passed": abs(final - stored) <= 1e-6,
        },
        {
            "step": "interval_low",
            "stored_value": float(ledger["interval"]["low"]),
            "recomputed_value": interval_low,
            "difference": interval_low - float(ledger["interval"]["low"]),
            "passed": abs(interval_low - float(ledger["interval"]["low"])) <= 1e-6,
        },
        {
            "step": "interval_high",
            "stored_value": float(ledger["interval"]["high"]),
            "recomputed_value": interval_high,
            "difference": interval_high - float(ledger["interval"]["high"]),
            "passed": abs(interval_high - float(ledger["interval"]["high"])) <= 1e-6,
        },
    ]
    lifecycle_ids = [
        str(row.get("lifecycle_id") or row.get("candidate_id") or "")
        for row in ledger["retrieval"]["top100_candidates"]
    ]
    duplicate_lifecycle_count = len(lifecycle_ids) - len(set(lifecycle_ids))
    return {
        "quote_id": ledger["quote_id"],
        "recomputed_statistical_baseline": baseline,
        "stored_statistical_baseline": statistical["baseline_price"],
        "recomputed_final_price": final,
        "stored_final_price": stored,
        "difference": final - stored,
        "passed": all(step["passed"] for step in steps),
        "future_data_violation_count": sum(
            str(row["knowledge_available_at"]) > str(ledger["prediction_time"])
            for row in ledger["retrieval"]["top100_candidates"]
        ),
        "duplicate_lifecycle_count": duplicate_lifecycle_count,
        "steps": steps,
    }


def ledger_json(ledger: dict[str, Any]) -> str:
    return json.dumps(ledger, ensure_ascii=False, default=str)
