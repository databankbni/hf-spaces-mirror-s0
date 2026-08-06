from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional


SOURCE_ID_RE = re.compile(r"(?:车源号|车源ID|商品ID|ID)\s*([A-Za-z0-9-]{4,})", re.I)


DEMO_ACQUISITION_BIDS = [
    {
        "orderId": "SC-20260427-1008",
        "docType": "收车单",
        "city": "上海",
        "store": "上海虹桥体验店",
        "owner": "王凯",
        "evaluator": "张三",
        "status": "评估中",
        "title": "2021款 特斯拉Model 3 后轮驱动版",
        "brand": "特斯拉",
        "year": "2021",
        "regDate": "2021年8月",
        "mileage": "4.8万公里",
        "color": "红色",
        "tags": ["企业收车", "车辆报价", "新能源"],
        "dsi": "DSI持续走高",
        "vehicleSourceNo": "66621499",
        "plateNo": "沪A8T321",
        "vinLast4": "9K21",
        "acquisitionTime": "2026-04-27 10:20",
        "updatedAt": "2026-04-27 11:35",
        "remark": "客户希望今日完成收车价确认，需优先出价。",
        "ownerExpectedPrice": 25,
        "smartSalePrice": 25.69,
        "smartPurchasePrice": 24.89,
        "finalBidPrice": 10.50,
        "maxAcquisitionPrice": 10.50,
        "reasonablePriceRange": [11.38, 13.19],
        "excellentPriceMax": 10.53,
        "goodPriceMax": 11.38,
        "normalPriceMax": 13.19,
        "averagePriceMax": 13.99,
        "cityCompetitiveness": {"city": "洛阳", "lowerThanPercent": 100, "similarVehicleCount": None, "rank": 1},
        "nationalCompetitiveness": {"lowerThanPercent": 100, "similarVehicleCount": 9, "rank": 1},
        "turnoverEstimate": {"daysRange": "15~25天"},
    },
    {
        "orderId": "SC-20260427-1024",
        "docType": "收车单",
        "city": "北京",
        "store": "北京-东城",
        "owner": "赵明",
        "evaluator": "邓如意",
        "status": "待出价",
        "title": "2022款 宝马X3 xDrive25i M运动套装",
        "brand": "宝马",
        "year": "2022",
        "regDate": "2022年05月",
        "mileage": "3.7万公里",
        "color": "白色",
        "tags": ["企业收车", "家用车", "车辆报价"],
        "dsi": "DSI持续走低",
        "vehicleSourceNo": "66228018",
        "plateNo": "京A****8",
        "vinLast4": "8018",
        "acquisitionTime": "2026-04-27 12:10",
        "updatedAt": "2026-04-27 13:05",
        "remark": "同款供给增加，建议结合整备成本谨慎出价。",
        "ownerExpectedPrice": 25,
        "smartSalePrice": 25.69,
        "smartPurchasePrice": 24.89,
        "finalBidPrice": 10.50,
        "maxAcquisitionPrice": 10.50,
        "reasonablePriceRange": [11.38, 13.19],
        "excellentPriceMax": 10.53,
        "goodPriceMax": 11.38,
        "normalPriceMax": 13.19,
        "averagePriceMax": 13.99,
        "cityCompetitiveness": {"city": "洛阳", "lowerThanPercent": 100, "similarVehicleCount": None, "rank": 1},
        "nationalCompetitiveness": {"lowerThanPercent": 100, "similarVehicleCount": 9, "rank": 1},
        "turnoverEstimate": {"daysRange": "15~25天"},
    },
]


def parse_vehicle_source_lookup(message: str) -> Optional[Dict[str, str]]:
    text = (message or "").strip()
    if not text:
        return None
    match = SOURCE_ID_RE.search(text) or re.search(r"\b(\d{6,12})\b", text)
    if not match:
        return None
    source_id = match.group(1)
    wants_acquisition_bid = bool(re.search(r"(收车出价|收车价|收购价|收车定价|出价|收车单)", text))
    wants_adjustment = bool(re.search(r"(调价|销售价|挂牌价|降价|涨价|下调|上调)", text))
    if not wants_acquisition_bid and not wants_adjustment:
        return None
    return {
        "vehicle_source_no": source_id,
        "lookup_type": "acquisition_bid" if wants_acquisition_bid else "price_adjustment",
    }


def find_demo_acquisition_bid(vehicle_source_no: str) -> list[Dict[str, Any]]:
    source_no = str(vehicle_source_no or "").strip()
    return [item for item in DEMO_ACQUISITION_BIDS if str(item.get("vehicleSourceNo")) == source_no]


def build_vehicle_source_lookup_turn(
    *,
    session_id: str,
    turn_id: str,
    message: str,
    shortcut: Dict[str, str],
) -> Dict[str, Any]:
    source_no = shortcut["vehicle_source_no"]
    lookup_type = shortcut["lookup_type"]
    items = find_demo_acquisition_bid(source_no) if lookup_type == "acquisition_bid" else []
    matched = bool(items)
    if lookup_type == "acquisition_bid":
        if matched:
            first = items[0]
            reply = (
                f"已进入定价调价-查收车出价，并命中车源号 {source_no} 的收车单。"
                f"当前状态：{first.get('status', '-') }，智能收购价参考 {first.get('smartPurchasePrice', '-') } 万。"
            )
        else:
            reply = (
                f"已进入定价调价-查收车出价，但没有命中车源号 {source_no} 的收车单。"
                "请确认车源号，或接入实时工单库后再查询。"
            )
        intent_type = "ACQUISITION_BID_LOOKUP"
    else:
        reply = f"已进入定价调价-车源调价查询，车源号 {source_no} 暂未命中调价记录。"
        intent_type = "PRICE_ADJUSTMENT_LOOKUP"

    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "intent": {
            "type": intent_type,
            "task": "BUSINESS_WORKFLOW",
            "confidence": 0.99,
            "source": "rule",
            "reason": "车源号业务快捷查询，不进入六要素估价槽位补全",
        },
        "slots": {"vehicle_source_no": source_no, "business_lookup_type": lookup_type},
        "vehicle_match": {},
        "missing_fields": [],
        "quick_tags": [
            {
                "id": "source_lookup_again",
                "type": "business_shortcut",
                "label": "重新输入车源号",
                "payload": {"field": "vehicle_source_no"},
                "field": "vehicle_source_no",
                "priority": 10,
                "enabled": True,
            }
        ],
        "pricing": {
            "should_call_price": False,
            "called_price": False,
            "price_request": {},
            "price_result": {
                "workflow": "vehicle_source_lookup",
                "lookup_type": lookup_type,
                "vehicle_source_no": source_no,
                "matched": matched,
                "items": items,
                "source": "pricing_adjustment_shortcut",
            },
            "price_state": "business_lookup_matched" if matched else "business_lookup_not_found",
        },
        "reply": {"text": reply, "style": "business_lookup", "cards": []},
        "warnings": [] if matched else ["VEHICLE_SOURCE_NOT_FOUND"],
        "errors": [],
        "debug": {
            "enabled": False,
            "intent_source": "rule",
            "shortcut_router": "pricing_adjustment_shortcuts",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    }
