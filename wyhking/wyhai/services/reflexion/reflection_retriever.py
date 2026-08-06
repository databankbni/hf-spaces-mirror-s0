from __future__ import annotations

from typing import Any, Dict

from .feedback_schema import vehicle_context_from_slots
from .reflection_policy import reflection_policy_audit
from .reflection_store import ReflectionStore


def retrieve_for_context(
    context: Dict[str, Any],
    *,
    top_k: int = 5,
    store: ReflectionStore | None = None,
) -> Dict[str, Any]:
    store = store or ReflectionStore()
    applied, ignored = store.retrieve_reflections(context, top_k=top_k)
    safe_applied = []
    for record in applied:
        audit = reflection_policy_audit(record)
        safe_applied.append({
            "reflection_id": record.get("reflection_id"),
            "scope": record.get("scope"),
            "failure_mode": record.get("failure_mode"),
            "lesson": record.get("lesson"),
            "next_time_instruction": record.get("next_time_instruction"),
            "apply_to": record.get("apply_to") or [],
            "confidence": record.get("confidence"),
            "match_score": record.get("match_score"),
            "evidence_summary": record.get("evidence_summary"),
            "policy_audit": audit,
        })
    return {
        "applied_reflections": safe_applied,
        "ignored_reflections": ignored,
        "reason": "相似任务反馈记忆已用于优化解释和话术，不影响模型价格。" if safe_applied else "未找到可用相似反馈记忆。",
        "price_mutation_allowed": False,
    }


def get_reflection_context(
    vehicle_slots: Dict[str, Any],
    *,
    price: Any = None,
    task_type: str = "purchase_price",
    top_k: int = 3,
    store: ReflectionStore | None = None,
) -> str:
    """Return a safe business-memory snippet for explanations/scripts only."""
    context = {
        "module": "pricing",
        "task_type": task_type,
        **vehicle_context_from_slots(vehicle_slots or {}, price),
    }
    bundle = retrieve_for_context(context, top_k=top_k, store=store)
    reflections = bundle.get("applied_reflections") or []
    if not reflections:
        return "历史反馈：暂无可用相似反馈记忆。本次价格仍以估价引擎结果为准。"
    lines = [
        "历史反馈只用于优化解释、话术、风险提示和下一步动作，不允许改写模型价格。",
        "可用反馈记忆：",
    ]
    for item in reflections[:top_k]:
        instruction = str(item.get("next_time_instruction") or item.get("lesson") or "").strip()
        if not instruction:
            continue
        scope = str(item.get("scope") or "相似任务")
        lines.append(f"- {scope}：{instruction}")
    return "\n".join(lines)
