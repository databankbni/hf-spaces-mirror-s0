from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_6_business import (
    V1926ServingQuoteService,
    add_candidate_price_roles,
)


COUNTERFACTUAL_SCENARIOS = (
    "AGE_PLUS_1Y",
    "MILEAGE_PLUS_1W",
    "MILEAGE_PLUS_5W",
    "TRANSFER_PLUS_1",
    "CONDITION_GOOD_TO_MINOR_DEFECT",
)


@dataclass
class V1927ServingQuoteService(V1926ServingQuoteService):
    entrypoint_name: str = "V1927ServingQuoteService.quote"


def apply_b2c_conversion_guard(
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = candidates.copy()
    original = pd.to_numeric(result["candidate_price"], errors="coerce")
    converted = pd.to_numeric(
        result["adjusted_candidate_price"], errors="coerce"
    )
    b2c = result["cluster_price_type"].isin(
        ["B2C", "EXT_B2C_LISTING"]
    )
    raw_ratio = converted / original.replace(0, np.nan)
    above_one = b2c & raw_ratio.gt(1.0)
    result["conversion_ratio_raw_v192_7"] = raw_ratio
    result["conversion_ratio_guard_reason_v192_7"] = np.where(
        above_one,
        "CONVERSION_RATIO_CLIPPED_TO_ONE",
        "",
    )
    result["conversion_ratio_retained_above_one_v192_7"] = 0
    result.loc[above_one, "adjusted_candidate_price"] = original[above_one]
    result["conversion_ratio_final_v192_7"] = (
        pd.to_numeric(
            result["adjusted_candidate_price"], errors="coerce"
        )
        / original.replace(0, np.nan)
    )
    result["conversion_guard_applied_v192_7"] = above_one.astype(int)
    result["conversion_weight_multiplier_v192_7"] = np.where(
        above_one, 0.85, 1.0
    )
    result["source_quality"] = (
        pd.to_numeric(result["source_quality"], errors="coerce").fillna(0)
        * result["conversion_weight_multiplier_v192_7"]
    )
    audit = pd.DataFrame(
        {
            "query_id": result["query_id"],
            "candidate_id": result["candidate_id"],
            "source_family": result["source_family"],
            "cluster_price_type": result["cluster_price_type"],
            "original_b2c_price": original,
            "raw_c2b_equivalent_price": converted,
            "raw_conversion_ratio": raw_ratio,
            "final_c2b_equivalent_price": pd.to_numeric(
                result["adjusted_candidate_price"], errors="coerce"
            ),
            "final_conversion_ratio": result[
                "conversion_ratio_final_v192_7"
            ],
            "conversion_guard_applied": above_one.astype(int),
            "retained_above_one_with_downweight": 0,
            "weight_multiplier": result[
                "conversion_weight_multiplier_v192_7"
            ],
            "reason_code": result[
                "conversion_ratio_guard_reason_v192_7"
            ],
        }
    )
    return result, audit


def add_v192_7_candidate_price_roles(
    selected: pd.DataFrame,
) -> pd.DataFrame:
    result = add_candidate_price_roles(selected)
    result["conversion_ratio_raw_v192_7"] = pd.to_numeric(
        result.get(
            "conversion_ratio_raw_v192_7",
            result["conversion_ratio_v192_6"],
        ),
        errors="coerce",
    )
    result["conversion_ratio_final_v192_7"] = pd.to_numeric(
        result.get(
            "conversion_ratio_final_v192_7",
            result["conversion_ratio_v192_6"],
        ),
        errors="coerce",
    )
    result["conversion_guard_applied_v192_7"] = pd.to_numeric(
        result.get("conversion_guard_applied_v192_7", 0),
        errors="coerce",
    ).fillna(0).astype(int)
    result["conversion_warning_reason_v192_7"] = result.get(
        "conversion_ratio_guard_reason_v192_7", ""
    )
    result["conversion_ratio_v192_6"] = result[
        "conversion_ratio_final_v192_7"
    ]
    result["converted_c2b_equivalent_price_v192_6"] = pd.to_numeric(
        result["adjusted_candidate_price"], errors="coerce"
    )
    result["final_price_used_v192_6"] = result[
        "converted_c2b_equivalent_price_v192_6"
    ]
    return result


def counterfactual_vehicle_state(
    original: dict[str, Any], scenario: str
) -> dict[str, Any]:
    result = {
        "age_years": original.get("age_years"),
        "mileage_wan_km": original.get("mileage_wan_km"),
        "transfer_count": original.get("transfer_count"),
        "condition_risk_level": original.get(
            "condition_risk_level", "unknown"
        ),
    }
    if scenario == "AGE_PLUS_1Y":
        result["age_years"] = float(result["age_years"] or 0) + 1
    elif scenario == "MILEAGE_PLUS_1W":
        result["mileage_wan_km"] = (
            float(result["mileage_wan_km"] or 0) + 1
        )
    elif scenario == "MILEAGE_PLUS_5W":
        result["mileage_wan_km"] = (
            float(result["mileage_wan_km"] or 0) + 5
        )
    elif scenario == "TRANSFER_PLUS_1":
        result["transfer_count"] = (
            float(result["transfer_count"] or 0) + 1
        )
    elif scenario == "CONDITION_GOOD_TO_MINOR_DEFECT":
        result["condition_risk_level"] = "minor_defect"
    return result


def raw_direction_violation(
    scenario: str,
    original_price: Any,
    counterfactual_price: Any,
) -> bool:
    if pd.isna(original_price) or pd.isna(counterfactual_price):
        return False
    deterioration = scenario in COUNTERFACTUAL_SCENARIOS
    return bool(
        deterioration
        and float(counterfactual_price) > float(original_price) + 1e-9
    )


def build_residual_business_explanation(
    trace: pd.DataFrame,
    selected: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    selected_map = {
        query_id: group
        for query_id, group in selected.groupby("query_id", sort=False)
    }
    factors = (
        "age",
        "mileage",
        "transfer",
        "condition",
        "city",
        "freshness",
        "dispersion",
    )
    for quote in trace.to_dict("records"):
        group = selected_map.get(quote["query_id"], pd.DataFrame())
        weights = pd.to_numeric(
            group.get(
                "final_normalized_weight_v192_4",
                pd.Series(dtype=float),
            ),
            errors="coerce",
        ).fillna(0)
        direction = (
            "UP"
            if float(quote.get("base_residual_clipped_adjustment") or 0)
            > 1e-12
            else "DOWN"
            if float(quote.get("base_residual_clipped_adjustment") or 0)
            < -1e-12
            else "FLAT"
        )

        def weighted_numeric(column: str) -> float | None:
            if group.empty or column not in group or weights.sum() <= 0:
                return None
            values = pd.to_numeric(group[column], errors="coerce")
            valid = values.notna() & weights.gt(0)
            if not valid.any():
                return None
            return float(np.average(values[valid], weights=weights[valid]))

        comparable = {
            "age": weighted_numeric("age_years"),
            "mileage": weighted_numeric("mileage_wan_km"),
            "transfer": weighted_numeric("transfer_count"),
            "condition": (
                float(
                    weights[
                        group["condition_match"].eq(1)
                    ].sum()
                )
                if not group.empty
                else None
            ),
            "city": (
                float(weights[group["city_match"].eq(1)].sum())
                if not group.empty
                else None
            ),
            "freshness": weighted_numeric("days_since_transaction"),
            "dispersion": quote.get("candidate_dispersion"),
        }
        target = {
            "age": quote.get("age_years"),
            "mileage": quote.get("mileage_wan_km"),
            "transfer": quote.get("transfer_count"),
            "condition": quote.get("condition_risk_level"),
            "city": quote.get("city"),
            "freshness": 0.0,
            "dispersion": 0.0,
        }
        for factor in factors:
            target_value = target[factor]
            comparable_value = comparable[factor]
            difference: Any = None
            if factor in {"age", "mileage", "transfer", "freshness", "dispersion"}:
                if pd.notna(target_value) and pd.notna(comparable_value):
                    difference = float(target_value) - float(comparable_value)
            elif factor in {"condition", "city"}:
                difference = (
                    None
                    if comparable_value is None
                    else 1.0 - float(comparable_value)
                )
            confidence = (
                "HIGH"
                if len(group) >= 8 and comparable_value is not None
                else "MEDIUM"
                if len(group) >= 5 and comparable_value is not None
                else "LOW"
            )
            reason = _factor_reason(
                factor,
                target_value,
                comparable_value,
                difference,
                direction,
            )
            rows.append(
                {
                    "query_id": quote["query_id"],
                    "factor": factor,
                    "target_value": target_value,
                    "comparable_weighted_value": comparable_value,
                    "difference": difference,
                    "model_direction": direction,
                    "business_reason": reason,
                    "reason_confidence": confidence,
                    "is_actual_model_adjustment_explanation": 1,
                    "is_counterfactual_sensitivity": 0,
                }
            )
    return pd.DataFrame(rows)


def _factor_reason(
    factor: str,
    target: Any,
    comparable: Any,
    difference: Any,
    direction: str,
) -> str:
    direction_text = {
        "UP": "上调",
        "DOWN": "下调",
        "FLAT": "基本不调整",
    }[direction]
    if comparable is None or pd.isna(comparable):
        return f"{factor}缺少可靠加权可比值，本项不单独归因；模型净方向为{direction_text}。"
    if factor == "age":
        return (
            f"目标车龄{float(target):.1f}年，可比车加权均值"
            f"{float(comparable):.1f}年，差{float(difference):+.1f}年；"
            f"模型净方向为{direction_text}。"
        )
    if factor == "mileage":
        return (
            f"目标里程{float(target):.1f}万公里，可比车加权均值"
            f"{float(comparable):.1f}万公里，差{float(difference):+.1f}万公里；"
            f"模型净方向为{direction_text}。"
        )
    if factor == "transfer":
        return (
            f"目标过户{float(target):.0f}次，可比车加权均值"
            f"{float(comparable):.1f}次，差{float(difference):+.1f}次；"
            f"模型净方向为{direction_text}。"
        )
    if factor == "condition":
        return (
            f"目标车况为{target}，最终可比车车况匹配权重"
            f"{float(comparable):.1%}；模型净方向为{direction_text}。"
        )
    if factor == "city":
        return (
            f"目标城市为{target}，最终可比车同城权重"
            f"{float(comparable):.1%}；模型净方向为{direction_text}。"
        )
    if factor == "freshness":
        return (
            f"最终可比车距报价日加权平均{float(comparable):.0f}天；"
            f"模型净方向为{direction_text}。"
        )
    return (
        f"候选价格离散度为{float(comparable):.1%}；"
        f"模型净方向为{direction_text}。"
    )
