#!/usr/bin/env python3
"""Render deterministic business text strictly from ledger fields."""

from __future__ import annotations

import re
from typing import Any

from .price_explanation_schema import PriceExplanationLedger


NUMBER_PATTERN = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?%?")


def _wan(value: Any) -> str:
    return f"{float(value) / 10000:.2f}万元"


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.1f}%"


def render_business_explanation(ledger: PriceExplanationLedger) -> dict[str, Any]:
    final = ledger.final_price
    interval = ledger.interval
    retrieval = ledger.retrieval_summary
    confidence = ledger.confidence
    statistical = ledger.statistical_price
    adjustment = ledger.model_adjustment

    point = final.get("final_point_price")
    low = interval.get("price_low")
    high = interval.get("price_high")
    bucket = str(confidence.get("confidence_bucket") or "Manual")
    retrieved = int(retrieval.get("total_retrieved_count") or 0)
    selected = int(len(ledger.selected_comparables))
    latest_days = retrieval.get("latest_evidence_days")
    dispersion = statistical.get("price_dispersion")
    adjustment_amount = float(adjustment.get("final_adjustment_amount") or 0)

    if point is None:
        summary = f"本次未生成自动单点报价，置信度为{bucket}，需要人工复核。"
    else:
        summary = f"本次单点参考价为{_wan(point)}，参考区间为{_wan(low)}至{_wan(high)}，置信度为{bucket}。"

    comparable_summary = f"系统在报价时点之前召回{retrieved}辆候选，最终采用{selected}个价格组件形成统计基线"
    if statistical.get("baseline_price") is not None:
        comparable_summary += f"{_wan(statistical['baseline_price'])}"
    comparable_summary += "。"

    if latest_days is not None:
        comparable_summary += f"最近一条可用证据距报价时点{int(round(float(latest_days)))}天。"

    if adjustment.get("model_name") in {"", None, "NO_RESIDUAL_MODEL"}:
        adjustment_summary = "当前链路没有启用残差模型，模型调整为0.00万元，最终价格未被树模型改变。"
    else:
        direction = "上调" if adjustment_amount >= 0 else "下调"
        adjustment_summary = f"残差模型{direction}{_wan(abs(adjustment_amount))}。"

    interval_summary = "报价区间由可比车价格云、证据数量、时效和召回层级共同决定。"
    if dispersion is not None:
        interval_summary += f"当前候选价格离散度为{_percent(dispersion)}。"

    reason_details = confidence.get("reason_details") or []
    reason_text = "；".join(str(item.get("message") or item.get("reason") or "") for item in reason_details if item)
    confidence_summary = f"置信度为{bucket}"
    if reason_text:
        confidence_summary += f"，主要因为{reason_text}"
    if confidence.get("probability_ape_le_5") is None:
        confidence_summary += "；当前尚未接入单车风险概率模型，因此APE概率字段不作估计"
    confidence_summary += "。"

    full_text = "\n".join(
        [
            summary,
            comparable_summary,
            adjustment_summary,
            interval_summary,
            confidence_summary,
        ]
    )
    grounding = {
        "final_point_price": point,
        "price_low": low,
        "price_high": high,
        "retrieved_count": retrieved,
        "selected_count": selected,
        "baseline_price": statistical.get("baseline_price"),
        "latest_evidence_days": latest_days,
        "model_adjustment_amount": adjustment_amount,
        "price_dispersion": dispersion,
    }
    return {
        "summary": summary,
        "comparable_summary": comparable_summary,
        "adjustment_summary": adjustment_summary,
        "interval_summary": interval_summary,
        "confidence_summary": confidence_summary,
        "full_text": full_text,
        "grounding_values": grounding,
        "numeric_tokens": NUMBER_PATTERN.findall(full_text),
    }


def render_and_attach(ledger: PriceExplanationLedger) -> PriceExplanationLedger:
    ledger.business_explanation = render_business_explanation(ledger)
    return ledger
