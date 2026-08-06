from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def stable_hash(value: Any, prefix: str = "") -> str:
    digest = hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


class VehicleContext(BaseModel):
    """A user-visible vehicle context.

    The identity fingerprint intentionally excludes mutable quote attributes
    such as mileage, transfer count and condition.  Those live in
    six_element_key and quote request hashes, not in the stable vehicle id.
    """

    vehicle_context_id: str
    stable_vehicle_fingerprint: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    vehicle_match: Dict[str, Any] = Field(default_factory=dict)
    six_element_key: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    active: bool = True


class QuoteRecord(BaseModel):
    quote_id: str
    vehicle_context_id: str
    quote_role: Literal["C2B", "B2C", "BOTH", "UNKNOWN"] = "UNKNOWN"
    request_hash: str = ""
    price_result: Dict[str, Any] = Field(default_factory=dict)
    evidence_card_id: str = ""
    pricing_engine_version: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class EnterpriseSessionSnapshot(BaseModel):
    session_id: str
    active_vehicle_context_id: str = ""
    active_quote_id: str = ""
    vehicle_contexts: List[VehicleContext] = Field(default_factory=list)
    quote_records: List[QuoteRecord] = Field(default_factory=list)
    module: str = "media_pricing"
    selected_city: Optional[str] = None
    last_daily_report_context: Dict[str, Any] = Field(default_factory=dict)
    last_market_opportunity_context: Dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_client_state_patch(self) -> Dict[str, Any]:
        active_vehicle = next(
            (item for item in self.vehicle_contexts if item.vehicle_context_id == self.active_vehicle_context_id),
            None,
        )
        active_quote = next((item for item in self.quote_records if item.quote_id == self.active_quote_id), None)
        latest_quote_by_vehicle: Dict[str, QuoteRecord] = {}
        for quote in self.quote_records:
            latest_quote_by_vehicle[quote.vehicle_context_id] = quote
        patch: Dict[str, Any] = {
            "module": self.module,
            "selectedBusinessModule": self.module,
            "selectedCity": self.selected_city,
            "enterpriseSession": self.model_dump(mode="json"),
            "vehicle_history": [
                {
                    "vehicle_context_id": item.vehicle_context_id,
                    "stable_vehicle_fingerprint": item.stable_vehicle_fingerprint,
                    "slots": item.slots,
                    "vehicle_match": item.vehicle_match,
                    "pricing_result": latest_quote_by_vehicle.get(item.vehicle_context_id).price_result
                    if latest_quote_by_vehicle.get(item.vehicle_context_id)
                    else {},
                    "quote_id": latest_quote_by_vehicle.get(item.vehicle_context_id).quote_id
                    if latest_quote_by_vehicle.get(item.vehicle_context_id)
                    else "",
                    "saved_at": item.updated_at,
                }
                for item in self.vehicle_contexts
            ],
            "quote_history": [
                {
                    "quote_id": item.quote_id,
                    "vehicle_context_id": item.vehicle_context_id,
                    "pricing_result": item.price_result,
                    "created_at": item.created_at,
                }
                for item in self.quote_records
            ],
        }
        if active_vehicle:
            patch["current_slots"] = active_vehicle.slots
            patch["current_vehicle_match"] = active_vehicle.vehicle_match
            patch["active_vehicle_context_id"] = active_vehicle.vehicle_context_id
            patch["stable_vehicle_fingerprint"] = active_vehicle.stable_vehicle_fingerprint
        if active_quote:
            patch["current_pricing_result"] = active_quote.price_result
            patch["active_quote_id"] = active_quote.quote_id
            patch["evidence_card_id"] = active_quote.evidence_card_id
        if self.last_daily_report_context:
            patch["lastDailyReportContext"] = self.last_daily_report_context
        if self.last_market_opportunity_context:
            patch["lastMarketOpportunityContext"] = self.last_market_opportunity_context
        return patch


def build_vehicle_identity(slots: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "brand": slots.get("brand") or "",
        "series": slots.get("series") or "",
        "model_year": slots.get("model_year") or "",
        "trim": slots.get("trim") or slots.get("model") or "",
        "color": slots.get("color") or "",
    }


def build_six_element_key(slots: Dict[str, Any]) -> str:
    fields = {
        "brand": slots.get("brand") or "",
        "series": slots.get("series") or "",
        "model_year": slots.get("model_year") or "",
        "trim": slots.get("trim") or slots.get("model") or "",
        "city": slots.get("city") or "",
        "color": slots.get("color") or "",
        "mileage": slots.get("mileage_wan_km") or slots.get("mileage") or "",
        "transfer": slots.get("transfer_count") or slots.get("transfer") or "",
    }
    return "|".join(f"{key}={value}" for key, value in fields.items())
