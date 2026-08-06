from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


PRICE_MUTATION_FORBIDDEN = (
    "改模型价",
    "覆盖价格",
    "直接降价",
    "直接涨价",
    "无条件压价",
    "无条件加价",
    "always lower",
    "always raise",
)

CUSTOMER_FORBIDDEN_WORDS = (
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


def sanitize_instruction(text: str, limit: int = 80) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\s+", " ", value)
    for word in PRICE_MUTATION_FORBIDDEN:
        value = value.replace(word, "")
    value = value.replace("直接改价", "改进解释")
    value = value.replace("按反馈改价", "按反馈优化解释")
    return value[:limit]


def reflection_policy_audit(reflection: Dict[str, Any]) -> List[str]:
    instruction = str(reflection.get("next_time_instruction") or "")
    audit = ["反馈记忆只影响解释、话术、证据优先级和风险提示。", "是否影响价格：否"]
    if any(word in instruction for word in PRICE_MUTATION_FORBIDDEN):
        audit.append("发现危险改价指令，已拒绝。")
    return audit


def can_treat_as_transaction_fact(feedback: Dict[str, Any]) -> bool:
    outcome = str(feedback.get("business_outcome") or feedback.get("businessOutcome") or "")
    return outcome in {"accepted", "adopted", "transacted"}


def ensure_no_price_mutation(before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[bool, List[str]]:
    keys = [
        "point_price_yuan",
        "lower_yuan",
        "upper_yuan",
        "baseline_price_yuan",
        "purchase_price",
        "sale_price",
    ]
    changed = []
    for key in keys:
        if key in before or key in after:
            if before.get(key) != after.get(key):
                changed.append(key)
    return (not changed, changed)


def scrub_customer_copy(text: str, internal_numbers: Iterable[str] = ()) -> str:
    value = str(text or "")
    for word in CUSTOMER_FORBIDDEN_WORDS:
        value = value.replace(word, "")
    for number in internal_numbers:
        if number:
            value = value.replace(str(number), "这个价")
    value = re.sub(r"\s+", " ", value).strip()
    return value
