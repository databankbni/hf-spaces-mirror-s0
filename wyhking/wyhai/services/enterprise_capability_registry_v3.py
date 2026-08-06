from __future__ import annotations

from typing import Any


CAPABILITY_CONTRACTS: dict[str, dict[str, Any]] = {
    "single_vehicle_pricing": {
        "goal": "按定价模型和车辆七要素完成单车定价",
        "required_slots": ["series", "first_license_date", "mileage_wan_km", "city", "transfer_count", "color", "condition_group"],
        "tools": ["price_book_tool", "comparable_evidence_tool", "vehicle_adjustment_tool", "price_ladder_tool", "response_composer"],
        "outputs": ["suggested_listing_price", "estimated_sale_price", "suggested_purchase_price", "maximum_purchase_price", "first_offer_price", "price_intervals", "confidence", "comparable_evidence", "seven_element_adjustments"],
        "confirmations": ["accept_price", "formal_quote", "reprice", "export_report"],
    },
    "purchase_price_judgement": {
        "goal": "判断用户给出的收车价是否合理",
        "required_slots": ["series", "first_license_date", "mileage_wan_km", "city", "transfer_count", "color", "condition_group", "user_given_price_yuan"],
        "tools": ["price_book_tool", "comparable_evidence_tool", "vehicle_adjustment_tool", "price_ladder_tool", "response_composer"],
        "outputs": ["judgement", "suggested_purchase_interval", "maximum_purchase_reference", "risk_points", "evidence"],
        "confirmations": ["accept_price", "manual_review", "reprice"],
    },
    "sale_price_advice": {
        "goal": "生成售车/挂牌价建议",
        "required_slots": ["series", "first_license_date", "mileage_wan_km", "city", "transfer_count", "color", "condition_group"],
        "tools": ["price_book_tool", "comparable_evidence_tool", "vehicle_adjustment_tool", "price_ladder_tool", "response_composer"],
        "outputs": ["suggested_sale_price", "price_band_position", "market_competition", "risk_points"],
        "confirmations": ["accept_price", "create_listing", "reprice"],
    },
    "price_explanation": {
        "goal": "解释已有报价，不重新估价",
        "required_slots": ["quote_id"],
        "tools": ["quote_context_tool", "evidence_ledger_tool", "response_composer"],
        "outputs": ["price_bridge", "comparables", "low_confidence_reasons", "business_advice"],
        "confirmations": ["show_evidence", "manual_review", "export_report"],
    },
    "market_selection": {
        "goal": "筛选值得收、谨慎收和暂缓补库的车系",
        "required_slots": ["city"],
        "tools": ["market_indicator_tool", "market_state_tool", "selection_strategy_tool", "daily_report_tool", "response_composer"],
        "outputs": ["top_series", "market_labels", "opportunity_score", "recommended_action", "price_reference_range", "risk_reasons"],
        "confirmations": ["add_watchlist", "start_pricing", "export_report"],
    },
    "market_report": {
        "goal": "生成车型、城市、价格带或行业日报维度行情分析",
        "required_slots": [],
        "tools": ["market_indicator_tool", "market_state_tool", "daily_report_tool", "response_composer"],
        "outputs": ["market_conclusion", "demand_change", "supply_change", "price_change", "market_label", "events", "business_advice"],
        "confirmations": ["export_report", "switch_selection", "start_pricing"],
    },
    "compound_selection_pricing": {
        "goal": "从城市选品结果进入可执行定价",
        "required_slots": ["city"],
        "tools": ["market_indicator_tool", "market_state_tool", "selection_strategy_tool", "valuation_tool", "daily_report_tool", "response_composer"],
        "outputs": ["top_series", "price_reference_ranges", "risk_reasons", "next_vehicle_fields"],
        "confirmations": ["choose_series", "fill_vehicle_fields", "formal_quote"],
    },
    "compound_pricing_market_explanation": {
        "goal": "用单车估值、车型城市行情和日报事件解释收车价判断",
        "required_slots": ["series", "first_license_date", "mileage_wan_km", "city", "transfer_count", "color", "condition_group"],
        "tools": ["price_book_tool", "comparable_evidence_tool", "vehicle_adjustment_tool", "price_ladder_tool", "response_composer"],
        "outputs": ["price_judgement", "market_support", "risk_labels", "evidence", "business_action"],
        "confirmations": ["accept_price", "manual_review", "reprice"],
    },
    "compound_market_report_advice": {
        "goal": "生成行情报告并形成经营/收车建议",
        "required_slots": ["city"],
        "tools": ["market_indicator_tool", "market_state_tool", "daily_report_tool", "selection_strategy_tool", "response_composer"],
        "outputs": ["market_report", "opportunities", "risks", "business_advice", "price_reference_ranges"],
        "confirmations": ["export_report", "switch_selection", "start_pricing"],
    },
}


def contract_for(task_type: str, internal_intent: str = "") -> dict[str, Any]:
    if task_type.startswith("single_vehicle_pricing"):
        key = "sale_price_advice" if "listing" in task_type else "single_vehicle_pricing"
    elif task_type == "single_vehicle_purchase_price_judgement":
        key = "purchase_price_judgement"
    elif task_type == "car_selection_or_market_state":
        key = "market_selection"
    else:
        key = task_type
    return {"capability_id": key, **CAPABILITY_CONTRACTS.get(key, {})}
