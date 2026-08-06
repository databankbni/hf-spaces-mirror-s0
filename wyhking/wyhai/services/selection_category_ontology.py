from __future__ import annotations

import re
from typing import Any

from .brand_tier import extract_brand_tier_from_text
from .vehicle_taxonomy import (
    normalize_energy_subtype,
    normalize_manufacturer_attribute,
    normalize_vehicle_category,
)


# These are production filters backed by the internal 90-day data and the
# Dongchedi taxonomy/ranking evidence index.  UI buttons are only convenient
# presets; natural-language queries may combine any of these dimensions.
SELECTION_CATEGORY_ONTOLOGY = {
    "brand_scope": {
        "label": "品牌阵营",
        "values": ("自主", "合资", "豪华", "豪华新能源", "进口"),
    },
    "energy_subtype": {
        "label": "能源类型",
        "values": ("燃油", "新能源", "纯电", "插混", "增程"),
    },
    "vehicle_category": {
        "label": "车身类别",
        "values": ("轿车", "SUV", "MPV", "皮卡", "微面", "轻客", "微卡"),
    },
    "price_band": {
        "label": "预算/成交价带",
        "values": ("任意上限", "任意下限", "任意区间", "某价格附近"),
    },
    "location": {
        "label": "地域",
        "values": ("全国", "任意已覆盖城市"),
    },
    "vehicle_identity": {
        "label": "车辆身份",
        "values": ("品牌", "品牌组", "车系", "车型年款"),
    },
    "business_state": {
        "label": "经营状态",
        "values": ("机会", "风险", "高周转", "低价机会", "价格下行", "供需状态"),
    },
}


def extract_selection_category_constraints(text: Any) -> dict[str, str]:
    raw = str(text or "")
    constraints: dict[str, str] = {}

    brand_tier = extract_brand_tier_from_text(raw)
    if brand_tier:
        constraints["brand_tier"] = brand_tier
    if re.search(r"进口(?:车|品牌|车系|车型|阵营)?", raw):
        constraints["manufacturer_attribute"] = "进口"

    energy_subtype = ""
    for pattern, label in (
        (r"增程|EREV", "增程"),
        (r"插混|插电混|PHEV|DM-?i|EM-?P", "插混"),
        (r"纯电|BEV|电动车", "纯电"),
        (r"综合新能源|新能源", "新能源"),
        (r"燃油车|燃油|油车|汽油车|柴油车", "燃油"),
    ):
        if re.search(pattern, raw, flags=re.I):
            energy_subtype = label
            break
    energy_subtype = normalize_energy_subtype(energy_subtype)
    if energy_subtype:
        constraints["energy_subtype"] = energy_subtype
        constraints["fuel_type"] = "新能源" if energy_subtype in {"新能源", "纯电", "插混", "增程"} else "燃油车"

    vehicle_category = ""
    for pattern, label in (
        (r"皮卡|pickup", "皮卡"),
        (r"微型?面包车|微面|面包车", "微面"),
        (r"轻型客车|轻客", "轻客"),
        (r"微型?卡车|微卡|小卡", "微卡"),
        (r"MPV|商务车", "MPV"),
        (r"SUV", "SUV"),
        (r"轿车", "轿车"),
    ):
        if re.search(pattern, raw, flags=re.I):
            vehicle_category = label
            break
    vehicle_category = normalize_vehicle_category(vehicle_category)
    if vehicle_category:
        constraints["body_category"] = vehicle_category
        constraints["vehicle_type"] = vehicle_category
        if vehicle_category in {"轿车", "SUV", "MPV"}:
            constraints["selection_filter"] = vehicle_category

    manufacturer = normalize_manufacturer_attribute(constraints.get("manufacturer_attribute"))
    if manufacturer:
        constraints["manufacturer_attribute"] = manufacturer
    return constraints


def describe_category_scope(constraints: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for key, label in (
        ("brand_tier", "品牌阵营"),
        ("manufacturer_attribute", "产销属性"),
        ("energy_subtype", "能源"),
        ("body_category", "车身"),
    ):
        value = str(constraints.get(key) or "").strip()
        if value:
            labels.append(f"{label}：{value}")
    return labels
