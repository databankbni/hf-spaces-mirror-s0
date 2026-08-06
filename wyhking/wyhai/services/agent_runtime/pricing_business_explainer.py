from __future__ import annotations

from typing import Any, Dict, List


def compose_pricing_step_explanation(
    *,
    step_name: str,
    tool_result: Dict[str, Any],
    vehicle_slots: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize one tool result into a business-first step DTO.

    Tool rows remain available for evidence details, but the default card reads
    from this DTO so the UI can answer "what does this mean for my quote?"
    without exposing technical internals.
    """
    rows = _detail_rows(tool_result)
    metrics = _key_metrics(tool_result)
    title = str(tool_result.get("title") or step_name or "任务执行")
    conclusion = _business_text(tool_result.get("stage_conclusion") or tool_result.get("summary"))
    impact = _business_text(tool_result.get("price_impact") or tool_result.get("business_meaning"))
    if not impact and rows:
        impact = next((str(row.get("impact") or "") for row in rows if row.get("impact")), "")
    next_action = _business_text(tool_result.get("action")) or "继续结合车况和行情判断报价边界。"
    confidence_reason = _business_text(tool_result.get("why_trust"))
    return {
        "step_title": title,
        "status": "done",
        "one_line_conclusion": conclusion,
        "business_impact": _strip_label(impact, "业务含义"),
        "next_action": _strip_label(next_action, "下一步"),
        "key_metrics": metrics[:4],
        "detail_rows": rows[:3],
        "confidence_reason": confidence_reason,
        "internal_only": True,
        "customer_safe": False,
        "technical_detail": {
            "task_id": tool_result.get("task_id"),
            "sources": tool_result.get("sources") or [],
            "llm_explained": bool(tool_result.get("llm_explained")),
            "audit": tool_result.get("llm_audit") or {},
            "vehicle_slots": vehicle_slots,
            "market_context": market_context,
        },
    }


def running_step_explanation(task_id: str, title: str, display_text: str) -> Dict[str, Any]:
    return {
        "step_title": title,
        "status": "running",
        "one_line_conclusion": "",
        "business_impact": display_text,
        "next_action": "完成后会给出这一步对报价的影响。",
        "key_metrics": [],
        "detail_rows": [],
        "confidence_reason": "",
        "internal_only": True,
        "customer_safe": False,
        "technical_detail": {"task_id": task_id},
    }


def _key_metrics(tool_result: Dict[str, Any]) -> List[Dict[str, str]]:
    metrics: list[Dict[str, str]] = []
    for item in tool_result.get("metric_chips") or []:
        text = str(item or "").strip()
        if not text:
            continue
        if " " in text:
            label, value = text.split(" ", 1)
        elif "：" in text:
            label, value = text.split("：", 1)
        else:
            label, value = "关键数字", text
        metrics.append({"label": label.strip("：:"), "value": value.strip()})
    return metrics


def _detail_rows(tool_result: Dict[str, Any]) -> List[Dict[str, str]]:
    result: list[Dict[str, str]] = []
    for row in tool_result.get("rows") or []:
        if not isinstance(row, list):
            continue
        values = list(row[:3])
        while len(values) < 3:
            values.append("")
        result.append({
            "dimension": str(values[0] or ""),
            "finding": str(values[1] or ""),
            "impact": str(values[2] or ""),
        })
    return result


def _strip_label(text: str, label: str) -> str:
    value = str(text or "").strip()
    prefix = f"{label}："
    return value[len(prefix):].strip() if value.startswith(prefix) else value


def _business_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "one_sentence", "summary", "headline", "judgement", "conclusion"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        listing = value.get("recommended_listing_wan")
        sale = value.get("expected_b2c_wan")
        purchase = value.get("expected_c2b_wan") or value.get("reference_price_wan")
        parts = []
        if listing not in (None, ""):
            parts.append(f"建议挂牌价{listing}万")
        if sale not in (None, ""):
            parts.append(f"预计售卖价{sale}万")
        if purchase not in (None, ""):
            parts.append(f"建议收车价{purchase}万")
        return "；".join(parts)
    if value in (None, ""):
        return ""
    return str(value).strip()
