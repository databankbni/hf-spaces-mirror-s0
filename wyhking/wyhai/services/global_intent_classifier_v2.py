from __future__ import annotations

import os
import re
from typing import Any, Dict

from .brand_tier import extract_brand_tier_from_text, normalize_brand_tier
from .enterprise_llm_intent_fallback import EnterpriseLLMIntentFallback
from .daily_report_date_resolver import resolve_daily_report_date
from .intent_example_matcher_v2 import IntentExampleMatcherV2
from .intent_schema_v2 import build_intent_result
from .open_semantic_resolver import resolve_open_semantic
from .selection_intent_detail_router import build_selection_detail_contract, classify_selection_detail_intent
from .selection_query_semantics import classify_selection_query_family, is_explicit_pricing_query
from .selection_category_ontology import extract_selection_category_constraints
from .vehicle_slot_extractor_v2 import VehicleSlotExtractorV2


MODULE_ALIASES = {
    "daily_report": "daily_report",
    "行业日报": "daily_report",
    "日报": "daily_report",
    "market_state": "market_state",
    "行情状态机": "market_state",
    "行情选品": "market_state",
    "行情": "market_state",
    "media_pricing": "media_pricing",
    "媒体定价": "media_pricing",
    "车辆估价": "media_pricing",
    "估价": "media_pricing",
}

LLM_REFINABLE_SELECTION_DETAILS = {
    "",
    "clarify.missing_scope",
    "selection.recommend_scope",
    "selection.entity_resolution",
    "selection.robust_nlu",
}


class GlobalIntentClassifierV2:
    def __init__(
        self,
        slot_extractor: VehicleSlotExtractorV2 | None = None,
        example_matcher: IntentExampleMatcherV2 | None = None,
        llm_fallback: EnterpriseLLMIntentFallback | None = None,
    ) -> None:
        self.slot_extractor = slot_extractor or VehicleSlotExtractorV2()
        self.example_matcher = example_matcher or IntentExampleMatcherV2()
        self._llm_fallback_injected = llm_fallback is not None
        self.llm_fallback = llm_fallback or EnterpriseLLMIntentFallback()

    def classify(
        self,
        message: str,
        selected_module: str,
        client_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        text = str(message or "").strip()
        client_state = client_state or {}
        slots_result = self.slot_extractor.extract(text, client_state)
        slots = slots_result["slots"]
        if re.search(r"这(?:辆|台)车|该车|它(?:的|在|值|能|可|该)", text):
            current_vehicle = client_state.get("current_slots") or {}
            for key in ("brand", "series", "trim", "model_year"):
                if slots.get(key) in (None, "") and current_vehicle.get(key) not in (None, ""):
                    slots[key] = current_vehicle.get(key)
        slots.update(self._extract_enterprise_task_slots(text, slots))
        self._clean_enterprise_scope_slots(text, slots)
        semantic_resolution = resolve_open_semantic(text)
        semantic_constraints: Dict[str, Any] = {}
        if semantic_resolution:
            semantic_constraints = dict(semantic_resolution.constraints)
            for key, value in semantic_resolution.slots.items():
                if key in slots and slots.get(key) in (None, "") and value not in (None, ""):
                    slots[key] = value
            self._clean_enterprise_scope_slots(text, slots)
        selected_module = selected_module if selected_module in {
            "daily_report",
            "market_state",
            "media_pricing",
        } else "media_pricing"
        if selected_module == "market_state":
            self._canonicalize_selection_entity_slots(slots)

        geo_knowledge = self._pure_geography_knowledge_route(text, selected_module, slots, semantic_resolution)
        if geo_knowledge:
            return self._attach_semantic(geo_knowledge, semantic_constraints, semantic_resolution)

        direct_daily_request = bool(
            re.search(
                r"^(?:给我|看(?:一下)?|读(?:一下)?|打开|查看|来一份|我要看)?"
                r"(?:今天|今日|最新)?(?:的)?(?:汽车|行业|行情)?日报$",
                text,
            )
        ) and not bool(re.search(r"写日报|生成日报|制作日报", text))
        if direct_daily_request:
            result = self._result(
                "daily_report",
                "DAILY_REPORT",
                "DAILY_REPORT_READ",
                slots,
                0.99,
                {"type": None, "id": None},
                render_daily=True,
                reason="用户明确请求读取现有行业日报",
            )
            result["explicit_cross_module_intent"] = True
            return self._attach_semantic(result, semantic_constraints, semantic_resolution)

        target_module = self._explicit_module_switch(text, selected_module)
        if target_module:
            return self._attach_semantic(build_intent_result(
                selected_module=selected_module,
                business_category="CROSS_MODULE_SWITCH",
                internal_intent="MODULE_SWITCH",
                confidence=0.99,
                slots=slots,
                target_module=target_module,
                reason=f"用户明确要求切换到{target_module}",
            ), semantic_constraints, semantic_resolution)
        if selected_module == "market_state":
            detail_probe = classify_selection_detail_intent(
                text,
                slots=slots,
                internal_intent="MARKET_STATE_QUERY",
                has_context=bool(
                    client_state.get("lastMarketOpportunityContext")
                    or client_state.get("last_market_opportunity_context")
                ),
            )
            pricing_payload_fields = sum(
                slots.get(key) not in (None, "")
                for key in ("series", "city", "mileage_wan_km", "transfer_count", "color")
            )
            has_license_time = any(
                slots.get(key) not in (None, "")
                for key in ("first_license_date", "first_license_year", "reg_date")
            )
            has_actionable_pricing_payload = has_license_time and pricing_payload_fields >= 5
            if (
                detail_probe.get("selection_detail_intent") == "selection.handoff_pricing"
                and not has_actionable_pricing_payload
                and not self._should_route_to_media_pricing(text, slots)
            ):
                result = self._result(
                    "market_state",
                    "MARKET_STATE",
                    "COMPOUND_SELECTION_PRICING",
                    slots,
                    0.96,
                    {"type": None, "id": None},
                    render_market=True,
                    reason="选品模块内识别为单车定价承接，先生成定价交接动作",
                )
                result.update(detail_probe)
                result["module_intent"] = "car_selection"
                result["task_intent"] = detail_probe.get("selection_task_intent")
                return self._attach_semantic(result, semantic_constraints, semantic_resolution)
            # A named brand/series followed by a business judgement question
            # (for example “全国，特斯拉怎么样”) is a selection entity
            # lookup, even when the user did not literally say “推荐收”.  Do
            # this before the generic market classifier so the answer resolves
            # the actual vehicle and its rank instead of returning a macro
            # market card.
            if client_state.get("ui_module") == "selection" and detail_probe.get("selection_detail_intent") in {
                "selection.entity_resolution",
                "selection.series_judgement",
            } and (
                slots.get("brand") or slots.get("series") or slots.get("trim")
            ):
                result = self._result(
                    "market_state",
                    "MARKET_STATE",
                    "MARKET_STATE_QUERY",
                    slots,
                    0.97,
                    {"type": None, "id": None},
                    render_market=True,
                    reason="识别到具体品牌或车系，进入选品实体研判链路",
                )
                result.update(detail_probe)
                result["module_intent"] = "car_selection"
                result["task_intent"] = detail_probe.get("selection_task_intent")
                return self._attach_semantic(result, semantic_constraints, semantic_resolution)

        # A clicked module is only workspace context, never permission to turn
        # every vehicle question into that module's default task.  Resolve
        # explicit vehicle/model knowledge questions before selection/market
        # fallbacks (for example “AMG GT50 是什么车”).
        open_automotive_task = self._cross_module_open_automotive_qa(
            text,
            selected_module,
            slots,
        )
        if open_automotive_task:
            return self._attach_semantic(open_automotive_task, semantic_constraints, semantic_resolution)
        text_first_route = self._text_first_business_route(text, selected_module, slots, client_state)
        if text_first_route:
            return self._attach_semantic(text_first_route, semantic_constraints, semantic_resolution)
        primary_llm_route = self._apply_llm_primary_route(
            message=text,
            selected_module=selected_module,
            slots=slots,
            client_state=client_state,
            semantic_constraints=semantic_constraints,
        )
        if primary_llm_route:
            return self._attach_semantic(primary_llm_route, semantic_constraints, semantic_resolution)
        cross_module_task = self._explicit_cross_module_task(text, selected_module, slots, client_state)
        if cross_module_task:
            return self._attach_semantic(cross_module_task, semantic_constraints, semantic_resolution)
        if re.search(r"全部重置|清空全部|重新开始整个任务", text):
            return self._attach_semantic(build_intent_result(
                selected_module=selected_module,
                business_category="RESET_CONTEXT",
                internal_intent="RESET_ALL",
                confidence=0.99,
                slots=slots,
                should_invalidate_quote=True,
                reason="用户要求重置全部业务上下文",
            ), semantic_constraints, semantic_resolution)

        semantic_route = self._semantic_cross_module_route(text, selected_module, slots, client_state)
        if semantic_route:
            return self._attach_semantic(semantic_route, semantic_constraints, semantic_resolution)

        open_semantic_route = self._open_semantic_route(text, selected_module, slots, semantic_constraints)
        if open_semantic_route:
            return self._attach_semantic(open_semantic_route, semantic_constraints, semantic_resolution)

        # Enterprise workflow rule: explicit vehicle pricing/acquisition/sale
        # requests must not be trapped by the currently selected non-pricing
        # module.  A user may be reading a report and then type “卖多少钱呢” or
        # “我要收车”; that is a pricing task, not a daily/market follow-up.
        if selected_module != "media_pricing" and self._should_route_to_media_pricing(text, slots):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = True
            result["reason"] = (
                result.get("reason") or ""
            ) + "；显式车辆估价/收售车话术跨模块抢占到媒体定价"
            return self._attach_semantic(result, semantic_constraints, semantic_resolution)

        if selected_module == "daily_report":
            result = self._classify_daily(text, slots, client_state)
        elif selected_module == "market_state":
            result = self._classify_market(text, slots, client_state)
        else:
            result = self._classify_media(text, slots, client_state)
        result = self._apply_semantic_fallback(
            result=result,
            message=text,
            selected_module=selected_module,
            slots=slots,
            client_state=client_state,
        )
        result = self._apply_llm_fallback(
            result=result,
            message=text,
            selected_module=selected_module,
            slots=slots,
            client_state=client_state,
        )
        return self._attach_semantic(result, semantic_constraints, semantic_resolution)

    @staticmethod
    def _llm_slot_value_is_explicit(message: str, key: str, value: Any) -> bool:
        """Reject a small set of known linguistic non-values from LLM slots."""

        text = str(message or "")
        normalized = str(value or "").strip()
        if key == "color" and normalized in {"其他", "其它", "其他颜色", "其它颜色"}:
            # In “其他不变/其它不变”, 其他 is a quantifier meaning all other
            # fields, not the catch-all vehicle color.
            if re.search(r"(?:其他|其它)\s*(?:都)?不变", text) and not re.search(
                r"(?:颜色\s*(?:是|为|改成|换成)?\s*(?:其他|其它)|(?:其他|其它)\s*颜色)",
                text,
            ):
                return False
        return True

    def _apply_llm_primary_route(
        self,
        *,
        message: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
        semantic_constraints: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        flag = os.environ.get("INTENT_V2_LLM_PRIMARY", "true").strip().lower()
        if flag in {"0", "false", "no", "off"}:
            return None
        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            and not os.environ.get("INTENT_V2_LLM_PRIMARY_TEST_ENABLE")
        ):
            return None
        if os.environ.get("INTENT_V2_LLM_PRIMARY_FORCE", "").strip().lower() not in {"1", "true", "yes", "on"}:
            if self._is_high_precision_enterprise_route(message, selected_module, slots):
                return None
        deterministic_seed = build_intent_result(
            selected_module=selected_module,
            business_category="UNKNOWN_OR_INCOMPLETE",
            internal_intent="UNKNOWN_OR_INCOMPLETE",
            confidence=0.20,
            slots=slots,
            reason="llm_primary_seed",
        )
        decision = self.llm_fallback.parse(
            message=message,
            selected_module=selected_module,
            deterministic_result=deterministic_seed,
            client_state=client_state,
            candidate_hints={
                "deterministic_slots": slots,
                "semantic_constraints": semantic_constraints,
                "routing_policy": {
                    "selection_reason_query": "market_state/MARKET_REASON_QUERY",
                    "selection_recommend_query": "market_state/MARKET_OPPORTUNITY_RECOMMEND",
                    "market_series_query": "market_state/MARKET_SERIES_QUERY",
                    "daily_report_only_when_explicit": True,
                    "pricing_only_when_price_or_six_elements": True,
                },
            },
        )
        if not decision.ok or not decision.result:
            return None
        llm = decision.result
        llm_confidence = float(llm.get("confidence") or 0)
        if llm_confidence < float(os.environ.get("INTENT_V2_LLM_PRIMARY_MIN_CONFIDENCE", "0.60")):
            return None
        merged_slots = dict(slots)
        for key, value in (llm.get("slots") or {}).items():
            # The LLM is the primary intent router, not an authority that may
            # coarsen explicit vehicle facts already extracted from the user's
            # text.  It may fill missing fields, while deterministic/catalog
            # identities such as “宋PLUS DM-i” must survive verbatim.
            if (
                merged_slots.get(key) in (None, "")
                and value not in (None, "", "null", "None", "未知")
                and self._llm_slot_value_is_explicit(message, key, value)
            ):
                merged_slots[key] = value
        target_module = llm.get("selected_module") or selected_module
        intent = llm.get("internal_intent") or "UNKNOWN_OR_INCOMPLETE"
        category = llm.get("business_category") or "UNKNOWN_OR_INCOMPLETE"
        if self._is_selection_reason_text(message):
            target_module = "market_state"
            category = "MARKET_STATE"
            intent = "MARKET_REASON_QUERY"
        if target_module == "media_pricing" and not self._should_route_to_media_pricing(message, merged_slots):
            if intent not in {
                "GENERAL_AUTOMOTIVE_QA",
                "VEHICLE_INFO_ADD",
                "VEHICLE_INFO_UPDATE",
                "PRICE_EXPLANATION_REQUEST",
                "CANDIDATE_EVIDENCE_REQUEST",
                "WHY_LOW_CONFIDENCE",
                "HISTORY_VEHICLE_REFERENCE",
                "BUSINESS_INTENT_CLARIFICATION",
            }:
                return None
        result = build_intent_result(
            selected_module=target_module,
            business_category=category,
            internal_intent=intent,
            confidence=min(0.93, max(0.62, llm_confidence)),
            slots=merged_slots,
            context_reference=llm.get("context_reference") or {"type": None, "id": None},
            fallback_message=llm.get("clarification_question") if llm.get("needs_clarification") else None,
            target_module=target_module if target_module != selected_module else None,
            reason=f"LLM primary route accepted: {llm.get('reason') or ''}".strip(),
        )
        result["llm_intent_primary"] = {
            "used": True,
            "model": llm.get("llm_model"),
            "latency_ms": llm.get("llm_latency_ms"),
            "raw": decision.raw,
        }
        if llm.get("semantic_entities"):
            result["semantic_entities"] = llm.get("semantic_entities")
        if target_module == "market_state":
            detail = classify_selection_detail_intent(
                message,
                slots=merged_slots,
                internal_intent=intent,
                has_context=bool(
                    client_state.get("lastMarketOpportunityContext")
                    or client_state.get("last_market_opportunity_context")
                ),
            )
            llm_detail = str(llm.get("selection_detail_intent") or "").strip()
            deterministic_detail = str(detail.get("selection_detail_intent") or "")
            llm_may_refine_detail = deterministic_detail in LLM_REFINABLE_SELECTION_DETAILS
            if llm_detail and llm_may_refine_detail:
                detail = build_selection_detail_contract(llm_detail, internal_intent=intent)
            result.update(detail)
            if llm.get("answer_mode") and llm_may_refine_detail:
                result["answer_mode"] = llm.get("answer_mode")
            result["module_intent"] = "car_selection"
            result["task_intent"] = detail.get("selection_task_intent")
        if target_module != selected_module:
            result["explicit_cross_module_intent"] = True
        return result

    @staticmethod
    def _attach_semantic(
        result: Dict[str, Any],
        semantic_constraints: Dict[str, Any] | None,
        semantic_resolution: Any | None = None,
    ) -> Dict[str, Any]:
        GlobalIntentClassifierV2._apply_enterprise_taxonomy(result)
        if semantic_constraints:
            result["semantic_constraints"] = dict(semantic_constraints)
            entities = dict(result.get("semantic_entities") or {})
            entities.update(
                {
                    "referenced_entity": semantic_constraints.get("referenced_entity") or entities.get("referenced_entity"),
                    "implied_brand": semantic_constraints.get("implied_brand") or result.get("slots", {}).get("brand") or entities.get("implied_brand"),
                    "brand_origin_country": semantic_constraints.get("brand_origin_country") or entities.get("brand_origin_country"),
                    "query_focus": entities.get("query_focus"),
                    "open_world_terms": entities.get("open_world_terms") or [],
                }
            )
            result["semantic_entities"] = entities
            result["semantic_resolution"] = {
                "confidence": getattr(semantic_resolution, "confidence", None),
                "reason": getattr(semantic_resolution, "reason", ""),
            }
        return result

    @staticmethod
    def _apply_enterprise_taxonomy(result: Dict[str, Any]) -> None:
        selected_module = result.get("selected_module")
        business_category = result.get("business_category")
        internal = result.get("internal_intent")
        pricing_task = result.get("pricing_task")
        # Open vehicle knowledge questions are not selection tasks merely
        # because the user happened to type them while the selection tab was
        # active.  Keep the clicked module as presentation context, while the
        # task contract truthfully describes a direct answer.
        if internal == "GENERAL_AUTOMOTIVE_QA" or business_category == "GENERAL_AUTOMOTIVE_QA":
            result["module_intent"] = "other"
            result["task_intent"] = "answer_automotive_question"
            return
        if result.get("module_intent") not in {"car_selection", "pricing", "market_report", "other"}:
            if selected_module == "media_pricing" and business_category in {"MEDIA_VALUATION", "PARAM_ADJUSTMENT", "PRICING_QA"}:
                result["module_intent"] = "pricing"
            elif selected_module == "market_state" and internal in {"MARKET_REPORT_QUERY", "MARKET_STATE_QUERY", "MARKET_SERIES_QUERY"}:
                result["module_intent"] = "market_report"
            elif selected_module == "market_state":
                result["module_intent"] = "car_selection"
            elif selected_module == "daily_report":
                result["module_intent"] = "market_report"
            else:
                result["module_intent"] = "other"
        if result.get("task_intent"):
            return
        if result["module_intent"] == "pricing":
            if internal == "PURCHASE_PRICE_JUDGEMENT":
                result["task_intent"] = "judge_purchase_price"
            elif internal == "PRICE_EXPLANATION_REQUEST":
                result["task_intent"] = "explain_pricing_result"
            elif internal == "PRICE_FEEDBACK_CLARIFICATION":
                result["task_intent"] = "clarify_pricing_feedback"
            elif internal == "CANDIDATE_EVIDENCE_REQUEST":
                result["task_intent"] = "explain_comparable_evidence"
            elif internal == "WHY_LOW_CONFIDENCE":
                result["task_intent"] = "explain_pricing_confidence"
            elif internal == "HISTORY_VEHICLE_REFERENCE":
                result["task_intent"] = "explain_history_quote"
            elif result.get("pricing_advice_mode") == "recommend_purchase_price":
                result["task_intent"] = "recommend_purchase_price"
            elif result.get("pricing_advice_mode") == "judge_listing_price":
                result["task_intent"] = "judge_listing_price"
            elif result.get("pricing_advice_mode") == "judge_customer_offer":
                result["task_intent"] = "judge_customer_offer"
            elif pricing_task == "B2C" or result.get("pricing_advice_mode") == "sale_price_advice":
                result["task_intent"] = "judge_listing_price"
            else:
                result["task_intent"] = "estimate_vehicle_value"
        elif result["module_intent"] == "car_selection":
            mapping = {
                "MARKET_OPPORTUNITY_RECOMMEND": "recommend_models",
                "MARKET_PRICE_BUCKET_QUERY": "recommend_price_band",
                "MARKET_CITY_CHANGE": "recommend_city_opportunity",
                "MARKET_RISK_QUERY": "identify_risky_models",
                "MARKET_REASON_QUERY": "explain_selection_reason",
                "COMPOUND_SELECTION_PRICING": "selection_to_pricing",
            }
            result["task_intent"] = mapping.get(str(internal), "recommend_models")
        elif result["module_intent"] == "market_report":
            if result.get("slots", {}).get("city"):
                result["task_intent"] = "city_market_report"
            elif result.get("slots", {}).get("price_bucket") or result.get("slots", {}).get("price_band"):
                result["task_intent"] = "price_band_report"
            elif re.search(r"新车|降价|优惠|冲击|影响", str(result.get("reason") or "")):
                result["task_intent"] = "new_car_impact_report"
            else:
                result["task_intent"] = "model_market_report"
        else:
            result["task_intent"] = "other"

    def _open_semantic_route(
        self,
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
        semantic_constraints: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if not semantic_constraints:
            return None
        if (
            self._is_pricing_request_text(text)
            or self._is_daily_request_text(text)
            or self._is_market_request_text(text)
            or self._is_buy_request_text(text)
        ):
            return None
        if semantic_constraints.get("brand_origin_country") and re.search(r"推荐|有哪些|什么|哪.*品牌|哪.*车|值得|适合|怎么选", text):
            return build_intent_result(
                selected_module="market_state" if re.search(r"值得收|行情|库存|周转|市场", text) else selected_module,
                business_category="GENERAL_AUTOMOTIVE_QA",
                internal_intent="GENERAL_AUTOMOTIVE_QA",
                confidence=0.78,
                slots=slots,
                reason="开放品牌派系语义问题，进入受控汽车业务问答",
            )
        if semantic_constraints.get("referenced_entity") or semantic_constraints.get("implied_brand"):
            return build_intent_result(
                selected_module=selected_module,
                business_category="GENERAL_AUTOMOTIVE_QA",
                internal_intent="GENERAL_AUTOMOTIVE_QA",
                confidence=0.76,
                slots=slots,
                reason="开放世界车辆实体引用，进入受控汽车业务问答",
            )
        return None

    @classmethod
    def _is_high_precision_enterprise_route(cls, text: str, selected_module: str, slots: Dict[str, Any]) -> bool:
        if cls._is_selection_reason_text(text):
            return True
        if cls._is_daily_request_text(text) or cls._is_pricing_request_text(text):
            return True
        if cls._is_market_request_text(text):
            return True
        if re.search(r"行情|选品|值得收|风险车系|机会车系|库存|周转|价格段|价格带", str(text or "")):
            return True
        if (
            re.search(r"\d+(?:\.\d+)?\s*(?:[-~—至到]\s*\d+(?:\.\d+)?)?\s*万(?:以内|以下|以上|起)?", str(text or ""))
            and re.search(r"机会|值得|推荐|适合|可收|能做|筛|优先", str(text or ""))
        ):
            return True
        if selected_module == "market_state" and (slots.get("brand") or slots.get("series") or slots.get("city")):
            return True
        return False

    def _cross_module_open_automotive_qa(
        self,
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if not self._looks_like_cross_module_open_automotive_question(text, slots):
            return None
        qa_slots = self._augment_open_qa_topic_slots(text, slots)
        return build_intent_result(
            selected_module=selected_module,
            business_category="GENERAL_AUTOMOTIVE_QA",
            internal_intent="GENERAL_AUTOMOTIVE_QA",
            confidence=0.84,
            slots=qa_slots,
            reason="跨模块开放汽车常识/车型知识问题，进入受控问答，不调用估价工具",
        )

    def _apply_semantic_fallback(
        self,
        *,
        result: Dict[str, Any],
        message: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_intent = result.get("internal_intent")
        match = self.example_matcher.match(message, selected_module)
        if not match:
            return result
        expected = match["expected"]
        intent = expected.get("internal_intent")
        category = expected.get("business_category") or "UNKNOWN_OR_INCOMPLETE"
        generic_overrides = {
            ("VEHICLE_INFO_ADD", "BUSINESS_INTENT_CLARIFICATION"),
            ("MARKET_STATE_QUERY", "MARKET_OPPORTUNITY_RECOMMEND"),
            ("MARKET_STATE_QUERY", "MARKET_RISK_QUERY"),
            ("MARKET_STATE_QUERY", "MARKET_PRICE_BUCKET_QUERY"),
        }
        if current_intent not in {"UNKNOWN_OR_INCOMPLETE", "OUT_OF_SCOPE"}:
            if (current_intent, intent) not in generic_overrides or float(match["score"]) < 0.70:
                return result
        requires_daily_context = intent in {
            "DAILY_REPORT_DETAIL_QUESTION",
            "DAILY_REPORT_POLICY_QUERY",
            "DAILY_REPORT_DISCOUNT_QUERY",
            "DAILY_REPORT_NEWS_QUERY",
            "DAILY_REPORT_SECTION_QUERY",
        }
        requires_market_context = intent == "MARKET_REASON_QUERY"
        requires_quote = intent in {
            "PRICE_EXPLANATION_REQUEST",
            "PRICE_FEEDBACK_CLARIFICATION",
            "CANDIDATE_EVIDENCE_REQUEST",
            "WHY_LOW_CONFIDENCE",
            "HISTORY_VEHICLE_REFERENCE",
        }
        if requires_daily_context and not (
            client_state.get("lastDailyReportContext") or client_state.get("last_daily_report_context")
        ):
            return result
        if requires_market_context and not (
            client_state.get("lastMarketOpportunityContext") or client_state.get("last_market_opportunity_context")
        ):
            return result
        if requires_quote and not (
            client_state.get("current_pricing_result")
            or client_state.get("last_price_result")
            or client_state.get("vehicle_history")
        ):
            return result
        semantic_result = build_intent_result(
            selected_module=selected_module,
            business_category=category,
            internal_intent=intent,
            confidence=min(0.89, max(0.62, float(match["score"]))),
            slots=slots,
            context_reference=result.get("context_reference") or {"type": None, "id": None},
            reason=(
                "reviewed-example semantic fallback: "
                f"{match['supporting_examples'][0]['example_id']} "
                f"score={match['score']} margin={match['margin']}"
            ),
        )
        semantic_result["semantic_intent_match"] = {
            "score": match["score"],
            "margin": match["margin"],
            "supporting_examples": match["supporting_examples"],
        }
        return semantic_result

    def _apply_llm_fallback(
        self,
        *,
        result: Dict[str, Any],
        message: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        should_consult_llm = (
            result.get("internal_intent") in {"UNKNOWN_OR_INCOMPLETE", "OUT_OF_SCOPE", "BUSINESS_INTENT_CLARIFICATION"}
            or float(result.get("confidence") or 0) < 0.58
            or bool(result.get("fallback_message")) and result.get("business_category") == "UNKNOWN_OR_INCOMPLETE"
        )
        if not should_consult_llm:
            return result
        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            and not self._llm_fallback_injected
            and not os.environ.get("INTENT_V2_LLM_FALLBACK_TEST_ENABLE")
        ):
            return result

        decision = self.llm_fallback.parse(
            message=message,
            selected_module=selected_module,
            deterministic_result=result,
            client_state=client_state,
            candidate_hints={
                "deterministic_slots": slots,
                "semantic_match": result.get("semantic_intent_match") or result.get("enterprise_semantic_route"),
            },
        )
        if not decision.ok or not decision.result:
            result["llm_intent_fallback"] = {"used": False, "reason": decision.reason}
            return result

        llm = decision.result
        llm_confidence = float(llm.get("confidence") or 0)
        if llm_confidence < 0.62:
            result["llm_intent_fallback"] = {"used": False, "reason": "LLM_LOW_CONFIDENCE", "raw": decision.raw}
            return result

        merged_slots = dict(slots)
        for key, value in (llm.get("slots") or {}).items():
            if (
                key in merged_slots
                and merged_slots.get(key) in (None, "")
                and value not in (None, "")
                and self._llm_slot_value_is_explicit(message, key, value)
            ):
                merged_slots[key] = value

        target_module = llm.get("selected_module") or selected_module
        intent = llm.get("internal_intent") or result.get("internal_intent")
        category = llm.get("business_category") or result.get("business_category")

        if target_module == "media_pricing" and not self._should_route_to_media_pricing(message, merged_slots):
            if intent not in {
                "VEHICLE_INFO_ADD",
                "VEHICLE_INFO_UPDATE",
                "PRICE_EXPLANATION_REQUEST",
                "PRICE_FEEDBACK_CLARIFICATION",
                "CANDIDATE_EVIDENCE_REQUEST",
                "WHY_LOW_CONFIDENCE",
                "HISTORY_VEHICLE_REFERENCE",
                "BUY_CAR_INTENT",
                "BUSINESS_INTENT_CLARIFICATION",
                "GENERAL_AUTOMOTIVE_QA",
            }:
                result["llm_intent_fallback"] = {"used": False, "reason": "MEDIA_ROUTE_POLICY_REJECT", "raw": decision.raw}
                return result

        fallback = llm.get("clarification_question") if llm.get("needs_clarification") else result.get("fallback_message")
        llm_result = build_intent_result(
            selected_module=target_module,
            business_category=category,
            internal_intent=intent,
            confidence=max(float(result.get("confidence") or 0), min(0.86, llm_confidence)),
            slots=merged_slots,
            context_reference=llm.get("context_reference") or result.get("context_reference") or {"type": None, "id": None},
            fallback_message=fallback,
            target_module=target_module if target_module != selected_module else None,
            reason=f"LLM structured fallback accepted: {llm.get('reason') or ''}".strip(),
        )
        llm_result["llm_intent_fallback"] = {
            "used": True,
            "model": llm.get("llm_model"),
            "latency_ms": llm.get("llm_latency_ms"),
            "raw": decision.raw,
        }
        if llm.get("semantic_entities"):
            llm_result["semantic_entities"] = llm.get("semantic_entities")
        if target_module == "market_state":
            detail = classify_selection_detail_intent(
                message,
                slots=merged_slots,
                internal_intent=intent,
                has_context=bool(
                    client_state.get("lastMarketOpportunityContext")
                    or client_state.get("last_market_opportunity_context")
                ),
            )
            llm_detail = str(llm.get("selection_detail_intent") or "").strip()
            deterministic_detail = str(detail.get("selection_detail_intent") or "")
            llm_may_refine_detail = deterministic_detail in LLM_REFINABLE_SELECTION_DETAILS
            if llm_detail and llm_may_refine_detail:
                detail = build_selection_detail_contract(llm_detail, internal_intent=intent)
            llm_result.update(detail)
            if llm.get("answer_mode") and llm_may_refine_detail:
                llm_result["answer_mode"] = llm.get("answer_mode")
            llm_result["module_intent"] = "car_selection"
            llm_result["task_intent"] = detail.get("selection_task_intent")
        if target_module != selected_module:
            llm_result["explicit_cross_module_intent"] = True
        return llm_result

    def _semantic_cross_module_route(
        self,
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        route = self.example_matcher.route_across_modules(text, selected_module)
        if not route:
            return None
        target_module = route.get("selected_module")
        expected = route.get("expected") or {}
        target_intent = expected.get("internal_intent")
        score = float(route.get("score") or 0)
        module_margin = float(route.get("module_margin") or 0)

        if selected_module == "media_pricing" and target_module != "media_pricing":
            vehicle_identity_count = sum(
                slots.get(key) not in (None, "")
                for key in ("brand", "series", "model_year", "trim")
            )
            if vehicle_identity_count and target_intent in {"OUT_OF_SCOPE", "MARKET_STATE_QUERY"}:
                return None

        if route.get("needs_clarification"):
            return build_intent_result(
                selected_module=selected_module,
                business_category="UNKNOWN_OR_INCOMPLETE",
                internal_intent="BUSINESS_INTENT_CLARIFICATION",
                confidence=min(0.69, max(0.55, score)),
                slots=slots,
                fallback_message="这句话可能对应多个任务，请确认是要估价、看日报，还是看城市行情。",
                reason=(
                    "enterprise semantic router found close module scores: "
                    f"{route.get('module_scores')}"
                ),
            )

        if target_module == selected_module:
            return None
        if target_module == "media_pricing" and not self._should_route_to_media_pricing(text, slots):
            return None
        if score < 0.56 and module_margin < 0.045:
            return None

        if target_module == "daily_report":
            result = self._classify_daily(text, slots, client_state)
        elif target_module == "market_state":
            result = self._classify_market(text, slots, client_state)
        elif target_module == "media_pricing":
            result = self._classify_media(text, slots, client_state)
        else:
            return None
        result["selected_module"] = target_module
        result["explicit_cross_module_intent"] = True
        result["enterprise_semantic_route"] = {
            "score": route.get("score"),
            "raw_score": route.get("raw_score"),
            "module_margin": route.get("module_margin"),
            "intent_margin": route.get("intent_margin"),
            "module_scores": route.get("module_scores"),
            "supporting_examples": route.get("supporting_examples"),
        }
        result["reason"] = (
            result.get("reason") or ""
        ) + "；enterprise semantic router 跨模块路由"
        return result

    def _text_first_business_route(
        self,
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """Route explicit business tasks by the utterance, not by the clicked UI module."""
        if not text:
            return None
        discount_board_lookup = bool(
            (
                re.search(r"降价(?:榜|排行)|新车降价榜|降价.*最多|优惠.*最多", text)
                and re.search(r"打开|查看|看看|在不在|有没有|排名|第几|数据|筛选|榜单|哪些|什么车|哪.*车|最多", text)
            )
            and not re.search(r"为什么|风险还是机会|选品策略|推荐收|值得收|适合收|怎么影响收车", text)
        )
        if discount_board_lookup:
            result = self._classify_daily(text, slots, client_state)
            result["selected_module"] = "daily_report"
            result["explicit_cross_module_intent"] = selected_module != "daily_report"
            result["reason"] = (result.get("reason") or "") + "；明确查询降价榜名单、名次或筛选结果，优先进入公开榜单工具"
            return result
        has_quote = bool(
            client_state.get("current_pricing_result")
            or client_state.get("last_price_result")
        )
        if has_quote and re.search(
            r"(?:里程|公里|城市|上牌|过户|颜色|车况|车型).{0,8}(?:改成|修改|更正|换成|调整)|"
            r"(?:改成|修改|更正|换成|调整).{0,8}(?:里程|公里|城市|上牌|过户|颜色|车况|车型)|"
            r"(?:里程|公里|车龄|过户).{0,12}(?:增加|减少|多|少|再加|再减|变成).{0,8}(?:会怎样|会如何|差多少|影响|重新算|再算|怎么样|如何)|"
            r"(?:重新估|重新算|再估|再算)",
            text,
        ):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；有效报价上下文中的字段修改由定价链路承接"
            return result
        if (
            selected_module == "media_pricing"
            and re.search(r"这两辆|两台车|哪辆更|哪个报价|比较这两辆|对比这两辆", text)
            and not re.search(r"选品|车系|榜单|推荐收|值得收|风险", text)
        ):
            result = self._classify_media(text, slots, client_state)
            if result.get("internal_intent") != "UNKNOWN_OR_INCOMPLETE":
                return result
        if (
            selected_module == "daily_report"
            and (client_state.get("lastDailyReportContext") or client_state.get("last_daily_report_context"))
            and (
                re.search(r"上面|这条|这个|刚才|该政策|那个政策", text)
                and re.search(r"政策|补贴|日报|影响|展开|原因", text)
                or re.search(r"数据来源|数据口径|时间范围|这些数据", text)
                or (
                    re.search(r"政策|补贴|降价|行业动态|日报", text)
                    and re.search(r"影响|原因|为什么|是什么|怎么看|展开|哪些|哪条", text)
                )
            )
            and not re.search(r"选品|推荐收|值得收|收车|风险车系|机会车系", text)
        ):
            result = self._classify_daily(text, slots, client_state)
            result["selected_module"] = "daily_report"
            result["reason"] = (result.get("reason") or "") + "；日报上下文追问优先由日报模块承接"
            return result
        if selected_module == "daily_report" and re.search(
            r"数据来源|数据口径|时间范围|这些数据|日报来源|报告来源",
            text,
        ):
            result = self._classify_daily(text, slots, client_state)
            result["selected_module"] = "daily_report"
            result["reason"] = (result.get("reason") or "") + "；日报工作区中的数据口径问题由日报证据链承接"
            return result
        compound_selection_pricing = bool(
            re.search(r"哪些车|选品|值得收|适合收|推荐收|车系推荐|补库", text)
            and re.search(r"收车价|售车价|报价|估价|多少钱|建议收车价", text)
        )
        compound_report_advice = bool(
            re.search(r"行情报告|行情日报|市场报告", text)
            and re.search(r"收车建议|经营建议|怎么收|建议收", text)
        )
        if compound_selection_pricing or compound_report_advice:
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；复合选品/行情与定价任务按多工具链执行"
            return result
        has_vehicle_context = bool(
            client_state.get("current_slots")
            or client_state.get("current_vehicle_match")
            or has_quote
        )
        if (
            has_quote
            and slots.get("user_given_price_yuan") not in (None, "")
            and re.search(r"按.{0,12}收|这个价|这价格|收进来|拿下", text)
            and re.search(r"赚|亏|利润|毛利|划算|合算|能不能做|可不可以做", text)
        ):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；已有报价上的指定收车价利润试算由定价链路承接"
            return result
        if (
            has_vehicle_context
            and slots.get("user_given_price_yuan") not in (None, "")
            and re.search(r"能不能收|可不可以收|这个价能收|收这个价|收高了|收贵了", text)
        ):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；已有单车上下文中的客户报价判断由定价链路承接"
            return result
        if has_quote and re.search(r"(?:再|还能?|如果)?(?:往上)?加\s*[0-9]+(?:\.[0-9]+)?\s*(?:万|千|元)?", text) and re.search(r"能不能收|可以收|可不可以收|还能收|还可以收|行不行|值不值", text):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；当前报价上的加价试算由定价利润链路承接"
            return result
        selection_family = classify_selection_query_family(
            text,
            has_vehicle_entity=bool(slots.get("brand") or slots.get("series") or slots.get("trim")),
        )
        if selection_family:
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (
                result.get("reason") or ""
            ) + f"；文本语义族{selection_family}优先进入选品链路，当前模块仅作界面提示"
            return result
        if has_quote and re.search(
            r"价格不准|报价不准|不准确|不合理|有偏差|不靠谱|"
            r"(?:收车价|售车价|卖车价|挂牌价|报价|价格).*(?:偏高|太高|高了|偏低|太低|低了)|"
            r"(?:网上|瓜子|懂车帝|汽车之家|人人车|优信|车商|市场).*(?:卖|挂|成交|报价)|"
            r"(?:其他机构|别家|同行).*(?:报价|给价|出价|给(?:了)?我?\s*\d)|"
            r"同款.*(?:比你|更)(?:高|低)|成交价.*(?:比你|更)(?:高|低)|同款车别人|别人卖|市场不是|收进来.*亏|肯定亏",
            text,
        ) and not re.search(r"为什么|为啥|为何|原因|怎么会", text):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；有效报价上下文中的价格质疑由只读反馈链路承接"
            return result
        if has_quote and re.search(
            r"可比车|候选车|相似成交|报价.*(?:依据|证据|解释|怎么|如何|为什么|得出|来的)|"
            r"(?:报价|价格|估值|置信).*(?:为什么|怎么|如何|依据|不高|低)|"
            r"收车价.*售车价|售车价.*收车价|这个报价|这个价格",
            text,
        ):
            result = self._classify_media(text, slots, client_state)
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；有效报价上下文中的证据/解释问题由定价承接"
            return result
        unambiguous_selection_action = bool(
            re.search(
                r"选品|值得收|适合收|推荐收|哪些车|机会车系|风险车系|暂缓收|别碰|避坑|补库|"
                r"优先收车方向|收车方向|谁更适合做|谁更适合收|能不能收|好不好做|推荐几个车",
                text,
            )
        )
        if unambiguous_selection_action and self._is_selection_request_text(text, slots) and not is_explicit_pricing_query(text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；选品业务动作优先于当前模块按钮"
            return result
        if re.search(r"(?:找到|锁定|有了).{0,8}具体车.{0,12}(?:怎么|如何).{0,8}(?:定价|收车价)", text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；这是选品到单车定价的流程追问，不是当前车辆报价请求"
            return result
        if self._should_route_to_media_pricing(text, slots):
            result = self._classify_media(text, slots, client_state)
            if result.get("internal_intent") != "UNKNOWN_OR_INCOMPLETE":
                result["selected_module"] = "media_pricing"
                result["explicit_cross_module_intent"] = selected_module != "media_pricing"
                result["reason"] = (result.get("reason") or "") + "；明确价格/报价上下文优先于通用证据词"
                return result
            return None
        if self._is_batch_pricing_text(text):
            result = self._classify_media(text, slots, client_state)
            if result.get("internal_intent") == "UNKNOWN_OR_INCOMPLETE":
                return None
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；批量/多车估价文本优先进入定价链路"
            return result
        if re.search(r"查一下.*政策|最新政策|购车补贴最新政策", text) and not re.search(r"选品|推荐|收车|二手车推荐", text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；政策检索任务进入政策工具而非日报阅读"
            return result
        if self._is_daily_request_text(text) and not self._is_selection_request_text(text, slots):
            result = self._classify_daily(text, slots, client_state)
            result["selected_module"] = "daily_report"
            result["explicit_cross_module_intent"] = selected_module != "daily_report"
            result["reason"] = (result.get("reason") or "") + "；文本优先识别为日报/政策/榜单任务，忽略当前模块按钮"
            return result
        if self._is_selection_ui_scope_text(text, selected_module, slots, client_state):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["module_intent"] = "car_selection"
            result["task_intent"] = result.get("task_intent") or "recommend_models"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；选品模块筛选条件触发选品链路"
            clean_slots = result.get("slots") or slots
            if str(clean_slots.get("series") or "").strip() in {"新能源", "燃油", "油车", "电车", "SUV", "MPV", "轿车", "综合新能源"}:
                clean_slots["series"] = None
                clean_slots["brand"] = None
            ui_category = str(
                client_state.get("selectedBodyType")
                or client_state.get("selected_body_type")
                or client_state.get("body_filter")
                or client_state.get("selectedVehicleCategory")
                or client_state.get("selected_vehicle_category")
                or ""
            ).strip()
            ui_energy = str(
                client_state.get("selectedEnergyType")
                or client_state.get("selected_energy_type")
                or client_state.get("energy_filter")
                or ""
            ).strip()
            legacy_category = str(
                client_state.get("selectedVehicleCategory")
                or client_state.get("selected_vehicle_category")
                or ""
            ).strip()
            if legacy_category in {"新能源", "综合新能源", "燃油", "燃油车", "油车"} and not ui_energy:
                ui_energy = legacy_category
                ui_category = ""
            if ui_energy:
                clean_slots["fuel_type"] = "新能源" if ui_energy in {"新能源", "综合新能源", "电车", "纯电", "插混", "增程"} else "燃油车" if ui_energy in {"燃油", "燃油车", "油车"} else ui_energy
                clean_slots["energy_filter"] = clean_slots["fuel_type"]
            tier = normalize_brand_tier(legacy_category) or normalize_brand_tier(ui_category)
            if tier:
                clean_slots["brand_tier"] = tier
            if ui_category:
                normalized_category = "新能源" if ui_category == "综合新能源" else ui_category
                if normalized_category in {"全部", "总计", "轿车", "SUV", "MPV"}:
                    clean_slots["selection_filter"] = "全部" if normalized_category == "总计" else normalized_category
                    clean_slots["body_filter"] = clean_slots["selection_filter"]
                if normalized_category in {"轿车", "SUV", "MPV"}:
                    clean_slots["vehicle_type"] = normalized_category
                    clean_slots["vehicle_category"] = normalized_category
            detail = classify_selection_detail_intent(
                text,
                slots=clean_slots,
                internal_intent=result.get("internal_intent") or "",
                has_context=bool(client_state.get("lastMarketOpportunityContext")),
            )
            result.update(detail)
            return result
        if self._is_selection_request_text(text, slots):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；文本优先识别为选品/行情任务，忽略当前模块按钮"
            return result
        if self._should_route_to_media_pricing(text, slots):
            result = self._classify_media(text, slots, client_state)
            if result.get("internal_intent") == "UNKNOWN_OR_INCOMPLETE":
                return None
            result["selected_module"] = "media_pricing"
            result["explicit_cross_module_intent"] = selected_module != "media_pricing"
            result["reason"] = (result.get("reason") or "") + "；文本优先识别为单车定价任务，忽略当前模块按钮"
            return result
        if self._is_market_request_text(text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；文本优先识别为行情/选品任务，忽略当前模块按钮"
            return result
        return None

    def _explicit_cross_module_task(
        self,
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if not text:
            return None
        if re.search(r"行情报告|市场报告", text) and re.search(r"收车建议|经营建议|怎么收|建议收", text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；跨模块识别为行情报告+经营/收车建议复合任务"
            return result
        daily_patterns = (
            r"日报|今日报告|行业报告|降价最多|降价榜|降价排行|降价品牌|降价车系|优惠最大|优惠最多|促销|"
            r"什么车.*降价|哪.*车.*降价|"
            r"政策速递|政策.*影响|影响.*政策|政策.*怎么看|补贴.*影响|新车发布|新车上市|新车有哪些|新车.*改款|改款.*上市|预售|"
            r"行业动态|经营建议|全国榜单|价格波动榜"
        )
        market_patterns = (
            r"行情状态|行情选品|城市行情|值得收|哪些车值得|库存|周转|流动性|市场机会|"
            r"选品推荐|推荐里|为什么.*推荐|为什么.*不在.*推荐|不在.*选品|"
            r"(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|长春|全国).{0,4}行情"
        )
        geo_market_request = bool(slots.get("city") and re.search(r"行情|市场|选品|值得收|库存|周转", text))
        if (re.search(market_patterns, text) or geo_market_request) and not re.search(r"日报|报告|降价榜|降价最多|全国榜单", text):
            result = self._classify_market(text, slots, client_state)
            result["selected_module"] = "market_state"
            result["explicit_cross_module_intent"] = selected_module != "market_state"
            result["reason"] = (result.get("reason") or "") + "；跨模块识别为行情状态机任务"
            return result
        if re.search(daily_patterns, text) and not re.search(
            r"估价|报价|收车|卖车|售价|卖多少钱|收多少钱|调价|展板价",
            text,
        ):
            result = self._classify_daily(text, slots, client_state)
            result["selected_module"] = "daily_report"
            result["explicit_cross_module_intent"] = selected_module != "daily_report"
            result["reason"] = (result.get("reason") or "") + "；跨模块识别为行业日报/报告任务"
            return result
        return None

    def _classify_daily(
        self,
        text: str,
        slots: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = state.get("lastDailyReportContext") or state.get("last_daily_report_context") or {}
        context_ref = {
            "type": "last_daily_report" if context else None,
            "id": context.get("report_id") or context.get("filename"),
        }
        date_query = resolve_daily_report_date(text)
        if date_query.is_explicit:
            date_specific: tuple[str, str | None] | None = None
            if re.search(r"政策|补贴|法规|以旧换新", text):
                date_specific = ("DAILY_REPORT_POLICY_QUERY", "policy")
            elif re.search(r"降价|优惠|价格战", text):
                date_specific = ("DAILY_REPORT_DISCOUNT_QUERY", "discount")
            elif re.search(r"新车|上市|预售|行业动态|行业新闻", text):
                date_specific = ("DAILY_REPORT_NEWS_QUERY", "new_car")
            elif re.search(r"行情|成交|上架|库存|周转", text):
                date_specific = ("DAILY_REPORT_SECTION_QUERY", "industry_data")
            elif re.search(r"经营建议|收车建议|怎么做", text):
                date_specific = ("DAILY_REPORT_SECTION_QUERY", "suggestion")
            if date_specific:
                result = self._result(
                    "daily_report", "DAILY_REPORT", date_specific[0], slots, 0.98, context_ref, section=date_specific[1]
                )
                result["daily_report_query"] = date_query.as_dict()
                return result
        if date_query.is_explicit or re.search(r"历史日报|过去.*日报|哪天.*日报", text):
            result = self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_HISTORY", slots, 0.98, context_ref, render_daily=True)
            result["daily_report_query"] = date_query.as_dict()
            return result
        if re.search(r"数据来源|数据口径|时间范围|这些数据真实吗|CADA|懂车帝降价榜", text, flags=re.I):
            return self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_DATA_SCOPE_QUERY", slots, 0.97, context_ref)
        if context and re.search(r"这个|上面|刚才|原因|为什么|影响|展开|下跌|上涨|跌幅|涨幅", text):
            return self._result(
                "daily_report",
                "DAILY_REPORT",
                "DAILY_REPORT_DETAIL_QUESTION",
                slots,
                0.94,
                context_ref,
            )
        if re.search(r"政策|补贴|法规|以旧换新", text):
            return self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_POLICY_QUERY", slots, 0.96, context_ref, section="policy")
        if re.search(
            r"降价品牌|哪些.*降价|降价车系|价格战|什么车.*降价|哪.*车.*降价|"
            r"降价.*最多|降价榜|降价排行|优惠最大|优惠最多|新车降价",
            text,
        ):
            return self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_DISCOUNT_QUERY", slots, 0.96, context_ref, section="discount")
        if re.search(r"新车发布|新车有哪些|行业动态|行业新闻|车企动态", text):
            return self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_NEWS_QUERY", slots, 0.95, context_ref, section="new_car")
        if re.search(r"经营建议|行情数据怎么看|收车有什么影响|库存建议|新能源评估", text):
            section = "suggestion" if "建议" in text or "影响" in text else "industry_data"
            return self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_SECTION_QUERY", slots, 0.94, context_ref, section=section)
        if re.search(r"(?:全国|城市|品牌|车系|车型|价格波动)?.{0,4}(?:榜单|排行|排名|TOP|top)", text):
            fallback = None if context else "请先查看今日行业日报，再查看全国、城市、品牌或车系榜单。"
            return self._result(
                "daily_report",
                "DAILY_REPORT" if context else "UNKNOWN_OR_INCOMPLETE",
                "DAILY_REPORT_SECTION_QUERY" if context else "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.96 if context else 0.62,
                context_ref,
                section="ranking",
                fallback=fallback,
            )
        if re.search(r"这个|上面|原因|为什么|影响|展开|下跌|上涨|跌幅|涨幅", text):
            fallback = None if context else "请先查看今日行业日报，再围绕日报内容继续追问。"
            return self._result(
                "daily_report",
                "DAILY_REPORT" if context else "UNKNOWN_OR_INCOMPLETE",
                "DAILY_REPORT_DETAIL_QUESTION" if context else "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.92 if context else 0.58,
                context_ref,
                fallback=fallback,
            )
        if re.search(r"日报|今日行情|今天行情|读一下|来一份", text):
            result = self._result("daily_report", "DAILY_REPORT", "DAILY_REPORT_READ", slots, 0.98, context_ref, render_daily=True)
            result["daily_report_query"] = date_query.as_dict()
            return result
        return self._result(
            "daily_report",
            "FALLBACK",
            "OUT_OF_SCOPE",
            slots,
            0.72,
            context_ref,
            fallback="当前处于行业日报模块。请查询今日日报、政策、降价、新车、数据口径或历史日报。",
        )

    @staticmethod
    def _pure_geography_knowledge_route(
        text: str,
        selected_module: str,
        slots: Dict[str, Any],
        semantic_resolution: Any | None,
    ) -> Dict[str, Any] | None:
        if not re.search(r"省会|省城|首府|在哪里|是哪(?:里|个城市)|属于哪个省|哪个省的", text):
            return None
        if re.search(r"估价|报价|多少钱|收车|卖车|行情|选品|库存|周转|日报|报告|值得收|推荐|哪些车", text):
            return None
        city = slots.get("city") or getattr(semantic_resolution, "slots", {}).get("city") if semantic_resolution else slots.get("city")
        result = build_intent_result(
            selected_module=selected_module,
            business_category="GENERAL_AUTOMOTIVE_QA",
            internal_intent="GENERAL_AUTOMOTIVE_QA",
            confidence=0.98,
            slots=slots,
            reason="纯地理知识问答，不创建估价或行情任务",
        )
        result["knowledge_query"] = {
            "type": "geography",
            "resolved_city": city,
            "ask_vehicle_location_confirmation": bool(city),
        }
        return result

    def _classify_market(
        self,
        text: str,
        slots: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = state.get("lastMarketOpportunityContext") or state.get("last_market_opportunity_context") or {}
        context_ref = {
            "type": "last_market_opportunity" if context else None,
            "id": context.get("state_id"),
        }
        def finish(result: Dict[str, Any]) -> Dict[str, Any]:
            self._clean_enterprise_scope_slots(text, result.get("slots") or slots)
            internal = str(result.get("internal_intent") or "")
            detail = classify_selection_detail_intent(
                text,
                slots=result.get("slots") or slots,
                internal_intent=internal,
                has_context=bool(context),
            )
            detail_intent = str(detail.get("selection_detail_intent") or "")
            selectionish = (
                self._is_selection_request_text(text, result.get("slots") or slots)
                or detail_intent in {
                    "selection.entity_resolution",
                    "selection.explain_exclusion",
                    "selection.explain_rank_score",
                    "selection.signal_rule",
                }
                or internal in {
                "MARKET_OPPORTUNITY_RECOMMEND",
                "MARKET_RISK_QUERY",
                "MARKET_REASON_QUERY",
                "MARKET_PRICE_BUCKET_QUERY",
                "MARKET_SERIES_COMPARE",
                "COMPOUND_SELECTION_PRICING",
                }
            )
            if not selectionish:
                return result
            result.update(detail)
            if result.get("selected_module") == "market_state":
                result["module_intent"] = "car_selection"
                result["task_intent"] = detail.get("selection_task_intent") or result.get("task_intent")
                if str(detail.get("selection_detail_intent", "")).startswith("out_of_scope"):
                    result["business_category"] = "FALLBACK"
                    result["internal_intent"] = "OUT_OF_SCOPE"
                    result["should_render_market_card"] = False
            return result

        if re.search(r"(?:风险|避免|推荐|机会|排名|排序).*(?:怎么算|如何计算|计算逻辑|公式|权重|占比)", text):
            return finish(self._result(
                "market_state",
                "MARKET_STATE",
                "MARKET_REASON_QUERY",
                slots,
                0.98,
                context_ref,
                render_market=True,
                reason="识别为选品资格、排序或风险规则解释",
            ))
        if re.search(r"数据来源|数据口径|怎么算|指标口径|数据范围", text):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_DATA_SCOPE_QUERY", slots, 0.96, context_ref, render_market=True))
        if re.search(r"对比|比较|差异|哪个更值得|谁更值得", text) and len(slots.get("comparison_series") or []) >= 2:
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_SERIES_COMPARE", slots, 0.97, context_ref, render_market=True))
        if re.search(r"行情报告|生成.*报告|市场报告", text):
            intent = "COMPOUND_MARKET_REPORT_ADVICE" if re.search(r"收车建议|经营建议|怎么收|建议收", text) else "MARKET_REPORT_QUERY"
            return finish(self._result("market_state", "MARKET_STATE", intent, slots, 0.97, context_ref, render_market=True))
        if re.search(r"值得收|推荐|机会车系", text) and re.search(r"收车价|建议价格|价格区间|定价|估价", text):
            return finish(self._result("market_state", "MARKET_STATE", "COMPOUND_SELECTION_PRICING", slots, 0.97, context_ref, render_market=True))
        if re.search(r"换成|城市改成|改看|再看|切到", text) and slots.get("city"):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_CITY_CHANGE", slots, 0.98, context_ref, render_market=True))
        if re.fullmatch(r"(?:看)?(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|长春|全国)(?:行情)?(?:看看)?", text.strip()):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_CITY_CHANGE", slots, 0.96, context_ref, render_market=True))
        if re.search(r"为什么推荐|为什么说|为什么不建议|为什么.*不在.*推荐|不在.*选品|不在.*推荐|这个车系风险|机会分|第一个", text):
            has_subject = bool(slots.get("brand") or slots.get("series") or slots.get("raw_vehicle_text"))
            can_answer_without_context = self._is_selection_reason_text(text) and has_subject
            fallback = None if (context or can_answer_without_context) else "请先生成一份城市行情结果，再追问推荐或风险原因。"
            return finish(self._result(
                "market_state",
                "MARKET_STATE" if (context or can_answer_without_context) else "UNKNOWN_OR_INCOMPLETE",
                "MARKET_REASON_QUERY" if (context or can_answer_without_context) else "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.94 if (context or can_answer_without_context) else 0.6,
                context_ref,
                render_market=bool(context or can_answer_without_context),
                fallback=fallback,
            ))
        if re.search(r"不要收|不建议收|风险大|跌得厉害|急跌|阴跌|库存压力|周转慢|避开", text):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_RISK_QUERY", slots, 0.97, context_ref, render_market=True))
        if re.search(r"库存|周转|清库|成交周期|库存周期", text):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_INVENTORY_QUERY", slots, 0.96, context_ref, render_market=True))
        if slots.get("price_bucket") or re.search(r"价格段|万以内|万以上", text):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_PRICE_BUCKET_QUERY", slots, 0.96, context_ref, render_market=True))
        if re.search(r"推荐|值得收|哪些车值得|有机会|热门车系|流动性好|优先关注", text):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_OPPORTUNITY_RECOMMEND", slots, 0.97, context_ref, render_market=True))
        if slots.get("series"):
            return finish(self._result("market_state", "MARKET_STATE", "MARKET_STATE_QUERY", slots, 0.95, context_ref, render_market=True))
        return finish(self._result("market_state", "MARKET_STATE", "MARKET_STATE_QUERY", slots, 0.88, context_ref, render_market=True))

    def _classify_media(
        self,
        text: str,
        slots: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        quote = state.get("current_pricing_result") or state.get("last_price_result") or {}
        quote_id = quote.get("quote_id") or quote.get("request_id") if isinstance(quote, dict) else None
        context_ref = {"type": "active_quote" if quote else None, "id": quote_id}
        history_match = self._match_history_vehicle_identity(text, state)
        has_history = bool(state.get("vehicle_history") or state.get("quote_history") or state.get("pricing_history"))
        has_history_reference_word = bool(
            re.search(r"这台|这辆|当前|刚才(?:的)?|那台|那辆|之前(?:的)?|前面(?:的)?|第一|第二|第三|上一|前一", text)
        )
        has_quote_question = bool(re.search(r"价格|报价|区间|候选|证据|解释|为什么|怎么|多少钱", text))
        if (has_history_reference_word and (history_match or has_history)) and has_quote_question:
            return self._result(
                "media_pricing",
                "PRICING_QA",
                "HISTORY_VEHICLE_REFERENCE",
                slots,
                0.97,
                {
                    "type": "quote_history",
                    "id": history_match.get("quote_id") if history_match else None,
                    "history_index": history_match.get("history_index") if history_match else None,
                },
                reason="用户按车辆身份引用历史报价对象",
            )
        if re.search(r"故意报低|吓他|改成比模型|给领导看|包装成|不要按模型|不按模型", text):
            return self._result("media_pricing", "FALLBACK", "OUT_OF_SCOPE", slots, 0.97, context_ref)
        if (
            quote
            and slots.get("user_given_price_yuan") not in (None, "")
            and re.search(r"按.{0,12}收|这个价|这价格|收进来|拿下", text)
            and re.search(r"赚|亏|利润|毛利|划算|合算|能不能做|可不可以做", text)
        ):
            result = self._result("media_pricing", "PRICING_QA", "PURCHASE_PRICE_JUDGEMENT", slots, 0.99, context_ref)
            result["pricing_task"] = "C2B"
            result["pricing_advice_mode"] = "judge_purchase_price_delta"
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_purchase_price"
            result["reason"] = "基于当前有效报价试算指定收车价的净毛利和追价边界，不重新调用定价模型"
            return result
        if quote and (
            re.search(
                r"价格不准|报价不准|不准确|不合理|有偏差|不靠谱|同款车别人|别人卖|市场不是|"
                r"(?:网上|瓜子|懂车帝|汽车之家|人人车|优信|车商|市场).*(?:卖|挂|成交|报价)|"
                r"(?:其他机构|别家|同行).*(?:报价|给价|出价|给(?:了)?我?\s*\d)|"
                r"同款.*(?:比你|更)(?:高|低)|成交价.*(?:比你|更)(?:高|低)|收进来.*亏|肯定亏",
                text,
            )
            or (
                re.search(r"收车价|售车价|卖车价|挂牌价|报价|价格", text)
                and re.search(r"偏高|太高|高了|偏低|太低|低了", text)
                and not re.search(r"为什么|为啥|为何|原因|怎么会", text)
            )
        ):
            return self._result(
                "media_pricing",
                "PRICING_QA",
                "PRICE_FEEDBACK_CLARIFICATION",
                slots,
                0.99,
                context_ref,
                reason="用户质疑已有报价，先确认价格角色、偏差方向和参照，不重新估价",
            )
        if quote and re.search(
            r"(?:车况.*(?:很好|非常好|特别好).*(?:精品|高价)|按精品车(?:报|算|估)|"
            r"精品车.*(?:报|算|估))",
            text,
        ):
            return self._result(
                "media_pricing",
                "PRICING_QA",
                "PRICE_EXPLANATION_REQUEST",
                slots,
                0.98,
                context_ref,
                reason="用户希望仅凭口头车况描述上调车况等级，需要验车边界说明",
            )
        if re.search(r"只有照片|只有图片|看照片|看图片|照片.*估|图片.*估", text):
            return self._result("media_pricing", "MEDIA_VALUATION", "VEHICLE_INFO_ADD", slots, 0.9, context_ref)
        if quote and re.search(r"为什么低置信|低置信|为什么人工|为什么不自动|置信度.*(?:不高|低|原因|为什么)|估值.*置信", text):
            return self._result("media_pricing", "PRICING_QA", "WHY_LOW_CONFIDENCE", slots, 0.98, context_ref)
        if quote and re.search(
            r"置信|确定吗|准不准|为什么.*差|收车价.*售车价|售车价.*收车价|这个价格是|怎么得出|如何得出|"
            r"客户嫌低|怎么说|话术|最高.*(?:追|收)|最多.*(?:出|收)|收车上限|边界|底线|依据|解释|为什么|为啥|怎么算|输出字段",
            text,
        ):
            return self._result("media_pricing", "PRICING_QA", "PRICE_EXPLANATION_REQUEST", slots, 0.98, context_ref)
        if self._is_batch_pricing_text(text):
            result = self._result("media_pricing", "MEDIA_VALUATION", "BATCH_PRICE_QUOTE", slots, 0.97, context_ref)
            result["pricing_task"] = "BOTH" if re.search(r"收售|收/卖|收车.*卖车|都给", text) else "C2B"
            result["module_intent"] = "pricing"
            result["task_intent"] = "estimate_vehicle_batch_value"
            return result
        if quote and re.search(r"(?:再|还能?|如果)?(?:往上)?加\s*[0-9一二三四五六七八九十百千万.]+\s*(?:万|千|元)?", text) and re.search(r"能不能收|可以收|可不可以收|还能收|行不行|值不值", text):
            match = re.search(r"加\s*([0-9]+(?:\.[0-9]+)?)\s*(万|千|元)?", text)
            delta_yuan = 0.0
            if match:
                delta_yuan = float(match.group(1))
                unit = match.group(2) or "元"
                if unit == "万":
                    delta_yuan *= 10000
                elif unit == "千":
                    delta_yuan *= 1000
            ladder = quote.get("price_ladder") or ((quote.get("appraiser_decision_record") or {}).get("final_price_ladder_yuan")) or {}
            current_c2b = (
                ladder.get("expected_c2b_yuan")
                or quote.get("final_price")
                or (quote.get("price") or {}).get("point")
                or 0
            )
            result_slots = dict(slots)
            if current_c2b and delta_yuan:
                result_slots["user_given_price_yuan"] = float(current_c2b) + delta_yuan
            result = self._result("media_pricing", "PRICING_QA", "PURCHASE_PRICE_JUDGEMENT", result_slots, 0.99, context_ref)
            result["pricing_task"] = "C2B"
            result["pricing_advice_mode"] = "judge_purchase_price_delta"
            result["price_delta_yuan"] = delta_yuan
            result["base_purchase_price_yuan"] = float(current_c2b or 0)
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_purchase_price"
            result["reason"] = "基于当前有效报价试算加价后的收车边界，不重新调用定价模型"
            return result
        if re.search(r"能不能收|可不可以收|收这个价|这个价能收|最高能收|收高了|收贵了", text) and slots.get("user_given_price_yuan"):
            result = self._result("media_pricing", "MEDIA_VALUATION", "PURCHASE_PRICE_JUDGEMENT", slots, 0.98, context_ref)
            result["pricing_task"] = "C2B"
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_purchase_price"
            return result
        if re.search(r"客户(?:给|出|报价|还价)|客人(?:给|出|报价|还价)", text) and slots.get("user_given_price_yuan"):
            result = self._result("media_pricing", "MEDIA_VALUATION", "PRICE_QUOTE_REQUEST", slots, 0.97, context_ref)
            result["pricing_task"] = "B2C"
            result["pricing_advice_mode"] = "judge_customer_offer"
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_customer_offer"
            return result
        if re.search(r"挂|挂牌|上架|展板|对外价", text) and re.search(r"高不高|低不低|贵不贵|便宜不便宜|合适|行不行|能不能", text) and slots.get("user_given_price_yuan"):
            result = self._result("media_pricing", "MEDIA_VALUATION", "PRICE_QUOTE_REQUEST", slots, 0.97, context_ref)
            result["pricing_task"] = "B2C"
            result["pricing_advice_mode"] = "judge_listing_price"
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_listing_price"
            return result
        if re.search(r"最多(?:能)?(?:出|收)|最高(?:能)?(?:出|收)|顶格(?:出|收)|建议收车价|收车建议|出多少|给多少", text):
            result = self._result("media_pricing", "MEDIA_VALUATION", "PRICE_QUOTE_REQUEST", slots, 0.97, context_ref)
            result["pricing_task"] = "C2B"
            result["pricing_advice_mode"] = "recommend_purchase_price"
            result["module_intent"] = "pricing"
            result["task_intent"] = "recommend_purchase_price"
            return result
        if re.search(
            r"收售价|收车和卖车|卖车和收车|"
            r"收车价.*(?:售车价|卖车价|售价|卖价)|"
            r"(?:售车价|卖车价|售价|卖价).*收车价|"
            r"买入卖出|卖出买入",
            text,
        ):
            result = self._result("media_pricing", "MEDIA_VALUATION", "BOTH_PRICE_ADVICE", slots, 0.97, context_ref)
            result["pricing_task"] = "BOTH"
            result["module_intent"] = "pricing"
            result["task_intent"] = "estimate_vehicle_value"
            return result
        if re.search(r"售车价|建议卖价|建议售价|卖多少钱|挂多少|挂牌价|对外价", text):
            result = self._result("media_pricing", "MEDIA_VALUATION", "PRICE_QUOTE_REQUEST", slots, 0.98, context_ref)
            result["pricing_task"] = "B2C"
            result["pricing_advice_mode"] = "sale_price_advice"
            result["module_intent"] = "pricing"
            result["task_intent"] = "judge_listing_price"
            return result
        if re.search(r"写日报|生成日报", text):
            return self._result("media_pricing", "FALLBACK", "OUT_OF_SCOPE", slots, 0.94, context_ref)
        if re.search(r"调价|调低|调高|展板价|上架价|调价工单|批量预览", text):
            # The existing inventory/price-adjustment workflow remains the
            # owner of this task.  V2 deliberately yields so it cannot be
            # mistaken for a vehicle valuation merely because a brand appears.
            return self._result(
                "media_pricing",
                "UNKNOWN_OR_INCOMPLETE",
                "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.35,
                context_ref,
                reason="yield to existing deterministic price-adjustment workflow",
            )
        if re.search(r"换一辆车|重置(?:当前)?车辆|清空这辆|不估这辆", text):
            return self._result("media_pricing", "RESET_CONTEXT", "RESET_VEHICLE", slots, 0.98, context_ref, invalidate=True)
        history_match = self._match_history_vehicle_identity(text, state)
        has_history = bool(state.get("vehicle_history") or state.get("quote_history") or state.get("pricing_history"))
        has_history_reference_word = bool(
            re.search(r"这台|这辆|当前|刚才(?:的)?|那台|那辆|之前(?:的)?|前面(?:的)?|第一|第二|第三|上一|前一", text)
        )
        has_quote_question = bool(re.search(r"价格|报价|区间|候选|证据|解释|为什么|怎么|多少钱", text))
        if (has_history_reference_word and (history_match or has_history)) and has_quote_question:
            return self._result(
                "media_pricing",
                "PRICING_QA",
                "HISTORY_VEHICLE_REFERENCE",
                slots,
                0.97,
                {
                    "type": "quote_history",
                    "id": history_match.get("quote_id"),
                    "history_index": history_match.get("history_index"),
                },
                reason="用户按车辆身份引用历史报价对象",
            )
        if re.search(r"上一辆|前一辆|第一辆|第二辆|第三辆|刚才那辆|之前那辆", text):
            return self._result("media_pricing", "PRICING_QA", "HISTORY_VEHICLE_REFERENCE", slots, 0.96, {"type": "quote_history", "id": None})
        if re.search(r"对比|比较(?!合适|合理|好|划算|稳)|哪辆更|哪个给价高|谁给价高|哪个报价高|哪个价格高|这两辆|两台车", text):
            return self._result("media_pricing", "MEDIA_VALUATION", "MULTI_VEHICLE_COMPARE", slots, 0.9, context_ref)
        if re.search(r"候选证据|候选车|可比车|查看.*证据|参考了哪些|相似成交|证据是什么|证据有哪些|用了哪些.*车|哪些.*候选", text):
            return self._result("media_pricing", "PRICING_QA", "CANDIDATE_EVIDENCE_REQUEST", slots, 0.98, context_ref)
        if re.search(r"为什么低置信|低置信|为什么人工|为什么不自动|置信度.*(?:不高|低|原因|为什么)|估值.*置信", text):
            return self._result("media_pricing", "PRICING_QA", "WHY_LOW_CONFIDENCE", slots, 0.98, context_ref)
        if re.search(
            r"价格不准|报价不准|不准确|不合理|有偏差|不靠谱|同款车别人|别人卖|市场不是|"
            r"(?:网上|瓜子|懂车帝|汽车之家|人人车|优信|车商|市场).*(?:卖|挂|成交|报价)|"
            r"(?:其他机构|别家|同行).*(?:报价|给价|出价|给(?:了)?我?\s*\d)|"
            r"同款.*(?:比你|更)(?:高|低)|成交价.*(?:比你|更)(?:高|低)|收进来.*亏|肯定亏",
            text,
        ):
            return self._result(
                "media_pricing",
                "PRICING_QA" if quote else "UNKNOWN_OR_INCOMPLETE",
                "PRICE_FEEDBACK_CLARIFICATION" if quote else "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.97 if quote else 0.62,
                context_ref,
                reason="价格反馈必须绑定当前有效报价" if quote else "当前没有可供反馈的有效报价",
                fallback=None if quote else "当前没有有效报价。请先完成一辆车的估价，再反馈具体哪个价格不准。",
            )
        if re.search(r"为什么|为啥|怎么来的|怎么得出|如何得出|怎么算|解释|价格逻辑|这个价|偏高|偏低", text):
            fallback = None if quote else "请先完成一辆车的估价，再查看价格解释和候选证据。"
            return self._result(
                "media_pricing",
                "PRICING_QA" if quote else "UNKNOWN_OR_INCOMPLETE",
                "PRICE_EXPLANATION_REQUEST" if quote else "UNKNOWN_OR_INCOMPLETE",
                slots,
                0.97 if quote else 0.62,
                context_ref,
                fallback=fallback,
            )
        if re.search(r"推荐.*二手车|找车|看二手|有没有.*车", text):
            return self._result("media_pricing", "FALLBACK", "BUY_CAR_INTENT", slots, 0.96, context_ref)
        if re.search(r"我要买|想买|买一辆|买一台", text):
            return self._result("media_pricing", "FALLBACK", "BUY_CAR_INTENT", slots, 0.96, context_ref)
        if re.search(r"我想要一辆|我想要一台|我需要一辆|我需要一台", text):
            result = self._result(
                "media_pricing",
                "UNKNOWN_OR_INCOMPLETE",
                "BUSINESS_INTENT_CLARIFICATION",
                slots,
                0.68,
                context_ref,
                fallback="请确认你是要做收车估价、售车估价，还是查找可购买车源。",
            )
            result["secondary_intents"] = [
                "PRICE_QUOTE_REQUEST_C2B",
                "PRICE_QUOTE_REQUEST_B2C",
                "BUY_CAR_INTENT",
            ]
            return result
        if re.search(r"如果|假设|要是|换作", text) and any(
            slots.get(key) not in (None, "")
            for key in ("city", "mileage_km", "transfer_count", "color", "model_year", "first_license_year", "first_license_date")
        ):
            return self._result(
                "media_pricing",
                "PARAM_ADJUSTMENT",
                "VEHICLE_INFO_UPDATE",
                slots,
                0.96,
                context_ref,
                hypothetical=True,
                reason="识别为假设性参数变化，不直接覆盖当前车辆",
            )
        if quote and re.search(r"里程.*(?:改|从).*(?:降|影响|少多少|差多少)|颜色.*(?:改|换).*(?:影响|差多少)|过户.*(?:改|多|少).*(?:影响|差多少)", text):
            return self._result(
                "media_pricing",
                "PARAM_ADJUSTMENT",
                "VEHICLE_INFO_UPDATE",
                slots,
                0.96,
                context_ref,
                hypothetical=True,
                reason="识别为报价上下文参数敏感性问题，不覆盖当前车辆",
            )
        if re.search(r"不是|改成|修改|更正|纠正|换成|里程改|颜色换|过户改|年款换", text):
            return self._result(
                "media_pricing",
                "PARAM_ADJUSTMENT",
                "VEHICLE_INFO_UPDATE",
                slots,
                0.97,
                context_ref,
                invalidate=True,
            )
        if re.search(r"按.+重新算|按.+再算", text) and any(
            slots.get(key) not in (None, "")
            for key in ("city", "mileage_km", "transfer_count", "color", "model_year", "first_license_year", "first_license_date")
        ):
            return self._result(
                "media_pricing",
                "PARAM_ADJUSTMENT",
                "VEHICLE_INFO_UPDATE",
                slots,
                0.95,
                context_ref,
                invalidate=True,
            )
        if re.search(r"就这个|确认车型|确认款型|选第", text):
            return self._result("media_pricing", "MEDIA_VALUATION", "VEHICLE_CONFIRM", slots, 0.95, context_ref)
        if re.search(r"重新算|重新估|重新报价|再算一次", text):
            return self._result("media_pricing", "MEDIA_VALUATION", "PRICE_RECALCULATE", slots, 0.96, context_ref)
        if re.search(r"收车价|我要收|想收|收一个|收一辆|收一台|车商收|收多少钱", text):
            result = self._result(
                "media_pricing",
                "MEDIA_VALUATION",
                "PRICE_QUOTE_REQUEST",
                slots,
                0.97,
                context_ref,
            )
            result["pricing_task"] = "C2B"
            return result
        if re.search(r"销售价|售车价|售价|卖价|卖多少钱|我要卖|想卖|卖一辆|卖一台", text):
            result = self._result(
                "media_pricing",
                "MEDIA_VALUATION",
                "PRICE_QUOTE_REQUEST",
                slots,
                0.97,
                context_ref,
            )
            result["pricing_task"] = "B2C"
            return result
        vehicle_slots = sum(
            slots.get(key) not in (None, "")
            for key in (
                "brand",
                "series",
                "model_year",
                "first_license_year",
                "first_license_date",
                "trim",
                "city",
                "mileage_wan_km",
                "mileage_km",
                "transfer_count",
                "color",
            )
        )
        if re.search(r"估一下|估个价|估一估|估价|报个价|多少钱|能卖多少|收车价|售车价|值多少", text):
            return self._result("media_pricing", "MEDIA_VALUATION", "PRICE_QUOTE_REQUEST", slots, 0.96, context_ref)
        if self._looks_like_open_automotive_question(text, slots):
            return self._result(
                "media_pricing",
                "GENERAL_AUTOMOTIVE_QA",
                "GENERAL_AUTOMOTIVE_QA",
                slots,
                0.68,
                context_ref,
                reason="开放汽车/选购/品牌常识问题，进入受控问答，不直接估价",
            )
        if vehicle_slots:
            has_license_time = any(slots.get(key) not in (None, "") for key in ("first_license_year", "first_license_date", "reg_date"))
            complete = all(
                slots.get(key) not in (None, "")
                for key in ("series", "city", "mileage_wan_km", "transfer_count", "color")
            )
            complete = complete and has_license_time
            return self._result(
                "media_pricing",
                "MEDIA_VALUATION",
                "PRICE_QUOTE_REQUEST" if complete else "VEHICLE_INFO_ADD",
                slots,
                0.94 if complete else 0.9,
                context_ref,
            )
        return self._result(
            "media_pricing",
            "UNKNOWN_OR_INCOMPLETE",
            "UNKNOWN_OR_INCOMPLETE",
            slots,
            0.45,
            context_ref,
            fallback="请提供车型、上牌时间、里程、城市、过户次数和颜色，或说明要查看价格解释/候选证据。",
        )

    @staticmethod
    def _extract_enterprise_task_slots(text: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        slots: Dict[str, Any] = dict(extract_selection_category_constraints(text))
        price_match = re.search(
            r"(?<!\d)(\d+(?:\.\d+)?)\s*(万|万元|元)"
            r"(?=.{0,8}(?:收|卖|售|挂|挂牌|上架|展板|对外|报价|价格|能不能|可不可以|高不高|合适|行不行))",
            text,
        )
        if not price_match:
            price_match = re.search(
                r"(?:收|卖|售价|卖价|挂牌|挂牌价|挂|上架|展板|对外价|报价|价格|客户给|客户出|客人给|客人出)"
                r".{0,8}?(\d+(?:\.\d+)?)\s*(万|万元|元)",
                text,
            )
        if price_match:
            value = float(price_match.group(1))
            slots["user_given_price_yuan"] = round(value * 10000 if price_match.group(2) in {"万", "万元"} else value, 2)
        if re.search(r"E(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*E(?:级|评)?|泡水|火烧|调表", text, flags=re.I):
            slots["condition"] = "high_risk"
            slots["condition_group"] = "E"
            slots["inspection_grade"] = "E"
        elif re.search(r"D(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*D(?:级|评)?|重大事故|事故车|结构件事故", text, flags=re.I):
            slots["condition"] = "high_risk"
            slots["condition_group"] = "D"
            slots["inspection_grade"] = "D"
        elif re.search(r"C(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*C(?:级|评)?|一般车况|轻微瑕疵|多处喷漆", text, flags=re.I):
            slots["condition"] = "minor_defect"
            slots["condition_group"] = "C"
            slots["inspection_grade"] = "C"
        elif re.search(r"A(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*A(?:级|评)?|精品车况|准新车况|优秀车况", text, flags=re.I):
            slots["condition"] = "good"
            slots["condition_group"] = "A"
            slots["inspection_grade"] = "A"
        elif re.search(r"B(?:级车况|级评定|级检测|评级|评)|(?:车况|检测|评定|评级|等级)\s*[:：]?\s*B(?:级|评)?|车况良好|正常车况|无事故", text, flags=re.I):
            slots["condition"] = "good"
            slots["condition_group"] = "B"
            slots["inspection_grade"] = "B"
        if re.search(r"新能源|纯电|插混|混动|增程|BEV|EV|PHEV|EREV|DM-i", text, flags=re.I):
            slots["fuel_type"] = "新能源"
        elif re.search(r"燃油|油车|ICE", text, flags=re.I):
            slots["fuel_type"] = "燃油车"
        vehicle_type_match = re.search(r"SUV|MPV|轿车|家用车|代步车|B级车", text, flags=re.I)
        if vehicle_type_match:
            label = vehicle_type_match.group(0)
            slots["vehicle_type"] = {
                "suv": "SUV",
                "mpv": "MPV",
                "b级车": "B级车",
                "家用车": "家用车",
                "代步车": "代步车",
            }.get(label.lower(), label)
            if slots["vehicle_type"] in {"轿车", "SUV", "MPV"}:
                slots["vehicle_category"] = slots["vehicle_type"]
                slots["selection_filter"] = slots["vehicle_type"]
        if re.search(r"综合新能源|新能源|纯电|插混|混动|增程|电车", text, flags=re.I):
            slots["energy_filter"] = "新能源"
        elif re.search(r"\b全部\b|总计", text, flags=re.I):
            slots["selection_filter"] = "全部"
        brand_tier = extract_brand_tier_from_text(text)
        if brand_tier:
            slots["brand_tier"] = brand_tier
        band = re.search(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*(?:万|w)", text, flags=re.I)
        if band:
            low = float(band.group(1)) * 10000
            high = float(band.group(2)) * 10000
            slots["price_band"] = {"label": f"{band.group(1)}-{band.group(2)}万", "low": low, "high": high}
        elif re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)以内", text, flags=re.I):
            upper_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)以内", text, flags=re.I)
            upper = float(upper_match.group(1)) * 10000
            slots["price_band"] = {"label": f"{upper_match.group(1)}万以内", "low": None, "high": upper}
        elif re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)以上", text, flags=re.I):
            lower_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)以上", text, flags=re.I)
            lower = float(lower_match.group(1)) * 10000
            slots["price_band"] = {"label": f"{lower_match.group(1)}万以上", "low": lower, "high": None}
        elif re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)左右", text, flags=re.I):
            around_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)左右", text, flags=re.I)
            center = float(around_match.group(1)) * 10000
            slots["price_band"] = {"label": f"{around_match.group(1)}万左右", "low": center * 0.85, "high": center * 1.15}
        elif re.search(
            r"(\d+(?:\.\d+)?)\s*(?:万|w).{0,8}(?:机会|值得|推荐|适合|可收|能做|筛|优先)",
            text,
            flags=re.I,
        ):
            # Natural budget wording such as “17.5万有什么机会” is an
            # upper-budget selection constraint.  It is intentionally generic
            # for any numeric amount rather than a special case for 20/30万.
            budget_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:万|w)", text, flags=re.I)
            upper = float(budget_match.group(1)) * 10000
            slots["price_band"] = {
                "label": f"{budget_match.group(1)}万预算内",
                "low": None,
                "high": upper,
            }
        window = re.search(r"近?(\d+)\s*(天|日|周|个月|月)", text)
        if window:
            slots["time_window"] = window.group(0)
        if re.search(r"值得收|推荐|机会", text):
            slots["selection_target"] = "opportunity"
        elif re.search(r"不要收|不建议|风险|避开", text):
            slots["selection_target"] = "risk"
        if re.search(r"行情报告|市场报告", text):
            slots["report_type"] = "market_report"
        series = []
        for token in re.split(r"和|与|、|对比|比较|vs|VS", text):
            match = re.search(r"([A-Za-z\u4e00-\u9fff]+(?:\d|L|PLUS|Max|Pro|系|级|腾|瑞|阁|逸|朗|轩|豹|鸥|汉|唐|宋|Y|3)+)", token)
            if match:
                value = match.group(1).strip()
                if value and value not in series:
                    series.append(value)
        if len(series) >= 2:
            slots["comparison_series"] = series[:4]
        return slots

    @staticmethod
    def _clean_enterprise_scope_slots(text: str, slots: Dict[str, Any]) -> None:
        """Prevent scope words from becoming vehicle identity in market tasks.

        Queries such as “重庆 20万以内新能源哪些值得收” describe a city,
        price band and energy scope.  They should not be routed as a concrete
        vehicle just because the generic slot extractor saw “新能源” or “20万”.
        """
        if not text or not slots:
            return
        is_market_scope = bool(
            re.search(
                r"行情|选品|值得收|适合收|能做|哪些车|推荐|机会|风险|库存|周转|优先跟进|重点关注|重点看|"
                r"不建议|不在|没进|没出现|进榜|榜单|机会分|凭什么|排序|样本|低价|前五|前十|排名",
                text,
            )
            or bool(re.search(r"100%赚钱|别管数据|忽略回测|所有城市所有车系|售车转化", text))
            or slots.get("selection_target")
            or slots.get("price_band")
            or re.fullmatch(r"[\s，,。;；]*(?:全国|北京|上海|广州|深圳|重庆|成都|杭州|武汉|长春)?[\s，,。;；]*(?:全部|总计|综合新能源|新能源|SUV|MPV|轿车)[\s，,。;；]*", text or "", flags=re.I)
        )
        if not is_market_scope:
            return
        if re.search(r"DSI", text, flags=re.I):
            if str(slots.get("brand") or "").upper() == "DS":
                slots["brand"] = None
            if str(slots.get("series") or "").upper() == "DSI":
                slots["series"] = None
        generic_series = {"新能源", "新能源车", "燃油", "燃油车", "油车", "电车", "纯电", "插混", "混动", "二手车", "车", "SUV", "MPV", "轿车", "豪华", "家用车", "综合新能源"}
        series_text = str(slots.get("series") or "").strip()
        brand_text = str(slots.get("brand") or "").strip()
        if re.search(r"\d+(?:\.\d+)?%", text) and re.fullmatch(r"\d+(?:\.\d+)?", series_text):
            slots["series"] = None
            if brand_text and brand_text not in text:
                slots["brand"] = None
            series_text = ""
            brand_text = str(slots.get("brand") or "").strip()
        if (
            series_text in generic_series
            or series_text.upper() in generic_series
            or (brand_text in {"华凯", "北京"} and series_text in {"新能源", "U5"})
        ):
            slots["series"] = None
            if not re.search(r"奔驰|宝马|奥迪|丰田|本田|特斯拉|比亚迪|理想|蔚来|小鹏|问界|大众|日产|保时捷", text):
                slots["brand"] = None
            if str(slots.get("raw_vehicle_text") or "").strip() in generic_series:
                slots["raw_vehicle_text"] = None
        brand_text = str(slots.get("brand") or "").strip()
        series_text = str(slots.get("series") or "").strip()
        if re.fullmatch(
            r"(?:豪华|自主|合资|进口)?(?:新能源|纯电|插混|混动|增程|燃油)?(?:SUV|MPV|轿车|皮卡|微面|轻客|微卡|商务车)",
            series_text,
            flags=re.I,
        ):
            slots["series"] = None
            slots["trim"] = None
            slots["raw_vehicle_text"] = None
            series_text = ""
        normalized_query = re.sub(r"\s+", "", text).lower()
        if brand_text and re.sub(r"\s+", "", brand_text).lower() not in normalized_query:
            slots["brand"] = None
            brand_text = ""
        if series_text and re.sub(r"\s+", "", series_text).lower() not in normalized_query:
            slots["series"] = None
            slots["trim"] = None
            slots["raw_vehicle_text"] = None
            series_text = ""
        full_series_aliases = {
            ("宝马", "3系"): "宝马3系",
            ("宝马", "5系"): "宝马5系",
            ("小米", "SU7"): "小米SU7",
            ("理想", "L6"): "理想L6",
            ("理想", "L7"): "理想L7",
            ("理想", "L8"): "理想L8",
            ("岚图", "FREE"): "岚图FREE",
            ("领克", "07 EM-P"): "领克07 EM-P",
            ("领克", "07"): "领克07 EM-P",
            ("吉利", "ICON"): "吉利ICON",
            ("小鹏", "MONA M03"): "小鹏MONA M03",
            ("极氪", "7X"): "ZEEKR 7X",
        }
        if (brand_text, series_text) in full_series_aliases:
            slots["series"] = full_series_aliases[(brand_text, series_text)]
        if re.search(r"\d+(?:\.\d+)?\s*万以内|\d+(?:\.\d+)?\s*[-~—至到]\s*\d+(?:\.\d+)?\s*万", text) and not re.search(
            r"20\d{2}\s*(?:款|年|年款|上牌)",
            text,
        ):
            slots["model_year"] = None
        if slots.get("price_band") and re.search(r"值得收|选品|推荐|机会|风险|哪些车", text):
            slots["user_given_price_yuan"] = None
            if not re.search(r"20\d{2}\s*(?:年|[-/.])\s*\d{1,2}|上牌|登记|落户|初登|注册", text):
                for key in ("first_license_date", "first_license_year", "first_license_month", "reg_date"):
                    slots[key] = None

    @staticmethod
    def _canonicalize_selection_entity_slots(slots: Dict[str, Any]) -> None:
        """Use a stable display identity inside selection without changing pricing slots."""
        brand = str(slots.get("brand") or "").strip()
        series = str(slots.get("series") or "").strip()
        canonical = {
            ("宝马", "3系"): "宝马3系",
            ("宝马", "5系"): "宝马5系",
            ("极氪", "7X"): "ZEEKR 7X",
            ("岚图", "FREE"): "岚图FREE",
            ("小鹏", "MONA M03"): "小鹏MONA M03",
        }.get((brand, series))
        if canonical:
            slots["series"] = canonical

    @staticmethod
    def _is_batch_pricing_text(text: str) -> bool:
        return bool(
            re.search(
                r"同时估|批量估|多台|两台|两个.*(?:估|报价|价格)|2台|分别估|分别.*(?:估|报价|价格)|都要估|不要混|"
                r"[1１][）\\)].*[2２][）\\)]|\\bA\\b.*\\bB\\b|同一个.*两台|一台.*另一台",
                str(text or ""),
                flags=re.I,
            )
        )

    @staticmethod
    def _is_pricing_request_text(text: str) -> bool:
        return bool(
            re.search(
                r"估价|(?:帮我)?估(?:一下|个价|一估)|重新估|报价|多少钱|收车|收多少钱|卖车|卖多少钱|售价|售车价|值多少|候选证据|候选车|可比车|相似成交|"
                r"价格解释|价格怎么来的|调价|展板价|同时估|批量估|两台.*估|两个.*估|分别估|分别.*估|都要估|不要混|"
                r"只有照片|只有图片|看照片|看图片",
                str(text or ""),
            )
        )

    @staticmethod
    def _is_daily_request_text(text: str) -> bool:
        return bool(
            re.search(
                r"日报|今日报告|行业报告|降价榜|降价最多|降价品牌|降价车系|优惠最大|优惠最多|促销|"
                r"政策速递|政策.*影响|补贴.*影响|新车发布|新车上市|新车有哪些|新车.*改款|改款.*上市|预售|"
                r"行业动态|经营建议|全国榜单|价格波动榜",
                str(text or ""),
            )
        )

    @staticmethod
    def _is_market_request_text(text: str) -> bool:
        if classify_selection_query_family(str(text or ""), has_vehicle_entity=True):
            return True
        return bool(
            re.search(
                r"行情状态|行情选品|城市行情|值得收|适合收|推荐收|哪些车值得|哪些适合|能做|补库|"
                r"库存|周转|流动性|市场机会|机会车系|风险车系|暂缓收|别碰|避坑|"
                r"风险|机会分|推荐原因|为什么推荐|为什么不建议|选品推荐|为什么.*不在.*推荐|不在.*选品|"
                r"总利润|选中率|样本量|四项指标|baseline|DSI|排行榜.*有没有用|低价机会|捡漏|只适合看纯电|谁更适合做|"
                r"在前五|前十车系|排序依据|没进榜|进榜|误推|全用是不是更强|只准行情\+日报|政策单独|全信号|"
                r"内部行情.*DSI.*榜单.*日报|Excel表字段",
                str(text or ""),
                flags=re.I,
            )
        )

    @staticmethod
    def _is_selection_request_text(text: str, slots: Dict[str, Any] | None = None) -> bool:
        text = str(text or "")
        slots = slots or {}
        if not text:
            return False
        if (
            re.search(r"(?:是|属于|算)什么车|是啥车|什么车型|介绍一下.*车", text, flags=re.I)
            and not re.search(r"机会|推荐|值得|适合收|可收|能做|榜单|排名|第\s*[一二三四五六七八九十两\d]+", text)
        ):
            return False
        if classify_selection_query_family(
            text,
            has_vehicle_entity=bool((slots or {}).get("brand") or (slots or {}).get("series") or (slots or {}).get("trim")),
        ):
            return True
        if re.search(r"降价最多|降价榜|优惠最大|优惠最多|价格波动榜", text) and not re.search(
            r"选品|推荐收|值得收|适合收|避坑|风险|机会|样本|DSI",
            text,
            flags=re.I,
        ):
            return False
        if re.search(r"选品|值得收|适合收|推荐收|推荐几个车|SUV推荐|哪些车|什么车|机会车系|风险车系|暂缓收|别碰|避坑|补库|重点看|重点关注|优先跟进|优先看|优先收车|好不好做|能不能收|能做|方向|谁更适合做|谁更适合收|横向比较|只适合看纯电", text):
            return True
        if re.search(
            r"推荐\s*10\s*个|强行|别管数据|100%赚钱|所有城市所有车系|别筛条件|忽略回测|"
            r"最优推荐|就推荐|售车转化|成交周期长但利润低|周转慢无所谓|成交2辆.*重点关注",
            text,
            flags=re.I,
        ):
            return True
        if re.search(r"有推荐|推荐吗|值得做|值得看|不建议|不要主动|风险高|风险更低|容易亏|别追价|谁更稳|谁风险更低|谁更适合|怎么排|哪个更|对比|比较|周转更好|利润.*周转|价格带|价位|优先跟进", text):
            return True
        if re.search(r"机会分|样本量|样本可信|成交\s*\d+\s*(?:辆|台)|四项指标|总利润|选中率|低价机会|捡漏|为什么.*推荐|不在.*推荐|没进.*推荐|没进.*榜|没有.*推荐|数据没抓到|没出现|在前五|前十车系|排序依据|凭什么", text):
            return True
        if re.search(r"DSI|排行榜|热门榜|降价榜|销量榜|城市榜", text, flags=re.I) and re.search(r"推荐|收|避坑|机会|选品|有没有用|规则|一定|凭什么|影响|误推|结论|变差|效果", text):
            return True
        if re.search(r"回测|达标|baseline|基线|策略对照|ablation|market_only|market_daily|full_signal|信号|全信号|只用.*日报|不用日报|全用是不是更强|只准行情\+日报|政策单独|误推", text, flags=re.I):
            return True
        if re.search(r"数据质量|数据覆盖|覆盖率|映射|车型库|样本太少|字段|price[_ ]?band|匹配不上|英文和中文|同一个|数据来源|证据|排序依据|Excel表字段|强风险标签|分别是什么结论", text, flags=re.I):
            return True
        if re.search(r"只看|加上|不要|过滤|排序|按.*排|top\\s*\\d+|前\\s*\\d+", text, flags=re.I):
            return True
        if re.search(r"低于市场价|不能正常价|低价|高风险高机会|单车定价复核|不适合直接推荐", text):
            return True
        # “政策影响是什么”首先是日报/政策追问，不能仅因“影响”二字被误判为选品。
        # 只有同时出现明确的选品动作、排名或回测口径时，政策才进入选品链路。
        if re.search(r"新车|新款|上市|老款|政策|补贴|以旧换新", text) and re.search(
            r"选品|二手车推荐|收车|值得收|推荐|车系.{0,6}(?:排序|展示|排名)|排序|排名|回测|售车转化",
            text,
        ):
            return True
        if re.search(r"导出|报告|给领导|Excel|PPT|JSON|保存成规则|给Codex", text, flags=re.I) and re.search(r"选品|推荐|谨慎|低价机会|避坑|四项|总利润|策略|筛选条件|前端", text):
            return True
        if re.search(r"能做|方向", text) and (
            re.search(r"新能源|燃油|SUV|MPV|轿车|豪华|\d+\s*[-~—至到]?\s*\d*\s*万|全国|北京|上海|广州|深圳|重庆|成都|杭州|武汉", text, flags=re.I)
        ):
            return True
        if re.search(r"价格带|预算|价位", text) and re.search(r"机会|值得|太卷|能做", text):
            return True
        # Natural language may combine constraints that are not represented by
        # a single UI filter, for example “豪华新能源有什么机会” or
        # “8万左右自主轿车有哪些值得做”.  Once at least one genuine scope
        # constraint was extracted, “机会/推荐/值得” denotes cohort selection.
        if re.search(r"机会|推荐|值得|适合|可收|能做|优先", text) and any(
            slots.get(key) not in (None, "", {})
            for key in (
                "price_band",
                "brand_tier",
                "manufacturer_attribute",
                "fuel_type",
                "energy_subtype",
                "vehicle_type",
                "body_category",
                "selection_filter",
            )
        ):
            return True
        return False

    @staticmethod
    def _is_selection_ui_scope_text(
        text: str,
        selected_module: str,
        slots: Dict[str, Any] | None,
        client_state: Dict[str, Any] | None,
    ) -> bool:
        client_state = client_state or {}
        if selected_module != "market_state" and client_state.get("ui_module") != "selection":
            return False
        if client_state.get("ui_module") != "selection":
            return False
        if GlobalIntentClassifierV2._is_pricing_request_text(text):
            return False
        if GlobalIntentClassifierV2._is_daily_request_text(text):
            return False
        category = str(
            client_state.get("selectedBodyType")
            or client_state.get("selected_body_type")
            or client_state.get("selectedVehicleCategory")
            or client_state.get("selected_vehicle_category")
            or ""
        ).strip()
        energy = str(
            client_state.get("selectedEnergyType")
            or client_state.get("selected_energy_type")
            or ""
        ).strip()
        scope_text = re.sub(r"[，,。.!！?？；;\s]+", "", str(text or ""))
        for term in ("综合新能源", "自主燃油", "合资燃油", "豪华燃油", "新能源", "燃油车", "燃油", "油车", "自主", "合资", "豪华", "全部", "总计", "轿车", "SUV", "suv", "MPV", "mpv"):
            scope_text = scope_text.replace(term, "")
        city = str((slots or {}).get("city") or client_state.get("selectedCity") or "").strip()
        if city:
            scope_text = scope_text.replace(city, "")
        scope_text = scope_text.replace("全国", "").replace("市场", "").replace("榜", "")
        if (category and category not in {"全部", "总计"} or energy and energy not in {"全部", "总计"}) and not scope_text:
            return True
        return bool(not scope_text and re.search(r"全国|北京|上海|广州|深圳|重庆|成都|杭州|武汉|轿车|SUV|MPV|新能源|综合新能源|燃油车|燃油|自主燃油|合资燃油|豪华燃油", str(text or ""), flags=re.I))

    @staticmethod
    def _is_selection_reason_text(text: str) -> bool:
        if classify_selection_query_family(str(text or ""), has_vehicle_entity=True) in {
            "rank_lookup",
            "explain_exclusion",
        }:
            return True
        return bool(
            re.search(
                r"选品推荐|推荐里|为什么.*推荐|为什么.*不推荐|为什么.*不建议|为什么.*不在.*推荐|"
                r"不在.*选品|不在.*推荐|机会分|推荐原因",
                str(text or ""),
            )
        )

    @classmethod
    def _is_buy_request_text(cls, text: str) -> bool:
        return bool(
            re.search(
                r"我要买|想买|买一辆|买一台|找车|看二手|有没有.*车|推荐.*二手车|"
                r"\d+\s*万以内.*(?:车|二手车)|预算.*(?:车|二手车)",
                str(text or ""),
            )
        )

    @classmethod
    def _looks_like_cross_module_open_automotive_question(cls, text: str, slots: Dict[str, Any]) -> bool:
        if not text:
            return False
        # “第四名是什么车” contains the surface form “是什么车”, but it is
        # an ordinal lookup against the previous selection result, not a model
        # definition question.
        if classify_selection_query_family(
            text,
            has_vehicle_entity=bool(slots.get("brand") or slots.get("series") or slots.get("trim")),
        ) == "rank_lookup":
            return False
        if cls._is_selection_request_text(text, slots):
            return False
        if re.search(r"汽车新闻|行业新闻有哪些|今天.*新闻", text):
            return False
        model_definition = bool(
            re.search(r"(?:是|属于|算)什么车|是啥车|什么车型|介绍一下.*车", text, flags=re.I)
        )
        has_business_action = bool(
            re.search(r"值得收|适合收|推荐收|哪些车|哪几个|排名|榜单|行情|库存|周转|日报|估价|报价|多少钱", text)
        )
        if model_definition and not has_business_action and cls._looks_like_vehicle_or_auto_topic(text):
            return True
        if (
            cls._is_pricing_request_text(text)
            or cls._is_daily_request_text(text)
            or cls._is_market_request_text(text)
            or cls._is_buy_request_text(text)
        ):
            return False
        explicit_open_marker = bool(
            re.search(
                r"知道|知不知道|懂|懂不懂|了解|熟悉|介绍|讲讲|说说|听说过|听过|认识|科普|是什么|啥是|"
                r"区别|优缺点|适合|怎么选|推荐|有哪些|哪.*品牌|什么.*品牌|座驾|国家|产地|德系|日系|美系",
                text,
            )
        )
        if not explicit_open_marker:
            return False
        has_vehicle_slot = any(slots.get(key) not in (None, "") for key in ("brand", "series", "model_year", "trim"))
        automotive_terms = cls._looks_like_vehicle_or_auto_topic(text)
        return bool(has_vehicle_slot or automotive_terms)

    @staticmethod
    def _should_route_to_media_pricing(text: str, slots: Dict[str, Any]) -> bool:
        if not text:
            return False
        if classify_selection_query_family(
            text,
            has_vehicle_entity=bool(slots.get("brand") or slots.get("series") or slots.get("trim")),
        ):
            return False
        if re.search(r"带到估价|进入单车定价|转为单车定价|转成单车定价|转到估价", text):
            return False
        if re.search(r"值得收|适合收|推荐收|哪些车|什么车|机会车系|风险车系|暂缓收|别碰|避坑|补库|选品", text):
            if not re.search(r"这台|这辆|这车|客户这台|当前这台|收车价|收多少钱|多少钱收|能多少钱收|估价|报价|同时估|批量估|两台.*估|两个.*估|分别估|分别.*估|都要估|不要混", text):
                return False
        if re.search(r"日报|政策|榜单|排行|行情状态|行情选品|库存|周转", text) and not re.search(
            r"估价|报价|多少钱|收车|卖车|售价|收多少钱|卖多少钱|候选证据|价格解释|同时估|批量估|两台.*估|两个.*估|分别估|分别.*估|都要估|不要混",
            text,
        ):
            return False
        if re.search(
            r"估价|估一下|估个价|估一估|帮我估|报个价|报价|收车价|我要收|想收|收一辆|收一台|收一个|车商收|收多少钱|多少钱收|多少收|能多少钱收|"
            r"卖车|卖多少钱|多少钱卖|售价|售车价|值多少|"
            r"收/卖|收售建议|候选证据|候选车|可比车|相似成交|"
            r"价格解释|价格怎么来的|"
            r"挂出去|标价|怎么标|给客户看|对外价|展销价|同时估|批量估|两台.*估|两个.*估|分别估|分别.*估|都要估|不要混|"
            r"只有照片|只有图片|看照片|看图片",
            text,
        ):
            return True
        if re.search(r"怎么样|行情|日报|政策|榜单|排行|库存|周转|推荐|值得收|降价", text):
            return False
        vehicle_identity_count = sum(
            slots.get(key) not in (None, "")
            for key in ("brand", "series", "model_year", "trim")
        )
        vehicle_measure_count = sum(
            slots.get(key) not in (None, "")
            for key in ("city", "mileage_km", "mileage_wan_km", "transfer_count", "color")
        )
        # Cross-module auto-pricing is allowed for a full vehicle description
        # such as “2021款 宝马3系 5万公里 上海 1次过户 白色”.  A bare vehicle
        # mention like “宝马3系怎么样” remains owned by the current module.
        explicit_year = bool(
            re.search(r"(?:19|20)\d{2}\s*(?:年|款)?", text)
            or re.search(r"(?<![A-Za-z0-9])\d{2}\s*(?:年|年款|款)(?![A-Za-z0-9])", text)
        )
        return (vehicle_identity_count >= 2 and vehicle_measure_count >= 1) or (
            vehicle_identity_count >= 2 and explicit_year
        )

    @staticmethod
    def _looks_like_open_automotive_question(text: str, slots: Dict[str, Any]) -> bool:
        if not text:
            return False
        if re.search(
            r"估价|报价|多少钱|收车|收多少钱|卖车|卖多少钱|售价|售车价|值多少|候选证据|候选车|可比车|相似成交|"
            r"价格解释|价格怎么来的|调价|展板价|同时估|批量估|两台.*估|两个.*估|分别估|分别.*估|都要估|不要混",
            text,
        ):
            return False
        if re.search(r"日报|行情状态|行情选品|库存|周转|城市行情|降价榜|价格波动榜", text):
            return False
        has_vehicle_slot = any(slots.get(key) not in (None, "") for key in ("brand", "series", "model_year", "trim"))
        open_question = bool(
            re.search(
                r"推荐|有哪些|哪.*(?:品牌|车|车型|车系)|什么.*(?:品牌|车|车型|车系)|"
                r"知道|知不知道|懂|懂不懂|了解|熟悉|介绍|讲讲|说说|听说过|听过|认识|科普|是什么|啥是|"
                r"怎么样|如何|区别|优缺点|适合|买哪|怎么选|保值|油耗|空间|故障|"
                r"座驾|国家|产地|德系|日系|美系|国产|新能源|燃油",
                text,
            )
        )
        automotive_terms = GlobalIntentClassifierV2._looks_like_vehicle_or_auto_topic(text)
        return bool(open_question and (automotive_terms or has_vehicle_slot))

    @staticmethod
    def _looks_like_vehicle_or_auto_topic(text: str) -> bool:
        """Broad automotive topic detector for open Q&A.

        This intentionally complements structured vehicle matching.  Users ask
        short questions such as “你懂G63吗 / 奔驰300是什么 / RS6怎么样” where a
        catalogue lookup may not have resolved a unique trim yet.  Those are
        read-only automotive knowledge questions, not valuation completion.
        """
        text = str(text or "")
        if re.search(
            r"车|汽车|二手车|品牌|车系|车型|配置|款型|座驾|SUV|轿车|MPV|新能源|燃油|插混|纯电|混动|越野|性能车|跑车",
            text,
            flags=re.I,
        ):
            return True
        # Brand and sub-brand coverage is intentionally broad.  It is not used
        # to price a car; it only prevents open automotive questions from being
        # mistaken as incomplete valuation tasks.
        brand_terms = (
            r"奔驰|梅赛德斯|AMG|迈巴赫|宝马|MINI|劳斯莱斯|奥迪|保时捷|大众|宾利|兰博基尼|"
            r"丰田|本田|日产|雷克萨斯|英菲尼迪|讴歌|马自达|三菱|斯巴鲁|铃木|"
            r"别克|雪佛兰|凯迪拉克|林肯|福特|Jeep|道奇|特斯拉|"
            r"比亚迪|仰望|腾势|方程豹|蔚来|理想|小鹏|问界|赛力斯|鸿蒙智行|智界|享界|尊界|"
            r"极氪|领克|银河|吉利|几何|沃尔沃|极星|长城|哈弗|坦克|魏牌|欧拉|"
            r"长安|深蓝|阿维塔|启源|奇瑞|星途|捷途|iCAR|零跑|哪吒|岚图|猛士|东风|"
            r"广汽|传祺|埃安|五菱|宝骏|红旗|奔腾|荣威|名爵|智己|飞凡|上汽|"
            r"现代|起亚|捷尼赛思|路虎|捷豹|阿尔法罗密欧|玛莎拉蒂|法拉利|迈凯伦|阿斯顿马丁|路特斯"
        )
        if re.search(brand_terms, text, flags=re.I):
            return True
        # Performance/model shorthand: G63/E63/M5/RS6/911/U8/SU7/MEGA etc.
        model_code_patterns = (
            r"(?:AMG|M|RS|S|C|E|G|A|Q|X|GLA|GLB|GLC|GLE|GLS|CLA|CLS|SL|GT)\s*[-]?\s*\d{1,3}[A-Z]*|"
            r"(?:911|718|Panamera|Taycan|Cayenne|Macan|Model\s*[3YSX]|Cybertruck)|"
            r"(?:U8|U9|SU7|MEGA|L6|L7|L8|L9|ES6|ES8|ET5|ET7|EC6|M5|M7|M9|S9|R7)"
        )
        if re.search(model_code_patterns, text, flags=re.I):
            return True
        # Chinese nicknames or common product names that may not include brand.
        return bool(re.search(r"大G|小G|帕拉梅拉|卡宴|卡曼|牛魔王|海鸥|海豚|宋PLUS|秦PLUS|汉EV|唐DM|宏光MINI", text, flags=re.I))

    @staticmethod
    def _augment_open_qa_topic_slots(text: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        """Keep bare model-code questions usable as conversational context.

        A user may ask “你懂G63吗” without saying Mercedes.  We should not
        start a valuation task, but the response payload should still carry the
        detected topic so later follow-ups can reference it.
        """
        enriched = dict(slots or {})
        if any(enriched.get(key) not in (None, "") for key in ("brand", "series", "trim")):
            return enriched
        match = re.search(
            r"(AMG\s*[-]?\s*\d{1,3}[A-Z]*|"
            r"(?:M|RS|S|C|E|G|A|Q|X|GLA|GLB|GLC|GLE|GLS|CLA|CLS|SL|GT)\s*[-]?\s*\d{1,3}[A-Z]*|"
            r"911|718|Panamera|Taycan|Cayenne|Macan|Model\s*[3YSX]|Cybertruck|"
            r"U8|U9|SU7|MEGA|L6|L7|L8|L9|ES6|ES8|ET5|ET7|EC6|M5|M7|M9|S9|R7)",
            str(text or ""),
            flags=re.I,
        )
        if match:
            enriched["trim"] = re.sub(r"\s+", "", match.group(1)).upper()
        return enriched

    @staticmethod
    def _match_history_vehicle_identity(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
        compact = re.sub(r"[\s，。,.、/_-]+", "", str(text or "")).lower()
        history = state.get("vehicle_history") or []
        if not compact or not isinstance(history, list):
            return {}
        for index, item in reversed(list(enumerate(history))):
            if not isinstance(item, dict):
                continue
            slots = item.get("slots") or {}
            match = item.get("vehicle_match") or {}
            pricing = item.get("pricing_result") or item.get("price_result") or {}
            identities: list[str] = []
            for value in (
                slots.get("brand"),
                slots.get("series"),
                slots.get("trim"),
                match.get("brand_name"),
                match.get("series_name"),
                match.get("model_name"),
            ):
                normalized = re.sub(r"[\s，。,.、/_-]+", "", str(value or "")).lower()
                if len(normalized) >= 2 and normalized not in identities:
                    identities.append(normalized)
            if any(identity in compact for identity in identities):
                return {
                    "history_index": index,
                    "quote_id": pricing.get("quote_id") if isinstance(pricing, dict) else None,
                }
        return {}

    def _result(
        self,
        module: str,
        category: str,
        intent: str,
        slots: Dict[str, Any],
        confidence: float,
        context_reference: Dict[str, Any],
        *,
        hypothetical: bool = False,
        render_daily: bool = False,
        render_market: bool = False,
        invalidate: bool = False,
        fallback: str | None = None,
        reason: str = "",
        section: str | None = None,
    ) -> Dict[str, Any]:
        return build_intent_result(
            selected_module=module,
            business_category=category,
            internal_intent=intent,
            confidence=confidence,
            slots=slots,
            context_reference=context_reference,
            is_hypothetical=hypothetical,
            should_render_daily_report_card=render_daily,
            should_render_market_card=render_market,
            should_invalidate_quote=invalidate,
            fallback_message=fallback,
            reason=reason or f"{module} 模块确定性规则命中 {intent}",
            section=section,
        )

    def _explicit_module_switch(self, text: str, current_module: str) -> str | None:
        if not re.search(r"切换|切到|打开|进入|去看|转到|换到", text):
            return None
        compact = re.sub(r"\s+", "", text)
        for alias, module in MODULE_ALIASES.items():
            if alias in compact and module != current_module:
                return module
        return None
