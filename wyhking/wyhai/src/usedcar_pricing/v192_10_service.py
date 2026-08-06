from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .v192_7_business import V1927ServingQuoteService
from .v192_9_service import (
    _display_type,
    _extract_price_yuan,
    _normalize_interval,
    _normalize_warnings,
    infer_energy_type,
)


PRICING_ENGINE_VERSION = "192.10.0"
MODEL_VERSION = "v192.8_historical_market_core"
POLICY_VERSION = "v192.10_real_deployment_policy"
EVIDENCE_CARD_VERSION = "v192.10_evidence_card"


class PricingEngine(Protocol):
    def quote(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def stable_vehicle_fingerprint(payload: dict[str, Any]) -> str:
    """Stable vehicle fingerprint, intentionally excluding mutable state.

    Mileage, transfer count, and condition can change between quotes and must
    not be part of the key used to find a previous quote.
    """

    stable_id = (
        payload.get("vin_hash")
        or payload.get("vinHash")
        or payload.get("vehicle_id")
        or payload.get("lifecycle_id")
    )
    if stable_id:
        return _normalize_text(stable_id)
    fields = [
        payload.get("brand"),
        payload.get("series"),
        payload.get("model") or payload.get("trim"),
        payload.get("modelYear") or payload.get("model_year"),
        payload.get("regDate") or payload.get("reg_date"),
        payload.get("color"),
    ]
    text = "|".join(_normalize_text(value) for value in fields)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class V19210QuoteStateStore:
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
                CREATE TABLE IF NOT EXISTS quote_state_v192_10 (
                    quote_id TEXT PRIMARY KEY,
                    parent_quote_id TEXT,
                    vehicle_id TEXT,
                    lifecycle_id TEXT,
                    stable_vehicle_fingerprint TEXT NOT NULL,
                    vehicle_state TEXT NOT NULL,
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
                "CREATE INDEX IF NOT EXISTS qsv10_vehicle_idx "
                "ON quote_state_v192_10(vehicle_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS qsv10_lifecycle_idx "
                "ON quote_state_v192_10(lifecycle_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS qsv10_fingerprint_idx "
                "ON quote_state_v192_10(stable_vehicle_fingerprint, created_at)"
            )

    def save(self, state: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO quote_state_v192_10 (
                    quote_id, parent_quote_id, vehicle_id, lifecycle_id,
                    stable_vehicle_fingerprint, vehicle_state,
                    final_price, confidence, evidence_summary, model_version,
                    pricing_engine_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["quote_id"],
                    state.get("parent_quote_id"),
                    state.get("vehicle_id"),
                    state.get("lifecycle_id"),
                    state["stable_vehicle_fingerprint"],
                    json.dumps(state["vehicle_state"], ensure_ascii=False),
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
                "SELECT * FROM quote_state_v192_10 "
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
                "SELECT * FROM quote_state_v192_10 WHERE vehicle_id = ? "
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
                "SELECT * FROM quote_state_v192_10 WHERE lifecycle_id = ? "
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
                "SELECT * FROM quote_state_v192_10 "
                "WHERE stable_vehicle_fingerprint = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return _decode_row(row)


@dataclass
class V19210PricingService:
    engine: PricingEngine
    state_store: V19210QuoteStateStore
    legacy_fallback: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload, input_meta = normalize_api_payload(payload)
        quote_id = str(payload.get("quote_id") or uuid.uuid4())
        previous, state_meta = self._trusted_previous_state(
            normalized_payload,
            input_meta,
        )
        try:
            raw_result = self.engine.quote(normalized_payload)
            pricing_engine_used = "V192_10"
            fallback = None
        except Exception as error:
            if self.legacy_fallback is None:
                raise
            raw_result = self.legacy_fallback(dict(normalized_payload))
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
            raw_result=raw_result,
            pricing_engine_used=pricing_engine_used,
            fallback=fallback,
        )
        self.state_store.save(
            {
                "quote_id": unified["quote_id"],
                "parent_quote_id": state_meta.get("parent_quote_id"),
                "vehicle_id": input_meta["vehicle_id"],
                "lifecycle_id": input_meta["lifecycle_id"],
                "stable_vehicle_fingerprint": input_meta[
                    "stable_vehicle_fingerprint"
                ],
                "vehicle_state": unified["vehicle_state"],
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
        if previous_quote_id:
            state_meta["lookup_strategy"] = "previous_quote_id"
            candidate = self.state_store.load_by_quote_id(previous_quote_id)
            if candidate is None:
                state_meta[
                    "previous_state_rejected_reason"
                ] = "PREVIOUS_QUOTE_ID_NOT_FOUND"
                return None, state_meta
            state_meta["previous_state_found"] = 1
            if _identity_matches(candidate, meta):
                state_meta["previous_state_trusted"] = 1
                state_meta["parent_quote_id"] = candidate["quote_id"]
                return candidate, state_meta
            state_meta[
                "previous_state_rejected_reason"
            ] = "IDENTITY_MISMATCH_FOR_PREVIOUS_QUOTE_ID"
            return None, state_meta
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
                "stable_vehicle_fingerprint",
                meta["stable_vehicle_fingerprint"],
                self.state_store.load_latest_by_fingerprint,
            ),
        ):
            if not value:
                continue
            state_meta["lookup_strategy"] = strategy
            candidate = loader(value)
            if candidate is not None:
                state_meta["previous_state_found"] = 1
                state_meta["previous_state_trusted"] = 1
                state_meta["parent_quote_id"] = candidate["quote_id"]
                return candidate, state_meta
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
            entrypoint_name="V19210PricingService.quote"
        ).quote(
            raw_price=raw_price,
            raw_confidence=raw_confidence,
            previous_price=(
                previous.get("final_price") if previous is not None else None
            ),
            previous_confidence=(
                previous.get("confidence") if previous is not None else None
            ),
            previous_vehicle_state=(
                previous.get("vehicle_state") if previous is not None else None
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
        price_trace = {
            **(raw_result.get("price_trace") or {}),
            "guard_adjustment_amount": guard["guard_adjustment_amount"],
            "final_price_after_guard": final_price,
        }
        risk_warnings = _grounded_risk_warnings(
            risk_warnings,
            selected,
            evidence_summary,
            interval,
            final_price,
            input_meta,
        )
        confidence_after = guard[
            "quote_evidence_confidence_after_guard"
        ]
        reasonableness = raw_result.get(
            "reasonableness_level", "SUPPORTED_WITH_LIMITATIONS"
        )
        display_type = _display_type(confidence_after)
        guard_rule_codes = [
            item
            for item in str(guard["guard_rule_codes"]).split("|")
            if item
        ]
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
        result = {
            "quote_id": quote_id,
            "pricing_engine_used": pricing_engine_used,
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": PRICING_ENGINE_VERSION,
            "underlying_model_version": MODEL_VERSION,
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
            "vehicle_state": current_vehicle_state,
            "normalized_vehicle_state": current_vehicle_state,
            "input_normalization": input_meta,
            "evidence_summary": evidence_summary,
            "retrieval_summary": raw_result.get("retrieval_summary") or {},
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
            "modelName": "v192.10",
            "confidence": confidence_after,
        }
        return _json_safe(result)


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
    fingerprint = stable_vehicle_fingerprint(result)
    result["stable_vehicle_fingerprint"] = fingerprint
    result["normalized_vehicle_fingerprint"] = fingerprint
    result["vehicle_id"] = vehicle_id or fingerprint
    result["lifecycle_id"] = lifecycle_id or fingerprint
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
        "stable_vehicle_fingerprint": fingerprint,
        "vehicle_id_source": (
            "USER_PROVIDED" if vehicle_id else "STABLE_FINGERPRINT_FALLBACK"
        ),
        "lifecycle_id_source": (
            "USER_PROVIDED"
            if lifecycle_id
            else "STABLE_FINGERPRINT_FALLBACK"
        ),
    }
    return result, meta


def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["vehicle_state"] = json.loads(result["vehicle_state"])
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
    return previous.get("stable_vehicle_fingerprint") == meta.get(
        "stable_vehicle_fingerprint"
    )


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
        "model_year": payload.get("modelYear") or payload.get("model_year"),
        "trim": payload.get("trim") or payload.get("model"),
        "city": payload.get("city"),
        "color": payload.get("color"),
        "mileage_wan_km": payload.get("mileage_wan_km")
        or payload.get("mileage"),
        "transfer_count": payload.get("transfer_count")
        or payload.get("transfer"),
    }
    summary = (
        "v192.10 使用真实历史候选召回、时间过滤、语义TopK、统计基线、"
        "残差/车系校准、Guard、区间和置信度生成价格证据卡；"
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
        "model_version": PRICING_ENGINE_VERSION,
        "underlying_model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s\t\r\n\u3000_/\\|,，。:：;；()（）+]+", "", text)


def _grounded_risk_warnings(
    warnings: list[str],
    selected: list[dict[str, Any]],
    evidence_summary: dict[str, Any],
    interval: dict[str, Any],
    final_price: float | None,
    input_meta: dict[str, Any],
) -> list[str]:
    result = list(dict.fromkeys(str(item) for item in warnings if item))

    def add(message: str) -> None:
        if message not in result:
            result.append(message)

    if input_meta.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION":
        add("当前价格基于系统默认良好车况假设，实际检测后可能调整。")
    if selected:
        source_families = {
            str(item.get("source_family") or "")
            for item in selected
            if item.get("source_family")
        }
        if len(source_families) <= 1:
            add("只有单一来源")
        if not any(float(item.get("city_match") or 0) > 0 for item in selected):
            add("无同城证据")
        if any(
            "B2C" in str(item.get("original_price_role") or "").upper()
            or "LISTING" in str(item.get("original_price_role") or "").upper()
            or "b2c" in str(item.get("source_family") or "").lower()
            or "listing" in str(item.get("source_family") or "").lower()
            for item in selected
        ):
            add("B2C折算候选仅作为辅助证据")
        if any(
            "T3B" in str(item.get("semantic_tier") or "")
            for item in selected
        ):
            add("使用T3B启发式候选")
        if any(
            "T4" in str(item.get("semantic_tier") or "")
            for item in selected
        ):
            add("使用T4兜底候选")
        if any(
            int(float(item.get("conversion_guard_applied") or 0)) == 1
            for item in selected
        ):
            add("B2C转换比例被裁剪")
        condition_weight = evidence_summary.get(
            "candidate_condition_match_weight"
        )
        if condition_weight is not None and float(condition_weight or 0) < 0.6:
            add("候选车况不完全匹配")
    else:
        add("候选数量较少")
    if len(selected) <= 3:
        add("候选数量较少")
    recent_weight = evidence_summary.get("recent_90d_weight")
    if recent_weight is not None and float(recent_weight or 0) < 0.6:
        add("近期证据不足")
    if final_price:
        width_ratio = (
            float(interval.get("high") or final_price)
            - float(interval.get("low") or final_price)
        ) / max(float(final_price), 1.0)
        if width_ratio > 0.30:
            add("价格区间较宽")
    return result


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        if value in {"NaT", "nan", "NaN", "inf", "-inf"}:
            return None
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            converted = value.isoformat()
            if converted in {"NaT", "nan", "NaN", "inf", "-inf"}:
                return None
            return converted
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    text = str(value)
    if text in {"NaT", "nan", "NaN", "inf", "-inf"}:
        return None
    return text
