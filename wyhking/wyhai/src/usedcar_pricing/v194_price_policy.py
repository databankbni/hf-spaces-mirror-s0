from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_16_semantics import canonicalize_trim, normalize_energy_type


PRICE_POLICY_VERSION = "v194_price_role_quality_policy_v1"

TOKEN_PRICE_VALUES = {
    1,
    2,
    4,
    10,
    50,
    100,
    101,
    111,
    123,
    999,
    1000,
    1111,
    1234,
    2000,
    2222,
    3000,
    3333,
    9999,
}


@dataclass(frozen=True)
class PriceRolePolicy:
    price_role: str
    source_family: str
    allowed_for_c2b_point_baseline: bool
    allowed_for_b2c_market_reference: bool
    allowed_for_c2b_bridge_input: bool
    allowed_for_interval: bool
    allowed_for_explanation: bool
    allowed_for_manual_reference: bool
    default_price_quality: str
    definition: str


PRICE_ROLE_POLICIES: dict[str, PriceRolePolicy] = {
    "INTERNAL_C2B_PURCHASE_ACTUAL": PriceRolePolicy(
        price_role="INTERNAL_C2B_PURCHASE_ACTUAL",
        source_family="internal_c2b",
        allowed_for_c2b_point_baseline=True,
        allowed_for_b2c_market_reference=False,
        allowed_for_c2b_bridge_input=False,
        allowed_for_interval=True,
        allowed_for_explanation=True,
        allowed_for_manual_reference=True,
        default_price_quality="strict",
        definition="内部真实收车合同价；可作为 C2B 历史 as-of 单点基线证据。",
    ),
    "INTERNAL_B2C_SOLD_ACTUAL": PriceRolePolicy(
        price_role="INTERNAL_B2C_SOLD_ACTUAL",
        source_family="internal_b2c",
        allowed_for_c2b_point_baseline=False,
        allowed_for_b2c_market_reference=True,
        allowed_for_c2b_bridge_input=True,
        allowed_for_interval=True,
        allowed_for_explanation=True,
        allowed_for_manual_reference=True,
        default_price_quality="bridge_input",
        definition="内部真实零售成交价；只能通过 B2C→C2B bridge 或区间/解释进入。",
    ),
    "EXTERNAL_B2C_LISTING": PriceRolePolicy(
        price_role="EXTERNAL_B2C_LISTING",
        source_family="external_b2c",
        allowed_for_c2b_point_baseline=False,
        allowed_for_b2c_market_reference=True,
        allowed_for_c2b_bridge_input=True,
        allowed_for_interval=True,
        allowed_for_explanation=True,
        allowed_for_manual_reference=True,
        default_price_quality="external_listing",
        definition="外部二手车挂牌价；不得直接作为 C2B 单点基线。",
    ),
    "NEW_CAR_GUIDE_PRICE": PriceRolePolicy(
        price_role="NEW_CAR_GUIDE_PRICE",
        source_family="static_kb",
        allowed_for_c2b_point_baseline=False,
        allowed_for_b2c_market_reference=False,
        allowed_for_c2b_bridge_input=False,
        allowed_for_interval=False,
        allowed_for_explanation=True,
        allowed_for_manual_reference=True,
        default_price_quality="static_reference",
        definition="厂商指导价/新车价；只能作为静态属性和折旧参考，不能当二手成交价。",
    ),
    "WEB_AGGREGATE_OR_CONTEXT_PRICE": PriceRolePolicy(
        price_role="WEB_AGGREGATE_OR_CONTEXT_PRICE",
        source_family="web_context",
        allowed_for_c2b_point_baseline=False,
        allowed_for_b2c_market_reference=False,
        allowed_for_c2b_bridge_input=False,
        allowed_for_interval=False,
        allowed_for_explanation=True,
        allowed_for_manual_reference=True,
        default_price_quality="context_only",
        definition="网页聚合价/资讯价/参数页价；只能用于解释或人工参考。",
    ),
    "UNKNOWN_OR_UNTRUSTED_PRICE": PriceRolePolicy(
        price_role="UNKNOWN_OR_UNTRUSTED_PRICE",
        source_family="unknown",
        allowed_for_c2b_point_baseline=False,
        allowed_for_b2c_market_reference=False,
        allowed_for_c2b_bridge_input=False,
        allowed_for_interval=False,
        allowed_for_explanation=False,
        allowed_for_manual_reference=True,
        default_price_quality="quarantined",
        definition="口径不明或不可信价格；隔离，不进入自动定价。",
    ),
}


def price_role_definition_frame() -> pd.DataFrame:
    return pd.DataFrame([policy.__dict__ for policy in PRICE_ROLE_POLICIES.values()])


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _norm_text(value).lower())


def normalize_price_role(source_type: Any, price_type: Any, source_url: Any = "") -> str:
    source = _compact(source_type)
    price = _compact(price_type)
    url = _compact(source_url)
    body = "|".join([source, price, url])
    if "internal_c2b_purchase" in source or "c2b_purchase_actual" in price:
        return "INTERNAL_C2B_PURCHASE_ACTUAL"
    if "internal_b2c_sold" in source or "b2c_sold_actual" in price:
        return "INTERNAL_B2C_SOLD_ACTUAL"
    if "external_autohome_b2c_listing" in source or "external_guazi_b2c_listing" in source or "external_b2c_listing" in price:
        return "EXTERNAL_B2C_LISTING"
    if any(token in body for token in ("guide_price", "newcar", "厂商指导", "新车指导", "official")):
        return "NEW_CAR_GUIDE_PRICE"
    if any(token in body for token in ("article", "news", "parameter", "aggregate", "context", "参数", "资讯", "报价")):
        return "WEB_AGGREGATE_OR_CONTEXT_PRICE"
    return "UNKNOWN_OR_UNTRUSTED_PRICE"


def _is_yes(value: Any) -> bool:
    text = _compact(value)
    return text in {"1", "true", "yes", "y", "是", "事故", "泡水", "火烧", "调表"}


def normalize_condition_record(record: dict[str, Any]) -> dict[str, Any]:
    grade = _norm_text(record.get("inspection_grade") or record.get("inspection_grade_norm")).upper()
    if grade not in {"A", "B", "C", "D", "E"}:
        grade = "missing"
    major = any(_is_yes(record.get(key)) for key in ("is_accident", "is_flood", "is_fire", "is_odometer_abnormal"))
    if major or grade in {"D", "E"}:
        level = "major_risk"
    elif grade in {"A", "B"}:
        level = "clean"
    elif grade == "C":
        level = "minor_defect"
    else:
        raw = _norm_text(record.get("condition_risk_level") or record.get("condition_risk_level_v192_16")).lower()
        level = raw if raw in {"clean", "minor_defect", "major_risk", "unknown"} else "unknown"
    return {
        "inspection_grade_norm": grade,
        "has_inspection_report": int(grade != "missing"),
        "condition_risk_level_strict": level,
    }


def quality_rule_matrix_frame() -> pd.DataFrame:
    rows = [
        {
            "rule_group": "price_placeholder",
            "rule": "price in token set or non-positive",
            "automatic_action": "quarantine",
            "allowed_for_point_baseline": False,
            "reason_code": "TOKEN_OR_PLACEHOLDER_PRICE",
        },
        {
            "rule_group": "price_range",
            "rule": "price < 1000 or price > 2,000,000",
            "automatic_action": "quarantine",
            "allowed_for_point_baseline": False,
            "reason_code": "PRICE_OUT_OF_BUSINESS_RANGE",
        },
        {
            "rule_group": "event_time",
            "rule": "event_time missing, sentinel 1970, or knowledge_available_at before event sanity fails",
            "automatic_action": "manual_reference_only",
            "allowed_for_point_baseline": False,
            "reason_code": "EVENT_TIME_INVALID",
        },
        {
            "rule_group": "vehicle_identity",
            "rule": "brand/series/year/trim canonical key missing or unresolved",
            "automatic_action": "exclude_from_same_trim_baseline",
            "allowed_for_point_baseline": False,
            "reason_code": "VEHICLE_IDENTITY_INSUFFICIENT",
        },
        {
            "rule_group": "condition",
            "rule": "D/E, accident, flood, fire, odometer abnormal",
            "automatic_action": "separate_risk_scope",
            "allowed_for_point_baseline": False,
            "reason_code": "MAJOR_CONDITION_RISK",
        },
        {
            "rule_group": "source_role",
            "rule": "external/current listing or web context",
            "automatic_action": "not_direct_c2b_baseline",
            "allowed_for_point_baseline": False,
            "reason_code": "ROLE_NOT_DIRECT_C2B",
        },
    ]
    return pd.DataFrame(rows)


def _price_reason_codes(price: Any) -> list[str]:
    numeric = pd.to_numeric(price, errors="coerce")
    if pd.isna(numeric):
        return ["PRICE_MISSING"]
    value = float(numeric)
    if value <= 0:
        return ["PRICE_MISSING_OR_NONPOSITIVE"]
    if int(round(value)) in TOKEN_PRICE_VALUES:
        return ["TOKEN_OR_PLACEHOLDER_PRICE"]
    if value < 1000 or value > 2_000_000:
        return ["PRICE_OUT_OF_BUSINESS_RANGE"]
    return []


def _event_reason_codes(event_time: Any, knowledge_available_at: Any) -> list[str]:
    event = pd.to_datetime(event_time, errors="coerce")
    known = pd.to_datetime(knowledge_available_at, errors="coerce")
    reasons: list[str] = []
    if pd.isna(event) or event.year <= 1971:
        reasons.append("EVENT_TIME_INVALID")
    if pd.isna(known):
        reasons.append("KNOWLEDGE_AVAILABLE_AT_MISSING")
    return reasons


def _identity_reason_codes(record: dict[str, Any]) -> list[str]:
    missing = [
        name
        for name in ("brand", "series", "model_year", "canonical_trim_key")
        if not _norm_text(record.get(name))
    ]
    if missing:
        return [f"VEHICLE_IDENTITY_INSUFFICIENT:{','.join(missing)}"]
    return []


def _source_reason_codes(price_role: str) -> list[str]:
    policy = PRICE_ROLE_POLICIES.get(price_role, PRICE_ROLE_POLICIES["UNKNOWN_OR_UNTRUSTED_PRICE"])
    if price_role == "UNKNOWN_OR_UNTRUSTED_PRICE":
        return ["UNKNOWN_OR_UNTRUSTED_PRICE_ROLE"]
    if not policy.allowed_for_c2b_point_baseline:
        return ["ROLE_NOT_DIRECT_C2B"]
    return []


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    records = []
    for row in result.to_dict("records"):
        records.append(
            canonicalize_trim(
                row.get("trim"),
                row.get("brand"),
                row.get("series"),
                row.get("model_year"),
                model_id=row.get("model_id"),
                energy_value=row.get("is_new_energy") or row.get("energy_type"),
            )
        )
    parsed = pd.DataFrame(records, index=result.index)
    for column in parsed.columns:
        if column not in result:
            result[column] = parsed[column]
        else:
            if parsed[column].dtype == "object":
                result[column] = result[column].astype("object")
            existing = result[column]
            missing = existing.isna() | existing.astype(str).str.strip().isin({"", "nan", "None"})
            result.loc[missing, column] = parsed.loc[missing, column]
    if "normalized_energy_type" not in result:
        energy_records = [
            normalize_energy_type(
                row.get("is_new_energy") or row.get("energy_type"),
                brand=row.get("brand"),
                series=row.get("series"),
                trim=row.get("trim"),
                is_new_energy=row.get("is_new_energy"),
            )
            for row in result.to_dict("records")
        ]
        energy = pd.DataFrame(energy_records, index=result.index)
        result["normalized_energy_type"] = energy["energy_type"]
    return result


def build_evidence_warehouse(frame: pd.DataFrame) -> pd.DataFrame:
    required = [
        "observation_id",
        "source_type",
        "price_type",
        "price",
        "event_time",
        "knowledge_available_at",
        "brand",
        "series",
        "model_year",
        "trim",
        "city",
        "color_raw",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "inspection_grade",
        "is_accident",
        "is_flood",
        "is_fire",
        "is_odometer_abnormal",
        "condition_risk_level",
        "vehicle_id_hash",
        "clue_id_hash",
        "listing_id",
        "source_url",
        "dedup_keep_flag",
        "candidate_clean_flag",
        "clean_for_memory_flag",
        "market_clean_flag",
        "is_token_price",
        "canonical_trim_key",
        "normalized_trim",
        "brand_key",
        "series_key",
        "model_year_key",
        "normalized_energy_type",
        "body_type",
        "canonicalization_confidence",
        "canonicalization_reason",
    ]
    data = frame.copy()
    for column in required:
        if column not in data:
            data[column] = np.nan
    data = _canonical_columns(data)

    roles = [
        normalize_price_role(row.get("source_type"), row.get("price_type"), row.get("source_url"))
        for row in data[["source_type", "price_type", "source_url"]].to_dict("records")
    ]
    data["price_role"] = roles
    policy_frame = price_role_definition_frame().set_index("price_role")
    for column in [
        "source_family",
        "allowed_for_c2b_point_baseline",
        "allowed_for_b2c_market_reference",
        "allowed_for_c2b_bridge_input",
        "allowed_for_interval",
        "allowed_for_explanation",
        "allowed_for_manual_reference",
        "default_price_quality",
    ]:
        data[column] = data["price_role"].map(policy_frame[column].to_dict())

    data["price_yuan"] = pd.to_numeric(data["price"], errors="coerce")
    data["event_time"] = pd.to_datetime(data["event_time"], errors="coerce")
    data["knowledge_available_at"] = pd.to_datetime(data["knowledge_available_at"], errors="coerce")
    data["age_years"] = pd.to_numeric(data["age_years"], errors="coerce")
    data["mileage_wan_km"] = pd.to_numeric(data["mileage_wan_km"], errors="coerce")
    data["transfer_count"] = pd.to_numeric(data["transfer_count"], errors="coerce")
    data["model_year"] = pd.to_numeric(data["model_year"], errors="coerce")

    conditions = pd.DataFrame([normalize_condition_record(row) for row in data.to_dict("records")], index=data.index)
    for column in conditions.columns:
        data[column] = conditions[column]

    reason_rows: list[str] = []
    quality_rows: list[str] = []
    for row in data.to_dict("records"):
        reasons: list[str] = []
        reasons.extend(_price_reason_codes(row.get("price_yuan")))
        reasons.extend(_event_reason_codes(row.get("event_time"), row.get("knowledge_available_at")))
        reasons.extend(_identity_reason_codes(row))
        if row.get("condition_risk_level_strict") == "major_risk":
            reasons.append("MAJOR_CONDITION_RISK")
        if str(row.get("dedup_keep_flag")).lower() in {"0", "false"}:
            reasons.append("DUPLICATE_NOT_PRIMARY")
        if str(row.get("candidate_clean_flag")).lower() in {"0", "false"}:
            reasons.append("SOURCE_CANDIDATE_CLEAN_FLAG_FALSE")
        if str(row.get("is_token_price")).lower() in {"1", "true"}:
            reasons.append("TOKEN_OR_PLACEHOLDER_PRICE")
        if row.get("price_role") == "UNKNOWN_OR_UNTRUSTED_PRICE":
            reasons.extend(_source_reason_codes(row.get("price_role")))
        unique_reasons = list(dict.fromkeys(reasons))
        reason_rows.append("|".join(unique_reasons))
        if any(code.startswith("PRICE") or code in {"TOKEN_OR_PLACEHOLDER_PRICE", "EVENT_TIME_INVALID"} for code in unique_reasons):
            quality = "quarantined_dirty"
        elif "MAJOR_CONDITION_RISK" in unique_reasons:
            quality = "separate_condition_risk"
        elif any(code.startswith("VEHICLE_IDENTITY") for code in unique_reasons):
            quality = "identity_insufficient"
        elif row.get("price_role") == "INTERNAL_C2B_PURCHASE_ACTUAL":
            quality = "strict_c2b_evidence"
        elif row.get("price_role") in {"INTERNAL_B2C_SOLD_ACTUAL", "EXTERNAL_B2C_LISTING"}:
            quality = "bridge_or_interval_evidence"
        else:
            quality = "manual_reference_only"
        quality_rows.append(quality)
    data["quality_reason_codes_v194"] = reason_rows
    data["evidence_quality_bucket"] = quality_rows

    data["allowed_for_c2b_point_baseline"] = (
        data["allowed_for_c2b_point_baseline"].fillna(False).astype(bool)
        & data["evidence_quality_bucket"].eq("strict_c2b_evidence")
    )
    data["allowed_for_b2c_market_reference"] = (
        data["allowed_for_b2c_market_reference"].fillna(False).astype(bool)
        & data["evidence_quality_bucket"].isin({"bridge_or_interval_evidence", "strict_c2b_evidence"})
    )
    data["allowed_for_c2b_bridge_input"] = (
        data["allowed_for_c2b_bridge_input"].fillna(False).astype(bool)
        & data["evidence_quality_bucket"].eq("bridge_or_interval_evidence")
    )
    data["allowed_for_interval"] = data["allowed_for_interval"].fillna(False).astype(bool) & ~data[
        "evidence_quality_bucket"
    ].eq("quarantined_dirty")
    data["allowed_for_explanation"] = data["allowed_for_explanation"].fillna(False).astype(bool) & ~data[
        "evidence_quality_bucket"
    ].eq("quarantined_dirty")
    data["allowed_for_manual_reference"] = data["allowed_for_manual_reference"].fillna(True).astype(bool)

    data["age_fine_value"] = data["age_years"].round(1)
    data["mileage_fine_value"] = (data["mileage_wan_km"] * 2).round() / 2
    data["transfer_fine_value"] = data["transfer_count"].round()
    data["city_key_v194"] = data["city"].map(_compact)
    data["color_key_v194"] = data["color_raw"].map(_compact)
    data["homogeneous_key_v194"] = (
        data["brand_key"].fillna("").astype(str)
        + "|"
        + data["series_key"].fillna("").astype(str)
        + "|"
        + data["model_year"].fillna(-1).astype(int).astype(str)
        + "|"
        + data["canonical_trim_key"].fillna("").astype(str)
        + "|age="
        + data["age_fine_value"].fillna(-1).astype(str)
        + "|mile="
        + data["mileage_fine_value"].fillna(-1).astype(str)
        + "|transfer="
        + data["transfer_fine_value"].fillna(-1).astype(str)
        + "|city="
        + data["city_key_v194"].fillna("").astype(str)
        + "|condition="
        + data["condition_risk_level_strict"].fillna("unknown").astype(str)
    )
    data["series_year_key_v194"] = (
        data["brand_key"].fillna("").astype(str)
        + "|"
        + data["series_key"].fillna("").astype(str)
        + "|"
        + data["model_year"].fillna(-1).astype(int).astype(str)
    )
    data["pricing_policy_version"] = PRICE_POLICY_VERSION
    return data


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return float("nan")
    values = values[mask]
    weights = weights[mask]
    sorter = np.argsort(values)
    values = values[sorter]
    weights = weights[sorter]
    cdf = np.cumsum(weights) - 0.5 * weights
    cdf = cdf / np.sum(weights)
    return float(np.interp(quantile, cdf, values))


def robust_price_cluster_summary(
    warehouse: pd.DataFrame,
    *,
    key_column: str = "homogeneous_key_v194",
    min_rows: int = 3,
) -> pd.DataFrame:
    eligible = warehouse[
        warehouse["allowed_for_c2b_point_baseline"].fillna(False)
        & warehouse["price_yuan"].notna()
        & warehouse["price_yuan"].gt(0)
    ].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                key_column,
                "rows",
                "main_cluster_rows",
                "median_price",
                "p20_price",
                "p40_price",
                "p60_price",
                "p80_price",
                "mad_log_price",
                "iqr_ratio",
                "trusted_cluster_flag",
                "cluster_policy_version",
            ]
        )
    eligible["log_price"] = np.log(eligible["price_yuan"])
    rows: list[dict[str, Any]] = []
    for key, group in eligible.groupby(key_column, dropna=False):
        prices = pd.to_numeric(group["price_yuan"], errors="coerce").dropna().to_numpy(dtype=float)
        logs = np.log(prices)
        if len(prices) == 0:
            continue
        med_log = float(np.median(logs))
        mad = float(np.median(np.abs(logs - med_log)))
        threshold = max(0.08, min(0.35, 3.5 * 1.4826 * mad)) if math.isfinite(mad) else 0.18
        main_mask = np.abs(logs - med_log) <= threshold
        main_prices = prices[main_mask] if main_mask.any() else prices
        q25 = float(np.quantile(main_prices, 0.25))
        q75 = float(np.quantile(main_prices, 0.75))
        median = float(np.median(main_prices))
        rows.append(
            {
                key_column: key,
                "rows": int(len(prices)),
                "main_cluster_rows": int(len(main_prices)),
                "outlier_rows": int(len(prices) - len(main_prices)),
                "median_price": median,
                "p20_price": float(np.quantile(main_prices, 0.20)),
                "p40_price": float(np.quantile(main_prices, 0.40)),
                "p60_price": float(np.quantile(main_prices, 0.60)),
                "p80_price": float(np.quantile(main_prices, 0.80)),
                "mad_log_price": mad,
                "iqr_ratio": float((q75 - q25) / median) if median else np.nan,
                "trusted_cluster_flag": int(len(main_prices) >= min_rows and ((q75 - q25) / median if median else 99) <= 0.22),
                "cluster_policy_version": "v194_robust_main_cluster_mad_iqr_v1",
            }
        )
    return pd.DataFrame(rows)
