from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

from .daily_report_content_service import DailyReportContentService
from .c2b_from_b2c_spread_service import get_c2b_from_b2c_spread_service
from .b2c_three_source_calibration_service import get_b2c_three_source_calibration_service
from .third_party_listing_price_service import get_third_party_listing_price_service
from .llm_client import Qwen3LocalClient
from .market_opportunity_service import build_market_opportunity_response
from .market_state_data_loader import get_market_state_loader
from .pricing_ladder_completion import complete_legacy_business_ladder


WORKFLOW_VERSION = "enterprise_pricing_workflow_v2.3_pricebook"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _safe_json(value: Any) -> Any:
    return json.loads(json.dumps(_json_sanitize(value), ensure_ascii=False, default=str, allow_nan=False))


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


def _digest(value: Any) -> str:
    payload = json.dumps(_json_sanitize(value), ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _public_market_row(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "brand",
        "series",
        "city",
        "market_category",
        "category_basis",
        "price_change_7d",
        "price_change_14d",
        "price_change_30d",
        "deal_sample_90d",
        "deal_price_low_90d",
        "deal_price_high_90d",
        "deal_count",
        "listing_count",
        "sell_through_rate",
        "avg_deal_cycle",
        "current_inventory",
        "inventory_cycle",
        "price_cut_rate_30d",
        "lead_rate",
        "inquiry_conversion_rate",
        "search_volume",
        "detail_uv",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def _vehicle_identity(slots: Dict[str, Any]) -> str:
    brand = str(slots.get("brand") or "").strip()
    series = str(slots.get("series") or "").strip()
    trim = str(slots.get("trim") or "").strip()
    model_year = slots.get("model_year")
    parts = [series or brand]
    if brand and series and brand not in series:
        parts.insert(0, brand)
    if trim and trim not in " ".join(parts):
        parts.append(trim)
    identity = " ".join(part for part in parts if part).strip()
    if model_year and str(model_year) not in identity:
        identity = f"{model_year}款 {identity}".strip()
    return identity


def _money(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and number > 0 else 0.0


def _signed_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _price_yuan(value: Any) -> float:
    number = _money(value)
    if not number:
        return 0.0
    return number * 10000 if number < 1000 else number


def _price_wan(value: Any) -> float:
    number = _price_yuan(value)
    return round(number / 10000.0, 6) if number else 0.0


def _has_b2c_price(price_result: Dict[str, Any]) -> bool:
    if not isinstance(price_result, dict):
        return False
    if _price_yuan(price_result.get("b2cPrice") or price_result.get("b2c_price") or price_result.get("targetB2C")):
        return True
    tasks = price_result.get("tasks") if isinstance(price_result.get("tasks"), dict) else {}
    b2c_task = tasks.get("b2c") if isinstance(tasks.get("b2c"), dict) else {}
    if _price_yuan(b2c_task.get("point") or b2c_task.get("final_price")):
        return True
    return False


def _b2c_point(price_result: Dict[str, Any]) -> float:
    if not isinstance(price_result, dict):
        return 0.0
    price = price_result.get("price") if isinstance(price_result.get("price"), dict) else {}
    for value in (
        price_result.get("b2cPrice"),
        price_result.get("b2c_price"),
        price_result.get("targetB2C"),
        price_result.get("b2c_point"),
        price_result.get("b2c_final_price"),
        price.get("b2c_point") if isinstance(price, dict) else None,
    ):
        number = _price_yuan(value)
        if number:
            return number
    tasks = price_result.get("tasks") if isinstance(price_result.get("tasks"), dict) else {}
    b2c_task = tasks.get("b2c") if isinstance(tasks.get("b2c"), dict) else {}
    for value in (b2c_task.get("point"), b2c_task.get("final_price")):
        number = _price_yuan(value)
        if number:
            return number
    return 0.0


def _enforce_b2c_not_below_c2b(price_result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(price_result, dict):
        return price_result
    c2b_point = _price_point(price_result)
    b2c_point = _b2c_point(price_result)
    adjusted = dict(price_result)
    if b2c_point:
        adjusted["b2c_transaction_price_yuan"] = round(b2c_point, 2)
        adjusted["b2c_transaction_price_wan"] = _price_wan(b2c_point)
        adjusted["sale_price_role"] = "B2C_TRANSACTION_PRICE"
    if not c2b_point or not b2c_point or b2c_point > c2b_point:
        return adjusted
    minimum_gap = max(1_000.0, b2c_point * 0.03)
    capped_c2b = max(1_000.0, b2c_point - minimum_gap)
    c2b_range = adjusted.get("c2bRange") if isinstance(adjusted.get("c2bRange"), list) else []
    low = _price_yuan(c2b_range[0] if len(c2b_range) > 0 else None) or capped_c2b * 0.95
    high = _price_yuan(c2b_range[1] if len(c2b_range) > 1 else None) or capped_c2b * 1.05
    interval = adjusted.get("interval") if isinstance(adjusted.get("interval"), dict) else {}
    interval = dict(interval)
    interval["low"] = min(low, capped_c2b)
    interval["high"] = min(max(high, capped_c2b), b2c_point - 1.0)
    price_result_block = adjusted.get("price_result") if isinstance(adjusted.get("price_result"), dict) else {}
    price_result_block = dict(price_result_block)
    price_result_block.update(
        {
            "final_price": round(capped_c2b, 2),
            "price_low": interval["low"],
            "price_high": interval["high"],
        }
    )
    adjusted.update(
        {
            "final_price": round(capped_c2b, 2),
            "display_price_wan": _price_wan(capped_c2b),
            "c2bPrice": _price_wan(capped_c2b),
            "c2b_price": _price_wan(capped_c2b),
            "targetC2B": _price_wan(capped_c2b),
            "c2bRange": [_price_wan(interval["low"]), _price_wan(interval["high"])],
            "interval": interval,
            "price_result": price_result_block,
            "c2b_below_b2c_cap_applied": True,
            "c2b_pre_cap_price_yuan": round(c2b_point, 2),
            "c2b_b2c_minimum_gap_yuan": round(minimum_gap, 2),
            "c2b_price_warning": "C2B_PRICE_CAPPED_BELOW_B2C_TRANSACTION_PRICE",
        }
    )
    return adjusted


def _wan_text(value: Any) -> str:
    number = _money(value)
    if not number:
        return "暂无"
    wan = number / 10000 if number > 1000 else number
    return f"{wan:.2f}万".replace(".00万", "万")


def _price_point(price_result: Dict[str, Any]) -> float:
    price = price_result.get("price") or {}
    for value in (
        price_result.get("final_price"),
        price.get("point") if isinstance(price, dict) else None,
        price_result.get("c2bPrice"),
        price_result.get("c2b_point"),
        price_result.get("point_price"),
    ):
        number = _price_yuan(value)
        if number:
            return number
    return 0.0


def _price_range(price_result: Dict[str, Any], point: float) -> tuple[float, float]:
    price = price_result.get("price") or {}
    interval = price_result.get("price_interval") or price_result.get("interval") or price_result.get("range") or {}
    tuple_range = price_result.get("c2bRange") if isinstance(price_result.get("c2bRange"), list) else []
    lower = (
        _money(price.get("lower") if isinstance(price, dict) else None)
        or _money(tuple_range[0] if len(tuple_range) > 0 else None)
        or _money(interval.get("lower") if isinstance(interval, dict) else None)
        or _money(interval.get("low") if isinstance(interval, dict) else None)
        or _money(price_result.get("lower"))
        or _money(price_result.get("c2b_lower"))
    )
    upper = (
        _money(price.get("upper") if isinstance(price, dict) else None)
        or _money(tuple_range[1] if len(tuple_range) > 1 else None)
        or _money(interval.get("upper") if isinstance(interval, dict) else None)
        or _money(interval.get("high") if isinstance(interval, dict) else None)
        or _money(price_result.get("upper"))
        or _money(price_result.get("c2b_upper"))
    )
    if not lower and point:
        lower = point * 0.95
    if not upper and point:
        upper = point * 1.05
    return lower, upper


def _candidate_price(row: Dict[str, Any]) -> float:
    for key in (
        "converted_c2b_price",
        "c2b_price",
        "price_yuan",
        "listing_price_yuan",
        "transaction_price_yuan",
        "price",
        "b2c_price",
    ):
        value = _money(row.get(key))
        if value:
            return value
    return 0.0


def _selected_comparables(price_result: Dict[str, Any]) -> list[Dict[str, Any]]:
    evidence_card = price_result.get("evidence_card") if isinstance(price_result.get("evidence_card"), dict) else {}
    groups = [
        price_result.get("selected_comparables"),
        price_result.get("ref_cars"),
        price_result.get("comparables"),
        price_result.get("top_candidates"),
        evidence_card.get("selected_comparables"),
        evidence_card.get("top_comparables"),
        evidence_card.get("candidates"),
    ]
    for group in groups:
        if isinstance(group, list) and group:
            rows = [item for item in group if isinstance(item, dict)]
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
                key = (
                    str(row.get("vehicle_id") or row.get("listing_id") or row.get("clue_id") or "").strip(),
                    title,
                    str(row.get("model_year") or "").strip(),
                    round(_price_yuan(row.get("mileage_wan_km") or row.get("mileage")), 2),
                    str(row.get("city") or "").strip(),
                    str(row.get("transfer_count") or "").strip(),
                    round(_candidate_price(row), 0),
                    str(row.get("event_time") or row.get("data_date") or row.get("event_date") or "")[:10],
                )
                if key in seen:
                    continue
                seen.add(key)
                result.append(row)
            return result
    return []


def _match_basis(row: Dict[str, Any]) -> str:
    role = str(row.get("price_role") or "").upper()
    source = str(row.get("source") or "").strip()
    if role == "EXTERNAL_B2C_LISTING_CONSENSUS":
        return "第三方挂牌共识"
    if role == "EXTERNAL_B2C_LISTING":
        return source or "当前市场挂牌"
    raw = str(row.get("retrieval_level") or row.get("source_family") or "").lower()
    if "six" in raw or "exact" in raw or "same_trim_year" in raw:
        return "同款型/同年款"
    if "trim" in raw:
        return "同款型"
    if "series" in raw:
        return "同车系"
    if row.get("city"):
        return "同车系/相近城市"
    return "同车系可比"


def _candidate_impact(row: Dict[str, Any], point: float) -> str:
    price = _candidate_price(row)
    if not price or not point:
        return "用于补充同车系价格分布"
    ratio = price / point - 1
    if abs(ratio) <= 0.03:
        return "贴近建议价，支持当前价格锚点"
    if ratio > 0:
        return "高于建议价，说明高配/低里程样本存在上探空间"
    return "低于建议价，提醒谈判时保留安全边际"


def _adjustment_direction(label: str, slots: Dict[str, Any], candidates: list[Dict[str, Any]]) -> str:
    if not candidates:
        return "可比证据不足，暂不判断方向"
    try:
        if label == "里程":
            current = float(slots.get("mileage_wan_km"))
            values = [float(c.get("mileage_wan_km") or c.get("mileage")) for c in candidates if c.get("mileage_wan_km") or c.get("mileage")]
            if values:
                avg = sum(values) / len(values)
                if current < avg * 0.85:
                    return "当前里程低于可比车平均，对价格有支撑"
                if current > avg * 1.15:
                    return "当前里程高于可比车平均，对价格有压制"
        if label == "过户":
            current = float(slots.get("transfer_count"))
            values = [float(c.get("transfer_count")) for c in candidates if c.get("transfer_count") not in (None, "")]
            if values:
                avg = sum(values) / len(values)
                if current < avg:
                    return "过户次数不高，对价格有支撑"
                if current > avg:
                    return "过户次数高于部分可比车，谈判时需要留折让"
    except Exception:
        pass
    if label == "车型/款型":
        return "按标准车型和可比车证据确定基线，未单独编造修正金额"
    if label == "上牌时间":
        return "上牌时间用于计算车龄，新旧差异已进入估价引擎"
    if label == "城市":
        return "城市用于匹配本地成交和库存环境，影响价格边界"
    if label == "颜色":
        color = str(slots.get("color") or "")
        if color and color not in {"白色", "黑色", "灰色", "银色"}:
            return f"{color}相对主流色更依赖买家偏好，谈判时需关注接受度"
        return "主流颜色或影响较小，保持基线判断"
    return "方向不明确，不展示精确金额"


def _build_business_context(
    slots: Dict[str, Any],
    indicator: Dict[str, Any],
    market_state: Dict[str, Any],
    daily_report: Dict[str, Any],
    price_result: Dict[str, Any],
) -> Dict[str, Any]:
    point = _price_point(price_result)
    lower, upper = _price_range(price_result, point)
    candidates = _selected_comparables(price_result)
    candidate_prices = [_candidate_price(row) for row in candidates if _candidate_price(row)]
    baseline = _money((price_result.get("price_trace") or {}).get("baseline_p40")) or (
        sorted(candidate_prices)[len(candidate_prices) // 2] if candidate_prices else point
    )
    vehicle = _vehicle_identity(slots)
    count = len(candidates)
    confidence = str(price_result.get("confidence") or "MEDIUM").upper()
    confidence_text = {"HIGH": "高，证据充足", "MEDIUM": "中，按建议区间使用", "LOW": "低，按保守区间使用"}.get(confidence, "中，按建议区间使用")
    risk_items = list(market_state.get("risks") or [])
    if confidence in {"LOW", "MEDIUM"}:
        risk_items.append("本次置信度不是高，价格边界已按保守口径展示")
    if count < 5:
        risk_items.append("可比证据偏少，价格边界需保守使用")
    comparable_evidence = [
        {
            "vehicle": row.get("title") or row.get("vehicle") or "可比车辆",
            "match_basis": _match_basis(row),
            "price_yuan": _candidate_price(row),
            "condition": " · ".join(str(v) for v in (row.get("city"), row.get("model_year"), row.get("mileage_wan_km") or row.get("mileage")) if v not in (None, "")),
            "impact": _candidate_impact(row, point),
        }
        for row in candidates[:12]
    ]
    price_bridge = {
        "baseline_price_yuan": baseline,
        "baseline_label": "可比车基线价",
        "baseline_reason": (
            f"系统先用{count}条可比车辆形成市场基线，再结合当前车七要素和估价引擎输出建议价。"
            if count
            else "当前可比证据不足，基线主要依赖估价引擎和历史知识库。"
        ),
        "adjustments": [
            {"label": "车型/款型", "direction": "基本不变", "explanation": _adjustment_direction("车型/款型", slots, candidates)},
            {"label": "上牌时间", "direction": "已计入", "explanation": _adjustment_direction("上牌时间", slots, candidates)},
            {"label": "里程", "direction": "看具体差异", "explanation": _adjustment_direction("里程", slots, candidates)},
            {"label": "城市", "direction": "已计入", "explanation": _adjustment_direction("城市", slots, candidates)},
            {"label": "过户次数", "direction": "看具体差异", "explanation": _adjustment_direction("过户", slots, candidates)},
            {"label": "颜色", "direction": "轻微影响", "explanation": _adjustment_direction("颜色", slots, candidates)},
            {"label": "车况", "direction": "已计入", "explanation": f"{slots.get('condition_group') or slots.get('inspection_grade') or '车况等级'}已进入本次定价。"},
        ],
        "final_price_yuan": point,
        "amount_policy": "未收到 explicit adjustment_amount 时只展示影响方向，不编造精确修正金额。",
    }
    executive_summary = {
        "title": "本次估价结论",
        "one_sentence": (
            f"建议以 {_wan_text(point)} 作为谈判锚点，业务参考区间为 {_wan_text(lower)} - {_wan_text(upper)}。"
            if point
            else "当前未生成有效价格，请先补齐车辆七要素。"
        ),
        "why": f"本次价格基于定价模型、{count}条可比证据和当前车辆七要素共同确定；行情日报不参与单车定价。",
        "how_to_do": f"如果车况正常，可以围绕 {_wan_text(point)} 推进；如果发现事故、泡水、火烧、调表或重大维修，应下调或人工复核。",
        "risk": "；".join(dict.fromkeys(str(item) for item in risk_items if item)) or "暂无额外风险标签，仍需核验真实车况。",
    }
    action_guide = {
        "judgement": (
            f"建议以 {_wan_text(point)} 为收车价格锚点，最高不超过 {_wan_text(upper)}。"
            if point
            else "价格尚未生成，不建议推进收车决策。"
        ),
        "actions": [
            f"报价策略：以 {_wan_text(point)} 作为谈判锚点，超过 {_wan_text(upper)} 不建议继续追价。",
            "车况复核：重点确认事故、泡水、火烧、调表和核心部件维修记录。",
            "议价策略：如客户报价偏高，用可比车差异、颜色、里程和过户证据说明价格边界。",
            "库存策略：门店同类库存偏高时按区间下沿执行；线索活跃且车况优秀时可接近锚点。",
            "后续追踪：成交后记录真实收车价、整备成本和售卖价，用于校准定价模型。",
        ],
    }
    valuation_summary = {
        "purchase_price_note": "建议收车价用于业务谈判锚点，不等于最终成交价。",
        "range_note": "区间下沿适合保守收车，区间上沿是业务风险边界。",
        "confidence_note": confidence_text,
    }
    return {
        "vehicle_title": vehicle,
        "executive_summary": executive_summary,
        "valuation_summary": valuation_summary,
        "price_bridge": price_bridge,
        "action_guide": action_guide,
        "comparable_evidence": comparable_evidence,
        "business_output_contract": {
            "estimate_vehicle_value": ["建议挂牌价及区间", "预计实际售卖价及区间", "实际收车价及区间", "最高收车价", "七要素修正", "定价依据"],
            "judge_purchase_price": ["能不能收", "当前报价与建议价差距", "安全边界", "建议最高收车价", "下一步动作"],
            "recommend_purchase_price": ["保守价", "建议价", "最高价", "上探条件", "下调条件"],
            "judge_listing_price": ["挂牌是否偏高", "建议挂牌区间", "议价空间", "周转影响", "调价建议"],
            "judge_customer_offer": ["客户报价是否可接受", "市场差距", "毛利信息缺口", "接受/还价/暂不成交"],
            "recommend_price_adjustment": ["是否降价", "降多少", "为什么", "降价目标", "不降价风险", "观察指标"],
        },
    }


def _llm_business_copy(facts: Dict[str, Any]) -> Dict[str, Any]:
    client = Qwen3LocalClient()
    if not (client.config_snapshot().get("api_key_configured") and client.enable_rewrite):
        return {"enabled": False, "fallback_reason": "LLM not configured"}
    prompt = (
        "你是二手车一线业务助手。只根据输入事实改写中文业务话术，禁止编造价格、可比车、行情指标、日报事件或精确修正金额。"
        "输出 JSON，字段为 executive_summary_text、action_guide_text。"
    )
    result = client.structured_extract(prompt, {"facts": facts})
    if not result.ok:
        return {"enabled": False, "fallback_reason": result.fallback_reason, "latency_ms": result.latency_ms}
    try:
        parsed = json.loads(result.content)
    except Exception:
        parsed = {}
    return {
        "enabled": bool(parsed),
        "model": result.model,
        "latency_ms": result.latency_ms,
        "content": parsed,
    }


def _tool_business_explanation(
    tool_name: str,
    status: str,
    result: Dict[str, Any],
    tool_input: Dict[str, Any],
    warnings: list[str],
) -> Dict[str, Any]:
    """Translate tool output into frontline-business language.

    The factual data still comes from the underlying tool result. This helper
    only shapes that data into a stable contract the UI can render without
    exposing implementation names by default.
    """
    warning_text = "；".join(str(item) for item in warnings if item)
    if status in {"failed", "blocked"}:
        return {
            "conclusion": "这一步没有成功完成，暂不把它作为价格依据。",
            "evidence": [warning_text or "工具执行失败或被前置条件阻断"],
            "impact": "不改变本次价格，需业务复核后再推进。",
            "action": "先处理阻断原因，再重新估价。",
            "risk": "如果忽略该问题直接报价，可能误导收车判断。",
        }
    if status in {"skipped", "not_required", "not_loaded", "available_as_context"}:
        return {
            "conclusion": warning_text or "当前没有命中可直接使用的数据。",
            "evidence": ["工具已按条件检查，但没有可用结果"] if not warning_text else [warning_text],
            "impact": "不直接改变建议价，只提醒业务按保守边界使用结果。",
            "action": "继续使用已生成的价格和可比证据；证据不足时人工复核。",
            "risk": "外部背景不足，不能把这一步当作强依据。",
        }

    if tool_name == "market_indicator_tool":
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        city = result.get("city") or tool_input.get("city") or "当前城市"
        series = result.get("series") or tool_input.get("series") or "当前车型"
        matched = int(result.get("matched_rows") or 0)
        evidence = [
            f"对象：{city} · {series}",
            f"命中结构化行情记录：{matched} 条",
        ]
        if metrics.get("deal_sample_90d") not in (None, ""):
            evidence.append(f"近90天成交样本：{metrics.get('deal_sample_90d')} 辆")
        if metrics.get("listing_count") not in (None, ""):
            evidence.append(f"在售样本：{metrics.get('listing_count')} 辆")
        if metrics.get("avg_deal_cycle") not in (None, ""):
            evidence.append(f"平均成交周期：{metrics.get('avg_deal_cycle')} 天")
        return {
            "conclusion": f"已检查{city}{series}的结构化行情数据。",
            "evidence": evidence,
            "impact": "用于判断成交活跃度、库存压力和价格边界，不从日报里直接取数。",
            "action": "若样本充足，可把行情状态作为收车风险判断；样本不足时降低置信度。",
            "risk": warning_text or "行情指标只是市场背景，不能替代单车检测和可比车证据。",
        }

    if tool_name == "market_state_tool":
        reasons = [str(item) for item in (result.get("reasons") or []) if item]
        risks = [str(item) for item in (result.get("risks") or []) if item]
        label = result.get("recommendation_label") or result.get("market_category_label") or result.get("market_category") or "结合单车复核"
        return {
            "conclusion": f"行情判断：{label}。",
            "evidence": reasons[:4] or ["当前车型+城市行情样本不足，未形成强行情判断"],
            "impact": "行情状态只影响收车风险和谈判边界，不直接改写估价点位。",
            "action": result.get("action") or "结合车况、整备成本和门店库存再决定是否推进。",
            "risk": "；".join(risks[:3]) or warning_text or "暂无额外行情风险标签。",
        }

    if tool_name == "daily_report_tool":
        evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
        conclusions = [str(item) for item in (result.get("core_conclusions") or []) if item]
        snippets: list[str] = []
        for item in evidence[:3]:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("summary") or item.get("title") or "").strip()
            else:
                text = str(item).strip()
            if text:
                snippets.append(text[:96])
        return {
            "conclusion": f"已融合日报背景：{result.get('filename') or result.get('report_id') or '最新上传日报'}。",
            "evidence": snippets or conclusions[:3] or ["本轮没有检索到与该车强相关的日报片段"],
            "impact": "日报只补充政策、降价、新车冲击和品牌事件背景，不生成行情样本或模型价格。",
            "action": "若日报出现新车降价、品牌负面或政策变化，收车时按区间下沿或人工复核。",
            "risk": warning_text or "日报事件有时滞，不能替代当前成交和车况证据。",
        }

    if tool_name == "price_book_tool":
        point = _price_point(result)
        lower, upper = _price_range(result, point)
        candidates = _selected_comparables(result)
        return {
            "conclusion": f"定价模型已生成这台车的建议收车价：{_wan_text(point)}。",
            "evidence": [
                f"业务参考区间：{_wan_text(lower)} - {_wan_text(upper)}",
                f"可比证据：{len(candidates)} 条",
                f"模型置信度：{result.get('confidence') or 'MEDIUM'}",
            ],
            "impact": "这是本次报价的模型锚点；后续用可比证据、七要素和价格梯度解释并校验，不重复改价。",
            "action": f"围绕{_wan_text(point)}谈判，超过{_wan_text(upper)}需谨慎追价。",
            "risk": "若实际车况差于描述，应按检测结果下调或人工复核。",
        }

    if tool_name == "comparable_evidence_tool":
        count = int(result.get("comparable_count") or 0)
        comparables = result.get("comparables") if isinstance(result.get("comparables"), list) else []
        evidence = [
            f"{item.get('vehicle') or '可比车辆'}：{_wan_text(item.get('price_yuan'))}，{item.get('match_basis') or '同车系可比'}"
            for item in comparables[:4]
            if isinstance(item, dict)
        ]
        market_consensus = _money(result.get("market_consensus_yuan"))
        listing_consensus = _money(result.get("third_party_listing_yuan"))
        expected_c2b = _money(result.get("expected_c2b_yuan"))
        impact_parts = []
        if market_consensus:
            impact_parts.append(f"多源市场基线 {_wan_text(market_consensus)}")
        if listing_consensus:
            impact_parts.append(f"当前挂牌共识 {_wan_text(listing_consensus)}")
        if expected_c2b:
            impact_parts.append(f"结合本车七要素后建议收车 {_wan_text(expected_c2b)}")
        return {
            "conclusion": f"已核对 {count} 条可比车证据。",
            "evidence": evidence or ["当前没有足够可比车，系统已降低证据置信度"],
            "impact": "；".join(impact_parts) or "可比证据用于确定市场基线和价格分布，不直接照搬为本车报价。",
            "action": "证据少于5条时按保守边界谈判，并安排人工复核。",
            "risk": result.get("evidence_boundary") or "可比车必须与当前车款型和车况口径可比。",
        }

    if tool_name == "vehicle_adjustment_tool":
        adjustments = result.get("adjustments") if isinstance(result.get("adjustments"), list) else []
        evidence = [
            f"{item.get('label')}：{item.get('explanation')}"
            for item in adjustments[:7]
            if isinstance(item, dict) and item.get("label")
        ]
        local_pct = result.get("local_adjustment_percent")
        pct_text = ""
        if isinstance(local_pct, (int, float)):
            pct_text = f"模型记录的七要素局部修正系数为 {local_pct:+.2f}%；"
        return {
            "conclusion": "已逐项核对当前车七要素对价格的影响。",
            "evidence": evidence or ["七要素已进入定价模型，但上游未返回逐项解释"],
            "impact": f"{pct_text}修正后建议收车价为 {_wan_text(result.get('final_price_yuan'))}。",
            "action": f"按最终建议价 {_wan_text(result.get('final_price_yuan'))} 进入价格梯度校验。",
            "risk": result.get("amount_policy") or "没有可靠金额时只说明方向，不编造修正值。",
        }

    if tool_name == "price_ladder_tool":
        ladder = result.get("price_ladder") if isinstance(result.get("price_ladder"), dict) else {}
        if not ladder:
            return {
                "conclusion": "定价模型没有返回完整价格梯度，本轮不能伪造缺失价格。",
                "evidence": [str(result.get("warning") or "缺少售卖价或收车价角色")],
                "impact": "只展示定价模型已返回的价格，缺失角色标为不可用。",
                "action": "补齐定价模型输出后重新估价。",
                "risk": "价格角色不完整时直接补数会造成错误毛利判断。",
            }
        return {
            "conclusion": "完整价格梯度已生成并完成顺序校验。" if result.get("ordering_valid") else "价格梯度已生成，但顺序校验未通过。",
            "evidence": [
                f"建议挂牌价：{_wan_text(ladder.get('recommended_listing_yuan'))}",
                f"预计实际售卖价：{_wan_text(ladder.get('expected_b2c_transaction_yuan'))}",
                f"预计实际收车价：{_wan_text(ladder.get('expected_c2b_yuan'))}",
                f"最高收车价：{_wan_text(ladder.get('max_c2b_yuan'))}",
            ],
            "impact": "明确挂牌、售卖、收车和最高边界，避免一线混用价格角色。",
            "action": "只在最高收车价以内推进，实际成交优先围绕建议收车价谈判。",
            "risk": "顺序校验未通过时不得向一线展示为可执行报价。" if not result.get("ordering_valid") else "仍需核验实际整备成本和车况。",
        }

    if tool_name == "response_composer":
        executive = result.get("executive_summary") if isinstance(result.get("executive_summary"), dict) else {}
        action = result.get("action_guide") if isinstance(result.get("action_guide"), dict) else {}
        return {
            "conclusion": executive.get("one_sentence") or "已生成可给一线业务直接使用的估价结论。",
            "evidence": [executive.get("why") or "已整合定价模型、七要素和可比车证据"],
            "impact": "把价格结果转成各价格角色、谈判边界、定价依据与风险说明。",
            "action": action.get("judgement") or "按建议价谈判，按区间上沿控制追价风险。",
            "risk": executive.get("risk") or "仍需核验真实车况。",
        }

    return {
        "conclusion": "步骤已完成。",
        "evidence": ["结果已进入任务卡"],
        "impact": "作为本轮业务判断的辅助信息。",
        "action": "继续下一步。",
        "risk": warning_text or "暂无额外风险。",
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


class EnterprisePricingWorkflowV22:
    """Execute the auditable single-vehicle price-book chain.

    Selection decides whether a vehicle should be acquired.  Pricing answers
    the price for the vehicle supplied by the user, so this workflow does not
    fetch a daily report or run a selection/market-opportunity gate.
    """

    def __init__(self, pricing_callable: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.pricing_callable = pricing_callable

    def run(
        self,
        *,
        price_request: Dict[str, Any],
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
        task_id: str,
        event_sink: Callable[[Dict[str, Any]], None] | None = None,
    ) -> Dict[str, Any]:
        trace_id = f"wf_{uuid.uuid4().hex[:16]}"
        runs: list[Dict[str, Any]] = []

        valuation = self._execute(
            runs,
            trace_id=trace_id,
            step_id="step_1",
            tool_name="price_book_tool",
            tool_input={
                "price_request_hash": _digest(price_request),
                "vehicle": {
                    "model": price_request.get("modelName") or price_request.get("model"),
                    "model_year": price_request.get("modelYear"),
                    "first_license_date": price_request.get("regDate") or price_request.get("firstLicenseDate"),
                    "mileage_wan_km": price_request.get("mileage"),
                    "city": price_request.get("city"),
                    "transfer_count": price_request.get("transfer"),
                    "color": price_request.get("color"),
                    "condition": slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"),
                },
            },
            source="active_production_price_book",
            required=True,
            operation=lambda: self._valuation_with_sale_price(dict(price_request)),
            event_sink=event_sink,
            task_id=task_id,
        )
        price_result = complete_legacy_business_ladder(
            valuation.get("raw_result") or {},
            slots=slots,
        )
        valuation["raw_result"] = price_result
        valuation_result = _safe_json(price_result)
        if isinstance(valuation_result, dict):
            valuation_result["tool_business_explanation"] = _safe_json(
                _tool_business_explanation(
                    "price_book_tool",
                    str(valuation.get("status") or "success"),
                    price_result,
                    valuation.get("input") if isinstance(valuation.get("input"), dict) else {},
                    valuation.get("warnings") or [],
                )
            )
        valuation["result"] = valuation_result

        evidence = self._execute(
            runs,
            trace_id=trace_id,
            step_id="step_2",
            tool_name="comparable_evidence_tool",
            tool_input={
                "price_book_tool_run_id": valuation.get("tool_run_id"),
                "quote_id": price_result.get("quote_id") or price_result.get("request_id") or price_result.get("traceId"),
            },
            source="price_book_comparable_evidence",
            required=True,
            operation=lambda: self._comparable_evidence(price_result),
            event_sink=event_sink,
            task_id=task_id,
        )
        adjustment = self._execute(
            runs,
            trace_id=trace_id,
            step_id="step_3",
            tool_name="vehicle_adjustment_tool",
            tool_input={
                "comparable_evidence_tool_run_id": evidence.get("tool_run_id"),
                "vehicle_elements": self._vehicle_elements(slots, price_result),
            },
            source="price_book_seven_element_adjustment",
            required=True,
            operation=lambda: self._vehicle_adjustment(slots, price_result),
            event_sink=event_sink,
            task_id=task_id,
        )
        ladder = self._execute(
            runs,
            trace_id=trace_id,
            step_id="step_4",
            tool_name="price_ladder_tool",
            tool_input={
                "price_book_tool_run_id": valuation.get("tool_run_id"),
                "vehicle_adjustment_tool_run_id": adjustment.get("tool_run_id"),
            },
            source="business_price_ladder_contract",
            required=True,
            operation=lambda: self._price_ladder(price_result),
            event_sink=event_sink,
            task_id=task_id,
        )
        composer = self._execute(
            runs,
            trace_id=trace_id,
            step_id="step_5",
            tool_name="response_composer",
            tool_input={
                "price_book_tool_run_id": valuation.get("tool_run_id"),
                "comparable_evidence_tool_run_id": evidence.get("tool_run_id"),
                "vehicle_adjustment_tool_run_id": adjustment.get("tool_run_id"),
                "price_ladder_tool_run_id": ladder.get("tool_run_id"),
            },
            source="enterprise_response_composer",
            required=True,
            operation=lambda: self._compose(slots, {}, {}, {}, price_result),
            event_sink=event_sink,
            task_id=task_id,
        )
        report_context = composer.get("raw_result") or {}
        for run in runs:
            run.pop("raw_result", None)
        return {
            "workflow_version": WORKFLOW_VERSION,
            "trace_id": trace_id,
            "task_id": task_id,
            "started_at": runs[0]["started_at"] if runs else _now(),
            "finished_at": runs[-1]["finished_at"] if runs else _now(),
            "tool_results": runs,
            "price_result": price_result,
            "report_context": report_context,
            "market_context": {},
            "daily_report_context": {},
        }

    @staticmethod
    def _vehicle_elements(slots: Dict[str, Any], price_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "standard_vehicle": price_result.get("vehicle_title") or _vehicle_identity(slots),
            "first_license_date": _first_license_value(slots),
            "mileage_wan_km": slots.get("mileage_wan_km"),
            "city": slots.get("city"),
            "transfer_count": slots.get("transfer_count"),
            "color": slots.get("color"),
            "condition_group": slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"),
        }

    @staticmethod
    def _comparable_evidence(price_result: Dict[str, Any]) -> Dict[str, Any]:
        candidates = _selected_comparables(price_result)
        trace = price_result.get("price_trace") if isinstance(price_result.get("price_trace"), dict) else {}
        candidate_prices = [_candidate_price(row) for row in candidates if _candidate_price(row)]
        return {
            "quote_id": price_result.get("quote_id") or price_result.get("request_id") or price_result.get("traceId"),
            "comparable_count": len(candidates),
            "comparables": [
                {
                    "vehicle": row.get("title") or row.get("vehicle") or row.get("source") or "市场可比证据",
                    "match_basis": _match_basis(row),
                    "price_yuan": _candidate_price(row),
                    "city": row.get("city"),
                    "model_year": row.get("model_year"),
                    "mileage_wan_km": row.get("mileage_wan_km") or row.get("mileage"),
                }
                for row in candidates[:12]
            ],
            "price_range_yuan": [min(candidate_prices), max(candidate_prices)] if candidate_prices else [],
            "market_consensus_yuan": _money(trace.get("market_consensus_yuan")),
            "third_party_listing_yuan": _money(trace.get("third_party_listing_yuan")),
            "expected_c2b_yuan": _money((price_result.get("price_ladder") or {}).get("expected_c2b_yuan")),
            "confidence": price_result.get("confidence") or "MEDIUM",
            "evidence_boundary": "可比证据用于确定市场基线；证据少时降低置信度，不虚构车源或成交金额。",
        }

    @staticmethod
    def _vehicle_adjustment(slots: Dict[str, Any], price_result: Dict[str, Any]) -> Dict[str, Any]:
        context = _build_business_context(slots, {}, {}, {}, price_result)
        bridge = context.get("price_bridge") if isinstance(context.get("price_bridge"), dict) else {}
        trace = price_result.get("price_trace") if isinstance(price_result.get("price_trace"), dict) else {}
        element_trace = trace.get("element_adjustment_trace") if isinstance(trace.get("element_adjustment_trace"), dict) else {}
        city_log = _signed_number(element_trace.get("city_log_adjustment"))
        color_log = _signed_number(element_trace.get("color_log_adjustment"))
        city_pct = (math.exp(city_log) - 1.0) * 100.0 if city_log is not None else None
        color_pct = (math.exp(color_log) - 1.0) * 100.0 if color_log is not None else None
        local_factor = _money(trace.get("local_adjustment_factor"))
        local_pct = (local_factor - 1.0) * 100.0 if local_factor else None
        condition = slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition")
        adjustments = [
            {
                "label": "车型/款型",
                "direction": "已锁定",
                "explanation": f"命中{trace.get('matched_model_year') or slots.get('model_year') or '当前'}年款 {trace.get('matched_trim') or slots.get('trim') or slots.get('standard_vehicle') or '标准车型'}，避免串到泛车系。",
            },
            {
                "label": "上牌时间",
                "direction": "已计入",
                "explanation": f"{_first_license_value(slots) or '当前上牌时间'}已进入车龄折旧计算。",
            },
            {
                "label": "里程",
                "direction": "已计入",
                "explanation": f"{slots.get('mileage_wan_km') or '当前'}万公里已进入连续里程修正。",
            },
            {
                "label": "城市",
                "direction": "上调" if city_pct and city_pct > 0 else "下调" if city_pct and city_pct < 0 else "已计入",
                "explanation": (
                    f"{slots.get('city') or '当前城市'}残差修正 {city_pct:+.2f}%（支持样本 {int(element_trace.get('city_support') or 0)} 条）。"
                    if city_pct is not None else f"{slots.get('city') or '当前城市'}已进入本地市场修正。"
                ),
            },
            {
                "label": "过户次数",
                "direction": "已计入",
                "explanation": f"{slots.get('transfer_count') if slots.get('transfer_count') not in (None, '') else '当前'}次过户已进入车辆差异修正。",
            },
            {
                "label": "颜色",
                "direction": "上调" if color_pct and color_pct > 0 else "下调" if color_pct and color_pct < 0 else "轻微影响",
                "explanation": (
                    f"{slots.get('color') or '当前颜色'}修正 {color_pct:+.2f}%（同款年款支持样本 {int(element_trace.get('color_support') or 0)} 条）。"
                    if color_pct is not None else f"{slots.get('color') or '当前颜色'}按主流度进行轻量修正。"
                ),
            },
            {
                "label": "车况",
                "direction": "已计入",
                "explanation": f"{condition or '当前车况'}级车况已进入本次定价。",
            },
        ]
        return {
            "baseline_price_yuan": _money(trace.get("market_consensus_yuan")) or bridge.get("baseline_price_yuan"),
            "adjustments": adjustments,
            "final_price_yuan": bridge.get("final_price_yuan"),
            "local_adjustment_percent": round(local_pct, 2) if local_pct is not None else None,
            "amount_policy": "只展示定价模型实际记录的修正方向、支持样本和系数；没有独立金额的维度不虚构金额。",
        }

    @staticmethod
    def _price_ladder(price_result: Dict[str, Any]) -> Dict[str, Any]:
        ladder = price_result.get("price_ladder") if isinstance(price_result.get("price_ladder"), dict) else {}
        if ladder:
            return {"price_ladder": ladder, "ordering_valid": EnterprisePricingWorkflowV22._ladder_order_valid(ladder)}
        point = _price_point(price_result)
        lower, upper = _price_range(price_result, point)
        return {
            "price_ladder": {},
            "expected_c2b_yuan": point or None,
            "c2b_range_yuan": [lower, upper] if point else [],
            "ordering_valid": False,
            "warning": "定价模型未返回完整售卖价与收车价梯度，前端不得伪造缺失价格角色。",
        }

    @staticmethod
    def _ladder_order_valid(ladder: Dict[str, Any]) -> bool:
        listing = _money(ladder.get("recommended_listing_yuan"))
        sale = _money(ladder.get("expected_b2c_transaction_yuan"))
        c2b = _money(ladder.get("expected_c2b_yuan"))
        first_offer = _money(ladder.get("first_c2b_offer_yuan"))
        max_c2b = _money(ladder.get("max_c2b_yuan"))
        if not all((listing, sale, c2b, first_offer, max_c2b)):
            return False
        return listing >= sale > max_c2b >= c2b >= first_offer

    def _valuation_with_sale_price(self, price_request: Dict[str, Any]) -> Dict[str, Any]:
        """Run C2B valuation and attach B2C sale-price output when the engine supports it."""

        primary = self.pricing_callable(dict(price_request)) or {}
        if not isinstance(primary, dict):
            return {}
        if _has_b2c_price(primary):
            return _enforce_b2c_not_below_c2b(primary)
        b2c_payload = dict(price_request)
        primary_c2b_point = _price_point(primary)
        b2c_payload.update(
            {
                "pricing_task": "b2c_sale",
                "price_role": "B2C",
                "target_type": "B2C",
                "business_type": "B2C",
                "valuation_type": "B2C",
                "module": "b2c_sale_price",
                "precomputed_c2b_price_yuan": primary_c2b_point or None,
                "precomputed_c2b_price_trace": primary.get("price_trace")
                if isinstance(primary.get("price_trace"), dict)
                else {},
            }
        )
        try:
            b2c_result = self.pricing_callable(b2c_payload) or {}
        except Exception as exc:
            primary["b2c_price_warning"] = f"B2C_PRICE_CALL_FAILED: {exc}"
            return primary
        if not isinstance(b2c_result, dict) or b2c_result.get("success") is False:
            primary["b2c_price_warning"] = "B2C_PRICE_CALL_FAILED"
            primary["b2c_price_result"] = _safe_json(b2c_result) if isinstance(b2c_result, dict) else {}
            return primary

        b2c_point = (
            _price_yuan(b2c_result.get("b2cPrice"))
            or _price_yuan(b2c_result.get("b2c_price"))
            or _price_yuan(b2c_result.get("targetB2C"))
            or _price_yuan(b2c_result.get("final_price"))
            or _price_yuan((b2c_result.get("price") or {}).get("point") if isinstance(b2c_result.get("price"), dict) else None)
        )
        b2c_range = b2c_result.get("b2cRange") if isinstance(b2c_result.get("b2cRange"), list) else []
        b2c_low = (
            _price_yuan(b2c_range[0] if len(b2c_range) > 0 else None)
            or _price_yuan(b2c_result.get("b2c_low"))
            or _price_yuan(b2c_result.get("b2c_lower"))
            or _price_yuan(b2c_result.get("price_low"))
        )
        b2c_high = (
            _price_yuan(b2c_range[1] if len(b2c_range) > 1 else None)
            or _price_yuan(b2c_result.get("b2c_high"))
            or _price_yuan(b2c_result.get("b2c_upper"))
            or _price_yuan(b2c_result.get("price_high"))
        )
        if not b2c_point:
            primary["b2c_price_warning"] = "B2C_PRICE_CALL_RETURNED_NO_POINT"
            primary["b2c_price_result"] = _safe_json(b2c_result)
            return primary
        if not b2c_low:
            b2c_low = b2c_point * 0.975
        if not b2c_high:
            b2c_high = b2c_point * 1.035
        merged = dict(primary)
        spread_candidate = get_c2b_from_b2c_spread_service().predict(
            b2c_payload,
            b2c_transaction_price_yuan=b2c_point,
        )
        if b2c_payload.get("series") and (b2c_payload.get("trim") or b2c_payload.get("model") or b2c_payload.get("modelName")):
            try:
                listing_result = get_third_party_listing_price_service().quote(b2c_payload)
            except Exception as exc:
                listing_result = {"enabled": False, "reason": "THIRD_PARTY_LISTING_RUNTIME_ERROR", "error": str(exc)}
        else:
            listing_result = {"enabled": False, "reason": "VEHICLE_IDENTITY_INCOMPLETE"}
        three_source_calibration = get_b2c_three_source_calibration_service().predict(
            b2c_payload,
            b2c_transaction_price_yuan=b2c_point,
            listing_result=listing_result,
        )
        merged.update(
            {
                "b2cPrice": _price_wan(b2c_point),
                "b2c_price": _price_wan(b2c_point),
                "targetB2C": _price_wan(b2c_point),
                "b2cRange": [_price_wan(b2c_low), _price_wan(b2c_high)],
                "b2c_price_result": _safe_json(b2c_result),
                "b2c_pricing_engine_used": b2c_result.get("pricing_engine_used"),
                "b2c_quote_id": b2c_result.get("quote_id") or b2c_result.get("request_id") or b2c_result.get("traceId"),
                "c2b_from_b2c_spread_candidate": _safe_json(spread_candidate),
                "third_party_listing_price_result": _safe_json(listing_result),
                "b2c_three_source_calibration_candidate": _safe_json(three_source_calibration),
                "listing_price_yuan": listing_result.get("listing_price_yuan") if listing_result.get("enabled") else None,
                "listing_price_wan": listing_result.get("listing_price_wan") if listing_result.get("enabled") else None,
                "listing_price_role": "THIRD_PARTY_B2C_LISTING_PRICE",
            }
        )
        return _enforce_b2c_not_below_c2b(merged)

    def _execute(
        self,
        runs: list[Dict[str, Any]],
        *,
        trace_id: str,
        step_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        source: str,
        required: bool,
        operation: Callable[[], Dict[str, Any]],
        event_sink: Callable[[Dict[str, Any]], None] | None = None,
        task_id: str = "",
    ) -> Dict[str, Any]:
        started_at = _now()
        started = time.perf_counter()
        run: Dict[str, Any] = {
            "tool_run_id": f"tool_{uuid.uuid4().hex[:12]}",
            "trace_id": trace_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "status": "running",
            "required": required,
            "executed": True,
            "started_at": started_at,
            "input": _safe_json(tool_input),
            "input_hash": _digest(tool_input),
            "source": source,
            "warnings": [],
        }
        tool_labels = {
            "price_book_tool": "调用定价模型并生成单车价格",
            "comparable_evidence_tool": "核对可比车与市场基线",
            "vehicle_adjustment_tool": "核对七要素价格影响",
            "price_ladder_tool": "校验完整价格梯度",
            "response_composer": "生成业务结论",
        }
        if event_sink is not None:
            event_sink(
                {
                    "event_type": "tool.started",
                    "task_id": task_id,
                    "module": "pricing",
                    "at": started_at,
                    "step": {
                        "step_id": step_id,
                        "tool_run_id": run["tool_run_id"],
                        "name": tool_labels.get(tool_name, tool_name),
                        "status": "running",
                        "detail": {
                            "price_book_tool": "正在调用定价模型，按标准车型、市场基线和七要素生成收售价格。",
                            "comparable_evidence_tool": "正在核对可比车数量、相似程度与价格分布。",
                            "vehicle_adjustment_tool": "正在逐项核对上牌、里程、城市、过户、颜色和车况影响。",
                            "price_ladder_tool": "正在校验挂牌、实际售卖、实际收车、首报价和最高收车价的顺序。",
                            "response_composer": "正在把工具事实整理成一线可直接执行的结论。",
                        }.get(tool_name, "正在执行真实业务工具。"),
                    },
                }
            )
        try:
            result = operation() or {}
            status = str(result.pop("_tool_status", "success"))
            warning = result.pop("_tool_warning", "")
            run["status"] = status
            run["result"] = _safe_json(result)
            run["raw_result"] = result
            if warning:
                run["warnings"].append(str(warning))
        except Exception as exc:
            run["status"] = "failed"
            run["result"] = {}
            run["raw_result"] = {}
            run["warnings"].append(f"{type(exc).__name__}: {exc}")
        business_explanation = _tool_business_explanation(
            tool_name,
            str(run.get("status") or ""),
            run.get("raw_result") or {},
            tool_input,
            run.get("warnings") or [],
        )
        if isinstance(run.get("result"), dict):
            run["result"]["business_explanation"] = _safe_json(business_explanation)
        run["finished_at"] = _now()
        run["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        run["output_hash"] = _digest(run.get("result") or {})
        runs.append(run)
        if event_sink is not None:
            final_status = "done" if run["status"] in {"success", "done"} else (
                "warning" if run["status"] in {"skipped", "not_required", "not_loaded", "available_as_context"} else "failed"
            )
            event_sink(
                {
                    "event_type": "tool.completed",
                    "task_id": task_id,
                    "module": "pricing",
                    "at": run["finished_at"],
                    "step": {
                        "step_id": step_id,
                        "tool_run_id": run["tool_run_id"],
                        "name": tool_labels.get(tool_name, tool_name),
                        "status": final_status,
                        "detail": business_explanation.get("conclusion") or "步骤已完成。",
                        "business_explanation": business_explanation,
                        "duration_ms": run["duration_ms"],
                    },
                }
            )
        return run

    @staticmethod
    def _market_indicator(slots: Dict[str, Any]) -> Dict[str, Any]:
        loader = get_market_state_loader()
        city = str(slots.get("city") or "全国")
        series = str(slots.get("series") or "")
        brand = str(slots.get("brand") or "")
        if not loader.available:
            return {
                "_tool_status": "skipped",
                "_tool_warning": "行情业务校准数据不可用",
                "city": city,
                "series": series,
                "matched_rows": 0,
            }
        rows = loader.filter(city=city, series=series) if series else loader.filter(city=city, brand=brand)
        if not rows and city != "全国":
            rows = loader.filter(city="全国", series=series) if series else loader.filter(city="全国", brand=brand)
        if not rows:
            return {
                "_tool_status": "skipped",
                "_tool_warning": "未命中车型+城市行情指标",
                "city": city,
                "series": series,
                "matched_rows": 0,
                "data_source": loader.metadata,
            }
        return {
            "city": city,
            "series": series,
            "matched_rows": len(rows),
            "metrics": _public_market_row(rows[0]),
            "data_source": loader.metadata,
        }

    @staticmethod
    def _market_state(
        slots: Dict[str, Any],
        client_state: Dict[str, Any],
        indicator_run: Dict[str, Any],
    ) -> Dict[str, Any]:
        city = str(slots.get("city") or "全国")
        series = str(slots.get("series") or "")
        indicator_result = indicator_run.get("raw_result") or indicator_run.get("result") or {}
        if indicator_run.get("status") != "success" or not int(indicator_result.get("matched_rows") or 0):
            return {
                "_tool_status": "skipped",
                "_tool_warning": "未命中当前车型+城市行情指标，未生成替代车型行情状态",
                "state_id": None,
                "city": city,
                "series": series,
                "indicator_tool_run_id": indicator_run.get("tool_run_id"),
                "data_source": indicator_result.get("data_source") or {},
            }
        query = f"{city} {series} 行情与收车风险".strip()
        result = build_market_opportunity_response(query, city, client_state)
        card = result.get("market_agent_card") or {}
        recommendations = card.get("recommendations") or []
        if not recommendations:
            return {
                "_tool_status": "skipped",
                "_tool_warning": "行情状态服务未返回当前车型状态",
                "state_id": card.get("state_id"),
                "city": city,
                "series": series,
                "indicator_tool_run_id": indicator_run.get("tool_run_id"),
            }
        top = recommendations[0]
        return {
            "state_id": card.get("state_id"),
            "city": card.get("city") or city,
            "series": top.get("series") or series,
            "indicator_tool_run_id": indicator_run.get("tool_run_id"),
            "market_category": top.get("market_category"),
            "market_category_label": top.get("market_category_label"),
            "recommendation_label": top.get("recommendation_label"),
            "opportunity_score": top.get("opportunity_score"),
            "reasons": top.get("reasons") or [],
            "risks": top.get("risks") or [],
            "action": top.get("action"),
            "metrics": _public_market_row(top),
            "data_source": card.get("data_source") or {},
        }

    @staticmethod
    def _daily_report(slots: Dict[str, Any]) -> Dict[str, Any]:
        service = DailyReportContentService()
        candidates: list[tuple[str, Path]] = []
        for directory in (service.root / "uploaded_reports", service.root / "outputs"):
            if not directory.exists():
                continue
            for path in directory.glob("daily_report_20*.pdf*"):
                match = re.search(r"daily_report_(20\d{2}-\d{2}-\d{2})\.pdf", path.name)
                if match:
                    candidates.append((match.group(1), path))
        if not candidates:
            return {
                "_tool_status": "skipped",
                "_tool_warning": "没有可读取的已上传行业日报",
            }
        report_date = sorted(candidates, key=lambda item: item[0])[-1][0]
        card = service.card_payload(report_date)
        if not card:
            return {
                "_tool_status": "skipped",
                "_tool_warning": f"日报 {report_date} 无法解析",
                "report_date": report_date,
            }
        query = f"{slots.get('brand') or ''}{slots.get('series') or ''} {slots.get('city') or ''} 价格 成交 库存 降价"
        evidence = service.retrieve(report_date, query, limit=3)
        return {
            "report_id": card.get("filename"),
            "filename": card.get("filename"),
            "report_date": report_date,
            "source_type": card.get("source_type"),
            "page_count": card.get("page_count"),
            "core_conclusions": card.get("core_conclusions") or [],
            "evidence": evidence,
        }

    @staticmethod
    def _compose(
        slots: Dict[str, Any],
        indicator_run: Dict[str, Any],
        market_state_run: Dict[str, Any],
        daily_report_run: Dict[str, Any],
        price_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        indicator = indicator_run.get("raw_result") or {}
        market_state = market_state_run.get("raw_result") or {}
        daily_report = daily_report_run.get("raw_result") or {}
        business_context = _build_business_context(slots, indicator, market_state, daily_report, price_result)
        llm_business_copy = _llm_business_copy(business_context)
        return {
            "vehicle_six_elements": {
                "standard_vehicle": price_result.get("vehicle_title") or _vehicle_identity(slots),
                "model_year": slots.get("model_year"),
                "first_license_date": _first_license_value(slots),
                "first_license_year": slots.get("first_license_year"),
                "first_license_month": slots.get("first_license_month"),
                "mileage_wan_km": slots.get("mileage_wan_km"),
                "city": slots.get("city"),
                "transfer_count": slots.get("transfer_count"),
                "color": slots.get("color"),
                "condition_group": slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"),
            },
            "market_indicator": indicator,
            "market_state": market_state,
            "daily_report": daily_report,
            "business_guidance": {
                "market_action": market_state.get("action"),
                "market_risks": market_state.get("risks") or [],
                "evidence_boundary": "行情与日报只用于风险解释和业务判断，不直接篡改估价引擎输出。",
            },
            "executive_summary": business_context.get("executive_summary") or {},
            "valuation_summary": business_context.get("valuation_summary") or {},
            "price_bridge": business_context.get("price_bridge") or {},
            "action_guide": business_context.get("action_guide") or {},
            "comparable_evidence": business_context.get("comparable_evidence") or [],
            "business_output_contract": business_context.get("business_output_contract") or {},
            "llm_business_copy": llm_business_copy,
            "quote_id": price_result.get("quote_id") or price_result.get("request_id") or price_result.get("traceId"),
        }
