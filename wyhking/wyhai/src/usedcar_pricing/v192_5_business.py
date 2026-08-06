from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_1_pricing import weighted_quantile
from .v192_4_business import apply_serving_guard, baseline_candidates


CONFIDENCE_ORDER = {"MANUAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
KNOWN_CONDITIONS = {"clean", "minor_defect", "major_risk"}


def _weighted_sum(
    frame: pd.DataFrame, mask: pd.Series, weight_column: str
) -> float:
    return float(
        pd.to_numeric(
            frame.loc[mask, weight_column], errors="coerce"
        ).fillna(0).sum()
    )


def _stable_hash(values: list[Any]) -> str:
    text = "|".join("" if pd.isna(value) else str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def add_v192_5_evidence_features(
    trace: pd.DataFrame, selected: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    weight_column = "final_normalized_weight_v192_4"
    for query_id, raw_group in selected.groupby("query_id", sort=False):
        group = baseline_candidates(raw_group)
        if group.empty:
            rows.append(
                {
                    "query_id": query_id,
                    "canonical_lifecycle_id": f"unresolved::{query_id}",
                    "candidate_condition_known_weight": 0.0,
                    "candidate_condition_unknown_weight": 0.0,
                    "candidate_condition_match_weight": 0.0,
                    "source_family_count_v192_5": 0,
                    "source_family_list_v192_5": "",
                    "weighted_candidate_age_years": 0.0,
                    "weighted_candidate_mileage_wan_km": 0.0,
                    "weighted_candidate_transfer_count": 0.0,
                    "weighted_candidate_days_since_transaction": 9999.0,
                    "effective_candidate_count": 0.0,
                }
            )
            continue
        weights = pd.to_numeric(
            group[weight_column], errors="coerce"
        ).fillna(0)
        if len(group) and weights.sum() <= 0:
            weights = pd.Series(np.ones(len(group)) / len(group), index=group.index)
        lifecycle_values = group["query_canonical_lifecycle_id"].dropna()
        rows.append(
            {
                "query_id": query_id,
                "canonical_lifecycle_id": (
                    str(lifecycle_values.iloc[0])
                    if not lifecycle_values.empty
                    else f"unresolved::{query_id}"
                ),
                "candidate_condition_known_weight": _weighted_sum(
                    group,
                    group["condition_risk_level"].isin(KNOWN_CONDITIONS),
                    weight_column,
                ),
                "candidate_condition_unknown_weight": _weighted_sum(
                    group,
                    ~group["condition_risk_level"].isin(KNOWN_CONDITIONS),
                    weight_column,
                ),
                "candidate_condition_match_weight": _weighted_sum(
                    group, group["condition_match"].eq(1), weight_column
                ),
                "source_family_count_v192_5": int(
                    group["source_family"].nunique(dropna=True)
                ),
                "source_family_list_v192_5": "|".join(
                    sorted(
                        {
                            str(value)
                            for value in group["source_family"].dropna()
                            if str(value).strip()
                        }
                    )
                ),
                "weighted_candidate_age_years": float(
                    np.average(
                        pd.to_numeric(
                            group["age_years"], errors="coerce"
                        ).fillna(0),
                        weights=weights,
                    )
                ),
                "weighted_candidate_mileage_wan_km": float(
                    np.average(
                        pd.to_numeric(
                            group["mileage_wan_km"], errors="coerce"
                        ).fillna(0),
                        weights=weights,
                    )
                ),
                "weighted_candidate_transfer_count": float(
                    np.average(
                        pd.to_numeric(
                            group["transfer_count"], errors="coerce"
                        ).fillna(0),
                        weights=weights,
                    )
                ),
                "weighted_candidate_days_since_transaction": float(
                    np.average(
                        pd.to_numeric(
                            group["days_since_transaction"], errors="coerce"
                        ).fillna(9999),
                        weights=weights,
                    )
                ),
                "effective_candidate_count": float(
                    1.0 / max(float(np.square(weights).sum()), 1e-12)
                ),
            }
        )
    result = trace.merge(pd.DataFrame(rows), on="query_id", how="left")
    result["canonical_lifecycle_id"] = result[
        "canonical_lifecycle_id"
    ].fillna(result["query_id"].map(lambda value: f"unresolved::{value}"))
    result["normalized_input_id"] = result.apply(
        lambda row: _stable_hash(
            [
                row.get("brand"),
                row.get("series"),
                row.get("model_year"),
                row.get("trim"),
                row.get("city"),
                row.get("color"),
                round(float(row.get("age_years") or 0), 2),
                round(float(row.get("mileage_wan_km") or 0), 2),
                round(float(row.get("transfer_count") or 0), 1),
                row.get("condition_risk_level"),
                row.get("query_energy_type"),
            ]
        ),
        axis=1,
    )
    confirmed = result["condition_risk_level"].isin(KNOWN_CONDITIONS)
    result["target_condition_confirmed_flag"] = confirmed.astype(int)
    result["target_good_condition_assumption_flag"] = (~confirmed).astype(int)
    result["target_condition_pricing_basis"] = np.where(
        confirmed,
        "CONFIRMED_CONDITION_INPUT",
        "ASSUMED_GOOD_CONDITION_REQUIRES_CONFIRMATION",
    )
    result["single_source_family_flag"] = (
        result["source_family_count_v192_5"].fillna(0).le(1).astype(int)
    )
    result["no_same_city_evidence_flag"] = (
        result["same_city_weight"].fillna(0).le(1e-12).astype(int)
    )
    return result


def compute_v192_5_confidence(trace: pd.DataFrame) -> pd.DataFrame:
    result = trace.copy()
    no_quote = result["raw_price_before_guard"].isna()
    manual = (
        no_quote
        | result["candidate_dispersion"].fillna(np.inf).gt(0.65)
        | result["t4_fallback_weight"].fillna(0).gt(0.50)
    )
    condition_basis_ok = (
        result["target_condition_confirmed_flag"].eq(1)
        | result["target_good_condition_assumption_flag"].eq(1)
    )
    weak_semantic_too_heavy = (
        result["t3b_heuristic_weight"].fillna(0)
        + result["t4_fallback_weight"].fillna(0)
    ).gt(0.12)
    high = (
        ~manual
        & result["target_condition_confirmed_flag"].eq(1)
        & ~weak_semantic_too_heavy
        & result["final_selected_candidate_count"].fillna(0).ge(8)
        & (
            result["exact_trim_weight"].fillna(0)
            + result["t3a_verified_weight"].fillna(0)
        ).ge(0.90)
        & result["exact_trim_weight"].fillna(0).ge(0.55)
        & result["candidate_condition_known_weight"].fillna(0).ge(0.85)
        & result["evidence_weight_within_90d"].fillna(0).ge(0.70)
        & result["candidate_dispersion"].fillna(np.inf).le(0.12)
        & result["source_family_count_v192_5"].fillna(0).ge(2)
        & result["same_city_weight"].fillna(0).ge(0.10)
        & result["energy_information_complete"].fillna(0).eq(1)
        & result["model_adjustment_abs_ratio"].fillna(np.inf).le(0.05)
    )
    medium = (
        ~manual
        & ~high
        & condition_basis_ok
        & ~weak_semantic_too_heavy
        & result["final_selected_candidate_count"].fillna(0).ge(5)
        & (
            result["exact_trim_weight"].fillna(0)
            + result["t3a_verified_weight"].fillna(0)
        ).ge(0.75)
        & result["candidate_condition_known_weight"].fillna(0).ge(0.60)
        & result["evidence_weight_within_180d"].fillna(0).ge(0.65)
        & result["candidate_dispersion"].fillna(np.inf).le(0.22)
        & result["source_family_count_v192_5"].fillna(0).ge(2)
        & result["energy_information_complete"].fillna(0).eq(1)
        & result["model_adjustment_abs_ratio"].fillna(np.inf).le(0.10)
    )
    result["quote_evidence_confidence_pre_interval_v192_5"] = np.select(
        [manual, high, medium],
        ["MANUAL", "HIGH", "MEDIUM"],
        default="LOW",
    )
    result["quote_evidence_confidence_reason_v192_5"] = result.apply(
        confidence_reason_v192_5, axis=1
    )
    return result


def confidence_reason_v192_5(row: pd.Series) -> str:
    reasons: list[str] = []
    if pd.isna(row.get("raw_price_before_guard")):
        reasons.append("NO_MARKET_REFERENCE_POINT")
    if row.get("target_condition_confirmed_flag", 0) == 0:
        reasons.append("TARGET_CONDITION_ASSUMED_GOOD")
    if row.get("candidate_condition_known_weight", 0) < 0.60:
        reasons.append("CANDIDATE_CONDITION_MOSTLY_UNKNOWN")
    if row.get("t3b_heuristic_weight", 0) > 0.12:
        reasons.append("USES_T3B_HEURISTIC")
    if row.get("t4_fallback_weight", 0) > 0.08:
        reasons.append("USES_T4_FALLBACK")
    if row.get("source_family_count_v192_5", 0) < 2:
        reasons.append("SINGLE_SOURCE_FAMILY")
    if row.get("same_city_weight", 0) <= 1e-12:
        reasons.append("NO_SAME_CITY_EVIDENCE")
    if row.get("evidence_weight_within_180d", 0) < 0.65:
        reasons.append("RECENT_EVIDENCE_INSUFFICIENT")
    if row.get("candidate_dispersion", np.inf) > 0.22:
        reasons.append("CANDIDATE_PRICE_DISPERSION_HIGH")
    if row.get("final_selected_candidate_count", 0) < 5:
        reasons.append("CANDIDATE_COUNT_LIMITED")
    return "|".join(reasons) if reasons else "STRICT_BUSINESS_EVIDENCE_PASS"


def build_v192_5_intervals(trace: pd.DataFrame) -> pd.DataFrame:
    result = trace.copy()
    price = pd.to_numeric(
        result["raw_price_before_guard"], errors="coerce"
    )
    count = result["final_selected_candidate_count"].fillna(0)
    dispersion = result["candidate_dispersion"].fillna(0.60).clip(0, 1.5)
    model_adjustment = result["model_adjustment_abs_ratio"].fillna(0)
    low_price = price.lt(30_000)
    scarcity_floor = np.select(
        [count.le(1), count.le(3), count.le(5), count.le(8)],
        [0.30, 0.24, 0.20, 0.16],
        default=0.12,
    )
    scarcity_floor = np.where(
        low_price,
        np.maximum(scarcity_floor, np.where(price.lt(10_000), 0.45, 0.32)),
        scarcity_floor,
    )
    semantic_uncertainty = (
        0.18 * result["t3b_heuristic_weight"].fillna(0)
        + 0.28 * result["t4_fallback_weight"].fillna(0)
        + 0.08 * result["unknown_energy_strict_weight"].fillna(0)
    )
    freshness_uncertainty = np.select(
        [
            result["evidence_weight_within_90d"].fillna(0).ge(0.70),
            result["evidence_weight_within_180d"].fillna(0).ge(0.65),
        ],
        [0.0, 0.04],
        default=0.10,
    )
    city_uncertainty = np.where(
        result["same_city_weight"].fillna(0).gt(0), 0.0, 0.05
    )
    source_uncertainty = np.where(
        result["source_family_count_v192_5"].fillna(0).ge(2), 0.0, 0.06
    )
    condition_uncertainty = (
        0.10
        * (1 - result["candidate_condition_known_weight"].fillna(0).clip(0, 1))
    )
    required_width = np.maximum.reduce(
        [
            np.asarray(scarcity_floor, dtype=float),
            (1.15 * dispersion).to_numpy(dtype=float),
            (1.25 * model_adjustment).to_numpy(dtype=float),
            (
                semantic_uncertainty
                + freshness_uncertainty
                + city_uncertainty
                + source_uncertainty
                + condition_uncertainty
            ).to_numpy(dtype=float),
            np.full(len(result), 0.08),
        ]
    )
    required_width = np.clip(required_width, 0.08, 0.70)
    result["minimum_uncertainty_width_ratio"] = scarcity_floor
    result["required_interval_width_ratio_v192_5"] = required_width
    confidence = result[
        "quote_evidence_confidence_pre_interval_v192_5"
    ].copy()
    high_too_wide = confidence.eq("HIGH") & (required_width > 0.15)
    confidence.loc[high_too_wide] = "MEDIUM"
    high_outside_core = confidence.eq("HIGH") & ~price.between(
        result["candidate_price_p25"], result["candidate_price_p75"]
    )
    confidence.loc[high_outside_core] = "MEDIUM"
    medium_too_wide = confidence.eq("MEDIUM") & (required_width > 0.25)
    confidence.loc[medium_too_wide] = "LOW"
    medium_outside_range = confidence.eq("MEDIUM") & ~price.between(
        result["candidate_price_p10"], result["candidate_price_p90"]
    )
    confidence.loc[medium_outside_range] = "LOW"
    result["interval_confidence_downgrade_reason_v192_5"] = np.select(
        [
            medium_outside_range,
            medium_too_wide,
            high_outside_core,
            high_too_wide,
        ],
        [
            "MEDIUM_POINT_OUTSIDE_CANDIDATE_P10_P90",
            "MEDIUM_REQUIRED_WIDTH_EXCEEDS_25_PERCENT",
            "HIGH_POINT_OUTSIDE_CANDIDATE_P25_P75",
            "HIGH_REQUIRED_WIDTH_EXCEEDS_15_PERCENT",
        ],
        default="",
    )
    result["quote_evidence_confidence"] = confidence
    auto = confidence.isin(["HIGH", "MEDIUM"]) & price.notna()
    result["interval_type"] = np.where(
        auto, "AUTO_QUOTE_INTERVAL", "EVIDENCE_REFERENCE_RANGE"
    )
    result["interval_display_label"] = np.select(
        [
            confidence.eq("MANUAL"),
            confidence.eq("LOW"),
            auto,
        ],
        ["证据参考范围", "证据参考范围", "合理报价区间"],
        default="证据参考范围",
    )
    result["quote_display_type"] = np.select(
        [
            confidence.eq("MANUAL"),
            confidence.eq("LOW"),
            auto,
        ],
        [
            "MANUAL_REVIEW_REFERENCE",
            "LOW_CONFIDENCE_MARKET_REFERENCE",
            "AUTO_QUOTE_MARKET_REFERENCE",
        ],
        default="MANUAL_REVIEW_REFERENCE",
    )
    result["quote_point_display_label"] = np.select(
        [
            confidence.eq("MANUAL"),
            confidence.eq("LOW"),
            auto,
        ],
        ["待复核市场参考点", "低置信市场参考", "建议市场参考价"],
        default="待复核市场参考点",
    )
    result["auto_quote_recommendation"] = np.where(
        auto, "建议自动报价", "暂不建议自动报价"
    )
    center = price.fillna(result["statistical_baseline_price"])
    half_width = required_width / 2
    proposed_low = center * (1 - half_width)
    proposed_high = center * (1 + half_width)
    candidate_low = result["candidate_price_p10"]
    candidate_high = result["candidate_price_p90"]
    evidence_range = ~auto
    proposed_low = np.where(
        evidence_range & candidate_low.notna(),
        np.minimum(proposed_low, candidate_low),
        proposed_low,
    )
    proposed_high = np.where(
        evidence_range & candidate_high.notna(),
        np.maximum(proposed_high, candidate_high),
        proposed_high,
    )
    result["business_interval_low"] = pd.Series(
        proposed_low, index=result.index
    ).clip(lower=0)
    result["business_interval_high"] = proposed_high
    result.loc[center.isna(), ["business_interval_low", "business_interval_high"]] = np.nan
    result["business_interval_width_ratio"] = (
        result["business_interval_high"] - result["business_interval_low"]
    ) / center.replace(0, np.nan)
    result["zero_width_interval_flag"] = (
        center.notna()
        & (
            result["business_interval_high"]
            - result["business_interval_low"]
        ).abs().le(1e-9)
    ).astype(int)
    result["market_reference_point"] = center
    result["final_quote_display_value"] = np.where(
        auto, result["final_price"], np.nan
    )
    return result


@dataclass
class V1925ServingQuoteService:
    entrypoint_name: str = "V1925ServingQuoteService.quote"

    def quote(
        self,
        *,
        raw_price: float | None,
        raw_confidence: str,
        reference_price: float | None = None,
        reference_confidence: str | None = None,
        age_increased: bool = False,
        mileage_increased: bool = False,
        transfer_increased: bool = False,
        condition_worsened: bool = False,
        evidence_weakened: bool = False,
    ) -> dict[str, Any]:
        guard = apply_serving_guard(
            raw_price,
            raw_confidence,
            reference_price=reference_price,
            reference_confidence=reference_confidence,
            age_increased=age_increased,
            mileage_increased=mileage_increased,
            transfer_increased=transfer_increased,
            condition_worsened=condition_worsened,
            evidence_weakened=evidence_weakened,
        )
        return {
            "serving_entrypoint": self.entrypoint_name,
            "serving_guard_called": 1,
            "guard_rule_codes": guard["guard_rule"],
            "guard_adjustment_amount": guard["guard_adjustment"],
            **guard,
        }


def apply_formal_serving(
    trace: pd.DataFrame,
    *,
    service: V1925ServingQuoteService | None = None,
) -> pd.DataFrame:
    service = service or V1925ServingQuoteService()
    result = trace.copy()
    outputs = [
        service.quote(
            raw_price=row.get("raw_price_before_guard"),
            raw_confidence=row.get(
                "quote_evidence_confidence", "MANUAL"
            ),
        )
        for row in result.to_dict("records")
    ]
    guard = pd.DataFrame(outputs, index=result.index)
    guard = guard.drop(columns=["raw_price_before_guard"])
    drop = [
        column
        for column in (
            "guard_rule",
            "guard_triggered",
            "guard_adjustment",
            "final_price_after_guard",
            "quote_evidence_confidence_after_guard",
        )
        if column in result.columns
    ]
    result = result.drop(columns=drop)
    result = pd.concat([result, guard], axis=1)
    result["guard_rule"] = result["guard_rule_codes"]
    result["guard_adjustment"] = result["guard_adjustment_amount"]
    result["final_price"] = result["final_price_after_guard"]
    result["quote_evidence_confidence"] = result[
        "quote_evidence_confidence_after_guard"
    ]
    return result


def risk_warnings_v192_5(row: pd.Series) -> list[str]:
    warnings: list[str] = []
    if row.get("target_condition_confirmed_flag", 0) == 0:
        warnings.append("目标车况未知，当前按良好车况假设")
    if row.get("candidate_condition_known_weight", 0) < 0.60:
        warnings.append("候选车况未知权重过高")
    if row.get("source_family_count_v192_5", 0) < 2:
        warnings.append("只有单一来源")
    if row.get("same_city_weight", 0) <= 1e-12:
        warnings.append("没有同城证据")
    if row.get("evidence_weight_within_180d", 0) < 0.65:
        warnings.append("近期证据不足")
    if row.get("t3b_heuristic_weight", 0) > 1e-12:
        warnings.append("使用T3B启发式候选")
    if row.get("t4_fallback_weight", 0) > 1e-12:
        warnings.append("使用T4兜底")
    if row.get("final_selected_candidate_count", 0) <= 3:
        warnings.append("候选数量过少")
    if row.get("business_interval_width_ratio", 0) > 0.30:
        warnings.append("证据参考范围较宽")
    if row.get("query_energy_type") in {None, "", "UNKNOWN"}:
        warnings.append("能源字段未知")
    return warnings


def market_positioning_v192_5(row: pd.Series) -> str:
    confidence = row.get("quote_evidence_confidence", "MANUAL")
    strict_medium = (
        confidence == "MEDIUM"
        and row.get("evidence_weight_within_90d", 0) >= 0.60
        and row.get("source_family_count_v192_5", 0) >= 2
        and row.get("candidate_condition_known_weight", 0) >= 0.70
    )
    if confidence == "HIGH" or strict_medium:
        return "当前市场行情参考"
    if row.get("evidence_weight_within_180d", 0) >= 0.50:
        return "近期历史成交参考"
    return "跨区域历史市场证据"


def finite_or_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: finite_or_none(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_or_none(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if not isinstance(value, (str, bool)) and pd.isna(value):
        return None
    return value


def strict_json_dumps(value: Any) -> str:
    return json.dumps(
        finite_or_none(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
