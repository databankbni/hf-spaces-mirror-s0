from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple


PRICE_AFFECTING_FIELDS = {
    "brand",
    "series",
    "model_year",
    "first_license_date",
    "first_license_year",
    "first_license_month",
    "city",
    "color",
    "mileage_wan_km",
    "transfer_count",
    "energy_type",
    "condition_group",
    "trim",
    "raw_vehicle_text",
    "vehicle_confirmed",
    "task",
    "matched_model_id",
    "matched_series_id",
}


def flatten_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
    flat = {}
    for key, value in (slots or {}).items():
        if isinstance(value, dict) and "value" in value:
            flat[key] = value.get("value")
        else:
            flat[key] = value
    return flat


def merge_slots(current: Dict[str, Any], new_slots: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    current_flat = flatten_slots(current)
    merged = dict(current_flat)
    stale = False
    for key, slot in (new_slots or {}).items():
        value = slot.get("value") if isinstance(slot, dict) else slot
        confidence = float(slot.get("confidence") or 0) if isinstance(slot, dict) else 1.0
        if value is None or confidence < 0.4:
            continue
        old = merged.get(key)
        if old != value:
            merged[key] = value
            if key in PRICE_AFFECTING_FIELDS:
                stale = True
    return merged, stale


def hash_price_request(payload: Dict[str, Any]) -> str:
    normalized = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
