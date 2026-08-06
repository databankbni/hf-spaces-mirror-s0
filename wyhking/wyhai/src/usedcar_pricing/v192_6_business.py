from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_4_business import apply_serving_guard


CONFIDENCE_ORDER = {"MANUAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
CONDITION_ORDER = {
    "clean": 0,
    "minor_defect": 1,
    "major_risk": 2,
}

PRICE_ROLE_BY_SOURCE = {
    "internal_c2b_purchase": "INTERNAL_C2B_PURCHASE_PRICE",
    "internal_b2c_sold": "INTERNAL_B2C_SOLD_PRICE",
    "internal_b2c_listing": "INTERNAL_LISTING_PRICE",
    "external_autohome_b2c_listing": "EXTERNAL_LISTING_PRICE",
    "external_guazi_b2c_listing": "EXTERNAL_LISTING_PRICE",
}
PLATFORM_BY_SOURCE = {
    "internal_c2b_purchase": "INTERNAL_C2B",
    "internal_b2c_sold": "INTERNAL_B2C",
    "internal_b2c_listing": "INTERNAL_B2C",
    "external_autohome_b2c_listing": "AUTOHOME",
    "external_guazi_b2c_listing": "GUAZI",
}


def add_condition_input_basis(trace: pd.DataFrame) -> pd.DataFrame:
    result = trace.copy()
    condition = result["condition_risk_level"].fillna("unknown")
    complete = result.get(
        "condition_information_complete",
        pd.Series(0, index=result.index),
    ).fillna(0).eq(1)
    result["condition_input_basis_v192_6"] = np.select(
        [
            complete & condition.eq("clean"),
            complete & condition.isin(["minor_defect", "major_risk"]),
            ~complete & condition.eq("unknown"),
        ],
        [
            "USER_CONFIRMED_GOOD_CONDITION",
            "INSPECTION_CONFIRMED_CONDITION",
            "SYSTEM_DEFAULT_GOOD_CONDITION",
        ],
        default="CONDITION_UNKNOWN",
    )
    result["user_confirmed_condition_flag_v192_6"] = result[
        "condition_input_basis_v192_6"
    ].isin(
        [
            "USER_CONFIRMED_GOOD_CONDITION",
            "INSPECTION_CONFIRMED_CONDITION",
        ]
    ).astype(int)
    result["system_default_good_condition_flag_v192_6"] = result[
        "condition_input_basis_v192_6"
    ].eq("SYSTEM_DEFAULT_GOOD_CONDITION").astype(int)
    result["condition_unknown_flag_v192_6"] = result[
        "condition_input_basis_v192_6"
    ].eq("CONDITION_UNKNOWN").astype(int)
    return result


def compute_v192_6_confidence(trace: pd.DataFrame) -> pd.DataFrame:
    result = add_condition_input_basis(trace)
    no_quote = result["raw_price_before_guard"].isna()
    manual = (
        no_quote
        | result["candidate_dispersion"].fillna(np.inf).gt(0.65)
        | result["t4_fallback_weight"].fillna(0).gt(0.50)
    )
    weak_semantic_too_heavy = (
        result["t3b_heuristic_weight"].fillna(0)
        + result["t4_fallback_weight"].fillna(0)
    ).gt(0.12)
    condition_confirmed = result[
        "user_confirmed_condition_flag_v192_6"
    ].eq(1)
    condition_match = result[
        "candidate_condition_match_weight"
    ].fillna(0)
    high = (
        ~manual
        & condition_confirmed
        & ~weak_semantic_too_heavy
        & result["final_selected_candidate_count"].fillna(0).ge(8)
        & (
            result["exact_trim_weight"].fillna(0)
            + result["t3a_verified_weight"].fillna(0)
        ).ge(0.90)
        & result["exact_trim_weight"].fillna(0).ge(0.55)
        & result["candidate_condition_known_weight"].fillna(0).ge(0.85)
        & condition_match.ge(0.80)
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
        & condition_confirmed
        & ~weak_semantic_too_heavy
        & result["final_selected_candidate_count"].fillna(0).ge(5)
        & (
            result["exact_trim_weight"].fillna(0)
            + result["t3a_verified_weight"].fillna(0)
        ).ge(0.75)
        & result["candidate_condition_known_weight"].fillna(0).ge(0.60)
        & condition_match.ge(0.60)
        & result["evidence_weight_within_180d"].fillna(0).ge(0.65)
        & result["candidate_dispersion"].fillna(np.inf).le(0.22)
        & result["source_family_count_v192_5"].fillna(0).ge(2)
        & result["energy_information_complete"].fillna(0).eq(1)
        & result["model_adjustment_abs_ratio"].fillna(np.inf).le(0.10)
    )
    result["quote_evidence_confidence_pre_interval_v192_6"] = np.select(
        [manual, high, medium],
        ["MANUAL", "HIGH", "MEDIUM"],
        default="LOW",
    )
    result["quote_evidence_confidence_reason_v192_6"] = result.apply(
        confidence_reason_v192_6, axis=1
    )
    return result


def confidence_reason_v192_6(row: pd.Series) -> str:
    reasons: list[str] = []
    basis = row.get("condition_input_basis_v192_6")
    if basis == "SYSTEM_DEFAULT_GOOD_CONDITION":
        reasons.append("SYSTEM_DEFAULT_GOOD_CONDITION_MAX_LOW")
    elif basis == "CONDITION_UNKNOWN":
        reasons.append("CONDITION_UNKNOWN_MAX_LOW")
    if row.get("candidate_condition_match_weight", 0) < 0.60:
        reasons.append("CANDIDATE_CONDITION_MATCH_WEIGHT_INSUFFICIENT")
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


def apply_v192_6_interval_confidence(
    trace: pd.DataFrame,
) -> pd.DataFrame:
    result = trace.copy()
    confidence = result[
        "quote_evidence_confidence_pre_interval_v192_6"
    ].copy()
    width = result["required_interval_width_ratio_v192_5"].fillna(np.inf)
    price = pd.to_numeric(
        result["raw_price_before_guard"], errors="coerce"
    )
    high_too_wide = confidence.eq("HIGH") & width.gt(0.15)
    confidence.loc[high_too_wide] = "MEDIUM"
    high_outside = confidence.eq("HIGH") & ~price.between(
        result["candidate_price_p25"], result["candidate_price_p75"]
    )
    confidence.loc[high_outside] = "MEDIUM"
    medium_too_wide = confidence.eq("MEDIUM") & width.gt(0.25)
    confidence.loc[medium_too_wide] = "LOW"
    medium_outside = confidence.eq("MEDIUM") & ~price.between(
        result["candidate_price_p10"], result["candidate_price_p90"]
    )
    confidence.loc[medium_outside] = "LOW"
    result["quote_evidence_confidence"] = confidence
    result["quote_evidence_confidence_pre_interval"] = result[
        "quote_evidence_confidence_pre_interval_v192_6"
    ]
    auto = confidence.isin(["HIGH", "MEDIUM"]) & price.notna()
    result["interval_type"] = np.where(
        auto, "AUTO_QUOTE_INTERVAL", "EVIDENCE_REFERENCE_RANGE"
    )
    result["interval_display_label"] = np.where(
        auto, "合理报价区间", "证据参考范围"
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
    result["final_quote_display_value"] = np.where(
        auto, result["final_price"], np.nan
    )
    return result


def add_candidate_price_roles(selected: pd.DataFrame) -> pd.DataFrame:
    result = selected.copy()
    result["source_platform_v192_6"] = result["source_family"].map(
        PLATFORM_BY_SOURCE
    ).fillna("UNKNOWN_PLATFORM")
    result["original_price_role_v192_6"] = result["source_family"].map(
        PRICE_ROLE_BY_SOURCE
    ).fillna("UNKNOWN_PRICE_ROLE")
    result["original_price_v192_6"] = pd.to_numeric(
        result["candidate_price"], errors="coerce"
    )
    result["converted_c2b_equivalent_price_v192_6"] = pd.to_numeric(
        result["adjusted_candidate_price"], errors="coerce"
    )
    result["conversion_ratio_v192_6"] = (
        result["converted_c2b_equivalent_price_v192_6"]
        / result["original_price_v192_6"].replace(0, np.nan)
    )
    direct = result["original_price_role_v192_6"].eq(
        "INTERNAL_C2B_PURCHASE_PRICE"
    )
    result["conversion_method_v192_6"] = np.select(
        [
            direct,
            result["original_price_role_v192_6"].eq(
                "INTERNAL_B2C_SOLD_PRICE"
            ),
            result["original_price_role_v192_6"].eq(
                "INTERNAL_LISTING_PRICE"
            ),
            result["original_price_role_v192_6"].eq(
                "EXTERNAL_LISTING_PRICE"
            ),
        ],
        [
            "DIRECT_INTERNAL_C2B_NO_CONVERSION",
            "HISTORICAL_INTERNAL_B2C_TO_C2B_BRIDGE",
            "HISTORICAL_INTERNAL_LISTING_TO_C2B_BRIDGE",
            "EXTERNAL_LISTING_TO_C2B_BRIDGE",
        ],
        default="UNKNOWN_CONVERSION_METHOD",
    )
    result["final_price_used_v192_6"] = result[
        "converted_c2b_equivalent_price_v192_6"
    ]
    result["price_conversion_applied_flag_v192_6"] = (~direct).astype(int)
    result["price_role_conversion_valid_flag_v192_6"] = (
        result["original_price_v192_6"].gt(0)
        & result["converted_c2b_equivalent_price_v192_6"].gt(0)
        & result["conversion_ratio_v192_6"].gt(0)
        & result["original_price_role_v192_6"].ne("UNKNOWN_PRICE_ROLE")
    ).astype(int)
    return result


def _condition_worsened(
    previous: dict[str, Any], current: dict[str, Any]
) -> bool:
    before = CONDITION_ORDER.get(str(previous.get("condition_risk_level")))
    after = CONDITION_ORDER.get(str(current.get("condition_risk_level")))
    return (
        before is not None
        and after is not None
        and after > before
    )


def detect_request_changes(
    previous_vehicle_state: dict[str, Any] | None,
    current_vehicle_state: dict[str, Any] | None,
    previous_evidence_state: dict[str, Any] | None = None,
    current_evidence_state: dict[str, Any] | None = None,
) -> dict[str, bool]:
    previous_vehicle_state = previous_vehicle_state or {}
    current_vehicle_state = current_vehicle_state or {}

    def increased(field: str) -> bool:
        before = pd.to_numeric(
            pd.Series([previous_vehicle_state.get(field)]),
            errors="coerce",
        ).iloc[0]
        after = pd.to_numeric(
            pd.Series([current_vehicle_state.get(field)]),
            errors="coerce",
        ).iloc[0]
        return bool(pd.notna(before) and pd.notna(after) and after > before)

    evidence_weakened = False
    if previous_evidence_state and current_evidence_state:
        strength_fields = (
            "source_family_count",
            "same_city_weight",
            "recent_90d_weight",
            "candidate_condition_match_weight",
        )
        evidence_weakened = any(
            float(current_evidence_state.get(field) or 0)
            < float(previous_evidence_state.get(field) or 0) - 1e-12
            for field in strength_fields
        )
    return {
        "age_increased": increased("age_years"),
        "mileage_increased": increased("mileage_wan_km"),
        "transfer_increased": increased("transfer_count"),
        "condition_worsened": _condition_worsened(
            previous_vehicle_state, current_vehicle_state
        ),
        "evidence_weakened": evidence_weakened,
    }


@dataclass
class V1926ServingQuoteService:
    entrypoint_name: str = "V1926ServingQuoteService.quote"

    def quote(
        self,
        *,
        raw_price: float | None,
        raw_confidence: str,
        previous_price: float | None = None,
        previous_confidence: str | None = None,
        previous_vehicle_state: dict[str, Any] | None = None,
        current_vehicle_state: dict[str, Any] | None = None,
        previous_evidence_state: dict[str, Any] | None = None,
        current_evidence_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        detected = detect_request_changes(
            previous_vehicle_state,
            current_vehicle_state,
            previous_evidence_state,
            current_evidence_state,
        )
        guard = apply_serving_guard(
            raw_price,
            raw_confidence,
            reference_price=previous_price,
            reference_confidence=previous_confidence,
            **detected,
        )
        return {
            "serving_entrypoint": self.entrypoint_name,
            "serving_guard_called": 1,
            "change_flags_source": "SERVICE_AUTO_DETECTION",
            "manual_change_flags_supplied_count": 0,
            **detected,
            "guard_rule_codes": guard["guard_rule"],
            "guard_adjustment_amount": guard["guard_adjustment"],
            **guard,
        }


def vehicle_state(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    return {
        "age_years": row.get(f"{prefix}age_years"),
        "mileage_wan_km": row.get(f"{prefix}mileage_wan_km"),
        "transfer_count": row.get(f"{prefix}transfer_count"),
        "condition_risk_level": row.get(
            f"{prefix}condition_risk_level",
            row.get(f"{prefix}condition"),
        ),
    }


def evidence_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_family_count": row.get(
            "source_family_count_v192_5",
            row.get("source_family_count"),
        ),
        "same_city_weight": row.get("same_city_weight"),
        "recent_90d_weight": row.get("evidence_weight_within_90d"),
        "candidate_condition_match_weight": row.get(
            "candidate_condition_match_weight"
        ),
    }


def risk_warnings_v192_6(row: pd.Series) -> list[str]:
    warnings: list[str] = []
    basis = row.get("condition_input_basis_v192_6")
    if basis == "SYSTEM_DEFAULT_GOOD_CONDITION_ASSUMPTION":
        warnings.append("系统默认良好车况假设，未得到用户明确确认")
    elif basis == "CONDITION_UNKNOWN":
        warnings.append("目标车况未知")
    if row.get("candidate_condition_match_weight", 0) < 0.60:
        warnings.append("候选车况不完全匹配")
    if row.get("source_family_count_v192_5", 0) < 2:
        warnings.append("只有单一来源")
    if row.get("same_city_weight", 0) <= 1e-12:
        warnings.append("没有同城证据")
    if row.get("evidence_weight_within_90d", 0) < 0.60:
        warnings.append("近期证据不足")
    if row.get("t3b_heuristic_weight", 0) > 1e-12:
        warnings.append("使用T3B启发式候选")
    if row.get("t4_fallback_weight", 0) > 1e-12:
        warnings.append("使用T4兜底候选")
    if row.get("final_selected_candidate_count", 0) <= 3:
        warnings.append("候选数量较少")
    if row.get("business_interval_width_ratio", 0) > 0.30:
        warnings.append("证据参考范围较宽")
    if row.get("b2c_conversion_weight_v192_6", 0) > 1e-12:
        warnings.append("部分价格经过B2C到C2B折算")
    return warnings


def strict_json_dumps(value: Any) -> str:
    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: clean(value) for key, value in item.items()}
        if isinstance(item, list):
            return [clean(value) for value in item]
        if isinstance(item, (np.floating, float)):
            return float(item) if np.isfinite(item) else None
        if isinstance(item, np.integer):
            return int(item)
        if isinstance(item, pd.Timestamp):
            return item.isoformat()
        if not isinstance(item, (str, bool)) and pd.isna(item):
            return None
        return item

    return json.dumps(
        clean(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
