from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .enterprise_agent_schemas_v21 import (
    EnterpriseSessionSnapshot,
    QuoteRecord,
    VehicleContext,
    build_six_element_key,
    build_vehicle_identity,
    stable_hash,
)
from .interaction_state import flatten_slots


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LOG = ROOT / "data/agent_state/enterprise_agent_v21_events.jsonl"


class EnterpriseAgentStateStoreV21:
    """Session, vehicle and quote lifecycle store.

    Current implementation is an in-process index plus append-only JSONL audit
    log.  The public methods are deliberately storage-agnostic so the same
    contract can move to PostgreSQL/Redis without touching intent or pricing.
    """

    def __init__(self, event_log_path: Path | None = None, max_sessions: int = 1000) -> None:
        self.event_log_path = event_log_path or DEFAULT_EVENT_LOG
        self.max_sessions = max_sessions
        self._sessions: Dict[str, EnterpriseSessionSnapshot] = {}

    def load_session(self, session_id: str) -> EnterpriseSessionSnapshot:
        if session_id not in self._sessions:
            self._sessions[session_id] = EnterpriseSessionSnapshot(session_id=session_id)
        return self._sessions[session_id]

    def merge_client_state(self, session_id: str, client_state: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = self.load_session(session_id)
        patch = snapshot.to_client_state_patch()
        merged = dict(patch)
        merged.update(client_state or {})
        # Explicit client state wins, but server session history should survive
        # when the browser sends only a partial update.
        for key in (
            "quote_history",
            "vehicle_history",
            "lastDailyReportContext",
            "lastMarketOpportunityContext",
            "enterpriseSession",
        ):
            if not (client_state or {}).get(key) and patch.get(key):
                merged[key] = patch[key]
        return merged

    def remember_response(
        self,
        *,
        session_id: str,
        response: Dict[str, Any],
        client_state: Dict[str, Any],
        reset_for_new_vehicle: bool = False,
    ) -> EnterpriseSessionSnapshot:
        snapshot = self.load_session(session_id)
        if reset_for_new_vehicle:
            snapshot.active_vehicle_context_id = ""
            snapshot.active_quote_id = ""

        module = response.get("module") or client_state.get("module") or snapshot.module or "media_pricing"
        snapshot.module = str(module)
        snapshot.selected_city = response.get("selected_city") or client_state.get("selectedCity") or snapshot.selected_city

        slots = flatten_slots(response.get("slots") or client_state.get("current_slots") or {})
        vehicle_match = response.get("vehicle_match") or client_state.get("current_vehicle_match") or {}
        if slots:
            context = self._upsert_vehicle_context(snapshot, slots, vehicle_match)
            snapshot.active_vehicle_context_id = context.vehicle_context_id

        pricing = response.get("pricing") or {}
        price_result = pricing.get("price_result") or {}
        if pricing.get("called_price") and isinstance(price_result, dict) and price_result.get("success", True):
            quote = self._append_quote_record(snapshot, pricing, price_result)
            snapshot.active_quote_id = quote.quote_id

        if response.get("last_daily_report_context") or client_state.get("lastDailyReportContext"):
            snapshot.last_daily_report_context = response.get("last_daily_report_context") or client_state.get("lastDailyReportContext") or {}
        if response.get("last_market_opportunity_context") or client_state.get("lastMarketOpportunityContext"):
            snapshot.last_market_opportunity_context = (
                response.get("last_market_opportunity_context")
                or client_state.get("lastMarketOpportunityContext")
                or {}
            )

        snapshot.updated_at = datetime.now().isoformat(timespec="seconds")
        self._sessions[session_id] = snapshot
        if len(self._sessions) > self.max_sessions:
            oldest = next(iter(self._sessions))
            self._sessions.pop(oldest, None)
        self._append_event("session_snapshot", snapshot.model_dump(mode="json"))
        return snapshot

    def _upsert_vehicle_context(
        self,
        snapshot: EnterpriseSessionSnapshot,
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
    ) -> VehicleContext:
        identity = build_vehicle_identity(slots)
        fingerprint = stable_hash(identity, "veh_")
        existing: Optional[VehicleContext] = next(
            (item for item in snapshot.vehicle_contexts if item.stable_vehicle_fingerprint == fingerprint),
            None,
        )
        if existing is None:
            existing = VehicleContext(
                vehicle_context_id=stable_hash({"session": snapshot.session_id, "identity": identity}, "vc_"),
                stable_vehicle_fingerprint=fingerprint,
                slots=dict(slots),
                vehicle_match=dict(vehicle_match or {}),
                six_element_key=build_six_element_key(slots),
            )
            snapshot.vehicle_contexts.append(existing)
            snapshot.vehicle_contexts = snapshot.vehicle_contexts[-50:]
        else:
            existing.slots = {**existing.slots, **{k: v for k, v in slots.items() if v not in (None, "")}}
            existing.vehicle_match = dict(vehicle_match or existing.vehicle_match or {})
            existing.six_element_key = build_six_element_key(existing.slots)
            existing.updated_at = datetime.now().isoformat(timespec="seconds")
            existing.active = True
        for item in snapshot.vehicle_contexts:
            item.active = item.vehicle_context_id == existing.vehicle_context_id
        return existing

    def _append_quote_record(
        self,
        snapshot: EnterpriseSessionSnapshot,
        pricing: Dict[str, Any],
        price_result: Dict[str, Any],
    ) -> QuoteRecord:
        vehicle_context_id = snapshot.active_vehicle_context_id or stable_hash(
            {"session": snapshot.session_id, "fallback": "vehicle"}, "vc_"
        )
        quote_id = str(
            price_result.get("quote_id")
            or price_result.get("request_id")
            or price_result.get("traceId")
            or stable_hash({"session": snapshot.session_id, "price": price_result, "at": datetime.now().isoformat()}, "q_")
        )
        request_hash = str(pricing.get("price_request_hash") or price_result.get("price_request_hash") or "")
        if not request_hash:
            request_hash = stable_hash(
                {
                    "vehicle_context_id": vehicle_context_id,
                    "price": price_result.get("price") or price_result.get("point_price") or price_result,
                },
                "req_",
            )
        has_same_quote_different_request = any(
            item.quote_id == quote_id
            and (item.request_hash != request_hash or item.vehicle_context_id != vehicle_context_id)
            for item in snapshot.quote_records
        )
        if has_same_quote_different_request:
            quote_id = f"{quote_id}_{stable_hash({'request_hash': request_hash, 'vehicle': vehicle_context_id})[:8]}"
        quote_role = str((price_result.get("task") or price_result.get("price_role") or "").upper())
        if quote_role not in {"C2B", "B2C", "BOTH"}:
            quote_role = "UNKNOWN"
        evidence_card = price_result.get("evidence_card") if isinstance(price_result, dict) else {}
        record = QuoteRecord(
            quote_id=quote_id,
            vehicle_context_id=vehicle_context_id,
            quote_role=quote_role,  # type: ignore[arg-type]
            request_hash=request_hash,
            price_result=price_result,
            evidence_card_id=str(
                (evidence_card or {}).get("evidence_card_id")
                or price_result.get("evidence_card_id")
                or quote_id
            ),
            pricing_engine_version=str(
                price_result.get("pricing_engine_version")
                or price_result.get("model_version")
                or price_result.get("pricing_engine_used")
                or ""
            ),
        )
        snapshot.quote_records = [
            item
            for item in snapshot.quote_records
            if not (item.quote_id == quote_id and item.request_hash == request_hash)
        ]
        snapshot.quote_records.append(record)
        snapshot.quote_records = snapshot.quote_records[-100:]
        return record

    def _append_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_type": event_type,
            "event_time": datetime.now().isoformat(timespec="seconds"),
            "payload": payload,
        }
        with self.event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


_GLOBAL_STATE_STORE = EnterpriseAgentStateStoreV21()


def get_enterprise_agent_state_store() -> EnterpriseAgentStateStoreV21:
    return _GLOBAL_STATE_STORE
