from __future__ import annotations

import json
import re
from typing import Any, Dict

from ..llm_client import Qwen3LocalClient, extract_json_object


TECH_PATTERN = re.compile(r"算法|模型|RAG|workflow|特征|tool[_\s-]?name|intent[_\s-]?code", re.I)


def explain_stage(
    *,
    client: Qwen3LocalClient,
    enabled: bool,
    disabled_reason: str,
    message: str,
    table: Dict[str, Any],
    facts: Dict[str, Any],
) -> Dict[str, Any]:
    """Turn one deterministic tool result into a business-readable stage card.

    The table/chips stay deterministic. The LLM may only explain what the
    existing numbers mean; if it fails, the returned card is explicitly marked
    as fallback with llm_explained=false.
    """
    base = _fallback_explanation(table)
    audit = {
        "stage": f"stage_explainer:{table.get('task_id')}",
        "used": False,
        "model": client.config_snapshot().get("model"),
        "fallback_reason": disabled_reason,
    }
    if not enabled:
        return {**base, "llm_audit": audit}

    prompt = (
        "你是一线二手车收车 Agent 的阶段解释器。"
        "工具已经给出事实，LLM 只负责解释业务含义，不能改价格、样本数、百分比、日期或来源。"
        "不得编造数字，不得写算法、模型、RAG、workflow、特征等技术词。"
        "每句话短，面向一线收车业务人员。"
        "输出 JSON："
        "{\"stage_conclusion\":\"\",\"why_trust\":\"\",\"business_meaning\":\"\","
        "\"price_impact\":\"\",\"action\":\"\",\"need_review\":\"\"}"
    )
    payload = {
        "user_message": message,
        "task_name": table.get("title"),
        "vehicle_slots": facts.get("six_elements") or facts.get("slots") or {},
        "tool_result": {
            "metric_chips": table.get("metric_chips") or [],
            "columns": table.get("columns") or [],
            "rows": table.get("rows") or [],
            "details": table.get("details") or "",
            "sources": table.get("sources") or [],
            "daily_note": table.get("daily_note") or "",
        },
        "pricing_result": {
            "point_price_yuan": facts.get("point_price_yuan"),
            "lower_yuan": facts.get("lower_yuan"),
            "upper_yuan": facts.get("upper_yuan"),
            "baseline_price_yuan": facts.get("baseline_price_yuan"),
            "candidate_count": facts.get("candidate_count"),
            "confidence": facts.get("confidence"),
        },
        "market_result": {
            "market_state": facts.get("market_state") or {},
            "market_indicator": facts.get("market_indicator") or {},
        },
        "daily_report_result": facts.get("daily_report") or {},
        "constraints": {
            "no_fake_numbers": True,
            "no_price_rewrite_by_llm": True,
            "audience": "一线收车业务人员",
            "max_rows": 3,
            "max_sentence_length": 40,
        },
    }
    result = client.structured_extract(prompt, payload)
    audit.update({"latency_ms": result.latency_ms, "model": result.model or audit["model"]})
    parsed = extract_json_object(result.content) if result.ok else None
    if not isinstance(parsed, dict):
        audit.update({"fallback_reason": result.fallback_reason or "LLM returned non-json"})
        return {**base, "llm_audit": audit}

    allowed_text = json.dumps(payload, ensure_ascii=False, default=str)
    refined = dict(base)
    accepted_any = False
    for field, limit in (
        ("stage_conclusion", 72),
        ("why_trust", 96),
        ("business_meaning", 88),
        ("price_impact", 72),
        ("action", 72),
        ("need_review", 96),
    ):
        candidate = _clip_text(parsed.get(field), limit)
        if _safe_business_copy(candidate, allowed_text):
            refined[field] = candidate
            accepted_any = True
    if accepted_any:
        refined["llm_explained"] = True
        audit.update({"used": True, "fallback_reason": ""})
    else:
        audit.update({"fallback_reason": "LLM copy failed grounding checks"})
    refined["llm_audit"] = audit
    return refined


def _fallback_explanation(table: Dict[str, Any]) -> Dict[str, Any]:
    title = str(table.get("title") or "")
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    sources = [str(item) for item in (table.get("sources") or []) if item]
    first_impact = ""
    if rows and isinstance(rows[0], list) and len(rows[0]) >= 3:
        first_impact = str(rows[0][2])
    why_trust = _why_trust_from_table(title, rows, sources, table.get("daily_note"))
    return {
        "stage_conclusion": str(table.get("stage_conclusion") or table.get("summary") or ""),
        "why_trust": why_trust,
        "business_meaning": _business_meaning_from_title(title),
        "price_impact": first_impact or "只作为报价参考，不单独改写价格。",
        "action": _action_from_title(title),
        "need_review": "",
        "trust_sources": sources[:4],
        "llm_explained": False,
    }


def _why_trust_from_table(title: str, rows: list[Any], sources: list[str], daily_note: Any) -> str:
    source_text = "、".join(sources[:3]) or "后端工具结果"
    if "可比车" in title:
        count = _row_finding(rows, "证据数量")
        interval = _row_finding(rows, "价格区间")
        return f"为什么可信：{source_text}提供{count or '样本'}和{interval or '价格范围'}，但仍需看分散度。"
    if "差异" in title:
        return f"为什么可信：{source_text}已覆盖车辆七要素，只解释方向，不编分项金额。"
    if "行情" in title:
        note = str(daily_note or "日报暂无强相关事件")
        return f"为什么可信：{source_text}只用于补充风险说明；{note}"
    if "补全" in title or "字段" in title:
        return "为什么需要谨慎：车辆七要素不完整，补齐前不能输出可靠报价。"
    return f"为什么可信：{source_text}为本阶段直接来源。"


def _business_meaning_from_title(title: str) -> str:
    if "可比车" in title:
        return "业务含义：先确认市场参考范围，不把中位价直接当收车价。"
    if "差异" in title:
        return "业务含义：看本车和相近样本差异，决定报价应偏稳还是可上探。"
    if "行情" in title:
        return "业务含义：行情只判断能不能追价，不直接替代单车估价。"
    if "报价" in title:
        return "业务含义：把用户报价放进建议价和上限里判断能不能继续谈。"
    return "业务含义：先把证据转成可执行的报价判断。"


def _action_from_title(title: str) -> str:
    if "可比车" in title:
        return "下一步：继续核对本车七要素差异，再校验完整价格梯度。"
    if "差异" in title:
        return "下一步：用车辆差异解释价格修正，并确定最高收车价。"
    if "行情" in title:
        return "下一步：客户坚持高价时，用行情波动和周转风险压价。"
    if "补全" in title or "字段" in title:
        return "下一步：先补齐缺失字段，再重新估价。"
    return "下一步：结合车况检测做人工复核。"


def _row_finding(rows: list[Any], key: str) -> str:
    for row in rows:
        if isinstance(row, list) and len(row) >= 2 and str(row[0]) == key:
            return str(row[1])
    return ""


def _safe_business_copy(candidate: str, allowed_text: str) -> bool:
    if not candidate or TECH_PATTERN.search(candidate):
        return False
    allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?", allowed_text))
    candidate_numbers = set(re.findall(r"\d+(?:\.\d+)?", candidate))
    return candidate_numbers.issubset(allowed_numbers)


def _clip_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip("，；。 ") + "…"
