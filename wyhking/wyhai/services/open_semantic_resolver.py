from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class SemanticResolution:
    slots: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


BRAND_ORIGIN_ALIASES = {
    "德国": {"德国", "德系", "德国品牌", "德国车", "德系车", "德系品牌"},
    "日本": {"日本", "日系", "日本品牌", "日本车", "日系车", "日系品牌"},
    "美国": {"美国", "美系", "美国品牌", "美国车", "美系车", "美系品牌"},
    "中国": {"中国", "国产", "自主", "中国品牌", "国产车", "自主品牌"},
    "韩国": {"韩国", "韩系", "韩国品牌", "韩系车"},
    "法国": {"法国", "法系", "法国品牌", "法系车"},
    "英国": {"英国", "英系", "英国品牌", "英系车"},
    "意大利": {"意大利", "意系", "意大利品牌", "意系车"},
    "瑞典": {"瑞典", "瑞典品牌", "北欧品牌"},
}

OPEN_WORLD_VEHICLE_REFERENCES = [
    {
        "patterns": [r"美国总统.{0,6}座驾", r"总统.{0,4}座驾", r"the\s*beast"],
        "slots": {"brand": "凯迪拉克"},
        "constraints": {
            "referenced_entity": "美国总统座驾",
            "implied_brand": "凯迪拉克",
            "semantic_source": "bounded_domain_reference",
        },
        "confidence": 0.78,
        "reason": "open_world_reference_to_cadillac",
    },
    {
        "patterns": [r"教皇.{0,4}座驾", r"pope\s*mobile"],
        "constraints": {
            "referenced_entity": "教皇座驾",
            "semantic_source": "bounded_domain_reference",
            "requires_clarification": True,
        },
        "confidence": 0.62,
        "reason": "open_world_reference_ambiguous_vehicle",
    },
]


def _compact(text: Any) -> str:
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", str(text or "")).lower()


def resolve_open_semantic(text: Any) -> SemanticResolution | None:
    raw = str(text or "")
    compact = _compact(raw)
    if not compact:
        return None

    slots: Dict[str, Any] = {}
    constraints: Dict[str, Any] = {}
    confidence = 0.0
    reasons: list[str] = []

    for item in OPEN_WORLD_VEHICLE_REFERENCES:
        if any(re.search(pattern, compact, flags=re.I) for pattern in item["patterns"]):
            slots.update(item.get("slots") or {})
            constraints.update(item.get("constraints") or {})
            confidence = max(confidence, float(item.get("confidence") or 0))
            reasons.append(str(item.get("reason") or "open_world_reference"))

    for country, aliases in BRAND_ORIGIN_ALIASES.items():
        if any(_compact(alias) in compact for alias in aliases):
            constraints["brand_origin_country"] = country
            constraints["brand_origin_alias_matched"] = next(
                alias for alias in aliases if _compact(alias) in compact
            )
            confidence = max(confidence, 0.82)
            reasons.append("brand_origin_constraint")
            break

    if not slots and not constraints:
        return None
    constraints.setdefault("semantic_resolution_version", "open_semantic_resolver_v1")
    return SemanticResolution(
        slots=slots,
        constraints=constraints,
        confidence=round(confidence or 0.55, 4),
        reason="|".join(dict.fromkeys(reasons)),
    )
