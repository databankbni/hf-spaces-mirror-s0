from __future__ import annotations

from typing import Any, Dict


SUPPORTED_MODULES = {"daily_report", "market_state", "media_pricing"}

BUSINESS_CATEGORIES = {
    "DAILY_REPORT",
    "MARKET_STATE",
    "MEDIA_VALUATION",
    "PARAM_ADJUSTMENT",
    "PRICING_QA",
    "GENERAL_AUTOMOTIVE_QA",
    "CROSS_MODULE_SWITCH",
    "RESET_CONTEXT",
    "FALLBACK",
    "UNKNOWN_OR_INCOMPLETE",
}

INTERNAL_INTENTS = {
    "DAILY_REPORT_READ",
    "DAILY_REPORT_HISTORY",
    "DAILY_REPORT_SECTION_QUERY",
    "DAILY_REPORT_DETAIL_QUESTION",
    "DAILY_REPORT_POLICY_QUERY",
    "DAILY_REPORT_DISCOUNT_QUERY",
    "DAILY_REPORT_NEWS_QUERY",
    "DAILY_REPORT_DATA_SCOPE_QUERY",
    "DAILY_REPORT_DATE_QUERY",
    "MARKET_STATE_QUERY",
    "MARKET_OPPORTUNITY_RECOMMEND",
    "MARKET_RISK_QUERY",
    "MARKET_CITY_CHANGE",
    "MARKET_SERIES_QUERY",
    "MARKET_PRICE_BUCKET_QUERY",
    "MARKET_INVENTORY_QUERY",
    "MARKET_REASON_QUERY",
    "MARKET_DATA_SCOPE_QUERY",
    "MARKET_SERIES_COMPARE",
    "MARKET_REPORT_QUERY",
    "PURCHASE_PRICE_JUDGEMENT",
    "SALE_PRICE_ADVICE",
    "BOTH_PRICE_ADVICE",
    "COMPOUND_SELECTION_PRICING",
    "COMPOUND_PRICING_MARKET_EXPLANATION",
    "COMPOUND_MARKET_REPORT_ADVICE",
    "PRICE_QUOTE_REQUEST",
    "BATCH_PRICE_QUOTE",
    "VEHICLE_INFO_ADD",
    "VEHICLE_INFO_UPDATE",
    "VEHICLE_CONFIRM",
    "PRICE_RECALCULATE",
    "PRICE_EXPLANATION_REQUEST",
    "PRICE_FEEDBACK_CLARIFICATION",
    "CANDIDATE_EVIDENCE_REQUEST",
    "WHY_LOW_CONFIDENCE",
    "HISTORY_VEHICLE_REFERENCE",
    "MULTI_VEHICLE_COMPARE",
    "BUY_CAR_INTENT",
    "BUSINESS_INTENT_CLARIFICATION",
    "GENERAL_AUTOMOTIVE_QA",
    "MODULE_SWITCH",
    "RESET_ALL",
    "RESET_VEHICLE",
    "OUT_OF_SCOPE",
    "UNKNOWN_OR_INCOMPLETE",
}

SLOT_KEYS = (
    "brand",
    "series",
    "city",
    "price_bucket",
    "model_year",
    "first_license_date",
    "first_license_year",
    "first_license_month",
    "reg_date",
    "trim",
    "raw_vehicle_text",
    "mileage_km",
    "mileage_wan_km",
    "transfer_count",
    "color",
    "energy_type",
    "condition",
    "condition_group",
    "inspection_grade",
    "user_given_price_yuan",
    "price_role",
    "price_band",
    "fuel_type",
    "vehicle_type",
    "vehicle_category",
    "selection_filter",
    "energy_filter",
    "body_filter",
    "brand_tier",
    "manufacturer_attribute",
    "energy_subtype",
    "body_category",
    "time_window",
    "selection_target",
    "report_target",
    "report_type",
    "comparison_series",
)


def empty_slots() -> Dict[str, Any]:
    return {key: None for key in SLOT_KEYS}


def build_intent_result(
    *,
    selected_module: str,
    business_category: str,
    internal_intent: str,
    confidence: float,
    slots: Dict[str, Any] | None = None,
    secondary_intents: list[str] | None = None,
    context_reference: Dict[str, Any] | None = None,
    is_hypothetical: bool = False,
    should_render_daily_report_card: bool = False,
    should_render_market_card: bool = False,
    should_invalidate_quote: bool = False,
    fallback_message: str | None = None,
    reason: str = "",
    target_module: str | None = None,
    section: str | None = None,
) -> Dict[str, Any]:
    normalized_slots = empty_slots()
    normalized_slots.update({k: v for k, v in (slots or {}).items() if k in normalized_slots})
    result = {
        "selected_module": selected_module,
        "business_category": business_category,
        "internal_intent": internal_intent,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "secondary_intents": list(secondary_intents or []),
        "slots": normalized_slots,
        "context_reference": context_reference or {"type": None, "id": None},
        "is_hypothetical": bool(is_hypothetical),
        "should_call_pricing": False,
        "should_render_daily_report_card": bool(should_render_daily_report_card),
        "should_render_market_card": bool(should_render_market_card),
        "should_invalidate_quote": bool(should_invalidate_quote),
        "fallback_message": fallback_message,
        "reason": reason,
    }
    if target_module:
        result["target_module"] = target_module
    if section:
        result["section"] = section
    validate_intent_result(result)
    return result


def validate_intent_result(result: Dict[str, Any]) -> None:
    if result.get("selected_module") not in SUPPORTED_MODULES:
        raise ValueError(f"invalid selected_module: {result.get('selected_module')}")
    if result.get("business_category") not in BUSINESS_CATEGORIES:
        raise ValueError(f"invalid business_category: {result.get('business_category')}")
    if result.get("internal_intent") not in INTERNAL_INTENTS:
        raise ValueError(f"invalid internal_intent: {result.get('internal_intent')}")
    slots = result.get("slots")
    if not isinstance(slots, dict) or set(slots) != set(SLOT_KEYS):
        raise ValueError("slots must contain the complete V2 slot schema")
    if result.get("should_call_pricing") not in {True, False}:
        raise ValueError("should_call_pricing must be boolean")
