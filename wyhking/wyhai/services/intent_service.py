from __future__ import annotations

import re
from typing import Any, Dict

from .intent_system import classify_intent


class IntentService:
    """Rule + structured slots intent classifier.

    The rules here provide deterministic business safety.  Qwen3 structured
    output can raise confidence, but it never directly triggers price calls.
    """

    PRICE_INTENTS = {
        "PRICE_ESTIMATE",
        "SELL_CAR_PRICE",
        "BUY_CAR_PRICE",
        "BOTH_PRICE",
    }

    def classify(self, message: str, extraction: Dict[str, Any], state: Dict[str, Any] | None = None) -> Dict[str, Any]:
        text = message or ""
        state = state or {}
        slots = extraction.get("slots") or {}
        deterministic = classify_intent(text, slots, state)
        if deterministic.get("type") not in {"OUT_OF_SCOPE"}:
            return deterministic
        llm_intent = ((extraction.get("llm_output") or {}).get("intent") or {}) if isinstance(extraction, dict) else {}
        has_vehicle_hint = any(
            (slots.get(k) or {}).get("value") not in {None, ""}
            for k in ["brand", "series", "model_year", "first_license_year", "mileage_wan_km", "city", "color", "transfer_count"]
        )
        has_context = bool(state.get("current_pricing_result") or state.get("current_slots"))

        if re.search(r"(价格不准|不准|不准确|不合理|有偏差|不靠谱|别人卖|市场不是|同款车别人)", text):
            return self._intent("FEEDBACK_INACCURATE", "UNKNOWN", 0.95, "用户反馈价格不准", "rule")
        if re.search(r"(偏高|太高|高了|贵了)", text):
            return self._intent("FEEDBACK_PRICE_TOO_HIGH", "UNKNOWN", 0.92, "用户反馈价格偏高", "rule")
        if re.search(r"(偏低|太低|低了|便宜了)", text):
            return self._intent("FEEDBACK_PRICE_TOO_LOW", "UNKNOWN", 0.92, "用户反馈价格偏低", "rule")
        if re.search(r"(解释|怎么来的|为什么|为啥|怎么算|依据|价格逻辑|价格接口失败)", text):
            reason = "用户追问已有报价依据" if has_context else "用户询问价格依据但缺少当前报价上下文"
            return self._intent("EXPLAIN_PRICE", "UNKNOWN", 0.9, reason, "rule")
        if re.search(r"(改成|修改|更正|不是|应该是|换成|重新算|按.+算|车型不是)", text) and (
            has_context or has_vehicle_hint
        ):
            return self._intent("UPDATE_FIELD", "UNKNOWN", 0.9, "用户补充或修改字段", "rule")
        if re.fullmatch(r"\s*重新估价\s*", text):
            return self._intent("PRICE_ESTIMATE", "UNKNOWN", 0.86, "用户请求重新估价", "rule")

        if re.search(
            r"(收售价|两个都要|都估|同时估|"
            r"收车价.*(?:销售价|售车价|卖车价|卖价)|"
            r"(?:销售价|售车价|卖车价|卖价).*收车价)",
            text,
        ):
            return self._intent("BOTH_PRICE", "BOTH", 0.94, "同时需要 C2B/B2C", "rule")
        if re.search(r"(收车|想收|我要收|收一个|车商收|拿车|收多少钱|收车价)", text):
            return self._intent("SELL_CAR_PRICE", "C2B", 0.94, "收车/C2B 估价请求", "rule")
        if re.search(r"(买一台|买一辆|想买|买车)", text):
            return self._intent("BUY_CAR_INTENT", "BUY", 0.92, "买车咨询，不触发估价", "rule")
        if re.search(r"(卖车|想卖|我要卖|卖多少钱|卖价|销售价|售价|挂牌价)", text):
            return self._intent("SELL_CAR_VALUATION_INTENT", "C2B", 0.9, "卖车/收车估价请求", "rule")
        if re.search(r"(重新估价|估价|估个价|多少钱|值多少|报价|能报多少|价格)", text) and (has_vehicle_hint or has_context):
            task = "UNKNOWN"
            if "task" in llm_intent and llm_intent.get("task") in {"C2B", "B2C", "BOTH"}:
                task = llm_intent["task"]
            return self._intent("PRICE_ESTIMATE", task, 0.86, "车辆估价请求", "rule")
        if has_vehicle_hint:
            return self._intent("PROVIDE_VEHICLE_INFO", "UNKNOWN", 0.8, "用户提供车辆字段", "rule")

        if llm_intent and llm_intent.get("type"):
            return {
                "type": llm_intent.get("type", "UNKNOWN"),
                "task": llm_intent.get("task", "UNKNOWN"),
                "confidence": float(llm_intent.get("confidence") or 0.5),
                "source": "llm",
                "reason": llm_intent.get("reason") or "Qwen3 structured output",
            }

        if not re.search(r"(车|价格|估价|报价|车型|品牌|里程|过户|收|卖|买|小米|宝马|奔驰|大众|问界)", text):
            return self._intent("OUT_OF_SCOPE", "UNKNOWN", 0.9, "与二手车估价无关", "rule")
        return self._intent("UNKNOWN", "UNKNOWN", 0.35, "无法稳定判断意图", "fallback")

    def _intent(self, intent_type: str, task: str, confidence: float, reason: str, source: str) -> Dict[str, Any]:
        return {
            "type": intent_type,
            "task": task,
            "confidence": confidence,
            "source": source,
            "reason": reason,
        }
