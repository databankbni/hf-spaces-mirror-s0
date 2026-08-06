from __future__ import annotations

from typing import Any, Dict, List

from .customer_script_composer import customer_script_block


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
    summary = report.get("decision_summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "type": "decision_summary",
        "title": "本次定价结论",
        "items": [
            {"label": "定价结论", "value": summary.get("decision") or "已给出本车收售价格与最高收车边界"},
            {"label": "建议沟通价", "value": summary.get("communication_price") or ""},
            {"label": "内部追价上限", "value": summary.get("internal_chase_limit") or ""},
            {"label": "对客是否展示上限", "value": summary.get("show_limit_to_customer") or "否"},
            {"label": "下一步动作", "value": summary.get("next_action") or "核对实车车况后按建议价推进议价"},
        ],
        "summary": summary.get("reason") or report.get("summary_why") or "",
    }


def compose_final_report_blocks(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    boundary_items = []
    for item in report.get("price_boundary") or []:
        if isinstance(item, dict):
            boundary_items.append(f"{item.get('value')}：{item.get('label')}。{item.get('advice')}")
    main_risks = report.get("main_risks")
    if not isinstance(main_risks, list) or not main_risks:
        main_risks = [report.get("main_risk") or "车况、整备和周转风险仍需人工复核。"]
    internal_basis = report.get("internal_basis")
    if not isinstance(internal_basis, list):
        internal_basis = []
    customer_questions = report.get("customer_questions")
    if not isinstance(customer_questions, list):
        customer_questions = []
    technical_audit = report.get("technical_audit")
    if not isinstance(technical_audit, list):
        technical_audit = ["技术细节默认隐藏；如需审计，可展开查看链路、版本和模型调用状态。"]
    return [
        build_decision_block(report),
        {"type": "section", "title": "建议怎么报价｜内部议价依据", "items": internal_basis[:6]},
        {"type": "section", "title": "为什么不能追高", "text": report.get("why_this_price") or ""},
        {"type": "section", "title": "价格边界怎么用", "items": boundary_items[:3]},
        {"type": "section", "title": "主要风险", "items": main_risks[:4]},
        customer_script_block(str(report.get("customer_script") or "")),
        {"type": "qa", "title": "客户常见反问", "items": customer_questions[:4]},
        {
            "type": "details",
            "title": "分析过程与证据详情",
            "items": ["点击“查看本次分析过程”展开任务规划、阶段结论和证据小表。"],
            "collapsed": True,
        },
        {
            "type": "technical_audit",
            "title": "技术溯源与算法审计",
            "items": technical_audit[:8],
            "collapsed": True,
        },
    ]
