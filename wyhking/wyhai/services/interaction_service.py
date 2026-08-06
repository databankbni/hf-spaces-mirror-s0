from __future__ import annotations

import json
import math
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .intent_service import IntentService
from .global_intent_classifier_v2 import GlobalIntentClassifierV2
from .intent_system import (
    BUY_CAR_INTENT, CANDIDATE_EVIDENCE_REQUEST, DAILY_REPORT_READ_INTENT,
    EXPLANATION_INTENTS, HISTORY_QUOTE_REFERENCE, NON_VALUATION_INTENTS, PRICE_ADJUSTMENT_INTENT,
    PRICE_EXPLANATION_REQUEST, PRICE_FEEDBACK_CLARIFICATION, PRICE_QUOTE_REQUEST, REPORT_DETAIL_QUESTION, RESET_VEHICLE,
    SELL_CAR_VALUATION_INTENT, VALUATION_INTENTS, VEHICLE_INFO_UPDATE, WHY_LOW_CONFIDENCE,
    build_vehicle_state, vehicle_state_hash,
)
from .module_guard_v2 import ModuleGuardV2
from .agent_task_v21 import AgentTaskPlannerV21
from .enterprise_agent_graph_v2 import EnterpriseAgentGraphV2
from .enterprise_tool_registry import build_default_tool_registry
from .enterprise_agent_state_store_v21 import get_enterprise_agent_state_store
from .enterprise_general_answer_service import EnterpriseGeneralAnswerService
from .daily_report_content_service import DailyReportContentService
from .interaction_state import flatten_slots, hash_price_request, merge_slots
from .pricing_request_builder import PricingRequestBuilder
from .quick_tag_service import QuickTagService
from .response_generator import ResponseGenerator
from .slot_extractor import SlotExtractor
from .vehicle_model_normalize_service import VehicleModelNormalizeService
from .pricing_adjustment_shortcuts import build_vehicle_source_lookup_turn, parse_vehicle_source_lookup
from .enterprise_pricing_workflow_v22 import EnterprisePricingWorkflowV22
from .pricing_agent_orchestrator_v23 import build_pricing_agent_package
from .pricing_ladder_completion import complete_legacy_business_ladder


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_LOG = ROOT / "feedback_records" / "interaction_feedback.jsonl"
_SESSION_STATE: Dict[str, Dict[str, Any]] = {}
_SESSION_STATE_MAX = 500
_SUPPORTED_MODULES = {"daily_report", "market_state", "media_pricing"}
_FRONTLINE_BRAND_NAMES = {
    "AITO": "问界",
    "理想汽车": "理想",
    "小米汽车": "小米",
    "小鹏汽车": "小鹏",
    "蔚来汽车": "蔚来",
}
_SLOT_LABELS = {
    "brand": "品牌",
    "series": "车系/车型",
    "model": "车型",
    "trim": "款型配置",
    "model_year": "车型年款",
    "first_license_date": "上牌时间",
    "first_license_year": "上牌时间",
    "first_license_month": "上牌时间",
    "year_disambiguation": "车型年款或上牌时间",
    "city": "城市",
    "mileage_wan_km": "里程",
    "mileage_km": "里程",
    "transfer_count": "过户次数",
    "color": "颜色",
    "vehicle_confirm": "标准车型",
    "standard_vehicle": "标准车型",
    "condition_group": "车况",
    "inspection_grade": "车况",
    "condition": "车况",
}
_MODULE_COMPATIBILITY_MAP = {
    "selection": "market_state",
    "market": "market_state",
    "pricing": "media_pricing",
    "media": "media_pricing",
    "mediaPricing": "media_pricing",
    "acquisition": "media_pricing",
    "sell": "media_pricing",
    "both": "media_pricing",
    "pricing_adjustment": "market_state",
    "jdcPricing": "market_state",
    "price_management": "daily_report",
    "priceManagement": "daily_report",
}


_STREAM_TOOL_LABELS = {
    "selection_strategy_tool": "运行选品策略",
    "market_report_tool": "分析市场行情",
    "daily_report_tool": "读取行业日报",
    "market_indicator_tool": "读取车型行情指标",
    "market_state_tool": "判断行情与风险边界",
    "valuation_tool": "执行单车定价",
    "response_composer": "生成业务结论",
}


def _emit_agent_event(
    event_sink: Optional[Callable[[Dict[str, Any]], None]],
    event_type: str,
    **payload: Any,
) -> None:
    """Publish a live Agent event without coupling the service to HTTP."""

    if event_sink is None:
        return
    try:
        event_sink(
            {
                "event_type": event_type,
                "at": datetime.now().isoformat(timespec="milliseconds"),
                **_json_safe_snapshot(payload),
            }
        )
    except Exception:
        # Observability must never change the business result.
        return


def _emit_stream_plan(
    event_sink: Optional[Callable[[Dict[str, Any]], None]],
    *,
    task_id: str,
    module: str,
    plan: Dict[str, Any],
) -> None:
    """Stream a plan one business action at a time."""

    steps = [str(item) for item in (plan.get("steps") or []) if item]
    plan_head = dict(plan)
    plan_head["steps"] = []
    plan_head["status"] = "planning" if steps else "done"
    _emit_agent_event(
        event_sink,
        "plan.ready",
        task_id=task_id,
        module=module,
        task_plan=plan_head,
    )
    for index, step in enumerate(steps):
        _emit_agent_event(
            event_sink,
            "plan.delta",
            task_id=task_id,
            module=module,
            task_plan_delta={"step": step, "step_index": index, "done": index == len(steps) - 1},
        )


def _emit_stream_step_content(
    event_sink: Optional[Callable[[Dict[str, Any]], None]],
    *,
    task_id: str,
    module: str,
    step: Dict[str, Any],
    already_started: bool = False,
) -> None:
    """Stream conclusion, evidence, impact, action and risk inside one real step."""

    step_id = str(step.get("step_id") or step.get("name") or "business_step")
    name = str(step.get("name") or "执行业务步骤")
    if not already_started:
        _emit_agent_event(
            event_sink,
            "tool.started",
            task_id=task_id,
            module=module,
            step={
                "step_id": step_id,
                "name": name,
                "status": "running",
                "detail": str(step.get("running_detail") or f"正在{name}。"),
            },
        )
    explanation = step.get("business_explanation") if isinstance(step.get("business_explanation"), dict) else {}
    for field in ("conclusion", "evidence", "chips", "impact", "action", "risk"):
        value = explanation.get(field)
        if value in (None, "", []):
            continue
        _emit_agent_event(
            event_sink,
            "tool.delta",
            task_id=task_id,
            module=module,
            step={
                "step_id": step_id,
                "name": name,
                "status": "running",
                "business_explanation": {field: value},
            },
        )
    completed = dict(step)
    completed["step_id"] = step_id
    completed["name"] = name
    completed["status"] = "done"
    completed.pop("running_detail", None)
    _emit_agent_event(
        event_sink,
        "tool.completed",
        task_id=task_id,
        module=module,
        step=completed,
    )


def _stream_ui_module(module: str, client_state: Dict[str, Any]) -> str:
    ui_module = str(client_state.get("ui_module") or "")
    if ui_module in {"selection", "market", "pricing"}:
        return ui_module
    return {
        "market_state": "market",
        "daily_report": "market",
        "media_pricing": "pricing",
    }.get(module, "pricing")


def _stream_plan(
    *,
    message: str,
    module: str,
    client_state: Dict[str, Any],
    intent: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a module-owned plan from the classified intent.

    These are business task contracts, not a simulated frontend timeline.  The
    selected branch and wording are decided after the LangGraph preflight.
    """

    ui_module = _stream_ui_module(module, client_state)
    task_intent = str(intent.get("task_intent") or intent.get("internal_intent") or "")
    slots = intent.get("slots") if isinstance(intent.get("slots"), dict) else {}
    internal_intent = str(intent.get("internal_intent") or "")
    if internal_intent in {"GENERAL_AUTOMOTIVE_QA", "PRICING_LIGHT_QA"}:
        return {
            "title": "汽车业务问答规划",
            "status": "done",
            "understanding": "本轮是车型知识或业务概念问题，只回答当前问题，不重跑选品、行情或定价。",
            "steps": [
                "确认问题对象与问法：区分车型介绍、业务概念与需要执行的任务",
                "查证必要事实并直接回答：只调用与当前问题相关的知识与上下文",
            ],
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "general_automotive_qa",
                "task_intent": task_intent,
                "business_goal": "弄清当前车型或业务问题",
                "business_task": "直接回答，不发起无关的整套任务",
                "business_scope": "不重跑选品榜、日报、行情或定价模型",
                "execution_reason": "问句要求知识解释，没有要求推荐或报价",
                "confidence": intent.get("confidence"),
                "decision": "进入汽车业务问答",
            },
        }
    if ui_module == "selection":
        detail_intent = str(intent.get("selection_detail_intent") or "")
        is_risk_task = task_intent in {"identify_risky_models", "RISKY_MODELS", "selection.risky_models"}
        if detail_intent == "selection.rank_lookup" or task_intent == "lookup_selection_rank":
            steps = [
                "定位榜单和查询名次：读取本次会话最近一次同口径选品结果",
                "核对该名次并直接回答：返回对应车系、经营标签和必要依据",
            ]
            task_name = "查询选品榜单指定名次"
            business_goal = "查清榜单上指定名次是哪个车系"
        elif detail_intent in {"selection.explain_rank_score", "selection.explain_exclusion", "selection.series_judgement"} or task_intent in {"explain_selection_score", "explain_selection_reason", "series_judgement"}:
            steps = [
                "定位目标车系与原榜单：确认用户问的是哪个车系和哪次结果",
                "核对该车系的经营证据：查看成交、利润、周转、亏损和供需信号",
                "解释排名或未推荐原因：给出结论、证据、风险和下一步",
            ]
            task_name = "解释目标车系的选品结果"
            business_goal = "看懂某个车系为什么位于当前名次"
        elif detail_intent in {"selection.signal_rule_explain", "selection.evidence_request", "selection.data_quality", "selection.backtest_metric", "selection.baseline_question"}:
            steps = [
                "确认要查的策略问题：区分计算逻辑、证据、数据质量或回测口径",
                "读取对应的可审计口径：只查当前问题需要的规则、指标和样本",
                "直接解释结论与边界：说明这个口径对一线决策的意义",
            ]
            task_name = "解释选品策略与证据"
            business_goal = "看懂选品结论如何产生"
        elif detail_intent == "selection.policy_newcar_effect":
            steps = [
                "检索相关日报与政策事件：只定位与目标车系直接相关的事件",
                "对照近90天经营证据：验证事件是否已体现在成交、价格或周转中",
                "说明事件影响与业务动作：事件只作风险证据，不单独改写排名",
            ]
            task_name = "分析政策或新车事件对选品的影响"
            business_goal = "判断事件是否改变选品风险"
        else:
            steps = [
                "读取近90天经营数据：确认成交、入库、库存、利润和亏损基础",
                "核对可比较的车系样本：按城市、预算、能源和车身条件统一比较口径",
                "判断供需、周转和价格风险：综合成交、库存、周转、价格趋势和供需指数",
                "排出并解释机会车系与风险车系：输出候选顺序、理由、风险和经营动作",
            ]
            task_name = "识别高风险车系" if is_risk_task else "推荐值得关注的车系"
            business_goal = "找到需要避开的车系" if is_risk_task else "找到值得关注的车系"
        city = slots.get("city") or client_state.get("selectedCity") or "全国"
        return {
            "title": "选品任务规划",
            "status": "done",
            "understanding": f"本轮任务：在{city}按当前经营条件筛选车系；只做选品，不进入单车定价。",
            "steps": steps,
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "car_selection",
                "task_intent": task_intent,
                "business_goal": business_goal,
                "business_task": task_name,
                "business_scope": "只做车系选品，不给具体单车报价",
                "execution_reason": f"已按{city}和当前筛选条件进入{'风险车系识别' if is_risk_task else '机会车系推荐'}",
                "confidence": intent.get("confidence"),
                "decision": "选品条件已确认，可以开始筛选",
            },
        }
    if ui_module == "market":
        wants_national = bool(re.search(r"全国.*行情|行情.*全国|全国二手车|行情研判|全国市场", message))
        city = "全国" if wants_national else (slots.get("city") or client_state.get("selectedCity") or "全国")
        target = slots.get("series") or slots.get("price_band") or "市场整体"
        needs_daily = bool(re.search(r"日报|政策|新车|降价事件|品牌事件", message))
        evidence_step = (
            "读取行情与事件证据：只读取当前范围行情和相关日报事件"
            if needs_daily
            else "读取当前范围行情数据：查看价格、成交、库存和周转"
        )
        return {
            "title": "行情任务规划",
            "status": "done",
            "understanding": f"已识别为行情任务；查询范围为{city} · {target}，不调用单车估价。",
            "steps": [
                "识别查询范围：确认城市、车系或价格带和时间范围",
                evidence_step,
                "判断价格、成交、库存和周转：形成当前市场强弱与风险边界",
                "整理行情结论和经营动作：输出一线可直接使用的结论、风险和动作",
            ],
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "market_report",
                "task_intent": task_intent,
                "business_goal": "看懂当前市场行情",
                "business_task": f"分析{city} · {target}的价格、成交、库存和周转",
                "business_scope": "只做行情判断，不给具体单车报价",
                "execution_reason": "已根据城市和查询对象进入行情分析",
                "confidence": intent.get("confidence"),
                "decision": "查询范围已确认，可以读取行情",
            },
        }
    if intent.get("pricing_advice_mode") == "judge_purchase_price_delta":
        return {
            "title": "追价试算规划",
            "status": "done",
            "understanding": "本轮在当前有效报价上试算加价后的利润和追价边界；车辆参数未变，不重新调用定价模型。",
            "steps": [
                "读取当前建议收车价、预计售车价、成本和最高收车价",
                "计算加价后的收车价、净毛利、毛利率和利润变化",
                "判断是否超过追价上限并给出明确收车动作",
            ],
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "pricing",
                "task_intent": "judge_purchase_price",
                "business_goal": "判断加价后还能不能收",
                "business_task": "基于当前报价实时试算利润和上限",
                "business_scope": "只做价格试算，不修改车辆参数和模型报价",
                "execution_reason": "用户给出相对当前建议价的加价金额",
                "confidence": intent.get("confidence"),
                "decision": "读取当前报价并完成利润试算",
            },
        }
    if internal_intent in {
        "PRICE_EXPLANATION_REQUEST",
        "CANDIDATE_EVIDENCE_REQUEST",
        "WHY_LOW_CONFIDENCE",
        "HISTORY_VEHICLE_REFERENCE",
    }:
        return {
            "title": "已有报价解释规划",
            "status": "done",
            "understanding": "本轮只解释当前有效报价及其证据，不重新估价，也不重复完整定价报告。",
            "steps": [
                "绑定当前报价：核对 quote_id、车辆状态和报价版本",
                "读取价格桥和证据：核对预计售车价、成本利润约束、可比车和七要素影响",
                "直接回答当前追问：先给结论，再说明数字依据、风险边界和可执行动作",
            ],
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "pricing",
                "task_intent": task_intent,
                "business_goal": "看懂当前报价为什么这样定",
                "business_task": "解释当前有效报价，不重新估价",
                "business_scope": "只读当前报价和证据；车辆参数未变化时不得重算",
                "execution_reason": "用户追问的是已有报价依据",
                "confidence": intent.get("confidence"),
                "decision": "读取当前报价并直接解释",
            },
        }
    if internal_intent == "PRICE_FEEDBACK_CLARIFICATION":
        return {
            "title": "价格反馈核对规划",
            "status": "done",
            "understanding": "本轮先定位用户认为哪个价格不准及偏差方向，不反驳、不重算、不要求重填整台车。",
            "steps": [
                "绑定当前报价：确认反馈对应当前车辆和当前报价版本",
                "定位分歧：判断收车价或售车价，以及偏高、偏低或市场参照不一致",
                "给出修正入口：提示补充真实成交、实车检测或具体车辆参数；收到新信息后才重新计算并对比",
            ],
            "can_execute": True,
            "missing_fields": [],
            "intent_route": {
                "module_intent": "pricing",
                "task_intent": "clarify_pricing_feedback",
                "business_goal": "定位报价分歧并决定是否需要重算",
                "business_task": "澄清价格角色、偏差方向和用户证据",
                "business_scope": "当前轮不重新估价；仅在参数或证据变化后重算",
                "execution_reason": "用户质疑已有报价但尚未给出完整分歧信息",
                "confidence": intent.get("confidence"),
                "decision": "先确认分歧，再决定修正动作",
            },
        }
    is_quote = str(intent.get("business_category") or "") == "MEDIA_VALUATION" or task_intent in {
        "PRICE_QUOTE_REQUEST",
        "SELL_CAR_VALUATION_INTENT",
        "estimate_vehicle_value",
        "PURCHASE_PRICE_JUDGEMENT",
    }
    return {
        "title": "定价任务规划" if is_quote else "业务问答规划",
        "status": "done",
        "understanding": (
            "已识别为单车定价任务；先核对标准车型与车辆参数，满足条件后才调用真实定价工具。"
            if is_quote
            else "已识别为汽车业务问答；本轮先回答问题，不会因为出现车型名称就强制进入估价。"
        ),
        "steps": (
            [
                "调用定价模型并核对可比车：按标准车型、市场基线和七要素确定定价基准",
                "解释七要素价格修正：逐项说明上牌、里程、城市、过户、颜色和车况影响",
                "校验完整价格梯度：生成并检查挂牌、实售、收车和最高收车价的排序与利润空间",
                "生成一线定价结论：把模型依据、修正逻辑、谈判边界和风险整理成可直接使用的回答",
            ]
            if is_quote
            else ["识别问题类型和上下文", "读取车型知识与业务事实", "生成直接、可核验的业务回答"]
        ),
        "can_execute": True,
        "missing_fields": [],
        "intent_route": {
            "module_intent": "pricing" if is_quote else "general_automotive_qa",
            "task_intent": task_intent,
            "business_goal": "给具体车辆定价" if is_quote else "回答汽车业务问题",
            "business_task": "生成挂牌价、预计售卖价、收车价和最高收车价" if is_quote else "直接回答当前问题",
            "business_scope": "七要素齐全后执行单车定价" if is_quote else "本轮不调用单车定价",
            "execution_reason": "已识别为明确的单车报价需求" if is_quote else "当前问题不需要生成车辆报价",
            "confidence": intent.get("confidence"),
            "decision": "车辆信息齐全后进入定价" if is_quote else "进入汽车业务问答",
        },
    }


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_json_sanitize(payload), ensure_ascii=False, default=str, allow_nan=False) + "\n")


def _json_sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_sanitize(item) for item in value]
    try:
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _json_sanitize(value.item())
        except Exception:
            pass
    text = str(value)
    return None if text in {"NaN", "nan", "NaT", "inf", "-inf", "<NA>"} else text


def _json_safe_snapshot(value: Any) -> Any:
    """Preserve the complete quote while normalizing runtime-only scalar types."""
    return json.loads(json.dumps(_json_sanitize(value), ensure_ascii=False, default=str, allow_nan=False))


def _slim_reply_card(card: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(card, dict):
        return {}
    recommendations = card.get("strict_recommendations") or card.get("recommendations") or []
    return {
        "card_type": card.get("card_type"),
        "state_id": card.get("state_id"),
        "city": card.get("city"),
        "scope": card.get("scope") or {},
        "answer_mode": card.get("answer_mode") or "task_card",
        "direct_answer": card.get("direct_answer") or {},
        "selection_explanation": card.get("selection_explanation") or {},
        "subject_lookup": card.get("subject_lookup") or {},
        "summary_report": card.get("summary_report") or {},
        "selection_audit": card.get("selection_audit") or {},
        "top_recommendations": [
            {
                "rank": item.get("rank"),
                "brand": item.get("brand"),
                "series": item.get("series"),
                "recommendation_label": item.get("recommendation_label"),
                "opportunity_score": item.get("opportunity_score"),
                "business_score": item.get("business_score"),
                "business_recommend": item.get("business_recommend"),
                "business_avoid": item.get("business_avoid"),
                "strict_rank": item.get("strict_rank"),
                "sold_count_90d": item.get("sold_count_90d"),
                "acquired_count_90d": item.get("acquired_count_90d"),
                "acquisition_conversion_rate": item.get("acquisition_conversion_rate"),
                "sale_conversion_rate": item.get("sale_conversion_rate"),
                "sold_from_acquired_rate": item.get("sold_from_acquired_rate"),
                "avg_deal_cycle": item.get("avg_deal_cycle"),
                "avg_turnover_days": item.get("avg_turnover_days"),
                "avg_gross_profit": item.get("avg_gross_profit"),
                "median_gross_profit": item.get("median_gross_profit"),
                "loss_rate": item.get("loss_rate"),
                "total_profit_contribution": item.get("total_profit_contribution"),
                "market_category": item.get("market_category"),
                "dsi_signal": item.get("dsi_signal") or {},
                "comparison_baseline": item.get("comparison_baseline") or {},
                "comparison_scope": item.get("comparison_scope"),
                "suggested_purchase_price_range": item.get("suggested_purchase_price_range") or {},
                "gate_reasons": item.get("gate_reasons") or [],
                "risks": item.get("risks") or [],
            }
            for item in recommendations[:30]
            if isinstance(item, dict)
        ],
    }


def _slotify(flat: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    slots = {}
    for key, value in (flat or {}).items():
        if isinstance(value, dict) and "value" in value:
            slots[key] = value
        else:
            slots[key] = {"value": value, "confidence": 1.0, "raw": None, "source": "state"}
    return slots


class InteractionService:
    def __init__(self, pricing_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None) -> None:
        self.slot_extractor = SlotExtractor()
        self.intent_service = IntentService()
        self.intent_classifier_v2 = GlobalIntentClassifierV2()
        self.module_guard_v2 = ModuleGuardV2()
        self.vehicle_normalizer = VehicleModelNormalizeService()
        self.pricing_builder = PricingRequestBuilder()
        self.quick_tag_service = QuickTagService()
        self.response_generator = ResponseGenerator()
        self.general_answer_service = EnterpriseGeneralAnswerService()
        self.agent_planner_v21 = AgentTaskPlannerV21()
        self.enterprise_state_store = get_enterprise_agent_state_store()
        self.enterprise_agent_graph_v2 = EnterpriseAgentGraphV2(
            intent_classifier=self.intent_classifier_v2,
            module_guard=self.module_guard_v2,
        )
        self.pricing_callable = pricing_callable
        self.enterprise_tool_registry = build_default_tool_registry(
            selection_handler=self._selection_tool,
            market_handler=self._market_report_tool,
            knowledge_handler=self._automotive_knowledge_tool,
            daily_report_handler=self._daily_report_tool,
            pricing_handler=self._price_quote_tool,
        )

    @staticmethod
    def _tool_execution_summary(invocation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tool_name": invocation.get("tool_name"),
            "status": invocation.get("status"),
            "output_contract": invocation.get("output_contract"),
            "started_at": invocation.get("started_at"),
            "completed_at": invocation.get("completed_at"),
        }

    @staticmethod
    def _selection_tool(
        *, query_text: str, selected_city: str, client_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        from .selection_strategy_service import build_selection_strategy_response

        return build_selection_strategy_response(
            query_text=query_text,
            selected_city=selected_city,
            client_state=client_state,
        )

    @staticmethod
    def _market_report_tool(
        *, query_text: str, selected_city: str, client_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        from .market_report_service import build_market_report_response

        return build_market_report_response(
            query_text=query_text,
            selected_city=selected_city,
            client_state=client_state,
        )

    def _automotive_knowledge_tool(
        self,
        *,
        user_message: str,
        intent_v2: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.general_answer_service.answer(
            user_message=user_message,
            intent_v2=intent_v2,
            client_state=client_state,
        )

    def _daily_report_tool(
        self,
        *,
        message: str,
        intent_v2: Dict[str, Any],
        daily_report_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._daily_report_reply(intent_v2, daily_report_context, message)

    def _price_quote_tool(
        self,
        *,
        price_request: Dict[str, Any],
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
        task_id: str,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        if not self.pricing_callable:
            raise RuntimeError("pricing callable is not configured")
        return EnterprisePricingWorkflowV22(self.pricing_callable).run(
            price_request=price_request,
            slots=slots,
            client_state=client_state,
            task_id=task_id,
            event_sink=event_sink,
        )

    def process_turn(
        self,
        request_payload: Dict[str, Any],
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        session_id = request_payload.get("session_id") or request_payload.get("sessionId") or str(uuid.uuid4())
        turn_id = str(request_payload.get("_stream_task_id") or uuid.uuid4())
        message = (request_payload.get("message") or "").strip()
        event_type = request_payload.get("event_type") or "user_message"
        payload = request_payload.get("payload") or {}
        client_state = self._merge_session_state(session_id, request_payload.get("client_state") or {})
        ui_module = payload.get("ui_module") or request_payload.get("ui_module")
        if ui_module in {"selection", "market", "pricing"}:
            client_state["ui_module"] = ui_module
        if payload.get("selected_vehicle_category"):
            client_state["selectedVehicleCategory"] = payload.get("selected_vehicle_category")
            client_state["selected_vehicle_category"] = payload.get("selected_vehicle_category")
        if payload.get("selected_energy_type"):
            client_state["selectedEnergyType"] = payload.get("selected_energy_type")
            client_state["selected_energy_type"] = payload.get("selected_energy_type")
        if payload.get("selected_body_type"):
            client_state["selectedBodyType"] = payload.get("selected_body_type")
            client_state["selected_body_type"] = payload.get("selected_body_type")
        module_context = self._resolve_module_context(request_payload, client_state)
        client_state["module"] = module_context["module"]
        client_state["selectedBusinessModule"] = module_context["module"]
        client_state["selectedCity"] = module_context["selected_city"]
        daily_report_context = client_state.get("lastDailyReportContext") or client_state.get("last_daily_report_context") or {}
        enterprise_preflight = self.enterprise_agent_graph_v2.run_preflight(
            message=message,
            selected_module=module_context["module"],
            client_state=client_state,
            session_id=session_id,
        )
        classifier_v2 = enterprise_preflight["classifier_result"]
        guarded_v2 = enterprise_preflight["guarded_result"]
        intent_v2 = guarded_v2["intent_result"]
        intent_v2["module_guard_reason"] = guarded_v2["guard_reason"]
        clarify_selection_vehicle = self._should_clarify_selection_vehicle_intent(
            message=message,
            module_context=module_context,
            client_state=client_state,
            intent_v2=intent_v2,
            event_type=event_type,
        )
        # A naked vehicle name entered from the selection surface is genuinely
        # ambiguous. Keep ownership on selection until the user chooses
        # “能不能收” or “估价”; otherwise the generic vehicle router changes
        # the module to pricing before this business clarification can run.
        routed_module = (
            module_context["module"]
            if clarify_selection_vehicle
            else intent_v2.get("selected_module") or module_context["module"]
        )
        if routed_module != module_context["module"]:
            module_context = {
                "module": routed_module,
                "selected_city": module_context.get("selected_city"),
                "blocks_pricing": routed_module in {"daily_report", "market_state"},
            }
            client_state["module"] = routed_module
            client_state["selectedBusinessModule"] = routed_module
        ui_stream_module = _stream_ui_module(module_context["module"], client_state)
        execution_route = str(enterprise_preflight.get("execution_route") or "information_collection")
        _emit_agent_event(
            event_sink,
            "intent.classified",
            task_id=turn_id,
            module=ui_stream_module,
            intent={
                "module_intent": intent_v2.get("module_intent"),
                "task_intent": intent_v2.get("task_intent") or intent_v2.get("internal_intent"),
                "internal_intent": intent_v2.get("internal_intent"),
                "confidence": intent_v2.get("confidence"),
                "reason": intent_v2.get("reason"),
                "source": (
                    "qwen_structured"
                    if intent_v2.get("llm_intent_primary") or intent_v2.get("llm_intent_fallback")
                    else "reviewed_rules_and_semantics"
                ),
            },
            agent_intro={
                "selection": "已识别为选品任务，正在按经营范围生成执行计划。",
                "market": "已识别为行情任务，正在确定查询口径和证据范围。",
                "pricing": "已识别为定价或汽车业务任务，正在生成对应工具计划。",
            }.get(ui_stream_module, "已识别业务意图，正在生成执行计划。"),
        )
        _emit_stream_plan(
            event_sink,
            task_id=turn_id,
            module=ui_stream_module,
            plan=_stream_plan(
                message=message,
                module=module_context["module"],
                client_state=client_state,
                intent=intent_v2,
            ),
        )
        if clarify_selection_vehicle:
            return self._build_selection_vehicle_intent_clarification(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                module_context=module_context,
                client_state=client_state,
                intent_v2=intent_v2,
            )
        if intent_v2.get("internal_intent") == "MODULE_SWITCH":
            return self._process_module_switch_turn(
                session_id=session_id,
                turn_id=turn_id,
                client_state=client_state,
                intent_v2=intent_v2,
            )
        if execution_route == "general_answer":
            _emit_stream_step_content(
                event_sink,
                task_id=turn_id,
                module=ui_stream_module,
                step={
                    "step_id": "qa_scope",
                    "name": "确认问题对象与问法",
                    "status": "done",
                    "business_explanation": {
                        "conclusion": "已确认本轮是车型知识或业务概念问题。",
                        "evidence": [f"用户问题：{message}"],
                        "impact": "不会因为当前停留在选品页就重跑选品榜。",
                        "action": "只查证当前问题所需的事实。",
                        "risk": "本轮不生成选品或定价结论。",
                    },
                },
            )
            _emit_agent_event(
                event_sink,
                "tool.started",
                task_id=turn_id,
                module=ui_stream_module,
                step={
                    "step_id": "qa_answer",
                    "name": "查证必要事实并直接回答",
                    "status": "running",
                    "detail": "正在核对车型身份、关键事实和业务含义。",
                },
            )
            response = self._process_general_automotive_qa_turn(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                module_context=module_context,
                client_state=client_state,
                intent_v2=intent_v2,
            )
            response["enterprise_agent_graph"] = enterprise_preflight
            answer_text = str((response.get("reply") or {}).get("text") or "已完成当前问题回答。")
            _emit_stream_step_content(
                event_sink,
                task_id=turn_id,
                module=ui_stream_module,
                already_started=True,
                step={
                    "step_id": "qa_answer",
                    "name": "查证必要事实并直接回答",
                    "status": "done",
                    "business_explanation": {
                        "conclusion": answer_text,
                        "evidence": ["回答已限定在当前问题范围"],
                        "impact": "一线可直接理解这个车型或概念，不被无关任务过程干扰。",
                        "action": "如需要行情、选品或定价，再明确发起对应任务。",
                        "risk": "车型知识回答不等于当前市场价格。",
                    },
                },
            )
            if module_context["module"] == "media_pricing" and self._is_pricing_light_qa(message):
                response["lightweight_route"] = "pricing_light_qa"
                response.setdefault("pricing", {})["price_state"] = "pricing_light_qa"
                response.setdefault("reply", {})["style"] = "pricing_light_qa"
            return response
        if execution_route == "daily_report":
            _emit_agent_event(
                event_sink,
                "tool.started",
                task_id=turn_id,
                module=ui_stream_module,
                step={
                    "step_id": "daily_report_tool",
                    "name": _STREAM_TOOL_LABELS["daily_report_tool"],
                    "status": "running",
                    "detail": "正在读取已上传日报并定位与问题相关的事实。",
                },
            )
            report_response = self._process_daily_report_turn(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                module_context=module_context,
                client_state=client_state,
                daily_report_context=daily_report_context,
                intent_v2=intent_v2,
            )
            report_response["enterprise_agent_graph"] = enterprise_preflight
            _emit_agent_event(
                event_sink,
                "tool.completed",
                task_id=turn_id,
                module=ui_stream_module,
                step={
                    "step_id": "daily_report_tool",
                    "name": _STREAM_TOOL_LABELS["daily_report_tool"],
                    "status": "done",
                    "detail": "已读取日报事实并完成与当前问题相关的业务回答。",
                },
            )
            return report_response
        if execution_route in {"selection", "market_report"}:
            market_response = self._process_market_state_turn(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                module_context=module_context,
                client_state=client_state,
                intent_v2=intent_v2,
                event_sink=event_sink,
            )
            market_response["enterprise_agent_graph"] = enterprise_preflight
            return market_response
        current_flat = flatten_slots(client_state.get("current_slots") or {})

        shortcut = parse_vehicle_source_lookup(message)
        if shortcut:
            return build_vehicle_source_lookup_turn(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                shortcut=shortcut,
            )

        synthetic_message = self._message_from_event(event_type, message, payload)
        extraction = self.slot_extractor.extract(synthetic_message or message, client_state)
        self._merge_v2_slots_into_extraction(extraction, intent_v2.get("slots") or {})
        if event_type in {"quick_tag_click", "field_update"}:
            self._apply_event_payload(extraction, payload)

        intent = self._legacy_intent_from_v2(intent_v2)
        if intent.get("type") == "UNKNOWN_OR_INCOMPLETE":
            intent = self.intent_service.classify(message or synthetic_message, extraction, client_state)
        if intent_v2.get("internal_intent") == "PRICE_FEEDBACK_CLARIFICATION" or intent_v2.get("pricing_advice_mode") == "judge_purchase_price_delta":
            # Amounts in evidence statements such as “网上同款都卖23万” are
            # market-price references, not a 23万公里 mileage update.  A price
            # challenge is read-only until the user explicitly edits a vehicle
            # field, so do not let generic number extraction invalidate the
            # quote or mutate the active vehicle.
            for field in (
                "brand", "series", "model_year", "first_license_date",
                "first_license_year", "first_license_month", "reg_date",
                "trim", "raw_vehicle_text", "mileage_km", "mileage_wan_km",
                "city", "transfer_count", "color", "condition",
                "condition_group", "inspection_grade",
            ):
                (extraction.get("slots") or {}).pop(field, None)
        if intent_v2.get("is_hypothetical"):
            return self._process_hypothetical_turn(
                session_id=session_id,
                turn_id=turn_id,
                client_state=client_state,
                intent_v2=intent_v2,
            )
        reset_for_new_vehicle = self._is_explicit_new_vehicle_message(
            message=message,
            extraction=extraction,
            event_type=event_type,
            client_state=client_state,
        )
        identity_context_reset = self._is_vehicle_identity_update(
            message=message,
            extraction=extraction,
            event_type=event_type,
            current_flat=current_flat,
        )
        quote_preserving_context_intents = {DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION}
        context_only_intent = (
            intent.get("type") in NON_VALUATION_INTENTS
            and intent.get("type") not in quote_preserving_context_intents
        )
        if reset_for_new_vehicle or context_only_intent:
            current_flat = {}
        elif identity_context_reset:
            current_flat = self._preserve_pricing_conditions_for_identity_update(current_flat)

        had_existing_slots = bool(current_flat)
        merged_slots, stale = merge_slots(current_flat, extraction.get("slots") or {})
        self._sanitize_vehicle_parameter_slots(merged_slots)
        self._normalize_first_license_slots(merged_slots)
        structured_vehicle_match = (
            self._vehicle_match_from_payload(extraction.get("vehicle_match_payload") or {})
            if event_type == "field_update"
            else {}
        )
        if structured_vehicle_match:
            self._apply_structured_vehicle_match_to_slots(merged_slots, structured_vehicle_match)
            stale = True
        if not had_existing_slots and not reset_for_new_vehicle:
            stale = False
        if reset_for_new_vehicle:
            stale = bool(client_state.get("current_pricing_result"))
        if identity_context_reset:
            stale = bool(client_state.get("current_pricing_result") or client_state.get("current_slots"))
        if structured_vehicle_match:
            vehicle_match = structured_vehicle_match
        elif event_type == "quick_tag_click" and payload.get("type") == "select_model":
            vehicle_match = self._vehicle_match_from_payload(payload.get("payload") or payload)
            if vehicle_match:
                self._apply_structured_vehicle_match_to_slots(merged_slots, vehicle_match)
                stale = True
            else:
                vehicle_match = client_state.get("current_vehicle_match") or {}
        else:
            existing_vehicle_match = {} if identity_context_reset else (client_state.get("current_vehicle_match") or {})
            vehicle_fields_changed = False
            for field in ("brand", "series", "model_year", "trim", "raw_vehicle_text"):
                incoming = (extraction.get("slots") or {}).get(field) or {}
                value = incoming.get("value") if isinstance(incoming, dict) else incoming
                if value not in (None, "") and str(value) != str(current_flat.get(field) or ""):
                    vehicle_fields_changed = True
                    break
            if reset_for_new_vehicle or identity_context_reset:
                vehicle_match = self.vehicle_normalizer.normalize(_slotify(merged_slots), message)
            elif existing_vehicle_match.get("matched") and not vehicle_fields_changed:
                vehicle_match = existing_vehicle_match
            else:
                vehicle_match = self.vehicle_normalizer.normalize(_slotify(merged_slots), message)

        if identity_context_reset and not any(
            self._slot_value_from_extraction(extraction, key) not in (None, "")
            for key in ("model_year", "trim", "vehicle_confirmed")
        ):
            vehicle_match = {
                **(vehicle_match or {}),
                "matched": False,
                "need_manual_confirm": True,
                "model_id": "",
                "model_name": "",
            }

        # Once the catalog has resolved the active vehicle, keep its canonical
        # brand/series in the conversation slots too.  The extractor may return
        # an abbreviation such as ``3系`` while the catalog has already matched
        # ``宝马3系``.  Leaving the two representations out of sync breaks later
        # natural-language follow-ups and makes the form/result disagree.
        if vehicle_match and (vehicle_match.get("matched") or identity_context_reset):
            canonical_brand = vehicle_match.get("brand_name") or vehicle_match.get("brand")
            canonical_series = vehicle_match.get("series_name") or vehicle_match.get("series")
            if canonical_brand:
                merged_slots["brand"] = self._frontline_brand_name(canonical_brand)
            if canonical_series:
                merged_slots["series"] = canonical_series

        task = self._resolve_task(intent, client_state)
        if task != "UNKNOWN":
            merged_slots["task"] = task

        active_vehicle_state = build_vehicle_state(merged_slots)
        active_vehicle_state_hash = vehicle_state_hash(active_vehicle_state)
        non_pricing_lifecycle = intent.get("type") in NON_VALUATION_INTENTS or intent.get("type") in EXPLANATION_INTENTS
        stale_quote_reason = ""
        if stale:
            stale_quote_reason = "VEHICLE_STATE_CHANGED"
        if intent.get("type") in {BUY_CAR_INTENT, PRICE_ADJUSTMENT_INTENT, RESET_VEHICLE}:
            stale_quote_reason = "NON_VALUATION_INTENT_INVALIDATES_ACTIVE_QUOTE"
        current_hash = (client_state.get("current_pricing_result") or {}).get("price_request_hash") or client_state.get("price_request_hash")
        current_price_result = client_state.get("current_pricing_result") or {}
        previous_price_result = dict(current_price_result) if isinstance(current_price_result, dict) else {}
        if reset_for_new_vehicle or identity_context_reset:
            current_hash = None
            current_price_result = {}
        history_quote_reference = None
        if intent.get("type") == HISTORY_QUOTE_REFERENCE:
            history_quote_reference = self._resolve_history_quote_reference(message, client_state)
            if history_quote_reference:
                current_price_result = history_quote_reference.get("pricing_result") or history_quote_reference.get("price_result") or history_quote_reference
                referenced_slots = history_quote_reference.get("slots") or {}
                referenced_match = history_quote_reference.get("vehicle_match") or {}
                if referenced_slots:
                    merged_slots = dict(referenced_slots)
                    active_vehicle_state = build_vehicle_state(merged_slots)
                    active_vehicle_state_hash = vehicle_state_hash(active_vehicle_state)
                if referenced_match:
                    vehicle_match = referenced_match
        if intent.get("type") in NON_VALUATION_INTENTS and intent.get("type") not in quote_preserving_context_intents and intent.get("type") != RESET_VEHICLE:
            current_price_result = {}
        if intent.get("type") == RESET_VEHICLE:
            current_price_result = {}
            merged_slots = {}
            active_vehicle_state = build_vehicle_state(merged_slots)
            active_vehicle_state_hash = vehicle_state_hash(active_vehicle_state)
        pricing = {
            "should_call_price": False,
            "called_price": False,
            "price_request": {},
            "price_result": current_price_result,
            "price_state": "not_ready",
            "quote_status": "STALE" if stale_quote_reason else ("COMPLETED" if current_price_result else "NONE"),
            "stale_quote_reason": stale_quote_reason,
            "active_vehicle_state_hash": active_vehicle_state_hash,
        }
        warnings: list[str] = []
        errors: list[str] = []
        pricing_workflow: Dict[str, Any] = {}

        if module_context["module"] == "media_pricing" and self._is_pricing_light_qa(message):
            return self._process_pricing_light_qa_turn(
                session_id=session_id,
                turn_id=turn_id,
                message=message,
                module_context=module_context,
                client_state=client_state,
                intent_v2=intent_v2,
                merged_slots=merged_slots,
                current_price_result=current_price_result,
                active_vehicle_state=active_vehicle_state,
                active_vehicle_state_hash=active_vehicle_state_hash,
            )

        if intent.get("type") in NON_VALUATION_INTENTS:
            build = {"should_call_price": False, "price_request": {}, "missing_fields": [], "price_request_hash": ""}
            missing_fields = []
            pricing["price_state"] = "non_pricing_intent"
        elif intent.get("type") in EXPLANATION_INTENTS:
            build = {"should_call_price": False, "price_request": {}, "missing_fields": [], "price_request_hash": ""}
            missing_fields = []
            pricing["price_state"] = "explain_ready" if current_price_result else "explain_missing_quote"
        else:
            build = self.pricing_builder.build(merged_slots, vehicle_match, task, session_id)
            missing_fields = build["missing_fields"]
            validation_errors = build.get("validation_errors") or {}
            if "YEAR_AMBIGUOUS_MODEL_OR_LICENSE" in (extraction.get("ambiguity") or []) and "year_disambiguation" not in missing_fields:
                missing_fields.append("year_disambiguation")

            if validation_errors:
                pricing["price_state"] = "invalid_input"
                errors.extend(validation_errors.values())
            elif missing_fields:
                pricing["price_state"] = "not_ready"
            elif stale and client_state.get("current_pricing_result"):
                pricing["price_state"] = "stale"
            elif not missing_fields:
                pricing["price_state"] = "ready"

        disable_pricing = (
            bool(request_payload.get("disable_pricing"))
            or bool(payload.get("disable_pricing"))
            or module_context["blocks_pricing"]
        )
        price_ready_intents = set(VALUATION_INTENTS) | {
            SELL_CAR_VALUATION_INTENT,
            "SELL_CAR_PRICE",
            "BUY_CAR_PRICE",
            "BOTH_PRICE",
        }
        should_run = (
            build["should_call_price"]
            and not disable_pricing
            and not missing_fields
            and intent.get("type") in price_ready_intents
            and (event_type == "quick_tag_click" and payload.get("type") == "run_pricing" or intent.get("confidence", 0) >= 0.72)
        )
        intent_v2["should_call_pricing"] = bool(should_run and build.get("price_request_hash") != current_hash)
        if should_run and build.get("price_request_hash") != current_hash:
            pricing["should_call_price"] = True
            pricing["price_request"] = build["price_request"]
            pricing["price_request_hash"] = build["price_request_hash"]
            if self.pricing_callable:
                try:
                    pricing_invocation = self.enterprise_tool_registry.invoke(
                        "price_quote_tool",
                        {
                            "price_request": dict(build["price_request"]),
                            "slots": merged_slots,
                            "client_state": client_state,
                            "task_id": turn_id,
                        },
                        runtime={"event_sink": event_sink},
                    )
                    pricing_workflow = pricing_invocation.get("output") or {}
                    result = pricing_workflow.get("price_result") or {}
                    if isinstance(result, dict):
                        result = complete_legacy_business_ladder(
                            result,
                            slots=merged_slots,
                        )
                        result["price_request_hash"] = build["price_request_hash"]
                        result["quote_id"] = result.get("quote_id") or result.get("request_id") or result.get("traceId") or turn_id
                        result["vehicle_state"] = active_vehicle_state
                        result["vehicle_state_hash"] = active_vehicle_state_hash
                    pricing.update(
                        {
                            "called_price": True,
                            "price_result": result,
                            "price_state": "predicted" if result and result.get("success", True) else "failed",
                            "workflow_version": pricing_workflow.get("workflow_version"),
                            "workflow_trace_id": pricing_workflow.get("trace_id"),
                            "tool_execution": self._tool_execution_summary(pricing_invocation),
                        }
                    )
                    if not result:
                        errors.append("PRICE_CALL_FAILED: valuation_tool returned no result")
                except Exception as exc:
                    pricing.update({"called_price": True, "price_state": "failed"})
                    errors.append(f"PRICE_CALL_FAILED: {exc}")
        elif not missing_fields and build.get("price_request_hash") == current_hash and client_state.get("current_pricing_result"):
            pricing["price_state"] = "predicted"

        price_change_comparison = self._build_price_change_comparison(
            previous_price_result=previous_price_result,
            new_price_result=pricing.get("price_result") or {},
            called_price=bool(pricing.get("called_price")),
        )

        if intent.get("type", "").startswith("FEEDBACK"):
            self._record_feedback(session_id, message, intent, merged_slots, pricing.get("price_result") or {})

        quick_tags = self.quick_tag_service.build(
            intent=intent,
            slots=merged_slots,
            vehicle_match=vehicle_match,
            missing_fields=missing_fields,
            price_state=pricing["price_state"],
        )
        self._attach_quick_tag_context(quick_tags, merged_slots, vehicle_match, missing_fields)
        reply = self.response_generator.generate(
            user_message=message,
            intent=intent,
            slots=merged_slots,
            vehicle_match=vehicle_match,
            missing_fields=missing_fields,
            quick_tags=quick_tags,
            pricing=pricing,
            warnings=warnings,
            fallback_used=bool(extraction.get("fallback_used")),
            fallback_reason=extraction.get("fallback_reason", ""),
        )
        if price_change_comparison:
            reply = {
                "text": price_change_comparison["summary"],
                "style": "price_change_comparison",
                "cards": [{"type": "price_change_comparison", **price_change_comparison}],
            }
        business_decision = self._build_business_price_decision(intent_v2, pricing.get("price_result") or {})
        if business_decision and business_decision.get("status") == "ready":
            reply = {
                "text": business_decision["summary"],
                "style": "business_price_decision",
                "cards": [{"type": "business_price_decision", **business_decision}],
            }
        elif event_type == "field_update" and not missing_fields and not pricing.get("called_price"):
            reply = {
                "text": "车辆七要素已更新完成，可以按新参数重新估价。",
                "style": "vehicle_parameters_ready",
                "cards": [],
            }
        if module_context["blocks_pricing"]:
            quick_tags = []
            reply = self._module_non_pricing_reply(module_context, daily_report_context)

        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": intent,
            "intent_v2": intent_v2,
            "slots": merged_slots,
            "vehicle_match": vehicle_match,
            "missing_fields": missing_fields,
            "validation_errors": build.get("validation_errors") or {},
            "quick_tags": quick_tags,
            "pricing": pricing,
            "reply": reply,
            "business_price_decision": business_decision,
            "price_change_comparison": price_change_comparison,
            "active_task_type": intent.get("type"),
            "vehicle_state": active_vehicle_state,
            "vehicle_state_hash": active_vehicle_state_hash,
            "quote_lifecycle": {
                "quote_status": pricing.get("quote_status"),
                "stale_quote_reason": pricing.get("stale_quote_reason"),
                "active_vehicle_state_hash": active_vehicle_state_hash,
                "default_reference": "latest_active_quote",
                "history_reference": history_quote_reference or {},
            },
            "module": module_context["module"],
            "selected_city": module_context["selected_city"],
            "module_context": module_context,
            "enterprise_agent_graph": enterprise_preflight,
            "pricing_workflow": pricing_workflow,
            "workflow_tool_results": pricing_workflow.get("tool_results") or [],
            "pricing_report_context": pricing_workflow.get("report_context") or {},
            "last_daily_report_context": (
                pricing_workflow.get("daily_report_context")
                or (daily_report_context if module_context["module"] == "daily_report" else {})
            ),
            "last_market_opportunity_context": pricing_workflow.get("market_context") or {},
            "warnings": warnings,
            "errors": errors,
            "debug": {
                "enabled": bool(request_payload.get("debug") or client_state.get("debug")),
                "intent_source": intent.get("source"),
                "reset_for_new_vehicle": reset_for_new_vehicle,
                "identity_context_reset": identity_context_reset,
                "slot_sources": {k: (v.get("source") if isinstance(v, dict) else "state") for k, v in (extraction.get("slots") or {}).items()},
                "llm_model": extraction.get("llm_model", ""),
                "fallback_used": bool(extraction.get("fallback_used")),
                "fallback_reason": extraction.get("fallback_reason", ""),
                "module": module_context["module"],
                "selected_city": module_context["selected_city"],
                "has_daily_report_context": bool(daily_report_context),
                "enterprise_agent_graph_version": enterprise_preflight.get("graph_version"),
                "enterprise_agent_framework": enterprise_preflight.get("framework"),
            },
        }
        if module_context["module"] == "media_pricing" and missing_fields:
            response["lightweight_route"] = "pricing_light_slot_check"
            response["light_card"] = self._build_missing_slots_light_card(merged_slots, missing_fields)
            response["agent_intro"] = response["light_card"]["summary"]
            response["final_result"] = {
                "type": "missing_slots",
                "status": "blocked",
                "title": response["light_card"]["title"],
                "summary": response["light_card"]["summary"],
                "metrics": {
                    "missing_slots": response["light_card"]["missing_slots"],
                    "known_slots": response["light_card"]["known_slots"],
                    "quick_reply_examples": response["light_card"]["quick_reply_examples"],
                    "light_card": response["light_card"],
                },
                "actions": response["light_card"]["quick_reply_examples"],
            }
            self._attach_agent_v21(
                response,
                daily_report_context=daily_report_context,
            )
            response = _json_safe_snapshot(response)
            self._remember_session_state(
                session_id=session_id,
                response=response,
                client_state=client_state,
                reset_for_new_vehicle=reset_for_new_vehicle,
                identity_context_reset=identity_context_reset,
            )
            return response
        if module_context["module"] == "media_pricing" and response.get("validation_errors"):
            validation_errors = response["validation_errors"]
            summary = "；".join(str(value) for value in validation_errors.values())
            response["lightweight_route"] = "pricing_invalid_input"
            response["agent_intro"] = f"车辆信息存在不合理值：{summary}。请修改后再估价。"
            response["final_result"] = {
                "type": "invalid_vehicle_fields",
                "status": "blocked",
                "title": "请先修正车辆信息",
                "summary": summary,
                "metrics": {
                    "field_errors": validation_errors,
                    "known_slots": self._known_slots_for_light_card(merged_slots),
                },
                "actions": ["修改车辆参数"],
            }
            self._attach_agent_v21(
                response,
                daily_report_context=daily_report_context,
            )
            response = _json_safe_snapshot(response)
            self._remember_session_state(
                session_id=session_id,
                response=response,
                client_state=client_state,
                reset_for_new_vehicle=reset_for_new_vehicle,
                identity_context_reset=identity_context_reset,
            )
            return response
        self._attach_agent_v21(
            response,
            daily_report_context=daily_report_context,
        )
        pricing_follow_up_intents = {
            PRICE_EXPLANATION_REQUEST,
            CANDIDATE_EVIDENCE_REQUEST,
            WHY_LOW_CONFIDENCE,
            HISTORY_QUOTE_REFERENCE,
            "FEEDBACK_INACCURATE",
            "FEEDBACK_PRICE_TOO_HIGH",
            "FEEDBACK_PRICE_TOO_LOW",
        }
        internal_follow_up_intents = {
            "PRICE_EXPLANATION_REQUEST",
            "PRICE_FEEDBACK_CLARIFICATION",
            "CANDIDATE_EVIDENCE_REQUEST",
            "WHY_LOW_CONFIDENCE",
            "HISTORY_VEHICLE_REFERENCE",
        }
        is_pricing_follow_up = (
            intent.get("type") in pricing_follow_up_intents
            or intent_v2.get("internal_intent") in internal_follow_up_intents
            or (
                intent_v2.get("internal_intent") == "PURCHASE_PRICE_JUDGEMENT"
                and bool(pricing.get("price_result"))
                and not pricing.get("called_price")
            )
        )
        if module_context["module"] == "media_pricing" and not is_pricing_follow_up:
            try:
                pricing_agent = build_pricing_agent_package(
                    message=message,
                    response=response,
                    preview_mode=disable_pricing,
                )
                if price_change_comparison:
                    pricing_agent["price_change_comparison"] = price_change_comparison
                    final_report = pricing_agent.get("final_report")
                    if isinstance(final_report, dict):
                        final_report["price_change_comparison"] = price_change_comparison
                final_report = pricing_agent.get("final_report")
                current_price_result = pricing.get("price_result")
                if (
                    isinstance(final_report, dict)
                    and isinstance(current_price_result, dict)
                    and bool(current_price_result)
                    and final_report.get("point_price_yuan") not in (None, "", 0)
                ):
                    # Follow-up profit judgements must use exactly the same
                    # cost inputs shown by the report calculator.  Persist the
                    # inputs on the active quote before session memory is saved;
                    # this does not alter any model price.
                    current_price_result["business_cost_inputs"] = {
                        "reconditioning_cost": float(final_report.get("estimated_recon_cost_yuan") or 0),
                        "channel_cost": float(final_report.get("platform_service_cost_yuan") or 0),
                        "holding_cost": 0.0,
                        "risk_buffer": float(final_report.get("risk_buffer_yuan") or 0),
                    }
                response["pricing_agent"] = pricing_agent
                response["pricing_agent_events"] = pricing_agent.get("events") or []
                if pricing_agent.get("agent_intro"):
                    response["agent_intro"] = pricing_agent["agent_intro"]
            except Exception as exc:
                response.setdefault("warnings", []).append(f"PRICING_AGENT_V23_ATTACH_FAILED: {exc}")
        elif module_context["module"] == "media_pricing" and is_pricing_follow_up:
            if intent_v2.get("internal_intent") == "PRICE_FEEDBACK_CLARIFICATION" or str(intent.get("type") or "").startswith("FEEDBACK"):
                response["agent_intro"] = "收到价格质疑。本轮先定位是哪个价格、偏高还是偏低，并核对当前报价依据；不会重新估价，也不会重复整份报告。"
            elif intent_v2.get("internal_intent") == "PURCHASE_PRICE_JUDGEMENT":
                response["agent_intro"] = "收到。我会基于当前有效报价试算这个收车价的利润和追价边界；车辆参数未变化，本轮不重新调用定价模型。"
            else:
                response["agent_intro"] = "收到。我会读取当前有效报价、可比证据和车辆参数，直接回答这个追问；本轮不会重新估价，也不会重复整份报告。"
            response["pricing_follow_up"] = {
                "mode": "read_current_quote",
                "quote_id": (pricing.get("price_result") or {}).get("quote_id") or (pricing.get("price_result") or {}).get("request_id"),
                "vehicle_state_hash": active_vehicle_state_hash,
                "internal_intent": intent_v2.get("internal_intent"),
                "reprice": False,
            }
        response = _json_safe_snapshot(response)
        self._remember_session_state(
            session_id=session_id,
            response=response,
            client_state=client_state,
            reset_for_new_vehicle=reset_for_new_vehicle,
            identity_context_reset=identity_context_reset,
        )
        return response

    @staticmethod
    def _should_clarify_selection_vehicle_intent(
        *,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
        event_type: str,
    ) -> bool:
        """Ask what to do when a selection user only types a vehicle name.

        A vehicle entity by itself is genuinely ambiguous: it may mean “is it
        worth acquiring?” or “price this particular car”.  Routing it straight
        to the selection ranking (or straight to missing pricing fields) makes
        the product appear hard-coded to the current tab.  Explicit business
        verbs always win and bypass this clarification.
        """

        if event_type != "user_message":
            return False
        if module_context.get("module") != "market_state" or client_state.get("ui_module") != "selection":
            return False
        text = re.sub(r"\s+", " ", str(message or "")).strip()
        # The frontend prepends the active selection scope, e.g.
        # “全国，Model Y” or “北京 新能源 SUV，Model Y”. That prefix is UI
        # context rather than user prose and must not make a bare vehicle name
        # fail the punctuation check below.
        if "，" in text or "," in text:
            head, tail = re.split(r"[，,]", text, maxsplit=1)
            scope_values = {
                str(client_state.get("selectedCity") or "").strip(),
                str(client_state.get("selectedEnergyType") or "").strip(),
                str(client_state.get("selectedBodyType") or "").strip(),
                "全国",
                "全部",
            }
            head_tokens = {token for token in re.split(r"\s+", head.strip()) if token}
            if tail.strip() and head_tokens and all(token in scope_values for token in head_tokens):
                text = tail.strip()
        if not text or len(text) > 40:
            return False
        if re.search(
            r"能不能收|可不可以收|值得收|推荐收|要不要收|不建议收|避免收|"
            r"估价|定价|多少钱|价格|卖多少|收多少|最高收|挂牌|"
            r"排名|第几|榜单|为什么|怎么排|数据|指标|行情|走势|降价|"
            r"是什么车|怎么样|对比|比较|风险|利润|周转|DSI",
            text,
            flags=re.I,
        ):
            return False
        slots = intent_v2.get("slots") if isinstance(intent_v2.get("slots"), dict) else {}
        has_vehicle = any(slots.get(key) not in (None, "") for key in ("series", "trim", "model", "brand"))
        if not has_vehicle:
            return False
        # A long sentence containing a recognized brand is not a bare vehicle
        # entity.  Accept common model punctuation/digits but reject normal
        # sentence punctuation and business prose.
        compact = re.sub(r"[\s·._+\-/]", "", text)
        return bool(compact and not re.search(r"[，。！？；：,!?;:]", text) and len(compact) <= 24)

    def _build_selection_vehicle_intent_clarification(
        self,
        *,
        session_id: str,
        turn_id: str,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
    ) -> Dict[str, Any]:
        slots = dict(intent_v2.get("slots") or {})
        vehicle_name = str(
            slots.get("trim")
            or slots.get("series")
            or slots.get("model")
            or slots.get("brand")
            or message
        ).strip()
        current_price_result = client_state.get("current_pricing_result") or {}
        summary = (
            f"你输入了“{vehicle_name}”，我还不能确定你是想判断这个车系值不值得收，"
            "还是想给一辆具体车辆估价。选择后我会进入对应链路，不会把两个任务混在一起。"
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": "SELECTION_VEHICLE_INTENT_CLARIFICATION",
                "task": "CLARIFY",
                "confidence": 1.0,
                "source": "business_disambiguation",
                "reason": "裸车系输入同时可能指向选品判断和单车估价",
            },
            "intent_v2": {
                **intent_v2,
                "internal_intent": "SELECTION_VEHICLE_INTENT_CLARIFICATION",
                "task_intent": "clarify_vehicle_business_action",
                "answer_mode": "clarification",
            },
            "slots": slots,
            "vehicle_match": {},
            "missing_fields": [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "selection_vehicle_intent_clarification",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            },
            "reply": {
                "text": summary,
                "style": "selection_vehicle_intent_clarification",
                "cards": [],
            },
            "final_result": {
                "type": "clarification_result",
                "status": "blocked",
                "title": "你想判断能不能收，还是给这辆车估价？",
                "summary": summary,
                "actions": [
                    f"判断{vehicle_name}能不能收",
                    f"给{vehicle_name}估价",
                ],
            },
            "active_task_type": "SELECTION_VEHICLE_INTENT_CLARIFICATION",
            "vehicle_state": {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": module_context.get("module") or "market_state",
            "selected_city": module_context.get("selected_city") or "全国",
            "module_context": module_context,
            "enterprise_agent_graph": {},
        }

    @staticmethod
    def _is_pricing_light_qa(message: str) -> bool:
        text = re.sub(r"\s+", "", message or "")
        if not text:
            return False
        patterns = [
            ("收车价" in text and "售车价" in text and any(word in text for word in ("区别", "差别", "不同", "什么关系"))),
            ("毛利" in text and any(word in text for word in ("怎么算", "怎么计算", "公式", "计算方式"))),
            ("过户" in text and any(word in text for word in ("为什么", "为啥", "影响", "要看", "看这个"))),
            ("反馈" in text and any(word in text for word in ("有什么用", "作用", "干嘛", "为什么要"))),
            ("追价上限" in text and any(word in text for word in ("是什么", "什么意思", "怎么用"))),
        ]
        return any(patterns)

    def _process_pricing_light_qa_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
        merged_slots: Dict[str, Any],
        current_price_result: Dict[str, Any],
        active_vehicle_state: Dict[str, Any],
        active_vehicle_state_hash: str,
    ) -> Dict[str, Any]:
        answer = self._pricing_light_qa_answer(message)
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": "PRICING_LIGHT_QA",
                "task": "NONE",
                "confidence": max(float(intent_v2.get("confidence") or 0.78), 0.78),
                "source": "pricing_light_router",
                "reason": "pricing module lightweight FAQ",
            },
            "intent_v2": {**intent_v2, "internal_intent": "PRICING_LIGHT_QA", "should_call_pricing": False},
            "slots": merged_slots,
            "vehicle_match": client_state.get("current_vehicle_match") or {},
            "missing_fields": [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "pricing_light_qa",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": active_vehicle_state_hash,
            },
            "reply": {"text": answer, "style": "pricing_light_qa", "cards": []},
            "active_task_type": "PRICING_LIGHT_QA",
            "vehicle_state": active_vehicle_state,
            "vehicle_state_hash": active_vehicle_state_hash,
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": active_vehicle_state_hash,
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": module_context.get("module") or "media_pricing",
            "selected_city": module_context.get("selected_city"),
            "module_context": module_context,
            "lightweight_route": "pricing_light_qa",
            "final_result": {
                "type": "knowledge_answer",
                "status": "done",
                "title": "定价业务说明",
                "summary": answer,
                "metrics": {"lightweight_route": "pricing_light_qa"},
                "actions": [],
            },
            "task_card": {},
            "agent_v21": {},
            "warnings": [],
            "errors": [],
            "debug": {
                "enabled": bool(client_state.get("debug")),
                "intent_source": "pricing_light_router",
                "module": module_context.get("module"),
            },
        }
        response = _json_safe_snapshot(response)
        self._remember_session_state(
            session_id=session_id,
            response=response,
            client_state=client_state,
            reset_for_new_vehicle=False,
            identity_context_reset=False,
        )
        return response

    @staticmethod
    def _pricing_light_qa_answer(message: str) -> str:
        text = re.sub(r"\s+", "", message or "")
        if "收车价" in text and "售车价" in text:
            return "收车价是门店把车收进来的价格，重点看风险和安全边际；售车价是后面卖给买家的预期价格，重点看成交、周转和利润空间。实际做业务时，先守住收车价，再用售车价和整备成本测算毛利。"
        if "毛利" in text:
            return "毛利可以简单理解为：预计售车价 - 当前收车价 - 整备成本 - 过户/运营等成本 - 风险缓冲。页面里的试算价改动后，毛利会跟着重新算，但这不代表模型重新估价。"
        if "过户" in text:
            return "过户次数会影响买家心理和后续流通。次数越多，客户越容易担心车况或使用历史，所以收车时通常要更谨慎，必要时把检测和整备风险留进报价里。"
        if "反馈" in text:
            return "反馈会进入相似任务记忆，用来优化下次报告解释和对客话术，比如少暴露内部价格、先讲检测和整备。它不会直接改模型点价，也不会把一次反馈当成价格规则。"
        if "追价上限" in text:
            return "追价上限是内部安全边界，不是给客户看的报价。超过这个数，后续整备、库存和再销售风险会明显变高，需要人工确认，不能直接承诺客户。"
        return "这是定价模块的轻量说明，不会进入完整估价链路。补齐车辆七要素后，我再给收车价、售车价和利润测算。"

    @staticmethod
    def _build_missing_slots_light_card(slots: Dict[str, Any], missing_fields: list[str]) -> Dict[str, Any]:
        missing_labels = [InteractionService._slot_label(field) for field in missing_fields]
        known_slots = InteractionService._known_slots_for_light_card(slots)
        examples = InteractionService._quick_reply_examples(missing_fields)
        title = f"还差 {len(missing_labels)} 个信息才能估价"
        summary = f"还差 {len(missing_labels)} 个信息才能估价：{'、'.join(missing_labels)}。补齐后我可以同时给你收车价、售车价和利润测算。"
        return {
            "type": "missing_slots",
            "card_type": "missing_slots",
            "title": title,
            "summary": summary,
            "missing_slots": missing_labels,
            "known_slots": known_slots,
            "quick_reply_examples": examples,
        }

    @staticmethod
    def _known_slots_for_light_card(slots: Dict[str, Any]) -> Dict[str, Any]:
        known: Dict[str, Any] = {}
        mapping = [
            ("标准车型", "standard_vehicle"),
            ("车型线索", "raw_vehicle_text"),
            ("车型", "series"),
            ("上牌时间", "first_license_date"),
            ("里程", "mileage_wan_km"),
            ("城市", "city"),
            ("过户次数", "transfer_count"),
            ("颜色", "color"),
            ("车况", "condition_group"),
        ]
        for label, key in mapping:
            value = slots.get(key)
            if value in (None, ""):
                continue
            if key == "mileage_wan_km":
                known[label] = f"{value}万公里"
            elif key == "transfer_count":
                known[label] = f"{value}次"
            else:
                known[label] = value
        return known

    @staticmethod
    def _quick_reply_examples(missing_fields: list[str]) -> list[str]:
        missing = set(missing_fields or [])
        examples: list[str] = []
        if {"first_license_date", "first_license_year", "first_license_month", "year_disambiguation"} & missing:
            examples.append("2024-06上牌")
        if {"mileage_wan_km", "mileage_km"} & missing:
            examples.append("1.8万公里")
        if "transfer_count" in missing:
            examples.append("1次过户")
        if "color" in missing:
            examples.append("白色")
        if {"condition_group", "inspection_grade", "condition"} & missing:
            examples.append("B级车况")
        if {"vehicle_confirm", "standard_vehicle", "trim", "series", "model"} & missing:
            examples.append("2024款 宝马3系 325Li M运动套装")
        if "city" in missing:
            examples.append("北京")
        if len(examples) < 2:
            examples.extend(["2024-06上牌，1万公里", "北京，1次过户，白色"])
        return examples[:3]

    @staticmethod
    def _slot_label(field: str) -> str:
        return _SLOT_LABELS.get(str(field), str(field))

    @staticmethod
    def _build_business_price_decision(intent_v2: Dict[str, Any], price_result: Dict[str, Any]) -> Dict[str, Any]:
        if intent_v2.get("internal_intent") != "PURCHASE_PRICE_JUDGEMENT":
            return {}
        user_price = (intent_v2.get("slots") or {}).get("user_given_price_yuan")

        ladder = price_result.get("price_ladder") or (
            (price_result.get("appraiser_decision_record") or {}).get("final_price_ladder_yuan")
        ) or {}

        def _number(*values: Any) -> Optional[float]:
            for value in values:
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    return parsed
            return None

        def _range(values: Any, point: float, *, low_ratio: float, high_ratio: float) -> tuple[float, float]:
            if isinstance(values, (list, tuple)) and len(values) >= 2:
                low = _number(values[0])
                high = _number(values[1])
                if low is not None and high is not None:
                    return min(low, high), max(low, high)
            return point * low_ratio, point * high_ratio

        c2b = _number(
            ladder.get("expected_c2b_yuan"),
            ladder.get("expected_c2b"),
            price_result.get("final_price"),
            (price_result.get("price") or {}).get("point"),
            (price_result.get("price_result") or {}).get("point_price"),
        )
        try:
            user_price = float(user_price)
        except (TypeError, ValueError):
            return {"status": "waiting_for_quote", "user_given_price_yuan": user_price}
        if c2b is None:
            return {"status": "waiting_for_quote", "user_given_price_yuan": user_price}

        legacy_interval = (
            price_result.get("business_interval")
            or price_result.get("interval")
            or price_result.get("price_interval")
            or {}
        )
        legacy_c2b_range = None
        if isinstance(legacy_interval, dict):
            legacy_c2b_range = [legacy_interval.get("low"), legacy_interval.get("high")]
        c2b_range = _range(
            ladder.get("c2b_range_yuan") or ladder.get("c2b_range") or legacy_c2b_range,
            c2b,
            low_ratio=0.95,
            high_ratio=1.03,
        )
        max_c2b = _number(
            ladder.get("max_c2b_yuan"),
            ladder.get("max_c2b"),
            price_result.get("max_c2b_price_yuan"),
            c2b_range[1],
        ) or c2b_range[1]
        max_c2b = max(max_c2b, c2b)
        b2c = _number(
            ladder.get("expected_b2c_transaction_yuan"),
            ladder.get("expected_b2c_transaction"),
        ) or max(max_c2b * 1.04, c2b * 1.08)
        listing = _number(
            ladder.get("recommended_listing_yuan"),
            ladder.get("recommended_listing"),
            price_result.get("recommended_listing_price_yuan"),
        ) or b2c * 1.05
        b2c_range = _range(
            ladder.get("b2c_transaction_range_yuan") or ladder.get("b2c_range"),
            b2c,
            low_ratio=0.97,
            high_ratio=1.03,
        )
        listing_range = _range(
            ladder.get("recommended_listing_range_yuan") or price_result.get("recommended_listing_range_yuan"),
            listing,
            low_ratio=0.98,
            high_ratio=1.02,
        )

        if not (listing > b2c > max_c2b >= c2b > 0):
            return {
                "status": "invalid_price_ladder",
                "user_given_price_yuan": user_price,
                "reason": "价格顺序异常，未生成收车判断",
            }

        delta_ratio = user_price / c2b - 1
        if user_price <= c2b:
            judgement = "有安全空间"
            action = "先核验车况、手续和整备项；没有隐藏风险时可以继续推进"
        elif user_price <= max_c2b:
            judgement = "在可谈上限内"
            action = "仍可谈，但要把验车发现的整备费用继续往下扣，不要超过最高收车价"
        else:
            judgement = "超过最高收车价"
            action = "不建议按这个价收；应压到最高收车价以内，并根据验车结果继续扣减"

        def _wan(value: float) -> str:
            return f"{value / 10000:.2f}万"

        four_prices = (
            f"建议挂牌价{_wan(listing)}（{_wan(listing_range[0])}-{_wan(listing_range[1])}）；"
            f"预计实际售车价{_wan(b2c)}（{_wan(b2c_range[0])}-{_wan(b2c_range[1])}）；"
            f"预计实际收车价{_wan(c2b)}（{_wan(c2b_range[0])}-{_wan(c2b_range[1])}）；"
            f"最高收车价{_wan(max_c2b)}。"
        )
        summary = (
            f"{four_prices}客户报价{_wan(user_price)}，结论：{judgement}。{action}。"
        )
        cost_inputs = price_result.get("business_cost_inputs") or {}
        operating_cost = sum(
            float(cost_inputs.get(key) or 0)
            for key in (
                "refurbishment_cost",
                "inspection_and_logistics_cost",
                "capital_cost",
                "selling_cost",
                "risk_reserve",
                "reconditioning_cost",
                "channel_cost",
                "holding_cost",
                "risk_buffer",
            )
        )
        original_profit = b2c - c2b - operating_cost
        new_profit = b2c - user_price - operating_cost
        new_profit_rate = new_profit / b2c if b2c else 0.0
        delta_yuan = float(intent_v2.get("price_delta_yuan") or 0)
        summary = (
            f"{four_prices}如果按{_wan(user_price)}收车，按预计实际售车价{_wan(b2c)}计算，"
            f"预计价差毛利约{_wan(new_profit)}（价差毛利率{new_profit_rate * 100:.1f}%）。"
            f"结论：{judgement}。{action}。"
        )
        if delta_yuan:
            boundary_text = (
                f"已经超过当前最高收车价{_wan(max_c2b)}，不建议直接加价"
                if user_price > max_c2b
                else f"仍在当前最高收车价{_wan(max_c2b)}以内，但不能再突破该上限"
            )
            summary = (
                f"在原建议收车价{_wan(c2b)}基础上加{int(round(delta_yuan)):,}元后，试算收车价为{_wan(user_price)}；"
                f"{boundary_text}。按预计实际售车价{_wan(b2c)}和当前成本计算，"
                f"预计价差毛利约{_wan(new_profit)}（价差毛利率{new_profit_rate * 100:.1f}%），"
                f"较原方案减少{_wan(max(0.0, original_profit - new_profit))}。{action}。"
            )
        return {
            "status": "ready",
            "user_given_price_yuan": user_price,
            "recommended_listing_yuan": listing,
            "recommended_listing_range_yuan": list(listing_range),
            "expected_b2c_transaction_yuan": b2c,
            "b2c_transaction_range_yuan": list(b2c_range),
            "expected_c2b_yuan": c2b,
            "c2b_range_yuan": list(c2b_range),
            "max_c2b_yuan": max_c2b,
            "suggested_purchase_low_yuan": c2b_range[0],
            "suggested_purchase_high_yuan": c2b_range[1],
            "maximum_purchase_reference_yuan": max_c2b,
            "delta_ratio": delta_ratio,
            "judgement": judgement,
            "risk_action": action,
            "price_delta_yuan": delta_yuan,
            "operating_cost_yuan": operating_cost,
            "original_net_profit_yuan": original_profit,
            "trial_net_profit_yuan": new_profit,
            "trial_net_profit_rate": round(new_profit_rate, 4),
            "summary": summary,
            "disclaimer": "最终收车前仍要以现场验车、手续核验和实际整备费用为准。",
        }

    @staticmethod
    def _build_price_change_comparison(
        *,
        previous_price_result: Dict[str, Any],
        new_price_result: Dict[str, Any],
        called_price: bool,
    ) -> Dict[str, Any]:
        """Explain a genuine reprice after vehicle facts changed.

        A comparison is only produced when this turn actually called the
        pricing model and the bound vehicle state changed.  This prevents an
        explanation/challenge follow-up from being presented as a new quote.
        """
        if not called_price or not previous_price_result or not new_price_result:
            return {}
        old_hash = str(previous_price_result.get("vehicle_state_hash") or "")
        new_hash = str(new_price_result.get("vehicle_state_hash") or "")
        if not old_hash or not new_hash or old_hash == new_hash:
            return {}

        def _number(*values: Any) -> Optional[float]:
            for value in values:
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    return parsed
            return None

        def _ladder(result: Dict[str, Any]) -> Dict[str, Any]:
            return result.get("price_ladder") or (
                (result.get("appraiser_decision_record") or {}).get("final_price_ladder_yuan")
            ) or {}

        def _price_points(result: Dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[float]]:
            ladder = _ladder(result)
            c2b = _number(
                ladder.get("expected_c2b_yuan"),
                ladder.get("expected_c2b"),
                result.get("final_price"),
                (result.get("price") or {}).get("point"),
                (result.get("price_result") or {}).get("point_price"),
            )
            b2c = _number(
                ladder.get("expected_b2c_transaction_yuan"),
                ladder.get("expected_b2c_transaction"),
                result.get("b2cPrice"),
                result.get("b2c_price"),
            )
            max_c2b = _number(
                ladder.get("max_c2b_yuan"),
                ladder.get("max_c2b"),
                result.get("max_c2b_price_yuan"),
            )
            return c2b, b2c, max_c2b

        old_c2b, old_b2c, old_max = _price_points(previous_price_result)
        new_c2b, new_b2c, new_max = _price_points(new_price_result)
        if old_c2b is None or new_c2b is None:
            return {}

        old_state = previous_price_result.get("vehicle_state") or {}
        new_state = new_price_result.get("vehicle_state") or {}
        labels = {
            "brand": "品牌",
            "series": "车系",
            "model_year": "款型年份",
            "first_license_date": "上牌时间",
            "first_license_year": "上牌年份",
            "first_license_month": "上牌月份",
            "trim": "标准车型",
            "powertrain": "能源类型",
            "mileage_km": "里程",
            "city": "城市",
            "transfer_count": "过户次数",
            "color": "颜色",
            "condition_grade": "车况",
        }

        def _display(key: str, value: Any) -> str:
            if value in (None, ""):
                return "未填写"
            if key == "mileage_km":
                try:
                    return f"{float(value) / 10000:.1f}万公里"
                except (TypeError, ValueError):
                    return str(value)
            if key == "transfer_count":
                return f"{value}次"
            return str(value)

        changed_fields = []
        for key, label in labels.items():
            old_value = old_state.get(key)
            new_value = new_state.get(key)
            if old_value == new_value:
                continue
            changed_fields.append(
                {
                    "field": key,
                    "label": label,
                    "old_value": old_value,
                    "new_value": new_value,
                    "old_display": _display(key, old_value),
                    "new_display": _display(key, new_value),
                }
            )
        if not changed_fields:
            return {}

        costs = new_price_result.get("business_cost_inputs") or {}
        operating_cost = _number(costs.get("total"))
        if operating_cost is None:
            operating_cost = sum(
                float(costs.get(key) or 0)
                for key in (
                    "refurbishment_cost",
                    "inspection_and_logistics_cost",
                    "capital_cost",
                    "selling_cost",
                    "risk_reserve",
                    "minimum_gross_profit",
                )
            )
        operating_cost = float(operating_cost or 0)
        new_net_profit = (
            float(new_b2c) - float(new_c2b) - operating_cost
            if new_b2c is not None
            else None
        )
        new_profit_rate = (
            new_net_profit / float(new_b2c)
            if new_net_profit is not None and new_b2c
            else None
        )

        def _wan(value: Optional[float]) -> str:
            return "暂缺" if value is None else f"{value / 10000:.2f}万"

        delta = float(new_c2b) - float(old_c2b)
        direction = "上调" if delta > 0 else ("下调" if delta < 0 else "不变")
        changes_text = "；".join(
            f"{item['label']}由{item['old_display']}改为{item['new_display']}"
            for item in changed_fields[:4]
        )
        profit_text = ""
        if new_net_profit is not None:
            profit_text = f"，按新预计售车价和当前成本测算，净毛利约{_wan(new_net_profit)}"
            if new_profit_rate is not None:
                profit_text += f"（{new_profit_rate * 100:.1f}%）"
        ceiling_text = f"，最高收车价{_wan(new_max)}" if new_max is not None else ""
        summary = (
            f"已按新参数重新调用定价模型。原建议收车价{_wan(old_c2b)}，"
            f"新建议收车价{_wan(new_c2b)}，{direction}{_wan(abs(delta))}。"
            f"本次变化来自：{changes_text}{profit_text}{ceiling_text}。"
        )
        return {
            "status": "ready",
            "old_quote_id": previous_price_result.get("quote_id") or previous_price_result.get("request_id"),
            "new_quote_id": new_price_result.get("quote_id") or new_price_result.get("request_id"),
            "old_vehicle_state_hash": old_hash,
            "new_vehicle_state_hash": new_hash,
            "changed_fields": changed_fields,
            "old_expected_c2b_yuan": old_c2b,
            "new_expected_c2b_yuan": new_c2b,
            "c2b_change_yuan": delta,
            "old_expected_b2c_yuan": old_b2c,
            "new_expected_b2c_yuan": new_b2c,
            "old_max_c2b_yuan": old_max,
            "new_max_c2b_yuan": new_max,
            "operating_cost_yuan": operating_cost,
            "new_net_profit_yuan": new_net_profit,
            "new_net_profit_rate": new_profit_rate,
            "summary": summary,
        }

    def _resolve_module_context(self, request_payload: Dict[str, Any], client_state: Dict[str, Any]) -> Dict[str, Any]:
        nested_payload = request_payload.get("payload") if isinstance(request_payload.get("payload"), dict) else {}
        raw_module = (
            request_payload.get("module")
            or nested_payload.get("module")
            or request_payload.get("selectedBusinessModule")
            or nested_payload.get("selectedBusinessModule")
            or client_state.get("module")
            or client_state.get("selectedBusinessModule")
            or "media_pricing"
        )
        module = _MODULE_COMPATIBILITY_MAP.get(str(raw_module), str(raw_module))
        if module not in _SUPPORTED_MODULES:
            module = "media_pricing"
        selected_city = (
            request_payload.get("selected_city")
            or nested_payload.get("selected_city")
            or nested_payload.get("selectedCity")
            or client_state.get("selectedCity")
            or client_state.get("selected_city")
            or client_state.get("last_selected_city")
            or (
                (client_state.get("lastMarketOpportunityContext") or {}).get("city")
                if isinstance(client_state.get("lastMarketOpportunityContext"), dict)
                else None
            )
            or None
        )
        if module == "market_state" and not selected_city:
            selected_city = "全国"
        return {
            "module": module,
            "selected_city": selected_city,
            "blocks_pricing": module in {"daily_report", "market_state"},
        }

    def _process_market_state_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        ui_module = client_state.get("ui_module")
        text = str(message or "")
        market_task_intents = {
            "model_market_report",
            "city_market_report",
            "price_band_report",
            "new_car_impact_report",
            "DAILY_REPORT_DISCOUNT_QUERY",
        }
        selection_task_intents = {
            "recommend_models",
            "recommend_price_band",
            "recommend_city_opportunity",
            "identify_risky_models",
            "compare_series",
            "low_price_opportunity",
            "series_judgement",
            "lookup_selection_rank",
            "selection_to_pricing",
            "explain_selection_reason",
            "explain_selection_score",
            "show_selection_evidence",
            "run_signal_ablation",
            "show_backtest_metrics",
            "explain_baseline",
            "explain_total_profit_scale",
            "explain_data_quality",
            "explain_signal_rule",
            "explain_policy_newcar_effect",
            "export_selection_report",
            "sort_filter_selection_result",
            "refine_selection_scope",
            "adjust_selection_signals",
            "answer_contextual_selection_question",
            "rewrite_selection_response",
            "explain_module_boundary",
            "handle_selection_constraints",
            "refuse_unsafe_selection_request",
            "clarify_selection_scope",
        }
        selection_reason_text = bool(
            re.search(
                r"选品推荐|推荐里|为什么.*推荐|为什么.*不推荐|为什么.*不建议|"
                r"为什么.*不在.*推荐|不在.*选品|不在.*推荐|机会分|推荐原因|值得收|风险车系|"
                r"回测|baseline|基线|总利润|选中率|样本可信|证据|DSI|排行榜|策略对照|ablation|"
                r"排序|筛选|导出.*选品|价格带机会|城市机会|暂缓|避坑|别碰",
                text,
                flags=re.I,
            )
        )
        explicit_discount_board_query = bool(
            intent_v2.get("internal_intent") == "DAILY_REPORT_DISCOUNT_QUERY"
            or (
                re.search(r"降价(?:榜|排行)|新车降价榜|降价.*最多|优惠.*最多", text)
                and re.search(r"打开|查看|看看|在不在|有没有|排名|第几|数据|筛选|榜单|哪些|什么车|哪.*车|最多", text)
                and not re.search(r"为什么|风险还是机会|选品策略|推荐收|值得收|适合收|怎么影响收车", text)
            )
        )
        # The clicked tab is presentation context only.  A typed question must
        # be dispatched by its task contract; otherwise every question in the
        # selection tab degenerates into the same selection workflow.
        use_selection_strategy = (
            not explicit_discount_board_query
            and (
                intent_v2.get("module_intent") == "car_selection"
                or intent_v2.get("task_intent") in selection_task_intents
                or selection_reason_text
            )
        )
        use_market_report = (
            not use_selection_strategy
            and (
                explicit_discount_board_query
                or intent_v2.get("module_intent") == "market_report"
                or intent_v2.get("task_intent") in market_task_intents
            )
        )
        enterprise_tool_execution: Dict[str, Any] = {}
        session_ranking_snapshot: Dict[str, Any] = {}
        if use_selection_strategy:
            needs_event_context = bool(re.search(r"日报|政策|新车|上市|降价事件|品牌事件", text))
            live_step = {
                "step_id": "daily_report_tool" if needs_event_context else "market_indicator_tool",
                "name": "读取行业事件与近90天经营数据" if needs_event_context else "读取近90天经营与分类数据",
                "status": "running",
                "detail": (
                    "正在读取相关行业事件、成交、入库、库存和周转数据。"
                    if needs_event_context
                    else "正在按本轮城市、预算、品牌、能源和车身约束生成候选集。"
                ),
            }
            _emit_agent_event(
                event_sink,
                "tool.started",
                task_id=turn_id,
                module="selection",
                step=live_step,
            )

            selection_client_state = dict(client_state)
            selection_client_state["intent_v2_slots"] = dict(intent_v2.get("slots") or {})
            selection_client_state["selection_detail_intent"] = intent_v2.get("selection_detail_intent")
            selection_client_state["selection_task_intent"] = intent_v2.get("selection_task_intent") or intent_v2.get("task_intent")
            selection_client_state["answer_mode"] = intent_v2.get("answer_mode")
            invocation = self.enterprise_tool_registry.invoke(
                "selection_strategy_tool",
                {
                    "query_text": message,
                    "selected_city": module_context.get("selected_city") or "全国",
                    "client_state": selection_client_state,
                },
            )
            enterprise_tool_execution = self._tool_execution_summary(invocation)
            result = invocation.get("output") or {}
            selection_card = result.get("market_agent_card") or {}
            session_ranking_snapshot = selection_card.pop("_session_ranking_snapshot", {}) or {}
            direct_answer = selection_card.get("direct_answer") or {}
            if direct_answer:
                from .grounded_agent_answer_service import get_grounded_agent_answer_service

                direct_answer = get_grounded_agent_answer_service().enhance_selection_answer(
                    query=message,
                    answer_mode=str(selection_card.get("answer_mode") or "task_card"),
                    deterministic_answer=direct_answer,
                )
                selection_card["direct_answer"] = direct_answer
            reply_text = str(
                direct_answer.get("text")
                or direct_answer.get("conclusion")
                or "收到，我会按成交、库存、周转、价格稳定和供需指数筛选选品机会。"
            )
            reply_style = "selection_strategy_agent"
            agent_kind = "selection_strategy"
            streamed_steps = [
                step for step in (selection_card.get("task_execution") or [])
                if isinstance(step, dict)
            ]
            if streamed_steps:
                for index, step in enumerate(streamed_steps):
                    _emit_stream_step_content(
                        event_sink,
                        task_id=turn_id,
                        module="selection",
                        step=step,
                        already_started=index == 0,
                    )
            else:
                _emit_agent_event(
                    event_sink,
                    "tool.completed",
                    task_id=turn_id,
                    module="selection",
                    step={
                        **live_step,
                        "status": "done",
                        "detail": str(
                            direct_answer.get("conclusion")
                            or direct_answer.get("text")
                            or "已完成机会车系与风险车系筛选，并生成可执行经营动作。"
                        ),
                    },
                )
        elif use_market_report:
            live_step = {
                "step_id": "market_scope_tool",
                "name": "识别查询范围",
                "status": "running",
                "detail": "正在确认城市、车系或价格带和时间范围。",
            }
            _emit_agent_event(
                event_sink,
                "tool.started",
                task_id=turn_id,
                module="market",
                step=live_step,
            )

            invocation = self.enterprise_tool_registry.invoke(
                "market_report_tool",
                {
                    "query_text": message,
                    "selected_city": module_context.get("selected_city") or "全国",
                    "client_state": client_state,
                },
            )
            enterprise_tool_execution = self._tool_execution_summary(invocation)
            result = invocation.get("output") or {}
            reply_text = "收到，我会按安全行情数据口径分析成交、在售、价格变化和周转，并给出经营动作。"
            reply_style = "market_report_agent"
            agent_kind = "market_report"
            market_card = result.get("market_agent_card") or {}
            direct = market_card.get("direct_answer") or {}
            summary = market_card.get("summary_report") or {}
            reply_text = str(
                direct.get("text")
                or direct.get("conclusion")
                or summary.get("headline")
                or summary.get("summary")
                or reply_text
            )
            streamed_steps = [
                step for step in (market_card.get("task_execution") or [])
                if isinstance(step, dict)
            ]
            if streamed_steps:
                for index, step in enumerate(streamed_steps):
                    _emit_stream_step_content(
                        event_sink,
                        task_id=turn_id,
                        module="market",
                        step=step,
                        already_started=index == 0,
                    )
            else:
                _emit_agent_event(
                    event_sink,
                    "tool.completed",
                    task_id=turn_id,
                    module="market",
                    step={
                        **live_step,
                        "status": "done",
                        "detail": str(
                            direct.get("conclusion")
                            or direct.get("text")
                            or summary.get("summary")
                            or "已完成行情判断并生成经营动作。"
                        ),
                    },
                )
        else:
            from .market_opportunity_service import build_market_opportunity_response

            result = build_market_opportunity_response(
                query_text=message,
                selected_city=module_context.get("selected_city") or "全国",
                client_state=client_state,
            )
            reply_text = f"收到您的请求，即将为您分析{result['market_agent_card'].get('city')}二手车市场中值得关注的车系与行情趋势。"
            reply_style = "market_opportunity_agent"
            agent_kind = "legacy_market_opportunity"
        card = result["market_agent_card"]
        recommendations = card.get("recommendations") or []
        slim_card = _slim_reply_card(card)
        market_context = {
            "state_id": card.get("state_id"),
            "city": card.get("city"),
            "query_text": card.get("query_text"),
            "scope": card.get("scope") or {},
            # Persist the exact displayed ranking snapshot.  Natural-language
            # follow-ups such as “第七名为什么这么排” must read this snapshot,
            # not recompute a potentially different list.
            "top_recommendations": slim_card.get("top_recommendations") or [],
            "all_ranked_candidates": session_ranking_snapshot.get("all_ranked_candidates") or [],
            "all_avoid_items": session_ranking_snapshot.get("all_avoid_items") or [],
            "candidate_count": session_ranking_snapshot.get("candidate_count") or len(recommendations),
            "avoid_count": session_ranking_snapshot.get("avoid_count") or 0,
            "subject_lookup": card.get("subject_lookup") or {},
            "created_at": card.get("created_at"),
        }
        current_price_result = client_state.get("current_pricing_result") or {}
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": intent_v2.get("internal_intent") or "MARKET_STATE_QUERY",
                "task": "UNKNOWN",
                "confidence": intent_v2.get("confidence", 1.0),
                "source": "global_intent_v2",
                "reason": intent_v2.get("reason") or "market_state module owns the city opportunity workflow",
            },
            "intent_v2": intent_v2,
            "slots": {},
            "vehicle_match": {},
            "missing_fields": [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "non_pricing_market_agent",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            },
            "reply": {
                "text": reply_text,
                "style": reply_style,
                "cards": [_slim_reply_card(card)],
            },
            "active_task_type": intent_v2.get("internal_intent") or "MARKET_STATE_QUERY",
            "vehicle_state": {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": "market_state",
            "selected_city": card.get("city"),
            "module_context": {
                "module": "market_state",
                "selected_city": card.get("city"),
                "blocks_pricing": True,
            },
            "last_daily_report_context": {},
            "last_market_opportunity_context": market_context,
            "market_agent_card": card,
            "enterprise_tool_execution": enterprise_tool_execution,
            "warnings": [],
            "errors": [],
            "debug": {
                "enabled": bool(client_state.get("debug")),
                "module": "market_state",
                "selected_city": card.get("city"),
                "market_dataset_available": card.get("card_type") != "empty_market_opportunity_agent",
                "market_result_count": len(recommendations),
                "agent_kind": agent_kind,
            },
        }
        self._attach_agent_v21(
            response,
            market_agent_card=card,
        )
        existing = _SESSION_STATE.get(session_id) or {}
        existing.update(
            {
                "last_module": "market_state",
                "last_selected_city": card.get("city"),
                "lastMarketOpportunityContext": market_context,
                "current_pricing_result": current_price_result,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _SESSION_STATE[session_id] = existing
        return response

    def _process_daily_report_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        daily_report_context: Dict[str, Any],
        intent_v2: Dict[str, Any],
    ) -> Dict[str, Any]:
        internal_intent = intent_v2.get("internal_intent") or "UNKNOWN_OR_INCOMPLETE"
        report_query = intent_v2.get("daily_report_query") or {}
        requested_date = report_query.get("requested_date")
        effective_context = dict(daily_report_context or {})
        report_service = DailyReportContentService()
        is_existing_report_follow_up = bool(effective_context) and internal_intent not in {
            "DAILY_REPORT_READ",
            "DAILY_REPORT_HISTORY",
        }
        target_date = (
            str(requested_date)
            if requested_date
            else str(effective_context.get("report_date") or "")
            if is_existing_report_follow_up
            else report_service.latest_date()
        )
        if target_date and effective_context.get("report_date") != target_date:
            document = report_service.card_payload(target_date)
            if document:
                effective_context = {
                    "report_id": document.get("filename") or f"daily_report_{target_date}.pdf",
                    "filename": document.get("filename") or f"daily_report_{target_date}.pdf",
                    "report_date": target_date,
                    "source_type": document.get("source_type") or "uploaded_report_extracted",
                    "source_label": document.get("source_label") or "汽车行业每日采集·最新脱敏版",
                    "privacy_level": document.get("privacy_level") or "desensitized",
                    "sections": document.get("sections") or [],
                    "core_conclusions": document.get("core_conclusions") or [],
                }
        legacy_type = (
            DAILY_REPORT_READ_INTENT
            if internal_intent in {"DAILY_REPORT_READ", "DAILY_REPORT_HISTORY"}
            else REPORT_DETAIL_QUESTION
        )
        current_price_result = client_state.get("current_pricing_result") or {}
        invocation = self.enterprise_tool_registry.invoke(
            "daily_report_tool",
            {
                "message": message,
                "intent_v2": intent_v2,
                "daily_report_context": effective_context,
            },
        )
        reply = invocation.get("output") or {}
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": legacy_type,
                "task": "REPORT",
                "confidence": intent_v2.get("confidence", 0.9),
                "source": "global_intent_v2",
                "reason": intent_v2.get("reason") or "",
            },
            "intent_v2": intent_v2,
            "slots": {},
            "vehicle_match": {},
            "missing_fields": [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "non_pricing_daily_report",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            },
            "reply": reply,
            "active_task_type": internal_intent,
            "vehicle_state": {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": "daily_report",
            "selected_city": None,
            "module_context": module_context,
            "last_daily_report_context": effective_context,
            "enterprise_tool_execution": self._tool_execution_summary(invocation),
            "warnings": [],
            "errors": [],
            "debug": {
                "enabled": bool(client_state.get("debug")),
                "intent_source": "global_intent_v2",
                "module": "daily_report",
                "has_daily_report_context": bool(effective_context),
            },
        }
        self._attach_agent_v21(
            response,
            daily_report_context=effective_context,
        )
        existing = _SESSION_STATE.get(session_id) or {}
        existing.update(
            {
                "last_module": "daily_report",
                "lastDailyReportContext": effective_context,
                "current_pricing_result": current_price_result,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _SESSION_STATE[session_id] = existing
        return response

    def _process_general_automotive_qa_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        message: str,
        module_context: Dict[str, Any],
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_price_result = client_state.get("current_pricing_result") or {}
        invocation = self.enterprise_tool_registry.invoke(
            "automotive_knowledge_tool",
            {
                "user_message": message,
                "intent_v2": intent_v2,
                "client_state": client_state,
            },
        )
        reply = invocation.get("output") or {}
        knowledge_query = intent_v2.get("knowledge_query") or {}
        resolved_city = knowledge_query.get("resolved_city")
        if knowledge_query.get("type") == "geography" and resolved_city:
            quick_tags = [
                {
                    "label": f"车在{resolved_city}，继续估价",
                    "type": "vehicle_field_value",
                    "field": "city",
                    "value": resolved_city,
                    "target_module": "media_pricing",
                },
                {
                    "label": f"查看{resolved_city}行情",
                    "type": "market_city_query",
                    "value": resolved_city,
                    "target_module": "market_state",
                },
                {"label": "仅查询地理信息", "type": "dismiss_suggestion"},
            ]
        else:
            quick_tags = [
                {"label": "查看城市行情", "type": "module_switch", "target_module": "market_state"},
                {"label": "输入具体车辆估价", "type": "module_switch", "target_module": "media_pricing"},
                {"label": "查看行业日报", "type": "module_switch", "target_module": "daily_report"},
            ]
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": "GENERAL_AUTOMOTIVE_QA",
                "task": "NONE",
                "confidence": intent_v2.get("confidence", 0.7),
                "source": "global_intent_v2",
                "reason": intent_v2.get("reason") or "",
            },
            "intent_v2": intent_v2,
            "slots": {"city": resolved_city} if resolved_city else {},
            "vehicle_match": {},
            "missing_fields": [],
            "quick_tags": quick_tags,
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "general_automotive_qa",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            },
            "reply": reply,
            "active_task_type": "GENERAL_AUTOMOTIVE_QA",
            "vehicle_state": {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": module_context.get("module") or "media_pricing",
            "selected_city": module_context.get("selected_city"),
            "module_context": module_context,
            "last_daily_report_context": client_state.get("lastDailyReportContext") or {},
            "last_market_opportunity_context": client_state.get("lastMarketOpportunityContext") or {},
            "enterprise_tool_execution": self._tool_execution_summary(invocation),
            "warnings": [],
            "errors": [],
            "debug": {
                "enabled": bool(client_state.get("debug")),
                "intent_source": "global_intent_v2",
                "module": module_context.get("module"),
                "llm_answer": (reply.get("llm_answer") if isinstance(reply, dict) else {}),
            },
        }
        # Open automotive Q&A is a read-only conversational answer. Do not
        # attach task/tool execution cards, otherwise the UI looks like a
        # blocked valuation workflow and asks for pricing fields.
        response["task_card"] = {}
        response["agent_v21"] = {"task_plan": {}, "tool_results": [], "task_card": {}}
        existing = _SESSION_STATE.get(session_id) or {}
        existing.update(
            {
                "last_module": module_context.get("module") or "media_pricing",
                "current_pricing_result": current_price_result,
                "last_general_automotive_qa": {
                    "message": message,
                    "intent_v2": intent_v2,
                    "reply": reply,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _SESSION_STATE[session_id] = existing
        return _json_safe_snapshot(response)

    def _daily_report_reply(
        self,
        intent_v2: Dict[str, Any],
        daily_report_context: Dict[str, Any],
        message: str = "",
    ) -> Dict[str, Any]:
        internal_intent = intent_v2.get("internal_intent")
        if intent_v2.get("fallback_message"):
            text = intent_v2["fallback_message"]
        elif internal_intent == "DAILY_REPORT_READ":
            text = "正在读取最新上传行业日报，并在页面内生成结构化日报卡。"
        elif internal_intent == "DAILY_REPORT_HISTORY":
            text = "正在读取历史行业日报列表。"
        elif not daily_report_context:
            text = "请先查看今日行业日报；加载日报后我才能基于该日报回答板块、政策、降价和数据口径问题。"
        else:
            report_date = daily_report_context.get("report_date") or "当前日报"
            section = intent_v2.get("section")
            section_labels = {
                "ranking": "全国/城市/品牌/车系榜单",
                "policy": "政策速递",
                "discount": "新车降价",
                "new_car": "新车发布/行业动态",
                "industry_data": "行情数据",
                "suggestion": "经营建议",
            }
            section_text = f"的“{section_labels.get(section, section)}”板块" if section else ""
            evidence = DailyReportContentService().retrieve(str(report_date), message, section=section, limit=4)
            if evidence:
                evidence_text = "\n".join(
                    f"- 第{item['page']}页：{item['text']}" for item in evidence[:3]
                )
                text = (
                    f"已定位到 {report_date}{section_text}，以下结论直接来自该日报原文：\n"
                    f"{evidence_text}\n"
                    "以上是原文证据摘要；如需经营建议，我会基于这些证据单独给出，并明确区分事实与建议。"
                )
                return {
                    "text": text,
                    "style": "daily_report_evidence_answer",
                    "cards": [{"type": "daily_report_evidence", "report_date": report_date, "section": section, "evidence": evidence}],
                }
            text = (
                f"已定位到 {report_date}{section_text}，但当前未从原文中检索到足够直接的证据。"
                "我不会用通用模板补造内容；可以打开原文或换一个更具体的关键词继续查。"
            )
        return {"text": text, "style": "module_non_pricing", "cards": []}

    def _process_module_switch_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
    ) -> Dict[str, Any]:
        target = intent_v2.get("target_module") or "media_pricing"
        current_price_result = client_state.get("current_pricing_result") or {}
        labels = {"daily_report": "行业日报", "market_state": "行情状态机", "media_pricing": "媒体定价"}
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": "MODULE_SWITCH",
                "task": "NONE",
                "confidence": intent_v2.get("confidence", 0.99),
                "source": "global_intent_v2",
                "reason": intent_v2.get("reason") or "",
            },
            "intent_v2": intent_v2,
            "slots": {},
            "vehicle_match": {},
            "missing_fields": [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "module_switch",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
            },
            "reply": {
                "text": f"已切换到{labels.get(target, target)}模块。",
                "style": "module_switch_v2",
                "cards": [],
            },
            "active_task_type": "MODULE_SWITCH",
            "vehicle_state": {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": target,
            "selected_city": client_state.get("selectedCity") if target == "market_state" else None,
            "module_context": {
                "module": target,
                "selected_city": client_state.get("selectedCity") if target == "market_state" else None,
                "blocks_pricing": target in {"daily_report", "market_state"},
            },
            "last_daily_report_context": client_state.get("lastDailyReportContext") or {},
            "last_market_opportunity_context": client_state.get("lastMarketOpportunityContext") or {},
            "warnings": [],
            "errors": [],
            "debug": {"enabled": bool(client_state.get("debug")), "intent_source": "global_intent_v2"},
        }
        self._attach_agent_v21(
            response,
            daily_report_context=client_state.get("lastDailyReportContext") or {},
            market_agent_card=(client_state.get("lastMarketOpportunityContext") or {}),
        )
        return response

    def _process_hypothetical_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        client_state: Dict[str, Any],
        intent_v2: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_price_result = client_state.get("current_pricing_result") or {}
        ladder = current_price_result.get("price_ladder") or (
            (current_price_result.get("appraiser_decision_record") or {}).get(
                "final_price_ladder_yuan"
            )
        ) or {}
        current_c2b = ladder.get("expected_c2b_yuan")
        current_price_text = ""
        try:
            if current_c2b not in (None, ""):
                current_price_text = f"当前建议收车价约{float(current_c2b) / 10000:.2f}万。"
        except (TypeError, ValueError):
            current_price_text = ""
        proposed = intent_v2.get("slots") or {}
        proposed_parts = []
        for key, label, formatter in (
            ("mileage_wan_km", "里程", lambda value: f"{float(value):g}万公里"),
            ("city", "城市", str),
            ("color", "颜色", str),
            ("transfer_count", "过户", lambda value: f"{int(float(value))}次"),
        ):
            value = proposed.get(key)
            if isinstance(value, dict):
                value = value.get("value")
            if value in (None, ""):
                continue
            try:
                proposed_parts.append(f"{label}改为{formatter(value)}")
            except (TypeError, ValueError):
                continue
        proposed_text = "、".join(proposed_parts)
        if proposed_text:
            proposed_text = f"我已识别到你要比较“{proposed_text}”。"
        response = {
            "session_id": session_id,
            "turn_id": turn_id,
            "intent": {
                "type": VEHICLE_INFO_UPDATE,
                "task": "C2B",
                "confidence": intent_v2.get("confidence", 0.95),
                "source": "global_intent_v2",
                "reason": "hypothetical parameter update",
            },
            "intent_v2": intent_v2,
            "slots": client_state.get("current_slots") or {},
            "vehicle_match": client_state.get("current_vehicle_match") or {},
            "missing_fields": client_state.get("last_missing_fields") or [],
            "quick_tags": [],
            "pricing": {
                "should_call_price": False,
                "called_price": False,
                "price_request": {},
                "price_result": current_price_result,
                "price_state": "hypothetical_confirmation_required",
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
            },
            "reply": {
                "text": (
                    f"{proposed_text}{current_price_text}这是对比场景，不会覆盖当前车辆。"
                    "准确差额必须用其他信息完全不变的新场景重新计算；现有报价不能按固定比例硬推。"
                    "确认要算这个对比场景后，我会单独给新价格和差额。"
                ),
                "style": "hypothetical_confirmation",
                "cards": [],
            },
            "active_task_type": "VEHICLE_INFO_UPDATE",
            "vehicle_state": client_state.get("active_vehicle_state") or {},
            "vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
            "quote_lifecycle": {
                "quote_status": "COMPLETED" if current_price_result else "NONE",
                "stale_quote_reason": "",
                "active_vehicle_state_hash": client_state.get("active_vehicle_state_hash") or "",
                "default_reference": "latest_active_quote",
                "history_reference": {},
            },
            "module": "media_pricing",
            "selected_city": None,
            "module_context": {"module": "media_pricing", "selected_city": None, "blocks_pricing": False},
            "warnings": [],
            "errors": [],
            "debug": {"enabled": bool(client_state.get("debug")), "intent_source": "global_intent_v2"},
        }
        self._attach_agent_v21(response)
        return response

    def _attach_agent_v21(
        self,
        response: Dict[str, Any],
        *,
        daily_report_context: Dict[str, Any] | None = None,
        market_agent_card: Dict[str, Any] | None = None,
    ) -> None:
        """Attach enterprise Agent task plan/tool/card metadata to every turn.

        The existing response shape is preserved for backwards compatibility.
        Frontend and tests can consume the explicit V2.1 contract instead of
        inferring flow from free-form text.
        """
        try:
            intent_v2 = response.get("intent_v2") or {}
            intent = response.get("intent") or {}
            pricing = response.get("pricing") or {}
            slots = response.get("slots") or {}
            missing_fields = response.get("missing_fields") or []
            vehicle_match = response.get("vehicle_match") or {}
            module = response.get("module") or (response.get("module_context") or {}).get("module") or "media_pricing"
            plan = self.agent_planner_v21.build_plan(
                module=module,
                intent_v2=intent_v2,
                intent=intent,
                slots=slots,
                missing_fields=missing_fields,
                vehicle_match=vehicle_match,
                pricing=pricing,
                daily_report_context=daily_report_context or response.get("last_daily_report_context") or {},
                market_context=response.get("last_market_opportunity_context") or {},
            )
            tool_results = self.agent_planner_v21.build_tool_results(
                plan=plan,
                pricing=pricing,
                market_agent_card=market_agent_card or response.get("market_agent_card") or {},
                daily_report_context=daily_report_context or response.get("last_daily_report_context") or {},
            )
            workflow_tool_results = response.get("workflow_tool_results") or []
            if workflow_tool_results:
                tool_results = workflow_tool_results
            task_card = self.agent_planner_v21.build_task_card(
                plan=plan,
                tool_results=tool_results,
                pricing=pricing,
                reply=response.get("reply") or {},
            )
            response["task_plan"] = plan
            response["tool_results"] = tool_results
            response["task_card"] = task_card
            response["agent_v21"] = {
                "task_plan": plan,
                "tool_results": tool_results,
                "task_card": task_card,
            }
        except Exception as exc:
            response.setdefault("warnings", []).append(f"AGENT_V21_ATTACH_FAILED: {exc}")

    def _merge_v2_slots_into_extraction(
        self,
        extraction: Dict[str, Any],
        v2_slots: Dict[str, Any],
    ) -> None:
        slot_map = {
            "brand": "brand",
            "series": "series",
            "model_year": "model_year",
            "first_license_date": "first_license_date",
            "first_license_year": "first_license_year",
            "first_license_month": "first_license_month",
            "trim": "trim",
            "raw_vehicle_text": "raw_vehicle_text",
            "city": "city",
            "mileage_wan_km": "mileage_wan_km",
            "transfer_count": "transfer_count",
            "color": "color",
            "energy_type": "energy_type",
            "condition": "condition",
            "user_given_price_yuan": "user_given_price_yuan",
            "price_role": "price_role",
            "price_band": "price_band",
            "fuel_type": "fuel_type",
            "time_window": "time_window",
            "selection_target": "selection_target",
            "report_target": "report_target",
            "report_type": "report_type",
            "comparison_series": "comparison_series",
        }
        target = extraction.setdefault("slots", {})
        for source_key, target_key in slot_map.items():
            value = v2_slots.get(source_key)
            if value in (None, ""):
                continue
            current = target.get(target_key)
            current_value = current.get("value") if isinstance(current, dict) else current
            v2_authoritative_fields = {
                "brand",
                "series",
                "first_license_date",
                "first_license_year",
                "first_license_month",
                "mileage_wan_km",
                "transfer_count",
                "color",
            }
            current_identity = self._compact_identity(current_value)
            incoming_identity = self._compact_identity(value)
            more_specific_identity = bool(
                target_key in {"series", "raw_vehicle_text"}
                and current_identity
                and current_identity in incoming_identity
                and len(incoming_identity) > len(current_identity)
            )
            if (
                current_value in (None, "")
                or target_key == "trim"
                or target_key in v2_authoritative_fields
                or more_specific_identity
            ):
                target[target_key] = {
                    "value": value,
                    "confidence": 0.98,
                    "raw": value,
                    "source": "global_intent_v2_catalog",
                }
        if (
            v2_slots.get("brand")
            and v2_slots.get("series")
            and (v2_slots.get("trim") or v2_slots.get("model_year") or v2_slots.get("raw_vehicle_text"))
        ):
            current = target.get("raw_vehicle_text")
            current_value = current.get("value") if isinstance(current, dict) else current
            if current_value in (None, ""):
                value = " ".join(
                    str(item)
                    for item in (
                        v2_slots.get("model_year"),
                        v2_slots.get("brand"),
                        v2_slots.get("series"),
                        v2_slots.get("trim"),
                    )
                    if item not in (None, "")
                )
                if value:
                    target["raw_vehicle_text"] = {
                        "value": value,
                        "confidence": 0.9,
                        "raw": None,
                        "source": "global_intent_v2_catalog",
                    }

    def _legacy_intent_from_v2(self, intent_v2: Dict[str, Any]) -> Dict[str, Any]:
        internal = intent_v2.get("internal_intent")
        pricing_task = intent_v2.get("pricing_task")
        quote_legacy_type = (
            "SELL_CAR_PRICE"
            if pricing_task == "C2B"
            else "BUY_CAR_PRICE"
            if pricing_task == "B2C"
            else "BOTH_PRICE"
            if pricing_task == "BOTH"
            else SELL_CAR_VALUATION_INTENT
        )
        mapping = {
            "PRICE_QUOTE_REQUEST": quote_legacy_type,
            "PURCHASE_PRICE_JUDGEMENT": "SELL_CAR_PRICE",
            "SALE_PRICE_ADVICE": "BUY_CAR_PRICE",
            "BOTH_PRICE_ADVICE": "BOTH_PRICE",
            "COMPOUND_PRICING_MARKET_EXPLANATION": "SELL_CAR_PRICE",
            "VEHICLE_INFO_ADD": "VEHICLE_INFO_ADD",
            "VEHICLE_INFO_UPDATE": "VEHICLE_INFO_UPDATE",
            "VEHICLE_CONFIRM": "VEHICLE_CONFIRM",
            "PRICE_RECALCULATE": PRICE_QUOTE_REQUEST,
            "PRICE_EXPLANATION_REQUEST": PRICE_EXPLANATION_REQUEST,
            "PRICE_FEEDBACK_CLARIFICATION": "FEEDBACK_INACCURATE",
            "CANDIDATE_EVIDENCE_REQUEST": CANDIDATE_EVIDENCE_REQUEST,
            "WHY_LOW_CONFIDENCE": WHY_LOW_CONFIDENCE,
            "HISTORY_VEHICLE_REFERENCE": HISTORY_QUOTE_REFERENCE,
            "BUY_CAR_INTENT": BUY_CAR_INTENT,
            "BUSINESS_INTENT_CLARIFICATION": "BUSINESS_INTENT_CLARIFICATION",
            "RESET_VEHICLE": RESET_VEHICLE,
            "OUT_OF_SCOPE": "OUT_OF_SCOPE",
            "UNKNOWN_OR_INCOMPLETE": "UNKNOWN_OR_INCOMPLETE",
            "MULTI_VEHICLE_COMPARE": BUY_CAR_INTENT,
            "BATCH_PRICE_QUOTE": BUY_CAR_INTENT,
            "GENERAL_AUTOMOTIVE_QA": "GENERAL_AUTOMOTIVE_QA",
        }
        legacy_type = mapping.get(internal, "UNKNOWN_OR_INCOMPLETE")
        return {
            "type": legacy_type,
            "task": (
                pricing_task
                if pricing_task in {"C2B", "B2C", "BOTH"}
                else "C2B"
                if legacy_type not in {BUY_CAR_INTENT, "OUT_OF_SCOPE", "UNKNOWN_OR_INCOMPLETE"}
                else "UNKNOWN"
            ),
            "confidence": intent_v2.get("confidence", 0.5),
            "source": "global_intent_v2",
            "reason": intent_v2.get("reason") or "",
        }

    def _module_non_pricing_reply(
        self,
        module_context: Dict[str, Any],
        daily_report_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        module = module_context["module"]
        if module == "daily_report":
            context = daily_report_context or {}
            if context.get("report_id") or context.get("filename"):
                report_date = context.get("report_date") or "当前日报"
                text = (
                    f"当前正在围绕 {report_date} 的上传日报继续追问。"
                    "本阶段只基于该日报上下文组织回答，不会生成单车估价报告；完整事实请以日报原文为准。"
                )
            else:
                text = "请先查看今日行业日报；加载日报后，我会围绕当前日报上下文继续回答，不会生成单车估价报告。"
        else:
            city = module_context.get("selected_city") or "全国"
            text = f"已收到{city}的行情状态查询。当前会保留城市和问题，等待后续行情状态规则接入；不会生成单车估价报告。"
        return {"text": text, "style": "module_non_pricing", "cards": []}

    def _attach_quick_tag_context(
        self,
        quick_tags: list[Dict[str, Any]],
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
        missing_fields: list[str],
    ) -> None:
        if not quick_tags or not slots or not missing_fields:
            return
        context_slots = {k: v for k, v in slots.items() if v not in (None, "")}
        context_vehicle = vehicle_match or {}
        for tag in quick_tags:
            if tag.get("type") not in {"fill_field", "ask_field", "run_pricing"}:
                continue
            tag["context_slots"] = context_slots
            tag["context_vehicle_match"] = context_vehicle

    def _merge_session_state(self, session_id: str, client_state: Dict[str, Any]) -> Dict[str, Any]:
        client_state = self.enterprise_state_store.merge_client_state(session_id, client_state or {})
        memory = _SESSION_STATE.get(session_id) or {}
        if not memory:
            return dict(client_state or {})
        merged = dict(memory)
        merged.update(client_state or {})

        memory_slots = memory.get("current_slots") or {}
        incoming_slots = (client_state or {}).get("current_slots") or {}
        if memory_slots or incoming_slots:
            slot_merged = dict(memory_slots)
            slot_merged.update({k: v for k, v in incoming_slots.items() if v not in (None, "")})
            merged["current_slots"] = slot_merged

        for key in ("current_vehicle_match", "current_pricing_result"):
            if not (client_state or {}).get(key) and memory.get(key):
                merged[key] = memory[key]
        if not (client_state or {}).get("last_missing_fields") and memory.get("last_missing_fields"):
            merged["last_missing_fields"] = memory["last_missing_fields"]
        if not (client_state or {}).get("quote_history") and memory.get("quote_history"):
            merged["quote_history"] = memory["quote_history"]
        if not (client_state or {}).get("vehicle_history") and memory.get("vehicle_history"):
            merged["vehicle_history"] = memory["vehicle_history"]
        if not (client_state or {}).get("lastMarketOpportunityContext") and memory.get("lastMarketOpportunityContext"):
            merged["lastMarketOpportunityContext"] = memory["lastMarketOpportunityContext"]
        return merged

    def _remember_session_state(
        self,
        *,
        session_id: str,
        response: Dict[str, Any],
        client_state: Dict[str, Any],
        reset_for_new_vehicle: bool,
        identity_context_reset: bool = False,
    ) -> None:
        intent_type = (response.get("intent") or {}).get("type")
        if intent_type == RESET_VEHICLE:
            _SESSION_STATE.pop(session_id, None)
            self.enterprise_state_store.remember_response(
                session_id=session_id,
                response=response,
                client_state=client_state,
                reset_for_new_vehicle=True,
            )
            return
        if intent_type in {
            BUY_CAR_INTENT,
            PRICE_ADJUSTMENT_INTENT,
            DAILY_REPORT_READ_INTENT,
            REPORT_DETAIL_QUESTION,
            HISTORY_QUOTE_REFERENCE,
        }:
            existing = _SESSION_STATE.get(session_id) or {}
            existing["last_module"] = response.get("module") or "media_pricing"
            existing["last_selected_city"] = response.get("selected_city")
            if response.get("module") == "daily_report":
                existing["lastDailyReportContext"] = client_state.get("lastDailyReportContext") or {}
            if response.get("module") == "market_state":
                existing["lastMarketOpportunityContext"] = client_state.get("lastMarketOpportunityContext") or {}
            existing["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _SESSION_STATE[session_id] = existing
            self.enterprise_state_store.remember_response(
                session_id=session_id,
                response=response,
                client_state=client_state,
                reset_for_new_vehicle=reset_for_new_vehicle,
            )
            return

        slots = response.get("slots") or {}
        if not slots and not response.get("missing_fields"):
            return
        pricing = response.get("pricing") or {}
        price_result = pricing.get("price_result") or {}
        if not price_result and not reset_for_new_vehicle:
            price_result = client_state.get("current_pricing_result") or {}
        quote_history = list(client_state.get("quote_history") or [])
        vehicle_history = list(client_state.get("vehicle_history") or [])
        if (reset_for_new_vehicle or identity_context_reset) and client_state.get("current_slots"):
            previous_snapshot = {
                "slots": flatten_slots(client_state.get("current_slots") or {}),
                "vehicle_match": client_state.get("current_vehicle_match") or {},
                "pricing_result": client_state.get("current_pricing_result") or {},
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            previous_key = json.dumps(
                {
                    "slots": previous_snapshot["slots"],
                    "quote_id": (previous_snapshot["pricing_result"] or {}).get("quote_id"),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            last_key = ""
            if vehicle_history:
                last = vehicle_history[-1]
                last_key = json.dumps(
                    {
                        "slots": last.get("slots") or {},
                        "quote_id": (last.get("pricing_result") or {}).get("quote_id"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            if previous_key != last_key:
                vehicle_history.append(previous_snapshot)
                vehicle_history = vehicle_history[-20:]
        if pricing.get("called_price") and isinstance(price_result, dict) and price_result.get("success", True):
            quote_history.append({"pricing_result": price_result})
            quote_history = quote_history[-20:]

        _SESSION_STATE[session_id] = _json_safe_snapshot({
            "current_slots": slots,
            "current_vehicle_match": response.get("vehicle_match") or client_state.get("current_vehicle_match") or {},
            "current_pricing_result": (
                price_result
                if price_result
                else ({} if reset_for_new_vehicle else client_state.get("current_pricing_result") or {})
            ),
            "last_missing_fields": response.get("missing_fields") or [],
            "quote_history": quote_history,
            "vehicle_history": vehicle_history,
            "last_module": response.get("module") or "media_pricing",
            "last_selected_city": response.get("selected_city"),
            "lastDailyReportContext": client_state.get("lastDailyReportContext") or {},
            "lastMarketOpportunityContext": client_state.get("lastMarketOpportunityContext") or {},
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reset_for_new_vehicle": reset_for_new_vehicle,
            "identity_context_reset": identity_context_reset,
        })
        if len(_SESSION_STATE) > _SESSION_STATE_MAX:
            oldest = next(iter(_SESSION_STATE))
            _SESSION_STATE.pop(oldest, None)
        self.enterprise_state_store.remember_response(
            session_id=session_id,
            response=response,
            client_state=client_state,
            reset_for_new_vehicle=reset_for_new_vehicle,
        )

    def _is_explicit_new_vehicle_message(
        self,
        *,
        message: str,
        extraction: Dict[str, Any],
        event_type: str,
        client_state: Dict[str, Any],
    ) -> bool:
        if event_type in {"quick_tag_click", "field_update"}:
            return False
        text = str(message or "")
        if not text:
            return False
        update_or_reference = (
            r"不是|改成|修改|更正|纠正|应该是|换成|补充|重新估价|重新报价|"
            r"上一辆|上一个|前一辆|第一辆|第二辆|第三辆|刚才那辆|之前那辆|"
            r"价格怎么|怎么来的|为什么|为啥|候选|证据|解释|依据|低置信|调价|工单|日报"
        )
        if re.search(update_or_reference, text):
            return False
        slots = extraction.get("slots") or {}

        def value(key: str) -> Any:
            slot = slots.get(key)
            return slot.get("value") if isinstance(slot, dict) else slot

        has_new_vehicle_identity = bool(
            value("brand")
            and value("series")
            and (value("trim") or value("raw_vehicle_text") or value("model_year"))
        )
        has_vehicle_measure = bool(value("mileage_wan_km") or value("city") or value("transfer_count") is not None or value("color"))
        has_existing_quote = bool(client_state.get("current_pricing_result") or client_state.get("current_slots"))
        current_brand = flatten_slots(client_state.get("current_slots") or {}).get("brand")
        incoming_brand = value("brand")
        explicit_new_brand_request = bool(
            incoming_brand
            and current_brand
            and str(incoming_brand) != str(current_brand)
        )
        return bool(
            has_existing_quote
            and (
                (has_new_vehicle_identity and has_vehicle_measure)
                or explicit_new_brand_request
            )
        )

    @staticmethod
    def _slot_value_from_extraction(extraction: Dict[str, Any], key: str) -> Any:
        slot = (extraction.get("slots") or {}).get(key)
        if isinstance(slot, dict):
            confidence = float(slot.get("confidence") or 0)
            value = slot.get("value")
            return value if confidence >= 0.4 else None
        return slot

    @staticmethod
    def _compact_identity(value: Any) -> str:
        text = str(value or "").lower()
        text = re.sub(r"[\s\u3000·,，、_-]+", "", text)
        text = text.replace("宝马", "").replace("奔驰", "").replace("奥迪", "").replace("比亚迪", "")
        return text

    def _is_vehicle_identity_update(
        self,
        *,
        message: str,
        extraction: Dict[str, Any],
        event_type: str,
        current_flat: Dict[str, Any],
    ) -> bool:
        if event_type == "quick_tag_click":
            return False
        if not current_flat:
            return False
        text = str(message or "")
        update_word = bool(re.search(r"改成|换成|不是|修改|更正|纠正|应该是|车型改|车系改", text))
        if event_type == "field_update":
            update_word = True
        incoming_brand = self._slot_value_from_extraction(extraction, "brand")
        incoming_series = self._slot_value_from_extraction(extraction, "series")
        incoming_trim = self._slot_value_from_extraction(extraction, "trim")
        incoming_raw = self._slot_value_from_extraction(extraction, "raw_vehicle_text")
        incoming_model_year = self._slot_value_from_extraction(extraction, "model_year")
        has_identity_input = any(value not in (None, "") for value in (incoming_brand, incoming_series, incoming_trim, incoming_raw, incoming_model_year))
        if not has_identity_input:
            return False
        current_brand = current_flat.get("brand")
        current_series = current_flat.get("series")
        current_trim = current_flat.get("trim") or current_flat.get("raw_vehicle_text")
        if incoming_brand not in (None, "") and current_brand not in (None, "") and str(incoming_brand) != str(current_brand):
            return True
        if incoming_series not in (None, "") and current_series not in (None, ""):
            if self._compact_identity(incoming_series) != self._compact_identity(current_series):
                return True
        if update_word and incoming_trim not in (None, "") and current_trim not in (None, ""):
            if self._compact_identity(incoming_trim) != self._compact_identity(current_trim):
                return True
        if update_word and incoming_raw not in (None, "") and current_trim not in (None, ""):
            if self._compact_identity(incoming_raw) != self._compact_identity(current_trim):
                return True
        if update_word and incoming_model_year not in (None, "") and current_flat.get("model_year") not in (None, ""):
            if str(incoming_model_year) != str(current_flat.get("model_year")):
                return True
        return False

    @staticmethod
    def _preserve_pricing_conditions_for_identity_update(current_flat: Dict[str, Any]) -> Dict[str, Any]:
        preserved_keys = {
            "first_license_date",
            "first_license_year",
            "first_license_month",
            "reg_date",
            "mileage_wan_km",
            "city",
            "transfer_count",
            "color",
            "condition_group",
            "task",
        }
        return {key: value for key, value in (current_flat or {}).items() if key in preserved_keys and value not in (None, "")}

    def _message_from_event(self, event_type: str, message: str, payload: Dict[str, Any]) -> str:
        if event_type == "quick_tag_click":
            tag_type = payload.get("type")
            if tag_type == "fill_field":
                return str((payload.get("payload") or {}).get("value") or payload.get("label") or message)
            if tag_type == "select_model":
                data = payload.get("payload") or payload
                return str(data.get("label") or data.get("series") or data.get("model_name") or message)
            if tag_type == "run_pricing":
                return message or "立即估价"
            if tag_type in {"feedback", "feedback_evidence"}:
                data = payload.get("payload") or payload
                return str(data.get("message") or payload.get("label") or message)
        if event_type == "field_update":
            fields = payload.get("fields") or {}
            if isinstance(fields, dict) and fields:
                return message or "已更新车辆七要素并重新估价"
            field = payload.get("field")
            value = payload.get("value")
            return f"{field}改成{value}"
        return message

    def _apply_event_payload(self, extraction: Dict[str, Any], payload: Dict[str, Any]) -> None:
        tag_type = payload.get("type")
        data = payload.get("payload") or payload
        vehicle_match_payload = payload.get("vehicle_match") or data.get("vehicle_match")
        if isinstance(vehicle_match_payload, dict):
            extraction["vehicle_match_payload"] = vehicle_match_payload
        field = data.get("field")
        value = data.get("value")
        if tag_type == "fill_field" and field:
            # Let rule parser handle natural labels first, then force normalized raw state.
            if field == "mileage_wan_km":
                text = str(value).replace("万公里", "").replace("公里", "")
                try:
                    value = float(text) if float(text) < 1000 else float(text) / 10000
                except Exception:
                    pass
            if field == "transfer_count":
                try:
                    value = int(str(value).replace("次过户", "").replace("次", ""))
                except Exception:
                    pass
            extraction.setdefault("slots", {})[field] = {"value": value, "confidence": 1.0, "raw": data.get("value"), "source": "quick_tag"}
        if payload.get("field"):
            field = payload.get("field")
            extraction.setdefault("slots", {})[field] = {
                "value": payload.get("value"),
                "confidence": 1.0,
                "raw": payload.get("value"),
                "source": "field_update",
            }
        fields = payload.get("fields") or {}
        if isinstance(fields, dict):
            for field, value in fields.items():
                if value in (None, ""):
                    continue
                if field == "mileage_wan_km":
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        pass
                elif field == "transfer_count":
                    try:
                        value = int(float(value))
                    except (TypeError, ValueError):
                        pass
                elif field == "model_year":
                    try:
                        value = int(float(value))
                    except (TypeError, ValueError):
                        pass
                elif field == "first_license_date":
                    text = str(value).strip().replace("/", "-")
                    match = re.match(r"^((?:19|20)\d{2})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", text)
                    if match:
                        year = int(match.group(1))
                        month = int(match.group(2) or 1)
                        month = max(1, min(12, month))
                        day = int(match.group(3)) if match.group(3) else None
                        if day is not None:
                            day = max(1, min(31, day))
                        value = f"{year}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
                        slots = extraction.setdefault("slots", {})
                        slots["first_license_year"] = {
                            "value": year,
                            "confidence": 1.0,
                            "raw": value,
                            "source": "structured_field_update",
                        }
                        slots["first_license_month"] = {
                            "value": month,
                            "confidence": 1.0,
                            "raw": value,
                            "source": "structured_field_update",
                        }
                elif field in {"first_license_year", "first_license_month"}:
                    try:
                        value = int(float(value))
                    except (TypeError, ValueError):
                        pass
                extraction.setdefault("slots", {})[field] = {
                    "value": value,
                    "confidence": 1.0,
                    "raw": value,
                    "source": "structured_field_update",
                }

    @staticmethod
    def _apply_structured_vehicle_match_to_slots(slots: Dict[str, Any], vehicle_match: Dict[str, Any]) -> None:
        if not vehicle_match:
            return
        brand = vehicle_match.get("brand_name") or vehicle_match.get("brand")
        series = vehicle_match.get("series_name") or vehicle_match.get("series")
        model_year = vehicle_match.get("model_year")
        model_name = vehicle_match.get("model_name") or vehicle_match.get("model") or ""
        if brand:
            slots["brand"] = InteractionService._frontline_brand_name(brand)
        if series:
            slots["series"] = series
        if model_year not in (None, ""):
            try:
                slots["model_year"] = int(float(model_year))
            except (TypeError, ValueError):
                slots["model_year"] = model_year
        if model_name:
            clean_model = InteractionService._clean_vehicle_identity_text(str(model_name))
            slots["trim"] = clean_model
            slots["standard_vehicle"] = clean_model
            slots["raw_vehicle_text"] = clean_model
        slots["vehicle_confirmed"] = True

    @staticmethod
    def _frontline_brand_name(value: Any) -> str:
        brand = str(value or "").strip()
        return _FRONTLINE_BRAND_NAMES.get(brand, brand)

    @staticmethod
    def _sanitize_vehicle_parameter_slots(slots: Dict[str, Any]) -> None:
        for key in ("trim", "raw_vehicle_text", "standard_vehicle", "model", "model_name"):
            value = slots.get(key)
            if value in (None, ""):
                continue
            cleaned = InteractionService._clean_vehicle_identity_text(str(value))
            if cleaned:
                slots[key] = cleaned

    @staticmethod
    def _clean_vehicle_identity_text(value: str) -> str:
        original = str(value or "").strip()
        cleaned = original
        patterns = [
            r"[，,、]?\s*(?:19|20)\d{2}\s*[-/.]\s*\d{1,2}(?:\s*[-/.]\s*\d{1,2})?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*(?:日|号)?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*(?:19|20)\d{2}\s*年\s*(?:上牌|登记|落户)",
            r"[，,、]?\s*年\s*\d{1,2}\s*月?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*-?\s*(?:0?[1-9]|1[0-2])\s*月?\s*(?:上牌|登记|落户)",
            r"[，,、]?\s*\d+(?:\.\d+)?\s*万\s*公里",
            r"[，,、]?\s*\d+(?:\.\d+)?\s*公里",
            r"[，,、]?\s*\d+\s*次\s*过户",
            r"[，,、]?\s*(?:白色|黑色|灰色|银色|银灰色|红色|蓝色|绿色|黄色|棕色|金色|其他颜色|其它颜色|其他|其它)\s*$",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        cleaned = re.sub(
            r"^(?:改成|换成|改为|修改为|更正为|纠正为|车型改成|车系改成)\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,、;；")
        return cleaned or original

    @staticmethod
    def _normalize_first_license_slots(slots: Dict[str, Any]) -> None:
        raw_date = str(slots.get("first_license_date") or slots.get("reg_date") or "").strip()
        year = slots.get("first_license_year")
        month = slots.get("first_license_month")
        day = None
        if raw_date:
            match = re.match(r"^((?:19|20)\d{2})(?:[-/年](\d{1,2}))?(?:[-/月](\d{1,2}))?", raw_date)
            if match:
                year = year or int(match.group(1))
                month = month or int(match.group(2) or 1)
                if match.group(3):
                    day = max(1, min(31, int(match.group(3))))
        if year in (None, ""):
            return
        try:
            year_int = int(float(year))
            month_int = int(float(month or 1))
        except (TypeError, ValueError):
            return
        month_int = max(1, min(12, month_int))
        slots["first_license_year"] = year_int
        slots["first_license_month"] = month_int
        slots["first_license_date"] = f"{year_int}-{month_int:02d}" + (f"-{day:02d}" if day is not None else "")
        slots["reg_date"] = slots["first_license_date"]

    def _vehicle_match_from_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}
        model_id = data.get("model_id") or data.get("id") or data.get("standardModelId") or data.get("standard_model_id") or ""
        model_name = (
            data.get("model_name")
            or data.get("model")
            or data.get("title")
            or data.get("standard_vehicle")
            or data.get("raw_vehicle_text")
            or ""
        )
        model_name = self._clean_vehicle_identity_text(str(model_name))
        brand = data.get("brand") or data.get("brand_name") or ""
        series = data.get("series") or data.get("series_name") or ""
        matched = bool(model_id or model_name)
        return {
            "matched": matched,
            "need_manual_confirm": False if matched else True,
            "brand_name": brand,
            "series_name": series,
            "model_id": model_id,
            "series_id": data.get("series_id") or "",
            "model_name": model_name,
            "model_year": data.get("model_year"),
            "match_confidence": 0.98 if model_id else (0.82 if model_name else 0.4),
            "match_method": "structured_select_model",
            "match_reason": "用户点击或表单确认标准车型候选",
            "candidates": [data],
        }

    def _resolve_task(self, intent: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        task = intent.get("task") or "UNKNOWN"
        if task in {"C2B", "B2C", "BOTH"}:
            return task
        if intent.get("type") == BUY_CAR_INTENT:
            return "BUY"
        if intent.get("type") == PRICE_ADJUSTMENT_INTENT:
            return "ADJUSTMENT"
        if intent.get("type") in {DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION}:
            return "REPORT"
        last = (client_state.get("current_slots") or {}).get("task") or client_state.get("last_task")
        if isinstance(last, dict):
            last = last.get("value")
        if last in {"C2B", "B2C", "BOTH"}:
            return last
        if intent.get("type") in {SELL_CAR_VALUATION_INTENT, "SELL_CAR_PRICE"}:
            return "C2B"
        if intent.get("type") == "BUY_CAR_PRICE":
            return "B2C"
        if intent.get("type") == "BOTH_PRICE":
            return "BOTH"
        return "UNKNOWN"

    def _resolve_history_quote_reference(self, message: str, client_state: Dict[str, Any]) -> Dict[str, Any]:
        def hydrate_history_item(item: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
            payload = item.get("pricing_result") or item.get("price_result") or {}
            item_slots = dict(item.get("slots") or {})
            item_match = dict(item.get("vehicle_match") or {})
            standard = payload.get("standard_vehicle") if isinstance(payload, dict) else {}
            if not standard and isinstance(payload, dict):
                standard = (payload.get("evidence_card") or {}).get("standard_vehicle") or {}
            raw_text = (
                item_slots.get("raw_vehicle_text")
                or item_slots.get("trim")
                or (item.get("car_data") or {}).get("title")
                or (item.get("car") or {}).get("title")
                or ""
            )
            if raw_text:
                try:
                    parsed = flatten_slots(
                        (self.slot_extractor.extract(str(raw_text), {"current_slots": {}}) or {}).get("slots") or {}
                    )
                except Exception:
                    parsed = {}
                for field in ("brand", "series", "model_year", "trim", "raw_vehicle_text"):
                    if not item_slots.get(field) and parsed.get(field):
                        item_slots[field] = parsed[field]
            standard_to_slot = {
                "brand_name": "brand",
                "series_name": "series",
                "model_year": "model_year",
                "model_name": "trim",
            }
            for source_field, slot_field in standard_to_slot.items():
                if not item_slots.get(slot_field) and standard.get(source_field) not in (None, ""):
                    item_slots[slot_field] = standard[source_field]
            if not item_match and standard:
                item_match = dict(standard)
            return payload, item_slots, item_match

        saved_history = client_state.get("vehicle_history") or []
        if not isinstance(saved_history, list):
            saved_history = []
        history = list(saved_history)
        current_slots = flatten_slots(client_state.get("current_slots") or {})
        current_match = client_state.get("current_vehicle_match") or {}
        current_price = client_state.get("current_pricing_result") or {}
        if current_slots or current_match or current_price:
            current_snapshot = {
                "slots": current_slots,
                "vehicle_match": current_match,
                "pricing_result": current_price,
                "is_active_vehicle": True,
            }
            current_key = json.dumps(
                {
                    "slots": current_slots,
                    "quote_id": current_price.get("quote_id") if isinstance(current_price, dict) else None,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            last_key = ""
            if history:
                last = history[-1] or {}
                last_price = last.get("pricing_result") or last.get("price_result") or {}
                last_key = json.dumps(
                    {
                        "slots": last.get("slots") or {},
                        "quote_id": last_price.get("quote_id") if isinstance(last_price, dict) else None,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            if current_key != last_key:
                history.append(current_snapshot)
        if not history:
            quote_history = client_state.get("quote_history") or client_state.get("pricing_history") or []
            history = list(quote_history) if isinstance(quote_history, list) else []
        if not history:
            return {}
        text = str(message or "")
        requested_identity: Dict[str, Any] = {}
        try:
            requested_extraction = self.slot_extractor.extract(text, {"current_slots": {}})
            requested_identity = flatten_slots(requested_extraction.get("slots") or {})
        except Exception:
            requested_identity = {}
        if "第一" in text or "第1" in text:
            idx = 0
        elif "第二" in text or "第2" in text:
            idx = 1
        elif "第三" in text or "第3" in text:
            idx = 2
        elif "上一" in text or "上一个" in text or "前一" in text:
            idx = max(len(history) - 2, 0)
        else:
            for item in reversed(history):
                payload, item_slots, item_match = hydrate_history_item(item)
                hay = json.dumps(item, ensure_ascii=False, default=str)
                compact_text = re.sub(r"\s+", "", text).lower()
                identity_tokens = []
                for value in (
                    item_slots.get("brand"),
                    item_slots.get("series"),
                    item_slots.get("trim"),
                    item_match.get("brand_name"),
                    item_match.get("series_name"),
                    item_match.get("model_name"),
                ):
                    value = str(value or "").strip()
                    if len(value) >= 2:
                        identity_tokens.append(value)
                requested_tokens = [
                    str(requested_identity.get(field) or "").strip()
                    for field in ("brand", "series", "trim", "raw_vehicle_text")
                    if str(requested_identity.get(field) or "").strip()
                ]
                direct_identity_match = any(token.lower() in compact_text and token in hay for token in identity_tokens)
                extracted_identity_match = any(
                    len(token) >= 2 and token.lower() in hay.lower()
                    for token in requested_tokens
                )
                if direct_identity_match or extracted_identity_match:
                    return {
                        "matched": True,
                        "match_method": "history_vehicle_text_match",
                        "history_index": history.index(item),
                        "pricing_result": payload,
                        "slots": item_slots,
                        "vehicle_match": item_match,
                        "is_active_vehicle": bool(item.get("is_active_vehicle")),
                    }
            idx = len(history) - 1
        if idx < 0 or idx >= len(history):
            return {}
        item = history[idx] or {}
        payload, item_slots, item_match = hydrate_history_item(item)
        return {
            "matched": True,
            "match_method": "history_vehicle_index",
            "history_index": idx,
            "pricing_result": payload,
            "slots": item_slots,
            "vehicle_match": item_match,
            "is_active_vehicle": bool(item.get("is_active_vehicle")),
        }

    def _record_feedback(self, session_id: str, message: str, intent: Dict[str, Any], slots: Dict[str, Any], pricing_result: Dict[str, Any]) -> None:
        _append_jsonl(
            FEEDBACK_LOG,
            {
                "request_id": pricing_result.get("request_id") or pricing_result.get("traceId") or "",
                "session_id": session_id,
                "user_message": message,
                "feedback_type": intent.get("type"),
                "current_price": (pricing_result.get("price") or {}).get("point"),
                "vehicle_slots": slots,
                "pricing_result": pricing_result,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
