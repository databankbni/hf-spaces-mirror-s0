from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .feedback_schema import (
    BusinessOutcome,
    FeedbackRecord,
    FeedbackTag,
    ReflectionMemory,
    ReflectionScope,
    now_iso,
    vehicle_context_from_slots,
)
from .reflection_policy import sanitize_instruction


def generate_reflection(
    feedback: FeedbackRecord,
    *,
    task_state: Dict[str, Any] | None = None,
    final_result: Dict[str, Any] | None = None,
    report_snapshot: Dict[str, Any] | None = None,
) -> ReflectionMemory:
    task_state = task_state or {}
    final_result = final_result or {}
    report_snapshot = report_snapshot or {}
    ctx = vehicle_context_from_slots(
        feedback.vehicle_slots,
        feedback.purchase_price or feedback.adopted_purchase_price or _nested(report_snapshot, ["point_price_yuan"]),
    )
    failure_mode, lesson, instruction, apply_to, confidence = _instruction_for_feedback(feedback)
    scope = _scope_for_feedback(feedback, ctx)
    evidence_summary = _evidence_summary(feedback, final_result, report_snapshot)
    return ReflectionMemory(
        reflection_id=f"reflection_{uuid.uuid4().hex[:12]}",
        created_at=now_iso(),
        source_feedback_id=feedback.feedback_id,
        scope=scope,
        module=feedback.module or "pricing",
        task_type=feedback.task_type or "pricing",
        city=ctx.get("city", ""),
        brand=ctx.get("brand", ""),
        series=ctx.get("series", ""),
        price_band=ctx.get("price_band", ""),
        failure_mode=failure_mode,
        lesson=lesson,
        next_time_instruction=sanitize_instruction(instruction, 80),
        apply_to=apply_to,
        confidence=confidence,
        decay_days=45 if feedback.business_outcome in {BusinessOutcome.ACCEPTED.value, BusinessOutcome.REJECTED.value} else 30,
        evidence_summary=evidence_summary,
        is_active=True,
        tags=feedback.tags,
    )


def _instruction_for_feedback(feedback: FeedbackRecord) -> tuple[str, str, str, List[str], float]:
    tags = set(feedback.tags or [])
    comment = feedback.comment + " " + feedback.customer_reject_reason
    if FeedbackTag.VEHICLE_RECOGNITION_WRONG.value in tags:
        return (
            "车型识别错",
            "用户更关注标准车型和款型确认。",
            "下次先确认标准车型和款型，不要带旧车型直接出报告。",
            ["task_plan", "stage_explanation", "final_report"],
            0.82,
        )
    if FeedbackTag.COMPARABLE_WRONG.value in tags:
        return (
            "可比车不准",
            "可比证据需要更严格贴合同车系/配置/城市。",
            "下次先说明可比车匹配口径，弱匹配只放详情不放主结论。",
            ["task_execution", "final_report", "evidence_priority"],
            0.78,
        )
    if FeedbackTag.SCRIPT_NOT_USEFUL.value in tags or "话术" in comment:
        return (
            "话术不好用",
            "客户沟通需要更口语，少暴露内部数据。",
            "下次对客话术少讲内部数据，多讲检测、整备和可申请空间。",
            ["customer_script", "customer_faq"],
            0.8,
        )
    if FeedbackTag.PRICE_TOO_HIGH.value in tags:
        return (
            "价格偏高反馈",
            "用户认为报价解释缺少保守边界。",
            "下次解释偏高质疑时强调车况、周转和整备风险，价格仍以模型为准。",
            ["final_report", "risk_hint", "customer_script"],
            0.65,
        )
    if FeedbackTag.PRICE_TOO_LOW.value in tags:
        return (
            "价格偏低反馈",
            "用户认为报价解释缺少加分项。",
            "下次解释偏低质疑时先讲里程配置等加分项，再说明检测后可申请。",
            ["final_report", "customer_script"],
            0.65,
        )
    if FeedbackTag.SALE_PRICE_WRONG.value in tags:
        return (
            "售车价不准",
            "售车价解释需要区分挂牌和成交。",
            "下次售车价解释先区分挂牌价和成交价，再讲周转风险。",
            ["final_report", "customer_script"],
            0.7,
        )
    if FeedbackTag.PROFIT_WRONG.value in tags or FeedbackTag.CALCULATOR_ADJUSTED.value in tags:
        return (
            "利润测算不准",
            "利润判断需要显性展示整备和运营成本。",
            "下次利润测算优先展示整备、过户和运营成本，不只看价差。",
            ["profit_calculator", "final_report"],
            0.76,
        )
    if feedback.business_outcome == BusinessOutcome.REJECTED.value:
        return (
            "客户拒绝",
            "客户拒绝时要先处理价格心理预期。",
            "下次先区分挂牌价和成交价，再把检测后可申请空间说清楚。",
            ["customer_script", "customer_faq"],
            0.74,
        )
    if feedback.business_outcome == BusinessOutcome.ACCEPTED.value:
        return (
            "客户接受",
            "本次话术结构可复用。",
            "相似条件下可保留先认可车况、再讲检测和整备的沟通顺序。",
            ["customer_script"],
            0.7,
        )
    if FeedbackTag.NOT_USEFUL.value in tags:
        return (
            "结果没帮助",
            "业务结论需要更直接。",
            "下次首屏先回答能不能收、先报多少、下一步怎么推进。",
            ["task_plan", "final_report"],
            0.62,
        )
    return (
        "正向反馈",
        "本次结构可作为相似任务参考。",
        "相似任务保持先给业务结论，再展开内部依据和话术。",
        ["final_report"],
        0.55,
    )


def _scope_for_feedback(feedback: FeedbackRecord, ctx: Dict[str, str]) -> str:
    tags = set(feedback.tags or [])
    if FeedbackTag.VEHICLE_RECOGNITION_WRONG.value in tags or FeedbackTag.COMPARABLE_WRONG.value in tags:
        return ReflectionScope.CITY_SERIES.value if ctx.get("city") and ctx.get("series") else ReflectionScope.VEHICLE_SERIES.value
    if FeedbackTag.SCRIPT_NOT_USEFUL.value in tags:
        return ReflectionScope.TASK_TYPE.value
    if ctx.get("series"):
        return ReflectionScope.CITY_SERIES.value if ctx.get("city") else ReflectionScope.VEHICLE_SERIES.value
    if ctx.get("price_band"):
        return ReflectionScope.PRICE_BAND.value
    return ReflectionScope.TASK_TYPE.value


def _evidence_summary(
    feedback: FeedbackRecord,
    final_result: Dict[str, Any],
    report_snapshot: Dict[str, Any],
) -> str:
    parts = []
    if feedback.tags:
        parts.append("标签：" + "、".join(feedback.tags[:4]))
    if feedback.business_outcome and feedback.business_outcome != BusinessOutcome.UNKNOWN.value:
        parts.append(f"结果：{feedback.business_outcome}")
    if feedback.comment:
        parts.append("备注：" + feedback.comment[:60])
    price = feedback.purchase_price or _nested(report_snapshot, ["point_price_yuan"]) or _nested(final_result, ["metrics", "point_price"])
    if price:
        parts.append(f"当次价格：{price}")
    return "；".join(parts)[:220]


def _nested(data: Dict[str, Any], path: List[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur
