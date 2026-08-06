from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

try:
    from usedcar_pricing.v192_7_business import V1927ServingQuoteService
except ModuleNotFoundError:
    from src.usedcar_pricing.v192_7_business import (
        V1927ServingQuoteService,
    )


def _year(value: Any) -> int | None:
    text = str(value or "")
    for token in text.replace("/", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


def _current_vehicle_state(payload: dict[str, Any]) -> dict[str, Any]:
    registration_year = _year(
        payload.get("regDate") or payload.get("reg_date")
    )
    age = (
        max(datetime.now().year - registration_year, 0)
        if registration_year
        else payload.get("age_years")
    )
    return {
        "age_years": age,
        "mileage_wan_km": payload.get("mileage"),
        "transfer_count": payload.get(
            "transferCount", payload.get("transfer")
        ),
        "condition_risk_level": payload.get(
            "condition_risk_level", payload.get("condition", "unknown")
        ),
    }


def quote_with_v1927_service(
    payload: dict[str, Any],
    pricing_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    result = pricing_callable(payload)
    raw_price_wan = result.get("c2bPrice")
    raw_price = (
        float(raw_price_wan) * 10000
        if raw_price_wan is not None
        else None
    )
    previous = payload.get("previous_quote") or {}
    previous_price = previous.get("final_price")
    if previous_price is None and previous.get("c2bPrice") is not None:
        previous_price = float(previous["c2bPrice"]) * 10000
    service = V1927ServingQuoteService()
    served = service.quote(
        raw_price=raw_price,
        raw_confidence=str(
            result.get("quote_evidence_confidence")
            or result.get("confidence")
            or "LOW"
        ).upper(),
        previous_price=previous_price,
        previous_confidence=previous.get("confidence"),
        previous_vehicle_state=payload.get("previous_vehicle_state"),
        current_vehicle_state=payload.get(
            "current_vehicle_state", _current_vehicle_state(payload)
        ),
        previous_evidence_state=payload.get("previous_evidence_state"),
        current_evidence_state=payload.get("current_evidence_state"),
    )
    final_price = served["final_price_after_guard"]
    if final_price is not None:
        result["c2bPrice"] = round(float(final_price) / 10000, 2)
    result["v1927Serving"] = {
        "raw_price_before_guard": raw_price,
        "final_price_after_guard": final_price,
        "guard_triggered": bool(served["guard_triggered"]),
        "guard_adjustment_amount": served["guard_adjustment_amount"],
        "guard_rule_codes": served["guard_rule_codes"],
        "change_flags_source": served["change_flags_source"],
        "age_increased": bool(served["age_increased"]),
        "mileage_increased": bool(served["mileage_increased"]),
        "transfer_increased": bool(served["transfer_increased"]),
        "condition_worsened": bool(served["condition_worsened"]),
        "evidence_weakened": bool(served["evidence_weakened"]),
        "serving_entrypoint": served["serving_entrypoint"],
    }
    return result
