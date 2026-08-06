from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .v192_7_business import V1927ServingQuoteService


class PricingEngine(Protocol):
    def quote(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class QuoteStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS quote_state (
                    quote_id TEXT PRIMARY KEY,
                    parent_quote_id TEXT,
                    vehicle_id TEXT,
                    lifecycle_id TEXT,
                    previous_vehicle_state TEXT NOT NULL,
                    previous_final_price REAL,
                    previous_confidence TEXT,
                    previous_evidence_summary TEXT NOT NULL,
                    previous_model_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS quote_state_vehicle_idx "
                "ON quote_state(vehicle_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS quote_state_lifecycle_idx "
                "ON quote_state(lifecycle_id, created_at)"
            )

    def save(self, state: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO quote_state (
                    quote_id, parent_quote_id, vehicle_id, lifecycle_id,
                    previous_vehicle_state, previous_final_price,
                    previous_confidence, previous_evidence_summary,
                    previous_model_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["quote_id"],
                    state.get("parent_quote_id"),
                    state.get("vehicle_id"),
                    state.get("lifecycle_id"),
                    json.dumps(
                        state["previous_vehicle_state"],
                        ensure_ascii=False,
                    ),
                    state.get("previous_final_price"),
                    state.get("previous_confidence"),
                    json.dumps(
                        state["previous_evidence_summary"],
                        ensure_ascii=False,
                    ),
                    state["previous_model_version"],
                    state["created_at"],
                ),
            )

    def load(
        self,
        *,
        quote_id: str | None = None,
        vehicle_id: str | None = None,
        lifecycle_id: str | None = None,
    ) -> dict[str, Any] | None:
        clauses: list[str] = []
        values: list[str] = []
        if quote_id:
            clauses.append("quote_id = ?")
            values.append(quote_id)
        if vehicle_id:
            clauses.append("vehicle_id = ?")
            values.append(vehicle_id)
        if lifecycle_id:
            clauses.append("lifecycle_id = ?")
            values.append(lifecycle_id)
        if not clauses:
            return None
        query = (
            "SELECT * FROM quote_state WHERE "
            + " OR ".join(clauses)
            + " ORDER BY created_at DESC LIMIT 1"
        )
        with self._connect() as connection:
            row = connection.execute(query, values).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["previous_vehicle_state"] = json.loads(
            result["previous_vehicle_state"]
        )
        result["previous_evidence_summary"] = json.loads(
            result["previous_evidence_summary"]
        )
        return result


@dataclass
class CallablePricingEngine:
    pricing_callable: Callable[[dict[str, Any]], dict[str, Any]]

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.pricing_callable(payload)


@dataclass
class V1928PricingService:
    engine: PricingEngine
    state_store: QuoteStateStore
    legacy_fallback: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    model_version: str = "v192.8"

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        quote_id = str(payload.get("quote_id") or uuid.uuid4())
        vehicle_id = _identity(payload, "vehicle_id")
        lifecycle_id = _identity(payload, "lifecycle_id")
        requested_previous_quote_id = str(
            payload.get("previous_quote_id") or ""
        )
        previous = self.state_store.load(
            quote_id=requested_previous_quote_id or None,
            vehicle_id=vehicle_id or None,
            lifecycle_id=lifecycle_id or None,
        )
        previous_trusted = _same_identity(
            previous, vehicle_id, lifecycle_id
        )
        try:
            result = self.engine.quote(payload)
            result["pricing_engine_used"] = "V192_8"
            result["legacy_v7_guard_only_flag"] = 0
        except Exception as error:
            if self.legacy_fallback is None:
                raise
            result = self.legacy_fallback(payload)
            result["pricing_engine_used"] = "LEGACY_V7_FALLBACK"
            result["legacy_v7_guard_only_flag"] = 1
            result["fallback_reason"] = str(error)

        raw_price = _price(result)
        confidence = str(
            result.get("confidence")
            or result.get("quote_evidence_confidence")
            or "LOW"
        ).upper()
        current_vehicle_state = result.get(
            "normalized_vehicle_state",
            payload.get("current_vehicle_state")
            or _vehicle_state(payload),
        )
        current_evidence = result.get("evidence_summary") or {}
        guard = V1927ServingQuoteService(
            entrypoint_name="V1928PricingService.quote"
        ).quote(
            raw_price=raw_price,
            raw_confidence=confidence,
            previous_price=(
                previous.get("previous_final_price")
                if previous_trusted
                else None
            ),
            previous_confidence=(
                previous.get("previous_confidence")
                if previous_trusted
                else None
            ),
            previous_vehicle_state=(
                previous.get("previous_vehicle_state")
                if previous_trusted
                else None
            ),
            current_vehicle_state=current_vehicle_state,
            previous_evidence_state=(
                previous.get("previous_evidence_summary")
                if previous_trusted
                else None
            ),
            current_evidence_state=current_evidence,
        )
        final_price = guard["final_price_after_guard"]
        interval = result.get("interval")
        if isinstance(interval, dict):
            low = interval.get("low")
            high = interval.get("high")
            if low is not None and high is not None and raw_price is not None:
                half_width = max((float(high) - float(low)) / 2.0, 0.0)
                interval["low"] = max(float(final_price) - half_width, 0.0)
                interval["high"] = float(final_price) + half_width
                interval["recentered_after_guard"] = int(
                    not _same_price(final_price, raw_price)
                )
        result["quote_id"] = quote_id
        result["final_price"] = final_price
        result["confidence"] = guard[
            "quote_evidence_confidence_after_guard"
        ]
        result["guard"] = {
            "triggered": bool(guard["guard_triggered"]),
            "adjustment_amount": guard["guard_adjustment_amount"],
            "reason_codes": guard["guard_rule_codes"],
            "change_flags_source": guard["change_flags_source"],
            "age_increased": bool(guard["age_increased"]),
            "mileage_increased": bool(guard["mileage_increased"]),
            "transfer_increased": bool(guard["transfer_increased"]),
            "condition_worsened": bool(guard["condition_worsened"]),
            "evidence_weakened": bool(guard["evidence_weakened"]),
        }
        result["server_state"] = {
            "previous_state_found": int(previous is not None),
            "previous_state_trusted": int(previous_trusted),
            "previous_state_source": (
                "SERVER_QUOTE_STATE_STORE"
                if previous_trusted
                else "NO_TRUSTED_PREVIOUS_STATE"
            ),
            "client_previous_fields_trusted": 0,
            "parent_quote_id": (
                previous.get("quote_id") if previous_trusted else None
            ),
        }
        price_trace = result.setdefault("price_trace", {})
        price_trace["guard_adjustment_amount"] = guard[
            "guard_adjustment_amount"
        ]
        price_trace["final_price_after_guard"] = final_price
        evidence_card = result.get("evidence_card")
        if isinstance(evidence_card, dict):
            evidence_card["quote_id"] = quote_id
            evidence_card["final_price"] = final_price
            evidence_card["interval"] = result.get("interval")
            evidence_card["confidence"] = result["confidence"]
            evidence_card["guard"] = result["guard"]
        self.state_store.save(
            {
                "quote_id": quote_id,
                "parent_quote_id": (
                    previous.get("quote_id")
                    if previous_trusted
                    else None
                ),
                "vehicle_id": vehicle_id,
                "lifecycle_id": lifecycle_id,
                "previous_vehicle_state": current_vehicle_state,
                "previous_final_price": final_price,
                "previous_confidence": result["confidence"],
                "previous_evidence_summary": current_evidence,
                "previous_model_version": self.model_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return result


def _identity(payload: dict[str, Any], field: str) -> str:
    return str(
        payload.get(field)
        or payload.get(f"{field}_hash")
        or ""
    ).strip()


def _same_identity(
    previous: dict[str, Any] | None,
    vehicle_id: str,
    lifecycle_id: str,
) -> bool:
    if previous is None:
        return False
    return bool(
        (vehicle_id and previous.get("vehicle_id") == vehicle_id)
        or (
            lifecycle_id
            and previous.get("lifecycle_id") == lifecycle_id
        )
    )


def _price(result: dict[str, Any]) -> float | None:
    if result.get("final_price") is not None:
        return float(result["final_price"])
    if result.get("c2bPrice") is not None:
        return float(result["c2bPrice"]) * 10000
    return None


def _same_price(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= 1e-9


def _vehicle_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "age_years": payload.get("age_years"),
        "mileage_wan_km": payload.get(
            "mileage_wan_km", payload.get("mileage")
        ),
        "transfer_count": payload.get(
            "transfer_count", payload.get("transfer")
        ),
        "condition_risk_level": payload.get(
            "condition_risk_level", "unknown"
        ),
    }
