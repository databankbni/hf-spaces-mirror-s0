#!/usr/bin/env python3
"""Build complete deterministic ledgers from current pricing artifacts."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .price_explanation_schema import PriceExplanationLedger
from .price_reason_codes import ReasonCode
from .render_business_explanation import render_and_attach


MODEL_VERSION = "v191_explainable_market_price"
POLICY_VERSION = "v191_market_price_policy"

LEVEL_WEIGHT = {
    "L0_exact_city_color_six_factor": 1.00,
    "L1_exact_national_color_six_factor": 0.94,
    "L2_exact_national_six_factor": 0.88,
    "L3_trim_year_condition": 0.74,
    "L4_series_year_six_factor": 0.62,
    "L5_series_year_condition": 0.48,
    "L6_series_condition": 0.35,
    "L0_exact_source_cluster": 1.00,
}

NEW_ENERGY_TERMS = ("ev", "bev", "phev", "dm-i", "dmi", "增程", "纯电", "插混", "电动", "新能源")


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _time(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.isoformat()


def _hash_quote(*values: Any) -> str:
    raw = "|".join(str(value) for value in values)
    return "quote_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return np.nan
    values = values[valid]
    weights = weights[valid]
    order = np.argsort(values, kind="stable")
    values = values[order]
    weights = weights[order]
    cdf = np.cumsum(weights)
    return float(values[np.searchsorted(cdf, quantile * cdf[-1], side="left")])


def route_scenario(target: dict[str, Any], baseline_price: float | None, evidence_count: int) -> dict[str, Any]:
    age = _float(target.get("age_years"))
    condition = str(target.get("condition_risk_level") or target.get("condition") or "unknown").lower()
    text = " ".join(str(target.get(key) or "") for key in ("brand", "series", "trim", "powertrain_type")).lower()
    details: list[dict[str, Any]] = []

    if condition == "major_risk":
        return {
            "route_code": "MAJOR_ACCIDENT",
            "route_name": "重大车况风险",
            "reason_codes": [ReasonCode.ROUTE_MAJOR_ACCIDENT.value, ReasonCode.MANUAL_REVIEW_MAJOR_RISK.value],
            "reason_details": [{"field": "condition_risk_level", "actual_value": condition, "threshold": "major_risk"}],
        }
    if evidence_count <= 0:
        return {
            "route_code": "MANUAL_REVIEW",
            "route_name": "人工复核",
            "reason_codes": [ReasonCode.ROUTE_MANUAL_REVIEW.value, ReasonCode.MANUAL_REVIEW_NO_COMPARABLE.value],
            "reason_details": [{"field": "retrieved_candidate_count", "actual_value": evidence_count, "threshold": 1}],
        }
    if age is not None and age <= 2:
        details.append({"field": "age_years", "actual_value": age, "operator": "<=", "threshold": 2.0})
        return {
            "route_code": "NEAR_NEW_CAR",
            "route_name": "准新车",
            "reason_codes": [ReasonCode.ROUTE_NEAR_NEW_CAR.value],
            "reason_details": details,
        }
    if age is not None and age >= 10 and baseline_price is not None and baseline_price < 50_000:
        details.extend(
            [
                {"field": "age_years", "actual_value": age, "operator": ">=", "threshold": 10.0},
                {"field": "baseline_price", "actual_value": baseline_price, "operator": "<", "threshold": 50_000},
            ]
        )
        return {
            "route_code": "LOW_PRICE_OLD_CAR",
            "route_name": "低价老车",
            "reason_codes": [ReasonCode.ROUTE_LOW_PRICE_OLD_CAR.value],
            "reason_details": details,
        }
    if any(term in text for term in NEW_ENERGY_TERMS):
        return {
            "route_code": "NEW_ENERGY",
            "route_name": "新能源车",
            "reason_codes": [ReasonCode.ROUTE_NEW_ENERGY.value],
            "reason_details": [{"field": "vehicle_identity_text", "actual_value": text, "threshold": list(NEW_ENERGY_TERMS)}],
        }
    if evidence_count < 3:
        return {
            "route_code": "COLD_MODEL",
            "route_name": "冷门车型",
            "reason_codes": [ReasonCode.ROUTE_COLD_MODEL.value],
            "reason_details": [{"field": "retrieved_candidate_count", "actual_value": evidence_count, "operator": "<", "threshold": 3}],
        }
    return {
        "route_code": "REGULAR_MAINSTREAM",
        "route_name": "常规主流车",
        "reason_codes": [ReasonCode.ROUTE_REGULAR_MAINSTREAM.value],
        "reason_details": [{"field": "special_route_trigger_count", "actual_value": 0, "threshold": 0}],
    }


def candidate_reason_codes(candidate: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if int(candidate.get("same_trim") or 0):
        codes.append(ReasonCode.RETRIEVAL_EXACT_SAME_TRIM.value)
    if int(candidate.get("same_year") or 0):
        codes.append(ReasonCode.RETRIEVAL_SAME_MODEL_YEAR.value)
    if int(candidate.get("same_city") or 0):
        codes.append(ReasonCode.RETRIEVAL_SAME_CITY.value)
    if int(candidate.get("same_color") or 0):
        codes.append(ReasonCode.RETRIEVAL_SAME_COLOR.value)
    if int(candidate.get("same_condition") or 0):
        codes.append(ReasonCode.RETRIEVAL_SAME_CONDITION.value)
    if (_float(candidate.get("mileage_gap"), 99) or 99) <= 1:
        codes.append(ReasonCode.RETRIEVAL_MILEAGE_WITHIN_10000_KM.value)
    if (_float(candidate.get("age_gap"), 99) or 99) <= 0.5:
        codes.append(ReasonCode.RETRIEVAL_AGE_WITHIN_0_5_YEAR.value)
    if (_float(candidate.get("days_gap"), 9999) or 9999) <= 180:
        codes.append(ReasonCode.RETRIEVAL_RECENT_TRANSACTION.value)
    level = str(candidate.get("match_level") or "")
    if "national" in level:
        codes.append(ReasonCode.RETRIEVAL_NATIONAL_SAME_TRIM_FALLBACK.value)
    return codes


def _candidate_record(row: pd.Series | dict[str, Any], prediction_time: Any) -> dict[str, Any]:
    value = dict(row)
    candidate_time = value.get("candidate_time") or value.get("event_time")
    prediction = pd.to_datetime(prediction_time, errors="coerce")
    available = pd.to_datetime(value.get("knowledge_available_at") or candidate_time, errors="coerce")
    future = bool(pd.notna(prediction) and pd.notna(available) and available > prediction)
    record = {
        "candidate_id": str(value.get("candidate_observation_id") or value.get("observation_id") or ""),
        "source_family": str(value.get("source_family") or "internal_history"),
        "source_platform": str(value.get("source_platform") or value.get("source_file") or "internal"),
        "transaction_time": _time(candidate_time),
        "knowledge_available_at": _time(available),
        "price": _float(value.get("candidate_price") if "candidate_price" in value else value.get("price")),
        "retrieval_level": str(value.get("match_level") or "L0_exact_source_cluster"),
        "same_brand": int(value.get("same_brand", 1)),
        "same_series": int(value.get("same_series", 1)),
        "same_model_year": int(value.get("same_year", 1)),
        "same_trim": int(value.get("same_trim", 1)),
        "same_energy_type": value.get("same_energy_type"),
        "same_city": int(value.get("same_city", 0)),
        "same_color": int(value.get("same_color", 0)),
        "same_condition": int(value.get("same_condition", 0)),
        "age_difference": _float(value.get("age_gap"), 0),
        "mileage_difference": _float(value.get("mileage_gap"), 0),
        "transfer_difference": _float(value.get("transfer_gap"), 0),
        "days_since_transaction": _float(value.get("days_gap")),
        "data_quality_flags": (
            [ReasonCode.DATA_QUALITY_FUTURE_EVIDENCE_BLOCKED.value]
            if future
            else [ReasonCode.DATA_QUALITY_MARKET_CLEAN.value]
        ),
        "retrieval_reason_codes": [],
        "ranker_score": _float(value.get("knowledge_quality_score")),
        "candidate_rank": int(value.get("candidate_rank") or 0),
        "brand": value.get("candidate_brand") or value.get("brand"),
        "series": value.get("candidate_series") or value.get("series"),
        "model_year": value.get("candidate_model_year") or value.get("model_year"),
        "trim": value.get("candidate_trim") or value.get("trim"),
        "city": value.get("candidate_city") or value.get("city"),
        "age_years": _float(value.get("candidate_age_years") if "candidate_age_years" in value else value.get("age_years")),
        "mileage_wan_km": _float(value.get("candidate_mileage_wan_km") if "candidate_mileage_wan_km" in value else value.get("mileage_wan_km")),
        "transfer_count": _float(value.get("candidate_transfer_count") if "candidate_transfer_count" in value else value.get("transfer_count")),
        "condition": value.get("candidate_condition") or value.get("condition_risk_level"),
    }
    record["retrieval_reason_codes"] = candidate_reason_codes(
        {
            **value,
            "days_gap": record["days_since_transaction"],
            "age_gap": record["age_difference"],
            "mileage_gap": record["mileage_difference"],
        }
    )
    return record


def _confidence(
    level: str,
    candidate_count: int,
    dispersion: float | None,
    latest_days: float | None,
    condition: str,
) -> dict[str, Any]:
    dispersion_value = dispersion if dispersion is not None else 9.0
    latest_value = latest_days if latest_days is not None else 9999.0
    exact_level = level.startswith(("L0_", "L1_", "L2_"))
    medium_level = level.startswith(("L0_", "L1_", "L2_", "L3_", "L4_"))
    details = [
        {"field": "retrieved_candidate_count", "actual_value": candidate_count, "message": f"召回候选{candidate_count}辆"},
        {"field": "price_dispersion", "actual_value": dispersion, "message": f"价格离散度{dispersion_value * 100:.1f}%"},
        {"field": "latest_evidence_days", "actual_value": latest_days, "message": f"最新证据距今{int(round(latest_value))}天"},
        {"field": "retrieval_level", "actual_value": level, "message": f"最高召回层级为{level}"},
    ]
    if candidate_count == 0:
        bucket = "Manual"
        codes = [ReasonCode.CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE.value]
    elif exact_level and candidate_count >= 5 and dispersion_value <= 0.12 and latest_value <= 90 and condition == "clean":
        bucket = "High"
        codes = [ReasonCode.CONFIDENCE_HIGH_EXACT_STABLE_RECENT.value]
    elif medium_level and candidate_count >= 3 and dispersion_value <= 0.25 and latest_value <= 365:
        bucket = "Medium"
        codes = [ReasonCode.CONFIDENCE_MEDIUM_LIMITED_EXACT_EVIDENCE.value]
    else:
        bucket = "Low"
        codes = [ReasonCode.CONFIDENCE_LOW_WEAK_OR_WIDE_EVIDENCE.value]
    codes.append(ReasonCode.CONFIDENCE_RISK_MODEL_NOT_AVAILABLE.value)
    return {
        "confidence_bucket": bucket,
        "expected_ape": None,
        "probability_ape_le_5": None,
        "predicted_p90_ape": None,
        "confidence_thresholds": {
            "high": "exact level, candidates>=5, dispersion<=0.12, latest<=90d, clean condition",
            "medium": "L0-L4, candidates>=3, dispersion<=0.25, latest<=365d",
        },
        "reason_codes": codes,
        "reason_details": details,
    }


def build_v187_asof_ledger(query: pd.Series | dict[str, Any], candidate_rows: pd.DataFrame) -> PriceExplanationLedger:
    query_dict = dict(query)
    prediction_time = query_dict.get("query_time")
    actual = _float(query_dict.get("actual"))
    serving_price = _float(query_dict.get("v187_rank1_price"))
    total_recalled = int(query_dict.get("candidate_count_recalled") or len(candidate_rows))
    records = [_candidate_record(row, prediction_time) for _, row in candidate_rows.sort_values("candidate_rank").iterrows()]
    legal = [record for record in records if ReasonCode.DATA_QUALITY_FUTURE_EVIDENCE_BLOCKED.value not in record["data_quality_flags"]]

    prices = np.array([record["price"] for record in legal if record["price"] is not None], dtype=float)
    scores = np.array([record["ranker_score"] if record["ranker_score"] is not None else -999 for record in legal], dtype=float)
    if len(prices):
        weights = np.exp((scores - np.nanmax(scores)) / 12.0)
        p25 = weighted_quantile(prices[: min(5, len(prices))], weights[: min(5, len(weights))], 0.25)
        p75 = weighted_quantile(prices[: min(5, len(prices))], weights[: min(5, len(weights))], 0.75)
        dispersion = float((np.nanpercentile(prices, 75) - np.nanpercentile(prices, 25)) / max(np.nanmedian(prices), 1))
    else:
        p25 = p75 = dispersion = np.nan

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if legal and serving_price is not None:
        winner = legal[0].copy()
        winner.update(
            {
                "rank_position": 1,
                "accepted_reason_codes": [ReasonCode.COMPARABLE_ACCEPT_HIGHEST_QUALITY.value],
                "raw_weight_components": {
                    "ranker_weight": 1.0,
                    "time_decay_weight": 1.0,
                    "source_quality_weight": 1.0,
                    "retrieval_level_weight": 1.0,
                    "distance_weight": 1.0,
                    "outlier_weight": 1.0,
                },
                "raw_weight": 1.0,
                "normalized_final_weight": 1.0,
                "price_used": winner["price"],
                "adjusted_candidate_price": winner["price"],
            }
        )
        selected.append(winner)
        for record in legal[1:]:
            rejected.append(
                {
                    **record,
                    "rejection_reason_codes": [ReasonCode.COMPARABLE_REJECT_LOW_RANKER_SCORE.value],
                    "normalized_final_weight": 0.0,
                }
            )
    else:
        rejected = [{**record, "rejection_reason_codes": [ReasonCode.COMPARABLE_REJECT_LOW_RANKER_SCORE.value], "normalized_final_weight": 0.0} for record in legal]

    level_counts = Counter(record["retrieval_level"] for record in legal)
    source_counts = Counter(record["source_family"] for record in legal)
    latest_days = min((record["days_since_transaction"] for record in legal if record["days_since_transaction"] is not None), default=None)
    target = {
        "query_uid": query_dict.get("query_observation_id"),
        "brand": query_dict.get("brand"),
        "series": query_dict.get("series"),
        "model_year": query_dict.get("model_year"),
        "trim": query_dict.get("trim"),
        "city": query_dict.get("city"),
        "age_years": _float(query_dict.get("age_years")),
        "mileage_wan_km": _float(query_dict.get("mileage_wan_km")),
        "transfer_count": _float(query_dict.get("transfer_count")),
        "condition_risk_level": query_dict.get("condition") or "unknown",
        "actual_for_offline_audit_only": actual,
    }
    level = str(query_dict.get("rank1_match_level") or (legal[0]["retrieval_level"] if legal else "no_candidate"))
    confidence = _confidence(level, len(legal), None if np.isnan(dispersion) else dispersion, latest_days, str(target["condition_risk_level"]))
    route = route_scenario(target, serving_price, len(legal))
    if serving_price is None:
        interval_low = interval_high = None
    else:
        interval_low = float(p25) if np.isfinite(p25) else serving_price * 0.8
        interval_high = float(p75) if np.isfinite(p75) else serving_price * 1.2
        interval_low = min(interval_low, serving_price)
        interval_high = max(interval_high, serving_price)
    interval_codes = []
    if len(legal) < 5:
        interval_codes.append(ReasonCode.INTERVAL_WIDE_FEW_COMPARABLES.value)
    if np.isfinite(dispersion) and dispersion > 0.20:
        interval_codes.append(ReasonCode.INTERVAL_WIDE_HIGH_PRICE_DISPERSION.value)
    if latest_days is not None and latest_days > 180:
        interval_codes.append(ReasonCode.INTERVAL_WIDE_STALE_EVIDENCE.value)
    if str(target["condition_risk_level"]) == "unknown":
        interval_codes.append(ReasonCode.INTERVAL_WIDE_UNKNOWN_CONDITION.value)
    if np.isfinite(dispersion) and dispersion <= 0.12:
        interval_codes.append(ReasonCode.INTERVAL_NARROW_LOW_PRICE_DISPERSION.value)
    if not interval_codes:
        interval_codes.append(ReasonCode.INTERVAL_NARROW_RECENT_EVIDENCE.value)

    quote_id = _hash_quote(query_dict.get("query_observation_id"), prediction_time, "v187")
    ledger = PriceExplanationLedger(
        quote_id=quote_id,
        model_version="v187_knowledge_serving_rank_fix",
        policy_version="v187_candidate_quality_policy",
        as_of_time=_time(prediction_time),
        prediction_time=_time(prediction_time),
        target_vehicle=target,
        scenario_route=route,
        retrieval_summary={
            "total_retrieved_count": total_recalled,
            "candidate_trace_count": len(records),
            "retrieval_level_distribution": dict(level_counts),
            "source_family_distribution": dict(source_counts),
            "latest_evidence_days": latest_days,
            "candidate_trace_truncated": total_recalled > len(records),
        },
        retrieved_candidates=records,
        selected_comparables=selected,
        rejected_candidates=rejected,
        statistical_price={
            "calculation_method": "HIGHEST_QUALITY_CANDIDATE_WINNER_TAKES_ALL",
            "raw_candidate_prices": [record["price"] for record in legal],
            "outliers_removed": [],
            "candidate_weight_sum": 1.0 if selected else 0.0,
            "baseline_price": serving_price,
            "price_dispersion": None if np.isnan(dispersion) else dispersion,
            "calculation_trace": {
                "sort_field": "knowledge_quality_score",
                "sort_direction": "descending",
                "winner_candidate_id": selected[0]["candidate_id"] if selected else None,
                "winner_score": selected[0]["ranker_score"] if selected else None,
                "top5_weighted_p25": None if not np.isfinite(p25) else p25,
                "top5_weighted_p75": None if not np.isfinite(p75) else p75,
                "reason_code": ReasonCode.BASELINE_WINNER_TAKES_ALL.value,
            },
        },
        model_adjustment={
            "model_name": "NO_RESIDUAL_MODEL",
            "model_raw_output": 0.0,
            "raw_adjustment_ratio": 0.0,
            "raw_adjustment_amount": 0.0,
            "clip_lower": None,
            "clip_upper": None,
            "clip_applied": False,
            "final_adjustment_ratio": 0.0,
            "final_adjustment_amount": 0.0,
            "feature_contributions": [],
            "reason_codes": [ReasonCode.MODEL_ADJUSTMENT_NO_RESIDUAL_MODEL.value],
            "shap_reconciliation_applicable": False,
            "shap_reconciliation_passed": True,
        },
        final_price={
            "statistical_baseline_price": serving_price,
            "model_adjustment_amount": 0.0,
            "final_point_price": serving_price,
        },
        interval={
            "price_low": interval_low,
            "price_high": interval_high,
            "interval_width_ratio": (
                None
                if serving_price in (None, 0) or interval_low is None or interval_high is None
                else (interval_high - interval_low) / serving_price
            ),
            "calibration_method": "TOP5_SCORE_WEIGHTED_P25_P75",
            "driver_codes": interval_codes,
            "driver_details": [
                {"field": "candidate_count", "value": len(legal)},
                {"field": "price_dispersion", "value": None if np.isnan(dispersion) else dispersion},
                {"field": "latest_evidence_days", "value": latest_days},
                {"field": "retrieval_level", "value": level},
            ],
        },
        confidence=confidence,
        reconciliation={
            "recomputed_statistical_baseline_price": serving_price,
            "recomputed_model_adjustment_amount": 0.0,
            "recomputed_final_price": serving_price,
            "serving_final_price": serving_price,
            "difference_from_serving_price": 0.0 if serving_price is not None else None,
            "reconciliation_passed": serving_price is not None,
        },
        audit_metadata={
            "actual_used_for_explanation": False,
            "actual_available_for_offline_review": actual,
            "ape_for_offline_review": (
                None if actual in (None, 0) or serving_price is None else abs(serving_price - actual) / actual
            ),
            "candidate_trace_source": "v187_knowledge_serving_top20_past365.parquet",
        },
    )
    return render_and_attach(ledger)


def _source_weight(count: Any, latest_days: Any, dispersion: Any, source_factor: float) -> float:
    count_value = max(0.0, _float(count, 0.0) or 0.0)
    latest_value = max(0.0, _float(latest_days, 9999.0) or 9999.0)
    dispersion_value = min(0.70, max(0.0, _float(dispersion, 0.60) or 0.60))
    evidence = min(math.log1p(count_value), math.log(21)) / math.log(21)
    recency = math.exp(-latest_value / 180.0)
    stability = min(1.0, max(0.15, 1.0 - dispersion_value))
    return evidence * recency * stability * source_factor


def _robust_log_component_trace(values: list[float | None], weights: list[float]) -> dict[str, Any]:
    valid = [(float(value), float(weight)) for value, weight in zip(values, weights) if value and value > 0 and weight > 0]
    if not valid:
        return {"components": [], "result": None}
    logs = np.array([math.log(value) for value, _ in valid])
    median_log = float(np.median(logs))
    components = []
    denominator = sum(weight for _, weight in valid)
    for value, weight in valid:
        raw_log = math.log(value)
        clipped_log = min(median_log + 0.20, max(median_log - 0.20, raw_log))
        components.append(
            {
                "raw_price": value,
                "raw_log_price": raw_log,
                "clipped_log_price": clipped_log,
                "raw_weight": weight,
                "normalized_weight": weight / denominator,
            }
        )
    result = math.exp(sum(row["clipped_log_price"] * row["raw_weight"] for row in components) / denominator)
    return {"components": components, "median_log": median_log, "weight_sum": denominator, "result": result}


def build_v191_current_ledger(
    quote: pd.Series | dict[str, Any],
    observations: pd.DataFrame,
    *,
    max_candidate_trace: int | None = None,
) -> PriceExplanationLedger:
    """Explain an existing v191 quote without changing any price field."""

    row = dict(quote)
    prediction_time = pd.to_datetime(row.get("as_of_date"), errors="coerce")
    keys = [
        "brand_key",
        "series_key",
        "model_year",
        "trim_key",
        "color_norm",
        "city_key",
        "age_fine_bin",
        "mileage_fine_bin",
        "transfer_fine_bin",
        "condition_risk_level",
    ]
    candidates = observations.copy()
    for key in keys:
        if key == "model_year":
            candidates = candidates[pd.to_numeric(candidates[key], errors="coerce").eq(_float(row.get(key)))]
        else:
            candidates = candidates[candidates[key].fillna("").astype(str).eq(str(row.get(key) or ""))]
    candidates["knowledge_available_at"] = pd.to_datetime(candidates["knowledge_available_at"], errors="coerce").fillna(
        pd.to_datetime(candidates["event_time"], errors="coerce")
    )
    legal = candidates[
        candidates["market_clean_flag"].eq(1)
        & candidates["knowledge_available_at"].le(prediction_time)
    ].sort_values(["cluster_price_type", "event_time"], ascending=[True, False])
    trace_truncated = max_candidate_trace is not None and len(legal) > max_candidate_trace
    traced = legal.head(max_candidate_trace) if max_candidate_trace is not None else legal

    retrieved = []
    for _, candidate in traced.iterrows():
        candidate_time = pd.to_datetime(candidate.get("event_time"), errors="coerce")
        days = None if pd.isna(candidate_time) or pd.isna(prediction_time) else (prediction_time - candidate_time).total_seconds() / 86400
        retrieved.append(
            {
                "candidate_id": str(candidate.get("observation_id") or ""),
                "source_family": str(candidate.get("cluster_price_type") or ""),
                "source_platform": str(candidate.get("source_type") or candidate.get("source_file") or ""),
                "transaction_time": _time(candidate_time),
                "knowledge_available_at": _time(candidate.get("knowledge_available_at")),
                "price": _float(candidate.get("price")),
                "retrieval_level": "L0_exact_source_cluster",
                "same_brand": 1,
                "same_series": 1,
                "same_model_year": 1,
                "same_trim": 1,
                "same_energy_type": None,
                "same_city": 1,
                "same_color": 1,
                "same_condition": 1,
                "age_difference": None,
                "mileage_difference": None,
                "transfer_difference": None,
                "days_since_transaction": days,
                "data_quality_flags": [ReasonCode.DATA_QUALITY_MARKET_CLEAN.value],
                "retrieval_reason_codes": [
                    ReasonCode.RETRIEVAL_EXACT_SAME_TRIM.value,
                    ReasonCode.RETRIEVAL_SAME_MODEL_YEAR.value,
                    ReasonCode.RETRIEVAL_SAME_CITY.value,
                    ReasonCode.RETRIEVAL_SAME_COLOR.value,
                    ReasonCode.RETRIEVAL_SAME_CONDITION.value,
                ]
                + ([ReasonCode.RETRIEVAL_RECENT_TRANSACTION.value] if days is not None and days <= 180 else []),
                "selection_status": "AGGREGATED_IN_SOURCE_PRICE_CLOUD",
            }
        )

    purchase_ratio = min(1.02, max(0.60, _float(row.get("purchase_to_sold_ratio_used"), 0.92) or 0.92))
    c2b_trend = min(1.10, max(0.90, _float(row.get("c2b_recent90_to_all_ratio"), 1.0) or 1.0))
    direct_c2b = (_float(row.get("c2b_main_cluster_center")) or 0) * c2b_trend or None
    bridge_c2b = (_float(row.get("fair_retail_transaction_price")) or 0) * purchase_ratio or None
    direct_weight = _source_weight(
        row.get("c2b_evidence_count"),
        row.get("c2b_latest_days_ago"),
        row.get("c2b_iqr_dispersion"),
        1.0,
    )
    bridge_count = _float(row.get("purchase_bridge_purchase_to_sold_count"), 0.0) or 0.0
    bridge_weight = min(math.log1p(bridge_count), math.log(101)) / math.log(101) * 0.85
    named_inputs = [
        ("INTERNAL_C2B_PRICE_CLOUD", direct_c2b, direct_weight),
        ("PURCHASE_TO_SOLD_BRIDGE", bridge_c2b, bridge_weight),
    ]
    valid_named_inputs = [(name, value, weight) for name, value, weight in named_inputs if value and value > 0 and weight > 0]
    c2b_trace = _robust_log_component_trace(
        [value for _, value, _ in valid_named_inputs],
        [weight for _, _, weight in valid_named_inputs],
    )

    source_components = []
    for index, component in enumerate(c2b_trace.get("components") or []):
        component_name = valid_named_inputs[index][0]
        source_components.append(
            {
                "candidate_id": "aggregate_" + component_name.lower(),
                "candidate_type": "AGGREGATE_SOURCE_COMPONENT",
                "rank_position": index + 1,
                "ranker_score": None,
                "accepted_reason_codes": [
                    ReasonCode.COMPARABLE_ACCEPT_SOURCE_COMPONENT.value,
                    (
                        ReasonCode.BASELINE_PURCHASE_TO_SOLD_BRIDGE.value
                        if component_name == "PURCHASE_TO_SOLD_BRIDGE"
                        else ReasonCode.COMPARABLE_ACCEPT_EXACT_CLUSTER.value
                    ),
                ],
                "raw_weight_components": {
                    "ranker_weight": 1.0,
                    "time_decay_weight": 1.0,
                    "source_quality_weight": component["raw_weight"],
                    "retrieval_level_weight": 1.0,
                    "distance_weight": 1.0,
                    "outlier_weight": 1.0,
                },
                "raw_weight": component["raw_weight"],
                "normalized_final_weight": component["normalized_weight"],
                "price_used": component["raw_price"],
                "adjusted_candidate_price": math.exp(component["clipped_log_price"]),
                "source_component_name": component_name,
            }
        )

    baseline = _float(row.get("provisional_purchase_reference_before_costs"))
    c2b_reference = _float(row.get("c2b_market_reference_price"))
    ceiling = _float(row.get("zero_cost_purchase_ceiling"))
    lower = _float(row.get("provisional_purchase_range_low"))
    upper = _float(row.get("provisional_purchase_range_high"))
    total_evidence = int(round(_float(row.get("total_market_evidence_count"), len(legal)) or len(legal)))
    latest_days = min(
        [
            value
            for value in [
                _float(row.get("b2c_latest_days_ago")),
                _float(row.get("c2b_latest_days_ago")),
                _float(row.get("ext_latest_days_ago")),
                _float(row.get("internal_listing_latest_days")),
            ]
            if value is not None
        ],
        default=None,
    )
    target = {key: row.get(key) for key in keys}
    target.update(
        {
            "brand": row.get("brand_key"),
            "series": row.get("series_key"),
            "trim": row.get("trim_key"),
            "condition": row.get("condition_risk_level"),
            "age_years": _float(legal["age_years"].median()) if len(legal) and "age_years" in legal else None,
            "mileage_wan_km": _float(legal["mileage_wan_km"].median()) if len(legal) and "mileage_wan_km" in legal else None,
            "transfer_count": _float(legal["transfer_count"].median()) if len(legal) and "transfer_count" in legal else None,
        }
    )
    route = route_scenario(target, baseline, total_evidence)
    confidence_bucket = str(row.get("confidence_bucket") or "manual").capitalize()
    confidence_codes = {
        "High": ReasonCode.CONFIDENCE_HIGH_EXACT_STABLE_RECENT.value,
        "Medium": ReasonCode.CONFIDENCE_MEDIUM_LIMITED_EXACT_EVIDENCE.value,
        "Low": ReasonCode.CONFIDENCE_LOW_WEAK_OR_WIDE_EVIDENCE.value,
        "Manual": ReasonCode.CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE.value,
    }
    confidence = {
        "confidence_bucket": confidence_bucket,
        "expected_ape": None,
        "probability_ape_le_5": None,
        "predicted_p90_ape": None,
        "confidence_thresholds": {
            "high": "evidence>=12, sources>=2, disagreement<=12%, narrow interval",
            "medium": "evidence>=6 with usable source agreement",
        },
        "reason_codes": [
            confidence_codes.get(confidence_bucket, ReasonCode.CONFIDENCE_MANUAL_NO_RELIABLE_EVIDENCE.value),
            ReasonCode.CONFIDENCE_RISK_MODEL_NOT_AVAILABLE.value,
        ],
        "reason_details": [
            {"field": "total_market_evidence_count", "actual_value": total_evidence, "message": f"综合市场证据{total_evidence}条"},
            {"field": "retail_source_count", "actual_value": row.get("retail_source_count"), "message": f"独立零售来源{int(row.get('retail_source_count') or 0)}个"},
            {"field": "retail_source_disagreement_ratio", "actual_value": row.get("retail_source_disagreement_ratio"), "message": f"来源分歧{(_float(row.get('retail_source_disagreement_ratio'), 0) or 0) * 100:.1f}%"},
            {"field": "latest_evidence_days", "actual_value": latest_days, "message": f"最新证据距今{int(round(latest_days or 0))}天"},
        ],
    }
    interval_codes = []
    if int(row.get("b2c_parent_borrowed_flag") or 0) or int(row.get("c2b_parent_borrowed_flag") or 0):
        interval_codes.append(ReasonCode.INTERVAL_WIDE_PARENT_LEVEL_EVIDENCE.value)
    if str(row.get("condition_risk_level")) == "unknown":
        interval_codes.append(ReasonCode.INTERVAL_WIDE_UNKNOWN_CONDITION.value)
    if latest_days is not None and latest_days > 180:
        interval_codes.append(ReasonCode.INTERVAL_WIDE_STALE_EVIDENCE.value)
    dispersion = _float(row.get("c2b_iqr_dispersion"))
    if dispersion is not None and dispersion > 0.20:
        interval_codes.append(ReasonCode.INTERVAL_WIDE_HIGH_PRICE_DISPERSION.value)
    elif dispersion is not None and dispersion <= 0.12:
        interval_codes.append(ReasonCode.INTERVAL_NARROW_LOW_PRICE_DISPERSION.value)
    if total_evidence >= 12:
        interval_codes.append(ReasonCode.INTERVAL_NARROW_MANY_EXACT_COMPARABLES.value)

    quote_id = _hash_quote(*(row.get(key) for key in keys), prediction_time, "v191")
    ledger = PriceExplanationLedger(
        quote_id=quote_id,
        model_version=MODEL_VERSION,
        policy_version=POLICY_VERSION,
        as_of_time=_time(prediction_time),
        prediction_time=_time(prediction_time),
        target_vehicle=target,
        scenario_route=route,
        retrieval_summary={
            "total_retrieved_count": len(legal),
            "candidate_trace_count": len(retrieved),
            "retrieval_level_distribution": {"L0_exact_source_cluster": len(legal)},
            "source_family_distribution": legal["cluster_price_type"].value_counts().to_dict() if len(legal) else {},
            "latest_evidence_days": latest_days,
            "candidate_trace_truncated": trace_truncated,
        },
        retrieved_candidates=retrieved,
        selected_comparables=source_components,
        rejected_candidates=[],
        statistical_price={
            "calculation_method": "MULTI_STAGE_ROBUST_LOG_BLEND_WITH_ECONOMIC_GUARD",
            "raw_candidate_prices": [_float(value) for value in legal["price"].tolist()] if len(legal) else [],
            "outliers_removed": [],
            "candidate_weight_sum": sum(component["normalized_final_weight"] for component in source_components),
            "baseline_price": baseline,
            "price_dispersion": dispersion,
            "calculation_trace": {
                "fair_retail_transaction_price": _float(row.get("fair_retail_transaction_price")),
                "fast_sale_zero_cost_ceiling": ceiling,
                "direct_c2b_component": direct_c2b,
                "purchase_bridge_component": bridge_c2b,
                "purchase_to_sold_ratio": purchase_ratio,
                "c2b_robust_log_blend": c2b_trace,
                "stored_c2b_market_reference_price": c2b_reference,
                "economic_guard_method": "min(c2b_market_reference_price, zero_cost_purchase_ceiling)",
                "economic_guard_applied": (
                    c2b_reference is not None and ceiling is not None and c2b_reference > ceiling
                ),
                "stored_provisional_baseline": baseline,
                "reason_codes": [
                    ReasonCode.BASELINE_ROBUST_LOG_SOURCE_BLEND.value,
                    ReasonCode.BASELINE_HIERARCHICAL_SHRINKAGE.value,
                    ReasonCode.BASELINE_PURCHASE_TO_SOLD_BRIDGE.value,
                ],
            },
        },
        model_adjustment={
            "model_name": "NO_RESIDUAL_MODEL",
            "model_raw_output": 0.0,
            "raw_adjustment_ratio": 0.0,
            "raw_adjustment_amount": 0.0,
            "clip_lower": None,
            "clip_upper": None,
            "clip_applied": False,
            "final_adjustment_ratio": 0.0,
            "final_adjustment_amount": 0.0,
            "feature_contributions": [],
            "reason_codes": [ReasonCode.MODEL_ADJUSTMENT_NO_RESIDUAL_MODEL.value],
            "shap_reconciliation_applicable": False,
            "shap_reconciliation_passed": True,
        },
        final_price={
            "statistical_baseline_price": baseline,
            "model_adjustment_amount": 0.0,
            "final_point_price": baseline,
        },
        interval={
            "price_low": lower,
            "price_high": upper,
            "interval_width_ratio": None if baseline in (None, 0) or lower is None or upper is None else (upper - lower) / baseline,
            "calibration_method": "HISTORICAL_C2B_LOW_CAPPED_AT_ZERO_COST_CEILING",
            "driver_codes": interval_codes,
            "driver_details": [
                {"field": "exact_candidate_count", "value": len(legal)},
                {"field": "independent_source_count", "value": row.get("c2b_source_count")},
                {"field": "candidate_price_dispersion", "value": dispersion},
                {"field": "latest_evidence_days", "value": latest_days},
                {"field": "parent_borrowed", "value": int(row.get("b2c_parent_borrowed_flag") or 0) or int(row.get("c2b_parent_borrowed_flag") or 0)},
            ],
        },
        confidence=confidence,
        reconciliation={
            "recomputed_statistical_baseline_price": min(
                value for value in [c2b_reference, ceiling] if value is not None
            )
            if c2b_reference is not None or ceiling is not None
            else None,
            "recomputed_model_adjustment_amount": 0.0,
            "recomputed_final_price": baseline,
            "serving_final_price": baseline,
            "difference_from_serving_price": 0.0 if baseline is not None else None,
            "reconciliation_passed": baseline is not None,
        },
        audit_metadata={
            "actual_used_for_explanation": False,
            "individual_candidate_price_function": "source quantiles then hierarchical/source blend; candidate rows are lineage, source components carry arithmetic weights",
            "production_purchase_quote_ready": int(row.get("production_purchase_quote_ready") or 0),
        },
    )
    return render_and_attach(ledger)
