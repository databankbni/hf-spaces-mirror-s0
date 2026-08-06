from __future__ import annotations

from typing import Any, Dict, List


def _display_wan(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        return f"{float(value):.2f}万"
    text = str(value or "").strip()
    return text or "-"


def compose_pricing_decision_report(
    *,
    pricing_result: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    market_context: Dict[str, Any],
    daily_report_context: Dict[str, Any],
    vehicle_slots: Dict[str, Any],
) -> Dict[str, Any]:
    """Build top-level decision DTO without changing model prices."""
    point = pricing_result.get("point_price_text") or "-"
    talk = pricing_result.get("customer_talk_price") or point
    upper = pricing_result.get("upper_price_text") or "-"
    internal_target = pricing_result.get("point_price_text") or "-"
    decision = pricing_result.get("decision") or "已形成收车建议，请按建议价和最高边界执行"
    reasons = [
        evidence_summary.get("summary") or "可比车用于核对定价模型参考起点",
        "车辆七要素已逐项进入价格修正",
        "挂牌、售卖、收车与最高收车价已完成大小关系校验",
    ]
    return {
        "decision": decision,
        "headline": pricing_result.get("decision_headline") or f"本次定价已完成，建议先按{talk}沟通。",
        "recommended_talk_price": talk,
        "internal_target_price": internal_target,
        "internal_upper_bound": upper,
        "show_upper_bound_to_customer": False,
        "next_best_action": pricing_result.get("next_action") or "先核对实车车况；确认与输入一致后，按建议价推进议价。",
        "do_not_do": pricing_result.get("do_not_do") or "不要直接按网上高价或最高可比样本追价。",
        "top_reasons": [str(item) for item in reasons if item][:3],
        "internal_only": True,
        "customer_safe": False,
    }


def build_summary_block(*, conclusion: str, why: str, how_to_do: str) -> Dict[str, Any]:
    return {
        "type": "summary",
        "title": "本次估价摘要",
        "items": [
            f"建议：{conclusion}",
            f"原因：{why}",
            f"动作：{how_to_do}",
        ],
    }


def build_decision_block(report: Dict[str, Any]) -> Dict[str, Any]:
    card = report.get("decision_card")
    if not isinstance(card, dict):
        card = {}
    summary = report.get("decision_summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "type": "decision_card",
        "title": "单车定价卡",
        "decision": card.get("decision") or summary.get("decision") or "已形成收车建议，请按建议价和最高边界执行",
        "headline": card.get("headline") or report.get("headline") or "",
        "items": [
            {"label": "建议沟通价", "value": card.get("recommended_talk_price") or summary.get("customer_talk_price") or summary.get("communication_price") or "", "badge": "对客可说"},
            {"label": "内部锚点", "value": card.get("internal_target_price") or summary.get("internal_target_price") or "", "badge": "内部使用"},
            {"label": "追价上限", "value": card.get("internal_upper_bound") or summary.get("internal_chase_limit") or "", "badge": "内部可见"},
            {"label": "建议售车价", "value": card.get("recommended_sale_price") or "", "badge": card.get("sale_price_source") or ""},
            {"label": "预计价差毛利", "value": card.get("gross_profit") or "", "badge": "扣成本后"},
            {"label": "毛利率", "value": card.get("gross_profit_rate") or "", "badge": "参考"},
        ],
        "show_upper_bound_to_customer": bool(card.get("show_upper_bound_to_customer")),
        "next_best_action": card.get("next_best_action") or summary.get("next_action") or "",
        "do_not_do": card.get("do_not_do") or summary.get("do_not_do") or "不要直接按网上高价或最高可比样本追价。",
        "top_reasons": card.get("top_reasons") or [],
        "internal_only": True,
        "customer_safe": False,
    }


def compose_final_report_blocks(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    boundary_items = []
    for item in report.get("price_boundary") or []:
        if isinstance(item, dict):
            internal = item.get("internal_only", True)
            boundary_items.append({
                "label": item.get("label"),
                "value": item.get("value"),
                "advice": item.get("advice"),
                "internal_only": internal,
                "customer_safe": False,
            })
    main_risks = report.get("main_risks")
    if not isinstance(main_risks, list) or not main_risks:
        main_risks = [report.get("main_risk") or "车况、整备和周转风险仍需人工复核。"]
    internal_basis = report.get("internal_basis")
    if not isinstance(internal_basis, list):
        internal_basis = []
    customer_script_pack = report.get("customer_script_pack")
    if not isinstance(customer_script_pack, dict):
        customer_script_pack = {}
    customer_questions = report.get("customer_questions")
    if not isinstance(customer_questions, list):
        customer_questions = []
    technical_audit = report.get("technical_audit")
    if not isinstance(technical_audit, list):
        technical_audit = ["技术细节默认隐藏；如需审计，可展开查看链路、版本和模型调用状态。"]
    card = report.get("decision_card") if isinstance(report.get("decision_card"), dict) else {}
    summary = report.get("decision_summary") if isinstance(report.get("decision_summary"), dict) else {}
    four_prices = [
        {"label": "建议挂牌价", "value": _display_wan(report.get("listing_price"))},
        {"label": "预计实际售车价", "value": card.get("recommended_sale_price") or report.get("sale_price_text") or "-"},
        {"label": "建议收车价", "value": card.get("internal_target_price") or summary.get("internal_target_price") or "-"},
        {"label": "最高收车价", "value": card.get("internal_upper_bound") or summary.get("internal_chase_limit") or "-"},
    ]
    return [
        {
            "type": "decision_summary",
            "title": "收车决策摘要",
            "decision": summary.get("decision") or report.get("headline") or "",
            "prices": four_prices,
            "top_reasons": (card.get("top_reasons") or internal_basis)[:3],
            "main_risks": main_risks[:2],
            "next_best_action": card.get("next_best_action") or summary.get("next_action") or report.get("summary_action") or "",
            "confidence_breakdown": report.get("confidence_breakdown") or {},
        },
        {
            "type": "price_formation",
            "title": "价格形成过程",
            "items": report.get("price_formation") or [],
            "price_reasoning": report.get("price_reasoning") or {},
        },
        {
            "type": "comparable_evidence",
            "title": "可比车与证据",
            "candidate_count": report.get("candidate_count") or 0,
            "items": report.get("comparable_evidence") or [],
        },
        {
            "type": "boundary_and_risk",
            "title": "价格边界与风险",
            "boundaries": boundary_items[:3],
            "risks": main_risks[:3],
        },
        {
            "type": "customer_script_pack",
            "title": "沟通助手",
            "scenarios": customer_script_pack.get("scenarios") or [],
            "questions": customer_questions[:5],
            "copyable": True,
            "customer_safe": True,
        },
        {
            "type": "details",
            "title": "分析过程与证据详情",
            "items": internal_basis[:6],
            "collapsed": True,
            "internal_only": True,
        },
        {
            "type": "technical_audit",
            "title": "技术溯源与算法审计",
            "items": technical_audit[:8],
            "collapsed": True,
            "internal_only": True,
        },
    ]
