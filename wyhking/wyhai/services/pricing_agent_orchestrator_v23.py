from __future__ import annotations

import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from typing import Any, Dict, Iterable, List

from .agent_runtime.claim_grounder import ground_report_claims
from .agent_runtime.customer_script_generator import (
    filter_customer_text,
    flatten_script_pack,
    generate_customer_faq,
    generate_customer_script_pack,
)
from .agent_runtime.pricing_business_explainer import compose_pricing_step_explanation, running_step_explanation
from .agent_runtime.report_composer import compose_final_report_blocks, compose_pricing_decision_report
from .agent_runtime.stage_explainer import explain_stage
from .llm_client import Qwen3LocalClient, extract_json_object
from .reflexion.feedback_schema import price_band_from_price, vehicle_context_from_slots
from .reflexion.reflection_retriever import retrieve_for_context


PRICING_AGENT_SCHEMA_VERSION = "pricing_agent_compact_v2"

MAX_VISIBLE_TABLE_ROWS = 3
MAX_FINDING_CHARS = 20
MAX_IMPACT_CHARS = 28
MAX_SOURCE_CHARS = 8

SIX_ELEMENT_FIELDS = [
    "standard_vehicle",
    "first_license_date",
    "mileage_wan_km",
    "city",
    "transfer_count",
    "color",
    "condition_group",
]

SLOT_LABELS = {
    "standard_vehicle": "标准车型",
    "vehicle_confirm": "标准车型",
    "model": "标准车型",
    "trim": "标准车型",
    "model_year": "标准车型",
    "year_disambiguation": "标准车型",
    "brand": "品牌",
    "series": "车系/车型",
    "first_license_date": "上牌时间",
    "first_license_year": "上牌时间",
    "first_license_month": "上牌时间",
    "mileage_wan_km": "里程",
    "mileage_km": "里程",
    "city": "城市",
    "transfer_count": "过户次数",
    "color": "颜色",
    "condition_group": "车况",
    "inspection_grade": "车况",
    "condition": "车况",
}


def _business_text(value: Any) -> str:
    """Return user-facing Chinese text without ever leaking a raw dict repr."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "one_sentence", "summary", "headline", "judgement", "conclusion"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        listing = value.get("recommended_listing_wan")
        sale = value.get("expected_b2c_wan")
        purchase = value.get("expected_c2b_wan") or value.get("reference_price_wan")
        parts = []
        if listing not in (None, ""):
            parts.append(f"建议挂牌价{listing}万")
        if sale not in (None, ""):
            parts.append(f"预计售卖价{sale}万")
        if purchase not in (None, ""):
            parts.append(f"建议收车价{purchase}万")
        return "；".join(parts)
    if value in (None, ""):
        return ""
    return str(value).strip()


def pricing_task_planner(
    *,
    message: str,
    response: Dict[str, Any],
    preview_mode: bool = False,
) -> Dict[str, Any]:
    slots = response.get("slots") or {}
    missing_fields = _normalize_missing_fields(response.get("missing_fields") or [])
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    report_context = response.get("pricing_report_context") or {}
    price_role = _detect_price_role(message, response)
    quote_amount_yuan = _extract_user_quote_yuan(message, response)
    point = _price_point(price_result)
    candidates = _selected_comparables(price_result)
    market_available = _has_market_or_daily_context(report_context)
    evidence_insufficient = bool(point) and len(candidates) < 5

    if missing_fields:
        tasks = [
            {
                "task_id": "field_confirmation_task",
                "task_name": "字段确认与补全",
                "task_goal": "确认标准车型、上牌时间、里程、城市、过户次数和颜色是否齐全；车况未填写时按系统默认良好车况估算，并明确待实车检测。",
                "trigger_reason": "车辆七要素不完整",
            }
        ]
        plan = {
            "title": "收车估价前置条件确认",
            "need_understanding": _missing_understanding(slots, missing_fields),
            "price_role": price_role,
            "quote_amount_yuan": quote_amount_yuan,
            "can_execute_pricing": False,
            "preview_mode": preview_mode,
            "tasks": tasks,
        }
        return _compact_plan(_llm_refine_plan(message, response, plan))

    workflow_runs = [
        item for item in (response.get("workflow_tool_results") or [])
        if isinstance(item, dict) and item.get("tool_name")
    ]
    if workflow_runs:
        labels = {
            "price_book_tool": ("调用定价模型并生成单车价格", "按标准车型、市场基线和七要素生成收车价与售卖价锚点。"),
            "comparable_evidence_tool": ("核对可比车与市场基线", "核对可比车数量、相似程度和价格分布。"),
            "vehicle_adjustment_tool": ("核对七要素价格影响", "逐项说明当前车与可比基线的差异如何影响价格。"),
            "price_ladder_tool": ("校验完整价格梯度", "校验挂牌、实际售卖、实际收车、首报价和最高收车价的角色与顺序。"),
            "response_composer": ("生成一线业务结论", "把价格、证据、谈判边界和风险整理成可直接执行的结论。"),
        }
        workflow_tasks = []
        for index, run in enumerate(workflow_runs):
            tool_name = str(run.get("tool_name") or "")
            title, goal = labels.get(tool_name, ("执行业务工具", "执行本轮计划中的真实业务能力。"))
            workflow_tasks.append(
                {
                    "task_id": tool_name,
                    "task_name": title,
                    "task_goal": goal,
                    "trigger_reason": "来自本轮真实工具运行记录",
                    "workflow_step_id": run.get("step_id") or f"step_{index + 1}",
                }
            )
        return _compact_plan(
            {
                "title": _plan_title(price_role),
                "need_understanding": _complete_understanding(slots, response, price_role, quote_amount_yuan),
                "price_role": price_role,
                "quote_amount_yuan": quote_amount_yuan,
                "can_execute_pricing": True,
                "preview_mode": preview_mode,
                "tasks": workflow_tasks,
                "source": "workflow_tool_results",
            }
        )

    tasks: list[Dict[str, Any]] = [
        {
            "task_id": "pricing_evidence_task",
            "task_name": "找相近车，确定市场参考价",
            "task_goal": "找到相近成交/在售样本，判断这台车的市场参考起点。",
            "trigger_reason": "七要素完整，可以进入估价证据分析",
        },
        {
            "task_id": "vehicle_difference_task",
            "task_name": "看本车条件，判断该加还是该压",
            "task_goal": "比较当前车和可比车在配置、里程、城市、过户、颜色上的差异。",
            "trigger_reason": "需要解释可比车基线如何变成建议价",
        },
    ]

    if _needs_quote_judgement(message, price_role, quote_amount_yuan):
        tasks.append(
            {
                "task_id": "quote_acceptance_task",
                "task_name": _quote_task_name(price_role),
                "task_goal": _quote_task_goal(price_role),
                "trigger_reason": "用户给出了具体报价或询问价格是否可接受",
            }
        )

    if evidence_insufficient:
        tasks.append(
            {
                "task_id": "low_confidence_task",
                "task_name": "说明本次定价置信度",
                "task_goal": "说明可比证据数量如何影响本次价格的置信度和使用边界。",
                "trigger_reason": "内部可比证据不足 5 条",
            }
        )

    tasks = _prioritize_tasks(tasks, has_quote=_needs_quote_judgement(message, price_role, quote_amount_yuan))
    plan = {
        "title": _plan_title(price_role),
        "need_understanding": _complete_understanding(slots, response, price_role, quote_amount_yuan),
        "price_role": price_role,
        "quote_amount_yuan": quote_amount_yuan,
        "can_execute_pricing": True,
        "preview_mode": preview_mode,
        "tasks": tasks[:3],
    }
    return _compact_plan(_llm_refine_plan(message, response, plan))


def pricing_task_executor(
    *,
    message: str,
    response: Dict[str, Any],
    task_plan: Dict[str, Any],
) -> list[Dict[str, Any]]:
    missing_fields = response.get("missing_fields") or []
    pricing = response.get("pricing") or {}
    price_result = pricing.get("price_result") or {}
    point = _price_point(price_result)
    preview_mode = bool(task_plan.get("preview_mode"))

    if missing_fields:
        tables = [
            pricing_result_table_builder(
                task_id="field_confirmation_task",
                message=message,
                response=response,
                task_plan=task_plan,
            )
        ]
        return _llm_refine_tables(message, response, [table for table in tables if table])

    if preview_mode or not point:
        return []

    workflow_runs = [
        item for item in (response.get("workflow_tool_results") or [])
        if isinstance(item, dict) and item.get("tool_name")
    ]
    if workflow_runs:
        tables: list[Dict[str, Any]] = []
        task_names = {
            str(item.get("task_id") or ""): str(item.get("task_name") or "业务步骤")
            for item in (task_plan.get("tasks") or [])
            if isinstance(item, dict)
        }
        for run in workflow_runs:
            tool_name = str(run.get("tool_name") or "")
            result = run.get("result") if isinstance(run.get("result"), dict) else {}
            explanation = result.get("tool_business_explanation") if isinstance(result.get("tool_business_explanation"), dict) else {}
            if not explanation:
                candidate = result.get("business_explanation") if isinstance(result.get("business_explanation"), dict) else {}
                if any(key in candidate for key in ("conclusion", "impact", "action", "evidence")):
                    explanation = candidate
            evidence = [str(item) for item in (explanation.get("evidence") or []) if str(item).strip()]
            conclusion = _business_text(explanation.get("conclusion")) or "步骤已完成"
            impact = _business_text(explanation.get("impact")) or "这一步已进入本轮定价判断。"
            action = _business_text(explanation.get("action")) or "继续下一步"
            tables.append(
                {
                    "task_id": tool_name,
                    "title": task_names.get(tool_name) or "业务步骤",
                    "columns": ["本步结论", "关键依据", "对报价的影响", "下一步"],
                    "rows": [[
                        conclusion,
                        "；".join(evidence[:4]) or "结果已写入本轮工具记录",
                        impact,
                        action,
                    ]],
                    "summary": conclusion,
                    "stage_conclusion": conclusion,
                    "business_meaning": impact,
                    "price_impact": impact,
                    "action": action,
                    "metric_chips": evidence[:3],
                    "risk": explanation.get("risk") or "",
                    "status": run.get("status") or "success",
                    "source": run.get("source") or "workflow_tool_results",
                    "tool_run_id": run.get("tool_run_id"),
                }
            )
        return tables

    tables: list[Dict[str, Any]] = []
    for task in task_plan.get("tasks") or []:
        table = pricing_result_table_builder(
            task_id=str(task.get("task_id") or ""),
            message=message,
            response=response,
            task_plan=task_plan,
        )
        if table:
            tables.append(table)
    return _llm_refine_tables(message, response, tables)


def pricing_result_table_builder(
    *,
    task_id: str,
    message: str,
    response: Dict[str, Any],
    task_plan: Dict[str, Any],
) -> Dict[str, Any] | None:
    if task_id == "field_confirmation_task":
        return _field_confirmation_table(response)
    if task_id == "pricing_evidence_task":
        return _evidence_table(response)
    if task_id == "vehicle_difference_task":
        return _difference_table(response)
    if task_id == "risk_boundary_task":
        return _risk_table(response)
    if task_id == "quote_acceptance_task":
        return _quote_acceptance_table(message, response, task_plan)
    if task_id == "low_confidence_task":
        return _low_confidence_table(response)
    return None


def pricing_report_composer(
    *,
    message: str,
    response: Dict[str, Any],
    task_plan: Dict[str, Any],
    task_result_tables: list[Dict[str, Any]],
) -> Dict[str, Any]:
    pricing = response.get("pricing") or {}
    price_result = pricing.get("price_result") or {}
    point = _price_point(price_result)
    if not point or response.get("missing_fields"):
        return {}

    report_context = response.get("pricing_report_context") or {}
    reflection_bundle = response.get("reflection_context") if isinstance(response.get("reflection_context"), dict) else {}
    six = _six_elements(response)
    vehicle_title = _vehicle_title(six, response)
    lower, upper = _price_range(price_result, point)
    sale_profit = _sale_profit_context(price_result, point, lower, upper)
    point = _price_yuan(sale_profit.get("purchase_price_yuan")) or point
    lower = _price_yuan(sale_profit.get("purchase_price_low_yuan")) or lower
    purchase_range_upper = _price_yuan(sale_profit.get("purchase_price_high_yuan")) or upper
    # The price ladder has one and only one chase limit.  Some upstream
    # payloads carry both a C2B range high and an explicit max-C2B field; the
    # explicit max is the business boundary used by the four-price card, so
    # reuse it everywhere in the report instead of showing two close but
    # contradictory “highest purchase prices”.
    upper = _price_yuan(sale_profit.get("max_c2b_price_yuan")) or upper
    baseline = _baseline_price(response)
    candidate_count = len(_selected_comparables(price_result))
    price_role = str(task_plan.get("price_role") or "purchase_price")
    quote_amount = _money(task_plan.get("quote_amount_yuan"))
    confidence = str(price_result.get("confidence") or "MEDIUM").upper()
    quote_rows = _table_rows(task_result_tables, "quote_acceptance_task")
    candidate_prices = [_candidate_price(row) for row in _selected_comparables(price_result) if _candidate_price(row)]
    dispersion = _dispersion_label(candidate_prices)
    low = min(candidate_prices) if candidate_prices else lower
    high = max(candidate_prices) if candidate_prices else upper
    daily_note = ""
    headline = _lead_sentence(vehicle_title, point, lower, upper, confidence, candidate_count, price_role, quote_amount)
    why_this_price = _why_this_price(
        response=response,
        task_result_tables=task_result_tables,
        count=candidate_count,
        low=low,
        high=high,
        baseline=baseline,
        point=point,
        dispersion=dispersion,
        purchase_lower=lower,
        purchase_upper=upper,
    )
    summary_why = _summary_why(response, candidate_count, dispersion, task_result_tables, daily_note)
    summary_action = _summary_action(point, upper, dispersion)
    price_boundary = [
        {"label": "保守收车价", "value": _wan_text(lower), "advice": "车况不确定、整备成本偏高、客户急卖时优先靠近这个价格。", "internal_only": True, "customer_safe": False},
        {"label": "建议谈判锚点", "value": _wan_text(point), "advice": "车况正常、手续清晰时，可以围绕这个价推进。", "internal_only": True, "customer_safe": False},
        {"label": "追价上限", "value": _wan_text(upper), "advice": "超过后风险明显变高，不建议继续追。", "internal_only": True, "customer_safe": False},
    ]
    main_risks = _main_risk_items(response, lower, upper, confidence, dispersion, daily_note)
    main_risk = "；".join(main_risks)
    actions = _action_items(point, lower, upper, confidence, candidate_count, quote_rows, report_context)[:4]
    decision_summary = _decision_summary(
        response=response,
        point=point,
        upper=upper,
        confidence=confidence,
        candidate_count=candidate_count,
        dispersion=dispersion,
        task_result_tables=task_result_tables,
        daily_note=daily_note,
    )
    decision_summary["decision"] = (
        f"建议围绕 {_wan_text(point)} 沟通，正常情况下可在 {_range_text(lower, purchase_range_upper)} 内谈；"
        f"超过 {_wan_text(upper)} 不建议继续追价。"
    )
    vehicle_condition_clause = _customer_vehicle_condition_clause(six, _selected_comparables(price_result))
    market_clause = _customer_market_clause(response, dispersion, daily_note)
    internal_basis = _internal_basis_items(
        candidate_count=candidate_count,
        low=low,
        high=high,
        baseline=baseline,
        point=point,
        upper=upper,
        confidence=confidence,
        dispersion=dispersion,
        daily_note=daily_note,
        task_result_tables=task_result_tables,
    )
    price_reasoning = _price_reasoning(
        response=response,
        baseline=baseline,
        point=point,
        high=high,
        dispersion=dispersion,
        task_result_tables=task_result_tables,
        mileage_impact=_mileage_impact(six, _selected_comparables(price_result)),
        daily_note=daily_note,
    )
    decision_card = compose_pricing_decision_report(
        pricing_result={
            "decision": decision_summary.get("decision"),
            "headline": headline,
            "point_price_text": _wan_text(point),
            "upper_price_text": _wan_text(upper),
            "customer_talk_price": decision_summary.get("customer_talk_price") or _customer_talk_price(point),
            "next_action": decision_summary.get("next_action"),
            "do_not_do": decision_summary.get("do_not_do"),
            "sale_price_text": _wan_text(sale_profit.get("sale_price_yuan")),
            "gross_profit_text": _signed_wan_text(sale_profit.get("gross_profit_yuan")),
            "gross_profit_rate_text": _percent_text(sale_profit.get("gross_profit_rate")),
        },
        evidence_summary={
            "summary": _evidence_stage_conclusion(candidate_count, dispersion),
            "candidate_count": candidate_count,
            "dispersion": dispersion,
        },
        market_context={},
        daily_report_context={},
        vehicle_slots=six,
    )
    decision_card["recommended_sale_price"] = _wan_text(sale_profit.get("sale_price_yuan"))
    decision_card["sale_price_source"] = sale_profit.get("sale_price_source")
    decision_card["gross_profit"] = _signed_wan_text(sale_profit.get("gross_profit_yuan"))
    decision_card["gross_profit_rate"] = _percent_text(sale_profit.get("gross_profit_rate"))
    decision_card["profit_note"] = (
        str(sale_profit.get("purchase_profit_guard_note") or "").strip()
        or _sale_price_source_note(str(sale_profit.get("sale_price_source") or ""))
    )
    stub_report_for_script = {
        "decision_summary": decision_summary,
        "decision_card": decision_card,
        "upper_yuan": upper,
        "baseline_price_yuan": baseline,
        "vehicle_title": vehicle_title,
        "candidate_count": candidate_count,
        "main_risks": main_risks,
        "comparable_price_range": _range_text(low, high),
    }
    customer_script_pack = generate_customer_script_pack(
        pricing_decision_report=stub_report_for_script,
        vehicle_slots=six,
        condition_clause=vehicle_condition_clause,
        market_clause=market_clause,
        dispersion=dispersion,
    )
    customer_questions = generate_customer_faq(
        pricing_decision_report=stub_report_for_script,
        vehicle_slots=six,
        dispersion=dispersion,
        condition_clause=vehicle_condition_clause,
        market_clause=market_clause,
    )
    customer_script_pack, customer_questions = _apply_reflections_to_customer_copy(
        customer_script_pack=customer_script_pack,
        customer_questions=customer_questions,
        reflection_bundle=reflection_bundle,
        report_stub=stub_report_for_script,
    )
    customer_script = flatten_script_pack(customer_script_pack)
    ai_summary = _build_pricing_ai_summary(
        six=six,
        point=point,
        lower=lower,
        upper=upper,
        baseline=baseline,
        candidate_count=candidate_count,
        comparable_low=low,
        comparable_high=high,
        confidence=confidence,
        dispersion=dispersion,
        sale_profit=sale_profit,
        why_this_price=why_this_price,
    )
    ai_summary["safe_purchase_high_yuan"] = purchase_range_upper
    comparables = _comparable_evidence_items(response, six)
    confidence_breakdown = _confidence_breakdown(
        response=response,
        model_confidence=confidence,
        comparables=comparables,
    )
    price_formation = _price_formation_steps(
        six=six,
        baseline=baseline,
        point=point,
        upper=upper,
        sale_price=_price_yuan(sale_profit.get("sale_price_yuan")),
        price_reasoning=price_reasoning,
        comparable_count=candidate_count,
    )
    deterministic_report = {
        "title": "单车定价建议",
        "vehicle_title": vehicle_title,
        "decision_card": decision_card,
        "decision_summary": decision_summary,
        "headline": headline,
        "lead": headline,
        "summary_why": summary_why,
        "summary_action": summary_action,
        "why_this_price": why_this_price,
        "price_reasoning": price_reasoning,
        "price_boundary": price_boundary,
        "main_risk": main_risk,
        "main_risks": main_risks,
        "action_guide": actions,
        "internal_basis": internal_basis,
        "ai_summary": ai_summary,
        "customer_script": customer_script,
        "customer_script_pack": customer_script_pack,
        "customer_questions": customer_questions,
        "daily_note": daily_note,
        "point_price_yuan": point,
        "lower_yuan": lower,
        "upper_yuan": upper,
        "baseline_price_yuan": baseline,
        "candidate_count": candidate_count,
        "confidence": confidence,
        "confidence_breakdown": confidence_breakdown,
        "comparable_evidence": comparables,
        "price_formation": price_formation,
        **sale_profit,
        "reflection_audit": reflection_bundle,
        "technical_audit": _technical_audit_items(response),
    }
    _sync_report_blocks(deterministic_report)
    refined = _llm_refine_report(message, response, task_plan, task_result_tables, deterministic_report)
    grounded, warnings = ground_report_claims(refined, _llm_fact_pack(response))
    if warnings:
        grounded.setdefault("llm_audit", refined.get("llm_audit") or {})
        grounded["llm_audit"]["claim_grounding_warnings"] = warnings
    return grounded


def build_pricing_agent_package(
    *,
    message: str,
    response: Dict[str, Any],
    preview_mode: bool = False,
) -> Dict[str, Any]:
    response = dict(response or {})
    response.setdefault("reflection_context", _retrieve_reflections_for_response(message, response))
    task_plan = pricing_task_planner(message=message, response=response, preview_mode=preview_mode)
    task_tables = pricing_task_executor(message=message, response=response, task_plan=task_plan)
    final_report = pricing_report_composer(
        message=message,
        response=response,
        task_plan=task_plan,
        task_result_tables=task_tables,
    )
    agent_intro = _agent_intro(message, response, task_plan)
    events = _build_events(agent_intro, task_plan, task_tables, final_report)
    return {
        "schema_version": PRICING_AGENT_SCHEMA_VERSION,
        "agent_intro": agent_intro,
        "task_plan": {
            "title": task_plan.get("title"),
            "need_understanding": task_plan.get("need_understanding"),
            "summary": task_plan.get("summary") or task_plan.get("need_understanding"),
            "price_role": task_plan.get("price_role"),
            "quote_amount_yuan": task_plan.get("quote_amount_yuan"),
            "can_execute_pricing": task_plan.get("can_execute_pricing"),
            "tasks": task_plan.get("tasks") or [],
            "llm_audit": task_plan.get("llm_audit") or {},
            "reflection_audit": response.get("reflection_context") or {},
        },
        "events": events,
        "task_result_tables": task_tables,
        "final_report": final_report,
        "reflection_audit": response.get("reflection_context") or {},
        "llm_audit": _collect_llm_audit(task_plan, task_tables, final_report),
        "streaming": {
            "mode": "simulated_from_backend_events",
            # Keep the execution legible, but do not stack seconds of fake
            # waiting on top of the real model and evidence lookup latency.
            "delay_ms": 180,
        },
    }


def _llm_runtime() -> tuple[Qwen3LocalClient, bool, str]:
    client = Qwen3LocalClient()
    snapshot = client.config_snapshot()
    explicit_base = bool(os.environ.get("LLM_BASE_URL"))
    configured = bool(snapshot.get("api_key_configured") or explicit_base)
    if os.environ.get("PRICING_AGENT_ENABLE_LLM", "true").lower() not in {"1", "true", "yes", "on", "auto"}:
        return client, False, "PRICING_AGENT_ENABLE_LLM=false"
    if not configured:
        return client, False, "LLM endpoint/api key not configured in current process"
    return client, True, ""


def _llm_refine_plan(message: str, response: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    client, enabled, reason = _llm_runtime()
    audit = {
        "stage": "pricing_task_planner",
        "used": False,
        "model": client.config_snapshot().get("model"),
        "fallback_reason": reason,
    }
    if not enabled:
        plan["llm_audit"] = audit
        return plan
    allowed_task_ids = [str(item.get("task_id")) for item in (plan.get("tasks") or []) if item.get("task_id")]
    prompt = (
        "你是一线二手车定价 Agent 的任务规划器。只根据用户问题和系统事实，生成动态任务规划 JSON。"
        "不得新增价格、不得新增工具事实、不得暴露 tool name / intent code。"
        "facts.reflection_memory 只能用于调整解释重点和任务表述，绝不能改价格或虚构事实。"
        "必须只使用 allowed_task_ids 里的 task_id，任务数量 1-3。"
        "规划必须短：需求理解只写一句业务目标，每个 task_goal 只写一个动作，不写长段背景。"
        "输出 JSON：{\"title\":\"\",\"need_understanding\":\"\",\"tasks\":[{\"task_id\":\"\",\"task_name\":\"\",\"task_goal\":\"\"}]}"
    )
    payload = {
        "user_message": message,
        "allowed_task_ids": allowed_task_ids,
        "deterministic_plan": {
            "title": plan.get("title"),
            "need_understanding": plan.get("need_understanding"),
            "tasks": plan.get("tasks") or [],
        },
        "facts": _llm_fact_pack(response),
    }
    result = client.structured_extract(prompt, payload)
    audit.update({"latency_ms": result.latency_ms, "model": result.model or audit["model"]})
    parsed = extract_json_object(result.content) if result.ok else None
    if not isinstance(parsed, dict):
        audit.update({"fallback_reason": result.fallback_reason or "LLM returned non-json"})
        plan["llm_audit"] = audit
        return plan
    task_by_id = {str(item.get("task_id")): item for item in (plan.get("tasks") or [])}
    refined_tasks: list[Dict[str, Any]] = []
    for item in parsed.get("tasks") or []:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "")
        if task_id not in task_by_id:
            continue
        original = task_by_id[task_id]
        refined_tasks.append({
            **original,
            "task_name": str(item.get("task_name") or original.get("task_name") or ""),
            "task_goal": str(item.get("task_goal") or original.get("task_goal") or ""),
            "llm_planned": True,
        })
    if refined_tasks:
        plan["tasks"] = refined_tasks[:3]
    if parsed.get("title"):
        plan["title"] = str(parsed["title"])[:80]
    if parsed.get("need_understanding"):
        plan["need_understanding"] = str(parsed["need_understanding"])[:260]
    audit.update({"used": True, "fallback_reason": ""})
    plan["llm_audit"] = audit
    return plan


def _llm_refine_table(message: str, response: Dict[str, Any], table: Dict[str, Any]) -> Dict[str, Any]:
    client, enabled, reason = _llm_runtime()
    table = _enforce_compact_table(table)
    explanation = explain_stage(
        client=client,
        enabled=enabled,
        disabled_reason=reason,
        message=message,
        table=table,
        facts=_llm_fact_pack(response),
    )
    for field in (
        "stage_conclusion",
        "why_trust",
        "business_meaning",
        "price_impact",
        "action",
        "need_review",
        "trust_sources",
        "llm_explained",
    ):
        if field in explanation:
            table[field] = explanation[field]
    table["summary"] = table.get("stage_conclusion") or table.get("summary")
    table["llm_audit"] = explanation.get("llm_audit") or {}
    table = _enforce_compact_table(table)
    table["business_explanation"] = compose_pricing_step_explanation(
        step_name=str(table.get("title") or ""),
        tool_result=table,
        vehicle_slots=_six_elements(response),
        market_context=(response.get("pricing_report_context") or {}),
    )
    return table


def _llm_refine_tables(message: str, response: Dict[str, Any], tables: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if len(tables) <= 1:
        return [_llm_refine_table(message, response, table) for table in tables]
    max_workers = min(4, len(tables))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(lambda table: _llm_refine_table(message, response, table), tables))


def _llm_refine_report(
    message: str,
    response: Dict[str, Any],
    task_plan: Dict[str, Any],
    task_result_tables: list[Dict[str, Any]],
    report: Dict[str, Any],
) -> Dict[str, Any]:
    client, enabled, reason = _llm_runtime()
    audit = {
        "stage": "pricing_report_composer",
        "used": False,
        "model": client.config_snapshot().get("model"),
        "fallback_reason": reason,
    }
    if not enabled:
        report["llm_audit"] = audit
        return report
    prompt = (
        "你是一线二手车收车定价 Agent 的最终业务结论编辑器。"
        "只基于 deterministic_report 改写，不得新增或修改任何价格、样本数、百分比、外部来源或日报事件。"
        "facts.reflection_memory 是历史反馈反思，只能影响表达重点，不允许覆盖估价结果。"
        "禁止出现算法、模型、RAG、workflow、特征等技术词。不要复制任务表。"
        "必须解释为什么不是可比车中位价/最高价。不要输出对客话术，对客话术由系统安全模板生成。"
        "输出 JSON：{\"why_this_price\":\"\",\"main_risks\":[\"\"]}"
    )
    payload = {
        "user_message": message,
        "task_plan": {
            "title": task_plan.get("title"),
            "need_understanding": task_plan.get("need_understanding"),
            "tasks": task_plan.get("tasks") or [],
        },
        "task_result_tables": task_result_tables,
        "deterministic_report": report,
        "facts": _llm_fact_pack(response),
    }
    result = client.structured_extract(prompt, payload)
    audit.update({"latency_ms": result.latency_ms, "model": result.model or audit["model"]})
    parsed = extract_json_object(result.content) if result.ok else None
    if not isinstance(parsed, dict):
        audit.update({"fallback_reason": result.fallback_reason or "LLM returned non-json"})
        report["llm_audit"] = audit
        return report
    allowed_text = str({
        "report": report,
        "tables": task_result_tables,
    })
    for field, limit in (("why_this_price", 520),):
        candidate = _clip_text(parsed.get(field), limit)
        if _llm_copy_is_safe(candidate, allowed_text):
            report[field] = candidate
    parsed_risks = parsed.get("main_risks")
    if isinstance(parsed_risks, list):
        risks = []
        for item in parsed_risks[:4]:
            candidate = _clip_text(item, 96)
            if _llm_copy_is_safe(candidate, allowed_text):
                risks.append(candidate)
        if risks:
            report["main_risks"] = risks[:4]
            report["main_risk"] = "；".join(risks[:4])
    # Action commands are deterministic business boundaries; the LLM may explain them,
    # but cannot rewrite the executable amounts or instructions.
    _sync_report_blocks(report)
    audit.update({"used": True, "fallback_reason": ""})
    report["llm_audit"] = audit
    return report


def _collect_llm_audit(
    task_plan: Dict[str, Any],
    task_tables: list[Dict[str, Any]],
    final_report: Dict[str, Any],
) -> Dict[str, Any]:
    entries = []
    if task_plan.get("llm_audit"):
        entries.append(task_plan["llm_audit"])
    for table in task_tables:
        if table.get("llm_audit"):
            entries.append(table["llm_audit"])
    if final_report.get("llm_audit"):
        entries.append(final_report["llm_audit"])
    return {
        "stages": entries,
        "all_stages_llm_used": bool(entries) and all(bool(item.get("used")) for item in entries),
        "used_count": sum(1 for item in entries if item.get("used")),
        "total_count": len(entries),
    }


def _llm_fact_pack(response: Dict[str, Any]) -> Dict[str, Any]:
    pricing = response.get("pricing") or {}
    price_result = pricing.get("price_result") or {}
    report_context = response.get("pricing_report_context") or {}
    point = _price_point(price_result)
    lower, upper = _price_range(price_result, point)
    candidates = _selected_comparables(price_result)
    return {
        "slots": response.get("slots") or {},
        "missing_fields": response.get("missing_fields") or [],
        "six_elements": _six_elements(response),
        "point_price_yuan": point,
        "lower_yuan": lower,
        "upper_yuan": upper,
        "baseline_price_yuan": _baseline_price(response),
        "candidate_count": len(candidates),
        "confidence": price_result.get("confidence"),
        "market_state": report_context.get("market_state") or {},
        "market_indicator": report_context.get("market_indicator") or {},
        "daily_report": report_context.get("daily_report") or {},
        "reflection_memory": _reflection_memory_payload(response),
    }


def _retrieve_reflections_for_response(message: str, response: Dict[str, Any]) -> Dict[str, Any]:
    try:
        context = _reflection_context_from_response(message, response)
        bundle = retrieve_for_context(context, top_k=5)
        bundle["context"] = context
        return bundle
    except Exception as exc:
        return {
            "applied_reflections": [],
            "ignored_reflections": [],
            "reason": f"反馈记忆检索失败：{exc}",
            "price_mutation_allowed": False,
        }


def _reflection_context_from_response(message: str, response: Dict[str, Any]) -> Dict[str, Any]:
    pricing = response.get("pricing") if isinstance(response.get("pricing"), dict) else {}
    price_result = pricing.get("price_result") if isinstance(pricing.get("price_result"), dict) else {}
    point = _price_point(price_result)
    six = _six_elements(response)
    vehicle_ctx = vehicle_context_from_slots(six, point)
    return {
        "module": "pricing",
        "task_type": _detect_price_role(message, response) or "purchase_price",
        "city": vehicle_ctx.get("city", ""),
        "brand": vehicle_ctx.get("brand", ""),
        "series": vehicle_ctx.get("series", ""),
        "price_band": vehicle_ctx.get("price_band") or price_band_from_price(point),
        "tags": [],
        "user_message": message,
    }


def _reflection_memory_payload(response: Dict[str, Any]) -> list[Dict[str, Any]]:
    bundle = response.get("reflection_context") if isinstance(response.get("reflection_context"), dict) else {}
    memories = []
    for item in bundle.get("applied_reflections") or []:
        if not isinstance(item, dict):
            continue
        memories.append({
            "reflection_id": item.get("reflection_id"),
            "failure_mode": item.get("failure_mode"),
            "next_time_instruction": item.get("next_time_instruction"),
            "apply_to": item.get("apply_to") or [],
            "policy": "仅优化解释/话术/证据优先级；不得修改模型价格。",
        })
    return memories[:5]


def _build_events(
    agent_intro: str,
    task_plan: Dict[str, Any],
    task_tables: list[Dict[str, Any]],
    final_report: Dict[str, Any],
) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = [
        {"event_type": "agent_intro", "text": agent_intro},
        {"event_type": "plan_started", "title": task_plan.get("title") or "任务规划"},
        {"event_type": "plan_done", "task_plan": {
            "title": task_plan.get("title"),
            "need_understanding": task_plan.get("need_understanding"),
            "summary": task_plan.get("summary") or task_plan.get("need_understanding"),
            "tasks": task_plan.get("tasks") or [],
        }},
    ]
    table_by_task = {table.get("task_id"): table for table in task_tables}
    for task in task_plan.get("tasks") or []:
        task_id = task.get("task_id")
        table = table_by_task.get(task_id)
        if not table and task_plan.get("preview_mode"):
            continue
        events.append({
            "event_type": "step_started",
            "task_id": task_id,
            "step_name": task.get("task_name"),
            "title": task.get("task_name"),
            "display_text": _task_running_message(str(task_id or ""), task),
            "message": _task_running_message(str(task_id or ""), task),
            "business_explanation": running_step_explanation(
                str(task_id or ""),
                str(task.get("task_name") or "任务执行"),
                _task_running_message(str(task_id or ""), task),
            ),
        })
        events.append({
            "event_type": "task_started",
            "task_id": task_id,
            "title": task.get("task_name"),
            "message": _task_running_message(str(task_id or ""), task),
        })
        if str(task_id) != "field_confirmation_task":
            events.append({
                "event_type": "tool_running",
                "task_id": task_id,
                "step_name": task.get("task_name"),
                "title": task.get("task_name"),
                "display_text": _task_source_message(str(task_id or "")),
                "message": _task_source_message(str(task_id or "")),
            })
            events.append({
                "event_type": "tool_searching",
                "task_id": task_id,
                "message": _task_source_message(str(task_id or "")),
            })
        if table:
            business_explanation = table.get("business_explanation") or compose_pricing_step_explanation(
                step_name=str(table.get("title") or task.get("task_name") or ""),
                tool_result=table,
                vehicle_slots={},
                market_context={},
            )
            events.append({
                "event_type": "tool_done",
                "task_id": task_id,
                "step_name": table.get("title"),
                "title": table.get("title"),
                "display_text": _tool_done_message(table),
                "message": _tool_done_message(table),
            })
            events.append({
                "event_type": "llm_explaining",
                "task_id": task_id,
                "step_name": table.get("title"),
                "title": table.get("title"),
                "display_text": "正在把工具结果转成业务判断...",
                "message": "正在把工具结果转成业务判断...",
                "llm_explained": table.get("llm_explained"),
            })
            events.append({
                "event_type": "stage_explaining",
                "task_id": task_id,
                "title": table.get("title"),
                "message": "正在整理这一步的业务含义...",
                "llm_explained": table.get("llm_explained"),
            })
            for row in table.get("rows") or []:
                events.append({
                    "event_type": "task_result_table_delta",
                    "task_id": task_id,
                    "title": table.get("title"),
                    "columns": table.get("columns") or [],
                    "row": row,
                })
            events.append({
                "event_type": "step_done",
                "task_id": task_id,
                "step_name": table.get("title"),
                "title": table.get("title"),
                "step_title": business_explanation.get("step_title") or table.get("title"),
                "status": business_explanation.get("status") or "done",
                "one_line_conclusion": business_explanation.get("one_line_conclusion") or table.get("stage_conclusion") or table.get("summary"),
                "stage_conclusion": table.get("stage_conclusion") or table.get("summary"),
                "business_meaning": table.get("business_meaning"),
                "business_impact": business_explanation.get("business_impact") or table.get("price_impact") or table.get("business_meaning"),
                "next_action": business_explanation.get("next_action") or table.get("action"),
                "key_metrics": business_explanation.get("key_metrics") or [],
                "detail_rows": business_explanation.get("detail_rows") or [],
                "confidence_reason": business_explanation.get("confidence_reason") or "",
                "technical_detail": business_explanation.get("technical_detail") or {},
                "internal_only": business_explanation.get("internal_only", False),
                "customer_safe": business_explanation.get("customer_safe", False),
                "business_explanation": business_explanation,
                "table": table,
            })
            events.append({
                "event_type": "task_done",
                "task_id": task_id,
                "title": table.get("title"),
                "summary": table.get("summary"),
                "table": table,
            })

    if final_report:
        events.append({"event_type": "final_report_started", "title": final_report.get("title")})
        for block in final_report.get("blocks") or []:
            events.append({"event_type": "final_report_delta", "block": block})
        events.append({"event_type": "final_report_done", "report": final_report})
    return events


def _field_confirmation_table(response: Dict[str, Any]) -> Dict[str, Any]:
    missing = set(_normalize_missing_fields(response.get("missing_fields") or []))
    six = _six_elements(response)
    rows = []
    for field in SIX_ELEMENT_FIELDS:
        value = _six_value(field, six)
        status = _field_status(field, value, missing)
        rows.append([
            SLOT_LABELS[field],
            value or "缺失",
            status,
            _field_next_step(field, status),
        ])
    visible_rows = [row for row in rows if row[2] != "完整"] or rows
    return _enforce_compact_table({
        "task_id": "field_confirmation_task",
        "title": "字段确认与补全",
        "stage_conclusion": "车辆信息未齐，补齐后再估价，当前不输出价格。",
        "metric_chips": [f"已识别 {7 - len(missing)} 项", f"待补 {len(missing)} 项"],
        "columns": ["字段", "当前识别", "下一步"],
        "rows": [[row[0], row[1], row[3]] for row in visible_rows],
        "details": _details_text(rows, ["用户输入"]),
        "sources": ["用户输入"],
    })


def _evidence_table(response: Dict[str, Any]) -> Dict[str, Any]:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    candidates = _selected_comparables(price_result)
    candidate_prices = [_candidate_price(row) for row in candidates if _candidate_price(row)]
    point = _price_point(price_result)
    lower, upper = _price_range(price_result, point)
    low = min(candidate_prices) if candidate_prices else lower
    high = max(candidate_prices) if candidate_prices else upper
    baseline = _baseline_price(response)
    count = len(candidates)
    dispersion = _dispersion_label(candidate_prices)
    stage_conclusion = _evidence_stage_conclusion(count, dispersion)
    baseline_impact = "只作上方参照" if baseline and point and point < baseline * 0.93 else "作为市场参照"
    if count <= 1 or _same_display_price(low, high):
        rows = [
            ["证据数量", f"{count}条", _evidence_count_impact(count)],
            ["证据覆盖", "单点参考", "不足以形成价格区间"],
            ["模型市场起点", _wan_text(baseline), baseline_impact],
        ]
    else:
        rows = [
            ["证据数量", f"{count}条", _evidence_count_impact(count)],
            ["价格区间", _range_text(low, high), _dispersion_short_impact(dispersion)],
            ["模型市场起点", _wan_text(baseline), baseline_impact],
        ]
    details = (
        f"可比车价格分布为{dispersion}。可比车中位价只用于观察市场位置，不代表最终建议价；"
        f"本车建议价由七要素、可比车分布和行情边界共同判断。"
    )
    return _enforce_compact_table({
        "task_id": "pricing_evidence_task",
        "title": "可比车证据与市场参考",
        "stage_conclusion": stage_conclusion,
        "metric_chips": [
            f"可比车 {count} 条",
            _evidence_strength_chip(count),
            f"样本{dispersion}",
            "只作市场参考",
        ],
        "business_meaning": "这一步只确定市场参考范围，不直接等同最终收车价。",
        "price_impact": "先确认市场大概位置，高价样本只作为上探参考。",
        "action": "继续看本车里程、配置和过户情况，判断能不能更积极。",
        "columns": ["维度", "发现", "对报价的影响"],
        "rows": rows,
        "details": details,
        "sources": ["内部可比车", "估价结果"],
        "locked_impact_rows": [0, 1, 2],
    })


def _difference_table(response: Dict[str, Any]) -> Dict[str, Any]:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    candidates = _selected_comparables(price_result)
    six = _six_elements(response)
    point = _price_point(price_result)
    baseline = _baseline_price(response)
    candidate_prices = [_candidate_price(row) for row in candidates if _candidate_price(row)]
    dispersion = _dispersion_label(candidate_prices)
    diff = abs(point - baseline) if point and baseline else 0.0
    mileage_impact = _mileage_impact(six, candidates)
    color_impact = _transfer_color_impact(six)
    rows = [
        ["车型配置", f"已锁定 {_short_vehicle_label(response)}", "避免串到泛车系"],
        ["里程", _short_mileage_finding(six, candidates), _short_direction(mileage_impact)],
        ["样本结构", _sample_structure_finding(dispersion), _sample_structure_impact(dispersion)],
    ]
    details = (
        f"可比车中位价 {_wan_text(baseline)}，建议价 {_wan_text(point)}，差异 {_wan_text(diff)}。"
        "这不是简单按中位价打折，而是先看定价模型和相近车位置，再结合当前车七要素形成业务参考价。"
        f"过户与颜色判断：{color_impact}。"
    )
    return _enforce_compact_table({
        "task_id": "vehicle_difference_task",
        "title": "车辆差异与价格修正",
        "stage_conclusion": _difference_stage_conclusion(baseline, point, dispersion, mileage_impact),
        "metric_chips": [
            f"建议价 {_wan_text(point)}",
            _factor_chip("里程", mileage_impact),
            _factor_chip("车况条件", color_impact),
            _sample_structure_impact(dispersion),
        ],
        "business_meaning": "这一步判断本车相对可比车是加分还是压价。",
        "price_impact": _difference_price_impact(mileage_impact, dispersion),
        "action": "校验收售价格梯度，确定最高收车价边界。",
        "columns": ["维度", "发现", "对报价的影响"],
        "rows": rows,
        "details": details,
        "sources": ["车辆七要素", "内部可比车", "估价结果"],
        "locked_impact_rows": [0, 1, 2],
    })


def _risk_table(response: Dict[str, Any]) -> Dict[str, Any]:
    report_context = response.get("pricing_report_context") or {}
    market_indicator = report_context.get("market_indicator") if isinstance(report_context.get("market_indicator"), dict) else {}
    market_state = report_context.get("market_state") if isinstance(report_context.get("market_state"), dict) else {}
    metrics = market_indicator.get("metrics") if isinstance(market_indicator.get("metrics"), dict) else {}
    if not metrics and isinstance(market_state.get("metrics"), dict):
        metrics = market_state.get("metrics") or {}
    market_label = str(market_state.get("market_category_label") or market_state.get("recommendation_label") or "暂无强相关行情")
    cycle = _money(metrics.get("avg_deal_cycle"))
    change_14d = _ratio(metrics.get("price_change_14d"))
    risks = [str(item) for item in (market_state.get("risks") or []) if item]
    daily_note, daily_detail = _daily_relevance(response)
    rows = [
        ["城市行情", market_label, _market_action_short(market_state)],
        ["周转", f"成交周期 {_days_text(cycle)}", _cycle_impact(cycle)],
        ["价格波动", f"14天 {_percent_text(change_14d)}", _price_change_impact(change_14d)],
    ]
    details = "；".join(item for item in [
        f"90天成交 {metrics.get('deal_sample_90d', '-')} 辆，在售 {metrics.get('listing_count', '-')} 辆，当前库存 {metrics.get('current_inventory', '-')} 辆。",
        "；".join(risks[:2]),
        daily_note,
        daily_detail,
    ] if item)
    return _enforce_compact_table({
        "task_id": "risk_boundary_task",
        "title": "行情风险与追价边界",
        "stage_conclusion": _risk_stage_conclusion(market_label, cycle, change_14d),
        "metric_chips": [
            f"90天成交 {metrics.get('deal_sample_90d', '-')} 辆",
            f"在售 {metrics.get('listing_count', '-')} 辆",
            f"成交周期 {_days_text(cycle)}",
            f"14天价格 {_percent_text(change_14d)}",
        ],
        "business_meaning": "这一步判断能不能追价，以及追到哪里必须停。",
        "price_impact": _risk_price_impact(cycle, change_14d),
        "action": "先按建议沟通价推进，车况检测优秀时再申请小幅上调。",
        "columns": ["维度", "发现", "对报价的影响"],
        "rows": rows,
        "daily_note": daily_note,
        "details": details,
        "sources": ["城市行情", "上传日报"],
        "locked_impact_rows": [0, 1, 2],
    })


def _quote_acceptance_table(message: str, response: Dict[str, Any], task_plan: Dict[str, Any]) -> Dict[str, Any]:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    point = _price_point(price_result)
    lower, upper = _price_range(price_result, point)
    b2c_point, b2c_lower, b2c_upper = _b2c_range(price_result)
    amount = _money(task_plan.get("quote_amount_yuan")) or _extract_user_quote_yuan(message, response)
    price_role = str(task_plan.get("price_role") or _detect_price_role(message, response))
    rows: list[list[str]] = []
    if price_role == "listing_price":
        reference = _range_text(b2c_lower, b2c_upper) if b2c_lower or b2c_upper else "暂缺建议挂牌区间"
        rows.append(["挂牌价", _wan_text(amount), _listing_conclusion(amount, b2c_point, b2c_lower, b2c_upper)])
    elif price_role == "customer_offer":
        reference = _range_text(b2c_lower, b2c_upper) if b2c_lower or b2c_upper else _range_text(lower, upper)
        rows.append(["客户报价", _wan_text(amount), _customer_offer_conclusion(amount, b2c_point, b2c_lower, b2c_upper)])
        rows.append(["市场参考", reference, "先判断市场位置"])
        rows.append(["毛利", "成本信息不足", "补成本后再判断"])
    else:
        rows.append(["当前报价", _wan_text(amount), _purchase_conclusion(amount, point, lower, upper)])
        rows.append(["建议锚点", _wan_text(point), "围绕建议价谈"])
        rows.append(["追价上限", _wan_text(upper), "超过上限不追"])
    conclusion = rows[0][2] if rows else "已完成报价可接受性判断。"
    return _enforce_compact_table({
        "task_id": "quote_acceptance_task",
        "title": _quote_task_name(price_role),
        "stage_conclusion": conclusion,
        "metric_chips": [f"当前报价 {_wan_text(amount)}", f"建议价 {_wan_text(point)}", f"上限 {_wan_text(upper)}"],
        "columns": ["判断项", "发现", "业务结论"],
        "rows": rows,
        "details": f"参考边界：{reference if price_role != 'purchase_price' else _range_text(lower, upper)}。",
        "sources": ["用户报价", "估价结果"],
    })


def _low_confidence_table(response: Dict[str, Any]) -> Dict[str, Any]:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    candidates = _selected_comparables(price_result)
    confidence = str(price_result.get("confidence") or "MEDIUM").upper()
    rows = [
        ["内部证据", f"可比车 {len(candidates)} 条", "按低置信使用"],
        ["参考可信度", _confidence_label(confidence), "按保守价格边界使用"],
        ["外部参考", "本轮未启用", "不冒充外部证据"],
    ]
    return _enforce_compact_table({
        "task_id": "low_confidence_task",
        "title": "本次定价置信度说明",
        "stage_conclusion": "可比证据不足，本次价格只能作为低置信参考。",
        "metric_chips": [f"可比车 {len(candidates)} 条", f"可信度 {_confidence_label(confidence)}"],
        "columns": ["维度", "发现", "对报价的影响"],
        "rows": rows,
        "details": "置信度反映可比证据充足程度；实车检测与整备成本仍会影响最终成交价。",
        "sources": ["内部可比车", "估价结果"],
    })


def _agent_intro(message: str, response: Dict[str, Any], task_plan: Dict[str, Any]) -> str:
    missing = response.get("missing_fields") or []
    slots = response.get("slots") or {}
    vehicle = _vehicle_title(_six_elements(response), response)
    city = slots.get("city") or (_six_elements(response).get("city")) or "本地"
    amount = _money(task_plan.get("quote_amount_yuan"))
    role = str(task_plan.get("price_role") or "purchase_price")
    if missing:
        return "收到您的请求，但当前车辆信息还不完整。我会先确认缺哪些关键字段，避免直接生成不可靠报价。"
    if amount and role == "purchase_price":
        return f"收到您的请求，我会先判断 {_wan_text(amount)} 相对{vehicle}市场参考价是偏高还是偏低，再给出能不能收和最高追价建议。"
    if amount and role == "listing_price":
        return f"收到您的请求，我会判断 {_wan_text(amount)} 作为{vehicle}挂牌价是否合理，并说明对周转和议价的影响。"
    if amount and role == "customer_offer":
        return f"收到您的请求，我会判断客户给 {_wan_text(amount)} 相对{vehicle}市场参考是否可接受；如果缺成本，会明确说明不能判断毛利。"
    return f"收到您的请求，我会调用这台{vehicle}的定价模型，核对七要素和相近可比车，再给出完整收售价格与最高收车边界。"


def _compact_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    role = str(plan.get("price_role") or "purchase_price")
    if plan.get("can_execute_pricing"):
        title = {
            "purchase_price": "收车估价可行性分析",
            "listing_price": "挂牌价合理性分析",
            "customer_offer": "客户报价可接受性分析",
        }.get(role, str(plan.get("title") or "定价任务分析"))
        summary = {
            "purchase_price": "判断这台车的建议收车价和最高收车价。",
            "listing_price": "判断这台车的合理挂牌价和周转边界。",
            "customer_offer": "判断客户报价是否可接受，以及成交边界。",
        }.get(role, _clip_text(plan.get("need_understanding"), 48))
        plan["title"] = title
        plan["need_understanding"] = summary
        plan["summary"] = summary
    else:
        plan["title"] = _clip_text(plan.get("title"), 32)
        plan["need_understanding"] = _clip_text(plan.get("need_understanding"), 72)
        plan["summary"] = plan["need_understanding"]
    tasks = []
    for item in (plan.get("tasks") or [])[:5]:
        if not isinstance(item, dict):
            continue
        tasks.append({
            **item,
            "task_name": _clip_text(item.get("task_name"), 24),
            "task_goal": _clip_text(item.get("task_goal"), 44),
        })
    plan["tasks"] = tasks
    return plan


def _enforce_compact_table(table: Dict[str, Any]) -> Dict[str, Any]:
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    compact_rows: list[list[str]] = []
    for row in rows[:MAX_VISIBLE_TABLE_ROWS]:
        if not isinstance(row, list):
            continue
        values = list(row[:3])
        while len(values) < 3:
            values.append("-")
        compact_rows.append([
            _clip_text(values[0], 12),
            _clip_text(values[1], MAX_FINDING_CHARS),
            _clip_text(values[2], MAX_IMPACT_CHARS),
        ])
    conclusion = _clip_text(table.get("stage_conclusion") or table.get("summary"), 64)
    table["stage_conclusion"] = conclusion
    table["summary"] = conclusion
    table["columns"] = [str(item) for item in (table.get("columns") or ["维度", "发现", "对报价的影响"])[:3]]
    table["rows"] = compact_rows
    compact_chips: list[str] = []
    for item in table.get("metric_chips") or []:
        chip = _clip_text(item, 32)
        if chip and chip not in compact_chips:
            compact_chips.append(chip)
        if len(compact_chips) >= 4:
            break
    table["metric_chips"] = compact_chips
    table["sources"] = [
        _clip_text(item, MAX_SOURCE_CHARS)
        for item in (table.get("sources") or [])[:4]
        if str(item).strip()
    ]
    table["trust_sources"] = [
        _clip_text(item, MAX_SOURCE_CHARS)
        for item in (table.get("trust_sources") or table.get("sources") or [])[:4]
        if str(item).strip()
    ]
    table["why_trust"] = _clip_text(table.get("why_trust"), 112)
    table["business_meaning"] = _clip_text(table.get("business_meaning"), 96)
    table["price_impact"] = _clip_text(table.get("price_impact"), 88)
    table["action"] = _clip_text(table.get("action"), 88)
    table["need_review"] = _clip_text(table.get("need_review"), 112)
    table["llm_explained"] = bool(table.get("llm_explained"))
    table["details"] = str(table.get("details") or "").strip()
    return table


def _clip_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip("，；。 ") + "…"


def _details_text(rows: list[list[Any]], sources: list[str]) -> str:
    row_text = "；".join(" / ".join(str(cell) for cell in row) for row in rows)
    return f"完整识别：{row_text}。数据来源：{'、'.join(sources)}。"


def _evidence_stage_conclusion(count: int, dispersion: str) -> str:
    if count < 5:
        dispersion_note = f"，价格{dispersion}" if dispersion else ""
        return f"页面展示 {count} 条严格可比车{dispersion_note}，但样本数量偏少，只用于核对定价模型参考点，不单独决定最终置信度。"
    if dispersion == "集中":
        return f"命中 {count} 条可比车，价格集中，建议价可信度较高。"
    return f"命中 {count} 条可比车，但价格{dispersion}，不能直接按高价样本追。"


def _dispersion_short_impact(dispersion: str) -> str:
    if dispersion == "集中":
        return "价格集中，可作主要参考"
    if dispersion in {"中等分散", "分散"}:
        return "分散，需保守"
    return "证据不足，降置信使用"


def _short_vehicle_label(response: Dict[str, Any]) -> str:
    slots = response.get("slots") if isinstance(response.get("slots"), dict) else {}
    label = slots.get("trim") or slots.get("model") or slots.get("series")
    if not label:
        label = _vehicle_title(_six_elements(response), response)
    return _clip_text(label, 14)


def _short_mileage_finding(six: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    current = _money(six.get("mileage_wan_km"))
    values = [_money(row.get("mileage_wan_km") or row.get("mileage")) for row in candidates]
    values = [value for value in values if value]
    if not current:
        return "里程信息不足"
    if not values:
        return f"{current:g}万公里"
    avg = sum(values) / len(values)
    if current < avg * 0.85:
        return f"{current:g}万公里，低于可比车"
    if current > avg * 1.15:
        return f"{current:g}万公里，高于可比车"
    return f"{current:g}万公里，接近可比车"


def _short_direction(text: str) -> str:
    if "偏低" in text or "有支撑" in text:
        return "里程低，有支撑" if "里程" in text or "支撑" in text else "有价格支撑"
    if "偏高" in text or "保守" in text:
        return "需保守报价"
    if "影响较小" in text or "常见范围" in text or "主流颜色" in text:
        return "影响较小"
    if "小众" in text or "买家偏好" in text or "谨慎追高" in text:
        return "颜色影响小，不溢价"
    return _clip_text(text, 18) or "方向影响有限"


def _factor_chip(label: str, text: str) -> str:
    if "偏低" in text or "有支撑" in text:
        return f"{label}有支撑"
    if "偏高" in text or "保守" in text or "谨慎" in text:
        return f"{label}需留空间"
    if label == "里程":
        return "里程接近同类车"
    return "流通条件正常"


def _sample_structure_finding(dispersion: str) -> str:
    if dispersion == "集中":
        return "价格集中"
    if dispersion in {"中等分散", "分散"}:
        return "高价样本偏多" if dispersion == "分散" else "样本有一定分散"
    return "样本不足"


def _sample_structure_impact(dispersion: str) -> str:
    if dispersion == "集中":
        return "可接近建议价谈"
    if dispersion in {"中等分散", "分散"}:
        return "不按高价追"
    return "按低置信使用"


def _difference_stage_conclusion(baseline: float, point: float, dispersion: str, mileage_impact: str) -> str:
    if point < baseline:
        tail = "高价样本不能直接照用" if dispersion != "集中" else "仍需按车辆差异执行"
        return f"最终建议价更保守；{_short_direction(mileage_impact)}，但{tail}。"
    if point > baseline:
        return "当前车辆条件对价格有支撑，可以围绕建议价推进。"
    return "当前车辆条件未触发明显上调或下压，围绕建议价推进。"


def _difference_price_impact(mileage_impact: str, dispersion: str) -> str:
    if "偏低" in mileage_impact or "支撑" in mileage_impact:
        base = "可以比保守价略积极"
    elif "偏高" in mileage_impact or "保守" in mileage_impact:
        base = "里程或车况预期会压价"
    else:
        base = "按建议价附近沟通"
    if dispersion != "集中":
        return f"{base}，但不能直接追到高价样本。"
    return f"{base}，再结合实车检测决定是否上调。"


def _ratio(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number / 100.0 if abs(number) > 1 else number


def _percent_text(value: float) -> str:
    if not value:
        return "-"
    return f"{value * 100:+.1f}%"


def _days_text(value: float) -> str:
    return f"{value:.1f} 天" if value else "-"


def _market_action_short(market_state: Dict[str, Any]) -> str:
    label = str(market_state.get("market_category_label") or market_state.get("recommendation_label") or "")
    if any(word in label for word in ("弱", "阴跌", "急跌", "谨慎")):
        return "按区间下沿执行"
    if any(word in label for word in ("结构性", "重点", "机会")):
        return "可纳入重点池"
    if any(word in label for word in ("强", "流动", "上涨")):
        return "可接近建议价谈"
    return "不支持额外追高"


def _cycle_impact(cycle: float) -> str:
    if not cycle:
        return "周期不足，保守使用"
    if cycle >= 35:
        return "成交偏慢，不宜追高"
    if cycle <= 25:
        return "周转较快，有支撑"
    return "周转一般，守建议价"


def _price_change_impact(change: float) -> str:
    if change <= -0.10:
        return "按区间下沿守价"
    if change < 0:
        return "行情偏弱，谨慎追价"
    if change >= 0.10:
        return "波动较大，守上限"
    if change > 0:
        return "行情有支撑"
    return "暂无明确方向"


def _risk_stage_conclusion(market_label: str, cycle: float, change_14d: float) -> str:
    if change_14d <= -0.10 or cycle >= 35:
        return f"{market_label}，但成交偏慢或价格波动大，报价要守上限。"
    if change_14d > 0 and cycle and cycle <= 25:
        return f"{market_label}且周转较快，行情有支撑，可以接近建议价谈。"
    return f"{market_label}，行情只用于判断追价边界，不直接改写报价。"


def _risk_price_impact(cycle: float, change_14d: float) -> str:
    if change_14d <= -0.10 or cycle >= 35:
        return "可以收，但报价要守住上限，不能因为客户坚持高价就继续追。"
    if change_14d > 0 and cycle and cycle <= 25:
        return "行情有支撑，可以围绕建议价积极推进。"
    return "行情不直接改价，只用于约束追价边界。"


def _daily_relevance(response: Dict[str, Any]) -> tuple[str, str]:
    report_context = response.get("pricing_report_context") or {}
    daily = report_context.get("daily_report") if isinstance(report_context.get("daily_report"), dict) else {}
    if not daily:
        return "日报暂无强相关事件，不改写报价。", ""
    slots = response.get("slots") if isinstance(response.get("slots"), dict) else {}
    six = _six_elements(response)
    tokens = {
        str(slots.get("brand") or "").strip(),
        str(slots.get("series") or "").strip(),
        str(slots.get("trim") or "").strip(),
        str(six.get("standard_vehicle") or "").strip(),
    }
    tokens = {token for token in tokens if len(token) >= 2}
    texts: list[str] = []
    for item in daily.get("evidence") or []:
        if isinstance(item, dict):
            text = item.get("summary") or item.get("text") or item.get("title")
        else:
            text = item
        if text:
            texts.append(str(text))
    texts.extend(str(item) for item in (daily.get("core_conclusions") or []) if item)
    for text in texts:
        if any(token in text for token in tokens):
            return "日报事件可能影响客户预期，需要纳入议价话术。", _clip_text(text, 140)
    return "日报暂无强相关事件，不改写报价。", ""


def _why_this_price(
    *,
    response: Dict[str, Any],
    task_result_tables: list[Dict[str, Any]],
    count: int,
    low: float,
    high: float,
    baseline: float,
    point: float,
    dispersion: str,
    purchase_lower: float,
    purchase_upper: float,
) -> str:
    six = _six_elements(response)
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    candidates = _selected_comparables(price_result)
    mileage_impact = _mileage_impact(six, candidates)
    six_notes = _six_direction_notes(response, six, mileage_impact)
    return (
        f"先由定价模型给出建议收车价 {_wan_text(point)}，合理收车区间 {_range_text(purchase_lower, purchase_upper)}。"
        f"再逐项核对七要素：{six_notes}。"
        "最后校验挂牌价、实际售卖价、最高收车价和预计实际收车价的大小关系；"
        "建议价用于谈判，超过最高收车价必须人工确认。"
    )


def _price_reasoning(
    *,
    response: Dict[str, Any],
    baseline: float,
    point: float,
    high: float,
    dispersion: str,
    task_result_tables: list[Dict[str, Any]],
    mileage_impact: str,
    daily_note: str,
) -> Dict[str, Any]:
    six = _six_elements(response)
    color = str(six.get("color") or "").strip()
    color_direction = "neutral"
    color_text = "当前结构化结果没有给出独立颜色调价系数，本轮不据此加价或压价。"
    color_finding = color or "颜色未明确"

    if "偏低" in mileage_impact or "支撑" in mileage_impact:
        mileage_direction = "support_up"
        mileage_text = "里程低，对价格有支撑。"
    elif "偏高" in mileage_impact or "保守" in mileage_impact:
        mileage_direction = "pressure_down"
        mileage_text = "里程偏高，后续买家会更关注车况和整备成本。"
    else:
        mileage_direction = "neutral"
        mileage_text = "里程没有触发明显加价或压价。"

    evidence_direction = "pressure_down" if dispersion != "集中" else "neutral"
    evidence_text = "可比车价格较分散，需要保守使用高价样本。" if dispersion != "集中" else "可比车价格接近，可用于校验方向；证据强度仍取决于样本数量与新鲜度。"
    diff_text = _wan_text(abs(point - baseline)) if point and baseline else ""
    return {
        "market_baseline": {
            "summary": "系统先用相近车源形成市场参考点。",
            "baseline_price": _wan_text(baseline),
            "how_to_use": "只代表相近车在市场上的参考位置，不等于这台车最终收车价。",
            "internal_only": True,
            "customer_safe": False,
        },
        "adjustment_logic": [
            {
                "factor": "里程",
                "finding": _six_value("mileage_wan_km", six) or "里程信息不足",
                "direction": mileage_direction,
                "business_text": mileage_text,
            },
            {
                "factor": "颜色",
                "finding": color_finding,
                "direction": color_direction,
                "business_text": color_text,
            },
            {
                "factor": "可比证据",
                "finding": evidence_text,
                "direction": evidence_direction,
                "business_text": "可比证据用于解释模型基线和置信边界，不替代车辆七要素。",
            },
        ],
        "final_bridge": (
            f"因此不是简单按中位价或最高价收，而是以相近车参考价为起点，"
            f"结合本车七要素和可比证据后，给出 {_wan_text(point)} 作为更稳妥的沟通锚点。"
            + (f" 这属于综合修正结果，和市场参考点相差 {diff_text}。" if diff_text else "")
        ),
        "why_not_highest": (
            f"最高样本 {_wan_text(high)} 的价格口径或车辆条件没有与本车完全对齐，"
            "因此只用于校验市场方向，不能直接当成本车收车价。"
        ),
        "why_not_customer_expected": "客户看到的多是挂牌价或个别高价，不等于真实可成交价格。",
        "dispersion": dispersion,
        "daily_note": "",
        "internal_only": True,
        "customer_safe": False,
    }


def _summary_why(
    response: Dict[str, Any],
    candidate_count: int,
    dispersion: str,
    task_result_tables: list[Dict[str, Any]],
    daily_note: str,
) -> str:
    six = _six_elements(response)
    candidates = _selected_comparables(((response.get("pricing") or {}).get("price_result") or {}))
    mileage = _short_direction(_mileage_impact(six, candidates))
    return (
        f"内部相近车源数量{'够' if candidate_count >= 10 else '偏少'}，价格{dispersion}；"
        f"本车{mileage}；定价模型已按七要素修正，并校验收售价梯度。"
    )


def _summary_action(point: float, upper: float, dispersion: str) -> str:
    pressure = "可比车价格分散 + 车况待检" if dispersion != "集中" else "车况待检 + 整备成本"
    return f"先用 {_wan_text(point)} 沟通，客户坚持高价时用“{pressure}”解释，超过 {_wan_text(upper)} 不追。"


def _decision_summary(
    *,
    response: Dict[str, Any],
    point: float,
    upper: float,
    confidence: str,
    candidate_count: int,
    dispersion: str,
    task_result_tables: list[Dict[str, Any]],
    daily_note: str,
) -> Dict[str, str]:
    decision = _decision_label(
        response=response,
        confidence=confidence,
        candidate_count=candidate_count,
        dispersion=dispersion,
        risk_summary="",
    )
    next_action = "先核对实车与七要素是否一致，再按建议价沟通；超过最高收车价需人工确认"
    reason_bits = []
    if dispersion != "集中":
        reason_bits.append("相近车价格不稳定")
    if candidate_count < 5:
        reason_bits.append("可比证据偏少")
    return {
        "decision": decision,
        "communication_price": f"{_wan_text(point)} 左右" if point else "-",
        "customer_talk_price": _customer_talk_price(point),
        "internal_target_price": _wan_text(point) if point else "-",
        "internal_chase_limit": _wan_text(upper) if upper else "-",
        "internal_upper_bound": _wan_text(upper) if upper else "-",
        "show_limit_to_customer": "否",
        "next_action": next_action,
        "do_not_do": "不要直接按网上高价或最高可比样本追价。",
        "reason": "；".join(reason_bits[:2]) or "七要素完整，定价模型与价格梯度校验通过",
    }


def _customer_talk_price(point: float) -> str:
    if not point:
        return "建议价附近"
    wan = point / 10000
    integer = int(wan)
    decimal = wan - integer
    if decimal >= 0.65:
        return f"{integer}万多"
    if decimal >= 0.20:
        return f"{integer}万出头"
    return f"{integer}万左右"


def _decision_label(
    *,
    response: Dict[str, Any],
    confidence: str,
    candidate_count: int,
    dispersion: str,
    risk_summary: str,
) -> str:
    # The first screen must state a business decision. Confidence is rendered
    # separately as model/evidence/execution confidence; never turn it into a
    # demo-like headline.
    return "已形成收车建议，请按建议价和最高边界执行"


def _build_pricing_ai_summary(
    *,
    six: Dict[str, Any],
    point: float,
    lower: float,
    upper: float,
    baseline: float,
    candidate_count: int,
    comparable_low: float,
    comparable_high: float,
    confidence: str,
    dispersion: str,
    sale_profit: Dict[str, Any],
    why_this_price: str,
) -> Dict[str, Any]:
    confidence_label = _confidence_label(confidence)
    sale_price = _price_yuan(sale_profit.get("sale_price_yuan"))
    max_price = _price_yuan(sale_profit.get("max_c2b_price_yuan")) or upper
    model_bridge = f"定价模型的市场参考起点为 {_wan_text(baseline)}，本车建议收车价为 {_wan_text(point)}。"
    comparable_bridge = (
        f"本次仅有 1 个可展示证据参考点 {_wan_text(comparable_low)}，不足以形成价格区间；该证据只校验方向。"
        if candidate_count == 1 or (candidate_count and _same_display_price(comparable_low, comparable_high))
        else (
            f"本次展示核对 {candidate_count} 条严格可比车，价格主要分布在 {_range_text(comparable_low, comparable_high)}；"
            f"这些样本用于校验价格方向，高价样本不直接作为追价依据。"
            if candidate_count
            else "本次没有命中可展示的严格可比车，最终价格由定价模型、七要素和多源市场基线共同校验。"
        )
    )
    seven_elements = "、".join(
        str(value)
        for value in (
            six.get("standard_vehicle") or six.get("trim") or six.get("series"),
            six.get("first_license_date") or six.get("first_license_year"),
            f"{six.get('mileage_wan_km')}万公里" if six.get("mileage_wan_km") not in (None, "") else "",
            six.get("city"),
            f"{six.get('transfer_count')}次过户" if six.get("transfer_count") not in (None, "") else "",
            six.get("color"),
            six.get("condition_group") or six.get("inspection_grade") or six.get("condition"),
        )
        if value not in (None, "")
    )
    decision = (
        f"预计实际收车价为 {_wan_text(point)}，可谈区间 {_range_text(lower, upper)}；"
        f"最高不超过 {_wan_text(max_price)}。"
    )
    if sale_price:
        decision += f"按预计实际售车价 {_wan_text(sale_price)} 测算收售价差；如需扣减个性化成本，可在下方利润计算器中填写。"
    return {
        "title": "收车决策摘要",
        "safe_purchase_price_yuan": point,
        "safe_purchase_low_yuan": lower,
        "safe_purchase_high_yuan": upper,
        "max_purchase_price_yuan": max_price,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "decision": decision,
        "why": f"{model_bridge}{comparable_bridge}",
        "why_items": [
            model_bridge,
            comparable_bridge,
            f"本次使用的车辆信息：{seven_elements or '车辆信息待补充'}。",
        ],
        "data_analysis": [
            {"label": "定价模型参考起点", "value": _wan_text(baseline), "explanation": "连接车型历史价格与本车条件"},
            {"label": "严格可比车", "value": f"{candidate_count} 条", "explanation": "用于复核模型参考点，不单独决定置信度"},
            {"label": "本车七要素", "value": "已核对", "explanation": seven_elements or "七要素完整"},
            {"label": "预计实际售车价", "value": _wan_text(sale_price), "explanation": "校验利润空间与价格顺序"},
        ],
        "source_scope": "仅使用定价模型、内部成交/在售证据、外部市场参考和当前车辆七要素；不使用选品结论。",
    }


def _comparable_evidence_items(response: Dict[str, Any], six: Dict[str, Any]) -> list[Dict[str, Any]]:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    current_mileage = _money(six.get("mileage_wan_km"))
    current_city = str(six.get("city") or "").strip()
    current_transfer = six.get("transfer_count")
    current_model = str(six.get("standard_vehicle") or six.get("trim") or six.get("series") or "").strip()
    rows: list[Dict[str, Any]] = []
    for index, item in enumerate(_selected_comparables(price_result)[:12]):
        title = str(item.get("title") or item.get("vehicle") or item.get("standard_vehicle") or item.get("model") or item.get("trim") or "").strip()
        mileage = _money(item.get("mileage_wan_km") or item.get("mileage"))
        city = str(item.get("city") or "").strip()
        transfer = item.get("transfer_count")
        source = str(item.get("source_family") or item.get("source") or "").strip()
        price_role = str(item.get("price_role") or "").strip().upper()
        price_type = (
            "内部收车" if "C2B" in price_role or "c2b" in source.lower() or "purchase" in source.lower() or item.get("c2b_price") not in (None, "")
            else "市场在售" if price_role.startswith("EXTERNAL_") or "listing" in source.lower() or "external" in source.lower()
            else "内部售车" if "B2C" in price_role or "b2c" in source.lower() or "sale" in source.lower() or item.get("b2c_price") not in (None, "")
            else "市场参考"
        )
        date = str(item.get("event_time") or item.get("data_date") or item.get("event_date") or item.get("created_at") or "").strip()[:10]
        differences: list[str] = []
        if current_model and title and current_model not in title and title not in current_model:
            differences.append("款型/配置不同")
        if current_mileage and mileage:
            delta = mileage - current_mileage
            if abs(delta) >= 0.5:
                differences.append(f"里程{'高' if delta > 0 else '低'}{abs(delta):.1f}万公里")
        if current_city and city and current_city != city:
            differences.append(f"城市为{city}")
        if current_transfer not in (None, "") and transfer not in (None, "") and str(current_transfer) != str(transfer):
            differences.append(f"过户{transfer}次")
        level = str(item.get("retrieval_level") or item.get("semantic_tier") or "").upper()
        weight = _money(item.get("final_normalized_weight") or item.get("final_weight") or item.get("weight"))
        if level in {"L1", "L2"} or not differences:
            inclusion = "车型和关键条件接近，纳入主要校验"
        else:
            inclusion = "用于校验价格方向，因条件差异已降权"
        has_vehicle_detail = bool(title or mileage or city or transfer not in (None, "") or date)
        if not title:
            title = "相近车源" if has_vehicle_detail else (f"{source}价格证据" if source else "市场聚合价格证据")
        rows.append({
            "rank": index + 1,
            "title": title,
            "model_year": item.get("model_year"),
            "trim": item.get("trim"),
            "mileage_wan_km": mileage or None,
            "city": city or None,
            "transfer_count": transfer,
            "price_yuan": _candidate_price(item),
            "price_type": price_type,
            "evidence_source": source or None,
            "data_date": date or None,
            "differences": differences or ["关键条件接近"],
            "inclusion_reason": (
                inclusion
                if has_vehicle_detail
                else "仅用于校验市场价格方向；缺少车辆明细，不能作为严格同条件可比车"
            ),
            "weight": weight or None,
        })
    return rows


def _confidence_breakdown(
    *,
    response: Dict[str, Any],
    model_confidence: str,
    comparables: list[Dict[str, Any]],
) -> Dict[str, Any]:
    six = _six_elements(response)
    model_level = _confidence_label(model_confidence)
    count = len(comparables)
    evidence_level = "高" if count >= 8 else "中" if count >= 3 else "低"
    dated = [str(item.get("data_date") or "") for item in comparables if str(item.get("data_date") or "").startswith("20")]
    freshness = "有日期记录" if dated else "日期证据不足"
    filled = sum(1 for key in SIX_ELEMENT_FIELDS if six.get(key) not in (None, ""))
    inspection_verified = bool(
        six.get("inspection_verified")
        or six.get("has_real_inspection")
        or str(six.get("inspection_status") or "").lower() in {"verified", "completed", "已检测", "已验车"}
    )
    execution_level = "高" if filled == len(SIX_ELEMENT_FIELDS) and inspection_verified else "中" if filled >= 6 else "低"
    execution_suffix = "已完成实车检测" if inspection_verified else "待实车检测"
    order = {"低": 0, "中": 1, "高": 2}
    overall = min((model_level, evidence_level, execution_level), key=lambda item: order.get(item, 1))
    return {
        "overall": overall,
        "model": {"level": model_level, "reason": "由定价模型覆盖、历史误差和数据稳定性计算"},
        "evidence": {"level": evidence_level, "reason": f"严格可比车 {count} 条，{freshness}"},
        "execution": {"level": execution_level, "reason": f"车辆信息已识别 {filled}/{len(SIX_ELEMENT_FIELDS)} 项，{execution_suffix}"},
    }


def _price_formation_steps(
    *,
    six: Dict[str, Any],
    baseline: float,
    point: float,
    upper: float,
    sale_price: float,
    price_reasoning: Dict[str, Any],
    comparable_count: int,
) -> list[Dict[str, Any]]:
    adjustments = []
    for item in (price_reasoning.get("adjustment_logic") or [])[:4]:
        text = str(item.get("business_text") or "").strip()
        if text:
            adjustments.append(f"{item.get('factor') or '车辆条件'}：{text}")
    return [
        {"title": "定价模型市场参考", "conclusion": _wan_text(baseline), "detail": "作为同车型历史价格与当前市场的参考起点，不直接等于最终收车价。"},
        {"title": "当前车辆条件调整", "conclusion": "；".join(adjustments) or "没有可验证的单项调整结论", "detail": "只展示结构化规则实际产生的影响；没有数据的要素不编造结论。"},
        {"title": "可比车证据校验", "conclusion": f"严格可比车 {comparable_count} 条", "detail": "用于校验方向和边界；样本少时不单独支撑高置信决策。"},
        {"title": "收售价格梯度", "conclusion": f"建议收车 {_wan_text(point)}，预计售车 {_wan_text(sale_price)}，最高收车 {_wan_text(upper)}", "detail": "统一校验挂牌价、实际售车价、建议收车价和最高收车价的大小关系。"},
    ]


def _customer_vehicle_condition_clause(six: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    parts: list[str] = []
    mileage_impact = _mileage_impact(six, candidates)
    mileage = _money(six.get("mileage_wan_km"))
    if "偏低" in mileage_impact or "支撑" in mileage_impact:
        parts.append("这台车里程不高，是价格上的加分项")
    elif "偏高" in mileage_impact or "保守" in mileage_impact:
        parts.append("这台车里程偏高，后续买家会更关注车况和整备成本")
    # Do not infer a colour/transfer premium from common sense. Those claims
    # are only allowed when a structured adjustment trace exists elsewhere in
    # the report. Here we keep only a mileage conclusion actually supported by
    # the selected comparable set.
    transfer = _money(six.get("transfer_count"))
    if transfer > 2:
        parts.append("过户次数偏多，需要把后续买家顾虑算进去")
    return "，".join(parts[:2]) or "当前按常规可交易车况估算，最终要以实车检测为准"


def _customer_market_clause(response: Dict[str, Any], dispersion: str, daily_note: str) -> str:
    if dispersion != "集中":
        return "相近车价格分布较散，个别高价不能直接当作这台车的成交价"
    return "相近车价格分布较集中，可以围绕定价模型建议价推进沟通"


def _six_direction_notes(response: Dict[str, Any], six: Dict[str, Any], mileage_impact: str) -> str:
    notes: list[str] = []
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    trace = price_result.get("price_trace") if isinstance(price_result.get("price_trace"), dict) else {}
    element_trace = trace.get("element_adjustment_trace") if isinstance(trace.get("element_adjustment_trace"), dict) else {}
    if "偏低" in mileage_impact or "支撑" in mileage_impact:
        notes.append("里程偏低，对价格有支撑")
    elif "偏高" in mileage_impact or "保守" in mileage_impact:
        notes.append("里程偏高，报价要更保守")
    else:
        notes.append("当前里程已参与定价，但结构化结果没有给出独立加减价")
    for field, label in (("city_log_adjustment", "城市"), ("color_log_adjustment", "颜色")):
        value = element_trace.get(field)
        try:
            percent = float(value) * 100
        except (TypeError, ValueError):
            continue
        if abs(percent) >= 0.05:
            notes.append(f"{label}修正{'上调' if percent > 0 else '下调'}{abs(percent):.1f}%")
    if six.get("color") and not any(note.startswith("颜色修正") for note in notes):
        notes.append("颜色已作为输入，但本次没有独立颜色调价证据")
    if six.get("transfer_count") not in (None, ""):
        notes.append("过户次数已作为输入，但本次没有独立过户调价证据")
    inspection_verified = bool(
        six.get("inspection_verified")
        or six.get("has_real_inspection")
        or str(six.get("inspection_status") or "").lower() in {"verified", "completed", "已检测", "已验车"}
    )
    if inspection_verified:
        notes.append("车况已有实车检测记录")
    else:
        notes.append("当前按常规可交易车况估算，尚未实车检测")
    return "；".join(notes[:4])


def _apply_reflections_to_customer_copy(
    *,
    customer_script_pack: Dict[str, Any],
    customer_questions: list[Dict[str, Any]],
    reflection_bundle: Dict[str, Any],
    report_stub: Dict[str, Any],
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    applied = [
        item for item in (reflection_bundle.get("applied_reflections") or [])
        if isinstance(item, dict)
    ]
    if not applied:
        return customer_script_pack, customer_questions
    targets = {
        target
        for item in applied
        for target in (item.get("apply_to") or [])
    }
    instructions = "；".join(str(item.get("next_time_instruction") or "") for item in applied)
    if not targets.intersection({"customer_script", "customer_faq", "final_report"}):
        return customer_script_pack, customer_questions
    pack = dict(customer_script_pack)
    scenarios = []
    for scenario in pack.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        text = str(scenario.get("text") or "")
        # Feedback memory may change emphasis, but it must not replace a
        # vehicle-grounded script with a fixed salutation/template or add an
        # unsupported explanation of another buyer's behaviour.
        scenarios.append({**scenario, "text": filter_customer_text(text, report_stub)})
    if scenarios:
        pack["scenarios"] = scenarios
        pack["reflection_applied"] = True
        pack["reflection_note"] = "已参考历史反馈优化对客话术，不影响价格。"
    faq = []
    for item in customer_questions:
        if not isinstance(item, dict):
            continue
        answer = str(item.get("recommended_answer") or item.get("answer") or "")
        if "挂牌价" in instructions or "成交价" in instructions:
            if "网上" in str(item.get("customer_question") or item.get("question") or ""):
                answer = "网上很多是挂牌价，不一定是成交价。我们收回来还要检测、整备和再卖，所以不能直接按零售价收。"
        faq.append({**item, "recommended_answer": filter_customer_text(answer, report_stub), "reflection_applied": True})
    return pack, faq or customer_questions


def _technical_audit_items(response: Dict[str, Any]) -> list[str]:
    pricing = response.get("pricing") if isinstance(response.get("pricing"), dict) else {}
    price_result = pricing.get("price_result") if isinstance(pricing.get("price_result"), dict) else {}
    items = []
    version = price_result.get("pricing_engine_version") or price_result.get("model_version")
    if version:
        items.append(f"engine_version：{version}")
    quote_id = price_result.get("quote_id") or price_result.get("trace_id")
    if quote_id:
        items.append(f"quote_id：{quote_id}")
    items.append("route：pricing_agent_v23 → task_plan → task_events → final_report")
    items.append("默认视图隐藏 workflow、tool name、model name、RAG 和 LLM 字段。")
    reflection_bundle = response.get("reflection_context") if isinstance(response.get("reflection_context"), dict) else {}
    applied = reflection_bundle.get("applied_reflections") or []
    ignored = reflection_bundle.get("ignored_reflections") or []
    items.append(f"feedback_memory：命中 {len(applied)} 条，忽略 {len(ignored)} 条。")
    if applied:
        ids = "、".join(str(item.get("reflection_id") or "") for item in applied[:3] if isinstance(item, dict))
        items.append(f"applied_reflection_ids：{ids}")
    items.append("feedback_memory_policy：只影响解释、话术、证据优先级和风险提示；不影响模型价格。")
    return items


def _internal_basis_items(
    *,
    candidate_count: int,
    low: float,
    high: float,
    baseline: float,
    point: float,
    upper: float,
    confidence: str,
    dispersion: str,
    daily_note: str,
    task_result_tables: list[Dict[str, Any]],
) -> list[str]:
    if candidate_count <= 1 or _same_display_price(low, high):
        evidence_line = (
            f"可比证据：当前仅有 {candidate_count} 个可展示参考点 {_wan_text(low)}，"
            "不足以形成价格区间，也不能解读成上下界。"
        )
    else:
        evidence_line = f"可比证据：命中 {candidate_count} 条，相近车价格分布 {_range_text(low, high)}，中位价 {_wan_text(baseline)}。"
    items = [
        evidence_line,
        f"谈判锚点：建议价 {_wan_text(point)}，追价上限 {_wan_text(upper)}，置信度 {_confidence_label(confidence)}。",
    ]
    if dispersion in {"中等分散", "分散"}:
        items.append(
            f"价格跨度说明：{_range_text(low, high)} 不是给客户看的报价区间，而是内部判断市场分布用的；"
            "跨度大说明市场价格不稳定，高价样本不能直接照用，因此报价要更保守。"
        )
        items.append("价格跨度较大，本次更适合用建议价作为谈判锚点，而不是按最高样本追价。")
    elif dispersion == "集中":
        items.append("价格分布说明：相近车价格比较集中，当前建议价参考性更强，但仍需结合实车检测。")
    else:
        items.append("证据边界：当前样本不足，单个参考点只用于核对方向，不单独决定报价或置信度。")
    risk_summary = _stage_summary(task_result_tables, "risk_boundary_task")
    items.append("七要素校验：具体款型、上牌、里程、城市、过户、颜色和车况均已进入本次定价。")
    return items[:5]


def _main_risk_text(response: Dict[str, Any], lower: float, upper: float, confidence: str, daily_note: str) -> str:
    report_context = response.get("pricing_report_context") or {}
    market_state = report_context.get("market_state") if isinstance(report_context.get("market_state"), dict) else {}
    risks = [str(item) for item in (market_state.get("risks") or []) if item]
    prefix = "；".join(risks[:2]) or "车况和整备成本仍需现场核验"
    boundary = f"。若存在事故、泡水、火烧、调表或高整备成本，应按区间下沿 {_wan_text(lower)} 执行；超过 {_wan_text(upper)} 不追。"
    confidence_note = "本次置信度不是高，请按保守价格边界使用。" if confidence != "HIGH" else ""
    return prefix + boundary + confidence_note + daily_note


def _main_risk_items(
    response: Dict[str, Any],
    lower: float,
    upper: float,
    confidence: str,
    dispersion: str,
    daily_note: str,
) -> list[str]:
    price_risk = (
        "可比车价格分散，高价样本不能直接照用。"
        if dispersion != "集中"
        else "可比车价格方向接近，但样本一致不等于实车条件一致。"
    )
    if confidence != "HIGH":
        price_risk += " 当前模型置信度为中或低，建议按保守边界执行。"
    return [
        "当前按无重大事故、泡水、火烧、调表等常规可交易车况估算，最终价格需结合实车检测确认。",
        price_risk,
        f"超过最高收车价 {_wan_text(upper)} 后，价格风险明显增大，不建议继续追价。",
    ]


def _stage_summary(task_result_tables: list[Dict[str, Any]], task_id: str) -> str:
    for table in task_result_tables:
        if table.get("task_id") == task_id:
            return str(table.get("stage_conclusion") or table.get("summary") or "")
    return ""


def _sync_report_blocks(report: Dict[str, Any]) -> None:
    report["blocks"] = compose_final_report_blocks(report)


def _llm_copy_is_safe(candidate: str, allowed_text: str) -> bool:
    if not candidate:
        return False
    if re.search(r"算法|模型|RAG|workflow|特征|tool[_\s-]?name|intent[_\s-]?code", candidate, re.I):
        return False
    allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?", allowed_text))
    candidate_numbers = set(re.findall(r"\d+(?:\.\d+)?", candidate))
    return candidate_numbers.issubset(allowed_numbers)


def _plan_title(price_role: str) -> str:
    return {
        "listing_price": "挂牌价合理性分析",
        "customer_offer": "客户报价可接受性分析",
        "purchase_price": "收车估价可行性分析",
    }.get(price_role, "收车估价可行性分析")


def _complete_understanding(slots: Dict[str, Any], response: Dict[str, Any], price_role: str, quote_amount: float) -> str:
    six = _six_elements(response)
    vehicle = _vehicle_title(six, response)
    attrs = [
        _six_value("first_license_date", six),
        _six_value("mileage_wan_km", six),
        _six_value("city", six),
        _six_value("transfer_count", six),
        _six_value("color", six),
        _six_value("condition_group", six),
    ]
    role_text = {
        "listing_price": "挂牌价是否合理",
        "customer_offer": "客户报价是否可接受",
        "purchase_price": "建议收车价和最高收车价",
    }.get(price_role, "建议收车价和最高收车价")
    quote = f"；用户报价 {_wan_text(quote_amount)}" if quote_amount else ""
    return f"判断{vehicle}（{'、'.join(str(item) for item in attrs if item)}）的{role_text}{quote}。"


def _missing_understanding(slots: Dict[str, Any], missing_fields: list[str]) -> str:
    vehicle = slots.get("standard_vehicle") or slots.get("series") or slots.get("brand") or "当前车辆"
    missing = "、".join(_slot_label(field) for field in missing_fields)
    return f"用户希望评估{vehicle}价格，但估价七要素还缺：{missing}。补齐前不进入估价。"


def _prioritize_tasks(tasks: list[Dict[str, Any]], *, has_quote: bool) -> list[Dict[str, Any]]:
    priority = {
        "pricing_evidence_task": 1,
        "vehicle_difference_task": 2,
        "quote_acceptance_task": 3 if has_quote else 5,
        "risk_boundary_task": 4,
        "low_confidence_task": 3 if not has_quote else 4,
    }
    ordered = sorted(tasks, key=lambda item: priority.get(str(item.get("task_id")), 99))
    if len(ordered) <= 3:
        return ordered
    keep_ids = {"pricing_evidence_task", "vehicle_difference_task"}
    if has_quote:
        keep_ids.add("quote_acceptance_task")
    if any(item.get("task_id") == "low_confidence_task" for item in ordered):
        keep_ids.add("low_confidence_task")
    result = [item for item in ordered if item.get("task_id") in keep_ids]
    for item in ordered:
        if len(result) >= 3:
            break
        if item not in result:
            result.append(item)
    return result[:3]


def _task_running_message(task_id: str, task: Dict[str, Any]) -> str:
    messages = {
        "field_confirmation_task": "正在核对估价七要素，缺字段时停止报价。",
        "pricing_evidence_task": "正在分析定价模型和可比车证据，优先使用内部成交与在售证据。",
        "vehicle_difference_task": "正在比较当前车与可比车的里程、过户、颜色和配置差异。",
        "risk_boundary_task": "正在校验挂牌、售卖、收车与最高收车价的大小关系。",
        "quote_acceptance_task": "正在把用户报价放进建议价和业务边界里判断。",
        "low_confidence_task": "正在检查证据数量和价格分布，确认本次置信度等级。",
    }
    return messages.get(task_id, str(task.get("task_goal") or "正在执行任务。"))


def _task_source_message(task_id: str) -> str:
    messages = {
        "pricing_evidence_task": "读取内部可比车、价格区间和后端基线价。",
        "vehicle_difference_task": "读取车辆七要素、可比车字段和估价结果。",
        "risk_boundary_task": "读取结构化行情数据和已上传日报背景。",
        "quote_acceptance_task": "读取建议价、价格区间和用户报价。",
        "low_confidence_task": "读取可比证据数量、置信度和系统能力边界。",
    }
    return messages.get(task_id, "读取本任务所需的后端结果。")


def _tool_done_message(table: Dict[str, Any]) -> str:
    title = str(table.get("title") or "")
    chips = [str(item) for item in (table.get("metric_chips") or []) if item]
    if "可比车" in title and chips:
        return f"已找到{chips[0].replace('可比车 ', '')}，正在判断这些价格能不能直接用于收车。"
    if "差异" in title:
        return "已完成车辆七要素差异检查，正在判断哪些因素支撑价格、哪些因素压低价格。"
    if "行情" in title:
        return "已读取城市行情和日报背景，正在判断是否需要保守报价。"
    if "字段" in title:
        return "已完成车辆字段核对，正在确认是否可以进入估价。"
    return "工具结果已返回，正在转换成业务判断。"


def _detect_price_role(message: str, response: Dict[str, Any]) -> str:
    intent_v2 = response.get("intent_v2") or {}
    slots = response.get("slots") or {}
    raw = str(intent_v2.get("price_role") or slots.get("price_role") or "").strip()
    text = message or ""
    task_intent = str(intent_v2.get("task_intent") or intent_v2.get("internal_intent") or "")
    if raw in {"purchase_price", "listing_price", "customer_offer"}:
        return raw
    if "customer_offer" in task_intent or re.search(r"客户(给|出).{0,6}(能不能|可以|卖)", text):
        return "customer_offer"
    if "listing" in task_intent or re.search(r"(挂|挂牌|售车价|卖价).{0,10}\d", text):
        return "listing_price"
    return "purchase_price"


def _needs_quote_judgement(message: str, price_role: str, quote_amount: float) -> bool:
    if quote_amount:
        return True
    return bool(re.search(r"(能不能收|能不能卖|可不可以收|可不可以卖|挂.*高不高|报价.*行不行)", message or "")) or price_role in {"listing_price", "customer_offer"}


def _quote_task_name(price_role: str) -> str:
    return {
        "listing_price": "挂牌价合理性判断",
        "customer_offer": "客户报价可接受性判断",
        "purchase_price": "报价可接受性判断",
    }.get(price_role, "报价可接受性判断")


def _quote_task_goal(price_role: str) -> str:
    return {
        "listing_price": "判断当前挂牌价相对建议挂牌区间是偏高、合理还是偏低。",
        "customer_offer": "判断客户报价相对市场参考是否可接受，并说明缺成本时不能判断毛利。",
        "purchase_price": "判断当前收车报价是否超过建议价和最高收车价。",
    }.get(price_role, "判断当前报价是否可接受。")


def _extract_user_quote_yuan(message: str, response: Dict[str, Any]) -> float:
    intent_slots = (response.get("intent_v2") or {}).get("slots") or {}
    slots = response.get("slots") or {}
    for value in (intent_slots.get("user_given_price_yuan"), slots.get("user_given_price_yuan")):
        number = _money(value)
        if number:
            return number
    text = message or ""
    price_context_patterns = [
        r"(?:客户(?:给|出|报价)|报价|出价|给价|给到|收车价|售车价|挂牌价|卖价|最高(?:出|收)|最多(?:出|收)|能不能(?:收|卖)|可不可以(?:收|卖)|挂(?:牌)?)(?:[^\d万]{0,12})(\d+(?:\.\d+)?)\s*万(?!\s*(?:公里|km|KM))",
        r"(\d+(?:\.\d+)?)\s*万(?!\s*(?:公里|km|KM))(?:[^\d万]{0,12})(?:能不能(?:收|卖)|可不可以(?:收|卖)|收不收|卖不卖|挂高不高|报价(?:行不行|合不合理))",
    ]
    for pattern in price_context_patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1)) * 10000
    return 0.0


def _normalize_missing_fields(fields: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    for field in fields:
        text = str(field or "").strip()
        if not text:
            continue
        if text in {"model_year", "year_disambiguation", "trim", "model", "vehicle_confirm"}:
            text = "standard_vehicle"
        if text in {"first_license_year", "first_license_month"}:
            text = "first_license_date"
        if text == "mileage_km":
            text = "mileage_wan_km"
        if text not in normalized:
            normalized.append(text)
    return normalized


def _field_status(field: str, value: str, missing: set[str]) -> str:
    if field in missing or not value:
        return "缺失"
    if field == "standard_vehicle" and value and ("标准车型" in value or len(value) < 5):
        return "待确认"
    return "已确认"


def _field_next_step(field: str, status: str) -> str:
    if status == "已确认":
        return "可用于估价"
    if field == "standard_vehicle":
        return "补充具体款型/配置"
    if field == "first_license_date":
        return "选择上牌年月"
    if field == "mileage_wan_km":
        return "补充表显里程"
    if field == "transfer_count":
        return "补充过户次数"
    return f"补充{SLOT_LABELS.get(field, field)}"


def _six_elements(response: Dict[str, Any]) -> Dict[str, Any]:
    report_context = response.get("pricing_report_context") or {}
    raw = report_context.get("vehicle_six_elements") if isinstance(report_context.get("vehicle_six_elements"), dict) else {}
    slots = response.get("slots") or {}
    vehicle_match = response.get("vehicle_match") or {}
    standard_vehicle = (
        raw.get("standard_vehicle")
        or slots.get("standard_vehicle")
        or slots.get("vehicle_title")
        or vehicle_match.get("display_name")
        or vehicle_match.get("model_name")
        or " ".join(str(v) for v in (slots.get("brand"), slots.get("series"), slots.get("trim") or slots.get("model")) if v)
    )
    standard_vehicle = _clean_standard_vehicle_label(standard_vehicle, slots, vehicle_match)
    return {
        "standard_vehicle": standard_vehicle,
        "first_license_date": raw.get("first_license_date") or _first_license_value(slots),
        "mileage_wan_km": raw.get("mileage_wan_km") if raw.get("mileage_wan_km") not in (None, "") else slots.get("mileage_wan_km"),
        "city": raw.get("city") or slots.get("city"),
        "transfer_count": raw.get("transfer_count") if raw.get("transfer_count") not in (None, "") else slots.get("transfer_count"),
        "color": raw.get("color") or slots.get("color"),
        "condition_group": raw.get("condition_group") or slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"),
    }


def _clean_standard_vehicle_label(label: Any, slots: Dict[str, Any], vehicle_match: Dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", str(label or "")).strip()
    candidates = vehicle_match.get("candidates") if isinstance(vehicle_match.get("candidates"), list) else []
    candidate_label = ""
    if candidates and isinstance(candidates[0], dict):
        candidate_label = str(candidates[0].get("label") or "").strip()
    noisy = bool(
        "上牌" in text
        or re.search(r"\s-\d{1,2}(?:月)?", text)
        or re.search(r"ModelY\s+Model\s*Y", text, re.I)
    )
    if noisy and candidate_label:
        return candidate_label
    text = re.sub(r"\s*(?:\d{4})?-\d{1,2}(?:月)?上牌", "", text)
    text = re.sub(r"\s*(?:19|20)\d{2}-\d{1,2}上牌", "", text)
    text = re.sub(r"ModelY\s+Model\s*Y", "Model Y", text, flags=re.I)
    brand = str(slots.get("brand") or "").strip()
    series = str(slots.get("series") or "").strip()
    if brand and series and text == f"{brand} {series}":
        trim = str(slots.get("trim") or "").strip()
        if trim:
            text = f"{brand} {series} {trim}"
    return re.sub(r"\s+", " ", text).strip() or candidate_label or "当前车辆"


def _six_value(field: str, six: Dict[str, Any]) -> str:
    value = six.get(field)
    if value in (None, ""):
        return ""
    if field == "mileage_wan_km":
        return f"{_trim_number(value)}万公里"
    if field == "transfer_count":
        return f"{_trim_number(value)}次"
    if field == "condition_group":
        text = str(value).strip()
        if text.upper() in {"A", "B", "C", "D"}:
            return f"{text.upper()}级车况"
        return {"excellent": "A级车况", "good": "B级车况", "fair": "C级车况", "poor": "D级车况"}.get(text.lower(), text)
    return str(value)


def _vehicle_title(six: Dict[str, Any], response: Dict[str, Any]) -> str:
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    title = (
        six.get("standard_vehicle")
        or price_result.get("vehicle_title")
        or price_result.get("standard_vehicle")
        or "当前车辆"
    )
    return str(title).strip() or "当前车辆"


def _first_license_value(slots: Dict[str, Any]) -> str:
    raw = str(slots.get("first_license_date") or slots.get("reg_date") or "").strip().replace("/", "-")
    match = re.match(r"^((?:19|20)\d{2})(?:-(\d{1,2}))?", raw)
    if match:
        month = match.group(2) or slots.get("first_license_month")
        if month not in (None, ""):
            return f"{match.group(1)}-{int(month):02d}"
        return match.group(1)
    year = slots.get("first_license_year")
    month = slots.get("first_license_month")
    if year not in (None, ""):
        if month not in (None, ""):
            return f"{int(year)}-{int(month):02d}"
        return str(year)
    return ""


def _selected_comparables(price_result: Dict[str, Any]) -> list[Dict[str, Any]]:
    evidence_card = price_result.get("evidence_card") if isinstance(price_result.get("evidence_card"), dict) else {}
    groups = (
        price_result.get("selected_comparables"),
        price_result.get("ref_cars"),
        price_result.get("comparables"),
        price_result.get("top_candidates"),
        evidence_card.get("selected_comparables"),
        evidence_card.get("top_comparables"),
        evidence_card.get("candidates"),
    )
    for group in groups:
        if isinstance(group, list) and group:
            return _dedupe_comparables([item for item in group if isinstance(item, dict)])
    return []


def _dedupe_comparables(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Remove repeated evidence records without collapsing genuinely different cars."""
    result: list[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        title = str(
            row.get("title")
            or row.get("vehicle")
            or row.get("standard_vehicle")
            or row.get("model")
            or row.get("trim")
            or ""
        ).strip().lower()
        has_vehicle_detail = bool(
            title
            or row.get("vehicle_id")
            or row.get("listing_id")
            or row.get("model_year") not in (None, "")
            or row.get("mileage_wan_km") not in (None, "")
            or row.get("mileage") not in (None, "")
            or row.get("city")
            or row.get("transfer_count") not in (None, "")
            or row.get("event_time")
            or row.get("data_date")
            or row.get("event_date")
        )
        # Detail-free provider anchors are not individual cars. Collapse
        # values that render identically at 0.01万; real vehicle rows retain
        # their full identity/date key even when their prices happen to match.
        display_price_key = (
            round(_candidate_price(row) / 100.0) * 100.0
            if not has_vehicle_detail
            else round(_candidate_price(row), 0)
        )
        key = (
            str(row.get("vehicle_id") or row.get("listing_id") or row.get("clue_id") or "").strip(),
            title,
            str(row.get("model_year") or "").strip(),
            round(_money(row.get("mileage_wan_km") or row.get("mileage")), 2),
            str(row.get("city") or "").strip(),
            str(row.get("transfer_count") or "").strip(),
            display_price_key,
            str(row.get("event_time") or row.get("data_date") or row.get("event_date") or "")[:10],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _candidate_price(row: Dict[str, Any]) -> float:
    for key in ("price_yuan", "converted_c2b_price", "c2b_price", "price", "b2c_price"):
        value = _money(row.get(key))
        if value:
            return value
    return 0.0


def _price_point(price_result: Dict[str, Any]) -> float:
    price = price_result.get("price") if isinstance(price_result.get("price"), dict) else {}
    for value in (
        price_result.get("final_price"),
        price.get("point"),
        price_result.get("c2bPrice"),
        price_result.get("c2b_point"),
        price_result.get("point_price"),
    ):
        number = _price_yuan(value)
        if number:
            return number
    return 0.0


def _price_range(price_result: Dict[str, Any], point: float) -> tuple[float, float]:
    price = price_result.get("price") if isinstance(price_result.get("price"), dict) else {}
    interval = price_result.get("price_interval") or price_result.get("interval") or price_result.get("range") or {}
    tuple_range = price_result.get("c2bRange") if isinstance(price_result.get("c2bRange"), list) else []
    lower = (
        _price_yuan(price.get("lower"))
        or _price_yuan(tuple_range[0] if len(tuple_range) > 0 else None)
        or _price_yuan(interval.get("lower") if isinstance(interval, dict) else None)
        or _price_yuan(interval.get("low") if isinstance(interval, dict) else None)
        or _price_yuan(price_result.get("price_low"))
        or _price_yuan(price_result.get("lower"))
        or _price_yuan(price_result.get("c2b_lower"))
    )
    upper = (
        _price_yuan(price.get("upper"))
        or _price_yuan(tuple_range[1] if len(tuple_range) > 1 else None)
        or _price_yuan(interval.get("upper") if isinstance(interval, dict) else None)
        or _price_yuan(interval.get("high") if isinstance(interval, dict) else None)
        or _price_yuan(price_result.get("price_high"))
        or _price_yuan(price_result.get("upper"))
        or _price_yuan(price_result.get("c2b_upper"))
    )
    if point and not lower:
        lower = point * 0.95
    if point and not upper:
        upper = point * 1.05
    return lower, upper


def _b2c_range(price_result: Dict[str, Any]) -> tuple[float, float, float]:
    tasks = price_result.get("tasks") if isinstance(price_result.get("tasks"), dict) else {}
    b2c_task = tasks.get("b2c") if isinstance(tasks.get("b2c"), dict) else {}
    b2c_nested = price_result.get("b2c") if isinstance(price_result.get("b2c"), dict) else {}
    b2c_price = b2c_task.get("price") if isinstance(b2c_task.get("price"), dict) else {}
    point = (
        _price_yuan(price_result.get("b2cPrice"))
        or _price_yuan(price_result.get("b2c_price"))
        or _price_yuan(price_result.get("b2c_point"))
        or _price_yuan(price_result.get("targetB2C"))
        or _price_yuan(b2c_task.get("point"))
        or _price_yuan(b2c_task.get("final_price"))
        or _price_yuan(b2c_price.get("point"))
        or _price_yuan(b2c_nested.get("point"))
        or _price_yuan(b2c_nested.get("final_price"))
    )
    tuple_range = price_result.get("b2cRange") if isinstance(price_result.get("b2cRange"), list) else []
    lower = (
        _price_yuan(tuple_range[0] if len(tuple_range) > 0 else None)
        or _price_yuan(price_result.get("b2c_low"))
        or _price_yuan(price_result.get("b2c_lower"))
        or _price_yuan(b2c_task.get("lower"))
        or _price_yuan(b2c_price.get("lower"))
        or _price_yuan(b2c_nested.get("lower"))
    )
    upper = (
        _price_yuan(tuple_range[1] if len(tuple_range) > 1 else None)
        or _price_yuan(price_result.get("b2c_high"))
        or _price_yuan(price_result.get("b2c_upper"))
        or _price_yuan(b2c_task.get("upper"))
        or _price_yuan(b2c_price.get("upper"))
        or _price_yuan(b2c_nested.get("upper"))
    )
    return point, lower, upper


def _sale_profit_context(price_result: Dict[str, Any], point: float, lower: float, upper: float) -> Dict[str, Any]:
    ladder = price_result.get("price_ladder") if isinstance(price_result.get("price_ladder"), dict) else {}
    listing_point = (
        _price_yuan(price_result.get("recommended_listing_price_yuan"))
        or _price_yuan(ladder.get("recommended_listing_yuan"))
    )
    listing_range = (
        price_result.get("recommended_listing_range_yuan")
        if isinstance(price_result.get("recommended_listing_range_yuan"), list)
        else ladder.get("recommended_listing_range_yuan")
        if isinstance(ladder.get("recommended_listing_range_yuan"), list)
        else []
    )
    listing_lower = _price_yuan(listing_range[0] if len(listing_range) > 0 else None)
    listing_upper = _price_yuan(listing_range[1] if len(listing_range) > 1 else None)
    max_c2b = (
        _price_yuan(price_result.get("max_c2b_price_yuan"))
        or _price_yuan(ladder.get("max_c2b_yuan"))
        or upper
    )
    sale_point, sale_lower, sale_upper = _b2c_range(price_result)
    source = "model" if sale_point or sale_lower or sale_upper else "unavailable"
    if not sale_point and (sale_lower or sale_upper):
        sale_point = (sale_lower or sale_upper) if not (sale_lower and sale_upper) else (sale_lower + sale_upper) / 2
    # Different stores and users have different operating-cost structures.
    # The default report uses the transparent frontline convention: price
    # spread = expected sale price - trial purchase price.
    estimated_recon_cost = 0.0
    platform_service_cost = 0.0
    risk_buffer = 0.0
    target_profit = _default_target_profit(point)
    sale_floor = point + estimated_recon_cost + platform_service_cost + risk_buffer + target_profit if point else 0.0
    if not sale_point and point:
        sale_point = sale_floor
        sale_lower = sale_point * 0.975
        sale_upper = sale_point * 1.035
        source = "fallback_rule"
    elif sale_point:
        # The B2C model estimates the market transaction price.  A target-profit
        # floor must not rewrite a valid low-margin quote; only repair the
        # impossible malformed case where B2C is below C2B.
        if point and sale_point < point:
            # This is a malformed upstream ladder rather than a normal
            # low-margin quote. Reconstruct only this impossible B2C<C2B case
            # so the published hierarchy remains usable.
            sale_point = max(point, sale_floor)
            source = "model_hierarchy_guard"
        elif sale_floor and sale_point < sale_floor:
            source = "model_below_target_margin"
        if not sale_lower:
            sale_lower = sale_point * 0.975
        if not sale_upper:
            sale_upper = sale_point * 1.035
        sale_lower = max(sale_lower, point) if point else sale_lower
        sale_upper = max(sale_upper, sale_point) if sale_point else sale_upper
    # The pricing module reports the market-consistent acquisition estimate.
    # Profitability belongs in the calculator/selection decision and must not
    # silently rewrite the model quote: doing so makes the initial answer,
    # report, follow-up and PDF disagree and can create an uncollectable price.
    purchase_guard_note = ""
    gross_profit = sale_point - point if sale_point and point else 0.0
    gross_profit_rate = gross_profit / sale_point if sale_point else 0.0
    # A listing price is the external asking price and must leave room above the
    # expected negotiated transaction price.  Guard malformed upstream payloads
    # here without changing the market transaction estimate.
    if sale_point:
        listing_point = max(listing_point or 0.0, sale_point * 1.02)
    if listing_point:
        listing_lower = max(listing_lower or 0.0, sale_point, listing_point * 0.97)
        listing_upper = max(listing_upper or 0.0, listing_point, listing_point * 1.03)
    if sale_point:
        max_c2b = min(max(max_c2b or 0.0, point or 0.0), sale_point)
    return {
        "listing_price": _wan_number(listing_point),
        "listing_price_low": _wan_number(listing_lower),
        "listing_price_high": _wan_number(listing_upper),
        "listing_price_yuan": listing_point,
        "listing_price_low_yuan": listing_lower,
        "listing_price_high_yuan": listing_upper,
        "purchase_price": _wan_number(point),
        "purchase_price_low": _wan_number(lower),
        "purchase_price_high": _wan_number(upper),
        "purchase_price_yuan": point,
        "purchase_price_low_yuan": lower,
        "purchase_price_high_yuan": upper,
        "max_c2b_price": _wan_number(max_c2b),
        "max_c2b_price_yuan": max_c2b,
        "sale_price": _wan_number(sale_point),
        "sale_price_low": _wan_number(sale_lower),
        "sale_price_high": _wan_number(sale_upper),
        "sale_price_yuan": sale_point,
        "sale_price_low_yuan": sale_lower,
        "sale_price_high_yuan": sale_upper,
        "sale_price_source": source,
        "gross_profit": _wan_number(gross_profit),
        "gross_profit_yuan": gross_profit,
        "gross_profit_rate": round(gross_profit_rate, 4),
        "purchase_profit_guard_applied": bool(purchase_guard_note),
        "purchase_profit_guard_note": purchase_guard_note,
        "estimated_recon_cost": _wan_number(estimated_recon_cost),
        "estimated_recon_cost_yuan": estimated_recon_cost,
        "platform_service_cost": _wan_number(platform_service_cost),
        "platform_service_cost_yuan": platform_service_cost,
        "risk_buffer": _wan_number(risk_buffer),
        "risk_buffer_yuan": risk_buffer,
        "target_profit": _wan_number(target_profit),
        "target_profit_yuan": target_profit,
    }


def _wan_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number == 0:
        return 0.0
    return round(number / 10000 if abs(number) > 1000 else number, 2)


def _price_yuan(value: Any) -> float:
    number = _money(value)
    if not number:
        return 0.0
    return number * 10000 if number < 1000 else number


def _default_recon_cost(point: float) -> float:
    if point >= 300000:
        return 12000.0
    if point >= 180000:
        return 8000.0
    if point >= 100000:
        return 6000.0
    return 4000.0


def _default_platform_cost(point: float) -> float:
    if point >= 300000:
        return 5000.0
    if point >= 100000:
        return 3000.0
    return 2000.0


def _default_risk_buffer(point: float) -> float:
    if point >= 300000:
        return 7000.0
    if point >= 180000:
        return 5000.0
    if point >= 100000:
        return 4000.0
    return 2500.0


def _default_target_profit(point: float) -> float:
    if point >= 300000:
        return 25000.0
    if point >= 200000:
        return 18000.0
    if point >= 100000:
        return 12000.0
    if point >= 50000:
        return 8000.0
    return 5000.0


def _sale_price_source_note(source: str) -> str:
    if source == "model":
        return "售车价来自售车价模型。"
    if source == "model_below_target_margin":
        return "售车价来自售车价模型；当前利润空间偏低，本次置信度相应下调，建议收车价靠近区间下沿。"
    if source == "model_hierarchy_guard":
        return "售车价模型已触发价格层级保护，本次按低置信度和保守收车边界输出。"
    if source == "fallback_rule":
        return "售车价由定价模型的收售价梯度生成，本次置信度已同步体现数据充分度。"
    return "售车价已按定价模型与收售价梯度生成。"


def _baseline_price(response: Dict[str, Any]) -> float:
    report_context = response.get("pricing_report_context") or {}
    price_bridge = report_context.get("price_bridge") if isinstance(report_context.get("price_bridge"), dict) else {}
    price_result = ((response.get("pricing") or {}).get("price_result") or {})
    candidates = _selected_comparables(price_result)
    candidate_prices = [_candidate_price(row) for row in candidates if _candidate_price(row)]
    return (
        _money(price_bridge.get("baseline_price_yuan"))
        or _money((price_result.get("price_trace") or {}).get("baseline_p40") if isinstance(price_result.get("price_trace"), dict) else None)
        or (median(candidate_prices) if candidate_prices else 0.0)
        or _price_point(price_result)
    )


def _money(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number <= 0:
        return 0.0
    return number


def _wan_text(value: Any) -> str:
    number = _money(value)
    if not number:
        return "暂无"
    wan = number / 10000 if number > 1000 else number
    return f"{wan:.2f}万".replace(".00万", "万")


def _signed_wan_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "暂无"
    if not math.isfinite(number):
        return "暂无"
    wan = number / 10000 if abs(number) > 1000 else number
    return f"{wan:.2f}万".replace(".00万", "万")


def _range_text(low: Any, high: Any) -> str:
    low_num = _money(low)
    high_num = _money(high)
    if low_num and high_num:
        if _same_display_price(low_num, high_num):
            return _wan_text(low_num)
        return f"{_wan_text(low_num)} - {_wan_text(high_num)}"
    if low_num:
        return f"不低于 {_wan_text(low_num)}"
    if high_num:
        return f"不高于 {_wan_text(high_num)}"
    return "暂无足够证据"


def _same_display_price(low: Any, high: Any) -> bool:
    low_num = _money(low)
    high_num = _money(high)
    return bool(low_num and high_num and _wan_text(low_num) == _wan_text(high_num))


def _trim_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "-"
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _slot_label(field: str) -> str:
    return SLOT_LABELS.get(field, field)


def _evidence_count_impact(count: int) -> str:
    if count >= 10:
        return "证据数量较充足，可支撑参考价"
    if count >= 5:
        return "证据可用，但追价仍需看车况"
    if count > 0:
        return "证据偏少，建议保守使用价格"
    return "内部证据不足，不能形成高置信基线"


def _evidence_strength_chip(count: int) -> str:
    if count >= 10:
        return "证据较充足"
    if count >= 5:
        return "证据可用"
    if count > 0:
        return "证据偏少"
    return "暂无有效证据"


def _dispersion_label(prices: list[float]) -> str:
    if len(prices) < 2:
        return "样本不足，无法判断"
    mid = median(prices)
    if not mid:
        return "样本不足，无法判断"
    ratio = (max(prices) - min(prices)) / mid
    if ratio <= 0.12:
        return "集中"
    if ratio <= 0.28:
        return "中等分散"
    return "分散"


def _dispersion_impact(label: str) -> str:
    if label == "集中":
        return "价格边界相对稳定，可按建议价谈"
    if label == "中等分散":
        return "需结合车况和配置决定是否靠近上沿"
    if label == "分散":
        return "价格分布较散，本次置信度较低，建议按区间下沿推进"
    return "置信度不足，不能单独作为报价依据"


def _mileage_difference(six: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    current = _money(six.get("mileage_wan_km"))
    values = [_money(row.get("mileage_wan_km") or row.get("mileage")) for row in candidates]
    values = [value for value in values if value]
    if current and values:
        return f"当前 {current:g}万公里，可比车均值约 {sum(values) / len(values):.1f}万公里"
    if current:
        return f"当前 {current:g}万公里，可比车里程均值暂缺"
    return "里程缺失"


def _mileage_impact(six: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    current = _money(six.get("mileage_wan_km"))
    values = [_money(row.get("mileage_wan_km") or row.get("mileage")) for row in candidates]
    values = [value for value in values if value]
    if not current or not values:
        return "里程已进入估价，但没有可比均值时不写高低判断"
    avg = sum(values) / len(values)
    if current < avg * 0.85:
        return "当前里程偏低，对价格有支撑"
    if current > avg * 1.15:
        return "当前里程偏高，应保守报价"
    return "里程处在可比车常见范围，影响较小"


def _transfer_color_difference(six: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    transfer = six.get("transfer_count")
    color = six.get("color")
    values = [_money(row.get("transfer_count")) for row in candidates if row.get("transfer_count") not in (None, "")]
    avg_text = f"；可比车过户均值约 {sum(values) / len(values):.1f}次" if values else ""
    return f"过户 {transfer if transfer not in (None, '') else '缺失'}次，颜色 {color or '缺失'}{avg_text}"


def _transfer_color_impact(six: Dict[str, Any]) -> str:
    color = str(six.get("color") or "")
    transfer = _money(six.get("transfer_count"))
    impacts = []
    if transfer > 2:
        impacts.append("过户偏多，谈判时需留折让")
    elif transfer:
        impacts.append("过户次数在常见范围")
    if color and color not in {"白色", "黑色", "灰色", "银色"}:
        impacts.append(f"{color}更依赖买家偏好，谨慎追高")
    elif color:
        impacts.append("主流颜色影响较小")
    return "；".join(impacts) or "影响方向不明确，不编造修正金额"


def _overall_change_text(baseline: float, point: float) -> str:
    if not baseline or not point:
        return "暂无"
    diff = point - baseline
    if abs(diff) < 100:
        return "基本不变"
    direction = "上修" if diff > 0 else "下修"
    return f"{direction} {_wan_text(abs(diff))}"


def _market_metric_summary(metrics: Dict[str, Any]) -> str:
    parts = []
    if metrics.get("deal_sample_90d") not in (None, ""):
        parts.append(f"90天成交 {metrics.get('deal_sample_90d')} 辆")
    if metrics.get("listing_count") not in (None, ""):
        parts.append(f"在售 {metrics.get('listing_count')} 辆")
    if metrics.get("avg_deal_cycle") not in (None, ""):
        parts.append(f"成交周期 {metrics.get('avg_deal_cycle')} 天")
    return "，".join(parts) or "暂无可用样本指标"


def _daily_summary(daily: Dict[str, Any], evidence: list[Any]) -> str:
    if evidence:
        item = evidence[0]
        if isinstance(item, dict):
            text = item.get("summary") or item.get("text") or item.get("title")
        else:
            text = item
        if text:
            return str(text)[:80]
    if daily.get("core_conclusions"):
        return str((daily.get("core_conclusions") or [""])[0])[:80]
    return f"{daily.get('filename') or daily.get('report_id')} 已读取，未命中强相关片段"


def _purchase_conclusion(amount: float, point: float, lower: float, upper: float) -> str:
    if not amount:
        return "未识别到具体收车报价，无法判断能不能收"
    if upper and amount > upper:
        return "已超过最高收车价，需要人工确认"
    if point and amount > point * 1.03:
        return "谨慎，报价高于建议价，需要优秀车况支撑"
    if lower and amount < lower:
        return "可以尝试，价格低于参考区间但需确认车况"
    return "可以进入谈判，仍需核验车况和整备成本"


def _listing_conclusion(amount: float, point: float, lower: float, upper: float) -> str:
    if not amount:
        return "未识别到具体挂牌价，无法判断"
    if upper and amount > upper:
        return "偏高，可能拉长周转"
    if lower and amount < lower:
        return "偏低，需确认是否为快速成交策略"
    if point:
        return "基本合理，可结合车况和议价空间微调"
    return "缺少建议挂牌区间，暂不能判断"


def _customer_offer_conclusion(amount: float, point: float, lower: float, upper: float) -> str:
    if not amount:
        return "未识别到客户报价，无法判断"
    if lower and amount < lower:
        return "客户报价偏低，除非库存压力大否则不建议直接接受"
    if upper and amount > upper:
        return "客户报价高于市场参考，可重点核算毛利后推进"
    return "客户报价接近市场参考，但缺成本时不能判断毛利"


def _confidence_label(value: str) -> str:
    return {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}.get(value.upper(), value or "中")


def _has_market_or_daily_context(report_context: Dict[str, Any]) -> bool:
    market_indicator = report_context.get("market_indicator") if isinstance(report_context.get("market_indicator"), dict) else {}
    market_state = report_context.get("market_state") if isinstance(report_context.get("market_state"), dict) else {}
    daily = report_context.get("daily_report") if isinstance(report_context.get("daily_report"), dict) else {}
    return bool(
        market_indicator.get("matched_rows")
        or market_state.get("recommendation_label")
        or market_state.get("market_category_label")
        or daily.get("filename")
        or daily.get("report_id")
    )


def _table_rows(tables: list[Dict[str, Any]], task_id: str) -> list[list[Any]]:
    for table in tables:
        if table.get("task_id") == task_id and isinstance(table.get("rows"), list):
            return table.get("rows") or []
    return []


def _report_items_from_rows(rows: list[list[Any]], limit: int) -> list[str]:
    items = []
    for row in rows[:limit]:
        if len(row) >= 3:
            items.append(f"{row[0]}：{row[1]}；{row[2]}")
    return items


def _lead_sentence(
    vehicle_title: str,
    point: float,
    lower: float,
    upper: float,
    confidence: str,
    candidate_count: int,
    price_role: str,
    quote_amount: float,
) -> str:
    confidence_text = _confidence_label(confidence)
    if quote_amount and price_role == "purchase_price":
        verdict = _purchase_conclusion(quote_amount, point, lower, upper)
        return f"这台{vehicle_title}的建议收车价为 {_wan_text(point)}，业务区间 {_range_text(lower, upper)}；用户报价 {_wan_text(quote_amount)} 的判断是：{verdict}。"
    if quote_amount and price_role == "listing_price":
        return f"这台{vehicle_title}的建议收车价参考为 {_wan_text(point)}；挂牌 {_wan_text(quote_amount)} 需要对照售车区间和周转目标判断。"
    if quote_amount and price_role == "customer_offer":
        return f"这台{vehicle_title}的建议收车价参考为 {_wan_text(point)}；客户报价 {_wan_text(quote_amount)} 只能先判断市场位置，毛利还需补充成本。"
    return f"这台{vehicle_title}建议围绕 {_wan_text(point)} 谈收车，参考区间 {_range_text(lower, upper)}；超过 {_wan_text(upper)} 不建议继续追。"


def _action_items(
    point: float,
    lower: float,
    upper: float,
    confidence: str,
    candidate_count: int,
    quote_rows: list[list[Any]],
    report_context: Dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if quote_rows:
        actions.append(str(quote_rows[0][-1]))
    if point:
        actions.append(f"先按 {_wan_text(point)} 谈。")
    if upper:
        actions.append(f"超过 {_wan_text(upper)} 不追。")
    actions.append("重点核验事故、泡水、火烧、调表和整备成本。")
    actions.append("客户报价偏高时，用可比车分布、车辆差异和最高收车价解释。")
    return list(dict.fromkeys(item for item in actions if item))[:4]


def _clean_rows(rows: list[list[Any]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        values = [str(item) if item not in (None, "") else "暂无足够证据" for item in row]
        cleaned.append(values)
    return cleaned
