from __future__ import annotations

import os
import copy
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict

from .intent_schema_v2 import BUSINESS_CATEGORIES, INTERNAL_INTENTS, SLOT_KEYS, SUPPORTED_MODULES
from .llm_client import Qwen3LocalClient, extract_json_object


SYSTEM_PROMPT = """
你是二手车企业内部任务型 Agent 的 NLU 解析器，只能输出 JSON。

你不能估价，不能生成价格，不能调用业务工具，不能编造证据。
你的唯一任务是把用户自然语言解析成：
1. 业务模块 module: daily_report / market_state / media_pricing / unknown
2. 内部意图 internal_intent
3. 业务分类 business_category
4. 结构化槽位 slots
5. 上下文引用 context_reference
6. 是否需要追问 needs_clarification
7. 选品细分意图 selection_detail_intent 与回答形态 answer_mode

可用模块：
- daily_report: 行业日报、政策、降价、新车、行情日报追问
- market_state: 城市行情、选品、库存、周转、机会车系、风险车系
- media_pricing: 单车收车价/售车价/卖多少钱/候选证据/价格解释/修改车辆六要素

注意：GENERAL_AUTOMOTIVE_QA 不是 module。汽车品牌、车型常识、国家派系、行业概念等开放问答应输出：
- module = media_pricing
- business_category = GENERAL_AUTOMOTIVE_QA
- internal_intent = GENERAL_AUTOMOTIVE_QA

必须严格输出 JSON object，字段如下：
{
  "module": "daily_report|market_state|media_pricing|unknown",
  "business_category": "...",
  "internal_intent": "...",
  "confidence": 0.0,
  "slots": {
    "brand": null,
    "series": null,
    "city": null,
    "price_bucket": null,
    "model_year": null,
    "trim": null,
    "mileage_km": null,
    "mileage_wan_km": null,
    "transfer_count": null,
    "color": null,
    "energy_type": null
  },
  "context_reference": {"type": null, "id": null, "ordinal": null},
  "semantic_entities": {
    "referenced_entity": null,
    "implied_brand": null,
    "implied_series": null,
    "brand_origin_country": null,
    "query_focus": null,
    "open_world_terms": []
  },
  "selection_detail_intent": null,
  "answer_mode": "task_card|rank_answer|exclusion_answer|series_judgement|score_explanation|method_explanation|evidence_answer|backtest_answer|pricing_explanation|clarification",
  "needs_clarification": false,
  "clarification_question": "",
  "reason": ""
}

约束：
- 用户只说“我要买/我想要一辆”通常是买车咨询，不要生成收车估价。
- 用户只说品牌/车系但缺少六要素时，归 media_pricing + VEHICLE_INFO_ADD，不要调用估价。
- 用户问“价格怎么来的/候选证据/为什么低信任”，如果上下文有报价，归 PRICING_QA。
- 用户问“今天日报/降价最多/政策影响”，归 daily_report。
- 用户问“长春行情/哪些车值得收/库存风险”，归 market_state。
- 用户问“为什么某车不在选品推荐里/为什么推荐/为什么不建议/机会分为什么低”，归 market_state + MARKET_REASON_QUERY，不要归 daily_report。
- 用户问某车“第几名/排哪/在榜单什么位置”，归 market_state + MARKET_REASON_QUERY，selection_detail_intent=selection.rank_lookup，answer_mode=rank_answer。
- 用户问某车“为什么没上榜/为什么不在推荐里”，归 market_state + MARKET_REASON_QUERY，selection_detail_intent=selection.explain_exclusion，answer_mode=exclusion_answer。
- 用户问某车“建议收吗/能不能做/值不值得收”，归 market_state + MARKET_STATE_QUERY，selection_detail_intent=selection.series_judgement，answer_mode=series_judgement。
- 用户问“机会分/综合分怎么来的/为什么排这么高”，归 market_state + MARKET_REASON_QUERY，selection_detail_intent=selection.explain_rank_score，answer_mode=score_explanation。
- 用户问“选品逻辑/计算公式/怎么排序/用了哪些数据”，归 market_state + MARKET_DATA_SCOPE_QUERY，selection_detail_intent=selection.signal_rule_explain，answer_mode=method_explanation。
- 用户问“证据/数据来源/DSI或排行榜是否参与”，归 market_state + MARKET_DATA_SCOPE_QUERY，selection_detail_intent=selection.evidence_request，answer_mode=evidence_answer。
- 用户问“回测/指标是否达标/baseline”，归 market_state，分别使用 selection.backtest_metric / selection.baseline_question。
- 选品比较使用 selection.compare；风险清单使用 selection.risk_scope；普通推荐使用 selection.recommend_scope。
- “特斯拉行情怎么样”这类车系行情查询归 market_state，不要归 daily_report；只有明确“日报/今日报告/政策/新车/降价榜”才归 daily_report。
- “选品推荐/值得收/风险车系/机会车系/价格带机会”均归 market_state 的选品任务。
- 城市可来自隐含表达，例如“山东省会”应解析为济南。
- “品牌是美国总统座驾”这类开放表达，应解析 referenced_entity，并尽量给出 implied_brand=凯迪拉克；若无法确定则 needs_clarification=true。
- “推荐德国品牌/德系车/日系车”这类按国家或派系筛选，归 market_state，并在 semantic_entities.brand_origin_country 写入国家。
- 如果问题是汽车/二手车/品牌/车型/行业相关常识，但不属于日报、行情状态、估价、调价或证据解释，归 GENERAL_AUTOMOTIVE_QA + GENERAL_AUTOMOTIVE_QA。
- 如果用户要求推荐品牌、派系、车型方向但没有城市/预算/业务动作，优先 GENERAL_AUTOMOTIVE_QA，并追问用途/预算/城市；不要直接估价。
- 不确定时 needs_clarification=true。
- deterministic_result 只是参考，不是答案；如果 deterministic_result 是 UNKNOWN_OR_INCOMPLETE，你必须根据用户原话重新判断，不要照抄 UNKNOWN。
""".strip()


@dataclass
class LLMIntentDecision:
    ok: bool
    result: Dict[str, Any] | None = None
    reason: str = ""
    raw: Dict[str, Any] | None = None


class EnterpriseLLMIntentFallback:
    _CACHE_LOCK = threading.Lock()
    _CACHE: "OrderedDict[str, tuple[float, LLMIntentDecision]]" = OrderedDict()
    _CACHE_TTL_SECONDS = 10 * 60
    _CACHE_MAX_ITEMS = 512

    def __init__(self, llm_client: Qwen3LocalClient | None = None) -> None:
        self.llm_client = llm_client or Qwen3LocalClient()
        flag = os.environ.get("INTENT_V2_ENABLE_LLM_FALLBACK", "auto").lower()
        has_remote_or_local_llm = bool(
            os.environ.get("LLM_BASE_URL")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("QWEN_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
        )
        self.enabled = flag in {"1", "true", "yes", "on"} or (
            flag == "auto"
            and has_remote_or_local_llm
        )

    def parse(
        self,
        *,
        message: str,
        selected_module: str,
        deterministic_result: Dict[str, Any],
        client_state: Dict[str, Any],
        candidate_hints: Dict[str, Any] | None = None,
    ) -> LLMIntentDecision:
        if not self.enabled:
            return LLMIntentDecision(ok=False, reason="INTENT_V2_ENABLE_LLM_FALLBACK=false")

        payload = {
            "task_type": "intent_routing",
            "purpose": "enterprise_agent_front_door_intent_routing",
            "message": str(message or ""),
            "selected_module": selected_module,
            "deterministic_result": {
                "module": deterministic_result.get("selected_module"),
                "business_category": deterministic_result.get("business_category"),
                "internal_intent": deterministic_result.get("internal_intent"),
                "confidence": deterministic_result.get("confidence"),
                "slots": deterministic_result.get("slots"),
                "reason": deterministic_result.get("reason"),
            },
            "client_state_summary": self._summarize_state(client_state),
            "candidate_hints": candidate_hints or {},
        }
        cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        llm_result = self.llm_client.structured_extract_until(SYSTEM_PROMPT, payload, self._accept_raw_route)
        if not llm_result.ok:
            return LLMIntentDecision(ok=False, reason=llm_result.fallback_reason)
        parsed = extract_json_object(llm_result.content)
        if not parsed:
            return LLMIntentDecision(ok=False, reason="LLM_NON_JSON", raw={"content": llm_result.content})
        sanitized = self._sanitize(parsed)
        if not sanitized:
            return LLMIntentDecision(
                ok=False,
                reason=(
                    "LLM_SCHEMA_REJECT:"
                    f"module={parsed.get('module') or parsed.get('selected_module')};"
                    f"category={parsed.get('business_category')};"
                    f"intent={parsed.get('internal_intent')}"
                ),
                raw=parsed,
            )
        sanitized["llm_model"] = llm_result.model
        sanitized["llm_latency_ms"] = llm_result.latency_ms
        decision = LLMIntentDecision(ok=True, result=sanitized, raw=parsed)
        self._put_cached(cache_key, decision)
        return decision

    @classmethod
    def _get_cached(cls, key: str) -> LLMIntentDecision | None:
        now = time.time()
        with cls._CACHE_LOCK:
            item = cls._CACHE.get(key)
            if not item:
                return None
            created_at, decision = item
            if now - created_at > cls._CACHE_TTL_SECONDS:
                cls._CACHE.pop(key, None)
                return None
            cls._CACHE.move_to_end(key)
            cached = copy.deepcopy(decision)
            if cached.result is not None:
                cached.result["llm_cache_hit"] = True
                cached.result["llm_latency_ms"] = 0
            return cached

    @classmethod
    def _put_cached(cls, key: str, decision: LLMIntentDecision) -> None:
        with cls._CACHE_LOCK:
            cls._CACHE[key] = (time.time(), copy.deepcopy(decision))
            cls._CACHE.move_to_end(key)
            while len(cls._CACHE) > cls._CACHE_MAX_ITEMS:
                cls._CACHE.popitem(last=False)

    @staticmethod
    def _accept_raw_route(parsed: Dict[str, Any]) -> bool:
        category = str(parsed.get("business_category") or "").strip()
        intent = str(parsed.get("internal_intent") or "").strip()
        try:
            confidence = float(parsed.get("confidence") or 0)
        except Exception:
            confidence = 0.0
        if category == "UNKNOWN_OR_INCOMPLETE" and intent == "UNKNOWN_OR_INCOMPLETE" and confidence < 0.5:
            return False
        if parsed.get("needs_clarification"):
            return True
        if not parsed.get("module") and not parsed.get("selected_module"):
            return False
        return True

    def _sanitize(self, parsed: Dict[str, Any]) -> Dict[str, Any] | None:
        module = str(parsed.get("module") or parsed.get("selected_module") or "unknown").strip()
        module_aliases = {
            "GENERAL_AUTOMOTIVE_QA": "media_pricing",
            "general_automotive_qa": "media_pricing",
            "automotive_qa": "media_pricing",
            "pricing": "media_pricing",
            "valuation": "media_pricing",
            "report": "daily_report",
            "market": "market_state",
        }
        module = module_aliases.get(module, module)
        if module == "unknown":
            module = "media_pricing"
        if module not in SUPPORTED_MODULES:
            return None
        category = str(parsed.get("business_category") or "UNKNOWN_OR_INCOMPLETE").strip()
        intent = str(parsed.get("internal_intent") or "UNKNOWN_OR_INCOMPLETE").strip()
        category_aliases = {
            "AUTOMOTIVE_QA": "GENERAL_AUTOMOTIVE_QA",
            "GENERAL_QA": "GENERAL_AUTOMOTIVE_QA",
            "VEHICLE_KNOWLEDGE": "GENERAL_AUTOMOTIVE_QA",
            "MARKET_REASON_QUERY": "MARKET_STATE",
            "MARKET_OPPORTUNITY_RECOMMEND": "MARKET_STATE",
            "MARKET_RISK_QUERY": "MARKET_STATE",
            "MARKET_STATE_QUERY": "MARKET_STATE",
            "MARKET_REPORT_QUERY": "MARKET_STATE",
            "MARKET_RANKING_QUERY": "MARKET_STATE",
            "SELECTION_RANK_QUERY": "MARKET_STATE",
            "SELECTION_EXCLUSION_QUERY": "MARKET_STATE",
            "SERIES_ACQUISITION_JUDGEMENT": "MARKET_STATE",
            "PRICE_QUOTE_REQUEST": "MEDIA_VALUATION",
            "VEHICLE_INFO_ADD": "MEDIA_VALUATION",
            "DAILY_REPORT_READ": "DAILY_REPORT",
            "DAILY_REPORT_SECTION_QUERY": "DAILY_REPORT",
        }
        intent_aliases = {
            "AUTOMOTIVE_QA": "GENERAL_AUTOMOTIVE_QA",
            "GENERAL_QA": "GENERAL_AUTOMOTIVE_QA",
            "VEHICLE_KNOWLEDGE": "GENERAL_AUTOMOTIVE_QA",
            "MARKET_RANKING_QUERY": "MARKET_REASON_QUERY",
            "SELECTION_RANK_QUERY": "MARKET_REASON_QUERY",
            "SELECTION_EXCLUSION_QUERY": "MARKET_REASON_QUERY",
            "SERIES_ACQUISITION_JUDGEMENT": "MARKET_STATE_QUERY",
        }
        category = category_aliases.get(category, category)
        intent = intent_aliases.get(intent, intent)
        if category not in BUSINESS_CATEGORIES or intent not in INTERNAL_INTENTS:
            repaired = self._repair_open_qa_enums(
                module=module,
                category=category,
                intent=intent,
                parsed=parsed,
            )
            if repaired:
                category, intent = repaired
        if category not in BUSINESS_CATEGORIES or intent not in INTERNAL_INTENTS:
            return None
        try:
            confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0)))
        except Exception:
            confidence = 0.0
        raw_slots = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else {}
        slots = {key: None for key in SLOT_KEYS}
        for key in SLOT_KEYS:
            value = raw_slots.get(key)
            if value not in ("", "null", "None", "未知"):
                slots[key] = value
        context = parsed.get("context_reference") if isinstance(parsed.get("context_reference"), dict) else {}
        semantic = parsed.get("semantic_entities") if isinstance(parsed.get("semantic_entities"), dict) else {}
        safe_semantic = {
            "referenced_entity": semantic.get("referenced_entity"),
            "implied_brand": semantic.get("implied_brand"),
            "implied_series": semantic.get("implied_series"),
            "brand_origin_country": semantic.get("brand_origin_country"),
            "query_focus": semantic.get("query_focus"),
            "open_world_terms": semantic.get("open_world_terms") if isinstance(semantic.get("open_world_terms"), list) else [],
        }
        detail_aliases = {
            "rank_lookup": "selection.rank_lookup",
            "selection_rank_lookup": "selection.rank_lookup",
            "explain_exclusion": "selection.explain_exclusion",
            "series_judgement": "selection.series_judgement",
            "explain_rank_score": "selection.explain_rank_score",
            "method_explanation": "selection.signal_rule_explain",
            "evidence_request": "selection.evidence_request",
            "backtest_metric": "selection.backtest_metric",
            "baseline_question": "selection.baseline_question",
        }
        detail = str(parsed.get("selection_detail_intent") or "").strip()
        detail = detail_aliases.get(detail, detail)
        if detail and not (detail.startswith("selection.") or detail == "clarify.missing_scope"):
            detail = ""
        answer_mode = str(parsed.get("answer_mode") or "").strip()
        return {
            "selected_module": module,
            "business_category": category,
            "internal_intent": intent,
            "confidence": round(confidence, 4),
            "slots": slots,
            "context_reference": {
                "type": context.get("type"),
                "id": context.get("id"),
                "ordinal": context.get("ordinal"),
            },
            "semantic_entities": safe_semantic,
            "selection_detail_intent": detail or None,
            "answer_mode": answer_mode or None,
            "needs_clarification": bool(parsed.get("needs_clarification")),
            "clarification_question": str(parsed.get("clarification_question") or ""),
            "reason": str(parsed.get("reason") or "llm_structured_fallback"),
        }

    @staticmethod
    def _repair_open_qa_enums(
        *,
        module: str,
        category: str,
        intent: str,
        parsed: Dict[str, Any],
    ) -> tuple[str, str] | None:
        """Repair descriptive LLM enum variants without accepting tool actions.

        Hosted models sometimes return a semantically useful subtype such as
        ``VEHICLE_TECH_EXPLANATION`` even though the public contract exposes
        only ``GENERAL_AUTOMOTIVE_QA``. This adapter collapses descriptive,
        read-only intents while continuing to reject unknown pricing, mutation,
        report, and market tool actions.
        """
        if module != "media_pricing":
            return None
        combined = " ".join(
            str(value or "").upper()
            for value in (
                category,
                intent,
                parsed.get("reason"),
                (parsed.get("semantic_entities") or {}).get("query_focus")
                if isinstance(parsed.get("semantic_entities"), dict)
                else "",
            )
        )
        tool_action_markers = (
            "QUOTE_REQUEST",
            "VALUATION_REQUEST",
            "REPRICE",
            "PRICE_ADJUST",
            "INVENTORY_ADJUST",
            "REPORT_READ",
            "REPORT_GENERATE",
            "MARKET_QUERY",
            "TOOL_CALL",
            "MUTATION",
        )
        if any(marker in combined for marker in tool_action_markers):
            return None
        read_only_markers = (
            "QA",
            "KNOWLEDGE",
            "EXPLAIN",
            "EXPLANATION",
            "WHY",
            "CONCEPT",
            "COMPARE",
            "COMPARISON",
            "RECOMMEND",
            "ADVICE",
            "TECH",
            "PRINCIPLE",
            "DIFFERENCE",
            "VARIANCE",
        )
        if any(marker in combined for marker in read_only_markers):
            return "GENERAL_AUTOMOTIVE_QA", "GENERAL_AUTOMOTIVE_QA"
        return None

    @staticmethod
    def _summarize_state(client_state: Dict[str, Any]) -> Dict[str, Any]:
        current_quote = client_state.get("current_pricing_result") or client_state.get("last_price_result") or {}
        current_slots = client_state.get("current_slots") or {}
        vehicle_history = client_state.get("vehicle_history") or []
        quote_history = client_state.get("quote_history") or []
        return {
            "module": client_state.get("module") or client_state.get("selectedBusinessModule"),
            "has_current_quote": bool(current_quote),
            "current_quote_id": current_quote.get("quote_id") if isinstance(current_quote, dict) else None,
            "current_slots": current_slots,
            "vehicle_history_count": len(vehicle_history) if isinstance(vehicle_history, list) else 0,
            "quote_history_count": len(quote_history) if isinstance(quote_history, list) else 0,
            "has_daily_report_context": bool(client_state.get("lastDailyReportContext")),
            "has_market_context": bool(client_state.get("lastMarketOpportunityContext")),
        }
