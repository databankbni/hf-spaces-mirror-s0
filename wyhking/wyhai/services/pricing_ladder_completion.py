"""Complete legacy two-point quotes into one auditable business price ladder.

This module does not invent a new market anchor.  It only takes an upstream
B2C and C2B point that already exists and adds the listing strategy, ranges,
full cost/profit ceiling and ordering required by the frontline product.
Market accuracy remains the responsibility of the identity appraiser/price
book and is explicitly marked as unreviewed when this compatibility path runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from usedcar_pricing.v195_production_pricing_engine import (
    RawPricingInputs,
    V195ProductionPricingEngine,
)


ROOT = Path(__file__).resolve().parents[1]
_ENGINE = V195ProductionPricingEngine(
    json.loads((ROOT / "config/v195_price_ladder.json").read_text(encoding="utf-8"))
)


def _positive(value: Any, *, value_is_wan: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number > 0):
        return None
    return number * 10_000.0 if value_is_wan else number


def _first_price(*candidates: tuple[Any, bool]) -> float | None:
    for value, value_is_wan in candidates:
        parsed = _positive(value, value_is_wan=value_is_wan)
        if parsed is not None:
            return parsed
    return None


def _complete_ladder_from_engine(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommended_listing_yuan": output["recommended_listing_price"],
        "recommended_listing_range_yuan": [
            output["recommended_listing_price_low"],
            output["recommended_listing_price_high"],
        ],
        "expected_b2c_transaction_yuan": output["expected_b2c_transaction_price"],
        "b2c_transaction_range_yuan": [
            output["expected_b2c_transaction_price_low"],
            output["expected_b2c_transaction_price_high"],
        ],
        "expected_c2b_yuan": output["expected_final_c2b_price"],
        "c2b_range_yuan": [
            output["expected_final_c2b_price_low"],
            output["expected_final_c2b_price_high"],
        ],
        "first_c2b_offer_yuan": output["recommended_first_offer"],
        "max_c2b_yuan": output["max_c2b_acquisition_price"],
    }


def complete_legacy_business_ladder(
    price_result: dict[str, Any],
    *,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the quote with a complete ladder when both legacy points exist."""

    if not isinstance(price_result, dict) or not price_result:
        return price_result
    decision = str(price_result.get("quote_decision") or "").strip().upper()
    if price_result.get("success") is False or decision in {"NO_QUOTE", "NO_DEAL"}:
        return price_result

    existing = price_result.get("price_ladder")
    required = {
        "recommended_listing_yuan",
        "recommended_listing_range_yuan",
        "expected_b2c_transaction_yuan",
        "b2c_transaction_range_yuan",
        "expected_c2b_yuan",
        "c2b_range_yuan",
        "first_c2b_offer_yuan",
        "max_c2b_yuan",
    }
    if isinstance(existing, dict) and required.issubset(existing):
        return price_result

    nested = price_result.get("price_result") or {}
    b2c = _first_price(
        ((existing or {}).get("expected_b2c_transaction_yuan"), False),
        (price_result.get("b2cPrice"), True),
        (price_result.get("b2c_price"), True),
        (price_result.get("targetB2C"), True),
        (price_result.get("sale_price"), True),
    )
    c2b = _first_price(
        ((existing or {}).get("expected_c2b_yuan"), False),
        (price_result.get("c2bPrice"), True),
        (price_result.get("c2b_price"), True),
        (price_result.get("targetC2B"), True),
        (price_result.get("purchase_price"), True),
    )
    if b2c is None or c2b is None:
        return price_result

    slots = slots or {}
    condition = str(
        slots.get("condition_group")
        or slots.get("condition_grade")
        or slots.get("inspection_grade")
        or "UNKNOWN"
    ).upper()
    confidence = str(
        price_result.get("confidence")
        or nested.get("confidence")
        or "LOW"
    ).upper()
    external_listing = _first_price(
        (price_result.get("recommended_listing_price_yuan"), False),
        ((existing or {}).get("recommended_listing_yuan"), False),
    )
    engine_output = _ENGINE.quote(
        RawPricingInputs(
            expected_b2c_transaction_price=b2c,
            expected_final_c2b_price=c2b,
            external_listing_anchor=external_listing,
            external_listing_dispersion=None,
            condition_grade=condition,
            confidence=confidence,
        )
    )
    result = dict(price_result)
    ladder = _complete_ladder_from_engine(engine_output)
    result.update(
        {
            "price_ladder": ladder,
            "recommended_listing_price_yuan": ladder["recommended_listing_yuan"],
            "recommended_listing_range_yuan": ladder["recommended_listing_range_yuan"],
            "first_c2b_offer_yuan": ladder["first_c2b_offer_yuan"],
            "max_c2b_price_yuan": ladder["max_c2b_yuan"],
            "legacy_ladder_completion_used": True,
            "legacy_ladder_completion_version": "v195_structural_ladder_completion_v1",
            "market_accuracy_reviewed_by_completion": False,
            "business_cost_inputs": engine_output["cost_inputs"],
            "profitable_c2b_ceiling_yuan": engine_output["profitable_c2b_ceiling"],
        }
    )
    return result
