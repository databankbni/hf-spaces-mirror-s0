"""Six-price raw generator plus v195 hierarchy projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .v195_price_ladder_solver import (
    PriceHierarchyProjector,
    business_cost_inputs,
    cost_inputs_dict,
)


@dataclass(frozen=True)
class RawPricingInputs:
    expected_b2c_transaction_price: float
    expected_final_c2b_price: float
    external_listing_anchor: float | None
    external_listing_dispersion: float | None
    condition_grade: str
    confidence: str
    b2c_interval_half_width_ratio: float | None = None
    c2b_interval_half_width_ratio: float | None = None
    business_cost_overrides: dict[str, float] | None = None


class V195ProductionPricingEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.projector = PriceHierarchyProjector(
            minimum_b2c_to_max_c2b_gap=float(
                config["minimum_b2c_to_max_c2b_gap"]
            )
        )
        self.version = "v195_production_six_price_engine_v1"

    def quote(self, inputs: RawPricingInputs) -> dict[str, Any]:
        original_b2c = float(inputs.expected_b2c_transaction_price)
        requested_final_c2b = float(inputs.expected_final_c2b_price)
        interval = self.config["interval_calibration"]
        b2c_half = float(
            inputs.b2c_interval_half_width_ratio
            if inputs.b2c_interval_half_width_ratio is not None
            else interval["b2c_half_width_ratio"]
        )
        c2b_half = float(
            inputs.c2b_interval_half_width_ratio
            if inputs.c2b_interval_half_width_ratio is not None
            else interval["c2b_half_width_ratio"]
        )
        minimum_gap = float(self.config["minimum_b2c_to_max_c2b_gap"])
        repaired_b2c = original_b2c
        costs = business_cost_inputs(
            repaired_b2c,
            condition_grade=inputs.condition_grade,
            confidence=inputs.confidence,
            config=self.config,
            overrides=inputs.business_cost_overrides,
        )
        # B2C is the market transaction estimate and must not be raised merely
        # to make an overly high acquisition price look profitable.  Keep the
        # market anchor fixed and cap C2B at the profitable business ceiling.
        b2c_low = repaired_b2c * (1.0 - b2c_half)
        profitable_c2b_ceiling = max(
            3_000.0,
            min(repaired_b2c - costs.total, b2c_low - minimum_gap),
        )
        final_c2b = min(requested_final_c2b, profitable_c2b_ceiling)
        c2b_profitability_clamp_used = final_c2b < requested_final_c2b - 1e-9
        b2c_anchor_repair_used = False
        listing_half = float(
            np.clip(
                inputs.external_listing_dispersion / 2.0
                if inputs.external_listing_dispersion is not None
                and np.isfinite(inputs.external_listing_dispersion)
                else interval["listing_min_half_width_ratio"],
                interval["listing_min_half_width_ratio"],
                interval["listing_max_half_width_ratio"],
            )
        )
        strategy_listing = max(
            repaired_b2c * (1.0 + float(self.config["listing_negotiation_ratio"])),
            repaired_b2c * (1.0 + b2c_half) / (1.0 - listing_half),
        )
        external = (
            float(inputs.external_listing_anchor)
            if inputs.external_listing_anchor is not None
            and np.isfinite(inputs.external_listing_anchor)
            and inputs.external_listing_anchor > 0
            else 0.0
        )
        listing_point = max(strategy_listing, external)
        max_c2b = profitable_c2b_ceiling
        final_c2b_high = min(final_c2b * (1.0 + c2b_half), max_c2b)
        suggested_acquisition = final_c2b
        first_offer = min(
            final_c2b * (1.0 - float(self.config["first_offer_negotiation_ratio"])),
            final_c2b * (1.0 - c2b_half),
        )
        raw = {
            "recommended_listing_price_high": listing_point * (1.0 + listing_half),
            "recommended_listing_price": listing_point,
            "recommended_listing_price_low": listing_point * (1.0 - listing_half),
            "expected_b2c_transaction_price_high": repaired_b2c * (1.0 + b2c_half),
            "expected_b2c_transaction_price": repaired_b2c,
            "expected_b2c_transaction_price_low": b2c_low,
            "max_c2b_acquisition_price": max_c2b,
            "expected_final_c2b_price_high": final_c2b_high,
            "expected_final_c2b_price": final_c2b,
            "recommended_acquisition_price": suggested_acquisition,
            "expected_final_c2b_price_low": final_c2b * (1.0 - c2b_half),
            "recommended_first_offer": first_offer,
        }
        projection = self.projector.project(raw)
        prices = projection.projected_prices
        return {
            "engine_version": self.version,
            **prices,
            "cost_inputs": cost_inputs_dict(costs),
            "original_b2c_anchor": original_b2c,
            "b2c_repaired_anchor": repaired_b2c,
            "b2c_anchor_repair_used": b2c_anchor_repair_used,
            "b2c_anchor_repair_reason": (
                "B2C_MARKET_ANCHOR_FIXED_C2B_CLAMPED"
                if c2b_profitability_clamp_used
                else "B2C_ANCHOR_ACCEPTED"
            ),
            "requested_final_c2b_price": requested_final_c2b,
            "profitable_c2b_ceiling": profitable_c2b_ceiling,
            "c2b_profitability_clamp_used": c2b_profitability_clamp_used,
            "raw_prices": projection.raw_prices,
            "projected_prices": projection.projected_prices,
            "adjustment_amount": projection.adjustment_amount,
            "constraint_triggered": projection.constraint_triggered,
            "constraint_reason": projection.constraint_reason,
            "projection_version": projection.projection_version,
            "weighted_squared_adjustment": projection.weighted_squared_adjustment,
            "inputs": asdict(inputs),
        }
