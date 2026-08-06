#!/usr/bin/env python3
"""Replay baseline, model adjustment, final point and interval from a ledger."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .price_explanation_schema import PriceExplanationLedger


def replay_price(ledger: PriceExplanationLedger | dict[str, Any]) -> dict[str, Any]:
    value = ledger.to_dict() if isinstance(ledger, PriceExplanationLedger) else ledger
    statistical = value["statistical_price"]
    method = statistical.get("calculation_method")
    trace = statistical.get("calculation_trace") or {}

    if method == "HIGHEST_QUALITY_CANDIDATE_WINNER_TAKES_ALL":
        selected = value.get("selected_comparables") or []
        baseline = (
            sum(float(item["adjusted_candidate_price"]) * float(item["normalized_final_weight"]) for item in selected)
            if selected
            else None
        )
    elif method == "MULTI_STAGE_ROBUST_LOG_BLEND_WITH_ECONOMIC_GUARD":
        reference = trace.get("stored_c2b_market_reference_price")
        ceiling = trace.get("fast_sale_zero_cost_ceiling")
        available = [float(item) for item in (reference, ceiling) if item is not None]
        baseline = min(available) if available else None
    else:
        baseline = statistical.get("baseline_price")

    adjustment = float(value["model_adjustment"].get("final_adjustment_amount") or 0.0)
    final_price = None if baseline is None else float(baseline) + adjustment
    interval = value["interval"]
    serving = value["final_price"].get("final_point_price")
    difference = None if serving is None or final_price is None else final_price - float(serving)
    return {
        "quote_id": value.get("quote_id"),
        "calculation_method": method,
        "recomputed_statistical_baseline_price": baseline,
        "recomputed_model_adjustment_amount": adjustment,
        "recomputed_final_price": final_price,
        "serving_final_price": serving,
        "difference_from_serving_price": difference,
        "recomputed_interval_low": interval.get("price_low"),
        "recomputed_interval_high": interval.get("price_high"),
        "reconciliation_passed": difference is None or math.isclose(difference, 0.0, abs_tol=1.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-json", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.ledger_json.read_text(encoding="utf-8"))
    print(json.dumps(replay_price(value), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
