from __future__ import annotations

from typing import Any, Dict, List

from .intent_system import (
    BUY_CAR_INTENT,
    CANDIDATE_EVIDENCE_REQUEST,
    DAILY_REPORT_READ_INTENT,
    PRICE_ADJUSTMENT_INTENT,
    PRICE_EXPLANATION_REQUEST,
    REPORT_DETAIL_QUESTION,
    RESET_VEHICLE,
    WHY_LOW_CONFIDENCE,
)


class QuickTagService:
    def build(
        self,
        *,
        intent: Dict[str, Any],
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
        missing_fields: List[str],
        price_state: str,
    ) -> List[Dict[str, Any]]:
        tags: List[Dict[str, Any]] = []
        intent_type = intent.get("type")
        if intent_type == "BUSINESS_INTENT_CLARIFICATION":
            return [
                {
                    "id": "clarify_c2b",
                    "type": "clarify_business_intent",
                    "label": "做收车估价",
                    "payload": {"message": "我要收一辆车，做收车估价"},
                    "field": "task",
                    "priority": 1,
                    "enabled": True,
                },
                {
                    "id": "clarify_b2c",
                    "type": "clarify_business_intent",
                    "label": "做售车估价",
                    "payload": {"message": "我要卖一辆车，做售车估价"},
                    "field": "task",
                    "priority": 2,
                    "enabled": True,
                },
                {
                    "id": "clarify_buy",
                    "type": "clarify_business_intent",
                    "label": "查找可购买车源",
                    "payload": {"message": "我要找可购买的二手车"},
                    "field": "",
                    "priority": 3,
                    "enabled": True,
                },
                {
                    "id": "clarify_adjust",
                    "type": "clarify_business_intent",
                    "label": "做库存调价",
                    "payload": {"message": "我要做库存调价"},
                    "field": "",
                    "priority": 4,
                    "enabled": True,
                },
            ]
        if intent_type in {BUY_CAR_INTENT, PRICE_ADJUSTMENT_INTENT, DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION, RESET_VEHICLE}:
            return tags

        should_show_model_candidates = "vehicle_confirm" in (missing_fields or []) or "series" in (missing_fields or [])
        if should_show_model_candidates:
            for candidate in (vehicle_match or {}).get("candidates", [])[:6]:
                label = candidate.get("label") or " ".join(
                    str(candidate.get(k) or "") for k in ["brand", "series", "model_name"]
                ).strip()
                if label:
                    tags.append(
                        {
                            "id": f"model_{candidate.get('model_id') or label}",
                            "type": "select_model",
                            "label": label,
                            "payload": candidate,
                            "field": "model_id",
                            "priority": 10,
                            "enabled": True,
                        }
                    )

        common_values = {
            "city": ["重庆", "北京", "上海", "成都"],
            "mileage_wan_km": ["5万公里", "10万公里"],
            "transfer_count": ["0次过户", "1次过户"],
            "color": ["白色", "黑色", "灰色"],
        }
        labels = {
            "series": "补充车系/车型",
            "model_year": "补充年款",
            "trim": "补充具体款型/配置",
            "vehicle_confirm": "补充具体款型/配置",
            "year_disambiguation": "确认年款/上牌",
            "first_license_date": "补充上牌时间",
            "first_license_year": "补充上牌年份",
            "city": "补充城市",
            "mileage_wan_km": "补充公里数",
            "transfer_count": "补充过户次数",
            "color": "补充颜色",
        }
        provided = set(k for k, v in (slots or {}).items() if v not in (None, ""))
        for field in missing_fields:
            if field in provided:
                continue
            if field in {"trim", "vehicle_confirm"}:
                continue
            tags.append(
                {
                    "id": f"ask_{field}",
                    "type": "ask_field",
                    "label": labels.get(field, f"补充{field}"),
                    "payload": {"field": field},
                    "field": field,
                    "priority": 50,
                    "enabled": True,
                }
            )
            for idx, value in enumerate(common_values.get(field, [])):
                tags.append(
                    {
                        "id": f"fill_{field}_{idx}",
                        "type": "fill_field",
                        "label": value,
                        "payload": {"field": field, "value": value},
                        "field": field,
                        "priority": 60 + idx,
                        "enabled": True,
                    }
                )

        if price_state == "ready":
            tags.append(
                {
                    "id": "run_pricing",
                    "type": "run_pricing",
                    "label": "立即估价",
                    "payload": {},
                    "field": "",
                    "priority": 90,
                    "enabled": True,
                }
            )
        if price_state == "stale":
            tags.append(
                {
                    "id": "rerun_pricing",
                    "type": "run_pricing",
                    "label": "重新估价",
                    "payload": {},
                    "field": "",
                    "priority": 90,
                    "enabled": True,
                }
            )
        if str(intent_type or "").startswith("FEEDBACK"):
            tags.extend(
                [
                    {
                        "id": f"feedback_{role}_{direction}",
                        "type": "feedback",
                        "label": label,
                        "payload": {"feedback_type": f"{role}_{direction}", "message": label},
                        "field": "",
                        "priority": 20 + index,
                        "enabled": True,
                    }
                    for index, (role, direction, label) in enumerate(
                        [
                            ("purchase", "low", "收车价偏低"),
                            ("purchase", "high", "收车价偏高"),
                            ("sale", "low", "售车价偏低"),
                            ("sale", "high", "售车价偏高"),
                        ]
                    )
                ]
            )
            tags.append(
                {
                    "id": "feedback_add_evidence",
                    "type": "feedback_evidence",
                    "label": "补充真实成交案例",
                    "payload": {},
                    "field": "",
                    "priority": 25,
                    "enabled": True,
                }
            )
            return sorted(tags, key=lambda item: item.get("priority", 999))[:16]
        if intent_type in {PRICE_EXPLANATION_REQUEST, CANDIDATE_EVIDENCE_REQUEST, WHY_LOW_CONFIDENCE, "EXPLAIN_PRICE"}:
            tags.extend(
                [
                    {
                        "id": "feedback_high",
                        "type": "feedback",
                        "label": "价格偏高",
                        "payload": {"feedback_type": "too_high"},
                        "field": "",
                        "priority": 20,
                        "enabled": True,
                    },
                    {
                        "id": "feedback_low",
                        "type": "feedback",
                        "label": "价格偏低",
                        "payload": {"feedback_type": "too_low"},
                        "field": "",
                        "priority": 21,
                        "enabled": True,
                    },
                    {
                        "id": "manual_review",
                        "type": "manual_review",
                        "label": "申请人工复核",
                        "payload": {},
                        "field": "",
                        "priority": 22,
                        "enabled": True,
                    },
                ]
            )
        return sorted(tags, key=lambda item: item.get("priority", 999))[:16]
