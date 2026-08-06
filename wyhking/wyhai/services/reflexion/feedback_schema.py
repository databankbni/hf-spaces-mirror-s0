from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class FeedbackTag(str, Enum):
    USEFUL = "有用"
    NOT_USEFUL = "没用"
    PRICE_TOO_HIGH = "价格偏高"
    PRICE_TOO_LOW = "价格偏低"
    SCRIPT_NOT_USEFUL = "话术不好用"
    COMPARABLE_WRONG = "可比车不准"
    VEHICLE_RECOGNITION_WRONG = "车型识别错"
    SALE_PRICE_WRONG = "售车价不准"
    PROFIT_WRONG = "利润测算不准"
    CUSTOMER_ACCEPTED = "客户已接受"
    CUSTOMER_REJECTED = "客户已拒绝"
    CALCULATOR_ADJUSTED = "calculator_adjusted"


class BusinessOutcome(str, Enum):
    UNKNOWN = "unknown"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ADOPTED = "adopted"
    TRANSACTED = "transacted"
    CALCULATOR_ADJUSTED = "calculator_adjusted"


class ReflectionScope(str, Enum):
    GLOBAL = "global"
    MODULE = "module"
    TASK_TYPE = "task_type"
    VEHICLE_SERIES = "vehicle_series"
    CITY_SERIES = "city_series"
    PRICE_BAND = "price_band"


@dataclass
class FeedbackRecord:
    feedback_id: str
    created_at: str
    module: str
    task_type: str
    trace_id: str = ""
    task_id: str = ""
    report_id: str = ""
    user_query: str = ""
    vehicle_slots: Dict[str, Any] = field(default_factory=dict)
    purchase_price: Optional[float] = None
    purchase_price_upper: Optional[float] = None
    sale_price: Optional[float] = None
    system_purchase_price: Optional[float] = None
    user_adjusted_purchase_price: Optional[float] = None
    system_sale_price: Optional[float] = None
    user_adjusted_sale_price: Optional[float] = None
    actual_purchase_price: Optional[float] = None
    actual_sale_price: Optional[float] = None
    gross_profit: Optional[float] = None
    estimated_profit: Optional[float] = None
    calculator_snapshot: Dict[str, Any] = field(default_factory=dict)
    vehicle_fingerprint: str = ""
    tags: List[str] = field(default_factory=list)
    comment: str = ""
    adopted_purchase_price: Optional[float] = None
    adopted_sale_price: Optional[float] = None
    actual_reconditioning_cost: Optional[float] = None
    accepted_by_customer: Optional[bool] = None
    business_outcome: str = BusinessOutcome.UNKNOWN.value
    customer_reject_reason: str = ""
    free_text: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: Dict[str, Any],
        *,
        fallback_id: str | None = None,
        created_at: str | None = None,
        trace: Dict[str, Any] | None = None,
    ) -> "FeedbackRecord":
        trace = trace or {}
        vehicle_slots = _as_dict(
            payload.get("vehicle_slots")
            or payload.get("vehicleSlots")
            or payload.get("slots")
            or _nested(trace, ["pricing_report_context", "vehicle_slots"])
            or trace.get("slots")
        )
        tags = normalize_tags(payload)
        outcome = normalize_outcome(payload, tags)
        return cls(
            feedback_id=str(payload.get("feedback_id") or payload.get("feedbackId") or fallback_id or uuid.uuid4()),
            created_at=str(payload.get("created_at") or payload.get("createdAt") or created_at or now_iso()),
            module=str(payload.get("module") or payload.get("businessModule") or "pricing"),
            task_type=normalize_task_type(payload.get("task_type") or payload.get("taskType") or payload.get("businessIntent") or "pricing"),
            trace_id=str(payload.get("trace_id") or payload.get("traceId") or trace.get("traceId") or ""),
            task_id=str(payload.get("task_id") or payload.get("taskId") or ""),
            report_id=str(payload.get("report_id") or payload.get("reportId") or ""),
            user_query=str(payload.get("user_query") or payload.get("userQuestion") or trace.get("userQuery") or ""),
            vehicle_slots=vehicle_slots,
            purchase_price=_num(payload.get("purchase_price") or payload.get("purchasePrice") or payload.get("aiC2bPrice")),
            purchase_price_upper=_num(payload.get("purchase_price_upper") or payload.get("purchasePriceUpper") or payload.get("aiPriceHigh")),
            sale_price=_num(payload.get("sale_price") or payload.get("salePrice") or payload.get("aiB2cPrice")),
            system_purchase_price=_num(payload.get("system_purchase_price") or payload.get("systemPurchasePrice")),
            user_adjusted_purchase_price=_num(payload.get("user_adjusted_purchase_price") or payload.get("userAdjustedPurchasePrice")),
            system_sale_price=_num(payload.get("system_sale_price") or payload.get("systemSalePrice")),
            user_adjusted_sale_price=_num(payload.get("user_adjusted_sale_price") or payload.get("userAdjustedSalePrice")),
            actual_purchase_price=_num(payload.get("actual_purchase_price") or payload.get("actualPurchasePrice")),
            actual_sale_price=_num(payload.get("actual_sale_price") or payload.get("actualSalePrice")),
            gross_profit=_num(payload.get("gross_profit") or payload.get("grossProfit")),
            estimated_profit=_num(payload.get("estimated_profit") or payload.get("estimatedProfit") or payload.get("gross_profit") or payload.get("grossProfit")),
            calculator_snapshot=_as_dict(payload.get("calculator_snapshot") or payload.get("calculatorSnapshot")),
            vehicle_fingerprint=str(payload.get("vehicle_fingerprint") or payload.get("vehicleFingerprint") or ""),
            tags=tags,
            comment=str(payload.get("comment") or payload.get("customFeedback") or ""),
            adopted_purchase_price=_num(payload.get("adopted_purchase_price") or payload.get("adoptedPurchasePrice") or payload.get("userFinalPrice")),
            adopted_sale_price=_num(payload.get("adopted_sale_price") or payload.get("adoptedSalePrice")),
            actual_reconditioning_cost=_num(payload.get("actual_reconditioning_cost") or payload.get("actualReconditioningCost")),
            accepted_by_customer=_bool(payload.get("accepted_by_customer") if "accepted_by_customer" in payload else payload.get("acceptedByCustomer")),
            business_outcome=outcome,
            customer_reject_reason=str(payload.get("customer_reject_reason") or payload.get("customerRejectReason") or ""),
            free_text=str(payload.get("free_text") or payload.get("freeText") or payload.get("comment") or payload.get("customFeedback") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackRecord":
        known = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{key: data.get(key) for key in known})


@dataclass
class ReflectionMemory:
    reflection_id: str
    created_at: str
    source_feedback_id: str
    scope: str
    module: str
    task_type: str
    city: str = ""
    brand: str = ""
    series: str = ""
    price_band: str = ""
    failure_mode: str = ""
    lesson: str = ""
    next_time_instruction: str = ""
    apply_to: List[str] = field(default_factory=list)
    confidence: float = 0.55
    decay_days: int = 30
    evidence_summary: str = ""
    is_active: bool = True
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReflectionMemory":
        known = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        values = {key: data.get(key) for key in known}
        values["apply_to"] = list(values.get("apply_to") or [])
        values["tags"] = list(values.get("tags") or [])
        values["is_active"] = bool(values.get("is_active", True))
        values["confidence"] = float(values.get("confidence") or 0.55)
        values["decay_days"] = int(values.get("decay_days") or 30)
        return cls(**values)


def normalize_tags(payload: Dict[str, Any]) -> List[str]:
    raw = (
        payload.get("tags")
        or payload.get("selectedTags")
        or payload.get("feedbackTags")
        or payload.get("feedbackTag")
        or payload.get("tag")
        or []
    )
    if isinstance(raw, str):
        raw = [raw]
    tags: List[str] = []
    for item in raw or []:
        text = str(item or "").strip()
        if not text:
            continue
        alias = {
            "helpful": FeedbackTag.USEFUL.value,
            "not_helpful": FeedbackTag.NOT_USEFUL.value,
            "price_high": FeedbackTag.PRICE_TOO_HIGH.value,
            "price_low": FeedbackTag.PRICE_TOO_LOW.value,
            "script_bad": FeedbackTag.SCRIPT_NOT_USEFUL.value,
            "comparable_wrong": FeedbackTag.COMPARABLE_WRONG.value,
            "vehicle_wrong": FeedbackTag.VEHICLE_RECOGNITION_WRONG.value,
            "sale_price_wrong": FeedbackTag.SALE_PRICE_WRONG.value,
            "profit_wrong": FeedbackTag.PROFIT_WRONG.value,
            "accepted": FeedbackTag.CUSTOMER_ACCEPTED.value,
            "rejected": FeedbackTag.CUSTOMER_REJECTED.value,
        }.get(text, text)
        if alias not in tags:
            tags.append(alias)
    return tags


def normalize_outcome(payload: Dict[str, Any], tags: List[str]) -> str:
    raw = str(payload.get("business_outcome") or payload.get("businessOutcome") or "").strip()
    if raw:
        mapping = {
            "客户已接受": BusinessOutcome.ACCEPTED.value,
            "客户已拒绝": BusinessOutcome.REJECTED.value,
            "成交": BusinessOutcome.TRANSACTED.value,
            "采纳": BusinessOutcome.ADOPTED.value,
        }
        return mapping.get(raw, raw)
    if FeedbackTag.CUSTOMER_ACCEPTED.value in tags:
        return BusinessOutcome.ACCEPTED.value
    if FeedbackTag.CUSTOMER_REJECTED.value in tags:
        return BusinessOutcome.REJECTED.value
    if FeedbackTag.CALCULATOR_ADJUSTED.value in tags:
        return BusinessOutcome.CALCULATOR_ADJUSTED.value
    return BusinessOutcome.UNKNOWN.value


def normalize_task_type(value: Any) -> str:
    text = str(value or "purchase_price").strip()
    mapping = {
        "pricing": "purchase_price",
        "media_pricing": "purchase_price",
        "valuation": "purchase_price",
        "estimate_vehicle_value": "purchase_price",
        "recommend_purchase_price": "purchase_price",
        "judge_purchase_price": "purchase_price",
        "c2b": "purchase_price",
        "listing_price": "listing_price",
        "judge_listing_price": "listing_price",
        "sale_price": "listing_price",
        "b2c": "listing_price",
        "customer_offer": "customer_offer",
        "judge_customer_offer": "customer_offer",
    }
    return mapping.get(text, text)


def price_band_from_price(price: Any) -> str:
    value = _num(price)
    if not value:
        return ""
    wan = value / 10000 if value > 1000 else value
    if wan < 5:
        return "0-5万"
    if wan < 10:
        return "5-10万"
    if wan < 15:
        return "10-15万"
    if wan < 20:
        return "15-20万"
    if wan < 30:
        return "20-30万"
    if wan < 50:
        return "30-50万"
    return "50万以上"


def vehicle_context_from_slots(slots: Dict[str, Any], price: Any = None) -> Dict[str, str]:
    standard = str(slots.get("standard_vehicle") or slots.get("vehicle_confirm") or slots.get("model") or "")
    return {
        "city": str(slots.get("city") or "").strip(),
        "brand": str(slots.get("brand") or "").strip() or _first_token(standard),
        "series": str(slots.get("series") or "").strip() or _guess_series(standard),
        "price_band": price_band_from_price(price),
    }


def _nested(data: Dict[str, Any], path: List[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("万", "").replace(",", "").strip())
    except Exception:
        return None


def _bool(value: Any) -> Optional[bool]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "accepted", "accept", "是", "已接受"}:
        return True
    if text in {"false", "0", "no", "rejected", "reject", "否", "已拒绝"}:
        return False
    return None


def _first_token(text: str) -> str:
    return text.split()[0] if text.split() else ""


def _guess_series(text: str) -> str:
    tokens = text.split()
    if len(tokens) >= 2:
        return tokens[1]
    return text[:12]
