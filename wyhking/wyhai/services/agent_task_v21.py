from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List
from .enterprise_capability_registry_v3 import contract_for


MODULE_LABELS = {
    "media_pricing": "定价",
    "market_state": "选品/行情状态",
    "daily_report": "行业日报",
}


def _non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _slot_summary(slots: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in (slots or {}).items()
        if _non_empty(value)
    }


def _first_license_value(slots: Dict[str, Any]) -> str:
    raw_date = str(slots.get("first_license_date") or slots.get("reg_date") or "").strip()
    year = slots.get("first_license_year")
    month = slots.get("first_license_month")
    if raw_date:
        parts = raw_date.replace("/", "-").split("-")
        if not year and parts and parts[0].isdigit():
            year = int(parts[0])
        if not month and len(parts) > 1 and parts[1].isdigit():
            month = int(parts[1])
    if year in (None, ""):
        return ""
    if month not in (None, ""):
        try:
            return f"{int(year)}-{max(1, min(12, int(month))):02d}"
        except Exception:
            pass
    return str(year)


def _slim_market_item(item: Dict[str, Any]) -> Dict[str, Any]:
    ratios = item.get("business_metric_ratios") if isinstance(item.get("business_metric_ratios"), dict) else {}
    return {
        "rank": item.get("rank"),
        "brand": item.get("brand"),
        "series": item.get("series"),
        "market_category": item.get("market_category"),
        "recommendation_label": item.get("recommendation_label"),
        "opportunity_score": item.get("opportunity_score"),
        "business_score": item.get("business_score"),
        "confidence_score": item.get("confidence_score"),
        "sold_count_90d": item.get("sold_count_90d"),
        "acquired_count_90d": item.get("acquired_count_90d"),
        "leader_metric_pass_count": item.get("leader_metric_pass_count"),
        "metric_ratios": {
            key: ratios.get(key)
            for key in ("avg_turnover_days", "avg_gross_profit", "sale_conversion_rate", "acquisition_conversion_rate")
            if ratios.get(key) is not None
        },
    }


def _pricing_steps(task_type: str, need_daily: bool = True) -> List[Dict[str, Any]]:
    return [
        {
            "step_id": "step_1",
            "tool": "price_book_tool",
            "purpose": "按标准车型、市场基线与七要素调用定价模型，生成这台车的收售价格锚点",
            "input_from": "slots",
            "required": True,
        },
        {
            "step_id": "step_2",
            "tool": "comparable_evidence_tool",
            "purpose": "核对可比车数量、相似程度和价格分布，说明市场基线",
            "input_from": "step_1",
            "required": True,
        },
        {
            "step_id": "step_3",
            "tool": "vehicle_adjustment_tool",
            "purpose": "逐项说明上牌、里程、城市、过户、颜色和车况如何修正基线",
            "input_from": "step_2",
            "required": True,
        },
        {
            "step_id": "step_4",
            "tool": "price_ladder_tool",
            "purpose": "生成并校验挂牌、实际售卖、实际收车、首报价和最高收车价的完整梯度",
            "input_from": "step_3",
            "required": True,
        },
        {
            "step_id": "step_5",
            "tool": "response_composer",
            "purpose": "把模型结果、七要素修正、可比证据和价格梯度整理为一线业务结论",
            "input_from": ["step_1", "step_2", "step_3", "step_4"],
            "required": True,
        },
    ]


class AgentTaskPlannerV21:
    """Task-card oriented planner for the enterprise Agent shell.

    This layer does not replace pricing/market/daily tools. It standardizes how
    every turn declares intent, slots, execution steps, tool status and cards so
    the frontend no longer has to infer business flow from free-form text.
    """

    def build_plan(
        self,
        *,
        module: str,
        intent_v2: Dict[str, Any],
        intent: Dict[str, Any],
        slots: Dict[str, Any],
        missing_fields: List[str],
        vehicle_match: Dict[str, Any],
        pricing: Dict[str, Any],
        daily_report_context: Dict[str, Any] | None = None,
        market_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        internal = intent_v2.get("internal_intent") or intent.get("type") or "UNKNOWN_OR_INCOMPLETE"
        pricing_task = intent_v2.get("pricing_task") or intent.get("task") or (slots or {}).get("task") or "UNKNOWN"
        price_role = self._price_role(internal, pricing_task)
        task_type = self._task_type(module, internal, price_role)
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        modules = self._modules_for_task(task_type)
        executable = not missing_fields and internal not in {"UNKNOWN_OR_INCOMPLETE", "OUT_OF_SCOPE"}
        need_confirmation = bool(
            price_role == "unknown_price"
            or internal in {"PRICE_ADJUSTMENT_INTENT", "BUSINESS_INTENT_CLARIFICATION"}
            or (pricing.get("price_result") or {}).get("review", {}).get("required")
        )
        if module == "media_pricing" and task_type.startswith("single_vehicle_pricing") and missing_fields:
            executable = False
        plan = {
            "schema_version": "agent_task_plan_v2_1",
            "task_id": task_id,
            "task_type": task_type,
            "task_goal": self._task_goal(task_type, slots, price_role, missing_fields),
            "runtime_module": module,
            "module_intent": intent_v2.get("module_intent") or self._enterprise_module_intent(module, internal),
            "task_intent": intent_v2.get("task_intent") or self._enterprise_task_intent(module, internal, pricing_task),
            "module_label": MODULE_LABELS.get(module, module),
            "business_intent": internal,
            "price_role": price_role,
            "intent_route": self._intent_route(
                intent_v2=intent_v2,
                intent=intent,
                module=module,
                task_type=task_type,
                price_role=price_role,
                can_execute=bool(executable),
                missing_fields=missing_fields,
            ),
            "modules": modules,
            "semantic_entities": intent_v2.get("semantic_entities") or intent_v2.get("semantic_constraints") or {},
            "slots": _slot_summary(slots),
            "vehicle_match": {
                "matched": bool(vehicle_match.get("matched")),
                "match_confidence": vehicle_match.get("match_confidence"),
                "brand_name": vehicle_match.get("brand_name"),
                "series_name": vehicle_match.get("series_name"),
                "model_name": None if vehicle_match.get("need_manual_confirm") else vehicle_match.get("model_name"),
                "model_year": vehicle_match.get("model_year"),
                "need_manual_confirm": bool(vehicle_match.get("need_manual_confirm")),
            },
            "missing_fields": list(missing_fields or []),
            "ambiguity": self._ambiguity(internal, price_role, missing_fields, vehicle_match),
            "execution_steps": self._execution_steps(task_type, internal, missing_fields),
            "can_execute": bool(executable),
            "need_user_confirmation": bool(need_confirmation),
            "vehicle_six_elements": self._six_elements(slots, vehicle_match),
            "safety_rules": [
                "LLM 不直接生成价格、供需指数或行情状态标签",
                "定价必须来自 price_book_tool / 现有 pricing engine",
                "价格解释只读取 quote_id 对应结果，不重新估价",
                "字段缺失或价格角色不明时只展示缺失项和结构化补全入口",
            ],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        plan["capability_contract"] = contract_for(task_type, internal)
        if daily_report_context:
            plan["daily_report_context_id"] = daily_report_context.get("report_id") or daily_report_context.get("filename")
        if market_context:
            plan["market_state_id"] = market_context.get("state_id")
        return plan

    def build_tool_results(
        self,
        *,
        plan: Dict[str, Any],
        pricing: Dict[str, Any],
        market_agent_card: Dict[str, Any] | None = None,
        daily_report_context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for step in plan.get("execution_steps", []):
            tool = step.get("tool")
            status = "not_run"
            result: Dict[str, Any] = {}
            warnings: List[str] = []
            if tool in {"valuation_tool", "price_book_tool"}:
                if pricing.get("called_price") and pricing.get("price_result"):
                    status = "success" if (pricing.get("price_result") or {}).get("success", True) else "failed"
                    price_result = pricing.get("price_result") or {}
                    result = {
                        "quote_id": price_result.get("quote_id") or price_result.get("request_id") or price_result.get("traceId"),
                        "final_price": price_result.get("final_price") or ((price_result.get("price") or {}).get("point")),
                        "confidence": price_result.get("confidence") or ((price_result.get("price_result") or {}).get("confidence")),
                        "candidate_count": len(price_result.get("selected_comparables") or []),
                    }
                elif pricing.get("price_state") in {"explain_ready", "predicted"} and pricing.get("price_result"):
                    status = "reused_context"
                    result = {"quote_id": (pricing.get("price_result") or {}).get("quote_id")}
                elif plan.get("runtime_module") != "media_pricing":
                    status = "skipped"
                    warnings.append("非定价模块不会调用估价工具")
                    result = {
                        "executed": False,
                        "skip_reason": "non_pricing_module",
                    }
                elif plan.get("missing_fields"):
                    status = "skipped"
                    warnings.append("缺少必要字段，未调用估价工具")
                    result = {
                        "executed": False,
                        "skip_reason": "seven_elements_incomplete",
                        "blocked_by": "vehicle_seven_element_gate",
                        "missing_fields": plan.get("missing_fields") or [],
                    }
            elif tool == "market_indicator_tool":
                if market_agent_card:
                    status = "success"
                    result = {
                        "city": market_agent_card.get("city"),
                        "recommendation_count": len(market_agent_card.get("recommendations") or []),
                        "data_time": market_agent_card.get("data_time") or market_agent_card.get("created_at"),
                    }
                else:
                    status = "available_as_context"
            elif tool == "market_state_tool":
                if market_agent_card:
                    status = "success"
                    result = {
                        "state_id": market_agent_card.get("state_id"),
                        "card_type": market_agent_card.get("card_type"),
                        "top_recommendations": [
                            _slim_market_item(item)
                            for item in (market_agent_card.get("recommendations") or [])[:3]
                        ],
                    }
                else:
                    status = "not_required"
            elif tool == "daily_report_tool":
                if daily_report_context:
                    status = "success"
                    result = {
                        "report_id": daily_report_context.get("report_id") or daily_report_context.get("filename"),
                        "report_date": daily_report_context.get("report_date"),
                        "source_type": daily_report_context.get("source_type") or "uploaded_report",
                    }
                else:
                    status = "not_loaded"
            elif tool == "selection_strategy_tool":
                if market_agent_card:
                    status = "success"
                    result = {
                        "recommendations": [
                            _slim_market_item(item)
                            for item in (market_agent_card.get("recommendations") or [])[:10]
                        ]
                    }
                else:
                    status = "blocked" if plan.get("runtime_module") == "market_state" else "not_required"
            elif tool == "semantic_resolution_tool":
                status = "success"
                result = {
                    "business_intent": plan.get("business_intent"),
                    "semantic_entities": plan.get("semantic_entities") or {},
                    "slots": plan.get("slots") or {},
                }
            elif tool == "controlled_llm_answer_tool":
                status = "success"
                result = {"policy": "no_price_generation_no_tool_side_effect"}
            elif tool == "intent_classifier":
                status = "success"
                result = {
                    "business_intent": plan.get("business_intent"),
                    "price_role": plan.get("price_role"),
                    "route": (plan.get("intent_route") or {}).get("route") or [],
                    "confidence": (plan.get("intent_route") or {}).get("confidence"),
                    "decision": (plan.get("intent_route") or {}).get("decision"),
                }
            elif tool == "slot_extraction_tool":
                status = "success"
                result = {
                    "recognized_slots": plan.get("slots") or {},
                    "vehicle_six_elements": plan.get("vehicle_six_elements") or {},
                }
            elif tool == "vehicle_seven_element_gate":
                if plan.get("missing_fields"):
                    status = "blocked"
                    warnings.append("七要素未补齐，定价模型未启动")
                else:
                    status = "success"
                result = {
                    "can_execute": bool(plan.get("can_execute")),
                    "missing_fields": plan.get("missing_fields") or [],
                }
            elif tool == "response_composer":
                status = "success"
            results.append(
                {
                    "tool_run_id": f"tool_{uuid.uuid4().hex[:10]}",
                    "step_id": step.get("step_id"),
                    "tool_name": tool,
                    "status": status,
                    "data_time": result.get("data_time") or datetime.now().date().isoformat(),
                    "granularity": self._granularity(tool, plan),
                    "coverage": result.get("coverage"),
                    "result": result,
                    "warnings": warnings,
                    "trace_id": plan.get("task_id"),
                }
            )
        return results

    def build_task_card(
        self,
        *,
        plan: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
        pricing: Dict[str, Any],
        reply: Dict[str, Any],
    ) -> Dict[str, Any]:
        price_result = pricing.get("price_result") or {}
        final_price = price_result.get("final_price") or ((price_result.get("price") or {}).get("point"))
        return {
            "card_type": self._card_type(plan.get("task_type")),
            "schema_version": "agent_task_card_v2_1",
            "task_id": plan.get("task_id"),
            "title": self._card_title(plan),
            "status": self._card_status(plan, pricing),
            "summary": reply.get("text") or "",
            "point_price": final_price,
            "confidence": price_result.get("confidence") or ((price_result.get("price_result") or {}).get("confidence")),
            "missing_fields": plan.get("missing_fields") or [],
            "tool_status": [
                {
                    "tool_name": item.get("tool_name"),
                    "status": item.get("status"),
                    "warnings": item.get("warnings") or [],
                }
                for item in tool_results
            ],
            "next_actions": self._next_actions(plan, pricing),
            "trace": {
                "task_id": plan.get("task_id"),
                "quote_id": price_result.get("quote_id") or price_result.get("request_id") or "",
                    "module": plan.get("runtime_module") or plan.get("module_intent"),
                "business_intent": plan.get("business_intent"),
            },
        }

    @staticmethod
    def _price_role(internal: str, pricing_task: Any) -> str:
        if internal == "GENERAL_AUTOMOTIVE_QA":
            return "no_price"
        if internal == "PURCHASE_PRICE_JUDGEMENT":
            return "purchase_price_judgement"
        if internal == "SALE_PRICE_ADVICE":
            return "listing_price"
        if internal == "BOTH_PRICE_ADVICE":
            return "market_value"
        if pricing_task == "C2B":
            return "purchase_price"
        if pricing_task == "B2C":
            return "listing_price"
        if pricing_task == "BOTH":
            return "market_value"
        if internal in {"PRICE_EXPLANATION_REQUEST", "PRICE_FEEDBACK_CLARIFICATION", "CANDIDATE_EVIDENCE_REQUEST", "WHY_LOW_CONFIDENCE"}:
            return "existing_quote_explanation"
        return "unknown_price"

    @staticmethod
    def _enterprise_module_intent(module: str, internal: str) -> str:
        if module == "media_pricing":
            return "pricing"
        if module == "daily_report":
            return "market_report"
        if module == "market_state":
            return "market_report" if "REPORT" in str(internal) else "car_selection"
        return "other"

    @staticmethod
    def _enterprise_task_intent(module: str, internal: str, pricing_task: Any) -> str:
        if module == "media_pricing":
            if internal == "PURCHASE_PRICE_JUDGEMENT":
                return "judge_purchase_price"
            if internal == "SALE_PRICE_ADVICE":
                return "judge_listing_price"
            if pricing_task == "B2C":
                return "judge_listing_price"
            return "estimate_vehicle_value"
        if module == "market_state":
            mapping = {
                "MARKET_OPPORTUNITY_RECOMMEND": "recommend_models",
                "MARKET_PRICE_BUCKET_QUERY": "recommend_price_band",
                "MARKET_CITY_CHANGE": "recommend_city_opportunity",
                "MARKET_RISK_QUERY": "identify_risky_models",
            }
            return mapping.get(str(internal), "model_market_report" if "REPORT" in str(internal) else "recommend_models")
        if module == "daily_report":
            return "model_market_report"
        return "other"

    @staticmethod
    def _task_type(module: str, internal: str, price_role: str) -> str:
        if internal == "COMPOUND_SELECTION_PRICING":
            return "compound_selection_pricing"
        if internal == "COMPOUND_MARKET_REPORT_ADVICE":
            return "compound_market_report_advice"
        if internal == "COMPOUND_PRICING_MARKET_EXPLANATION":
            return "compound_pricing_market_explanation"
        if module == "daily_report":
            return "market_report"
        if module == "market_state":
            return "car_selection_or_market_state"
        if internal == "GENERAL_AUTOMOTIVE_QA":
            return "general_automotive_qa"
        if internal in {"PRICE_EXPLANATION_REQUEST", "PRICE_FEEDBACK_CLARIFICATION", "CANDIDATE_EVIDENCE_REQUEST", "WHY_LOW_CONFIDENCE", "HISTORY_VEHICLE_REFERENCE"}:
            return "price_explanation"
        if internal == "BUSINESS_INTENT_CLARIFICATION":
            return "business_intent_clarification"
        if internal == "PRICE_ADJUSTMENT_INTENT":
            return "inventory_price_adjustment"
        if internal == "PURCHASE_PRICE_JUDGEMENT":
            return "single_vehicle_purchase_price_judgement"
        return f"single_vehicle_pricing_{price_role}"

    @staticmethod
    def _modules_for_task(task_type: str) -> List[str]:
        if task_type == "compound_selection_pricing":
            return ["car_selection", "pricing", "market_report"]
        if task_type == "compound_market_report_advice":
            return ["market_report", "car_selection", "pricing"]
        if task_type == "compound_pricing_market_explanation":
            return ["pricing", "market_report"]
        if task_type == "market_report":
            return ["market_report"]
        if task_type == "car_selection_or_market_state":
            return ["car_selection", "market_report"]
        if task_type == "general_automotive_qa":
            return ["general_automotive_qa"]
        if task_type == "price_explanation":
            return ["pricing"]
        if task_type == "inventory_price_adjustment":
            return ["pricing_adjustment"]
        return ["pricing"]

    @staticmethod
    def _task_goal(task_type: str, slots: Dict[str, Any], price_role: str, missing_fields: List[str] | None = None) -> str:
        series = slots.get("series") or slots.get("raw_vehicle_text") or "当前对象"
        city = slots.get("city") or "默认城市"
        if task_type == "market_report":
            return "读取并检索已上传行业日报"
        if task_type == "car_selection_or_market_state":
            return f"分析{city}二手车行情与选品机会"
        if task_type == "general_automotive_qa":
            return "回答汽车业务开放问题，并给出可进入的日报、行情或估价下一步"
        if task_type == "price_explanation":
            return "解释当前或历史报价的证据链"
        if task_type == "inventory_price_adjustment":
            return "处理库存/车源调价查询或工单筛选"
        role_text = {
            "purchase_price": "收车价",
            "listing_price": "售车价/挂牌价",
            "market_value": "收售综合价格",
            "unknown_price": "价格角色待确认",
        }.get(price_role, price_role)
        seven = [
            f"车型：{series}",
            f"上牌时间：{_first_license_value(slots) or '缺失'}",
            f"里程：{slots.get('mileage_wan_km') if slots.get('mileage_wan_km') not in (None, '') else '缺失'}万公里",
            f"城市：{slots.get('city') or '缺失'}",
            f"过户：{slots.get('transfer_count') if slots.get('transfer_count') not in (None, '') else '缺失'}次",
            f"颜色：{slots.get('color') or '缺失'}",
            f"车况：{slots.get('condition_group') or slots.get('inspection_grade') or slots.get('condition') or '缺失'}",
        ]
        if missing_fields:
            return f"识别到{role_text}意图；定价前置条件未满足，需补齐七要素后才能调用定价模型：" + "；".join(seven)
        return f"基于完整七要素执行{role_text}：" + "；".join(seven)

    @staticmethod
    def _six_elements(slots: Dict[str, Any], vehicle_match: Dict[str, Any]) -> Dict[str, Any]:
        brand = str(vehicle_match.get("brand_name") or slots.get("brand") or "").strip()
        series = str(vehicle_match.get("series_name") or slots.get("series") or "").strip()
        use_confirmed_match = bool(vehicle_match.get("matched") and not vehicle_match.get("need_manual_confirm"))
        trim = str((vehicle_match.get("model_name") if use_confirmed_match else None) or slots.get("trim") or "").strip()
        model_year = slots.get("model_year") or (vehicle_match.get("model_year") if use_confirmed_match else None)
        first_license_date = _first_license_value(slots)
        if trim and ((series and series in trim) or (brand and brand in trim)):
            identity = trim
        else:
            identity_parts = [series or brand]
            if brand and series and brand not in series:
                identity_parts.insert(0, brand)
            if trim:
                identity_parts.append(trim)
            identity = " ".join(part for part in identity_parts if part).strip()
        if model_year and str(model_year) not in identity:
            identity = f"{model_year}款 {identity}".strip()
        has_confirmed_standard_vehicle = bool(use_confirmed_match or trim or slots.get("vehicle_confirmed"))
        result = {
            "standard_vehicle": (identity or slots.get("raw_vehicle_text") or "") if has_confirmed_standard_vehicle else "",
            "model_year": model_year,
            "first_license_date": first_license_date,
            "first_license_year": slots.get("first_license_year"),
            "first_license_month": slots.get("first_license_month"),
            "mileage_wan_km": slots.get("mileage_wan_km"),
            "city": slots.get("city"),
            "transfer_count": slots.get("transfer_count"),
            "color": slots.get("color"),
            "condition_group": slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"),
        }
        if not has_confirmed_standard_vehicle:
            result["brand"] = brand or None
            result["series"] = series or None
        return result

    @staticmethod
    def _ambiguity(internal: str, price_role: str, missing_fields: List[str], vehicle_match: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if price_role == "unknown_price":
            items.append({"type": "PRICE_ROLE_UNKNOWN", "message": "价格角色不明确，需要确认收车价、售车价或客户报价"})
        if missing_fields:
            items.append({"type": "MISSING_FIELDS", "fields": missing_fields})
        if vehicle_match and not vehicle_match.get("matched"):
            items.append({"type": "VEHICLE_MODEL_UNCONFIRMED", "message": "车型库未精确确认，需用户或候选列表确认"})
        if internal == "BUSINESS_INTENT_CLARIFICATION":
            items.append({"type": "BUSINESS_INTENT_AMBIGUOUS", "message": "买/卖/收车口语需要确认业务动作"})
        return items

    @staticmethod
    def _intent_route(
        *,
        intent_v2: Dict[str, Any],
        intent: Dict[str, Any],
        module: str,
        task_type: str,
        price_role: str,
        can_execute: bool,
        missing_fields: List[str],
    ) -> Dict[str, Any]:
        route = ["global_intent_classifier_v2"]
        if intent.get("source") and intent.get("source") != "global_intent_v2":
            route.append(str(intent.get("source")))
        route.extend(["slot_extractor", "vehicle_model_normalizer", "pricing_request_builder"])
        decision = "ready_for_pricing_workflow" if can_execute else "blocked_before_pricing_workflow"
        if task_type in {"market_report", "car_selection_or_market_state", "general_automotive_qa"}:
            decision = "non_pricing_route"
        return {
            "route": route,
            "module": module,
            "task_type": task_type,
            "internal_intent": intent_v2.get("internal_intent") or intent.get("type"),
            "legacy_intent": intent.get("type"),
            "module_intent": intent_v2.get("module_intent"),
            "task_intent": intent_v2.get("task_intent"),
            "pricing_task": intent_v2.get("pricing_task") or intent.get("task"),
            "price_role": price_role,
            "confidence": intent_v2.get("confidence") if intent_v2.get("confidence") is not None else intent.get("confidence"),
            "should_call_pricing": bool(can_execute and task_type.startswith("single_vehicle_pricing")),
            "decision": decision,
            "blocked_by": list(missing_fields or []),
        }

    @staticmethod
    def _execution_steps(task_type: str, internal: str, missing_fields: List[str] | None = None) -> List[Dict[str, Any]]:
        if task_type.startswith("single_vehicle_pricing") and missing_fields:
            missing = "、".join(missing_fields)
            return [
                {
                    "step_id": "step_intent",
                    "tool": "intent_classifier",
                    "purpose": "识别用户业务意图、价格角色和是否属于单车估价",
                    "required": True,
                },
                {
                    "step_id": "step_slots",
                    "tool": "slot_extraction_tool",
                    "purpose": "抽取具体款型、上牌时间、里程、城市、过户、颜色和车况",
                    "required": True,
                },
                {
                    "step_id": "step_gate",
                    "tool": "vehicle_seven_element_gate",
                    "purpose": f"校验定价七要素；当前缺失：{missing}，因此不启动定价模型",
                    "required": True,
                },
                {
                    "step_id": "step_valuation",
                    "tool": "price_book_tool",
                    "purpose": f"七要素未补齐时显式跳过定价模型；缺失：{missing}，不生成价格",
                    "required": True,
                    "blocked_by": "vehicle_seven_element_gate",
                    "skip_policy": "seven_elements_incomplete",
                },
                {
                    "step_id": "step_final",
                    "tool": "response_composer",
                    "purpose": "生成缺失字段提示和结构化补全入口",
                    "required": True,
                },
            ]
        if task_type == "compound_selection_pricing":
            return [
                {"step_id": "step_1", "tool": "market_indicator_tool", "purpose": "读取城市/价格带/能源范围行情指标", "required": True},
                {"step_id": "step_2", "tool": "market_state_tool", "purpose": "生成机会与风险状态", "required": True},
                {"step_id": "step_3", "tool": "selection_strategy_tool", "purpose": "筛选值得收与谨慎收车系", "required": True},
                {"step_id": "step_4", "tool": "valuation_tool", "purpose": "对有完整单车要素的候选执行估价；否则输出历史成交参考带", "required": False},
                {"step_id": "step_5", "tool": "daily_report_tool", "purpose": "补充政策/降价/品牌事件风险", "required": False},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成可执行选品+定价任务卡", "required": True},
            ]
        if task_type == "compound_market_report_advice":
            return [
                {"step_id": "step_1", "tool": "market_indicator_tool", "purpose": "读取车型/城市/价格带指标", "required": True},
                {"step_id": "step_2", "tool": "market_state_tool", "purpose": "计算机会/风险标签", "required": True},
                {"step_id": "step_3", "tool": "daily_report_tool", "purpose": "检索日报事件证据", "required": False},
                {"step_id": "step_4", "tool": "selection_strategy_tool", "purpose": "形成经营建议", "required": True},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成行情报告与确认动作", "required": True},
            ]
        if task_type in {"compound_pricing_market_explanation", "single_vehicle_purchase_price_judgement"}:
            return _pricing_steps(task_type)
        if task_type == "general_automotive_qa":
            return [
                {"step_id": "step_1", "tool": "semantic_resolution_tool", "purpose": "解析开放表达、品牌派系、隐含实体和业务边界", "required": True},
                {"step_id": "step_2", "tool": "controlled_llm_answer_tool", "purpose": "在不调用估价的前提下生成受控业务回答", "required": False},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成问答卡和下一步动作", "required": True},
            ]
        if task_type == "market_report":
            return [
                {"step_id": "step_1", "tool": "daily_report_tool", "purpose": "读取上传日报或日报上下文", "required": True},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成日报证据卡和业务摘要", "required": True},
            ]
        if task_type == "car_selection_or_market_state":
            return [
                {"step_id": "step_1", "tool": "market_indicator_tool", "purpose": "读取城市/车系行情指标", "required": True},
                {"step_id": "step_2", "tool": "market_state_tool", "purpose": "判断行情状态与风险", "required": True},
                {"step_id": "step_3", "tool": "selection_strategy_tool", "purpose": "输出机会车系与风险车系", "required": True},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成选品任务卡", "required": True},
            ]
        if task_type == "price_explanation":
            return [
                {"step_id": "step_1", "tool": "valuation_tool", "purpose": "只读取现有 quote_id 的价格和证据，不重新估价", "required": True},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成证据解释卡", "required": True},
            ]
        if task_type == "inventory_price_adjustment":
            return [
                {"step_id": "step_1", "tool": "price_adjustment_lookup_tool", "purpose": "查询库存/车源调价工单或筛选条件", "required": False},
                {"step_id": "step_final", "tool": "response_composer", "purpose": "生成调价任务说明和缺失动作", "required": True},
            ]
        return _pricing_steps(task_type)

    @staticmethod
    def _granularity(tool: str, plan: Dict[str, Any]) -> str:
        slots = plan.get("slots") or {}
        if tool == "valuation_tool":
            return "single_vehicle"
        if slots.get("series") and slots.get("city"):
            return "model_city"
        if slots.get("series"):
            return "model"
        if slots.get("city"):
            return "city"
        return "global"

    @staticmethod
    def _card_type(task_type: str | None) -> str:
        if task_type in {"compound_selection_pricing", "compound_market_report_advice", "compound_pricing_market_explanation"}:
            return "compound_agent_task_card"
        if task_type == "market_report":
            return "daily_report_task_card"
        if task_type == "car_selection_or_market_state":
            return "market_selection_task_card"
        if task_type == "general_automotive_qa":
            return "general_automotive_qa_card"
        if task_type == "price_explanation":
            return "price_explanation_task_card"
        if task_type == "inventory_price_adjustment":
            return "price_adjustment_task_card"
        return "pricing_task_card"

    @staticmethod
    def _card_title(plan: Dict[str, Any]) -> str:
        mapping = {
            "compound_selection_pricing": "选品 + 定价任务",
            "compound_market_report_advice": "行情报告 + 经营建议任务",
            "compound_pricing_market_explanation": "定价 + 行情解释任务",
            "single_vehicle_purchase_price_judgement": "收车价判断任务",
            "market_report": "行业日报任务",
            "car_selection_or_market_state": "城市行情选品任务",
            "general_automotive_qa": "汽车业务问答",
            "price_explanation": "价格解释任务",
            "inventory_price_adjustment": "调价/工单任务",
        }
        return mapping.get(plan.get("task_type"), "车辆估价任务")

    @staticmethod
    def _card_status(plan: Dict[str, Any], pricing: Dict[str, Any]) -> str:
        if plan.get("missing_fields"):
            return "need_more_info"
        if pricing.get("called_price") and (pricing.get("price_result") or {}).get("success", True):
            return "completed"
        if plan.get("task_type") in {
            "market_report", "car_selection_or_market_state", "general_automotive_qa",
            "compound_selection_pricing", "compound_market_report_advice",
        }:
            return "completed"
        if plan.get("need_user_confirmation"):
            return "need_confirmation"
        return "ready"

    @staticmethod
    def _next_actions(plan: Dict[str, Any], pricing: Dict[str, Any]) -> List[Dict[str, Any]]:
        if plan.get("missing_fields"):
            return [
                {"action": "fill_missing_fields", "label": "补充缺失信息", "fields": plan.get("missing_fields")},
                {"action": "open_structured_form", "label": "表格填写"},
            ]
        if plan.get("task_type") == "price_explanation":
            return [{"action": "show_evidence_card", "label": "查看候选证据"}]
        if plan.get("task_type") == "car_selection_or_market_state":
            return [
                {"action": "drilldown_series", "label": "查看车系明细"},
                {"action": "start_pricing", "label": "对推荐车系估价"},
            ]
        if plan.get("task_type") == "compound_selection_pricing":
            return [
                {"action": "start_pricing", "label": "选择车系进入单车定价"},
                {"action": "add_watchlist", "label": "加入重点关注清单"},
                {"action": "export_report", "label": "导出选品策略"},
            ]
        if plan.get("task_type") == "compound_market_report_advice":
            return [
                {"action": "export_report", "label": "导出行情报告"},
                {"action": "switch_selection", "label": "转为选品任务"},
                {"action": "start_pricing", "label": "转为单车定价"},
            ]
        if plan.get("task_type") in {"compound_pricing_market_explanation", "single_vehicle_purchase_price_judgement"}:
            return [
                {"action": "accept_price", "label": "采纳建议价格"},
                {"action": "show_price_explanation", "label": "查看价格解释"},
                {"action": "reprice_with_modified_slots", "label": "修改参数重算"},
            ]
        if plan.get("task_type") == "general_automotive_qa":
            return [
                {"action": "switch_market_state", "label": "进入行情选品"},
                {"action": "switch_media_pricing", "label": "输入具体车辆估价"},
                {"action": "switch_daily_report", "label": "查看行业日报"},
            ]
        if pricing.get("called_price"):
            return [
                {"action": "show_price_explanation", "label": "查看价格解释"},
                {"action": "show_candidate_evidence", "label": "查看候选证据"},
                {"action": "reprice_with_modified_slots", "label": "修改参数重算"},
            ]
        return [{"action": "continue_task", "label": "继续任务"}]
