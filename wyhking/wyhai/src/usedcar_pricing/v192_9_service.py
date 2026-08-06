from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .v192_7_business import V1927ServingQuoteService


PRICING_ENGINE_VERSION = "192.9.0"
MODEL_VERSION = "v192.8_historical_market_core"
POLICY_VERSION = "v192.9_deployment_policy"
EVIDENCE_CARD_VERSION = "v192.9_evidence_card"


class PricingEngine(Protocol):
    def quote(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def stable_vehicle_fingerprint(payload: dict[str, Any]) -> str:
    fields = [
        payload.get("brand"),
        payload.get("series"),
        payload.get("model") or payload.get("trim"),
        payload.get("modelYear") or payload.get("model_year"),
        payload.get("regDate") or payload.get("reg_date"),
        payload.get("color"),
        payload.get("city"),
        payload.get("mileage_wan_km") or payload.get("mileage"),
        payload.get("transfer_count") or payload.get("transfer"),
    ]
    text = "|".join(_normalize_text(value) for value in fields)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class V1929QuoteStateStore:
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
                CREATE TABLE IF NOT EXISTS quote_state_v192_9 (
                    quote_id TEXT PRIMARY KEY,
                    parent_quote_id TEXT,
                    vehicle_id TEXT,
                    lifecycle_id TEXT,
                    normalized_vehicle_fingerprint TEXT NOT NULL,
                    normalized_vehicle_state TEXT NOT NULL,
                    final_price REAL,
                    confidence TEXT,
                    evidence_summary TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    pricing_engine_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS qsv9_vehicle_idx "
                "ON quote_state_v192_9(vehicle_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS qsv9_lifecycle_idx "
                "ON quote_state_v192_9(lifecycle_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS qsv9_fingerprint_idx "
                "ON quote_state_v192_9(normalized_vehicle_fingerprint, created_at)"
            )

    def save(self, state: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO quote_state_v192_9 (
                    quote_id, parent_quote_id, vehicle_id, lifecycle_id,
                    normalized_vehicle_fingerprint, normalized_vehicle_state,
                    final_price, confidence, evidence_summary, model_version,
                    pricing_engine_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["quote_id"],
                    state.get("parent_quote_id"),
                    state.get("vehicle_id"),
                    state.get("lifecycle_id"),
                    state["normalized_vehicle_fingerprint"],
                    json.dumps(
                        state["normalized_vehicle_state"],
                        ensure_ascii=False,
                    ),
                    state.get("final_price"),
                    state.get("confidence"),
                    json.dumps(
                        state.get("evidence_summary") or {},
                        ensure_ascii=False,
                    ),
                    state.get("model_version") or MODEL_VERSION,
                    state.get("pricing_engine_version")
                    or PRICING_ENGINE_VERSION,
                    state["created_at"],
                ),
            )

    def load_by_quote_id(self, quote_id: str) -> dict[str, Any] | None:
        if not quote_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quote_state_v192_9 "
                "WHERE quote_id = ? LIMIT 1",
                (quote_id,),
            ).fetchone()
        return _decode_row(row)

    def load_latest_by_vehicle_id(
        self,
        vehicle_id: str,
    ) -> dict[str, Any] | None:
        if not vehicle_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quote_state_v192_9 WHERE vehicle_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (vehicle_id,),
            ).fetchone()
        return _decode_row(row)

    def load_latest_by_lifecycle_id(
        self,
        lifecycle_id: str,
    ) -> dict[str, Any] | None:
        if not lifecycle_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quote_state_v192_9 WHERE lifecycle_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (lifecycle_id,),
            ).fetchone()
        return _decode_row(row)

    def load_latest_by_fingerprint(
        self,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        if not fingerprint:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quote_state_v192_9 "
                "WHERE normalized_vehicle_fingerprint = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return _decode_row(row)


@dataclass
class V1929PricingService:
    engine: PricingEngine
    state_store: V1929QuoteStateStore
    legacy_fallback: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload, input_meta = normalize_api_payload(payload)
        quote_id = str(payload.get("quote_id") or uuid.uuid4())
        previous, state_meta = self._trusted_previous_state(
            normalized_payload,
            input_meta,
        )
        fallback_payload = dict(normalized_payload)
        try:
            result = self.engine.quote(normalized_payload)
            pricing_engine_used = "V192_9"
            fallback = None
        except Exception as error:
            if self.legacy_fallback is None:
                raise
            result = self.legacy_fallback(fallback_payload)
            pricing_engine_used = "LEGACY_FALLBACK"
            fallback = {
                "fallback_reason": str(error),
                "fallback_engine": "legacy_callable",
            }
        unified = self._apply_guard_and_schema(
            quote_id=quote_id,
            payload=normalized_payload,
            input_meta=input_meta,
            previous=previous,
            state_meta=state_meta,
            raw_result=result,
            pricing_engine_used=pricing_engine_used,
            fallback=fallback,
        )
        self.state_store.save(
            {
                "quote_id": unified["quote_id"],
                "parent_quote_id": state_meta.get("parent_quote_id"),
                "vehicle_id": input_meta["vehicle_id"],
                "lifecycle_id": input_meta["lifecycle_id"],
                "normalized_vehicle_fingerprint": input_meta[
                    "normalized_vehicle_fingerprint"
                ],
                "normalized_vehicle_state": unified[
                    "normalized_vehicle_state"
                ],
                "final_price": unified["price_result"]["final_price"],
                "confidence": unified["price_result"]["confidence"],
                "evidence_summary": unified.get("evidence_summary") or {},
                "model_version": MODEL_VERSION,
                "pricing_engine_version": PRICING_ENGINE_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return unified

    def _trusted_previous_state(
        self,
        payload: dict[str, Any],
        meta: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        previous_quote_id = str(payload.get("previous_quote_id") or "")
        state_meta = {
            "lookup_strategy": "none",
            "previous_state_found": 0,
            "previous_state_trusted": 0,
            "previous_state_rejected_reason": "",
            "parent_quote_id": None,
            "client_previous_fields_trusted": 0,
        }
        previous = None
        if previous_quote_id:
            state_meta["lookup_strategy"] = "previous_quote_id"
            candidate = self.state_store.load_by_quote_id(previous_quote_id)
            if candidate is not None:
                state_meta["previous_state_found"] = 1
                if _identity_matches(candidate, meta):
                    previous = candidate
                    state_meta["previous_state_trusted"] = 1
                    state_meta["parent_quote_id"] = candidate["quote_id"]
                else:
                    state_meta[
                        "previous_state_rejected_reason"
                    ] = "IDENTITY_MISMATCH_FOR_PREVIOUS_QUOTE_ID"
            else:
                state_meta[
                    "previous_state_rejected_reason"
                ] = "PREVIOUS_QUOTE_ID_NOT_FOUND"
            return previous, state_meta
        for strategy, value, loader in (
            (
                "vehicle_id",
                meta["vehicle_id"],
                self.state_store.load_latest_by_vehicle_id,
            ),
            (
                "lifecycle_id",
                meta["lifecycle_id"],
                self.state_store.load_latest_by_lifecycle_id,
            ),
            (
                "normalized_vehicle_fingerprint",
                meta["normalized_vehicle_fingerprint"],
                self.state_store.load_latest_by_fingerprint,
            ),
        ):
            if not value:
                continue
            state_meta["lookup_strategy"] = strategy
            candidate = loader(value)
            if candidate is not None:
                state_meta["previous_state_found"] = 1
                previous = candidate
                state_meta["previous_state_trusted"] = 1
                state_meta["parent_quote_id"] = candidate["quote_id"]
                return previous, state_meta
        return None, state_meta

    def _apply_guard_and_schema(
        self,
        *,
        quote_id: str,
        payload: dict[str, Any],
        input_meta: dict[str, Any],
        previous: dict[str, Any] | None,
        state_meta: dict[str, Any],
        raw_result: dict[str, Any],
        pricing_engine_used: str,
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw_price = _extract_price_yuan(raw_result)
        raw_confidence = str(
            raw_result.get("confidence")
            or raw_result.get("quote_evidence_confidence")
            or "LOW"
        ).upper()
        current_vehicle_state = raw_result.get(
            "normalized_vehicle_state",
            _vehicle_state(payload, input_meta),
        )
        evidence_summary = raw_result.get("evidence_summary") or {}
        guard = V1927ServingQuoteService(
            entrypoint_name="V1929PricingService.quote"
        ).quote(
            raw_price=raw_price,
            raw_confidence=raw_confidence,
            previous_price=(
                previous.get("final_price")
                if previous is not None
                else None
            ),
            previous_confidence=(
                previous.get("confidence")
                if previous is not None
                else None
            ),
            previous_vehicle_state=(
                previous.get("normalized_vehicle_state")
                if previous is not None
                else None
            ),
            current_vehicle_state=current_vehicle_state,
            previous_evidence_state=(
                previous.get("evidence_summary")
                if previous is not None
                else None
            ),
            current_evidence_state=evidence_summary,
        )
        final_price = guard["final_price_after_guard"]
        interval = _normalize_interval(
            raw_result.get("interval"),
            final_price,
            raw_price,
        )
        risk_warnings = _normalize_warnings(
            raw_result.get("risk_warnings"),
            raw_result,
            input_meta,
        )
        selected = raw_result.get("selected_comparables") or []
        price_trace = raw_result.get("price_trace") or {}
        price_trace = {
            **price_trace,
            "guard_adjustment_amount": guard["guard_adjustment_amount"],
            "final_price_after_guard": final_price,
        }
        confidence_after = guard[
            "quote_evidence_confidence_after_guard"
        ]
        reasonableness = raw_result.get(
            "reasonableness_level", "SUPPORTED_WITH_LIMITATIONS"
        )
        display_type = _display_type(confidence_after)
        card = _evidence_card(
            quote_id=quote_id,
            payload=payload,
            input_meta=input_meta,
            final_price=final_price,
            interval=interval,
            confidence=confidence_after,
            reasonableness=reasonableness,
            selected=selected,
            price_trace=price_trace,
            risk_warnings=risk_warnings,
            raw_card=raw_result.get("evidence_card") or {},
            pricing_engine_used=pricing_engine_used,
        )
        guard_rule_codes = [
            item
            for item in str(guard["guard_rule_codes"]).split("|")
            if item
        ]
        result = {
            "quote_id": quote_id,
            "pricing_engine_used": pricing_engine_used,
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "policy_version": POLICY_VERSION,
            "evidence_card_version": EVIDENCE_CARD_VERSION,
            "price_result": {
                "final_price": final_price,
                "price_low": interval["low"],
                "price_high": interval["high"],
                "display_type": display_type,
                "confidence": confidence_after,
                "reasonableness_level": reasonableness,
            },
            "selected_comparables": selected,
            "price_trace": price_trace,
            "risk_warnings": risk_warnings,
            "evidence_card": card,
            "fallback": fallback,
            "guard": {
                "triggered": bool(guard["guard_triggered"]),
                "adjustment_amount": guard["guard_adjustment_amount"],
                "reason_codes": guard_rule_codes,
                "reason": guard["guard_rule_codes"],
                "change_flags_source": guard["change_flags_source"],
                "age_increased": bool(guard["age_increased"]),
                "mileage_increased": bool(guard["mileage_increased"]),
                "transfer_increased": bool(guard["transfer_increased"]),
                "condition_worsened": bool(guard["condition_worsened"]),
                "evidence_weakened": bool(guard["evidence_weakened"]),
            },
            "server_state": state_meta,
            "normalized_vehicle_state": current_vehicle_state,
            "input_normalization": input_meta,
            "evidence_summary": evidence_summary,
            "retrieval_summary": raw_result.get("retrieval_summary") or {},
            # Backward-compatible front-end fields.
            "c2bPrice": round(final_price / 10000.0, 2)
            if final_price is not None
            else None,
            "c2bRange": [
                round(interval["low"] / 10000.0, 2),
                round(interval["high"] / 10000.0, 2),
            ],
            "b2cPrice": round(final_price * 1.08 / 10000.0, 2)
            if final_price is not None
            else None,
            "ref_cars": selected,
            "reason": card["summary"],
            "modelName": "v192.9",
            "confidence": confidence_after,
        }
        return result


def normalize_api_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(payload)
    trim = result.get("trim") or result.get("model") or ""
    energy = (
        result.get("query_energy_type")
        or result.get("energy_type")
        or infer_energy_type(
            result.get("brand"),
            result.get("series"),
            result.get("modelYear") or result.get("model_year"),
            trim,
        )
    )
    result["query_energy_type"] = energy
    if result.get("condition_risk_level"):
        assumption = "USER_PROVIDED"
        condition = str(result["condition_risk_level"])
    else:
        condition = "clean"
        assumption = "SYSTEM_DEFAULT_GOOD_CONDITION"
        result["condition_risk_level"] = condition
    vehicle_id = _identity(result, "vehicle_id")
    lifecycle_id = _identity(result, "lifecycle_id")
    fingerprint = (
        vehicle_id
        or lifecycle_id
        or stable_vehicle_fingerprint(result)
    )
    result["normalized_vehicle_fingerprint"] = fingerprint
    result.setdefault("vehicle_id", vehicle_id or fingerprint)
    result.setdefault("lifecycle_id", lifecycle_id or fingerprint)
    meta = {
        "query_energy_type": energy,
        "energy_mapping_source": (
            "USER_PROVIDED"
            if payload.get("query_energy_type") or payload.get("energy_type")
            else "SERVER_TEXT_INFERENCE"
        ),
        "condition_risk_level": condition,
        "condition_assumption": assumption,
        "vehicle_id": str(result.get("vehicle_id") or ""),
        "lifecycle_id": str(result.get("lifecycle_id") or ""),
        "normalized_vehicle_fingerprint": fingerprint,
    }
    return result, meta


def infer_energy_type(
    brand: Any,
    series: Any,
    model_year: Any,
    trim: Any,
) -> str:
    text = _normalize_text(f"{brand} {series} {model_year} {trim}")
    if any(token in text for token in ["增程", "erev"]):
        return "EREV"
    if any(token in text for token in ["dm-i", "dmi", "插混", "phev", "phev"]):
        return "PHEV"
    if any(token in text for token in ["hev", "双擎", "油电混"]):
        return "HEV"
    if any(token in text for token in ["纯电", "bev", "ev", "电动"]):
        return "BEV"
    if re.search(r"\b\d{2,4}\s?km\b", text) and any(
        token in text
        for token in ["磷酸铁锂", "三元锂", "电池", "续航"]
    ):
        return "BEV"
    if any(token in text for token in ["宝马3系", "320i", "325i", "330i"]):
        return "ICE"
    return "UNKNOWN"


def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["normalized_vehicle_state"] = json.loads(
        result["normalized_vehicle_state"]
    )
    result["evidence_summary"] = json.loads(result["evidence_summary"])
    return result


def _identity(payload: dict[str, Any], field: str) -> str:
    return str(payload.get(field) or payload.get(f"{field}_hash") or "").strip()


def _identity_matches(
    previous: dict[str, Any],
    meta: dict[str, Any],
) -> bool:
    for field in ("vehicle_id", "lifecycle_id"):
        value = meta.get(field)
        if value and previous.get(field) == value:
            return True
    return (
        previous.get("normalized_vehicle_fingerprint")
        == meta.get("normalized_vehicle_fingerprint")
    )


def _extract_price_yuan(result: dict[str, Any]) -> float | None:
    if result.get("final_price") is not None:
        return float(result["final_price"])
    price_result = result.get("price_result") or {}
    if price_result.get("final_price") is not None:
        return float(price_result["final_price"])
    if result.get("c2bPrice") is not None:
        return float(result["c2bPrice"]) * 10000
    if result.get("c2b_price") is not None:
        return float(result["c2b_price"]) * 10000
    return None


def _vehicle_state(
    payload: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "age_years": payload.get("age_years"),
        "mileage_wan_km": payload.get(
            "mileage_wan_km", payload.get("mileage")
        ),
        "transfer_count": payload.get(
            "transfer_count", payload.get("transfer")
        ),
        "condition_risk_level": meta["condition_risk_level"],
    }


def _normalize_interval(
    interval: Any,
    final_price: float | None,
    raw_price: float | None,
) -> dict[str, Any]:
    if isinstance(interval, dict):
        low = interval.get("low")
        high = interval.get("high")
        interval_type = interval.get("type", "EVIDENCE_REFERENCE_RANGE")
    else:
        low = high = None
        interval_type = "EVIDENCE_REFERENCE_RANGE"
    if final_price is None:
        final_price = raw_price or 0.0
    if low is None or high is None:
        low = final_price * 0.9
        high = final_price * 1.1
    elif raw_price is not None and abs(final_price - raw_price) > 1e-9:
        half_width = max((float(high) - float(low)) / 2.0, 0.0)
        low = max(final_price - half_width, 0.0)
        high = final_price + half_width
    return {
        "low": float(low),
        "high": float(high),
        "type": interval_type,
    }


def _normalize_warnings(
    warnings: Any,
    raw_result: dict[str, Any],
    meta: dict[str, Any],
) -> list[str]:
    items = [str(item) for item in (warnings or []) if str(item).strip()]
    if meta["condition_assumption"] == "SYSTEM_DEFAULT_GOOD_CONDITION":
        message = "当前价格基于系统默认良好车况假设，实际检测后可能调整。"
        if message not in items:
            items.append(message)
    if raw_result.get("fallback_reason"):
        items.append(f"fallback: {raw_result['fallback_reason']}")
    return items


def _display_type(confidence: str) -> str:
    confidence = str(confidence or "").upper()
    if confidence == "HIGH":
        return "AUTO_SINGLE_POINT_QUOTE"
    if confidence in {"LOW", "MANUAL"}:
        return "LOW_CONFIDENCE_MARKET_REFERENCE"
    return "MARKET_REFERENCE"


def _evidence_card(
    *,
    quote_id: str,
    payload: dict[str, Any],
    input_meta: dict[str, Any],
    final_price: float | None,
    interval: dict[str, Any],
    confidence: str,
    reasonableness: str,
    selected: list[dict[str, Any]],
    price_trace: dict[str, Any],
    risk_warnings: list[str],
    raw_card: dict[str, Any],
    pricing_engine_used: str,
) -> dict[str, Any]:
    vehicle = raw_card.get("vehicle") or {
        "brand": payload.get("brand"),
        "series": payload.get("series"),
        "model_year": payload.get("modelYear")
        or payload.get("model_year"),
        "trim": payload.get("trim") or payload.get("model"),
        "city": payload.get("city"),
        "color": payload.get("color"),
        "mileage_wan_km": payload.get("mileage_wan_km")
        or payload.get("mileage"),
        "transfer_count": payload.get("transfer_count")
        or payload.get("transfer"),
    }
    summary = (
        f"v192.9 基于历史可比车、语义TopK、统计基线和受限调整生成；"
        f"当前置信度 {confidence}，价格合理性 {reasonableness}。"
    )
    if confidence in {"LOW", "MANUAL"}:
        summary += " 该结果是低置信历史市场参考，暂不建议自动报价。"
    return {
        **raw_card,
        "quote_id": quote_id,
        "summary": summary,
        "vehicle": vehicle,
        "final_price": final_price,
        "interval": interval,
        "confidence": confidence,
        "reasonableness_level": reasonableness,
        "selected_comparables": selected,
        "price_trace": price_trace,
        "risk_warnings": risk_warnings,
        "input_normalization": input_meta,
        "pricing_engine_used": pricing_engine_used,
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s\t\r\n\u3000_/\\|,，。:：;；()（）+]+", "", text)
