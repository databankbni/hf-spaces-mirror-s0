"""Deterministic weighted price-ladder projection for v195."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np


ORDERED_FIELDS = [
    "recommended_listing_price_high",
    "recommended_listing_price",
    "recommended_listing_price_low",
    "expected_b2c_transaction_price_high",
    "expected_b2c_transaction_price",
    "expected_b2c_transaction_price_low",
    "max_c2b_acquisition_price",
    "expected_final_c2b_price_high",
    "expected_final_c2b_price",
    "recommended_acquisition_price",
    "expected_final_c2b_price_low",
    "recommended_first_offer",
]


DEFAULT_WEIGHTS = {
    "recommended_listing_price_high": 2.5,
    "recommended_listing_price": 3.0,
    "recommended_listing_price_low": 3.0,
    "expected_b2c_transaction_price_high": 7.0,
    "expected_b2c_transaction_price": 10.0,
    "expected_b2c_transaction_price_low": 7.0,
    "max_c2b_acquisition_price": 6.0,
    "expected_final_c2b_price_high": 7.0,
    "expected_final_c2b_price": 10.0,
    "recommended_acquisition_price": 6.0,
    "expected_final_c2b_price_low": 7.0,
    "recommended_first_offer": 3.0,
}


@dataclass(frozen=True)
class BusinessCostInputs:
    refurbishment_cost: float
    inspection_and_logistics_cost: float
    capital_cost: float
    selling_cost: float
    risk_reserve: float
    minimum_gross_profit: float
    unscaled_total: float
    observed_spread_budget: float | None
    calibration_scale: float

    @property
    def total(self) -> float:
        return float(
            self.refurbishment_cost
            + self.inspection_and_logistics_cost
            + self.capital_cost
            + self.selling_cost
            + self.risk_reserve
            + self.minimum_gross_profit
        )


@dataclass(frozen=True)
class ProjectionResult:
    raw_prices: dict[str, float]
    projected_prices: dict[str, float]
    adjustment_amount: dict[str, float]
    constraint_triggered: bool
    constraint_reason: list[str]
    projection_version: str
    weighted_squared_adjustment: float


def load_ladder_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def price_band(price: float) -> str:
    if price <= 30_000:
        return "LE_30K"
    if price <= 50_000:
        return "30_50K"
    if price <= 80_000:
        return "50_80K"
    if price <= 120_000:
        return "80_120K"
    if price <= 200_000:
        return "120_200K"
    return "GT_200K"


def business_cost_inputs(
    expected_b2c_price: float,
    *,
    condition_grade: str,
    confidence: str,
    config: dict[str, Any],
    overrides: dict[str, float] | None = None,
) -> BusinessCostInputs:
    overrides = overrides or {}
    condition = str(condition_grade or "UNKNOWN").upper()
    if condition not in config["refurbishment_cost_by_condition"]:
        condition = "UNKNOWN"
    confidence_key = str(confidence or "LOW").upper()
    if confidence_key not in config["risk_reserve_ratio_by_confidence"]:
        confidence_key = "LOW"
    turnover_days = float(overrides.get("target_turnover_days", config["target_turnover_days"]))
    capital_rate = float(overrides.get("capital_annual_rate", config["capital_annual_rate"]))
    gross_ratio = float(
        overrides.get(
            "minimum_gross_profit_ratio",
            config["minimum_gross_profit_ratio_by_price_band"][price_band(expected_b2c_price)],
        )
    )
    minimum_gross_profit = max(
        float(config["minimum_gross_profit_floor"]), expected_b2c_price * gross_ratio
    )
    components = {
        "refurbishment_cost": float(
            overrides.get(
                "refurbishment_cost",
                config["refurbishment_cost_by_condition"][condition],
            )
        ),
        "inspection_and_logistics_cost": float(
            overrides.get(
                "inspection_and_logistics_cost",
                config["inspection_and_logistics_cost"],
            )
        ),
        "capital_cost": float(
            overrides.get(
                "capital_cost",
                expected_b2c_price * capital_rate * turnover_days / 365.0,
            )
        ),
        "selling_cost": float(
            overrides.get(
                "selling_cost", expected_b2c_price * float(config["selling_cost_ratio"])
            )
        ),
        "risk_reserve": float(
            overrides.get(
                "risk_reserve",
                expected_b2c_price
                * float(config["risk_reserve_ratio_by_confidence"][confidence_key]),
            )
        ),
        "minimum_gross_profit": float(
            overrides.get("minimum_gross_profit", minimum_gross_profit)
        ),
    }
    unscaled_total = float(sum(components.values()))
    budget: float | None = None
    scale = 1.0
    spread_calibration = config.get("observed_spread_budget")
    if not overrides and spread_calibration:
        band = price_band(expected_b2c_price)
        band_values = spread_calibration["price_bands"].get(band)
        if band_values:
            budget = max(
                expected_b2c_price * float(band_values["spread_ratio_q25"]),
                float(band_values["spread_yuan_q25"]),
            )
            if unscaled_total > 0:
                scale = min(1.0, budget / unscaled_total)
                components = {key: value * scale for key, value in components.items()}
    return BusinessCostInputs(
        **components,
        unscaled_total=unscaled_total,
        observed_spread_budget=budget,
        calibration_scale=scale,
    )


def _weighted_pava_nonincreasing(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    blocks: list[dict[str, float | int]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        blocks.append(
            {
                "start": index,
                "end": index,
                "weight": float(weight),
                "mean": float(value),
            }
        )
        while len(blocks) >= 2 and float(blocks[-2]["mean"]) < float(blocks[-1]["mean"]):
            right = blocks.pop()
            left = blocks.pop()
            total_weight = float(left["weight"]) + float(right["weight"])
            mean = (
                float(left["mean"]) * float(left["weight"])
                + float(right["mean"]) * float(right["weight"])
            ) / total_weight
            blocks.append(
                {
                    "start": int(left["start"]),
                    "end": int(right["end"]),
                    "weight": total_weight,
                    "mean": mean,
                }
            )
    output = np.empty_like(values, dtype=float)
    for block in blocks:
        output[int(block["start"]) : int(block["end"]) + 1] = float(block["mean"])
    return output


class PriceHierarchyProjector:
    def __init__(
        self,
        *,
        minimum_b2c_to_max_c2b_gap: float = 100.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.minimum_b2c_to_max_c2b_gap = float(minimum_b2c_to_max_c2b_gap)
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.version = "v195_weighted_pava_price_hierarchy_v1"

    def project(self, raw_prices: dict[str, float]) -> ProjectionResult:
        missing = [field for field in ORDERED_FIELDS if field not in raw_prices]
        if missing:
            raise ValueError(f"Missing hierarchy fields: {missing}")
        values = np.asarray([float(raw_prices[field]) for field in ORDERED_FIELDS], dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Every raw hierarchy price must be positive and finite")
        weights = np.asarray([float(self.weights[field]) for field in ORDERED_FIELDS], dtype=float)
        gaps = np.zeros(len(values) - 1, dtype=float)
        b2c_low_index = ORDERED_FIELDS.index("expected_b2c_transaction_price_low")
        gaps[b2c_low_index] = self.minimum_b2c_to_max_c2b_gap
        offsets = np.concatenate([[0.0], np.cumsum(gaps)])
        transformed = values + offsets
        projected_transformed = _weighted_pava_nonincreasing(transformed, weights)
        projected = projected_transformed - offsets
        projected_map = {
            field: float(value) for field, value in zip(ORDERED_FIELDS, projected)
        }
        adjustment = {
            field: projected_map[field] - float(raw_prices[field])
            for field in ORDERED_FIELDS
        }
        reasons = []
        for index, gap in enumerate(gaps):
            if values[index] < values[index + 1] + gap - 1e-9:
                reasons.append(
                    f"{ORDERED_FIELDS[index]} >= {ORDERED_FIELDS[index + 1]} + {gap:.2f}"
                )
        objective = float(
            sum(
                self.weights[field] * adjustment[field] ** 2
                for field in ORDERED_FIELDS
            )
        )
        return ProjectionResult(
            raw_prices={field: float(raw_prices[field]) for field in ORDERED_FIELDS},
            projected_prices=projected_map,
            adjustment_amount=adjustment,
            constraint_triggered=bool(reasons),
            constraint_reason=reasons,
            projection_version=self.version,
            weighted_squared_adjustment=objective,
        )


def hierarchy_violations(prices: dict[str, float], minimum_gap: float = 100.0) -> list[str]:
    values = [float(prices[field]) for field in ORDERED_FIELDS]
    violations: list[str] = []
    for index in range(len(values) - 1):
        gap = (
            minimum_gap
            if ORDERED_FIELDS[index] == "expected_b2c_transaction_price_low"
            else 0.0
        )
        if values[index] < values[index + 1] + gap - 1e-6:
            violations.append(f"{ORDERED_FIELDS[index]}<{ORDERED_FIELDS[index + 1]}+{gap}")
    return violations


def cost_inputs_dict(costs: BusinessCostInputs) -> dict[str, float]:
    return {**asdict(costs), "total": costs.total}
