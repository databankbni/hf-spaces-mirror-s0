from __future__ import annotations

from typing import Any, Dict


def compose_customer_script(
    *,
    vehicle_title: str,
    point_text: str,
    upper_text: str,
    lower_text: str,
    candidate_count: int,
    dispersion: str,
    confidence: str,
    daily_note: str,
    vehicle_condition_clause: str | None = None,
    market_clause: str | None = None,
) -> str:
    condition_clause = _sentence(vehicle_condition_clause) or _vehicle_condition_clause(vehicle_title)
    market_sentence = _sentence(market_clause)
    price_text = _soft_customer_price(point_text)
    if candidate_count < 5 or str(confidence).upper() == "LOW":
        return (
            f"这台车我按现有信息核过，{condition_clause}"
            f"{market_sentence}"
            "不过这类车我得先看实车，不能只按网上挂价直接报。"
            f"我建议咱们先按 {price_text} 这个价聊。"
            "车况要是检测出来确实好，没事故、没泡水、没调表，整备成本也低，我再帮你往上申请一点。"
            "没看实车之前我不建议直接按高价报，咱们先把检测约了，车况确认清楚后我再给你争取最终价。"
        )
    price_clause = (
        "外面价格差别比较大，高价不一定代表真实成交。"
        if dispersion != "集中"
        else "这类车价格参考性还可以，但最后还是要看实车检测。"
    )
    return (
        f"这台车我按现有信息核过，{condition_clause}"
        f"{market_sentence}"
        f"但我们收车不能只看网上挂价，挂价和真实成交价差别挺大。{price_clause}"
        "后面还要看检测、整备和再卖周期。"
        f"我建议咱们先按 {price_text} 这个价聊。"
        "车况要是检测出来确实好，没事故、没泡水、没调表，整备成本也低，我再帮你往上申请一点。"
        "没看实车之前我不建议直接按高价报，咱们先把检测约了，车况确认清楚后我再给你争取最终价。"
    )


def customer_script_block(script: str) -> Dict[str, Any]:
    return {
        "type": "customer_script",
        "title": "客户嫌低怎么说",
        "text": script,
        "copyable": True,
    }


def compose_customer_questions(*, point_text: str, upper_text: str, dispersion: str) -> list[Dict[str, str]]:
    price_reference = (
        "外面价格差别比较大，高价不一定代表真实成交。"
        if dispersion != "集中"
        else "外面价格能做参考，但最后还是要看实车检测和真实成交条件。"
    )
    return [
        {
            "question": "客户问：为什么别人能给更高？",
            "answer": (
                "其他报价可以参考，但需要先确认它对应的是挂牌、售车还是收车口径，以及是否已经验车。"
                "把对应车辆条件和报价口径发来后，可以与当前车辆逐项对齐差异。"
            ),
        },
        {
            "question": "客户问：网上同款卖得更贵，为什么你们收这么低？",
            "answer": (
                f"网上很多是挂牌价，不一定是成交价。{price_reference}"
                "我们收回来还要检测、整备、过户、库存和再卖，所以不能直接按零售价收。"
            ),
        },
        {
            "question": "客户问：能不能再加一点？",
            "answer": (
                "可以帮你争取，但要先看检测结果。"
                "车况好、手续清楚、整备成本低，我再往上申请；没看实车前我不敢直接加太多。"
            ),
        },
    ]


def _vehicle_condition_clause(vehicle_title: str) -> str:
    # Vehicle title is intentionally used only for context; customer copy should
    # avoid internal evidence and keep the praise generic unless facts are known.
    return "当前车辆条件已经纳入报价，最终仍要以实车检测为准。"


def _sentence(text: str | None) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return value if value.endswith(("。", "！", "？")) else f"{value}。"


def _soft_customer_price(point_text: str) -> str:
    return str(point_text or "建议价附近").replace("万", "万左右")
