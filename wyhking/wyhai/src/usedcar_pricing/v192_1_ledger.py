from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

from .v192_1_pricing import weighted_quantile


def quote_id(query_id: str, query_time: Any) -> str:
    digest = hashlib.sha1(f"{query_id}|{query_time}".encode("utf-8")).hexdigest()
    return f"v192_1_{digest[:20]}"


def recompute_statistical_baseline(
    method: str,
    candidates: list[dict[str, Any]],
    local_regression_trace: dict[str, Any] | None = None,
) -> float:
    prices = np.asarray(
        [float(row["adjusted_candidate_price"]) for row in candidates],
        dtype=float,
    )
    weights = np.asarray(
        [float(row["normalized_pricing_weight"]) for row in candidates],
        dtype=float,
    )
    if method.startswith("weighted_median"):
        return weighted_quantile(prices, weights, 0.50)
    if method.startswith("weighted_p25"):
        return weighted_quantile(prices, weights, 0.25)
    if method.startswith("weighted_p30"):
        return weighted_quantile(prices, weights, 0.30)
    if method.startswith("weighted_p40"):
        return weighted_quantile(prices, weights, 0.40)
    if method.startswith("trimmed_mean"):
        ordered = np.sort(prices)
        start = int(math.floor(len(ordered) * 0.10))
        end = max(start + 1, int(math.ceil(len(ordered) * 0.90)))
        return float(ordered[start:end].mean())
    if method.startswith("local_regression"):
        trace = local_regression_trace or {}
        if "constant_log_price" in trace:
            return float(np.exp(float(trace["constant_log_price"])))
        prediction_log = float(trace.get("intercept") or 0.0)
        prediction_log += sum(
            float((trace.get("coefficients") or {}).get(column, 0.0))
            * float((trace.get("query_features") or {}).get(column, 0.0))
            for column in trace.get("feature_columns") or []
        )
        return float(np.exp(prediction_log))
    raise ValueError(f"Unsupported statistical method: {method}")


def build_ledger(
    query: dict[str, Any],
    top100_candidates: list[dict[str, Any]],
    pricing_candidates: list[dict[str, Any]],
    shap_explanation: dict[str, Any],
) -> dict[str, Any]:
    method = str(query["statistical_method"])
    baseline = float(query["statistical_baseline_price"])
    clipped_adjustment = float(query["clipped_model_adjustment"])
    residual_price = float(query["base_final_price"])
    series_factor = float(np.exp(float(query.get("series_calibration_log_factor") or 0.0)))
    series_price = float(query.get("series_calibrated_price") or residual_price)
    final_price = float(query["final_price"])
    interval_low = float(query["interval_low"])
    interval_high = float(query["interval_high"])
    source_families = {
        str(row.get("source_family") or row.get("cluster_price_type") or "")
        for row in top100_candidates
        if row.get("source_family") or row.get("cluster_price_type")
    }
    lifecycles = {
        str(row.get("lifecycle_id") or row.get("candidate_id") or "")
        for row in top100_candidates
        if row.get("lifecycle_id") or row.get("candidate_id")
    }
    return {
        "quote_id": quote_id(str(query["query_id"]), query["query_time"]),
        "version": "v192_1",
        "prediction_time": str(query["query_time"]),
        "raw_query": {
            key: query.get(key)
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
        },
        "normalized_query": {
            key: query.get(key)
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
        },
        "matched_cluster": {
            "best_retrieval_level": query.get("best_retrieval_level"),
            "candidate_count": query.get("candidate_count"),
            "pricing_candidate_count": query.get("pricing_candidate_count"),
            "exact_candidate_count": query.get("exact_candidate_count"),
            "evidence_quality": query.get("evidence_quality"),
        },
        "source_accounting": {
            "raw_price_component_count": len(top100_candidates),
            "independent_source_family_count": len(source_families),
            "independent_vehicle_lifecycle_count": len(lifecycles),
        },
        "retrieval": {
            "top100_candidates": top100_candidates,
            "pricing_candidates": pricing_candidates,
        },
        "statistical_price": {
            "method": method,
            "stored_value": baseline,
            "local_regression_trace": query.get("local_regression_trace"),
        },
        "residual_model": {
            "raw_log_adjustment": float(query["raw_model_adjustment"]),
            "clipped_log_adjustment": clipped_adjustment,
            "stored_residual_price": residual_price,
            "shap": shap_explanation,
        },
        "series_calibration": {
            "log_factor": float(query.get("series_calibration_log_factor") or 0.0),
            "factor": series_factor,
            "stored_value": series_price,
            "applied": int(query.get("series_calibration_applied") or 0),
        },
        "low_price_specialist": {
            "applied": int(query.get("low_price_specialist_applied") or 0),
            "variant": str(query.get("low_price_specialist_variant") or ""),
            "stored_value": final_price,
        },
        "final_price": {
            "stored_value": final_price,
        },
        "interval": {
            "method": str(query["interval_method"]),
            "stored_low": interval_low,
            "stored_high": interval_high,
            "low_multiplier": interval_low / final_price,
            "high_multiplier": interval_high / final_price,
        },
        "confidence": {
            "bucket": query.get("confidence_bucket"),
            "expected_ape": query.get("expected_ape"),
            "probability_ape_le_5": query.get("probability_ape_le_5"),
            "predicted_p90_ape": query.get("predicted_p90_ape"),
            "auto_quote_flag": query.get("auto_quote_flag"),
        },
    }


def replay_arithmetic(ledger: dict[str, Any], tolerance: float = 1e-6) -> dict[str, Any]:
    statistical = ledger["statistical_price"]
    baseline = recompute_statistical_baseline(
        statistical["method"],
        ledger["retrieval"]["pricing_candidates"],
        statistical.get("local_regression_trace"),
    )
    clipped = float(ledger["residual_model"]["clipped_log_adjustment"])
    residual_price = baseline * np.exp(clipped)
    series_price = residual_price * float(ledger["series_calibration"]["factor"])
    if int(ledger["low_price_specialist"]["applied"]) == 1:
        final_price = float(ledger["low_price_specialist"]["stored_value"])
    else:
        final_price = series_price
    interval_low = final_price * float(ledger["interval"]["low_multiplier"])
    interval_high = final_price * float(ledger["interval"]["high_multiplier"])
    stored = {
        "statistical_baseline": float(statistical["stored_value"]),
        "residual_price": float(ledger["residual_model"]["stored_residual_price"]),
        "series_price": float(ledger["series_calibration"]["stored_value"]),
        "final_price": float(ledger["final_price"]["stored_value"]),
        "interval_low": float(ledger["interval"]["stored_low"]),
        "interval_high": float(ledger["interval"]["stored_high"]),
    }
    recomputed = {
        "statistical_baseline": float(baseline),
        "residual_price": float(residual_price),
        "series_price": float(series_price),
        "final_price": float(final_price),
        "interval_low": float(interval_low),
        "interval_high": float(interval_high),
    }
    steps = []
    for step, stored_value in stored.items():
        recomputed_value = recomputed[step]
        difference = recomputed_value - stored_value
        steps.append(
            {
                "step": step,
                "stored_value": stored_value,
                "recomputed_value": recomputed_value,
                "difference": difference,
                "passed": abs(difference) <= tolerance,
            }
        )
    return {
        "quote_id": ledger["quote_id"],
        "arithmetic_reconciliation_passed": all(
            row["passed"] for row in steps
        ),
        "steps": steps,
    }


def ledger_json(ledger: dict[str, Any]) -> str:
    return json.dumps(ledger, ensure_ascii=False, default=str)
