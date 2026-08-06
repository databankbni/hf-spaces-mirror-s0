from __future__ import annotations

import re
from typing import Any, Dict, List


FORBIDDEN_CUSTOMER_WORDS = (
    "中位价",
    "价格区间",
    "最高样本",
    "追价上限",
    "内部上限",
    "置信度",
    "模型",
    "算法",
    "RAG",
    "workflow",
    "trace",
    "数据库",
    "我们系统算出来",
)


def generate_customer_script_pack(
    *,
    pricing_decision_report: Dict[str, Any],
    vehicle_slots: Dict[str, Any],
    condition_clause: str,
    market_clause: str,
    dispersion: str,
) -> Dict[str, Any]:
    """Generate customer-safe negotiation copy.

    The exact internal target / upper bound stay in internal report fields.
    Customer copy only uses the soft communication price and human-readable
    reasons already derived from structured facts.
    """
    decision = pricing_decision_report.get("decision_summary") or {}
    decision_card = pricing_decision_report.get("decision_card") or {}
    talk_price = _customer_price(str(decision.get("customer_talk_price") or decision.get("communication_price") or "建议价附近"))
    title = _vehicle_title(vehicle_slots, pricing_decision_report)
    condition = _short_condition(condition_clause)
    market = _short_market(market_clause)
    count = int(pricing_decision_report.get("candidate_count") or 0)
    evidence_note = (
        f"这次有{count}台条件接近的车用于核对方向，但实车差异仍要靠检测确认。"
        if count > 0
        else "这次严格同条件样本有限，报价会更依赖当前车辆信息和实车检测。"
    )
    sale_price = str(decision_card.get("recommended_sale_price") or "")
    risk_items = [str(item) for item in (pricing_decision_report.get("main_risks") or []) if item]
    risk_note = risk_items[0] if risk_items else "最终还要核对事故、泡水、火烧、调表和整备情况。"
    price_reference = (
        "同款价格差异较大，单看最高挂牌价容易高估实际成交。"
        if dispersion != "集中"
        else "同款价格方向较接近，但仍不能替代当前车辆的检测结果。"
    )
    scenarios = [
        {
            "scene": "首次报价",
            "text": (
                f"这台{title}已按你提供的年款、公里数和手续信息估算，{condition}"
                f"结合近期同类车情况，我们先围绕{talk_price}沟通。"
                "实车检测与描述一致后，再确认最终收车价。"
            ),
            "customer_safe": True,
        },
        {
            "scene": "客户嫌低",
            "text": (
                f"我理解你觉得{talk_price}偏低。{evidence_note}"
                f"目前主要还差实车检测确认；如果关键车况没有额外扣减，再按检测结果复核可谈空间。"
            ),
            "customer_safe": True,
        },
        {
            "scene": "网上价格更高",
            "text": (
                f"网上同款通常混有不同年款、配置、里程和车况，挂牌价也不等于实际成交价。{price_reference}"
                f"这台{title}需要按当前七项车辆信息逐项对齐后再比较，不能直接拿最高价套用。"
            ),
            "customer_safe": True,
        },
        {
            "scene": "其他机构报价更高",
            "text": (
                "对方报价可以作为参考，我们先不判断它对不对。"
                f"请把报价对应的价格类型、车辆条件和是否验车发来；我会与这台{title}当前的收车口径逐项对齐，再说明差额来自哪里。"
            ),
            "customer_safe": True,
        },
        {
            "scene": "客户要求再加一点",
            "text": (
                f"可以继续谈，但这台{title}要先确认检测、手续和实际整备项。"
                f"当前预计售车价约为{sale_price or '报告所示价格'}，收售空间有限，不能只为成交直接抬高收车价；检测结果更好时再复核上调依据。"
            ),
            "customer_safe": True,
        },
        {
            "scene": "用户认为当前价格不准",
            "text": (
                f"可以先把分歧说清楚：你认为{talk_price}偏低，还是预计售车价不符合实际？"
                f"当前报价主要由这台{title}的车辆信息和可比证据支撑。{risk_note}"
                "你提供具体成交案例、检测结果或认为合理的价格后，我们按同一口径逐项核对，不直接重复整份估价。"
            ),
            "customer_safe": True,
        },
    ]
    safe_scenarios = []
    for scenario in scenarios:
        text = filter_customer_text(str(scenario.get("text") or ""), pricing_decision_report)
        safe_scenarios.append({**scenario, "text": text})
    return {
        "title": "沟通助手",
        "scenarios": safe_scenarios,
        "copyable": True,
        "customer_safe": True,
        "internal_only": False,
    }


def generate_customer_faq(
    *,
    pricing_decision_report: Dict[str, Any],
    vehicle_slots: Dict[str, Any],
    dispersion: str,
    condition_clause: str,
    market_clause: str,
) -> List[Dict[str, str]]:
    facts = _faq_fact_bits(vehicle_slots, condition_clause, market_clause, dispersion)
    faq = [
        {
            "customer_question": "为什么别人能给更高？",
            "recommended_answer": (
                "其他报价可以参考，但需要先确认它对应的是挂牌、售车还是收车口径，以及是否已经验车。"
                f"{facts[0]}把对方报价条件发来后，可以与当前车辆逐项对齐差异。"
            ),
            "internal_intent": "稳住客户，避免没验车就直接抬价。",
            "do_not_say": "不要说内部上限，不要说中位价，不要说模型置信度。",
            "customer_safe": True,
        },
        {
            "customer_question": "网上同款卖得更贵，为什么你们收这么低？",
            "recommended_answer": (
                "网上很多是挂牌价，不一定是成交价。"
                f"{facts[1]}我们收回来还要检测、整备、过户、库存和再卖，所以不能直接按零售价收。"
            ),
            "internal_intent": "解释挂牌价和收车价不同。",
            "do_not_say": "不要暴露可比车数量、价格区间和内部上限。",
            "customer_safe": True,
        },
        {
            "customer_question": "能不能再加一点？",
            "recommended_answer": (
                "可以帮您争取，但要先看检测结果。"
                f"{facts[2]}车况好、手续清楚、整备成本低，我再往上申请。"
            ),
            "internal_intent": "把加价前提拉回验车和整备。",
            "do_not_say": "不要承诺一定加价，不要说内部风险线。",
            "customer_safe": True,
        },
    ]
    return [
        {**item, "recommended_answer": filter_customer_text(item["recommended_answer"], pricing_decision_report)}
        for item in faq
    ]


def filter_customer_text(text: str, report: Dict[str, Any]) -> str:
    value = str(text or "")
    for word in FORBIDDEN_CUSTOMER_WORDS:
        value = value.replace(word, "")
    internal_numbers = _internal_numbers(report)
    for number in internal_numbers:
        if number:
            value = value.replace(number, "这个价")
    value = re.sub(r"\d+\.\d{2,}\s*万", lambda m: _soften_precise_price(m.group(0)), value)
    # A public sale price can round to the same wording as an internal upper
    # bound (for example 17.32万 -> 17万出头). Re-run the boundary scrub after
    # rounding so the coincidence never leaks the internal number.
    for number in internal_numbers:
        if number:
            value = value.replace(number, "这个价")
    value = re.sub(r"这个价(?:出头|左右|多)", "这个价", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def flatten_script_pack(pack: Dict[str, Any]) -> str:
    return "\n\n".join(
        f"{item.get('scene')}：{item.get('text')}"
        for item in (pack.get("scenarios") or [])
        if isinstance(item, dict) and item.get("text")
    )


def _internal_numbers(report: Dict[str, Any]) -> set[str]:
    result: set[str] = set()
    decision_summary = report.get("decision_summary") or {}
    decision_card = report.get("decision_card") or {}
    for key in ("internal_target_price", "internal_chase_limit", "internal_upper_bound"):
        value = str(decision_summary.get(key) or decision_card.get(key) or report.get(key) or "")
        if value:
            result.add(value)
            result.add(value.replace(" ", ""))
    for key in ("upper_yuan", "baseline_price_yuan"):
        number = report.get(key)
        if isinstance(number, (int, float)) and number:
            result.add(f"{number / 10000:.2f}万")
            result.add(f"{number / 10000:.1f}万")
    return result


def _customer_price(value: str) -> str:
    text = str(value or "建议价附近").replace(" 左右", "").strip()
    match = re.search(r"(\d+)(?:\.(\d+))?万", text)
    if not match:
        return text
    integer = int(match.group(1))
    decimal = float(f"0.{match.group(2)}") if match.group(2) else 0.0
    if decimal >= 0.65:
        return f"{integer}万多"
    if decimal >= 0.2:
        return f"{integer}万出头"
    return f"{integer}万左右"


def _vehicle_title(vehicle_slots: Dict[str, Any], report: Dict[str, Any]) -> str:
    explicit = str(report.get("vehicle_title") or "").strip()
    if explicit:
        return explicit
    parts = [
        vehicle_slots.get("model_year") or vehicle_slots.get("year"),
        vehicle_slots.get("brand"),
        vehicle_slots.get("series"),
        vehicle_slots.get("trim") or vehicle_slots.get("model") or vehicle_slots.get("standard_vehicle"),
    ]
    title = " ".join(str(item).strip() for item in parts if str(item or "").strip())
    return title or "当前车辆"


def _short_condition(condition_clause: str) -> str:
    text = str(condition_clause or "").strip("。")
    return text + "。" if text else "配置和公里数还可以。"


def _short_market(market_clause: str) -> str:
    text = str(market_clause or "").strip("。")
    return text + "。" if text else ""


def _soften_precise_price(text: str) -> str:
    match = re.search(r"(\d+)(?:\.(\d+))?万", text)
    if not match:
        return text
    return f"{int(match.group(1))}万出头"


def _faq_fact_bits(vehicle_slots: Dict[str, Any], condition_clause: str, market_clause: str, dispersion: str) -> list[str]:
    color = str(vehicle_slots.get("color") or "")
    bits = []
    if color and color not in {"白色", "黑色", "灰色", "银色"}:
        bits.append("当前颜色在部分买家中更挑偏好，最终仍要用同款真实成交证据判断。")
    else:
        bits.append(str(condition_clause or "当前车辆条件已经纳入报价，但实车仍待检测。"))
    bits.append("外面价格差别比较大，高价不一定代表真实成交。" if dispersion != "集中" else "")
    bits.append(str(market_clause or condition_clause or ""))
    return [str(item or "") for item in bits]
