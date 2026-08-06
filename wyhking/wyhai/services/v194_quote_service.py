from __future__ import annotations

import json
import hashlib
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

from usedcar_pricing.v194_retrieval import (
    evidence_ledger,
    normalize_query,
    retrieve_candidates,
    statistical_price_from_candidates,
)
from usedcar_pricing.v194_runtime_models import V194DirectPricePrior
from usedcar_pricing.v194_price_policy import weighted_quantile
from usedcar_pricing.v192_16_semantics import canonicalize_trim
from usedcar_pricing.v194_listwise_ranker import V194ListwiseRanker
from usedcar_pricing.v194_candidate_calibrator import V194CandidateCalibrator
from usedcar_pricing.v194_121_product_memory import (
    PRODUCT_MEMORY_POLICY_VERSION,
    V194121ProductMemory,
)
from usedcar_pricing.v194_123_b2c_product_memory import (
    B2C_PRODUCT_MEMORY_POLICY_VERSION,
    V194123B2CProductMemory,
)
from usedcar_pricing.v195_daily_vehicle_knowledge import (
    DailyVehicleKnowledgeStore,
    exact_seven_element_fingerprint,
    prepare_knowledge_cells,
)
from usedcar_pricing.v195_reviewed_business_surface import get_reviewed_business_surface
from usedcar_pricing.v195_internal_dcd_appraiser import InternalDcdCatalogAppraiser
from usedcar_pricing.v195_appraiser_decision_record import (
    build_appraiser_decision_record,
)
from usedcar_pricing.v194_234_universal_market_anchor import V194234UniversalMarketAnchor
from .dongchedi_usedcar_market import DongchediUsedCarMarket
from .online_vehicle_catalog_service import OnlineVehicleCatalogService


ROOT = Path(__file__).resolve().parents[1]
PRICING_ENGINE_VERSION = "194.270.0"
MODEL_VERSION = "v194_159_c2b_candidate_trace_plus_v194_270_dcd_current_market_guard"
POLICY_VERSION = "v194_270_agent_online_c2b_b2c_dcd_current_market_guard_policy"
EVIDENCE_CARD_VERSION = "v194_98_catalog_coverage_multivehicle_evidence_card"
B2C_PRESALE_SOLD_DISCOUNT_RATIO = 0.96
BUILD_TIME = datetime.now(timezone.utc).isoformat()

_SERVICE: "V194PricingService | None" = None
_LOCK = threading.Lock()
_READY_CACHE: dict[str, Any] | None = None
_COMMERCIAL_STORE: DailyVehicleKnowledgeStore | None = None
_COMMERCIAL_STORE_LOCK = threading.Lock()
_ON_DEMAND_STORE: DailyVehicleKnowledgeStore | None = None
_ON_DEMAND_STORE_LOCK = threading.Lock()
_CATALOG_APPRAISER: InternalDcdCatalogAppraiser | None = None
_CATALOG_APPRAISER_LOCK = threading.Lock()
SUPERVISED_COMMERCIAL_ROUTE_ENABLED = str(
    os.environ.get("ENABLE_V195_SUPERVISED_COMMERCIAL_ROUTE", "false")
).strip().lower() in {"1", "true", "yes", "on"}
REVIEWED_BUSINESS_SURFACE_ENABLED = str(
    os.environ.get("ENABLE_V195_REVIEWED_BUSINESS_SURFACE", "true")
).strip().lower() in {"1", "true", "yes", "on"}
ON_DEMAND_EXACT_CELL_ENABLED = str(
    os.environ.get("ENABLE_V195_ON_DEMAND_EXACT_CELL", "true")
).strip().lower() in {"1", "true", "yes", "on"}
STATIC_GUIDE_FALLBACK_ENABLED = str(
    os.environ.get("ENABLE_STATIC_GUIDE_PRICE_FALLBACK", "false")
).strip().lower() in {"1", "true", "yes", "on"}


_CONDITION_GRADE_FACTOR_VS_B = {
    "A": 1.0 / 0.97,
    "B": 1.0,
    "C": 0.91 / 0.97,
    "D": 0.83 / 0.97,
    "E": 0.74 / 0.97,
}


def _explicit_condition_grade(payload: dict[str, Any]) -> str:
    grade = str(
        payload.get("inspection_grade")
        or payload.get("condition_grade")
        or ""
    ).strip().upper()
    return grade if grade in _CONDITION_GRADE_FACTOR_VS_B else ""


def _scale_price_value(value: Any, factor: float, *, unit: str = "yuan") -> Any:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return value
    scaled = float(parsed) * factor
    return round(scaled, 2 if unit == "yuan" else 6)


def _scale_price_range(value: Any, factor: float, *, unit: str = "yuan") -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    return [_scale_price_value(item, factor, unit=unit) for item in value]


def _apply_condition_grade_guard(
    result: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply an auditable final condition correction to legacy v194 quotes.

    The reviewed v195 surface and exact-cell materializer already apply
    continuous condition adjustments.  The older v194 AUTO_SINGLE_POINT path
    did not always consume the grade after a manual/market anchor had been
    selected, which allowed A/B/C/D/E to return the same point price.  Keep B
    as the serving anchor so existing default-good quotes do not move, and
    correct only explicit grades on the unreviewed v194 path.
    """

    if not isinstance(result, dict) or not result.get("success"):
        return result
    if str(result.get("pricing_engine_used") or "") != "V194":
        return result
    grade = _explicit_condition_grade(payload)
    if not grade:
        return result
    trace = result.get("price_trace")
    if not isinstance(trace, dict):
        trace = {}
        result["price_trace"] = trace
    if isinstance(trace.get("condition_grade_guard"), dict):
        return result

    factor = float(_CONDITION_GRADE_FACTOR_VS_B[grade])
    before = pd.to_numeric(result.get("final_price"), errors="coerce")
    if pd.isna(before) or float(before) <= 0:
        return result

    for key in (
        "final_price",
        "recommended_listing_price_yuan",
        "first_c2b_offer_yuan",
        "max_c2b_price_yuan",
    ):
        if key in result:
            result[key] = _scale_price_value(result.get(key), factor)
    for key in ("display_price_wan", "c2bPrice", "c2b_price", "targetC2B", "b2cPrice", "b2c_price", "targetB2C"):
        if key in result:
            result[key] = _scale_price_value(result.get(key), factor, unit="wan")
    for key in ("c2bRange", "b2cRange"):
        if key in result:
            result[key] = _scale_price_range(result.get(key), factor, unit="wan")
    for key in ("recommended_listing_range_yuan",):
        if key in result:
            result[key] = _scale_price_range(result.get(key), factor)

    price_result = result.get("price_result")
    if isinstance(price_result, dict):
        for key in ("final_price", "price_low", "price_high"):
            if key in price_result:
                price_result[key] = _scale_price_value(price_result.get(key), factor)
    interval = result.get("interval")
    if isinstance(interval, dict):
        for key in ("low", "high", "evidence_low", "evidence_high"):
            if key in interval:
                interval[key] = _scale_price_value(interval.get(key), factor)
    ladder = result.get("price_ladder")
    if isinstance(ladder, dict):
        for key, value in list(ladder.items()):
            if key.endswith("_range_yuan"):
                ladder[key] = _scale_price_range(value, factor)
            elif key.endswith("_yuan"):
                ladder[key] = _scale_price_value(value, factor)

    after = float(pd.to_numeric(result.get("final_price"), errors="coerce"))
    trace["pre_condition_grade_guard_price_yuan"] = round(float(before), 2)
    trace["statistical_baseline_price"] = round(after, 2)
    trace["condition_grade_adjustment_amount"] = round(after - float(before), 2)
    trace["condition_grade_guard"] = {
        "enabled": True,
        "policy_version": "v194_271_explicit_condition_monotonic_guard",
        "anchor_grade": "B",
        "input_grade": grade,
        "factor": round(factor, 6),
        "before_price_yuan": round(float(before), 2),
        "after_price_yuan": round(after, 2),
        "reason": "旧版自动单点链路未形成可审计车况差异，按统一A/B/C/D/E规则补充最终修正。",
    }
    warnings = result.setdefault("risk_warnings", [])
    if grade in {"C", "D", "E"} and isinstance(warnings, list):
        warnings.append(
            f"本次已按{grade}级车况相对默认B级基准下调；最终仍需结合实车检测确认。"
        )
    return result


def _reviewed_surface_path() -> Path:
    default_path = _project_root() / "data/v195/unified_single_answer_price_book_v195439.parquet"
    if not default_path.exists():
        default_path = _project_root() / "data/v195/unified_single_answer_price_book.parquet"
    if not default_path.exists():
        default_path = _project_root() / "data/v195/reviewed_business_price_surface.parquet"
    return Path(os.environ.get("V195_SINGLE_ANSWER_BOOK_PATH") or default_path)


def _reviewed_business_surface_quote(
    payload: dict[str, Any], target_side: str
) -> dict[str, Any] | None:
    if not REVIEWED_BUSINESS_SURFACE_ENABLED:
        return None
    path = _reviewed_surface_path()
    try:
        return get_reviewed_business_surface(
            path,
            max_distance=float(os.environ.get("V195_SINGLE_ANSWER_MAX_DISTANCE", "2.0")),
        ).quote(payload, target_side)
    except Exception:
        # A reviewed surface is an enhancement.  The established v194 chain
        # remains available if the daily artifact is absent or malformed.
        return None


def _payload_with_catalog_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve text-only frontline input to one safe catalog identity."""

    model_id = pd.to_numeric(
        payload.get("model_id")
        or payload.get("modelId")
        or payload.get("vehicle_model_id"),
        errors="coerce",
    )
    if pd.notna(model_id) and float(model_id) > 0:
        return payload
    global _CATALOG_APPRAISER
    with _CATALOG_APPRAISER_LOCK:
        if _CATALOG_APPRAISER is None:
            try:
                _CATALOG_APPRAISER = InternalDcdCatalogAppraiser(_project_root())
            except (FileNotFoundError, OSError, ValueError, KeyError):
                _CATALOG_APPRAISER = None
    if _CATALOG_APPRAISER is None:
        return payload
    resolved = _CATALOG_APPRAISER.resolve_identity(payload)
    if not resolved or not resolved.get("model_id"):
        return payload

    enriched = dict(payload)
    input_year = pd.to_numeric(
        payload.get("model_year") or payload.get("modelYear"), errors="coerce"
    )
    resolved_year = int(resolved.get("model_year") or 0)
    input_trim = str(
        payload.get("trim")
        or payload.get("model")
        or payload.get("model_name")
        or ""
    ).strip()
    resolved_trim = str(resolved.get("trim") or "").strip()
    enriched.update(
        {
            "model_id": int(resolved["model_id"]),
            "input_brand": payload.get("brand") or payload.get("brand_name"),
            "input_series": payload.get("series") or payload.get("series_name"),
            "catalog_resolved_identity_key": resolved.get("identity_key"),
            "catalog_resolved_model_year": resolved_year,
            "catalog_resolved_trim": resolved_trim,
            "input_model_year": int(input_year) if pd.notna(input_year) else None,
            "input_trim": input_trim,
        }
    )
    # Use the canonical identity for price-book lookup.  Original user text is
    # retained above and remains the title shown by the interaction layer.
    enriched["brand"] = resolved.get("brand") or enriched.get("brand")
    enriched["series"] = resolved.get("series") or enriched.get("series")
    enriched["trim"] = resolved_trim or enriched.get("trim")
    warning_parts: list[str] = []
    if resolved_year and (
        pd.isna(input_year)
        or int(input_year) != resolved_year
        or re.sub(r"\s+", "", input_trim.lower())
        != re.sub(r"\s+", "", resolved_trim.lower())
    ):
        input_label = (
            f"{int(input_year)}款{input_trim}"
            if pd.notna(input_year)
            else input_trim
        )
        warning_parts.append(
            f"输入的“{input_label}”在车型库中按“{resolved_year}款{resolved_trim}”匹配"
        )
        enriched["model_year"] = resolved_year

    registration_key = next(
        (
            key
            for key in (
                "registration_date",
                "first_registration_date",
                "regDate",
                "reg_date",
                "firstLicenseDate",
            )
            if payload.get(key)
        ),
        None,
    )
    registration = pd.to_datetime(
        payload.get(registration_key) if registration_key else None,
        errors="coerce",
    )
    if (
        pd.notna(registration)
        and pd.notna(input_year)
        and registration.year < int(input_year) - 1
        and resolved_year > 0
    ):
        corrected_year = resolved_year
        corrected_day = min(int(registration.day), 28)
        corrected = pd.Timestamp(
            year=corrected_year,
            month=int(registration.month),
            day=corrected_day,
        )
        enriched["input_registration_date"] = str(registration.date())
        enriched["registration_date"] = str(corrected.date())
        enriched["first_registration_date"] = str(corrected.date())
        warning_parts.append(
            f"输入上牌时间{registration.strftime('%Y-%m')}早于该车款合理范围，暂按{corrected.strftime('%Y-%m')}估价"
        )
    if warning_parts:
        enriched["catalog_resolution_warning"] = (
            "车型信息校正：" + "；".join(warning_parts) + "，请核对后再锁定最终价。"
        )
    return enriched


def _on_demand_exact_cell_quote(
    payload: dict[str, Any],
    target_side: str,
    reviewed: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Materialize one exact seven-element cell; a neighbour is evidence only."""

    global _ON_DEMAND_STORE
    if not ON_DEMAND_EXACT_CELL_ENABLED:
        return None
    trace = (reviewed or {}).get("price_trace") or {}
    ladder = (reviewed or {}).get("price_ladder") or {}
    model_id = (
        payload.get("model_id")
        or payload.get("modelId")
        or payload.get("vehicle_model_id")
        or trace.get("matched_model_id")
    )
    model_year = _model_year(payload) or trace.get("matched_model_year")
    trim = (
        payload.get("trim")
        or payload.get("model")
        or payload.get("standard_vehicle")
        or payload.get("standardVehicle")
        or payload.get("model_name")
        or trace.get("matched_trim")
    )
    if not model_id and model_year and trim:
        identity_text = "|".join(
            re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())
            for value in (
                payload.get("brand"),
                payload.get("series"),
                trim,
                int(float(model_year)),
            )
        )
        digest = hashlib.sha1(identity_text.encode("utf-8")).hexdigest()
        model_id = 890_000_000 + int(digest[:10], 16) % 9_000_000
    registration = (
        payload.get("registration_date")
        or payload.get("regDate")
        or payload.get("reg_date")
        or payload.get("first_registration_date")
        or payload.get("first_license_date")
        or payload.get("firstLicenseDate")
    )
    mileage_km = pd.to_numeric(payload.get("mileage_km"), errors="coerce")
    if pd.isna(mileage_km):
        mileage_wan = pd.to_numeric(
            payload.get("mileage_wan_km") or payload.get("mileage"), errors="coerce"
        )
        mileage_km = mileage_wan * 10_000.0 if pd.notna(mileage_wan) else np.nan
    city = payload.get("city") or payload.get("city_name")
    transfer = (
        payload.get("transfer_count")
        if payload.get("transfer_count") is not None
        else payload.get("transferCount")
        if payload.get("transferCount") is not None
        else payload.get("transfer")
    )
    color = payload.get("color") or payload.get("color_raw")
    condition = (
        payload.get("inspection_grade")
        or payload.get("condition_grade")
        or payload.get("condition")
        or "A"
    )
    required = [model_id, model_year, trim, registration, mileage_km, city, transfer, color]
    if any(value is None or value == "" or pd.isna(value) for value in required):
        return None
    with _ON_DEMAND_STORE_LOCK:
        if _ON_DEMAND_STORE is None:
            try:
                pointer = json.loads(
                    (_project_root() / "data/v195/current_daily_vehicle_price_knowledge.json")
                    .read_text(encoding="utf-8")
                )
                snapshot_path = Path(pointer["snapshot_path"])
                if not snapshot_path.is_absolute():
                    snapshot_path = _project_root() / snapshot_path
                _ON_DEMAND_STORE = DailyVehicleKnowledgeStore(
                    pd.read_parquet(snapshot_path),
                    root=_project_root(),
                    commercial_frame=None,
                )
            except (FileNotFoundError, OSError, ValueError, KeyError, json.JSONDecodeError):
                return None
    exact_payload = {
        **payload,
        "model_id": int(float(model_id)),
        "model_year": int(float(model_year)),
        "trim": trim,
        "registration_date": registration,
        "mileage_km": float(mileage_km),
        "city": city,
        "transfer_count": transfer,
        "color": color,
        "condition_grade": condition,
    }
    global _CATALOG_APPRAISER
    with _CATALOG_APPRAISER_LOCK:
        if _CATALOG_APPRAISER is None:
            try:
                _CATALOG_APPRAISER = InternalDcdCatalogAppraiser(_project_root())
            except (FileNotFoundError, OSError, ValueError, KeyError):
                _CATALOG_APPRAISER = None
    catalog_anchor = (
        _CATALOG_APPRAISER.quote(exact_payload)
        if _CATALOG_APPRAISER is not None
        else None
    )
    if catalog_anchor is not None:
        exact_payload["catalog_appraiser_identity_key"] = catalog_anchor.identity_key
        exact_payload["catalog_appraiser_b2c_support"] = catalog_anchor.b2c_support
        exact_payload["catalog_appraiser_c2b_support"] = catalog_anchor.c2b_support
        exact_payload["catalog_appraiser_c2b_recency_days"] = (
            catalog_anchor.c2b_recency_days
        )
        exact_payload["catalog_appraiser_deal_decision"] = (
            catalog_anchor.derivation.get("deal_decision")
        )
    catalog_deal_decision = str(
        (catalog_anchor.derivation if catalog_anchor is not None else {}).get(
            "deal_decision"
        )
        or ""
    )
    reviewed_b2c = pd.to_numeric(
        ladder.get("expected_b2c_transaction_yuan"), errors="coerce"
    )
    reviewed_c2b = pd.to_numeric(ladder.get("expected_c2b_yuan"), errors="coerce")
    fallback_b2c = (
        catalog_anchor.b2c_yuan
        if catalog_anchor is not None and catalog_anchor.b2c_yuan is not None
        else float(reviewed_b2c)
        if pd.notna(reviewed_b2c)
        else None
    )
    fallback_c2b = (
        catalog_anchor.c2b_yuan
        if catalog_anchor is not None and catalog_anchor.c2b_yuan is not None
        else float(reviewed_c2b)
        if pd.notna(reviewed_c2b)
        else None
    )
    result = _ON_DEMAND_STORE.lookup(
        exact_payload,
        fallback_b2c_yuan=fallback_b2c,
        fallback_c2b_yuan=fallback_c2b,
        target_side=target_side,
        materialize_on_miss=True,
        allow_trusted_snapshot_hit=False,
    )
    pricing_only_market_panel = bool(
        catalog_anchor is not None
        and catalog_anchor.derivation.get("pricing_is_independent_from_selection") is True
        and catalog_deal_decision.startswith("PRICING_QUOTE")
        and catalog_anchor.b2c_yuan is not None
        and catalog_anchor.c2b_yuan is not None
    )
    if pricing_only_market_panel:
        # Pricing answers the market value.  The selection module consumes the
        # profit-safe ceiling separately; it must not be allowed to clamp or
        # suppress the market acquisition quote here.
        market_b2c = float(catalog_anchor.b2c_yuan)
        market_c2b = min(float(catalog_anchor.c2b_yuan), market_b2c * 0.965)
        market_max_c2b = pd.to_numeric(
            catalog_anchor.derivation.get("max_c2b_market_yuan"), errors="coerce"
        )
        market_max_c2b = (
            float(market_max_c2b)
            if pd.notna(market_max_c2b)
            else market_c2b * 1.025
        )
        market_max_c2b = min(max(market_max_c2b, market_c2b * 1.01), market_b2c * 0.975)
        market_b2c_low = market_b2c * 0.975
        market_b2c_high = market_b2c * 1.025
        market_listing = pd.to_numeric(
            ladder.get("recommended_listing_yuan"), errors="coerce"
        )
        market_listing = (
            float(market_listing)
            if pd.notna(market_listing) and float(market_listing) >= market_b2c_high
            else market_b2c * 1.055
        )
        market_listing_low = max(
            market_listing * 0.98,
            market_b2c_high + max(100.0, market_b2c * 0.001),
        )
        market_listing = max(
            market_listing,
            market_listing_low + max(100.0, market_b2c * 0.001),
        )
        market_c2b_low = market_c2b * 0.97
        market_c2b_high = min(market_c2b * 1.025, market_max_c2b)
        result.update(
            {
                "quote_decision": "PRICING_QUOTE_MARKET_VALUE",
                "recommended_listing_price": round(market_listing, 2),
                "recommended_listing_price_low": round(market_listing_low, 2),
                "recommended_listing_price_high": round(market_listing * 1.025, 2),
                "expected_b2c_transaction_price": round(market_b2c, 2),
                "expected_b2c_transaction_price_low": round(market_b2c_low, 2),
                "expected_b2c_transaction_price_high": round(market_b2c_high, 2),
                "max_c2b_acquisition_price": round(market_max_c2b, 2),
                "expected_final_c2b_price": round(market_c2b, 2),
                "expected_final_c2b_price_low": round(market_c2b_low, 2),
                "expected_final_c2b_price_high": round(market_c2b_high, 2),
                "recommended_acquisition_price": round(
                    market_c2b_low + (market_c2b - market_c2b_low) * 0.55, 2
                ),
                "recommended_first_offer": round(market_c2b_low * 0.97, 2),
                "c2b_pricing_route": (
                    f"{catalog_anchor.route}+MARKET_C2B_APPRAISER_SIGNOFF"
                ),
                "requested_final_c2b_price": round(market_c2b, 2),
                "profitable_c2b_ceiling": None,
                "c2b_profitability_clamp_used": False,
                "business_cost_inputs": {},
            }
        )
    if catalog_anchor is not None:
        b2c_route = str(result.get("b2c_pricing_route") or "")
        result["b2c_pricing_route"] = b2c_route.replace(
            "MODEL_FALLBACK_L5", catalog_anchor.route
        )
    if result.get("knowledge_lookup_route") not in {
        "ON_DEMAND_STRICT_PRICE_CELL",
        "ON_DEMAND_EXACT_CELL_CACHE_HIT",
        "TRUSTED_MATERIALIZED_CELL_HIT",
        "MANUAL_APPRAISER_EXACT_CELL",
    }:
        return None
    is_b2c = target_side.upper() == "B2C"
    point_field = "expected_b2c_transaction_price" if is_b2c else "expected_final_c2b_price"
    low_field = (
        "expected_b2c_transaction_price_low"
        if is_b2c
        else "expected_final_c2b_price_low"
    )
    high_field = (
        "expected_b2c_transaction_price_high"
        if is_b2c
        else "expected_final_c2b_price_high"
    )
    point = float(result[point_field])
    low = float(result[low_field])
    high = float(result[high_field])
    appraiser_record = build_appraiser_decision_record(
        payload=exact_payload,
        target_side=target_side,
        result=result,
        catalog_anchor=catalog_anchor,
    )
    catalog_resolution_warning = str(
        exact_payload.get("catalog_resolution_warning") or ""
    ).strip()
    risk_warnings: list[str] = []
    if catalog_resolution_warning:
        risk_warnings.append(catalog_resolution_warning)
    if result.get("knowledge_confidence") == "LOW":
        risk_warnings.append(
            "当前这台车的具体信息已独立生成价格，但近期完全同款成交较少，建议结合验车复核。"
        )
    response = {
        "success": True,
        "quote_id": payload.get("request_id") or payload.get("quote_id"),
        "knowledge_cell_id": result.get("knowledge_cell_id"),
        "pricing_engine_used": "V195_ON_DEMAND_EXACT_PRICE_CELL",
        "pricing_engine_version": "v195.402",
        "model_version": "v195_402_catalog_identity_price_book",
        "policy_version": "V195_AUDITED_EXACT_SEVEN_ELEMENT_PRICE_BOOK",
        "target_price_role": f"{target_side.upper()}_EXACT_SEVEN_ELEMENT_PRICE",
        "final_price": round(point, 2),
        "display_price_wan": round(point / 10_000.0, 2),
        "price_result": {
            "final_price": round(point, 2),
            "price_low": round(low, 2),
            "price_high": round(high, 2),
            "confidence": result.get("knowledge_confidence", "LOW"),
            "reasonableness_level": "EXACT_CELL_MULTI_SOURCE",
            "display_type": "EXACT_SEVEN_ELEMENT_PRICE",
        },
        "interval": {"low": round(low, 2), "high": round(high, 2)},
        "confidence": result.get("knowledge_confidence", "LOW"),
        "quote_decision": result.get("quote_decision"),
        "deal_decision": catalog_deal_decision or result.get("quote_decision"),
        "catalog_resolution_warning": catalog_resolution_warning or None,
        "knowledge_lookup_route": result.get("knowledge_lookup_route"),
        "price_ladder": {
            "recommended_listing_yuan": result.get("recommended_listing_price"),
            "recommended_listing_range_yuan": [
                result.get("recommended_listing_price_low"),
                result.get("recommended_listing_price_high"),
            ],
            "expected_b2c_transaction_yuan": result.get("expected_b2c_transaction_price"),
            "b2c_transaction_range_yuan": [
                result.get("expected_b2c_transaction_price_low"),
                result.get("expected_b2c_transaction_price_high"),
            ],
            "expected_c2b_yuan": result.get("expected_final_c2b_price"),
            "c2b_range_yuan": [
                result.get("expected_final_c2b_price_low"),
                result.get("expected_final_c2b_price_high"),
            ],
            "first_c2b_offer_yuan": result.get("recommended_first_offer"),
            "max_c2b_yuan": result.get("max_c2b_acquisition_price"),
        },
        "recommended_listing_price_yuan": result.get("recommended_listing_price"),
        "recommended_listing_range_yuan": [
            result.get("recommended_listing_price_low"),
            result.get("recommended_listing_price_high"),
        ],
        "first_c2b_offer_yuan": result.get("recommended_first_offer"),
        "max_c2b_price_yuan": result.get("max_c2b_acquisition_price"),
        "price_trace": {
            "baseline_method": "V195_ON_DEMAND_EXACT_SEVEN_ELEMENT_CELL",
            "knowledge_cell_id": result.get("knowledge_cell_id"),
            "exact_seven_element_fingerprint": result.get("knowledge_cell_id"),
            "b2c_pricing_route": result.get("b2c_pricing_route"),
            "c2b_pricing_route": result.get("c2b_pricing_route"),
            "external_b2c_proxy_yuan": result.get("external_b2c_proxy_yuan"),
            "external_source_count": result.get("external_source_count"),
            "exact_dcd_vehicle_match": result.get("exact_dcd_vehicle_match"),
            "exact_dcd_vehicle_listing_yuan": result.get(
                "exact_dcd_vehicle_listing_yuan"
            ),
            "exact_dcd_vehicle_sku_id": result.get("exact_dcd_vehicle_sku_id"),
            "comparable_is_evidence_only": True,
            "catalog_appraiser_identity_key": (
                catalog_anchor.identity_key if catalog_anchor is not None else None
            ),
            "catalog_appraiser_route": (
                catalog_anchor.route if catalog_anchor is not None else None
            ),
            "catalog_appraiser_b2c_support": (
                catalog_anchor.b2c_support if catalog_anchor is not None else 0
            ),
            "catalog_appraiser_c2b_support": (
                catalog_anchor.c2b_support if catalog_anchor is not None else 0
            ),
            "official_guide_price_used": False,
            "pricing_is_independent_from_selection": pricing_only_market_panel,
        },
        "appraiser_decision_record": appraiser_record,
        "business_explanation": {
            "format_version": "v195_appraiser_price_book_explanation_v1",
            "conclusion": {
                "target_side": target_side.upper(),
                "reference_price_yuan": round(point, 2),
                "interval_yuan": [round(low, 2), round(high, 2)],
                "evidence_score": appraiser_record["confidence"]["evidence_score"],
                "decision": appraiser_record["confidence"]["decision"],
            },
            "why_this_price": appraiser_record["why_this_price"],
            "calculation_logic": {
                "identity": "严格品牌+车系+车款+年款；配置不兼容即拒绝召回。",
                "b2c": "同款同年内部成交时效修正中枢，与三方挂牌折扣后的成交代理交叉校验，再按七要素生成独立价格。",
                "c2b": (
                    "使用近期同款同年真实收车证据，按本车七要素修正后给出市场可成交收车价。"
                    if pricing_only_market_panel
                    else "优先使用近期同款同年直接收车证据，并受B2C可售价格减整备、物流、资金、销售、风险和最低利润后的上限约束。"
                ),
                "listing": "当前三方同款挂牌证据与成交价上浮议价空间共同确定；挂牌价不作为成交真值。",
            },
            "seven_element_adjustment_ledger": appraiser_record[
                "seven_element_adjustment_ledger"
            ],
            "rejected_anchors": appraiser_record["rejected_anchors"],
        },
        "risk_warnings": risk_warnings,
        "normalized_query": exact_payload,
        "reason": (
            "该七要素已按当前市场收售证据独立生成完整价格梯度。"
            if pricing_only_market_panel
            else "该七要素已独立生成价格；近邻仅作修正证据，未直接继承近邻答案。"
        ),
    }
    b2c_wan = round(float(result["expected_b2c_transaction_price"]) / 10_000.0, 2)
    c2b_wan = round(float(result["expected_final_c2b_price"]) / 10_000.0, 2)
    response.update(
        {
            "b2cPrice": b2c_wan,
            "b2c_price": b2c_wan,
            "targetB2C": b2c_wan,
            "b2cRange": [
                round(float(result["expected_b2c_transaction_price_low"]) / 10_000.0, 2),
                round(float(result["expected_b2c_transaction_price_high"]) / 10_000.0, 2),
            ],
            "c2bPrice": c2b_wan,
            "c2b_price": c2b_wan,
            "targetC2B": c2b_wan,
            "c2bRange": [
                round(float(result["expected_final_c2b_price_low"]) / 10_000.0, 2),
                round(float(result["expected_final_c2b_price_high"]) / 10_000.0, 2),
            ],
        }
    )
    listing_wan = float(result["recommended_listing_price"]) / 10_000.0
    max_c2b_wan = float(result["max_c2b_acquisition_price"]) / 10_000.0
    b2c_low_wan = float(result["expected_b2c_transaction_price_low"]) / 10_000.0
    b2c_high_wan = float(result["expected_b2c_transaction_price_high"]) / 10_000.0
    c2b_low_wan = float(result["expected_final_c2b_price_low"]) / 10_000.0
    c2b_high_wan = float(result["expected_final_c2b_price_high"]) / 10_000.0
    warning_prefix = f"{catalog_resolution_warning} " if catalog_resolution_warning else ""
    response["frontline_answer"] = (
        f"{warning_prefix}建议挂牌{listing_wan:.2f}万，预计{b2c_wan:.2f}万左右成交，"
        f"正常成交区间{b2c_low_wan:.2f}-{b2c_high_wan:.2f}万。"
        f"预计实际收车{c2b_wan:.2f}万，正常收车区间{c2b_low_wan:.2f}-{c2b_high_wan:.2f}万，"
        f"最高收车价{max_c2b_wan:.2f}万。"
    )
    return response


def _project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT") or ROOT)


def _as_float(value: Any, default: float = 0.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return default
    return float(numeric)


def _timestamp_utc_naive(value: Any) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return pd.NaT
    return timestamp.tz_convert(None)


def _model_year(payload: dict[str, Any]) -> int | None:
    for key in ("model_year", "modelYear", "vehicle_model_year", "model", "trim"):
        text = str(payload.get(key) or "")
        match = pd.Series([text]).str.extract(r"((?:19|20)\d{2})")[0].iloc[0]
        if pd.notna(match):
            return int(match)
    return None


def _quote_time(payload: dict[str, Any]) -> pd.Timestamp:
    for key in ("quote_time", "prediction_time", "target_date", "event_time"):
        if payload.get(key):
            value = pd.to_datetime(payload.get(key), errors="coerce")
            if pd.notna(value):
                return value
    return pd.Timestamp(datetime.now())


def _current_market_guard_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """Allow current online listing evidence only for live quotes.

    DCD listings are a current-market sanity rail, not a historical label source.
    If a request carries an explicit historical quote time or uploaded actuals,
    the guard is disabled so blind backtests remain legal.
    """

    force = str(payload.get("allow_current_market_evidence") or "").strip().lower()
    if force in {"1", "true", "yes", "on"}:
        return {"allowed": True, "reason": "CURRENT_MARKET_FORCED_BY_CALLER"}

    historical_markers = (
        "source_file",
        "source_path",
        "eval_file",
        "actual_price",
        "actual_price_yuan",
        "target_price_yuan",
        "latest_order_sold_price_yuan",
        "latest_sold_price_yuan",
        "c2b_purchase_price_yuan",
        "收车合同价",
        "最新订单成交价",
    )
    for key in historical_markers:
        if payload.get(key) not in (None, ""):
            return {"allowed": False, "reason": f"DCD_CURRENT_MARKET_DISABLED_FOR_HISTORICAL_EVAL_MARKER:{key}"}

    for key in ("quote_time", "prediction_time", "target_date", "event_time"):
        if not payload.get(key):
            continue
        timestamp = _timestamp_utc_naive(payload.get(key))
        if pd.isna(timestamp):
            continue
        now = pd.Timestamp(datetime.now())
        if timestamp < now - pd.Timedelta(days=2):
            return {
                "allowed": False,
                "reason": "DCD_CURRENT_MARKET_DISABLED_FOR_HISTORICAL_QUOTE_TIME",
                "quote_time": str(timestamp),
            }
        return {"allowed": True, "reason": "CURRENT_MARKET_QUOTE_TIME_IS_RECENT", "quote_time": str(timestamp)}

    return {"allowed": True, "reason": "LIVE_QUOTE_WITHOUT_HISTORICAL_MARKERS"}


def _payload_to_query(payload: dict[str, Any]) -> dict[str, Any]:
    model_year = _model_year(payload)
    age = _as_float(payload.get("age_years"), default=np.nan)
    if pd.isna(age):
        reg_date = pd.to_datetime(
            payload.get("regDate")
            or payload.get("reg_date")
            or payload.get("first_registration_date")
            or payload.get("first_license_date")
            or payload.get("firstLicenseDate"),
            errors="coerce",
        )
        quote_time = _quote_time(payload)
        if pd.notna(reg_date):
            age = max(0.0, (quote_time - reg_date).days / 365.25)
        else:
            age = 0.0
    risk_flag = any(
        str(payload.get(key) or "").strip().lower() in {"1", "true", "yes", "是"}
        for key in ("is_accident", "is_flood", "is_fire", "is_odometer_abnormal")
    )
    grade = str(payload.get("inspection_grade") or payload.get("condition_grade") or "").strip().upper()
    raw_condition = str(payload.get("condition_risk_level_strict") or payload.get("condition") or "").strip()
    if raw_condition in {"clean", "minor_defect", "major_risk", "unknown", "unknown_report"}:
        condition = "unknown" if raw_condition == "unknown_report" else raw_condition
        condition_assumption = "EXPLICIT_CONDITION_FROM_PAYLOAD"
    else:
        condition = "major_risk" if risk_flag or grade in {"D", "E"} else "minor_defect" if grade == "C" else "clean"
        condition_assumption = (
            "SYSTEM_DEFAULT_GOOD_CONDITION"
            if payload.get("condition_is_default")
            else "INSPECTION_CONFIRMED_CONDITION" if grade
            else "SYSTEM_DEFAULT_GOOD_CONDITION"
        )
    return {
        "query_uid": str(payload.get("request_id") or payload.get("quote_id") or "v194_live_query"),
        "brand": str(payload.get("brand") or ""),
        "series": str(payload.get("series") or ""),
        "model_year": model_year,
        "model_id": str(payload.get("model_id") or payload.get("modelId") or payload.get("vehicle_model_id") or ""),
        "trim": str(
            payload.get("trim")
            or payload.get("standard_vehicle")
            or payload.get("raw_vehicle_text")
            or payload.get("model")
            or ""
        ),
        "model": str(
            payload.get("model")
            or payload.get("trim")
            or payload.get("standard_vehicle")
            or payload.get("raw_vehicle_text")
            or ""
        ),
        "city": str(payload.get("city") or ""),
        "color": str(payload.get("color") or payload.get("color_raw") or ""),
        "age_years": float(age),
        "mileage_wan_km": _as_float(payload.get("mileage_wan_km", payload.get("mileage")), default=0.0),
        "transfer_count": _as_float(payload.get("transfer_count", payload.get("transfer")), default=0.0),
        "is_new_energy": payload.get("is_new_energy"),
        "energy_type": payload.get("energy_type") or payload.get("query_energy_type"),
        "condition_risk_level_strict": condition,
        "inspection_grade_norm": grade if grade in {"A", "B", "C", "D", "E"} else "missing",
        "inspection_score": _as_float(payload.get("inspection_score") or payload.get("condition_score"), default=-1.0),
        "condition_assumption": condition_assumption,
        "source_file": str(payload.get("source_file") or payload.get("sourceFile") or ""),
        "raw_index": payload.get("raw_index", payload.get("source_row_id", payload.get("sourceRowId", ""))),
        "goods_id": str(payload.get("goods_id") or payload.get("goodsId") or payload.get("vehicle_id") or ""),
        "product_id": str(payload.get("product_id") or payload.get("productId") or payload.get("listing_id") or ""),
        "use_full_knowledge_candidates": bool(payload.get("use_full_knowledge_candidates") or payload.get("full_knowledge_candidates")),
        "year_consistency_warning": str(payload.get("year_consistency_warning") or ""),
        "catalog_source": str(payload.get("catalogSource") or payload.get("catalog_source") or ""),
        "catalog_source_url": str(payload.get("catalogSourceUrl") or payload.get("catalog_source_url") or ""),
        "catalog_coverage_level": str(payload.get("catalogCoverageLevel") or payload.get("catalog_coverage_level") or ""),
        "catalog_official_price_min": _currency(
            payload.get("catalogOfficialPriceMin") or payload.get("catalog_official_price_min")
        ),
        "catalog_official_price_max": _currency(
            payload.get("catalogOfficialPriceMax") or payload.get("catalog_official_price_max")
        ),
        "b2c_listing_price_yuan": _currency(
            payload.get("b2c_listing_price_yuan")
            or payload.get("current_listing_price_yuan")
            or payload.get("current_display_price_yuan")
            or payload.get("listing_price_yuan")
        ),
        "b2c_listing_price_source": str(
            payload.get("b2c_listing_price_source")
            or payload.get("current_listing_price_source")
            or payload.get("listing_price_source")
            or ""
        ),
        "current_listing_price_yuan": _currency(
            payload.get("current_listing_price_yuan")
            or payload.get("current_display_price_yuan")
            or payload.get("b2c_listing_price_yuan")
            or payload.get("listing_price_yuan")
        ),
        "first_listing_price_yuan": _currency(payload.get("first_listing_price_yuan") or payload.get("first_display_price_yuan")),
        "c2b_purchase_price_yuan": _currency(
            payload.get("c2b_purchase_price_yuan")
            or payload.get("purchase_price_yuan")
            or payload.get("收车合同价")
        ),
        "b2c_disposal_flag": str(payload.get("b2c_disposal_flag") or payload.get("是否B2C处置") or ""),
        "used_as_b2c_bridge_context": bool(payload.get("used_as_b2c_bridge_context")),
        "quote_time": _quote_time(payload),
    }


def _commercial_full_knowledge_quote(
    payload: dict[str, Any], target_side: str
) -> dict[str, Any] | None:
    """Return the supervised exact-cell ladder before the v194 fallback chain."""

    global _COMMERCIAL_STORE
    if not SUPERVISED_COMMERCIAL_ROUTE_ENABLED:
        return None
    model_id = payload.get("model_id") or payload.get("modelId") or payload.get("vehicle_model_id")
    model_year = _model_year(payload)
    registration = (
        payload.get("registration_date")
        or payload.get("regDate")
        or payload.get("reg_date")
        or payload.get("first_registration_date")
        or payload.get("first_license_date")
        or payload.get("firstLicenseDate")
    )
    mileage_km = pd.to_numeric(payload.get("mileage_km"), errors="coerce")
    if pd.isna(mileage_km):
        mileage_wan = pd.to_numeric(
            payload.get("mileage_wan_km") or payload.get("mileage"), errors="coerce"
        )
        mileage_km = mileage_wan * 10_000.0 if pd.notna(mileage_wan) else np.nan
    city = payload.get("city") or payload.get("city_name")
    transfer = payload.get("transfer_count")
    color = payload.get("color") or payload.get("color_raw")
    condition = payload.get("inspection_grade") or payload.get("condition_grade")
    required = [model_id, model_year, registration, mileage_km, city, transfer, color, condition]
    if any(value is None or value == "" or pd.isna(value) for value in required):
        return None
    with _COMMERCIAL_STORE_LOCK:
        if _COMMERCIAL_STORE is None:
            try:
                _COMMERCIAL_STORE = DailyVehicleKnowledgeStore.load_current(_project_root())
            except (FileNotFoundError, OSError, ValueError, KeyError):
                return None
    result = _COMMERCIAL_STORE.lookup(
        {
            "model_id": model_id,
            "model_year": model_year,
            "registration_date": registration,
            "mileage_km": float(mileage_km),
            "city": city,
            "transfer_count": transfer,
            "color": color,
            "condition_grade": condition,
        },
        target_side=target_side,
        materialize_on_miss=False,
    )
    if result.get("knowledge_lookup_route") != "SUPERVISED_COMMERCIAL_EXACT_CELL":
        return None
    is_b2c = target_side.upper() == "B2C"
    point_field = "expected_b2c_transaction_price" if is_b2c else "expected_final_c2b_price"
    low_field = "expected_b2c_transaction_price_low" if is_b2c else "expected_final_c2b_price_low"
    high_field = "expected_b2c_transaction_price_high" if is_b2c else "expected_final_c2b_price_high"
    point = float(result[point_field])
    low = float(result[low_field])
    high = float(result[high_field])
    price_wan = round(point / 10_000.0, 2)
    range_wan = [round(low / 10_000.0, 2), round(high / 10_000.0, 2)]
    response = {
        "success": True,
        "quote_id": payload.get("request_id") or payload.get("quote_id"),
        "pricing_engine_used": "V195_SUPERVISED_COMMERCIAL_PRICE_BOOK",
        "pricing_engine_version": "v195.380",
        "model_version": "v195_380_supervised_commercial_price_book",
        "policy_version": "ORACLE_ASSISTED_COMMERCIAL_FULL_KNOWLEDGE",
        "target_price_role": f"{target_side.upper()}_COMMERCIAL_FULL_KNOWLEDGE",
        "final_price": round(point, 2),
        "display_price_wan": price_wan,
        "price_result": {
            "final_price": round(point, 2),
            "price_low": low,
            "price_high": high,
            "confidence": "HIGH",
            "reasonableness_level": "SUPERVISED_FULL_KNOWLEDGE",
            "display_type": "AUTO_SINGLE_POINT",
        },
        "interval": {"low": low, "high": high},
        "confidence": "HIGH",
        "quote_decision": "AUTO_SINGLE_POINT",
        "knowledge_lookup_route": result["knowledge_lookup_route"],
        "commercial_price_ladder": {
            field: result[field] for field in (
                "recommended_listing_price_high",
                "recommended_listing_price",
                "recommended_listing_price_low",
                "expected_b2c_transaction_price_high",
                "expected_b2c_transaction_price",
                "expected_b2c_transaction_price_low",
                "max_c2b_acquisition_price",
                "expected_final_c2b_price_high",
                "expected_final_c2b_price",
                "recommended_acquisition_price",
                "expected_final_c2b_price_low",
                "recommended_first_offer",
            )
        },
        "price_trace": {
            "baseline_method": "SUPERVISED_COMMERCIAL_EXACT_SEVEN_ELEMENT_CELL",
            "knowledge_cell_id": result.get("knowledge_cell_id"),
            "confirmed_count": result.get("confirmed_count"),
            "supervised_weight": result.get("supervised_weight"),
            "data_cutoff": result.get("data_cutoff"),
        },
    }
    if is_b2c:
        response.update({"b2cPrice": price_wan, "b2c_price": price_wan, "targetB2C": price_wan, "b2cRange": range_wan})
    else:
        response.update({"c2bPrice": price_wan, "c2b_price": price_wan, "targetC2B": price_wan, "c2bRange": range_wan})
    return response


def _is_b2c_pricing_task(payload: dict[str, Any]) -> bool:
    """Return True for retail/sale pricing tasks.

    The default product path is C2B 收车价.  B2C must be explicit because using
    a C2B quote against latest order sold price was the source of the previous
    B2C MAPE inflation.
    """

    keys = (
        "pricing_task",
        "task_type",
        "target_type",
        "business_type",
        "valuation_type",
        "price_role",
        "module",
        "selectedBusinessModule",
        "intent",
    )
    text = " ".join(str(payload.get(key) or "").lower() for key in keys)
    if any(token in text for token in ("b2c", "retail", "sale", "sell", "sold", "售车", "卖车", "出售")):
        return True
    if any(token in text for token in ("c2b", "purchase", "buy", "收车", "收购")):
        return False
    return False


def _homogeneous_key(normalized: dict[str, Any], condition: str) -> str:
    age = pd.to_numeric(normalized.get("age_years"), errors="coerce")
    mileage = pd.to_numeric(normalized.get("mileage_wan_km"), errors="coerce")
    transfer = pd.to_numeric(normalized.get("transfer_count"), errors="coerce")
    year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
    age_value = round(float(age), 1) if pd.notna(age) else -1
    mileage_value = round(float(mileage) * 2) / 2 if pd.notna(mileage) else -1
    transfer_value = round(float(transfer)) if pd.notna(transfer) else -1
    year_value = int(year) if pd.notna(year) else -1
    return (
        f"{normalized.get('brand_key') or ''}|{normalized.get('series_key') or ''}|{year_value}|"
        f"{normalized.get('canonical_trim_key') or ''}|age={age_value}|mile={mileage_value}|"
        f"transfer={transfer_value}|city={normalized.get('city_key_v194') or ''}|condition={condition}"
    )


def _six_element_source_manual_key(normalized: dict[str, Any], condition: str, *, with_color: bool = True) -> str:
    age = pd.to_numeric(normalized.get("age_years"), errors="coerce")
    mileage = pd.to_numeric(normalized.get("mileage_wan_km"), errors="coerce")
    transfer = pd.to_numeric(normalized.get("transfer_count"), errors="coerce")
    year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
    age_value = round(float(age), 1) if pd.notna(age) else -1
    mileage_value = round(float(mileage) * 2) / 2 if pd.notna(mileage) else -1
    transfer_value = round(float(transfer)) if pd.notna(transfer) else -1
    year_value = int(year) if pd.notna(year) else -1
    color = normalized.get("color_key_v194") or ""
    color_part = f"|color={color}" if with_color else "|color=*"
    return (
        f"{normalized.get('brand_key') or ''}|{normalized.get('series_key') or ''}|{year_value}|"
        f"{normalized.get('canonical_trim_key') or ''}|age={age_value}|mile={mileage_value}|"
        f"transfer={transfer_value}|city={normalized.get('city_key_v194') or ''}"
        f"{color_part}|condition={condition}"
    )


def _memory_value(value: Any, width: float) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "-1"
    rounded = round(float(numeric) / width) * width
    return str(round(rounded, 2))


def _daily_source_memory_key_variants(normalized: dict[str, Any], condition: str) -> list[tuple[str, str]]:
    year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
    year_value = int(year) if pd.notna(year) else -1
    transfer = pd.to_numeric(normalized.get("transfer_count"), errors="coerce")
    transfer_value = int(round(float(transfer))) if pd.notna(transfer) else -1
    brand = str(normalized.get("brand_key") or "")
    series = str(normalized.get("series_key") or "")
    canonical = str(normalized.get("canonical_trim_key") or "")
    city = str(normalized.get("city_key_v194") or "")
    color = str(normalized.get("color_key_v194") or "")
    age_micro = _memory_value(normalized.get("age_years"), 0.25)
    mile_micro = _memory_value(normalized.get("mileage_wan_km"), 0.5)
    prefix = f"{brand}|{series}|{year_value}|{canonical}"
    return [
        (
            "exact_six",
            f"{prefix}|age={age_micro}|mile={mile_micro}|transfer={transfer_value}|city={city}|color={color}|condition={condition}",
        ),
        (
            "no_color",
            f"{prefix}|age={age_micro}|mile={mile_micro}|transfer={transfer_value}|city={city}|condition={condition}",
        ),
        (
            "no_city_color",
            f"{prefix}|age={age_micro}|mile={mile_micro}|transfer={transfer_value}|condition={condition}",
        ),
        (
            "micro",
            f"{canonical}|age_micro={age_micro}|mile_micro={mile_micro}|transfer={transfer_value}|condition={condition}",
        ),
        # Broader trim/year or series/year keys are useful for diagnostics and
        # manual review, but they were too coarse for automatic point-price
        # overrides on fresh uploads.  Runtime source memory therefore stops at
        # six-element-near / micro-bin evidence; broad keys stay in the CSV
        # artifact for analysis, not for direct price replacement.
    ]


def _quarter_bin(value: Any, width: float = 0.25) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return -1.0
    return round(float(numeric) / width) * width


def _v19492_manual_key(
    normalized: dict[str, Any],
    query: dict[str, Any],
    *,
    city: str | None = None,
    color: str | None = None,
    condition: str | None = None,
    grade: str | None = None,
) -> str:
    year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
    year_value = int(year) if pd.notna(year) else -1
    grade_value = str(
        grade
        if grade is not None
        else query.get("inspection_grade_norm")
        or query.get("inspection_grade")
        or "missing"
    ).strip().upper()
    if grade_value == "*":
        pass
    elif grade_value not in {"A", "B", "C", "D", "E"}:
        grade_value = "missing"
    return "|".join(
        [
            str(normalized.get("brand_key") or ""),
            str(normalized.get("series_key") or ""),
            str(normalized.get("canonical_trim_key") or ""),
            str(year_value),
            str(city if city is not None else normalized.get("city_key_v194") or ""),
            str(color if color is not None else normalized.get("color_key_v194") or ""),
            str(condition if condition is not None else query.get("condition_risk_level_strict") or "clean"),
            grade_value,
            str(_quarter_bin(normalized.get("age_years"), 0.25)),
            str(_quarter_bin(normalized.get("mileage_wan_km"), 0.25)),
            str(int(round(_as_float(normalized.get("transfer_count"), -1.0)))),
        ]
    )


def _strip_energy_token_from_canonical_key(value: Any) -> str:
    parts = str(value or "").split("|")
    if len(parts) >= 5 and parts[3] in {"ICE", "BEV", "PHEV", "HEV", "EREV", "UNKNOWN"}:
        return "|".join(parts[:3] + parts[4:])
    return str(value or "")


def _strip_energy_token_from_manual_key(value: Any) -> str:
    text = str(value or "")
    age_marker = "|age=" if "|age=" in text else "|age_micro=" if "|age_micro=" in text else ""
    if not age_marker:
        return text
    prefix, suffix = text.split(age_marker, 1)
    parts = prefix.split("|")
    energy_tokens = {"ICE", "BEV", "PHEV", "HEV", "EREV", "UNKNOWN"}
    stripped_parts = [part for part in parts if part not in energy_tokens]
    return "|".join(stripped_parts) + age_marker + suffix


def _strip_brand_prefix_from_series_key(brand: Any, series: Any) -> str:
    brand_text = str(brand or "").strip()
    series_text = str(series or "").strip()
    if brand_text and series_text.lower().startswith(brand_text.lower()) and len(series_text) > len(brand_text):
        return series_text[len(brand_text) :]
    return series_text


def _brand_series_manual_key_aliases(value: Any) -> list[str]:
    text = str(value or "")
    age_marker = "|age=" if "|age=" in text else "|age_micro=" if "|age_micro=" in text else ""
    if not age_marker:
        return [text] if text else []
    prefix, suffix = text.split(age_marker, 1)
    parts = prefix.split("|")
    if len(parts) < 3:
        return [text]
    brand = parts[0]
    series = parts[1]
    series_options = list(dict.fromkeys([series, _strip_brand_prefix_from_series_key(brand, series)]))
    embedded_series_index = 4 if len(parts) > 4 and parts[3] == brand else None
    embedded_options = [None]
    if embedded_series_index is not None:
        embedded_options = list(
            dict.fromkeys(
                [
                    parts[embedded_series_index],
                    _strip_brand_prefix_from_series_key(brand, parts[embedded_series_index]),
                ]
            )
        )
    aliases: list[str] = []
    for series_value in series_options:
        for embedded_value in embedded_options:
            candidate_parts = list(parts)
            candidate_parts[1] = series_value
            if embedded_series_index is not None and embedded_value is not None:
                candidate_parts[embedded_series_index] = embedded_value
            aliases.append("|".join(candidate_parts) + age_marker + suffix)
    return list(dict.fromkeys(alias for alias in aliases if alias and alias.lower() != "nan"))


def _manual_key_age_variants(value: Any, step: float = 0.1) -> list[str]:
    text = str(value or "")
    match = re.search(r"\|age=([-0-9.]+)\|mile=", text)
    if not match:
        return [text] if text else []
    age = pd.to_numeric(match.group(1), errors="coerce")
    if pd.isna(age) or float(age) < 0:
        return [text]
    variants = [text]
    for delta in (-step, step):
        new_age = round(float(age) + delta, 1)
        variants.append(text[: match.start(1)] + str(new_age) + text[match.end(1) :])
    return list(dict.fromkeys(variants))


def _currency(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def _v194263_compact(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value).strip().lower())


def _v194263_series_alias(value: Any) -> str:
    """Coarse series key for broad support fallback only."""

    text = _v194263_compact(value)
    for token in ("进口", "国产", "经典", "新能源", "phev", "hev", "ev"):
        text = text.replace(token, "")
    return text


def _v194263_trim_tokens(value: Any) -> set[str]:
    text = _v194263_compact(value)
    if not text:
        return set()
    tokens = set(re.findall(r"[a-z]+\d*|\d+[a-z]*|[\u4e00-\u9fff]{2,}", text))
    for token in ("自动", "手动", "四驱", "两驱", "豪华", "时尚", "舒适", "运动", "旗舰", "尊贵", "智享", "进取"):
        if token in text:
            tokens.add(token)
    return tokens


def _v194263_token_similarity(left: Any, right: Any) -> float:
    left_tokens = _v194263_trim_tokens(left)
    right_tokens = _v194263_trim_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _wan(value: Any) -> float | None:
    numeric = _currency(value)
    if numeric is None:
        return None
    return round(numeric / 10000.0, 2)


def _format_wan(value: Any) -> str:
    numeric = _wan(value)
    return "-" if numeric is None else f"{numeric:.2f}万"


def _candidate_record(row: dict[str, Any]) -> dict[str, Any]:
    price = _currency(row.get("price_yuan"))
    vehicle = " ".join(
        [
            str(row.get("brand") or ""),
            str(row.get("series") or ""),
            str(row.get("model_year") or "").replace(".0", ""),
            str(row.get("trim") or ""),
        ]
    ).strip()
    weight = _currency(row.get("final_retrieval_weight"))
    point_baseline = bool(row.get("used_for_point_baseline", False))
    interval_only = bool(row.get("used_for_interval", False)) and not point_baseline
    price_role = str(row.get("price_role") or "")
    candidate_role = (
        "POINT_PRICE_EVIDENCE"
        if point_baseline
        else "B2C_MARKET_CONTEXT_ONLY"
        if price_role in {"EXTERNAL_B2C_LISTING", "INTERNAL_B2C_SOLD_ACTUAL"}
        else "INTERVAL_OR_MANUAL_CONTEXT_ONLY"
        if interval_only
        else "NON_POINT_REFERENCE"
    )
    return {
        "candidate_id": str(row.get("observation_id") or ""),
        "lifecycle_key": str(row.get("runtime_candidate_lifecycle_key") or row.get("observation_id") or ""),
        "source_type": str(row.get("source_type") or ""),
        "source_family": str(row.get("source_type") or ""),
        "price_role": str(row.get("price_role") or ""),
        "original_price_role": str(row.get("price_role") or ""),
        "price": price,
        "price_wan": round(price / 10000.0, 6) if price else None,
        "original_price": price,
        "converted_c2b_price": _currency(row.get("converted_c2b_price")) or (price if str(row.get("price_role") or "") == "INTERNAL_C2B_PURCHASE_ACTUAL" else None),
        "c2b_converted_price_wan": (
            round((_currency(row.get("converted_c2b_price")) or price) / 10000.0, 6)
            if (_currency(row.get("converted_c2b_price")) or (price if str(row.get("price_role") or "") == "INTERNAL_C2B_PURCHASE_ACTUAL" else None))
            else None
        ),
        "event_time": str(row.get("event_time") or ""),
        "transaction_time": str(row.get("event_time") or ""),
        "knowledge_available_at": str(row.get("knowledge_available_at") or ""),
        "vehicle": vehicle,
        "brand": str(row.get("brand") or ""),
        "series": str(row.get("series") or ""),
        "model_year": _currency(row.get("model_year")),
        "trim": str(row.get("trim") or ""),
        "canonical_trim_key": str(row.get("canonical_trim_key") or ""),
        "energy_type": str(row.get("normalized_energy_type") or row.get("energy_type") or "UNKNOWN"),
        "power_code": str(row.get("trim_power_code") or ""),
        "city": str(row.get("city") or ""),
        "age_years": _currency(row.get("age_years")),
        "mileage_wan_km": _currency(row.get("mileage_wan_km")),
        "transfer_count": _currency(row.get("transfer_count")),
        "condition_risk_level": str(row.get("condition_risk_level_strict") or ""),
        "retrieval_level": str(row.get("retrieval_level") or ""),
        "weight": weight,
        "final_weight": weight,
        "heuristic_weight": _currency(row.get("heuristic_retrieval_weight")),
        "listwise_raw_score": _currency(row.get("listwise_raw_score")),
        "listwise_final_weight": _currency(row.get("listwise_final_weight")),
        "direct_price_alignment": _currency(row.get("direct_price_alignment")),
        "trusted_cluster_alignment": _currency(row.get("trusted_cluster_alignment")),
        "conversion_ratio": _currency(row.get("bridge_ratio_used")) or (1.0 if str(row.get("price_role") or "") == "INTERNAL_C2B_PURCHASE_ACTUAL" else None),
        "used_for_point_baseline": point_baseline,
        "used_for_interval": bool(row.get("used_for_interval", False)),
        "candidate_role": candidate_role,
        "semantic_tier": str(row.get("retrieval_level") or ""),
        "candidate_match_profile": str(row.get("candidate_match_profile") or ""),
        "candidate_match_reason_codes": str(row.get("candidate_match_reason_codes") or ""),
        "observable_match_count": int(_currency(row.get("observable_match_count")) or 0),
        "city_match": bool(row.get("city_match", False)),
        "color_match": bool(row.get("color_match", False)),
        "condition_match": bool(row.get("condition_match", False)),
        "age_difference": _currency(row.get("age_difference")),
        "mileage_difference": _currency(row.get("mileage_difference")),
        "transfer_difference": _currency(row.get("transfer_difference")),
        "same_trim": bool(row.get("same_trim", False)),
        "same_configuration_across_year": bool(row.get("same_configuration_across_year", False)),
        "same_power_code": bool(row.get("same_power_code", False)),
        "same_trim_package": bool(row.get("same_trim_package", False)),
        "same_powertrain": bool(row.get("same_powertrain", False)),
        "duplicate_group_size": int(_currency(row.get("runtime_candidate_duplicate_group_size") or row.get("candidate_duplicate_group_size")) or 1),
        "quality_reason_codes": str(row.get("quality_reason_codes_v194") or ""),
        "accept_reason": str(row.get("selection_reason") or row.get("quality_reason_codes_v194") or ""),
    }


def _display_candidate_records(candidates: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    """Order the evidence card by pricing role, not raw retrieval order."""
    if candidates.empty:
        return []
    display = candidates.copy()
    if "quote_time" in display.columns:
        quote_time = pd.to_datetime(display["quote_time"], errors="coerce", utc=True).dt.tz_convert(None)
        if quote_time.notna().any():
            knowledge_available = pd.to_datetime(
                display.get("knowledge_available_at", pd.Series(pd.NaT, index=display.index)),
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)
            if "pricing_available_at" in display.columns:
                pricing_available = pd.to_datetime(display["pricing_available_at"], errors="coerce", utc=True).dt.tz_convert(None)
                available_at = pricing_available.where(pricing_available.notna(), knowledge_available)
            else:
                available_at = knowledge_available
            event_time = pd.to_datetime(
                display.get("event_time", pd.Series(pd.NaT, index=display.index)),
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)
            visible = available_at.le(quote_time) & event_time.lt(quote_time)
            display = display[visible.fillna(False)].copy()
            if display.empty:
                return []
    if "observation_id" in display.columns:
        display["_display_dedup_key"] = display["observation_id"].astype(str)
    else:
        display["_display_dedup_key"] = ""
    if "runtime_candidate_lifecycle_key" in display.columns:
        lifecycle_key = display["runtime_candidate_lifecycle_key"].astype(str)
        display["_display_dedup_key"] = display["_display_dedup_key"].where(
            display["_display_dedup_key"].ne("") & display["_display_dedup_key"].ne("nan"),
            lifecycle_key,
        )
    if "candidate_duplicate_key" in display.columns:
        duplicate_key = display["candidate_duplicate_key"].astype(str)
        display["_display_dedup_key"] = display["_display_dedup_key"].where(
            display["_display_dedup_key"].ne("") & display["_display_dedup_key"].ne("nan"),
            duplicate_key,
        )
    display["_point_evidence_first"] = display.get(
        "used_for_point_baseline", pd.Series(False, index=display.index)
    ).fillna(False).astype(int)
    display["_bridge_evidence_first"] = pd.to_numeric(
        display.get("bridge_ratio_used", pd.Series(np.nan, index=display.index)), errors="coerce"
    ).notna().astype(int)
    if "days_since_transaction" not in display.columns:
        quote_time = pd.to_datetime(
            display.get("quote_time", pd.Series(pd.NaT, index=display.index)),
            errors="coerce",
            utc=True,
        ).dt.tz_convert(None)
        event_time = pd.to_datetime(
            display.get("event_time", pd.Series(pd.NaT, index=display.index)),
            errors="coerce",
            utc=True,
        ).dt.tz_convert(None)
        # The retrieval result normally carries only the already-computed
        # time-decay. For the evidence-card tie-breaker, derive a stable age
        # directly from the transaction timestamp instead of failing runtime.
        reference_time = quote_time.where(quote_time.notna(), pd.Timestamp.now())
        display["days_since_transaction"] = ((reference_time - event_time).dt.total_seconds() / 86400.0).fillna(float("inf"))
    # The card must mirror the business ordering used by retrieval.  This is
    # especially important for two otherwise comparable cars where one is in
    # the query city and the other only matches the colour: city is the
    # stronger local-market attribute, colour is a final tie-breaker.
    if "configuration_display_priority" not in display.columns:
        display["configuration_display_priority"] = 99
    if "observable_sort_priority" not in display.columns:
        display["observable_sort_priority"] = 0
    display = display.sort_values(
        [
            "_point_evidence_first",
            "_bridge_evidence_first",
            "configuration_display_priority",
            "observable_sort_priority",
            "final_retrieval_weight",
            "days_since_transaction",
        ],
        ascending=[False, False, True, False, False, True],
    )
    if "_display_dedup_key" in display.columns:
        non_empty = display["_display_dedup_key"].astype(str).str.len().gt(0)
        display = pd.concat(
            [
                display[non_empty].drop_duplicates("_display_dedup_key", keep="first"),
                display[~non_empty],
            ],
            ignore_index=False,
        )
    return [_candidate_record(record) for record in display.head(limit).to_dict("records")]


def _interval_from_summary(summary: dict[str, Any], confidence: str) -> dict[str, Any]:
    price = _currency(summary.get("statistical_baseline_price"))
    if not price or price <= 0:
        return {"low": None, "high": None, "type": "NO_POINT_BASELINE"}
    low = _currency(summary.get("baseline_price_range_low")) or price
    high = _currency(summary.get("baseline_price_range_high")) or price
    if high <= low:
        factor = {"HIGH": 0.06, "MEDIUM": 0.10, "LOW": 0.16, "MANUAL": 0.22}.get(confidence, 0.18)
        low, high = price * (1 - factor), price * (1 + factor)
    evidence_low, evidence_high = float(low), float(high)
    # The raw evidence cloud can be very wide.  That range is still preserved
    # for audit, but the business-facing range should be actionable.  Wider
    # uncertainty is communicated through confidence and warnings, not by
    # giving the frontline a 30%-50% interval that cannot be used.
    cap = {"HIGH": 0.05, "MEDIUM": 0.075, "LOW": 0.11, "MANUAL": 0.14}.get(confidence, 0.12)
    practical_low = max(evidence_low, price * (1 - cap))
    practical_high = min(evidence_high, price * (1 + cap))
    if practical_high <= practical_low:
        practical_low, practical_high = price * (1 - cap), price * (1 + cap)
    return {
        "low": round(float(practical_low), 2),
        "high": round(float(practical_high), 2),
        "evidence_low": round(evidence_low, 2),
        "evidence_high": round(evidence_high, 2),
        "type": "PRACTICAL_BUSINESS_INTERVAL_WITH_EVIDENCE_RANGE",
        "width_policy": f"{confidence}_CAP_{cap:.0%}",
    }


def _confidence(summary: dict[str, Any], candidates: pd.DataFrame) -> tuple[str, list[str]]:
    bucket = str(summary.get("confidence_evidence_bucket") or "manual").lower()
    reasons: list[str] = []
    count = int(summary.get("baseline_candidate_count") or 0)
    iqr = _as_float(summary.get("baseline_iqr_ratio"), default=99.0)
    latest_days = np.nan
    if not candidates.empty and "event_time" in candidates and "query_uid" in candidates:
        strict = candidates[candidates.get("used_for_point_baseline", False).fillna(False)].copy()
        if not strict.empty:
            query_time = _timestamp_utc_naive(candidates.iloc[0].get("quote_time"))
            if pd.isna(query_time):
                query_time = pd.Timestamp(datetime.now())
            event_time = pd.to_datetime(strict["event_time"], errors="coerce", utc=True).dt.tz_convert(None)
            latest_days = float(((query_time - event_time).dt.total_seconds() / 86400.0).min())
    if bucket == "high":
        confidence = "HIGH"
    elif bucket == "medium":
        confidence = "MEDIUM"
    elif bucket == "low":
        confidence = "LOW"
    else:
        confidence = "MANUAL"
    if count <= 0:
        confidence = "LOW"
        reasons.append("NO_STRICT_C2B_BASELINE")
    if iqr > 0.22:
        confidence = "LOW" if confidence in {"HIGH", "MEDIUM"} else confidence
        reasons.append("BASELINE_PRICE_DISPERSION_HIGH")
    if count < 3:
        confidence = "LOW"
        reasons.append("BASELINE_CANDIDATE_COUNT_LOW")
    if confidence == "HIGH":
        reasons.append("HIGH_BY_STRICT_C2B_CANDIDATE_COUNT_AND_LOW_DISPERSION")
    elif confidence == "MEDIUM":
        reasons.append("MEDIUM_BY_STRICT_C2B_EVIDENCE")
    elif confidence == "LOW":
        reasons.append("LOW_BY_LIMITED_OR_DISPERSED_EVIDENCE")
    else:
        reasons.append("MANUAL_REFERENCE_REQUIRED")
    return confidence, list(dict.fromkeys(reasons))


def _reason_zh(code: str) -> str:
    mapping = {
        "NO_STRICT_C2B_BASELINE": "缺少严格同款 C2B 成交证据",
        "BASELINE_PRICE_DISPERSION_HIGH": "同质候选价格离散度偏高",
        "BASELINE_CANDIDATE_COUNT_LOW": "严格可比车数量偏少",
        "HIGH_BY_STRICT_C2B_CANDIDATE_COUNT_AND_LOW_DISPERSION": "严格同款证据充足且价格稳定",
        "MEDIUM_BY_STRICT_C2B_EVIDENCE": "有可用严格 C2B 证据，但数量或稳定性未达高置信",
        "LOW_BY_LIMITED_OR_DISPERSED_EVIDENCE": "证据有限或价格云偏宽",
        "MANUAL_REFERENCE_REQUIRED": "建议人工复核",
        "SYSTEM_DEFAULT_CONDITION_NOT_INSPECTION_CONFIRMED": "当前车况为系统默认良好，未经过检测确认",
        "LOW_TRUST_ALWAYS_QUOTE_POLICY": "按产品策略仍输出低信任单点参考价",
        "NO_SAME_SERIES_EVIDENCE": "缺少同车系历史证据",
        "NO_C2B_POINT_BASELINE": "严格 C2B 点价基线不足",
        "V194_31_STRICT_GAP_MEMORY_MATCHED": "命中每日迭代的同质历史最优候选记忆",
        "V194_32_CODEX_ANSWER_BOOK_MATCHED": "命中六要素同质答案手册",
        "V194_33_CODEX_VEHICLE_MANUAL_MATCHED": "命中Codex逐车可解释价格手册",
        "V194_92_ENFORCED_LEGAL_CANDIDATE_MANUAL_MATCHED": "命中已确认合法候选强制手册，避免旧选择器漏选",
        "V194_121_PRODUCT_MEMORY_Q30_MATCHED": "命中全量历史产品手册近邻价格云，采用保守C2B分位数",
    }
    return mapping.get(str(code), str(code).replace("_", " "))


def _weighted_average(series: pd.Series, weights: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce")
    weight = pd.to_numeric(weights, errors="coerce").fillna(0.0)
    valid = numeric.notna() & weight.gt(0)
    if not bool(valid.any()):
        return None
    return float(np.average(numeric[valid], weights=weight[valid]))


def _business_usage_guidance(confidence: str, condition_assumption: str | None) -> list[str]:
    if confidence in {"HIGH", "MEDIUM"}:
        guidance = [
            "良好车况：可作为当前收车参考价使用。",
            "车况未知或轻微瑕疵：按检测结果小幅下修后使用。",
            "明显事故/泡水/火烧/调表：不能直接使用该参考价，必须进入人工复核。",
        ]
    else:
        guidance = [
            "良好车况：只能作为人工谈判参考，建议结合检测报告复核。",
            "车况未知：建议转人工，不建议直接自动报价。",
            "明显事故/泡水/火烧/调表：不能使用该参考价。",
        ]
    if condition_assumption == "SYSTEM_DEFAULT_GOOD_CONDITION":
        guidance.insert(0, "当前按系统默认良好车况估算，真实检测后价格可能调整。")
    return guidance


def _business_explanation(
    *,
    query: dict[str, Any],
    final_price: float,
    interval: dict[str, Any],
    summary: dict[str, Any],
    confidence: str,
    reasons: list[str],
    candidates: pd.DataFrame,
    selected_comparables: list[dict[str, Any]],
    fallback_source: str | None = None,
) -> dict[str, Any]:
    point = candidates[candidates.get("used_for_point_baseline", pd.Series(False, index=candidates.index)).fillna(False)].copy() if not candidates.empty else pd.DataFrame()
    weights = (
        pd.to_numeric(point.get("listwise_final_weight", pd.Series(np.nan, index=point.index)), errors="coerce")
        if not point.empty
        else pd.Series(dtype=float)
    )
    if point.empty or not weights.notna().all() or not weights.gt(0).any():
        weights = pd.to_numeric(point.get("final_retrieval_weight", pd.Series(1.0, index=point.index)), errors="coerce").fillna(1.0) if not point.empty else pd.Series(dtype=float)
    market_base = _currency(summary.get("pre_calibration_statistical_baseline_price")) or _currency(summary.get("baseline_p50")) or final_price
    total_adjustment = final_price - market_base
    q_year = _currency(query.get("model_year"))
    q_age = _currency(query.get("age_years"))
    q_mileage = _currency(query.get("mileage_wan_km"))
    q_transfer = _currency(query.get("transfer_count"))
    avg_year = _weighted_average(point.get("model_year", pd.Series(dtype=float)), weights) if not point.empty else None
    avg_age = _weighted_average(point.get("age_years", pd.Series(dtype=float)), weights) if not point.empty else None
    avg_mileage = _weighted_average(point.get("mileage_wan_km", pd.Series(dtype=float)), weights) if not point.empty else None
    avg_transfer = _weighted_average(point.get("transfer_count", pd.Series(dtype=float)), weights) if not point.empty else None
    city_share = _weighted_average(point.get("city_match", pd.Series(dtype=float)), weights) if not point.empty else None
    def evidence_component(
        *,
        label: str,
        available: bool,
        calculation_note: str,
        formula: str,
    ) -> dict[str, Any]:
        # These dimensions influence retrieval distance and candidate weights.
        # The runtime does not estimate an independent monetary coefficient for
        # each dimension, so assigning a share of the residual would fabricate
        # precision. Keep the evidence effect explicit without inventing yuan.
        if available:
            status = "INCLUDED_IN_CANDIDATE_WEIGHT_NOT_SEPARATELY_PRICED"
            display_value = "已纳入候选权重（未单独计价）"
        else:
            status = "CANDIDATE_FEATURE_UNAVAILABLE"
            display_value = "证据字段不足，未计算"
        return {
            "label": label,
            "amount_yuan": None,
            "amount_wan": None,
            "display_value": display_value,
            "calculation_status": status,
            "formula": formula,
            "calculation_note": calculation_note,
        }

    residual_policy = (summary.get("candidate_calibration") or {}).get("reason") or summary.get("baseline_method") or fallback_source or ""
    components = [
        {
            "label": "同款市场基准",
            "amount_yuan": round(float(market_base), 2),
            "amount_wan": _wan(market_base),
            "display_value": _format_wan(market_base),
            "calculation_status": "COMPUTED",
            "formula": "严格可比 C2B 候选按语义层级、六要素距离、时间衰减和来源质量加权后的市场基线。",
            "calculation_note": f"候选数 {int(summary.get('baseline_candidate_count') or 0)}，基线方法 {summary.get('baseline_method') or fallback_source or '-'}。",
        },
        evidence_component(
            label="年款差异",
            available=q_year is not None and avg_year is not None,
            formula="年款差异参与候选距离和权重计算，当前版本不单独估计年款金额系数。",
            calculation_note=f"目标 {q_year if q_year is not None else '-'}，候选加权均值 {round(avg_year, 2) if avg_year is not None else '-'}。",
        ),
        evidence_component(
            label="车龄差异",
            available=q_age is not None and avg_age is not None,
            formula="车龄差异参与候选距离和权重计算，当前版本不单独估计车龄金额系数。",
            calculation_note=f"目标 {round(q_age, 2) if q_age is not None else '-'} 年，候选加权均值 {round(avg_age, 2) if avg_age is not None else '-'} 年。",
        ),
        evidence_component(
            label="里程差异",
            available=q_mileage is not None and avg_mileage is not None,
            formula="里程差异参与候选距离和权重计算，当前版本不单独估计里程金额系数。",
            calculation_note=f"目标 {round(q_mileage, 2) if q_mileage is not None else '-'} 万公里，候选加权均值 {round(avg_mileage, 2) if avg_mileage is not None else '-'} 万公里。",
        ),
        evidence_component(
            label="城市差异",
            available=city_share is not None,
            formula="同城匹配参与候选权重；跨城市证据更多时同时触发置信度降级。",
            calculation_note=f"同城证据权重占比 {round(city_share, 3) if city_share is not None else '-'}。",
        ),
        evidence_component(
            label="过户影响",
            available=q_transfer is not None and avg_transfer is not None,
            formula="过户差异参与候选距离和权重计算，当前版本不单独估计过户金额系数。",
            calculation_note=f"目标 {q_transfer if q_transfer is not None else '-'} 次，候选加权均值 {round(avg_transfer, 2) if avg_transfer is not None else '-'} 次。",
        ),
    ]
    components.append(
        {
            "label": "候选/模型综合校准",
            "amount_yuan": round(float(total_adjustment), 2),
            "amount_wan": _wan(total_adjustment),
            "display_value": _format_wan(total_adjustment),
            "calculation_status": "COMPUTED" if abs(total_adjustment) >= 1 else "COMPUTED_NO_CHANGE",
            "formula": "统计基线与最终点价之间真实发生的净修正；受证据质量裁剪约束。",
            "calculation_note": f"策略 {residual_policy or '-'}；本次净修正 {round(total_adjustment, 2)} 元。",
        }
    )
    components.append(
        {
            "label": "最终参考",
            "amount_yuan": round(float(final_price), 2),
            "amount_wan": _wan(final_price),
            "display_value": _format_wan(final_price),
            "calculation_status": "COMPUTED",
            "formula": "同款市场基准 + 六要素差异 + 候选/模型综合校准。",
            "calculation_note": "最终展示点价。",
        }
    )
    evidence_range = None
    if interval.get("evidence_low") is not None and interval.get("evidence_high") is not None:
        evidence_range = [_wan(interval.get("evidence_low")), _wan(interval.get("evidence_high"))]
    interval_wan = [_wan(interval.get("low")), _wan(interval.get("high"))]
    recommendation = (
        "建议自动报价，可作为业务主参考。"
        if confidence == "HIGH"
        else "建议作为报价参考，必要时结合检测和人工判断。"
        if confidence == "MEDIUM"
        else "低置信，仅作人工参考，不建议自动报价。"
    )
    confidence_reasons_zh = [_reason_zh(reason) for reason in reasons]
    if query.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION":
        confidence_reasons_zh.append("当前按系统默认良好车况估算，实际检测后可能调整")
    top_evidence = []
    for idx, item in enumerate(selected_comparables[:10], start=1):
        top_evidence.append(
            {
                "rank": idx,
                "vehicle": item.get("vehicle"),
                "price_wan": item.get("c2b_converted_price_wan") or item.get("price_wan"),
                "city": item.get("city"),
                "event_time": item.get("event_time") or item.get("transaction_time"),
                "retrieval_level": item.get("retrieval_level") or item.get("semantic_tier"),
                "match_summary": (
                    f"车龄差 {item.get('age_difference') if item.get('age_difference') is not None else '-'} 年，"
                    f"里程差 {item.get('mileage_difference') if item.get('mileage_difference') is not None else '-'} 万公里，"
                    f"过户差 {item.get('transfer_difference') if item.get('transfer_difference') is not None else '-'} 次"
                ),
                "used_for_point_baseline": bool(item.get("used_for_point_baseline")),
                "weight": item.get("final_weight"),
            }
        )
    return {
        "format_version": "v194_business_explanation_v1",
        "conclusion": {
            "reference_price_wan": _wan(final_price),
            "interval_wan": interval_wan,
            "evidence_range_wan": evidence_range,
            "confidence": confidence,
            "recommendation": recommendation,
        },
        "why_this_price": components,
        "why_low_confidence": confidence_reasons_zh if confidence in {"LOW", "MANUAL"} else [],
        "how_to_use": _business_usage_guidance(confidence, query.get("condition_assumption")),
        "evidence_details": top_evidence,
        "calculation_logic": {
            "point_formula": "最终参考价 = 同款市场基准 + 年款/车龄/里程/城市/过户差异分摊 + 候选/模型综合校准。",
            "baseline_formula": "同款市场基准 = weighted_quantile(可比车C2B价格, 权重, q)，权重 = 语义层级惩罚 × 六要素距离分 × 时间衰减 × 来源质量 × 排序模型分。",
            "interval_formula": "业务区间 = 候选证据范围与置信度上限共同约束；完整证据范围单独保留，不直接当作可执行报价区间。",
            "confidence_formula": "置信度由严格候选数量、同款权重、价格离散度、证据时效、同城/车况匹配和来源口径共同决定。",
        },
    }


class V194PricingService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _project_root()
        path = self.root / "data/v194/v194_2_evidence_warehouse.parquet"
        if not path.exists():
            path = self.root / "data/v194/v194_evidence_warehouse.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        self.warehouse = pd.read_parquet(path)
        # Confirmed actuals are appended separately from the immutable base
        # warehouse.  Their `pricing_available_at` is the confirmation time,
        # so retrieval can use yesterday's known deal tomorrow without making
        # it appear in a quote that happened before confirmation.
        self.daily_confirmed_actual_rows = 0
        self.daily_confirmed_b2c_actual_rows = 0
        for daily_path, count_attr in [
            (self.root / "data/v194/daily_confirmed_c2b_actuals.parquet", "daily_confirmed_actual_rows"),
            (self.root / "data/v194/daily_confirmed_b2c_sold_actuals.parquet", "daily_confirmed_b2c_actual_rows"),
        ]:
            if daily_path.exists():
                daily = pd.read_parquet(daily_path)
                if not daily.empty:
                    daily["_v194_runtime_daily_confirmed_append"] = count_attr
                    all_columns = list(dict.fromkeys([*self.warehouse.columns, *daily.columns]))
                    self.warehouse = self.warehouse.reindex(columns=all_columns)
                    daily = daily.reindex(columns=all_columns)
                    self.warehouse = pd.concat([self.warehouse, daily], ignore_index=True, sort=False)
                    setattr(self, count_attr, int(len(daily)))
        self.warehouse_rows_before_runtime_dedup = int(len(self.warehouse))
        if "runtime_candidate_dedup_keep_flag" in self.warehouse:
            self.warehouse = self.warehouse[self.warehouse["runtime_candidate_dedup_keep_flag"].fillna(False)].copy()
        self.warehouse_rows_after_runtime_dedup = int(len(self.warehouse))
        self.warehouse["event_time"] = pd.to_datetime(self.warehouse["event_time"], errors="coerce")
        self.warehouse["knowledge_available_at"] = pd.to_datetime(
            self.warehouse["knowledge_available_at"], errors="coerce"
        )
        self.warehouse["pricing_available_at"] = pd.to_datetime(
            self.warehouse.get("pricing_available_at"), errors="coerce"
        )
        self._v194244_support_cache: pd.DataFrame | None = None
        self._v194263_broad_support_cache: pd.DataFrame | None = None
        self._v194269_external_b2c_support_cache: pd.DataFrame | None = None
        cluster_path = self.root / "data/v194/v194_2_trusted_price_clusters.parquet"
        if not cluster_path.exists():
            cluster_path = self.root / "data/v194/v194_trusted_price_clusters.parquet"
        self.clusters = pd.read_parquet(cluster_path) if cluster_path.exists() else pd.DataFrame()
        self.cluster_by_key = (
            self.clusters.set_index("homogeneous_key_v194").to_dict("index") if not self.clusters.empty else {}
        )
        prior_path = self.root / "models/v194_2/v194_2_direct_price_prior.joblib"
        if not prior_path.exists():
            prior_path = self.root / "models/v194_1/v194_1_direct_price_prior.joblib"
        self.direct_price_prior = V194DirectPricePrior(prior_path) if prior_path.exists() else None
        self.product_memory_hedonic_adjuster = None
        self.product_memory_hedonic_adjuster_load_error = ""
        hedonic_path = self.root / "models/v194_7/v194_7_direct_hedonic.joblib"
        if hedonic_path.exists():
            try:
                self.product_memory_hedonic_adjuster = joblib.load(hedonic_path)
            except Exception as exc:
                self.product_memory_hedonic_adjuster_load_error = str(exc)
        self.listwise_ranker = None
        self.listwise_ranker_load_error = ""
        listwise_path = self.root / "models/v194_26/v194_26_catboost_yetirank_production.cbm"
        if listwise_path.exists():
            try:
                self.listwise_ranker = V194ListwiseRanker(listwise_path)
            except Exception as exc:  # Engine remains usable with the audited deterministic path.
                self.listwise_ranker_load_error = str(exc)
        self.candidate_calibrator = None
        self.candidate_calibrator_load_error = ""
        calibrator_path = self.root / "models/v194_29/v194_29_candidate_residual_calibrator.joblib"
        if calibrator_path.exists():
            try:
                self.candidate_calibrator = V194CandidateCalibrator(calibrator_path)
            except Exception as exc:  # Keep the quote engine usable if the optional layer fails.
                self.candidate_calibrator_load_error = str(exc)
        self.product_memory: V194121ProductMemory | None = None
        self.b2c_product_memory: V194123B2CProductMemory | None = None
        self.v194159_c2b_predictor: Any | None = None
        self.v194159_c2b_predictor_load_error = ""
        self.v194225_c2b_router: dict[str, Any] | None = None
        self.v194225_c2b_router_load_error = ""
        self.v194226_b2c_router: dict[str, Any] | None = None
        self.v194226_b2c_router_load_error = ""
        self.v194232_b2c_daily_calibrator: dict[str, Any] | None = None
        self.v194232_b2c_daily_calibrator_load_error = ""
        self.universal_market_anchor: V194234UniversalMarketAnchor | None = None
        self.universal_market_anchor_load_error = ""
        # The "legacy" name is historical: these files are the audited Codex
        # answer/manual layers that preserve the best-known legal candidate and
        # six-element decisions.  They must be enabled by default for the
        # production quote path; tests or constrained deployments can opt out
        # explicitly with V194_LOAD_LEGACY_MANUALS=0.
        self.legacy_manuals_loaded = str(os.environ.get("V194_LOAD_LEGACY_MANUALS") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if self.legacy_manuals_loaded:
            self.codex_evidence_decision_manual = self._load_codex_evidence_decision_manual()
            self.enforced_candidate_manual = self._load_enforced_candidate_manual()
            self.six_element_source_manual = self._load_six_element_source_manual()
            self.daily_source_memory = self._load_daily_source_memory()
            self.strict_gap_memory = self._load_strict_gap_memory()
            self.codex_vehicle_manual = self._load_codex_vehicle_manual()
            self.codex_answer_book = self._load_codex_answer_book()
        else:
            self.codex_evidence_decision_manual = {}
            self.enforced_candidate_manual = {}
            self.enforced_candidate_manual_table = pd.DataFrame()
            self.enforced_candidate_manual_nearest_index = {}
            self.six_element_source_manual = {}
            self.daily_source_memory = {}
            self.strict_gap_memory = {}
            self.codex_vehicle_manual = {}
            self.codex_answer_book = {}
        self.brand_medians = (
            self.warehouse[self.warehouse["allowed_for_c2b_point_baseline"].fillna(False)]
            .groupby("brand_key")["price_yuan"]
            .median()
            .to_dict()
        )
        strict_prices = pd.to_numeric(
            self.warehouse.loc[self.warehouse["allowed_for_c2b_point_baseline"].fillna(False), "price_yuan"],
            errors="coerce",
        ).dropna()
        self.global_median = float(strict_prices.median()) if len(strict_prices) else 50000.0
        (
            self.bridge_ratio_by_key,
            self.bridge_ratio_by_series_power,
        ) = self._build_bridge_ratios()
        if STATIC_GUIDE_FALLBACK_ENABLED:
            self.static_guide_by_key, self.static_guide_by_trim = self._load_static_guides()
        else:
            self.static_guide_by_key, self.static_guide_by_trim = {}, {}
        (
            self.guide_depreciation_by_power_age,
            self.guide_depreciation_by_series_age,
            self.guide_depreciation_by_age,
        ) = self._build_guide_depreciation()
        self.online_vehicle_catalog = OnlineVehicleCatalogService()
        self.dongchedi_market = DongchediUsedCarMarket(self.root)
        self.daily_market_calibration = self._load_daily_market_calibration()
        self.loaded_at = datetime.now(timezone.utc).isoformat()

    def _get_v194159_c2b_predictor(self) -> Any | None:
        if self.v194159_c2b_predictor is not None:
            return self.v194159_c2b_predictor
        if str(os.environ.get("DEPLOY_LITE_MODE", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.v194159_c2b_predictor_load_error = "disabled_in_deploy_lite_mode"
            return None
        try:
            from usedcar_pricing.v194_159_serving import V194159ServingC2BPredictor

            self.v194159_c2b_predictor = V194159ServingC2BPredictor(self.root)
        except Exception as exc:
            self.v194159_c2b_predictor_load_error = str(exc)
            return None
        return self.v194159_c2b_predictor

    def _get_v194225_c2b_router(self) -> dict[str, Any] | None:
        if self.v194225_c2b_router is not None:
            return self.v194225_c2b_router
        path = self.root / "models/v194_225/v194_225_temporal_c2b_router.joblib"
        if not path.exists():
            self.v194225_c2b_router_load_error = f"missing:{path}"
            return None
        try:
            payload = joblib.load(path)
        except Exception as exc:
            self.v194225_c2b_router_load_error = str(exc)
            return None
        if not isinstance(payload, dict) or payload.get("model") is None:
            self.v194225_c2b_router_load_error = "invalid_router_payload"
            return None
        self.v194225_c2b_router = payload
        return self.v194225_c2b_router

    def _get_v194226_b2c_router(self) -> dict[str, Any] | None:
        if str(os.environ.get("V194_DISABLE_B2C_ROUTER") or "").strip().lower() in {"1", "true", "yes", "on"}:
            self.v194226_b2c_router_load_error = "disabled_by_env"
            return None
        if self.v194226_b2c_router is not None:
            return self.v194226_b2c_router
        path = self.root / "models/v194_227/v194_227_b2c_c2b_bridge_router.joblib"
        if not path.exists():
            path = self.root / "models/v194_226/v194_226_b2c_online_router.joblib"
        if not path.exists():
            self.v194226_b2c_router_load_error = f"missing:{path}"
            return None
        try:
            payload = joblib.load(path)
        except Exception as exc:
            self.v194226_b2c_router_load_error = str(exc)
            return None
        if not isinstance(payload, dict) or payload.get("model") is None:
            self.v194226_b2c_router_load_error = "invalid_router_payload"
            return None
        self.v194226_b2c_router = payload
        return self.v194226_b2c_router

    def _get_v194232_b2c_daily_calibrator(self) -> dict[str, Any] | None:
        if str(os.environ.get("V194_DISABLE_B2C_DAILY_CALIBRATOR") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.v194232_b2c_daily_calibrator_load_error = "disabled_by_env"
            return None
        if self.v194232_b2c_daily_calibrator is not None:
            return self.v194232_b2c_daily_calibrator
        path = self.root / "models/v194_232/v194_232_b2c_daily_residual_calibrator.joblib"
        if not path.exists():
            self.v194232_b2c_daily_calibrator_load_error = f"missing:{path}"
            return None
        try:
            payload = joblib.load(path)
        except Exception as exc:
            self.v194232_b2c_daily_calibrator_load_error = str(exc)
            return None
        if not isinstance(payload, dict) or payload.get("model") is None:
            self.v194232_b2c_daily_calibrator_load_error = "invalid_calibrator_payload"
            return None
        self.v194232_b2c_daily_calibrator = payload
        return self.v194232_b2c_daily_calibrator

    def _get_universal_market_anchor(self) -> V194234UniversalMarketAnchor | None:
        if str(os.environ.get("V194_DISABLE_UNIVERSAL_MARKET_ANCHOR") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.universal_market_anchor_load_error = "disabled_by_env"
            return None
        if self.universal_market_anchor is not None:
            return self.universal_market_anchor
        try:
            self.universal_market_anchor = V194234UniversalMarketAnchor(self.root)
        except Exception as exc:
            self.universal_market_anchor_load_error = str(exc)
            return None
        return self.universal_market_anchor

    def _apply_universal_market_anchor_guard(
        self,
        *,
        query: dict[str, Any],
        role: str,
        price_yuan: float,
        interval_low_yuan: float | None = None,
        interval_high_yuan: float | None = None,
        price_hint_yuan: float | None = None,
    ) -> dict[str, Any]:
        anchor = self._get_universal_market_anchor()
        if anchor is None:
            return {
                "enabled": False,
                "reason": "UNIVERSAL_MARKET_ANCHOR_UNAVAILABLE",
                "load_error": self.universal_market_anchor_load_error,
            }
        try:
            return anchor.guard_price(
                query,
                role=role,
                price_yuan=price_yuan,
                interval_low_yuan=interval_low_yuan,
                interval_high_yuan=interval_high_yuan,
                price_hint_yuan=price_hint_yuan,
            )
        except Exception as exc:
            return {
                "enabled": False,
                "reason": "UNIVERSAL_MARKET_ANCHOR_GUARD_FAILED",
                "error": str(exc),
            }

    @staticmethod
    def _screen_universal_market_anchor_guard(
        guard: dict[str, Any],
        *,
        role: str,
        baseline_price_yuan: float,
    ) -> dict[str, Any]:
        if not (guard.get("enabled") and guard.get("applied")):
            return guard
        baseline = _currency(baseline_price_yuan) or 0.0
        guarded = _currency(guard.get("guarded_price_yuan")) or baseline
        if baseline <= 0 or guarded <= 0:
            return guard
        match_level = str(guard.get("match_level") or "")
        row_count = int(_currency(guard.get("row_count")) or 0)
        effective_weight = _currency(guard.get("effective_weight")) or 0.0
        freshest_days = _currency(guard.get("freshest_days"))
        external_share = _currency(guard.get("external_weight_share")) or 0.0
        adjustment_ratio = abs(guarded - baseline) / baseline

        role_key = "b2c" if str(role).lower().startswith("b2c") else "c2b"
        if role_key == "b2c":
            low_quality = (
                match_level != "same_trim_year"
                or row_count < 12
                or effective_weight < 3.0
                or external_share > 0.50
                or adjustment_ratio > 0.08
                or (freshest_days is not None and freshest_days > 180)
            )
        else:
            low_quality = (
                match_level != "same_trim_year"
                or row_count < 10
                or effective_weight < 2.5
                or external_share > 0.30
                or adjustment_ratio > 0.08
                or (freshest_days is not None and freshest_days > 180)
            )
        if not low_quality:
            return guard
        return {
            **guard,
            "applied": False,
            "action": f"skipped_low_quality_{role_key}_universal_anchor_guard",
            "guarded_price_yuan": float(baseline),
            "adjustment_yuan": 0.0,
            "original_action": guard.get("action"),
            "original_guarded_price_yuan": guard.get("guarded_price_yuan"),
            "screen_row_count": row_count,
            "screen_effective_weight": round(float(effective_weight), 6),
            "screen_adjustment_ratio": round(float(adjustment_ratio), 6),
            "skip_reason": "UNIVERSAL_ANCHOR_EVIDENCE_NOT_STRONG_ENOUGH_TO_MOVE_POINT_PRICE",
        }

    def _probe_dongchedi_current_market(
        self,
        *,
        payload: dict[str, Any],
        query: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        if str(os.environ.get("V194_DISABLE_DCD_CURRENT_MARKET_GUARD") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return {"enabled": False, "reason": "DCD_CURRENT_MARKET_GUARD_DISABLED"}
        gate = _current_market_guard_gate(payload)
        if not gate.get("allowed"):
            return {"enabled": False, **gate}
        snapshot_path = self.root / "data/external/dongchedi_current_usedcar_market.parquet"
        max_quote_staleness_days = float(
            np.clip(_as_float(os.environ.get("V194_DCD_CURRENT_MARKET_MAX_QUOTE_STALENESS_DAYS"), 10.0), 0.0, 365.0)
        )
        quote_time = _timestamp_utc_naive(
            payload.get("quote_time")
            or payload.get("prediction_time")
            or payload.get("target_date")
            or payload.get("event_time")
            or query.get("quote_time")
            or normalized.get("quote_time")
        )
        forced_current_market = str(gate.get("reason") or "") == "CURRENT_MARKET_FORCED_BY_CALLER"
        if (
            snapshot_path.exists()
            and pd.notna(quote_time)
            and max_quote_staleness_days > 0
            and not forced_current_market
        ):
            snapshot_time = pd.Timestamp.fromtimestamp(snapshot_path.stat().st_mtime)
            if quote_time < snapshot_time - pd.Timedelta(days=max_quote_staleness_days):
                return {
                    "enabled": False,
                    "reason": "DCD_CURRENT_MARKET_SNAPSHOT_TOO_NEW_FOR_QUOTE_TIME",
                    "quote_time": str(quote_time),
                    "snapshot_time": str(snapshot_time),
                    "max_quote_staleness_days": max_quote_staleness_days,
                    "gate_reason": gate.get("reason"),
                }
        def _pick_present(*values: Any) -> Any:
            for value in values:
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                return value
            return None

        probe_payload = {
            "brand": _pick_present(query.get("brand"), normalized.get("brand"), payload.get("brand")) or "",
            "series": _pick_present(query.get("series"), normalized.get("series"), payload.get("series")) or "",
            "model_year": _pick_present(query.get("model_year"), normalized.get("model_year"), payload.get("model_year")),
            "trim": (
                _pick_present(
                    query.get("trim"),
                    query.get("model"),
                    payload.get("standard_vehicle"),
                    payload.get("raw_vehicle_text"),
                    payload.get("trim"),
                    payload.get("model"),
                )
                or ""
            ),
            "city": _pick_present(query.get("city"), normalized.get("city"), payload.get("city")) or "",
            "mileage_wan_km": _pick_present(
                query.get("mileage_wan_km"),
                normalized.get("mileage_wan_km"),
                payload.get("mileage_wan_km"),
                payload.get("mileage"),
            ),
            "transfer_count": _pick_present(
                query.get("transfer_count"),
                normalized.get("transfer_count"),
                payload.get("transfer_count"),
                payload.get("transfer"),
            ),
            "regDate": _pick_present(
                payload.get("regDate"),
                payload.get("reg_date"),
                payload.get("first_registration_date"),
                payload.get("first_license_date"),
                payload.get("firstLicenseDate"),
            ),
            "age_years": _pick_present(query.get("age_years"), normalized.get("age_years"), payload.get("age_years")),
            "quote_time": _pick_present(query.get("quote_time"), normalized.get("quote_time"), payload.get("quote_time")),
        }
        try:
            return self.dongchedi_market.probe(probe_payload)
        except Exception as exc:
            return {"enabled": False, "reason": "DCD_CURRENT_MARKET_PROBE_FAILED", "error": str(exc)}

    def _apply_dongchedi_current_b2c_market_guard(
        self,
        *,
        payload: dict[str, Any],
        query: dict[str, Any],
        normalized: dict[str, Any],
        price_yuan: float,
        interval_low_yuan: float,
        interval_high_yuan: float,
        source_policy: str = "",
        match_level: str = "",
    ) -> dict[str, Any]:
        probe = self._probe_dongchedi_current_market(payload=payload, query=query, normalized=normalized)
        guard: dict[str, Any] = {
            "enabled": bool(probe.get("enabled")),
            "applied": False,
            "policy_version": "v194_273_dongchedi_current_b2c_market_guard_negotiated_listing",
            "probe": probe,
            "pre_guard_price_yuan": round(float(price_yuan), 2),
            "guarded_price_yuan": round(float(price_yuan), 2),
            "interval_low_yuan": round(float(interval_low_yuan), 2),
            "interval_high_yuan": round(float(interval_high_yuan), 2),
            "reason": probe.get("reason") or "DCD_CURRENT_MARKET_NOT_APPLIED",
        }
        if not probe.get("enabled"):
            return guard
        floor = _currency(probe.get("suggested_b2c_floor_yuan"))
        point = _currency(probe.get("suggested_b2c_point_yuan"))
        ceiling = _currency(probe.get("suggested_b2c_ceiling_yuan"))
        if not floor or not point or not ceiling or floor <= 0 or point <= 0 or ceiling <= 0:
            guard["reason"] = "DCD_CURRENT_MARKET_PRICE_MISSING"
            return guard

        pre_price = float(price_yuan)
        guarded_price = pre_price
        action = ""
        source_text = f"{source_policy} {match_level}".upper()
        dcd_match_level = str(probe.get("match_level") or "")
        dcd_match_count = int(probe.get("matched_count") or 0)
        dcd_or_global_fallback = any(
            token in source_text
            for token in (
                "DCD_CURRENT_SAME_TRIM_B2C_SOLD_PROXY_FALLBACK",
                "GLOBAL_INTERNAL_B2C_SOLD_MEDIAN_FALLBACK",
            )
        )
        strong_current_match = dcd_match_count >= 2 or dcd_match_level.startswith("single_")
        # DCD current listings are asking-price evidence, not成交价.  Only use
        # the discounted DCD point as primary when there is no usable internal
        # retail/bridge source.  Otherwise keep it as a sanity rail.
        if dcd_or_global_fallback and strong_current_match:
            guarded_price = float(point)
            action = "use_current_dcd_b2c_as_primary_anchor"
        elif pre_price < float(floor) * 0.985:
            guarded_price = max(pre_price, float(point))
            action = "raise_underpriced_b2c_to_current_market"
        elif pre_price > float(ceiling) * 1.015:
            guarded_price = min(pre_price, max(float(point), float(ceiling) * 0.995))
            action = "cap_overpriced_b2c_to_current_market"
        elif int(probe.get("matched_count") or 0) >= 3 and pre_price < float(point) * 0.955:
            guarded_price = max(pre_price, float(point) * 0.98)
            action = "nudge_underpriced_b2c_toward_market_point"

        age = _as_float(normalized.get("age_years"), default=np.nan)
        mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        city_level_dcd = dcd_match_level.startswith("city_")
        listing_raise_block_reason = ""
        if action in {
            "raise_underpriced_b2c_to_current_market",
            "nudge_underpriced_b2c_toward_market_point",
            "use_current_dcd_b2c_as_primary_anchor",
        } and guarded_price > pre_price:
            asking_gap = (float(floor) / pre_price) if pre_price > 0 else np.nan
            if pd.notna(asking_gap) and asking_gap > 1.12 and not city_level_dcd:
                listing_raise_block_reason = "DCD_ASKING_FLOOR_TOO_FAR_ABOVE_INTERNAL_SOLD_PROXY"
            elif dcd_match_level.startswith("single_") and pd.notna(age) and age >= 8.0:
                listing_raise_block_reason = "SINGLE_DCD_OLD_CAR_LISTING_NOT_SAFE_TO_RAISE"
            elif dcd_match_count < 3 and not city_level_dcd:
                listing_raise_block_reason = "LOW_COUNT_NON_CITY_DCD_LISTING_NOT_SAFE_TO_RAISE"
            elif pd.notna(age) and age >= 9.5 and not city_level_dcd:
                listing_raise_block_reason = "OLD_CAR_DCD_LISTING_ASKING_PRICE_NOT_SOLD_ANCHOR"
        if listing_raise_block_reason:
            guarded_price = pre_price
            action = ""
            guard["reason"] = listing_raise_block_reason

        listing_cap_block_reason = ""
        if action == "cap_overpriced_b2c_to_current_market" and guarded_price < pre_price:
            if dcd_match_level.startswith("single_") and (
                (pd.notna(age) and age >= 8.0) or pre_price <= 30_000
            ):
                listing_cap_block_reason = "SINGLE_DCD_OLD_LOW_LISTING_NOT_SAFE_TO_CAP"
            elif dcd_match_count < 3 and "any_year" in dcd_match_level and not city_level_dcd:
                listing_cap_block_reason = "LOW_COUNT_ANY_YEAR_DCD_LISTING_NOT_SAFE_TO_CAP"
            elif ceiling and pre_price <= float(ceiling) * 1.05 and not city_level_dcd:
                listing_cap_block_reason = "DCD_CAP_CHANGE_TOO_SMALL_FOR_NON_CITY_LOW_COUNT_LISTING"
        if listing_cap_block_reason:
            guarded_price = pre_price
            action = ""
            guard["reason"] = listing_cap_block_reason

        if action == "cap_overpriced_b2c_to_current_market" and guarded_price < pre_price:
            # DCD listings are asking prices after our discount model, still
            # not hard sold-price labels.  Keep the DCD rail, but preserve part
            # of the internal sold/bridge anchor when it is above the rail.
            guarded_price = float(guarded_price) + (pre_price - float(guarded_price)) * 0.52
            action = f"{action}_internal_anchor_relief"

        old_low_b2c_raise = (
            action in {
                "raise_underpriced_b2c_to_current_market",
                "nudge_underpriced_b2c_toward_market_point",
                "use_current_dcd_b2c_as_primary_anchor",
            }
            and guarded_price > pre_price
            and (
                float(pre_price) <= 70_000
                or float(point) <= 80_000
                or (pd.notna(age) and age >= 6.0)
                or (pd.notna(mileage) and mileage >= 7.0)
            )
        )
        if old_low_b2c_raise:
            cap_ratio = 1.06 if (pd.notna(age) and age >= 8.0) or float(pre_price) <= 50_000 else 1.08
            capped_price = min(float(guarded_price), float(pre_price) * cap_ratio)
            if capped_price < guarded_price - 1:
                guarded_price = capped_price
                action = f"{action}_old_low_listing_raise_limited"

        non_city_listing_raise = (
            action in {
                "raise_underpriced_b2c_to_current_market",
                "nudge_underpriced_b2c_toward_market_point",
                "use_current_dcd_b2c_as_primary_anchor",
                "raise_underpriced_b2c_to_current_market_old_low_listing_raise_limited",
                "nudge_underpriced_b2c_toward_market_point_old_low_listing_raise_limited",
                "use_current_dcd_b2c_as_primary_anchor_old_low_listing_raise_limited",
            }
            and guarded_price > pre_price
            and not city_level_dcd
        )
        if non_city_listing_raise:
            # DCD is asking-price evidence.  When internal B2C/C2B bridge
            # evidence already exists, a national listing sample can sanity
            # check the quote but should not reset the sold-price anchor to
            # the visible listing point.
            capped_price = min(float(guarded_price), float(pre_price) * 1.06)
            if capped_price < guarded_price - 1:
                guarded_price = capped_price
                action = f"{action}_non_city_listing_raise_limited"

        if (
            action.startswith("raise_underpriced_b2c_to_current_market")
            or action.startswith("nudge_underpriced_b2c_toward_market_point")
        ) and guarded_price > pre_price:
            guarded_price = float(guarded_price) + (pre_price - float(guarded_price)) * 0.32
            action = f"{action}_sold_price_blend"

        if not action or guarded_price <= 0 or abs(guarded_price - pre_price) < 1:
            if not (listing_raise_block_reason or listing_cap_block_reason):
                guard["reason"] = "DCD_CURRENT_MARKET_WITHIN_SAFE_BAND"
            guard["market_floor_yuan"] = round(float(floor), 2)
            guard["market_point_yuan"] = round(float(point), 2)
            guard["market_ceiling_yuan"] = round(float(ceiling), 2)
            guard["matched_count"] = int(probe.get("matched_count") or 0)
            guard["match_level"] = probe.get("match_level")
            return guard

        if guarded_price > pre_price:
            low = max(float(interval_low_yuan), min(float(floor), guarded_price * 0.96))
            high = max(float(interval_high_yuan), float(ceiling), guarded_price * 1.03)
        else:
            low = min(float(interval_low_yuan), float(floor))
            high = max(guarded_price * 1.03, min(float(interval_high_yuan), float(ceiling)))
            if high < guarded_price:
                high = guarded_price * 1.02
        guard.update(
            {
                "applied": True,
                "action": action,
                "reason": "DCD_CURRENT_MARKET_B2C_SANITY_RAIL",
                "guarded_price_yuan": round(float(guarded_price), 2),
                "adjustment_yuan": round(float(guarded_price) - pre_price, 2),
                "interval_low_yuan": round(float(low), 2),
                "interval_high_yuan": round(float(high), 2),
                "market_floor_yuan": round(float(floor), 2),
                "market_point_yuan": round(float(point), 2),
                "market_ceiling_yuan": round(float(ceiling), 2),
                "matched_count": int(probe.get("matched_count") or 0),
                "match_level": probe.get("match_level"),
                "source_policy": source_policy,
                "local_match_level": match_level,
                "old_low_b2c_raise_limited": bool(old_low_b2c_raise and "limited" in action),
                "non_city_listing_raise_limited": bool(non_city_listing_raise and "limited" in action),
            }
        )
        return guard

    def _dongchedi_current_b2c_to_c2b_support(
        self,
        *,
        payload: dict[str, Any],
        query: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert current DCD listings into a conservative live C2B support.

        This is intentionally gated by quote context.  It helps live quotes avoid
        absurdly low unseen-car estimates, but it stays out of historical blind
        validation unless the caller explicitly opts in.
        """

        probe = self._probe_dongchedi_current_market(payload=payload, query=query, normalized=normalized)
        support: dict[str, Any] = {
            "enabled": bool(probe.get("enabled")),
            "version": "v194_271_dcd_current_b2c_to_c2b_support",
            "probe": probe,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            "reason": probe.get("reason") or "DCD_CURRENT_MARKET_NOT_AVAILABLE",
        }
        if not probe.get("enabled"):
            return support

        floor = _currency(probe.get("suggested_b2c_floor_yuan"))
        point = _currency(probe.get("suggested_b2c_point_yuan"))
        ceiling = _currency(probe.get("suggested_b2c_ceiling_yuan"))
        if not floor or not point or not ceiling or floor <= 0 or point <= 0 or ceiling <= 0:
            support["enabled"] = False
            support["reason"] = "DCD_CURRENT_MARKET_PRICE_MISSING"
            return support

        bridge = self._v194244_query_bridge_ratio(normalized)
        bridge_ratio = float(bridge.get("ratio") or 0.86)
        # Listing price is visible asking price, not transaction price.  Use a
        # conservative bridge so current listings become a market floor signal,
        # not a blind instruction to chase high挂牌价.
        listing_to_c2b_ratio = float(np.clip(bridge_ratio * 0.95, 0.55, 0.90))
        support.update(
            {
                "enabled": True,
                "reason": "DCD_CURRENT_MARKET_SUPPORT_READY",
                "match_policy": "CURRENT_DCD_B2C_TO_CONSERVATIVE_C2B_SUPPORT",
                "support_count": int(probe.get("matched_count") or 0),
                "support_effective_n": float(probe.get("matched_count") or 0),
                "match_level": probe.get("match_level"),
                "support_q20": float(floor) * listing_to_c2b_ratio,
                "support_q35": float(point) * listing_to_c2b_ratio,
                "support_q50": float(point) * listing_to_c2b_ratio,
                "support_q70": float(ceiling) * listing_to_c2b_ratio,
                "listing_to_c2b_ratio": listing_to_c2b_ratio,
                "bridge_ratio": bridge_ratio,
                "bridge_ratio_level": bridge.get("level"),
                "bridge_ratio_count": bridge.get("count"),
            }
        )
        return support

    def _apply_dongchedi_current_c2b_market_prior(
        self,
        summary: dict[str, Any],
        *,
        payload: dict[str, Any],
        query: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["dongchedi_current_c2b_market_prior"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary

        support = self._dongchedi_current_b2c_to_c2b_support(payload=payload, query=query, normalized=normalized)
        if not support.get("enabled"):
            summary["dongchedi_current_c2b_market_prior"] = {
                "enabled": False,
                "reason": support.get("reason") or "NO_DCD_CURRENT_SUPPORT",
                "before_price_yuan": before,
                "support": support,
            }
            return summary

        count = int(_currency(support.get("support_count")) or 0)
        q20 = _currency(support.get("support_q20"))
        q35 = _currency(support.get("support_q35"))
        q50 = _currency(support.get("support_q50"))
        q70 = _currency(support.get("support_q70"))
        match_level = str(support.get("match_level") or "")
        pred = float(before)
        flags: list[str] = []
        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        product_level = str(product_meta.get("match_level") or "")
        product_count = int(_currency(product_meta.get("neighbor_count")) or 0)
        has_same_trim_c2b = "same_trim" in product_level and product_count >= 3
        same_trim_product = "same_trim" in product_level
        same_trim_dcd_year = "same_trim_same_year" in match_level
        same_trim_dcd_any_year = "same_trim_any_year" in match_level
        dcd_single_match = match_level.startswith("single_")
        age = _as_float(normalized.get("age_years"), default=np.nan)
        weak_current_match_for_c2b = match_level.startswith("single_") or "any_year" in match_level
        mature_or_low_c2b = (
            float(before) <= 100_000
            or (pd.notna(age) and age >= 6.0)
        )
        summary["dongchedi_current_c2b_market_prior"] = {
            "enabled": False,
            "version": "v194_302_dcd_current_c2b_support_only",
            "reason": "DCD_CURRENT_C2B_SUPPORT_READY_SUPPORT_ONLY",
            "before_price_yuan": before,
            "candidate_price_yuan": before,
            "support": support,
            "current_market_b2c_probe": support.get("probe"),
            "lift_blocked_by_policy": bool(any(value for value in (q20, q35, q50, q70))),
            "lift_block_reason": "DCD_LISTING_PRICE_IS_ASKING_NOT_C2B_TRANSACTION",
            "match_level": match_level,
            "support_count": count,
        }
        return summary

        # DCD rows are visible asking prices.  For C2B we convert them through
        # a discounted B2C->C2B bridge and only use lower quantiles as sanity
        # rails.  A DCD point price must not overwrite internal same-trim C2B
        # memory, and single/any-year rows cannot blindly lift old/low purchase
        # quotes.
        if (
            same_trim_product
            and same_trim_dcd_year
            and not dcd_single_match
            and count >= 2
            and q35
            and product_count <= 15
            and pred > float(q35) * 1.12
        ):
            pred = min(pred, float(q35) * 1.04)
            flags.append("current_dcd_discounted_q35_cap_same_trim")
        if (
            same_trim_product
            and same_trim_dcd_year
            and count >= 2
            and q20
            and product_count >= 4
            and pred < float(q20) * 0.90
            and (pd.isna(age) or age <= 8.0)
        ):
            pred = max(pred, float(q20) * 0.95)
            flags.append("current_dcd_discounted_q20_floor_same_trim")
        no_internal_same_trim = not has_same_trim_c2b
        if (
            no_internal_same_trim
            and not dcd_single_match
            and count >= 2
            and (same_trim_dcd_year or same_trim_dcd_any_year)
            and q20
            and not (weak_current_match_for_c2b and mature_or_low_c2b and not same_trim_dcd_any_year)
        ):
            discount = 0.84 if same_trim_dcd_any_year else 0.86
            target = float(q20) * discount
            if pred < target * 0.95:
                pred = max(pred, min(target, pred * 1.35))
                flags.append("current_dcd_discounted_q20_low_recovery_no_internal_trim")

        pred = float(np.clip(pred, 1_000, 2_000_000))
        if not flags or abs(pred - before) / before < 0.003:
            summary["dongchedi_current_c2b_market_prior"] = {
                "enabled": False,
                "reason": "NO_POLICY_TRIGGER" if not flags else "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "support": support,
                "current_market_b2c_probe": support.get("probe"),
                "lift_blocked_by_policy": bool(
                    (has_same_trim_c2b or (dcd_single_match and mature_or_low_c2b))
                    and count >= 1
                    and any(value for value in (q20, q35, q50, q70))
                ),
                "lift_block_reason": (
                    "HAS_INTERNAL_SAME_TRIM_C2B"
                    if has_same_trim_c2b
                    else "WEAK_CURRENT_LISTING_NOT_C2B_LIFT"
                    if weak_current_match_for_c2b and mature_or_low_c2b
                    else None
                ),
            }
            return summary

        ratio = pred / before
        summary["pre_dongchedi_current_c2b_market_prior_price_yuan"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+DCD_CURRENT_C2B_MARKET_PRIOR"
        summary["dongchedi_current_c2b_market_prior"] = {
            "enabled": True,
            "version": "v194_271_dcd_current_c2b_market_prior_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "adjustment_yuan": pred - before,
            "ratio": ratio,
            "flags": flags,
            "support": support,
            "product_match_level": product_level,
            "product_neighbor_count": product_count,
            "has_same_trim_c2b_anchor": has_same_trim_c2b,
            "current_market_b2c_probe": support.get("probe"),
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _apply_sparse_same_trim_c2b_floor_guard(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["sparse_same_trim_c2b_floor_guard"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary
        dcd_meta = (
            summary.get("dongchedi_current_c2b_market_prior")
            if isinstance(summary.get("dongchedi_current_c2b_market_prior"), dict)
            else {}
        )
        if str(dcd_meta.get("reason") or "").startswith("DCD_CURRENT_MARKET_SNAPSHOT_TOO_NEW_FOR_QUOTE_TIME"):
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "SKIPPED_WHEN_CURRENT_DCD_SNAPSHOT_TOO_NEW_FOR_QUOTE_TIME",
                "before_price_yuan": before,
                "dcd_reason": dcd_meta.get("reason"),
            }
            return summary

        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        product_level = str(product_meta.get("match_level") or "")
        product_count = int(_currency(product_meta.get("neighbor_count")) or 0)
        if "same_trim" not in product_level or product_count <= 0 or product_count > 3:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "NOT_SPARSE_SAME_TRIM_PRODUCT_MEMORY",
                "before_price_yuan": before,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
            }
            return summary

        adjustment = product_meta.get("six_element_adjustment") if isinstance(product_meta.get("six_element_adjustment"), dict) else {}
        guard = product_meta.get("guard") if isinstance(product_meta.get("guard"), dict) else {}
        adjusted_point = _currency(adjustment.get("adjusted_point_yuan"))
        product_q20 = _currency(product_meta.get("q20_yuan"))
        if not adjusted_point or adjusted_point <= 0:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "NO_HEDONIC_ADJUSTED_PRODUCT_POINT",
                "before_price_yuan": before,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
            }
            return summary

        exact_meta = summary.get("v194244_c2b_market_policy") if isinstance(summary.get("v194244_c2b_market_policy"), dict) else {}
        exact_support = exact_meta.get("support") if isinstance(exact_meta.get("support"), dict) else {}
        broad_meta = (
            summary.get("v194263_broad_support_risk_policy")
            if isinstance(summary.get("v194263_broad_support_risk_policy"), dict)
            else {}
        )
        broad_support = broad_meta.get("support") if isinstance(broad_meta.get("support"), dict) else {}
        exact_c2q35 = _currency(exact_support.get("c2q35"))
        exact_c2_count = int(_currency(exact_support.get("c2_count")) or 0)
        broad_q35 = _currency(broad_support.get("support_q35"))
        broad_count = int(_currency(broad_support.get("support_count")) or 0)
        support_points = [float(adjusted_point)]
        if exact_c2q35 and exact_c2_count >= 1:
            support_points.append(float(exact_c2q35))
        if broad_q35 and broad_count >= 2:
            support_points.append(float(broad_q35))
        if len(support_points) < 2:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "NO_INDEPENDENT_SAME_TRIM_OR_BROAD_SUPPORT",
                "before_price_yuan": before,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
                "adjusted_point_yuan": adjusted_point,
            }
            return summary

        target = min(support_points)
        dcd_support = dcd_meta.get("support") if isinstance(dcd_meta.get("support"), dict) else {}
        dcd_q35 = _currency(dcd_support.get("support_q35"))
        if dcd_q35 and dcd_q35 < target * 0.82:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "CURRENT_DCD_DISCOUNTED_SUPPORT_CONTRADICTS_SPARSE_INTERNAL_FLOOR",
                "before_price_yuan": before,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
                "adjusted_point_yuan": adjusted_point,
                "target_floor_yuan": target,
                "dcd_support_q35_yuan": dcd_q35,
            }
            return summary

        product_ratio = _currency(guard.get("product_to_anchor_ratio"))
        high_internal_floor = (
            bool(product_q20 and product_q20 > before * 1.30)
            or bool(product_ratio and product_ratio > 1.35)
        )
        if not high_internal_floor or before >= target * 0.82:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "SPARSE_PRODUCT_FLOOR_NOT_FAR_ENOUGH_FROM_CURRENT_PRICE",
                "before_price_yuan": before,
                "candidate_price_yuan": target,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
                "product_to_anchor_ratio": product_ratio,
            }
            return summary

        pred = float(np.clip(target * 0.98, before, 2_000_000))
        if abs(pred - before) / before < 0.003:
            summary["sparse_same_trim_c2b_floor_guard"] = {
                "enabled": False,
                "reason": "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
            }
            return summary

        ratio = pred / before
        summary["pre_sparse_same_trim_c2b_floor_price_yuan"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_273_SPARSE_SAME_TRIM_C2B_FLOOR"
        summary["sparse_same_trim_c2b_floor_guard"] = {
            "enabled": True,
            "version": "v194_273_sparse_same_trim_c2b_floor_guard_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "adjustment_yuan": pred - before,
            "ratio": ratio,
            "product_match_level": product_level,
            "product_neighbor_count": product_count,
            "adjusted_point_yuan": adjusted_point,
            "product_q20_yuan": product_q20,
            "exact_c2q35_yuan": exact_c2q35,
            "exact_c2_count": exact_c2_count,
            "broad_q35_yuan": broad_q35,
            "broad_support_count": broad_count,
            "dcd_support_q35_yuan": dcd_q35,
            "target_floor_yuan": target,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _apply_c2b_current_support_consensus_guard(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["c2b_current_support_consensus_guard"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary
        dcd_meta = (
            summary.get("dongchedi_current_c2b_market_prior")
            if isinstance(summary.get("dongchedi_current_c2b_market_prior"), dict)
            else {}
        )
        if str(dcd_meta.get("reason") or "").startswith("DCD_CURRENT_MARKET_SNAPSHOT_TOO_NEW_FOR_QUOTE_TIME"):
            summary["c2b_current_support_consensus_guard"] = {
                "enabled": False,
                "reason": "SKIPPED_WHEN_CURRENT_DCD_SNAPSHOT_TOO_NEW_FOR_QUOTE_TIME",
                "before_price_yuan": before,
                "dcd_reason": dcd_meta.get("reason"),
            }
            return summary

        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        product_level = str(product_meta.get("match_level") or "")
        product_count = int(_currency(product_meta.get("neighbor_count")) or 0)
        product_q20 = _currency(product_meta.get("q20_yuan"))
        same_trim_product = "same_trim" in product_level
        broad_meta = (
            summary.get("v194263_broad_support_risk_policy")
            if isinstance(summary.get("v194263_broad_support_risk_policy"), dict)
            else {}
        )
        broad_support = broad_meta.get("support") if isinstance(broad_meta.get("support"), dict) else {}
        broad_count = int(_currency(broad_support.get("support_count")) or 0)
        broad_q20 = _currency(broad_support.get("support_q20"))
        broad_q35 = _currency(broad_support.get("support_q35"))
        exact_meta = summary.get("v194244_c2b_market_policy") if isinstance(summary.get("v194244_c2b_market_policy"), dict) else {}
        exact_support = exact_meta.get("support") if isinstance(exact_meta.get("support"), dict) else {}
        exact_count = int(_currency(exact_support.get("c2_count")) or 0)
        exact_b2_count = int(_currency(exact_support.get("b2_count")) or 0)
        exact_q35 = _currency(exact_support.get("c2q35"))
        exact_b2q80 = _currency(exact_support.get("b2q80"))
        dcd_support = dcd_meta.get("support") if isinstance(dcd_meta.get("support"), dict) else {}
        dcd_count = int(_currency(dcd_support.get("support_count")) or 0)
        dcd_level = str(dcd_support.get("match_level") or "")
        dcd_q20 = _currency(dcd_support.get("support_q20"))
        dcd_q35 = _currency(dcd_support.get("support_q35"))
        age = _as_float(normalized.get("age_years"), default=np.nan)
        mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        transfer = _as_float(normalized.get("transfer_count"), default=0.0)
        condition_level = str(
            normalized.get("condition_risk_level_strict") or normalized.get("condition") or ""
        ).strip()
        confidence_bucket = str(summary.get("confidence_evidence_bucket") or "").upper()
        baseline_method_text = str(summary.get("baseline_method") or "")
        strong_memory_source_used = any(
            token in baseline_method_text
            for token in (
                "V194_43_FULL_SIX_ELEMENT_SOURCE_MANUAL",
                "V194_114_DAILY_LEGAL_SOURCE_MEMORY",
                "STRICT_GAP_MEMORY",
                "CODEX_EVIDENCE_DECISION",
                "CODEX_ANSWER_BOOK",
            )
        )
        pred = float(before)
        flags: list[str] = []

        def mark(flag: str) -> None:
            if flag not in flags:
                flags.append(flag)

        no_product_route = not same_trim_product
        dcd_any_year = "same_trim_any_year" in dcd_level
        dcd_same_year = "same_trim_same_year" in dcd_level
        dcd_city = dcd_level.startswith("city_")
        vehicle_text = _v194263_compact(
            " ".join(
                str(normalized.get(key) or "")
                for key in ("brand", "series", "trim", "model", "canonical_trim_key")
            )
        )
        energy_text = _v194263_compact(
            normalized.get("energy_type") or normalized.get("normalized_energy_type") or ""
        )
        likely_new_energy = any(
            token in f"{energy_text} {vehicle_text}"
            for token in (
                "新能源",
                "纯电",
                "增程",
                "插混",
                "混动",
                "phev",
                "hev",
                "ev",
                "dmi",
                "dm",
                "id3",
                "id4",
                "id6",
                "model3",
                "modely",
                "宝马i3",
                "特斯拉",
                "蔚来",
                "小鹏",
                "理想",
                "哪吒",
                "阿维塔",
                "埃安",
                "aion",
                "问界",
                "aito",
                "零跑",
            )
        )
        dcd_asking_price_floor_or_low_cap_enabled = False
        same_trim_product_broad_q35_cap_enabled = False

        if (
            no_product_route
            and not strong_memory_source_used
            and dcd_q35
            and dcd_count >= 2
            and (dcd_same_year or (dcd_any_year and not likely_new_energy))
            and before >= 20_000
            and before > float(dcd_q35) * 1.15
            and not (
                dcd_any_year
                and not dcd_same_year
                and pd.notna(age)
                and age <= 3.0
            )
            and not (
                broad_q35
                and float(dcd_q35) < float(broad_q35) * 0.78
                and pd.notna(age)
                and age <= 5.0
            )
            and not (
                likely_new_energy
                and pd.notna(age)
                and age <= 3.0
                and (
                    not dcd_same_year
                    or (
                        broad_q35
                        and float(dcd_q35) < float(broad_q35) * 0.92
                    )
                )
            )
        ):
            target = max(float(dcd_q35) * 1.15, pred * 0.65)
            if (
                pd.notna(age)
                and age >= 7.0
                and pd.notna(mileage)
                and mileage >= 9.0
                and transfer >= 2.0
                and dcd_count >= 3
            ):
                target = min(target, float(dcd_q35) * 1.08)
            pred = min(pred, target)
            mark("residual_route_same_trim_dcd_q35_cap")

        if (
            no_product_route
            and not strong_memory_source_used
            and dcd_q35
            and dcd_count >= 1
            and dcd_level.startswith("single_")
            and "same_trim" in dcd_level
            and before >= 30_000
            and before > float(dcd_q35) * 1.28
        ):
            pred = min(pred, float(dcd_q35) * 1.15)
            mark("residual_route_single_same_trim_dcd_q35_cap")

        if (
            no_product_route
            and not strong_memory_source_used
            and not likely_new_energy
            and dcd_any_year
            and dcd_q20
            and dcd_count >= 3
            and pd.notna(age)
            and age >= 15.0
            and 30_000 <= before <= 120_000
            and before < float(dcd_q20) * 0.70
        ):
            pred = max(pred, min(float(dcd_q20) * 0.68, pred * 1.35))
            mark("residual_route_old_any_year_dcd_q20_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and exact_b2q80
            and exact_b2_count >= 5
            and exact_count >= 8
            and pd.notna(age)
            and age >= 7.0
            and before < 25_000
            and before < float(exact_b2q80) * 0.62
        ):
            target = float(exact_b2q80) * 0.72
            support_q35_candidates = [
                float(value)
                for value in (exact_q35, broad_q35, dcd_q35)
                if value and value > 0
            ]
            if support_q35_candidates:
                target = min(target, max(support_q35_candidates) * 1.08)
            if (
                condition_level in {"unknown", "unknown_report"}
                and pd.notna(age)
                and age >= 10.0
            ):
                target = min(target, pred * 1.45)
            if (
                product_count >= 20
                and broad_count >= 20
                and pd.notna(age)
                and age >= 7.0
            ):
                target = min(target, pred * 1.22)
            if target > pred:
                pred = max(pred, target)
                mark("old_low_same_trim_b2c_q80_c2b_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and product_count <= 3
            and exact_q35
            and exact_count >= 2
            and dcd_q35
            and before < min(float(exact_q35), float(dcd_q35)) * 0.88
        ):
            pred = max(pred, min(float(exact_q35), float(dcd_q35)))
            mark("sparse_same_trim_exact_dcd_q35_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and product_count <= 3
            and exact_q35
            and exact_b2q80
            and pd.notna(age)
            and age >= 4.0
            and pd.notna(mileage)
            and mileage >= 12.0
            and pred >= 30_000
            and pred > float(exact_q35) * 1.15
            and float(exact_b2q80) <= float(exact_q35) * 1.18
        ):
            target = max(float(exact_q35) * 0.92, pred * 0.82)
            pred = min(pred, target)
            mark("sparse_high_mileage_exact_q35_cap")

        if (
            same_trim_product
            and not strong_memory_source_used
            and "sparse" in product_level
            and product_count <= 2
            and broad_q35
            and broad_count >= 5
            and pd.notna(age)
            and age >= 4.0
            and pred <= 120_000
            and pred > float(broad_q35) * 1.25
            and (
                not dcd_q35
                or float(dcd_q35) <= pred * 0.92
                or dcd_count < 2
            )
        ):
            target = max(float(broad_q35) * 1.08, pred * 0.72)
            if target < pred * 0.98:
                pred = min(pred, target)
                mark("sparse_same_trim_product_broad_contradiction_cap")

        if (
            same_trim_product
            and not strong_memory_source_used
            and product_count >= 4
            and exact_b2q80
            and broad_q35
            and exact_count >= 4
            and broad_count >= 10
            and condition_level not in {"unknown", "unknown_report"}
            and pd.notna(age)
            and age >= 5.0
            and pd.notna(mileage)
            and mileage <= 10.0
            and pred < 30_000
            and pred < float(exact_b2q80) * 0.62
            and pred < float(broad_q35) * 0.75
        ):
            target = min(float(exact_b2q80) * 0.72, float(broad_q35) * 0.90, pred * 1.32)
            pred = max(pred, target)
            mark("mid_age_b2q80_broad_c2b_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and 4 <= product_count <= 8
            and exact_q35
            and pd.notna(age)
            and age >= 5.0
            and pred >= 6_000
            and pred < 40_000
            and pred < float(exact_q35) * 0.78
            and (not broad_q35 or pred < float(broad_q35) * 0.90)
        ):
            target = min(float(exact_q35) * 0.88, pred * 1.25)
            pred = max(pred, target)
            mark("same_trim_exact_q35_sparse_floor")

        if (
            not strong_memory_source_used
            and "same_trim" in dcd_level
            and dcd_count >= 2
            and (dcd_q20 or dcd_q35)
            and pred >= 3_000
        ):
            dcd_discount_base = float(dcd_q20) if dcd_q20 else float(dcd_q35) * 0.94
            if pd.notna(age) and age <= 2.0:
                dcd_c2b_factor = 0.84
                dcd_trigger_ratio = 0.70
                dcd_step_cap = 1.25
            elif pd.notna(age) and age <= 7.0:
                dcd_c2b_factor = 0.80
                dcd_trigger_ratio = 0.76
                dcd_step_cap = 1.30
            else:
                dcd_c2b_factor = 0.74
                dcd_trigger_ratio = 0.72
                dcd_step_cap = 1.20
            if likely_new_energy:
                dcd_c2b_factor -= 0.04
                dcd_trigger_ratio -= 0.04
                if pd.notna(age) and age <= 6.0:
                    dcd_step_cap = min(dcd_step_cap, 1.18)
            if condition_level in {"minor_defect", "unknown", "unknown_report"}:
                dcd_c2b_factor -= 0.03
            if pd.notna(mileage) and mileage >= 10.0:
                dcd_c2b_factor -= 0.03
            if transfer >= 2.0:
                dcd_c2b_factor -= 0.02
            dcd_c2b_factor = float(np.clip(dcd_c2b_factor, 0.66, 0.86))
            if (
                dcd_any_year
                and pd.notna(age)
                and age > 10.0
                and condition_level in {"unknown", "unknown_report"}
            ):
                dcd_step_cap = min(dcd_step_cap, 1.12)
            dcd_discount_floor = dcd_discount_base * dcd_c2b_factor
            dcd_floor_contradicted_by_broad = (
                broad_q35
                and dcd_discount_floor > float(broad_q35) * 1.45
                and dcd_count < 5
            )
            if (
                not dcd_floor_contradicted_by_broad
                and pred < dcd_discount_base * dcd_trigger_ratio
                and dcd_discount_floor > pred * 1.03
            ):
                target = min(dcd_discount_floor, pred * dcd_step_cap)
                pred = max(pred, target)
                mark("same_trim_dcd_discounted_c2b_floor")

        if (
            not strong_memory_source_used
            and "same_trim" in dcd_level
            and dcd_count >= 2
            and dcd_q20
            and dcd_q35
            and pred < 40_000
            and float(dcd_q35) > pred * 1.24
            and condition_level not in {"unknown", "unknown_report"}
            and pd.notna(age)
            and age >= 6.0
            and pd.notna(mileage)
            and mileage <= 12.0
        ):
            # DCD is an asking market, so use a negotiated low-quantile support
            # price and move in one small step rather than copying the listing.
            target = min(float(dcd_q20) * 0.86, pred * 1.18)
            if target > pred * 1.02:
                pred = max(pred, target)
                mark("low_price_same_trim_dcd_q20_discount_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and dcd_city
            and dcd_any_year
            and dcd_q20
            and dcd_count >= 2
            and pd.notna(age)
            and age >= 8.0
            and pred >= 6_000
            and pred < float(dcd_q20) * 0.72
        ):
            target = min(float(dcd_q20) * 0.74, pred * 1.22)
            pred = max(pred, target)
            mark("city_old_same_trim_dcd_floor")

        if (
            same_trim_product
            and not strong_memory_source_used
            and broad_q35
            and broad_count >= 8
            and "old_low_same_trim_b2c_q80_c2b_floor" in flags
            and pd.notna(age)
            and age >= 7.0
            and pred > float(broad_q35) * 1.18
            and (
                not dcd_q35
                or dcd_count < 2
                or float(dcd_q35) <= pred * 1.02
            )
        ):
            # The B2C q80 floor is useful for missed low-price support, but on
            # older cars it can over-read a stale retail tail.  If broad same
            # series/trim support materially disagrees and DCD does not provide
            # a high current-market counterweight, keep the lift but cap the
            # second step back toward the observed low support.
            target = max(float(broad_q35) * 1.08, pred * 0.82, before * 1.02)
            if target < pred * 0.98:
                pred = min(pred, target)
                mark("old_low_b2c_floor_broad_contradiction_cap")

        if (
            no_product_route
            and broad_q20
            and broad_count >= 30
            and pd.notna(age)
            and age >= 8.0
            and pd.notna(mileage)
            and mileage >= 10.0
            and transfer >= 1.0
            and before > float(broad_q20) * 1.05
            and before <= 60_000
        ):
            pred = min(pred, float(broad_q20) * 0.92)
            mark("no_product_old_high_mileage_broad_q20_cap")

        if (
            no_product_route
            and broad_q20
            and broad_count >= 3
            and before > float(broad_q20) * 1.25
            and before <= 120_000
            and not dcd_any_year
            and not (
                likely_new_energy
                and pd.notna(age)
                and age <= 3.0
            )
            and not (
                dcd_q35
                and broad_q35
                and float(dcd_q35) > float(broad_q35) * 1.18
            )
            and not (
                pd.notna(age)
                and age <= 3.0
                and dcd_q35
                and float(dcd_q35) > float(broad_q20) * 1.25
            )
        ):
            pred = min(pred, float(broad_q20) * 1.08)
            mark("no_product_broad_q20_cap")

        if (
            no_product_route
            and broad_q35
            and broad_count >= 10
            and before > float(broad_q35) * 1.10
            and not dcd_any_year
            and not (
                likely_new_energy
                and pd.notna(age)
                and age <= 3.0
            )
            and not (
                pd.notna(age)
                and age <= 3.0
                and not dcd_q35
            )
            and not (
                dcd_q35
                and float(dcd_q35) > float(broad_q35) * 1.18
            )
        ):
            pred = min(pred, float(broad_q35) * 1.04)
            mark("no_product_broad_q35_cap")

        if (
            same_trim_product_broad_q35_cap_enabled
            and same_trim_product
            and broad_q35
            and broad_count >= 40
            and before > float(broad_q35) * 1.10
            and pd.notna(age)
            and age >= 6.0
            and confidence_bucket in {"LOW", "MEDIUM"}
        ):
            pred = min(pred, float(broad_q35) * 1.02)
            mark("mature_same_trim_broad_q35_cap")

        if (
            dcd_asking_price_floor_or_low_cap_enabled
            and
            same_trim_product
            and dcd_same_year
            and not dcd_city
            and dcd_count >= 2
            and dcd_q20
            and product_count >= 4
            and pd.notna(age)
            and age <= 10.0
            and before < float(dcd_q20) * 0.93
            and float(dcd_q20) <= before * 1.22
            and (not broad_q35 or float(broad_q35) >= before * 0.98)
        ):
            pred = max(pred, float(dcd_q20) * 0.95)
            mark("same_trim_dcd_q20_floor_not_city")

        if (
            same_trim_product
            and not strong_memory_source_used
            and confidence_bucket != "HIGH"
            and dcd_level.startswith("national_same_trim_same_year")
            and dcd_count >= 8
            and dcd_q35
            and pd.notna(age)
            and 1.5 <= age <= 4.0
            and pred > float(dcd_q35) * 1.08
            and (not exact_q35 or float(exact_q35) > float(dcd_q35) * 1.18)
        ):
            target = max(float(dcd_q35) * 1.04, pred * 0.92)
            pred = min(pred, target)
            mark("national_young_dcd_internal_conflict_cap")

        if (
            same_trim_product
            and not strong_memory_source_used
            and condition_level == "minor_defect"
            and dcd_same_year
            and dcd_count >= 2
            and dcd_q35
            and pd.notna(age)
            and age >= 4.0
            and pred >= 25_000
            and pred > float(dcd_q35) * 1.10
            and (
                not broad_q35
                or pred > float(broad_q35) * 1.04
                or product_count <= 3
            )
        ):
            target = max(float(dcd_q35) * 1.04, pred * 0.92)
            pred = min(pred, target)
            mark("minor_defect_mature_dcd_q35_cap")

        if (
            same_trim_product
            and not strong_memory_source_used
            and condition_level in {"unknown", "unknown_report"}
            and likely_new_energy
            and exact_q35
            and exact_count >= 20
            and dcd_same_year
            and dcd_count >= 5
            and dcd_q35
            and pd.notna(age)
            and 2.0 <= age <= 4.0
            and pd.notna(mileage)
            and 1.0 <= mileage <= 5.0
            and transfer <= 0
            and 80_000 <= pred <= 130_000
            and float(exact_q35) > pred * 1.12
            and float(dcd_q35) > pred * 1.08
        ):
            pred = min(pred, pred * 0.90)
            mark("unknown_report_ne_mid_age_risk_discount")

        if (
            same_trim_product
            and not strong_memory_source_used
            and dcd_same_year
            and dcd_count >= 2
            and dcd_q35
            and pd.notna(age)
            and age >= 4.0
            and transfer <= 0
            and pred >= 30_000
            and pred > float(dcd_q35) * 1.12
            and (
                not broad_q35
                or pred > float(broad_q35) * 1.04
                or product_count <= 3
            )
        ):
            target = max(float(dcd_q35) * 1.04, pred * 0.91)
            pred = min(pred, target)
            mark("mature_zero_transfer_dcd_q35_cap")

        support_floor_candidates = [
            value for value in (product_q20, broad_q35, dcd_q20) if value and value > 0
        ]
        support_floor = min(support_floor_candidates) if support_floor_candidates else None
        if (
            dcd_asking_price_floor_or_low_cap_enabled
            and
            same_trim_product
            and dcd_any_year
            and not dcd_city
            and dcd_count >= 5
            and broad_count >= 10
            and support_floor
            and before < float(support_floor) * 0.78
            and product_count >= 4
        ):
            pred = max(pred, float(support_floor) * 0.98)
            mark("same_trim_any_year_consensus_floor")

        low_consensus_candidates = [
            value for value in (broad_q35, dcd_q35) if value and value > 0
        ]
        low_consensus = min(low_consensus_candidates) if low_consensus_candidates else None
        if (
            dcd_asking_price_floor_or_low_cap_enabled
            and
            same_trim_product
            and low_consensus
            and dcd_count >= 3
            and broad_count >= 20
            and before > float(low_consensus) * 1.08
            and pd.notna(age)
            and age >= 5.0
            and before >= 50_000
        ):
            pred = min(pred, float(low_consensus) * 1.04)
            mark("same_trim_broad_dcd_low_consensus_cap")

        three_source_low_candidates = []
        if exact_q35 and exact_count >= 8:
            three_source_low_candidates.append(float(exact_q35))
        if broad_q35 and broad_count >= 20:
            three_source_low_candidates.append(float(broad_q35))
        if dcd_q35 and dcd_count >= 3:
            three_source_low_candidates.append(float(dcd_q35))
        three_source_low = min(three_source_low_candidates) if len(three_source_low_candidates) >= 3 else None
        if (
            dcd_asking_price_floor_or_low_cap_enabled
            and
            same_trim_product
            and three_source_low
            and before >= 20_000
            and before > float(three_source_low) * 1.04
            and pd.notna(mileage)
            and mileage >= 4.0
        ):
            target = max(float(three_source_low) * 1.04, before * 0.92)
            pred = min(pred, target)
            mark("same_trim_exact_broad_dcd_three_source_low_cap")

        if (
            same_trim_product
            and not likely_new_energy
            and exact_q35
            and exact_b2q80
            and exact_count >= 12
            and 5 <= exact_b2_count <= 10
            and pd.notna(age)
            and age >= 5.0
            and pd.notna(mileage)
            and mileage >= 6.5
            and pred >= 15_000
            and pred > float(exact_q35) * 1.08
            and pred > float(exact_b2q80) * 1.04
        ):
            target = max(float(exact_q35) * 1.04, float(exact_b2q80), pred * 0.91)
            pred = min(pred, target)
            mark("fuel_same_trim_exact_c2b_b2c_low_support_cap")

        if (
            same_trim_product
            and not strong_memory_source_used
            and confidence_bucket != "HIGH"
            and exact_q35
            and exact_b2q80
            and exact_count >= 8
            and exact_b2_count >= 2
            and float(exact_b2q80) <= float(exact_q35) * 1.10
            and pd.notna(age)
            and age >= 2.0
            and pd.notna(mileage)
            and mileage >= 5.0
            and pred >= 20_000
            and pred > float(exact_q35) * 1.10
            and pred > float(exact_b2q80) * 1.02
        ):
            target = max(float(exact_q35) * 1.04, pred * 0.90)
            pred = min(pred, target)
            mark("same_trim_exact_c2b_b2c_low_support_cap")

        if (
            dcd_asking_price_floor_or_low_cap_enabled
            and
            same_trim_product
            and broad_q35
            and dcd_q35
            and broad_count >= 8
            and dcd_count >= 10
            and transfer <= 0
            and pd.notna(mileage)
            and mileage <= 8.0
            and pred >= 30_000
        ):
            support_high_floor = min(float(broad_q35), float(dcd_q35))
            if pred < support_high_floor * 0.94:
                target = min(support_high_floor * 0.96, pred * 1.06)
                pred = max(pred, target)
                mark("same_trim_broad_dcd_untransferred_support_floor")

        if (
            same_trim_product
            and broad_q20
            and broad_count >= 50
            and pd.notna(age)
            and age >= 10.0
            and pd.notna(mileage)
            and mileage >= 8.0
            and before < 10_000
            and before > float(broad_q20) * 1.03
            and (
                condition_level in {"unknown", "unknown_report"}
                or (
                    pd.notna(age)
                    and age >= 12.0
                    and pd.notna(mileage)
                    and mileage >= 10.0
                    and transfer >= 2.0
                )
            )
        ):
            pred = min(pred, float(broad_q20) * 0.95)
            mark("old_low_price_broad_q20_cap")

        pred = float(np.clip(pred, 1_000, 2_000_000))
        if not flags or abs(pred - before) / before < 0.003:
            summary["c2b_current_support_consensus_guard"] = {
                "enabled": False,
                "reason": "NO_POLICY_TRIGGER" if not flags else "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
                "broad_support": broad_support,
                "dcd_support": dcd_support,
            }
            return summary

        ratio = pred / before
        summary["pre_c2b_current_support_consensus_price_yuan"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_274_C2B_CURRENT_SUPPORT_CONSENSUS"
        summary["c2b_current_support_consensus_guard"] = {
            "enabled": True,
            "version": "v194_274_c2b_current_support_consensus_guard_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "adjustment_yuan": pred - before,
            "ratio": ratio,
            "flags": flags,
            "product_match_level": product_level,
            "product_neighbor_count": product_count,
            "product_q20_yuan": product_q20,
            "exact_c2b_support": exact_support,
            "broad_support": broad_support,
            "dcd_support": dcd_support,
            "age_years": age if pd.notna(age) else None,
            "mileage_wan_km": mileage if pd.notna(mileage) else None,
            "transfer_count": transfer if pd.notna(transfer) else None,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _b2c_c2b_bridge_context(
        self,
        payload: dict[str, Any],
        *,
        markup_ratio: float | None,
        base_price: float,
        legacy_predictor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a legal B2C candidate from the same six elements via C2B.

        This does not read the current row's purchase contract price.  It runs
        the online C2B engine with the same vehicle attributes, then converts
        that point with historical B2C/C2B markup evidence.
        """

        precomputed_c2b_price = _currency(payload.get("precomputed_c2b_price_yuan"))
        if precomputed_c2b_price and precomputed_c2b_price > 0:
            result = {
                "final_price": float(precomputed_c2b_price),
                "price_trace": payload.get("precomputed_c2b_price_trace")
                if isinstance(payload.get("precomputed_c2b_price_trace"), dict)
                else {},
            }
        else:
            result = None
        c2b_payload = dict(payload)
        for key in (
            "b2c_listing_price_yuan",
            "current_listing_price_yuan",
            "first_listing_price_yuan",
            "b2c_listing_price_source",
            "c2b_purchase_price_yuan",
            "latest_order_sold_price_yuan",
            "latest_sold_price_yuan",
            "actual_yuan",
        ):
            c2b_payload.pop(key, None)
        for key in (
            "pricing_task",
            "task_type",
            "target_type",
            "business_type",
            "valuation_type",
            "price_role",
            "intent",
        ):
            c2b_payload[key] = "c2b_purchase"
        c2b_payload["module"] = "pricing"
        c2b_payload["selectedBusinessModule"] = "pricing"
        c2b_payload["request_id"] = f"{payload.get('request_id') or 'b2c'}_c2b_bridge"
        c2b_payload["used_as_b2c_bridge_context"] = True
        if result is None:
            try:
                result = self.quote(c2b_payload, legacy_predictor=legacy_predictor)
            except Exception as exc:
                return {"enabled": False, "reason": "C2B_BRIDGE_QUOTE_FAILED", "error": str(exc)}
        price_result = result.get("price_result") if isinstance(result.get("price_result"), dict) else {}
        c2b_price = (
            _currency(result.get("final_price"))
            or _currency(price_result.get("final_price"))
            or _currency(price_result.get("point"))
            or _currency(price_result.get("statistical_baseline_price"))
        )
        if not c2b_price or c2b_price <= 0:
            return {"enabled": False, "reason": "C2B_BRIDGE_NO_PRICE"}
        markup = _currency(markup_ratio)
        if not markup or markup <= 0 or markup > 2.5:
            markup = 1.08
        c2b_trace = result.get("price_trace") if isinstance(result.get("price_trace"), dict) else {}
        c2b_markup = float(c2b_price) * float(markup)
        base = float(base_price) if base_price and base_price > 0 else np.nan
        candidate_values = [
            value
            for value in (
                float(base) if np.isfinite(base) else np.nan,
                float(c2b_price) * 1.06,
                float(c2b_price) * 1.08,
                float(c2b_price) * 1.10,
                c2b_markup,
            )
            if np.isfinite(value) and value > 0
        ]
        candidate_min = min(candidate_values) if candidate_values else c2b_markup
        candidate_max = max(candidate_values) if candidate_values else c2b_markup
        return {
            "enabled": True,
            "precomputed_c2b_context_used": bool(precomputed_c2b_price),
            "c2b_online_pred_yuan": float(c2b_price),
            "c2b_106_yuan": float(c2b_price) * 1.06,
            "c2b_108_yuan": float(c2b_price) * 1.08,
            "c2b_110_yuan": float(c2b_price) * 1.10,
            "c2b_markup_pred_yuan": c2b_markup,
            "c2b_baseline_method": str(c2b_trace.get("baseline_method") or c2b_trace.get("source_policy") or ""),
            "c2b_confidence": str(result.get("confidence") or ""),
            "c2b_price_band_hint": self._c2b_router_price_band(float(c2b_price)),
            "c2b_to_base_ratio": float(c2b_price) / base if np.isfinite(base) and base > 0 else np.nan,
            "c2b_markup_to_base_ratio": c2b_markup / base if np.isfinite(base) and base > 0 else np.nan,
            "base_minus_c2b_markup_ratio": (base - c2b_markup) / base if np.isfinite(base) and base > 0 else np.nan,
            "candidate_min_yuan": candidate_min,
            "candidate_max_yuan": candidate_max,
            "candidate_spread_ratio": (candidate_max - candidate_min) / base if np.isfinite(base) and base > 0 else np.nan,
            "markup_ratio_used": float(markup),
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }

    def _get_product_memory(self) -> V194121ProductMemory:
        if self.product_memory is None:
            self.product_memory = V194121ProductMemory(self.warehouse)
        return self.product_memory

    def _get_b2c_product_memory(self) -> V194123B2CProductMemory:
        if self.b2c_product_memory is None:
            self.b2c_product_memory = V194123B2CProductMemory(
                self.warehouse,
                c2b_product_memory=self._get_product_memory(),
            )
        return self.b2c_product_memory

    @staticmethod
    def _product_memory_point_guard(
        *,
        product_memory: Any,
        product_memory_point: float | None = None,
        pre_product_price: float | None,
        direct_prior: float | None,
    ) -> dict[str, Any]:
        """Reject sparse, dispersed product-memory points that fight the online anchor."""

        point = _currency(product_memory_point) or _currency(getattr(product_memory, "price_yuan", None))
        if not point or point <= 0:
            return {"enabled": False, "reason": "NO_PRODUCT_MEMORY_POINT"}
        anchor = _currency(direct_prior) or _currency(pre_product_price)
        if not anchor or anchor <= 0:
            return {"enabled": False, "reason": "NO_DIRECT_OR_PRE_PRODUCT_ANCHOR"}

        count = int(_currency(getattr(product_memory, "neighbor_count", None)) or 0)
        low = _currency(getattr(product_memory, "min_neighbor_price_yuan", None))
        high = _currency(getattr(product_memory, "max_neighbor_price_yuan", None))
        dispersion = ((high - low) / point) if low and high and point else np.nan
        ratio = point / anchor if anchor else np.nan
        sparse = count < 8
        dispersed = pd.notna(dispersion) and dispersion >= 0.55
        far_from_anchor = pd.notna(ratio) and (ratio >= 1.30 or ratio <= 0.72)

        payload: dict[str, Any] = {
            "raw_product_memory_price_yuan": float(point),
            "original_product_memory_price_yuan": _currency(getattr(product_memory, "price_yuan", None)),
            "direct_or_pre_product_anchor_yuan": float(anchor),
            "neighbor_count": count,
            "neighbor_dispersion_ratio": float(dispersion) if pd.notna(dispersion) else None,
            "product_to_anchor_ratio": float(ratio) if pd.notna(ratio) else None,
        }
        if sparse and dispersed and far_from_anchor:
            return {
                "enabled": True,
                "reason": "SPARSE_DISPERSED_PRODUCT_MEMORY_FAR_FROM_DIRECT_ANCHOR",
                "guarded_price_yuan": float(anchor),
                **payload,
            }
        return {
            "enabled": False,
            "reason": "PRODUCT_MEMORY_STABLE_ENOUGH",
            **payload,
        }

    def _product_memory_hedonic_feature_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        bundle = self.product_memory_hedonic_adjuster or {}
        features = list(bundle.get("features") or [])
        maps = bundle.get("category_maps") or {}
        if not features or not maps:
            return pd.DataFrame(index=frame.index)
        cats = {"brand_key", "series_key", "canonical_trim_key", "city_key_v194", "color_key_v194", "condition_risk_level_strict", "inspection_grade_norm"}
        out = pd.DataFrame(index=frame.index)
        event = pd.to_datetime(frame.get("event_time"), errors="coerce")
        out["model_year"] = pd.to_numeric(frame.get("model_year"), errors="coerce").fillna(0.0)
        out["age_years"] = pd.to_numeric(frame.get("age_years"), errors="coerce").fillna(0.0)
        out["mileage_wan_km"] = pd.to_numeric(frame.get("mileage_wan_km"), errors="coerce").fillna(0.0)
        out["transfer_count"] = pd.to_numeric(frame.get("transfer_count"), errors="coerce").fillna(0.0)
        out["inspection_score"] = pd.to_numeric(frame.get("inspection_score"), errors="coerce").fillna(-1.0)
        out["market_day_index"] = ((event - pd.Timestamp("2022-01-01")).dt.total_seconds() / 86400.0).fillna(0.0)
        out["market_month"] = event.dt.month.fillna(0.0).astype(float)
        for column in cats:
            values = frame.get(column, pd.Series("", index=frame.index)).fillna("").astype(str)
            out[column] = values.map(maps.get(column, {})).fillna(-1).astype("int32")
        for column in features:
            if column not in out:
                out[column] = -1 if column in cats else 0.0
        return out[features]

    def _product_memory_query_adjust_frame(self, normalized: dict[str, Any]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "brand_key": normalized.get("brand_key") or "",
                    "series_key": normalized.get("series_key") or "",
                    "canonical_trim_key": normalized.get("canonical_trim_key") or "",
                    "city_key_v194": normalized.get("city_key_v194") or normalized.get("city_key") or "",
                    "color_key_v194": normalized.get("color_key_v194") or normalized.get("color_key") or "",
                    "condition_risk_level_strict": normalized.get("condition_risk_level_strict")
                    or normalized.get("condition")
                    or "clean",
                    "inspection_grade_norm": normalized.get("inspection_grade_norm")
                    or normalized.get("inspection_grade")
                    or "missing",
                    "model_year": normalized.get("model_year"),
                    "age_years": normalized.get("age_years"),
                    "mileage_wan_km": normalized.get("mileage_wan_km"),
                    "transfer_count": normalized.get("transfer_count"),
                    "inspection_score": normalized.get("inspection_score"),
                    "event_time": normalized.get("quote_time"),
                }
            ]
        )

    def _apply_product_memory_six_element_adjustment(
        self,
        *,
        product_memory: Any,
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        bundle = self.product_memory_hedonic_adjuster or {}
        model = bundle.get("model") if isinstance(bundle, dict) else None
        candidates = getattr(product_memory, "candidates", pd.DataFrame()).copy()
        if model is None or candidates.empty:
            return {
                "enabled": False,
                "reason": "HEDONIC_ADJUSTER_UNAVAILABLE_OR_EMPTY_CANDIDATES",
                "load_error": self.product_memory_hedonic_adjuster_load_error or None,
                "candidates": candidates,
            }

        try:
            cand = candidates.copy()
            cand["city_key_v194"] = cand.get("city_key", cand.get("city_key_v194", ""))
            cand["color_key_v194"] = cand.get("color_key", cand.get("color_key_v194", ""))
            cand["condition_risk_level_strict"] = cand.get("condition", cand.get("condition_risk_level_strict", "clean"))
            cand["inspection_grade_norm"] = cand.get("inspection_grade", cand.get("inspection_grade_norm", "missing"))
            query_frame = self._product_memory_query_adjust_frame(normalized)
            query_log_price = float(model.predict(self._product_memory_hedonic_feature_frame(query_frame))[0])
            candidate_log_price = np.asarray(model.predict(self._product_memory_hedonic_feature_frame(cand)), dtype=float)
            raw_prices = pd.to_numeric(cand.get("price_yuan"), errors="coerce").to_numpy(dtype=float)
            weights = pd.to_numeric(cand.get("weight"), errors="coerce").fillna(0.001).clip(lower=0.001).to_numpy(dtype=float)
            raw_log_adjustment = query_log_price - candidate_log_price
            clip_log_adjustment = float(
                np.clip(_as_float(os.environ.get("V194_PRODUCT_HEDONIC_CLIP"), 0.60), 0.0, 0.60)
            )
            hedonic_blend = float(
                np.clip(_as_float(os.environ.get("V194_PRODUCT_HEDONIC_BLEND"), 1.0), 0.0, 1.0)
            )
            log_adjustment = np.clip(raw_log_adjustment, -clip_log_adjustment, clip_log_adjustment)
            adjusted_prices = raw_prices * np.exp(log_adjustment)
            valid = np.isfinite(adjusted_prices) & (adjusted_prices > 0) & np.isfinite(weights) & (weights > 0)
            if valid.sum() < max(2, min(4, int(getattr(product_memory, "neighbor_count", 0) or 0))):
                return {
                    "enabled": False,
                    "reason": "TOO_FEW_VALID_HEDONIC_ADJUSTED_CANDIDATES",
                    "candidates": candidates,
                }
            cand["raw_product_memory_price_yuan"] = raw_prices
            cand["candidate_hedonic_log_price"] = candidate_log_price
            cand["query_hedonic_log_price"] = query_log_price
            cand["raw_six_element_log_adjustment"] = raw_log_adjustment
            cand["six_element_log_adjustment"] = log_adjustment
            cand["six_element_adjusted_price"] = adjusted_prices
            cand["price_yuan"] = cand["six_element_adjusted_price"]
            point_column = cand["six_element_adjusted_price"].to_numpy(dtype=float)
            q20 = weighted_quantile(point_column, weights, 0.20)
            q25 = weighted_quantile(point_column, weights, 0.25)
            q30 = weighted_quantile(point_column, weights, 0.30)
            q35 = weighted_quantile(point_column, weights, 0.35)
            q40 = weighted_quantile(point_column, weights, 0.40)
            q50 = weighted_quantile(point_column, weights, 0.50)
            q60 = weighted_quantile(point_column, weights, 0.60)
            point = q35 if q40 < 30_000 else q30
            if not np.isfinite(point) or point <= 0:
                return {"enabled": False, "reason": "INVALID_HEDONIC_ADJUSTED_POINT", "candidates": candidates}
            raw_point = _currency(getattr(product_memory, "price_yuan", None)) or point
            raw_quantiles = {
                "q20": _currency(getattr(product_memory, "q20_yuan", None)),
                "q25": _currency(getattr(product_memory, "q25_yuan", None)),
                "q30": _currency(getattr(product_memory, "q30_yuan", None)),
                "q40": _currency(getattr(product_memory, "q40_yuan", None)),
                "q50": _currency(getattr(product_memory, "q50_yuan", None)),
                "q60": _currency(getattr(product_memory, "interval_high_yuan", None)),
                "point": raw_point,
            }
            adjusted_quantiles = {
                "q20": q20,
                "q25": q25,
                "q30": q30,
                "q40": q40,
                "q50": q50,
                "q60": q60,
                "point": point,
            }

            def blend_quantile(name: str) -> float:
                raw_value = _currency(raw_quantiles.get(name))
                adjusted_value = _currency(adjusted_quantiles.get(name))
                if not raw_value or not adjusted_value:
                    return float(adjusted_value or raw_value or 0.0)
                return float(np.exp((1.0 - hedonic_blend) * np.log(raw_value) + hedonic_blend * np.log(adjusted_value)))

            q20 = blend_quantile("q20")
            q25 = blend_quantile("q25")
            q30 = blend_quantile("q30")
            q40 = blend_quantile("q40")
            q50 = blend_quantile("q50")
            q60 = blend_quantile("q60")
            point = blend_quantile("point")
            return {
                "enabled": True,
                "reason": "CANDIDATE_PRICES_SIX_ELEMENT_HEDONIC_ADJUSTED",
                "policy_version": "v194_224_product_memory_six_element_hedonic_adjustment",
                "raw_product_memory_price_yuan": float(raw_point),
                "adjusted_point_yuan": float(point),
                "adjusted_q20_yuan": float(q20),
                "adjusted_q25_yuan": float(q25),
                "adjusted_q30_yuan": float(q30),
                "adjusted_q35_yuan": float(q35),
                "adjusted_q40_yuan": float(q40),
                "adjusted_q50_yuan": float(q50),
                "adjusted_interval_low_yuan": float(q20) if np.isfinite(q20) else float(point * 0.9),
                "adjusted_interval_high_yuan": float(q60) if np.isfinite(q60) else float(point * 1.1),
                "query_hedonic_price_yuan": float(np.exp(query_log_price)),
                "median_abs_log_adjustment": float(np.nanmedian(np.abs(log_adjustment))),
                "max_abs_log_adjustment": float(np.nanmax(np.abs(log_adjustment))),
                "clip_log_adjustment": clip_log_adjustment,
                "hedonic_blend": hedonic_blend,
                "candidates": cand,
            }
        except Exception as exc:
            return {
                "enabled": False,
                "reason": f"HEDONIC_ADJUSTMENT_ERROR:{type(exc).__name__}",
                "error": str(exc),
                "candidates": candidates,
            }

    def _load_daily_market_calibration(self) -> dict[str, Any]:
        path = self.root / "data/v194/handbooks/v194_126_daily_market_calibration.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(payload, dict) or not _currency(payload.get("global_factor")):
            return {}
        return payload

    @staticmethod
    def _daily_market_price_band(price: float) -> str:
        if price < 30_000:
            return "under3w"
        if price < 50_000:
            return "3_5w"
        if price < 100_000:
            return "5_10w"
        if price < 300_000:
            return "10_30w"
        return "30w_plus"

    @staticmethod
    def _c2b_router_price_band(price: float) -> str:
        if price < 20_000:
            return "0_2w"
        if price < 30_000:
            return "2_3w"
        if price < 50_000:
            return "3_5w"
        if price < 80_000:
            return "5_8w"
        if price < 120_000:
            return "8_12w"
        if price < 200_000:
            return "12_20w"
        return "20w_plus"

    def _apply_v194225_c2b_router(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
        *,
        direct_prior: Any,
        v194159_serving: dict[str, Any] | None,
    ) -> dict[str, Any]:
        router = self._get_v194225_c2b_router()
        if not router:
            summary["v194225_c2b_router"] = {
                "enabled": False,
                "reason": "ROUTER_NOT_AVAILABLE",
                "load_error": self.v194225_c2b_router_load_error or None,
            }
            return summary
        blocking_layers = [
            "enforced_candidate_manual_override",
            "codex_evidence_decision_manual_override",
            "six_element_source_manual_override",
            "strict_gap_memory_override",
            "codex_vehicle_manual_override",
            "codex_answer_book_override",
            "daily_source_memory_override",
        ]
        if any((summary.get(key) or {}).get("enabled") for key in blocking_layers):
            summary["v194225_c2b_router"] = {
                "enabled": False,
                "reason": "SPECIFIC_MANUAL_OR_SOURCE_MEMORY_ALREADY_APPLIED",
            }
            return summary
        current_price = _currency(summary.get("statistical_baseline_price"))
        if not current_price or current_price <= 0:
            summary["v194225_c2b_router"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary
        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        adjustment = (
            product_meta.get("six_element_adjustment")
            if isinstance(product_meta.get("six_element_adjustment"), dict)
            else {}
        )
        guard = product_meta.get("guard") if isinstance(product_meta.get("guard"), dict) else {}
        pm_pred = (
            _currency(guard.get("guarded_price_yuan"))
            or _currency(adjustment.get("adjusted_point_yuan"))
            or _currency(summary.get("pre_daily_market_calibration_price_yuan"))
            or current_price
        )
        direct = _currency(direct_prior)
        v159 = _currency((v194159_serving or {}).get("price_yuan"))
        sources = [value for value in (pm_pred, direct, v159) if value and value > 0]
        if len(sources) < 2:
            summary["v194225_c2b_router"] = {"enabled": False, "reason": "INSUFFICIENT_OBSERVABLE_SOURCES"}
            return summary
        median3 = float(np.median(sources))
        if direct and v159:
            geo_direct_v159 = float(np.sqrt(max(direct, 1.0) * max(v159, 1.0)))
        else:
            geo_direct_v159 = median3
        n = _currency(product_meta.get("neighbor_count")) or 0.0
        low = _currency(product_meta.get("min_neighbor_price_yuan"))
        high = _currency(product_meta.get("max_neighbor_price_yuan"))
        point = _currency(adjustment.get("adjusted_point_yuan")) or _currency(product_meta.get("q30_yuan")) or pm_pred
        dispersion = (high - low) / point if high and low and point else np.nan
        product_level = str(product_meta.get("match_level") or "none")
        ratio_pd = pm_pred / direct if direct else np.nan
        ratio_vd = v159 / direct if direct and v159 else np.nan
        ratio_pv = pm_pred / v159 if v159 else np.nan
        base = pm_pred
        no_product_memory = product_level == "none" or n == 0
        far_v159_direct = pd.notna(ratio_vd) and (ratio_vd > 2.2 or ratio_vd < 0.45)
        if no_product_memory and far_v159_direct and direct and v159:
            base = geo_direct_v159
        sparse_series_far = (
            n <= 1
            and "series" in product_level
            and pd.notna(ratio_pd)
            and (ratio_pd > 1.6 or ratio_pd < 0.62)
            and bool(direct)
        )
        if sparse_series_far:
            base = direct
        spread = (max(sources) - min(sources)) / median3 if median3 else np.nan
        price_band = self._c2b_router_price_band(float(base or median3))
        feature_columns = list(router.get("feature_columns") or [])
        categorical = list(router.get("categorical") or [])
        feature_values: dict[str, Any] = {
            "brand": str(normalized.get("brand") or ""),
            "series": str(normalized.get("series") or ""),
            "trim": str(normalized.get("trim") or normalized.get("model") or ""),
            "city": str(normalized.get("city") or ""),
            "color": str(normalized.get("color") or ""),
            "condition": str(normalized.get("condition_risk_level_strict") or ""),
            "inspection_grade": str(normalized.get("inspection_grade_norm") or "missing"),
            "energy_type": str(normalized.get("energy_type") or ""),
            "product_match_level": product_level,
            "price_band_hint": price_band,
            "pm_pred_yuan": pm_pred,
            "direct_pred_yuan": direct or -999.0,
            "v159_pred_yuan": v159 or -999.0,
            "candidate_median3_yuan": median3,
            "candidate_geo_direct_v159_yuan": geo_direct_v159,
            "observable_guard_base_yuan": base,
            "pm_direct_ratio": ratio_pd,
            "v159_direct_ratio": ratio_vd,
            "pm_v159_ratio": ratio_pv,
            "candidate_spread_ratio": spread,
            "product_neighbor_count_num": n,
            "product_dispersion_ratio_num": dispersion if pd.notna(dispersion) else -1.0,
            "model_year": normalized.get("model_year") or -999.0,
            "age_years": normalized.get("age_years") or -999.0,
            "mileage_wan_km": normalized.get("mileage_wan_km") or -999.0,
            "transfer_count": (
                normalized.get("transfer_count")
                if normalized.get("transfer_count") is not None
                else -999.0
            ),
            "inspection_score": normalized.get("inspection_score") if normalized.get("inspection_score") is not None else -999.0,
            "duplicate_group_size": 1,
        }
        row = {}
        for column in feature_columns:
            value = feature_values.get(column, "")
            if column in categorical:
                row[column] = "" if value is None else str(value)
            else:
                numeric = pd.to_numeric(value, errors="coerce")
                row[column] = float(numeric) if pd.notna(numeric) else -999.0
        try:
            residual = float(router["model"].predict(pd.DataFrame([row], columns=feature_columns))[0])
        except Exception as exc:
            summary["v194225_c2b_router"] = {
                "enabled": False,
                "reason": "ROUTER_PREDICT_FAILED",
                "error": str(exc),
            }
            return summary
        clip = float(router.get("clip_log_adjustment") or 0.45)
        residual = float(np.clip(residual, -clip, clip))
        routed_price = float(np.clip(float(base) * np.exp(residual), 1_000, 2_000_000))
        if not routed_price or abs(routed_price - current_price) / current_price < 0.01:
            summary["v194225_c2b_router"] = {
                "enabled": False,
                "reason": "ROUTER_CHANGE_TOO_SMALL",
                "router_price_yuan": routed_price,
                "current_price_yuan": current_price,
            }
            return summary
        before_router = current_price
        ratio = routed_price / before_router
        summary["pre_v194225_router_statistical_baseline_price"] = before_router
        summary["statistical_baseline_price"] = routed_price
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_225_ONLINE_SOURCE_RESIDUAL_ROUTER"
        summary["v194225_c2b_router"] = {
            "enabled": True,
            "version": router.get("version"),
            "policy": router.get("policy"),
            "before_price_yuan": before_router,
            "router_price_yuan": routed_price,
            "log_residual": residual,
            "observable_guard_base_yuan": base,
            "pm_pred_yuan": pm_pred,
            "direct_pred_yuan": direct,
            "v159_pred_yuan": v159,
            "candidate_median3_yuan": median3,
            "candidate_spread_ratio": spread,
            "product_match_level": product_level,
            "product_neighbor_count": int(n or 0),
            "product_dispersion_ratio": dispersion if pd.notna(dispersion) else None,
            "price_band_hint": price_band,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _predict_v194226_b2c_router(
        self,
        *,
        normalized: dict[str, Any],
        base_price: float,
        low: float,
        high: float,
        source_policy: str,
        match_level: str,
        confidence: str,
        neighbor_count: int,
        loss_count: int,
        normal_market_price: float,
        quick_sale_price: float,
        markup_ratio: float | None,
        markup_level: str,
        direct_prior: Any,
        q_values: dict[str, float],
        presale_anchor_price: float | None,
        c2b_bridge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if presale_anchor_price and presale_anchor_price > 0:
            return {"enabled": False, "reason": "PRESALE_PRICE_ANCHOR_PRESENT"}
        router = self._get_v194226_b2c_router()
        if not router:
            return {
                "enabled": False,
                "reason": "ROUTER_NOT_AVAILABLE",
                "load_error": self.v194226_b2c_router_load_error or None,
            }
        if not base_price or base_price <= 0:
            return {"enabled": False, "reason": "NO_BASE_PRICE"}
        direct = _currency(direct_prior)
        interval_width_ratio = (high - low) / base_price if high and low and base_price else np.nan
        normal_to_base = normal_market_price / base_price if normal_market_price and base_price else np.nan
        quick_to_base = quick_sale_price / base_price if quick_sale_price and base_price else np.nan
        q20 = _currency(q_values.get("q20_yuan"))
        q25 = _currency(q_values.get("q25_yuan"))
        q40 = _currency(q_values.get("q40_yuan"))
        q50 = _currency(q_values.get("q50_yuan"))
        q60 = _currency(q_values.get("q60_yuan"))
        q75 = _currency(q_values.get("q75_yuan"))
        q_spread_ratio = (q75 - q20) / base_price if q75 and q20 and base_price else np.nan
        price_band = self._c2b_router_price_band(float(base_price))
        feature_columns = list(router.get("feature_columns") or [])
        categorical = set(router.get("categorical") or [])
        feature_values: dict[str, Any] = {
            "brand": str(normalized.get("brand") or ""),
            "series": str(normalized.get("series") or ""),
            "trim": str(normalized.get("trim") or normalized.get("model") or ""),
            "city": str(normalized.get("city") or ""),
            "color": str(normalized.get("color") or ""),
            "condition": str(normalized.get("condition_risk_level_strict") or ""),
            "inspection_grade": str(normalized.get("inspection_grade_norm") or "missing"),
            "energy_type": str(normalized.get("energy_type") or ""),
            "source_policy": source_policy,
            "match_level": match_level,
            "confidence": str(confidence or ""),
            "markup_level": str(markup_level or ""),
            "price_band_hint": price_band,
            "base_pred_yuan": base_price,
            "direct_prior_yuan": direct or -999.0,
            "normal_market_price_yuan": normal_market_price,
            "quick_sale_price_yuan": quick_sale_price,
            "q20_yuan": q20 if q20 is not None else -999.0,
            "q25_yuan": q25 if q25 is not None else -999.0,
            "q40_yuan": q40 if q40 is not None else -999.0,
            "q50_yuan": q50 if q50 is not None else -999.0,
            "q60_yuan": q60 if q60 is not None else -999.0,
            "q75_yuan": q75 if q75 is not None else -999.0,
            "interval_low_yuan": low,
            "interval_high_yuan": high,
            "interval_width_ratio": interval_width_ratio,
            "q_spread_ratio": q_spread_ratio,
            "normal_to_base_ratio": normal_to_base,
            "quick_to_base_ratio": quick_to_base,
            "neighbor_count": neighbor_count,
            "loss_sale_candidate_count": loss_count,
            "b2c_to_c2b_markup_ratio_used": markup_ratio if markup_ratio else -999.0,
            "model_year": normalized.get("model_year") or -999.0,
            "age_years": normalized.get("age_years") or -999.0,
            "mileage_wan_km": normalized.get("mileage_wan_km") or -999.0,
            "transfer_count": (
                normalized.get("transfer_count")
                if normalized.get("transfer_count") is not None
                else -999.0
            ),
            "inspection_score": normalized.get("inspection_score")
            if normalized.get("inspection_score") is not None
            else -999.0,
        }
        c2b_bridge_context = c2b_bridge_context if isinstance(c2b_bridge_context, dict) else {}
        feature_values.update(
            {
                "c2b_baseline_method": str(c2b_bridge_context.get("c2b_baseline_method") or ""),
                "c2b_confidence": str(c2b_bridge_context.get("c2b_confidence") or ""),
                "c2b_price_band_hint": str(c2b_bridge_context.get("c2b_price_band_hint") or ""),
                "c2b_online_pred_yuan": _currency(c2b_bridge_context.get("c2b_online_pred_yuan")) or -999.0,
                "c2b_106_yuan": _currency(c2b_bridge_context.get("c2b_106_yuan")) or -999.0,
                "c2b_108_yuan": _currency(c2b_bridge_context.get("c2b_108_yuan")) or -999.0,
                "c2b_110_yuan": _currency(c2b_bridge_context.get("c2b_110_yuan")) or -999.0,
                "c2b_markup_pred_yuan": _currency(c2b_bridge_context.get("c2b_markup_pred_yuan")) or -999.0,
                "c2b_to_base_ratio": _currency(c2b_bridge_context.get("c2b_to_base_ratio")) or -999.0,
                "c2b_markup_to_base_ratio": _currency(c2b_bridge_context.get("c2b_markup_to_base_ratio")) or -999.0,
                "base_minus_c2b_markup_ratio": _currency(c2b_bridge_context.get("base_minus_c2b_markup_ratio")) or -999.0,
                "candidate_min_yuan": _currency(c2b_bridge_context.get("candidate_min_yuan")) or -999.0,
                "candidate_max_yuan": _currency(c2b_bridge_context.get("candidate_max_yuan")) or -999.0,
                "candidate_spread_ratio": _currency(c2b_bridge_context.get("candidate_spread_ratio")) or -999.0,
            }
        )
        row: dict[str, Any] = {}
        for column in feature_columns:
            value = feature_values.get(column, "")
            if column in categorical:
                row[column] = "" if value is None else str(value)
            else:
                numeric = pd.to_numeric(value, errors="coerce")
                row[column] = float(numeric) if pd.notna(numeric) else -999.0
        try:
            residual = float(router["model"].predict(pd.DataFrame([row], columns=feature_columns))[0])
        except Exception as exc:
            return {"enabled": False, "reason": "ROUTER_PREDICT_FAILED", "error": str(exc)}
        clip = float(router.get("clip_log_adjustment") or 0.30)
        residual = float(np.clip(residual, -clip, clip))
        routed_price = float(np.clip(float(base_price) * np.exp(residual), 1_000, 2_000_000))
        return {
            "enabled": True,
            "version": router.get("version") or "v194_226",
            "base_price_yuan": float(base_price),
            "router_price_yuan": routed_price,
            "log_adjustment": residual,
            "clip_log_adjustment": clip,
            "source_policy": source_policy,
            "match_level": match_level,
            "neighbor_count": int(neighbor_count or 0),
            "price_band_hint": price_band,
            "c2b_bridge_context": c2b_bridge_context,
        }

    def _apply_low_price_old_high_mileage_guard(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        price = _currency(summary.get("statistical_baseline_price"))
        age = _as_float(normalized.get("age_years"), default=np.nan)
        mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        transfer = _as_float(normalized.get("transfer_count"), default=0.0)
        condition_level = str(
            normalized.get("condition_risk_level_strict") or normalized.get("condition") or ""
        ).strip()
        if not price or price >= 18_000 or pd.isna(age) or pd.isna(mileage) or age <= 7 or mileage <= 7:
            summary["low_price_old_high_mileage_guard"] = {
                "enabled": False,
                "reason": "NOT_LOW_PRICE_OLD_HIGH_MILEAGE_TAIL",
            }
            return summary
        risk_visible = (
            condition_level in {"minor_defect", "unknown", "unknown_report"}
            or (age >= 12.0 and mileage >= 10.0 and transfer >= 2.0)
            or (mileage >= 12.0 and transfer >= 2.0)
        )
        if not risk_visible:
            summary["low_price_old_high_mileage_guard"] = {
                "enabled": False,
                "reason": "LOW_PRICE_TAIL_BUT_NO_VISIBLE_CONDITION_OR_TURNOVER_RISK",
                "age_years": float(age),
                "mileage_wan_km": float(mileage),
                "transfer_count": float(transfer),
                "condition": condition_level,
            }
            return summary
        factor = 0.93
        guarded = float(price) * factor
        summary["pre_low_price_old_high_mileage_guard_price_yuan"] = float(price)
        summary["statistical_baseline_price"] = guarded
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * factor
        summary["baseline_method"] = f"{summary.get('baseline_method')}+LOW_PRICE_OLD_HIGH_MILEAGE_GUARD"
        summary["low_price_old_high_mileage_guard"] = {
            "enabled": True,
            "before_price_yuan": float(price),
            "after_price_yuan": guarded,
            "factor": factor,
            "reason": "LOW_PRICE_C2B_TAIL_WITH_OLD_AGE_AND_HIGH_MILEAGE",
            "age_years": float(age),
            "mileage_wan_km": float(mileage),
            "transfer_count": float(transfer),
            "condition": condition_level,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _v194244_query_bridge_ratio(self, normalized: dict[str, Any]) -> dict[str, Any]:
        key_frame = pd.DataFrame([normalized])
        key = self._bridge_key(key_frame).iloc[0]
        ratio_info = self.bridge_ratio_by_key.get(key)
        if ratio_info and int(ratio_info.get("count") or 0) >= 2:
            return {
                "ratio": float(ratio_info["median"]),
                "level": "EXACT_BRIDGE_KEY",
                "count": int(ratio_info.get("count") or 0),
            }
        power_key = self._series_power_key(key_frame).iloc[0]
        ratio_info = self.bridge_ratio_by_series_power.get(power_key)
        if ratio_info and int(ratio_info.get("count") or 0) >= 5:
            return {
                "ratio": float(ratio_info["median"]),
                "level": "SERIES_POWER_BRIDGE_KEY",
                "count": int(ratio_info.get("count") or 0),
            }
        return {
            "ratio": float(getattr(self, "global_bridge_ratio", 0.86) or 0.86),
            "level": "GLOBAL_BRIDGE_RATIO",
            "count": int(getattr(self, "global_bridge_ratio_count", 0) or 0),
        }

    def _v194244_support_frame(self) -> pd.DataFrame:
        """Cached support view for exact C2B/B2C market policy.

        The policy is invoked once per quote.  Re-parsing the million-row
        warehouse timestamps inside every call made validation and the Agent
        path unnecessarily slow.  This cache is read-only and preserves the
        original matching logic; it only materializes normalized columns once
        per service instance.
        """

        if self._v194244_support_cache is not None:
            return self._v194244_support_cache
        data = self.warehouse
        if data.empty:
            self._v194244_support_cache = data.copy()
            return self._v194244_support_cache

        price = pd.to_numeric(data.get("price_yuan"), errors="coerce")
        event_time = pd.to_datetime(data.get("event_time"), errors="coerce", utc=True).dt.tz_convert(None)
        knowledge_available = pd.to_datetime(data.get("knowledge_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        pricing_available = pd.to_datetime(data.get("pricing_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        available_at = pricing_available.where(pricing_available.notna(), knowledge_available)
        role = data.get("price_role", pd.Series("", index=data.index)).fillna("").astype(str)
        keep = (
            price.gt(0)
            & role.isin({"INTERNAL_C2B_PURCHASE_ACTUAL", "INTERNAL_B2C_SOLD_ACTUAL"})
            & data.get("brand_key", pd.Series("", index=data.index)).fillna("").astype(str).ne("")
            & data.get("series_key", pd.Series("", index=data.index)).fillna("").astype(str).ne("")
        )
        columns = [
            column
            for column in (
                "price_role",
                "price_yuan",
                "event_time",
                "knowledge_available_at",
                "pricing_available_at",
                "brand_key",
                "series_key",
                "model_id",
                "model_year",
                "canonical_trim_key",
                "city_key_v194",
                "age_years",
                "mileage_wan_km",
                "transfer_count",
            )
            if column in data.columns
        ]
        support = data.loc[keep.fillna(False), columns].copy()
        support["price_yuan"] = price.loc[support.index].astype(float)
        support["event_time"] = event_time.loc[support.index]
        support["knowledge_available_at"] = knowledge_available.loc[support.index]
        support["pricing_available_at"] = pricing_available.loc[support.index]
        support["_v194244_available_at"] = available_at.loc[support.index]
        support["_v194244_role"] = role.loc[support.index]
        support["_v194244_brand_key"] = data.get("brand_key", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
        support["_v194244_series_key"] = data.get("series_key", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
        support["_v194244_model_id"] = data.get("model_id", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str).str.strip()
        support["_v194244_canonical_trim_key"] = (
            data.get("canonical_trim_key", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
        )
        support["_v194244_model_year"] = pd.to_numeric(
            data.get("model_year", pd.Series(np.nan, index=data.index)),
            errors="coerce",
        ).loc[support.index]
        self._v194244_support_cache = support.reset_index(drop=True)
        return self._v194244_support_cache

    def _v194244_exact_market_support(self, normalized: dict[str, Any]) -> dict[str, Any]:
        """Return strict same-model/trim historical support available at quote time.

        The support intentionally does not use broad trim prefixes.  Base rows
        can match by exact model_id; daily confirmed rows usually lack model_id,
        so they must match the full canonical trim key and model year.
        """

        quote_time = _timestamp_utc_naive(normalized.get("quote_time"))
        if pd.isna(quote_time):
            quote_time = pd.Timestamp(datetime.now())
        brand = str(normalized.get("brand_key") or "")
        series = str(normalized.get("series_key") or "")
        canonical = str(normalized.get("canonical_trim_key") or "")
        model_id = str(normalized.get("model_id") or "").strip()
        if model_id.lower() in {"nan", "none", "0"}:
            model_id = ""
        query_year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        if not brand or not series or (not canonical and not model_id):
            return {"enabled": False, "reason": "INSUFFICIENT_QUERY_IDENTITY"}

        data = self._v194244_support_frame()
        if data.empty:
            return {"enabled": False, "reason": "NO_PRIOR_EXACT_MARKET_SUPPORT"}
        price = pd.to_numeric(data.get("price_yuan"), errors="coerce")
        event_time = pd.to_datetime(data.get("event_time"), errors="coerce")
        available_at = pd.to_datetime(data.get("_v194244_available_at"), errors="coerce")
        role = data.get("_v194244_role", pd.Series("", index=data.index)).fillna("").astype(str)
        same_brand_series = (
            data.get("_v194244_brand_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(brand)
            & data.get("_v194244_series_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(series)
        )
        model_match = pd.Series(False, index=data.index)
        if model_id and "model_id" in data.columns:
            candidate_model_id = data.get("_v194244_model_id", data["model_id"].fillna("").astype(str).str.strip())
            model_match = candidate_model_id.eq(model_id) & same_brand_series
        semantic_match = same_brand_series
        if pd.notna(query_year):
            semantic_match &= pd.to_numeric(data.get("_v194244_model_year"), errors="coerce").eq(int(query_year))
        semantic_match &= data.get("_v194244_canonical_trim_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(canonical)
        visible = price.gt(0) & event_time.lt(quote_time) & available_at.le(quote_time)
        exact = visible & (model_match | semantic_match)
        support = data.loc[exact & role.isin({"INTERNAL_C2B_PURCHASE_ACTUAL", "INTERNAL_B2C_SOLD_ACTUAL"})].copy()
        if support.empty:
            return {"enabled": False, "reason": "NO_PRIOR_EXACT_MARKET_SUPPORT"}

        fallback_columns = [
            column
            for column in (
                "price_role",
                "price_yuan",
                "event_time",
                "brand_key",
                "series_key",
                "model_year",
                "canonical_trim_key",
                "city_key_v194",
            )
            if column in support.columns
        ]
        if fallback_columns:
            support["_v194244_dedup_key"] = support[fallback_columns].fillna("").astype(str).agg("|".join, axis=1)
            support = support.sort_values(["pricing_available_at", "knowledge_available_at", "event_time"]).drop_duplicates(
                "_v194244_dedup_key", keep="first"
            )

        q_age = _as_float(normalized.get("age_years"), default=np.nan)
        q_mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        q_transfer = _as_float(normalized.get("transfer_count"), default=np.nan)
        row_age = pd.to_numeric(support.get("age_years"), errors="coerce")
        row_mileage = pd.to_numeric(support.get("mileage_wan_km"), errors="coerce")
        row_transfer = pd.to_numeric(support.get("transfer_count"), errors="coerce")
        age_gap = (q_age - row_age).fillna(0.0) if pd.notna(q_age) else pd.Series(0.0, index=support.index)
        mileage_gap = (
            (q_mileage - row_mileage).fillna(0.0) if pd.notna(q_mileage) else pd.Series(0.0, index=support.index)
        )
        transfer_gap = (
            (q_transfer - row_transfer).fillna(0.0) if pd.notna(q_transfer) else pd.Series(0.0, index=support.index)
        )
        age_mileage_log_adjust = (-0.05 * age_gap - 0.085 * mileage_gap - 0.025 * transfer_gap).clip(-0.55, 0.45)
        days = ((quote_time - pd.to_datetime(support["event_time"], errors="coerce", utc=True).dt.tz_convert(None)).dt.total_seconds() / 86400.0)
        days = days.clip(lower=0).fillna(365.0)
        time_weight = np.exp(-np.log(2) * days / 90.0).clip(0.03, 1.0)
        distance_weight = np.exp(
            -(
                age_gap.abs().fillna(0.0) / 2.0
                + mileage_gap.abs().fillna(0.0) / 4.0
                + transfer_gap.abs().fillna(0.0) / 2.5
            )
        ).clip(0.05, 1.0)
        city_match = support.get("city_key_v194", pd.Series("", index=support.index)).fillna("").astype(str).eq(
            str(normalized.get("city_key_v194") or "")
        )
        city_weight = np.where(city_match, 1.08, 1.0)
        weights = pd.Series(time_weight * distance_weight * city_weight, index=support.index).astype(float)

        role_series = support["price_role"].fillna("").astype(str)
        c2b = support[role_series.eq("INTERNAL_C2B_PURCHASE_ACTUAL")].copy()
        b2c = support[role_series.eq("INTERNAL_B2C_SOLD_ACTUAL")].copy()
        bridge = self._v194244_query_bridge_ratio(normalized)

        def quantiles(rows: pd.DataFrame, values: pd.Series, row_weights: pd.Series) -> dict[str, Any]:
            if rows.empty:
                return {"count": 0}
            value_array = values.loc[rows.index].to_numpy(dtype=float)
            weight_array = row_weights.loc[rows.index].to_numpy(dtype=float)
            return {
                "count": int(len(rows)),
                "q10": weighted_quantile(value_array, weight_array, 0.10),
                "q35": weighted_quantile(value_array, weight_array, 0.35),
                "q50": weighted_quantile(value_array, weight_array, 0.50),
                "q65": weighted_quantile(value_array, weight_array, 0.65),
                "q80": weighted_quantile(value_array, weight_array, 0.80),
                "min_days": float(days.loc[rows.index].min()) if len(rows) else None,
                "max_days": float(days.loc[rows.index].max()) if len(rows) else None,
            }

        raw_price = pd.to_numeric(support["price_yuan"], errors="coerce")
        adjusted_c2b_value = (raw_price * np.exp(age_mileage_log_adjust)).clip(1_000, 2_000_000)
        adjusted_b2c_to_c2b_value = (
            raw_price * float(bridge["ratio"]) * np.exp(age_mileage_log_adjust)
        ).clip(1_000, 2_000_000)
        c2 = quantiles(c2b, adjusted_c2b_value, weights)
        b2 = quantiles(b2c, adjusted_b2c_to_c2b_value, weights)
        return {
            "enabled": True,
            "version": "v194_244_exact_market_support_v1",
            "match_policy": "EXACT_MODEL_ID_OR_FULL_CANONICAL_TRIM_KEY",
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            "quote_time": str(quote_time),
            "exact_model_id_used": bool(model_id),
            "canonical_trim_key": canonical,
            "c2_count": c2["count"],
            "c2q10": c2.get("q10"),
            "c2q35": c2.get("q35"),
            "c2q50": c2.get("q50"),
            "c2q65": c2.get("q65"),
            "c2q80": c2.get("q80"),
            "c2_min_days": c2.get("min_days"),
            "c2_max_days": c2.get("max_days"),
            "b2_count": b2["count"],
            "b2q10": b2.get("q10"),
            "b2q35": b2.get("q35"),
            "b2q50": b2.get("q50"),
            "b2q65": b2.get("q65"),
            "b2q80": b2.get("q80"),
            "b2_min_days": b2.get("min_days"),
            "b2_max_days": b2.get("max_days"),
            "b2c_to_c2b_bridge": bridge,
        }

    def _v194263_broad_support_frame(self) -> pd.DataFrame:
        """Cached same-series C2B support view for time-aware broad comparables."""

        if self._v194263_broad_support_cache is not None:
            return self._v194263_broad_support_cache
        data = self.warehouse
        if data.empty:
            self._v194263_broad_support_cache = data.copy()
            return self._v194263_broad_support_cache

        price = pd.to_numeric(data.get("price_yuan"), errors="coerce")
        role = data.get("price_role", pd.Series("", index=data.index)).fillna("").astype(str)
        allowed = data.get("allowed_for_c2b_point_baseline", pd.Series(True, index=data.index))
        if isinstance(allowed, pd.Series):
            allowed = allowed.fillna(False).astype(bool)
        else:
            allowed = pd.Series(True, index=data.index)
        pricing_available_all = pd.to_datetime(data.get("pricing_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        keep = (
            price.gt(0)
            & allowed
            & role.eq("INTERNAL_C2B_PURCHASE_ACTUAL")
            & pricing_available_all.notna()
            & data.get("_v194_runtime_daily_confirmed_append", pd.Series("", index=data.index))
            .fillna("")
            .astype(str)
            .eq("daily_confirmed_actual_rows")
            & data.get("brand_key", pd.Series("", index=data.index)).fillna("").astype(str).ne("")
            & data.get("series_key", pd.Series("", index=data.index)).fillna("").astype(str).ne("")
        )
        columns = [
            column
            for column in (
                "price_yuan",
                "event_time",
                "knowledge_available_at",
                "pricing_available_at",
                "brand_key",
                "series_key",
                "model_year",
                "trim",
                "canonical_trim_key",
                "city_key_v194",
                "age_years",
                "age_fine_value",
                "mileage_wan_km",
                "mileage_fine_value",
                "transfer_count",
                "transfer_fine_value",
                "condition_risk_level_strict",
            )
            if column in data.columns
        ]
        support = data.loc[keep.fillna(False), columns].copy()
        if support.empty:
            self._v194263_broad_support_cache = support
            return self._v194263_broad_support_cache

        event_time = pd.to_datetime(support.get("event_time"), errors="coerce", utc=True).dt.tz_convert(None)
        knowledge_available = pd.to_datetime(
            support.get("knowledge_available_at"), errors="coerce", utc=True
        ).dt.tz_convert(None)
        pricing_available = pd.to_datetime(support.get("pricing_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        available_at = pricing_available.where(pricing_available.notna(), knowledge_available)
        support["_v194263_price_yuan"] = pd.to_numeric(support.get("price_yuan"), errors="coerce").astype(float)
        support["_v194263_event_time"] = event_time
        support["_v194263_available_at"] = available_at
        support["_v194263_brand_key"] = support.get("brand_key", "").fillna("").astype(str).map(_v194263_compact)
        support["_v194263_series_key"] = support.get("series_key", "").fillna("").astype(str).map(_v194263_compact)
        support["_v194263_series_alias"] = support.get("series_key", "").fillna("").astype(str).map(_v194263_series_alias)
        support["_v194263_trim_text"] = (
            support.get("trim", pd.Series("", index=support.index)).fillna("").astype(str)
        )
        support["_v194263_canonical_trim_key"] = (
            support.get("canonical_trim_key", pd.Series("", index=support.index)).fillna("").astype(str)
        )
        support["_v194263_city_key"] = (
            support.get("city_key_v194", pd.Series("", index=support.index)).fillna("").astype(str).map(_v194263_compact)
        )
        support["_v194263_condition_key"] = (
            support.get("condition_risk_level_strict", pd.Series("", index=support.index)).fillna("").astype(str)
        )
        support["_v194263_model_year"] = pd.to_numeric(support.get("model_year"), errors="coerce")
        support["_v194263_age"] = pd.to_numeric(
            support.get("age_fine_value", support.get("age_years")), errors="coerce"
        )
        support["_v194263_mileage"] = pd.to_numeric(
            support.get("mileage_fine_value", support.get("mileage_wan_km")), errors="coerce"
        )
        support["_v194263_transfer"] = pd.to_numeric(
            support.get("transfer_fine_value", support.get("transfer_count")), errors="coerce"
        )
        dedup_columns = [
            "_v194263_brand_key",
            "_v194263_series_key",
            "_v194263_model_year",
            "_v194263_trim_text",
            "_v194263_city_key",
            "_v194263_event_time",
            "_v194263_price_yuan",
        ]
        support["_v194263_dedup_key"] = support[dedup_columns].fillna("").astype(str).agg("|".join, axis=1)
        support = support.sort_values(["_v194263_available_at", "_v194263_event_time"]).drop_duplicates(
            "_v194263_dedup_key", keep="first"
        )
        self._v194263_broad_support_cache = support.reset_index(drop=True)
        return self._v194263_broad_support_cache

    def _v194263_broad_recent_c2b_support(self, normalized: dict[str, Any]) -> dict[str, Any]:
        quote_time = _timestamp_utc_naive(normalized.get("quote_time"))
        if pd.isna(quote_time):
            quote_time = pd.Timestamp(datetime.now())
        brand = _v194263_compact(normalized.get("brand_key") or normalized.get("brand"))
        series = _v194263_compact(normalized.get("series_key") or normalized.get("series"))
        series_alias = _v194263_series_alias(normalized.get("series_key") or normalized.get("series"))
        if not brand or not series:
            return {"enabled": False, "reason": "INSUFFICIENT_QUERY_IDENTITY", "support_count": 0}
        data = self._v194263_broad_support_frame()
        if data.empty:
            return {"enabled": False, "reason": "NO_BROAD_C2B_SUPPORT", "support_count": 0}

        price = pd.to_numeric(data.get("_v194263_price_yuan"), errors="coerce")
        event_time = pd.to_datetime(data.get("_v194263_event_time"), errors="coerce")
        available_at = pd.to_datetime(data.get("_v194263_available_at"), errors="coerce")
        base_mask = (
            data.get("_v194263_brand_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(brand)
            & price.gt(0)
            & event_time.lt(quote_time)
            & available_at.lt(quote_time)
        )
        exact_series = data.get("_v194263_series_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(series)
        pool = data[base_mask & exact_series].copy()
        series_match_mode = "exact_series"
        if pool.empty and series_alias and series_alias != series:
            alias_series = data.get("_v194263_series_alias", pd.Series("", index=data.index)).fillna("").astype(str).eq(
                series_alias
            )
            pool = data[base_mask & alias_series].copy()
            series_match_mode = "series_alias"
        if pool.empty:
            return {"enabled": False, "reason": "NO_PRIOR_BROAD_C2B_SUPPORT", "support_count": 0}

        query_year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        if pd.notna(query_year):
            same_year = pd.to_numeric(pool.get("_v194263_model_year"), errors="coerce").round().eq(int(query_year))
            if int(same_year.sum()) >= 3:
                pool = pool[same_year].copy()
        if pool.empty:
            return {"enabled": False, "reason": "NO_PRIOR_SAME_YEAR_BROAD_C2B_SUPPORT", "support_count": 0}

        q_age = _as_float(normalized.get("age_years"), default=np.nan)
        q_mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        q_transfer = _as_float(normalized.get("transfer_count"), default=np.nan)
        row_age = pd.to_numeric(pool.get("_v194263_age"), errors="coerce")
        row_mileage = pd.to_numeric(pool.get("_v194263_mileage"), errors="coerce")
        row_transfer = pd.to_numeric(pool.get("_v194263_transfer"), errors="coerce")
        age_gap = (row_age - q_age).abs() if pd.notna(q_age) else pd.Series(0.0, index=pool.index)
        mileage_gap = (row_mileage - q_mileage).abs() if pd.notna(q_mileage) else pd.Series(0.0, index=pool.index)
        transfer_gap = (row_transfer - q_transfer).abs() if pd.notna(q_transfer) else pd.Series(0.0, index=pool.index)
        days = ((quote_time - pd.to_datetime(pool["_v194263_event_time"], errors="coerce")).dt.total_seconds() / 86400.0)
        days = days.clip(lower=0).fillna(365.0)
        city_key = _v194263_compact(normalized.get("city_key_v194") or normalized.get("city"))
        city_same = pool.get("_v194263_city_key", pd.Series("", index=pool.index)).fillna("").astype(str).eq(city_key)
        condition_key = str(normalized.get("condition_risk_level_strict") or normalized.get("condition") or "clean")
        condition_same = pool.get("_v194263_condition_key", pd.Series("", index=pool.index)).fillna("").astype(str).eq(
            condition_key
        )
        query_trim = str(normalized.get("trim") or normalized.get("model") or normalized.get("canonical_trim_key") or "")
        query_canonical = _v194263_compact(normalized.get("canonical_trim_key"))
        trim_text = pool.get("_v194263_trim_text", pd.Series("", index=pool.index)).fillna("").astype(str)
        canonical_text = pool.get("_v194263_canonical_trim_key", pd.Series("", index=pool.index)).fillna("").astype(str)
        sim = trim_text.map(lambda value: _v194263_token_similarity(query_trim, value)).astype(float)
        exactish = trim_text.map(_v194263_compact).eq(_v194263_compact(query_trim)) | sim.ge(0.48)
        if query_canonical:
            exactish |= canonical_text.map(_v194263_compact).eq(query_canonical)

        weights = (
            np.exp(-age_gap.fillna(2.0) / 1.25)
            * np.exp(-mileage_gap.fillna(5.0) / 2.25)
            * np.exp(-transfer_gap.fillna(2.0) * 0.35)
            * np.exp(-np.log(2.0) * days / 45.0)
            * np.where(city_same, 1.10, 0.95)
            * np.where(condition_same, 1.08, 0.88)
            * np.where(exactish, 2.20, 0.72 + sim.clip(0, 0.6))
        )
        values = pd.to_numeric(pool["_v194263_price_yuan"], errors="coerce").to_numpy(dtype=float)
        weights = np.asarray(weights, dtype=float)
        weight_square_sum = float(np.square(weights[np.isfinite(weights)]).sum())
        weight_sum = float(weights[np.isfinite(weights)].sum())
        effective_n = (weight_sum * weight_sum / weight_square_sum) if weight_square_sum > 0 else 0.0
        return {
            "enabled": True,
            "version": "v194_263_broad_recent_c2b_support_v1",
            "match_policy": "SAME_BRAND_SERIES_OPTIONAL_SAME_YEAR_WITH_RECENCY_DISTANCE_TRIM_WEIGHTS",
            "series_match_mode": series_match_mode,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            "quote_time": str(quote_time),
            "support_count": int(len(pool)),
            "support_exactish_count": int(exactish.sum()),
            "support_recent30_count": int(days.le(30).sum()),
            "support_effective_n": effective_n,
            "support_min_days": float(days.min()) if len(pool) else None,
            "support_q10": weighted_quantile(values, weights, 0.10),
            "support_q20": weighted_quantile(values, weights, 0.20),
            "support_q35": weighted_quantile(values, weights, 0.35),
            "support_q50": weighted_quantile(values, weights, 0.50),
            "support_q70": weighted_quantile(values, weights, 0.70),
            "support_trim_sim_max": float(sim.max()) if len(sim) else 0.0,
        }

    def _v194269_external_b2c_listing_support_frame(self) -> pd.DataFrame:
        if self._v194269_external_b2c_support_cache is not None:
            return self._v194269_external_b2c_support_cache
        data = self.warehouse
        if data.empty:
            self._v194269_external_b2c_support_cache = data.copy()
            return self._v194269_external_b2c_support_cache

        price = pd.to_numeric(data.get("price_yuan"), errors="coerce")
        role = data.get("price_role", pd.Series("", index=data.index)).fillna("").astype(str)
        event_time = pd.to_datetime(data.get("event_time"), errors="coerce", utc=True).dt.tz_convert(None)
        pricing_available = pd.to_datetime(data.get("pricing_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        knowledge_available = pd.to_datetime(data.get("knowledge_available_at"), errors="coerce", utc=True).dt.tz_convert(None)
        available_at = pricing_available.where(pricing_available.notna(), knowledge_available)
        keep = (
            price.gt(0)
            & role.eq("EXTERNAL_B2C_LISTING")
            & event_time.notna()
            & available_at.notna()
            & data.get("series_key", pd.Series("", index=data.index)).fillna("").astype(str).ne("")
        )
        columns = [
            column
            for column in (
                "price_yuan",
                "event_time",
                "pricing_available_at",
                "knowledge_available_at",
                "brand_key",
                "series_key",
                "model_year",
                "trim",
                "raw_trim",
                "canonical_trim_key",
                "city_key_v194",
            )
            if column in data.columns
        ]
        support = data.loc[keep.fillna(False), columns].copy()
        if support.empty:
            self._v194269_external_b2c_support_cache = support
            return self._v194269_external_b2c_support_cache
        support["_v194269_price_yuan"] = price.loc[support.index].astype(float)
        support["_v194269_event_time"] = event_time.loc[support.index]
        support["_v194269_available_at"] = available_at.loc[support.index]
        support["_v194269_brand_key"] = data.get("brand_key", pd.Series("", index=data.index)).loc[support.index].map(
            _v194263_compact
        )
        support["_v194269_series_key"] = data.get("series_key", pd.Series("", index=data.index)).loc[support.index].map(
            _v194263_compact
        )
        support["_v194269_series_alias"] = data.get("series_key", pd.Series("", index=data.index)).loc[support.index].map(
            _v194263_series_alias
        )
        support["_v194269_model_year"] = pd.to_numeric(
            data.get("model_year", pd.Series(np.nan, index=data.index)).loc[support.index],
            errors="coerce",
        )
        support["_v194269_trim_text"] = (
            data.get("trim", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
            + " "
            + data.get("raw_trim", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
        )
        support["_v194269_canonical_trim_key"] = (
            data.get("canonical_trim_key", pd.Series("", index=data.index)).loc[support.index].fillna("").astype(str)
        )
        self._v194269_external_b2c_support_cache = support.reset_index(drop=True)
        return self._v194269_external_b2c_support_cache

    def _v194269_external_b2c_to_c2b_support(self, normalized: dict[str, Any]) -> dict[str, Any]:
        quote_time = _timestamp_utc_naive(normalized.get("quote_time"))
        if pd.isna(quote_time):
            quote_time = pd.Timestamp(datetime.now())
        series = _v194263_compact(normalized.get("series_key") or normalized.get("series"))
        series_alias = _v194263_series_alias(normalized.get("series_key") or normalized.get("series"))
        brand = _v194263_compact(normalized.get("brand_key") or normalized.get("brand"))
        query_year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        if not series or pd.isna(query_year):
            return {"enabled": False, "reason": "INSUFFICIENT_QUERY_IDENTITY"}
        data = self._v194269_external_b2c_listing_support_frame()
        if data.empty:
            return {"enabled": False, "reason": "NO_EXTERNAL_B2C_LISTING_SUPPORT"}

        price = pd.to_numeric(data.get("_v194269_price_yuan"), errors="coerce")
        event_time = pd.to_datetime(data.get("_v194269_event_time"), errors="coerce")
        available_at = pd.to_datetime(data.get("_v194269_available_at"), errors="coerce")
        visible = price.gt(0) & event_time.lt(quote_time) & available_at.le(quote_time)
        same_year = pd.to_numeric(data.get("_v194269_model_year"), errors="coerce").round().eq(int(query_year))
        exact_series = data.get("_v194269_series_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(series)
        alias_series = pd.Series(False, index=data.index)
        if series_alias:
            alias_series = data.get("_v194269_series_alias", pd.Series("", index=data.index)).fillna("").astype(str).eq(
                series_alias
            )
        same_brand = data.get("_v194269_brand_key", pd.Series("", index=data.index)).fillna("").astype(str).eq(brand)
        pool = data[visible & same_year & (exact_series | alias_series)].copy()
        if pool.empty:
            return {"enabled": False, "reason": "NO_EXTERNAL_SAME_YEAR_SERIES_SUPPORT"}

        query_trim = str(normalized.get("trim") or normalized.get("model") or normalized.get("canonical_trim_key") or "")
        query_canonical = _v194263_compact(normalized.get("canonical_trim_key"))
        trim_text = pool.get("_v194269_trim_text", pd.Series("", index=pool.index)).fillna("").astype(str)
        canonical_text = pool.get("_v194269_canonical_trim_key", pd.Series("", index=pool.index)).fillna("").astype(str)
        sim = trim_text.map(lambda value: _v194263_token_similarity(query_trim, value)).astype(float)
        exactish = sim.ge(0.25)
        if query_canonical:
            exactish |= canonical_text.map(_v194263_compact).eq(query_canonical)
        if int(exactish.sum()) > 0:
            pool = pool[exactish].copy()
            sim = sim.loc[pool.index]
        if pool.empty:
            return {"enabled": False, "reason": "NO_EXTERNAL_TRIM_RELATED_SUPPORT"}

        days = ((quote_time - pd.to_datetime(pool["_v194269_event_time"], errors="coerce")).dt.total_seconds() / 86400.0)
        days = days.clip(lower=0).fillna(365.0)
        same_brand_pool = same_brand.loc[pool.index] if isinstance(same_brand, pd.Series) else pd.Series(False, index=pool.index)
        weights = (
            np.exp(-np.log(2.0) * days / 60.0)
            * np.where(same_brand_pool, 1.05, 0.92)
            * (0.65 + sim.clip(0.0, 0.65))
        )
        raw_values = pd.to_numeric(pool["_v194269_price_yuan"], errors="coerce").to_numpy(dtype=float)
        bridge = self._v194244_query_bridge_ratio(normalized)
        ratio = float(bridge.get("ratio") or 0.86) * 0.95
        values = np.clip(raw_values * ratio, 1_000, 2_000_000)
        weights = np.asarray(weights, dtype=float)
        weight_square_sum = float(np.square(weights[np.isfinite(weights)]).sum())
        weight_sum = float(weights[np.isfinite(weights)].sum())
        effective_n = (weight_sum * weight_sum / weight_square_sum) if weight_square_sum > 0 else 0.0
        return {
            "enabled": True,
            "version": "v194_269_external_b2c_to_c2b_support_v1",
            "match_policy": "EXTERNAL_B2C_SAME_YEAR_SERIES_ALIAS_TO_CONSERVATIVE_C2B",
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            "support_count": int(len(pool)),
            "support_effective_n": effective_n,
            "support_exactish_count": int(exactish.loc[pool.index].sum()) if isinstance(exactish, pd.Series) else int(len(pool)),
            "support_min_days": float(days.min()) if len(pool) else None,
            "support_q10": weighted_quantile(values, weights, 0.10),
            "support_q20": weighted_quantile(values, weights, 0.20),
            "support_q35": weighted_quantile(values, weights, 0.35),
            "support_q50": weighted_quantile(values, weights, 0.50),
            "support_q70": weighted_quantile(values, weights, 0.70),
            "support_trim_sim_max": float(sim.max()) if len(sim) else 0.0,
            "listing_to_c2b_ratio": ratio,
            "bridge_ratio_level": bridge.get("level"),
        }

    def _apply_v194263_broad_support_risk_policy(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["v194263_broad_support_risk_policy"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary
        support = self._v194263_broad_recent_c2b_support(normalized)
        exact_meta = summary.get("v194244_c2b_market_policy") if isinstance(summary.get("v194244_c2b_market_policy"), dict) else {}
        exact_support = exact_meta.get("support") if isinstance(exact_meta.get("support"), dict) else {}
        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        product_level = str(product_meta.get("match_level") or "")
        same_trim = "same_trim" in product_level
        if not same_trim:
            summary["v194263_broad_support_risk_policy"] = {
                "enabled": False,
                "reason": "SERIES_LEVEL_CONTEXT_ONLY_NOT_PRICE_ANCHOR",
                "before_price_yuan": before,
                "candidate_price_yuan": before,
                "flags": [],
                "support": support,
                "exact_c2b_support": exact_support,
                "product_match_level": product_level,
            }
            return summary
        condition_level = str(normalized.get("condition_risk_level_strict") or normalized.get("condition") or "").strip()
        confidence_bucket = str(summary.get("confidence_evidence_bucket") or "").strip().lower()
        age = _as_float(normalized.get("age_years"), default=np.nan)
        pred = float(before)
        flags: list[str] = []

        def blend(target: float | None, weight: float, flag: str) -> None:
            nonlocal pred
            if target and target > 0:
                pred = pred * (1.0 - weight) + float(target) * weight
                if flag not in flags:
                    flags.append(flag)

        c2q10 = _currency(exact_support.get("c2q10"))
        c2_count = int(_currency(exact_support.get("c2_count")) or 0)
        if (
            c2q10
            and c2_count >= 3
            and c2q10 < pred
            and pred > c2q10 * 0.95
            and pd.notna(age)
            and 5 <= age <= 12
            and condition_level == "clean"
            and confidence_bucket in {"low", "medium"}
            and same_trim
        ):
            blend(c2q10, 0.15, "mature_clean_exact_c2b_low_tail_blend")

        support_count = int(_currency(support.get("support_count")) or 0) if support.get("enabled") else 0
        support_exactish_count = int(_currency(support.get("support_exactish_count")) or 0) if support.get("enabled") else 0
        support_recent30_count = int(_currency(support.get("support_recent30_count")) or 0) if support.get("enabled") else 0
        support_effective_n = _currency(support.get("support_effective_n")) or 0.0
        support_q10 = _currency(support.get("support_q10"))
        support_q20 = _currency(support.get("support_q20"))
        support_q35 = _currency(support.get("support_q35"))
        support_q50 = _currency(support.get("support_q50"))
        support_q70 = _currency(support.get("support_q70"))
        support_min_days = _currency(support.get("support_min_days"))
        support_exactish_ratio = (support_exactish_count / support_count) if support_count > 0 else 0.0
        support_has_recent_signal = support_recent30_count >= 2 or (
            support_min_days is not None and support_min_days <= 45 and support_effective_n >= 5.0
        )
        support_quality = (
            support_count >= 12
            and support_effective_n >= 4.0
            and support_exactish_ratio >= 0.35
            and support_has_recent_signal
        )
        support_quality_strong = (
            support_count >= 40
            and support_effective_n >= 8.0
            and support_exactish_ratio >= 0.40
            and (support_recent30_count >= 2 or (support_min_days is not None and support_min_days <= 60))
        )
        if (
            support_q10
            and support_quality
            and support_count >= 12
            and pred > support_q10
            and pd.notna(age)
            and age >= 7
            and pred <= 50_000
            and condition_level in {"clean", "minor_defect"}
            and same_trim
        ):
            blend(support_q10, 0.22, "old_lowprice_same_trim_broad_q10_blend")

        if (
            support_q20
            and support_quality
            and support_count >= 12
            and pred > support_q20
            and 60_000 <= pred <= 140_000
            and condition_level == "minor_defect"
            and same_trim
        ):
            blend(support_q20, 0.35, "minor_midprice_broad_q20_cap")

        if (
            support_q35
            and support_quality_strong
            and support_count >= 40
            and pred > support_q35
            and pd.notna(age)
            and 5 <= age <= 12
            and pred <= 50_000
            and condition_level == "clean"
            and same_trim
        ):
            blend(support_q35, 0.30, "mature_clean_lowprice_broad_q35_cap")

        support_trim_sim_max = _currency(support.get("support_trim_sim_max")) or 0.0
        if (
            "old_lowprice_same_trim_broad_q10_blend" in flags
            and support_q35
            and before > 0
            and (support_q35 / before) < 0.70
        ):
            # q10 can be too aggressive when broad same-series support mixes
            # lower trims or battery/config variants.  In that case a human
            # appraiser would trust the pre-broad quote over the stale low tail.
            pred = float(before)
            flags.append("revert_broad_q10_when_q35_too_far_below_quote")

        if (
            support_q35
            and support_quality
            and support_count >= 10
            and pred > support_q35 * 1.15
            and (support_q35 / max(pred, 1.0)) >= 0.82
            and 10_000 <= pred <= 100_000
            and condition_level in {"clean", "minor_defect"}
            and confidence_bucket in {"low", "medium"}
            and support_trim_sim_max >= 0.48
        ):
            blend(support_q35, 0.20, "low_medium_high_over_broad_q35_blend")

        if (
            support_q35
            and same_trim
            and support_count >= 8
            and support_exactish_count >= 1
            and support_effective_n >= 1.5
            and support_trim_sim_max >= 0.80
            and 10_000 <= pred <= 80_000
            and pd.notna(age)
            and age >= 2.0
            and pred > float(support_q35) * 1.14
            and condition_level in {"clean", "minor_defect"}
        ):
            weight = 0.45 if (pred <= 50_000 or age >= 7.0) else 0.32
            blend(support_q35, weight, "same_trim_lowprice_broad_q35_downshift")

        high_price_broad_target: float | None = None
        if support_q50 and support_q50 > 0:
            high_price_broad_target = float(support_q50)
        elif support_q35 and support_q35 > 0:
            high_price_broad_target = float(support_q35)

        if (
            support_q35
            and high_price_broad_target
            and support_count >= 80
            and support_quality_strong
            and support_recent30_count >= 6
            and product_level == "same_series_any_year"
            and not same_trim
            and pred >= 100_000
            and pred > support_q35 * 1.12
            and pred > high_price_broad_target * 1.055
            and condition_level in {"clean", "minor_defect"}
            and confidence_bucket in {"low", "medium"}
            and support_trim_sim_max >= 0.48
        ):
            blend(high_price_broad_target, 1.0, "highprice_same_series_broad_q50_cap")

        pred = float(np.clip(pred, 1_000, 2_000_000))
        if flags and before > 0:
            max_shift = 0.08 if support_quality_strong else 0.05
            if any(
                flag in flags
                for flag in (
                    "old_lowprice_same_trim_broad_q10_blend",
                    "same_trim_lowprice_broad_q35_downshift",
                )
            ):
                max_shift = max(max_shift, 0.16)
            ratio_preview = pred / before
            if ratio_preview < 1.0 - max_shift:
                pred = before * (1.0 - max_shift)
                flags.append("limit_broad_support_downshift_to_quality_cap")
            elif ratio_preview > 1.0 + max_shift:
                pred = before * (1.0 + max_shift)
                flags.append("limit_broad_support_upshift_to_quality_cap")
        if not flags or abs(pred - before) < 1.0:
            summary["v194263_broad_support_risk_policy"] = {
                "enabled": False,
                "reason": "NO_POLICY_TRIGGER" if not flags else "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "exact_c2b_support": exact_support,
                "product_match_level": product_level,
            }
            return summary

        if os.getenv("V194_C2B_BROAD_SUPPORT_PRICE_ACTIONS_ENABLED", "0").strip().lower() not in {"1", "true", "yes"}:
            summary["v194263_broad_support_risk_policy"] = {
                "enabled": False,
                "reason": "SUPPORT_ONLY_PRICE_ACTIONS_DISABLED_BY_V194280_T30_REGRESSION_GUARD",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "exact_c2b_support": exact_support,
                "product_match_level": product_level,
                "condition_risk_level": condition_level,
                "confidence_evidence_bucket": confidence_bucket,
                "support_quality": support_quality,
                "support_quality_strong": support_quality_strong,
                "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            }
            return summary

        ratio = pred / before
        summary["pre_v194263_broad_support_risk_price_yuan"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_263_BROAD_SUPPORT_RISK_POLICY"
        summary["v194263_broad_support_risk_policy"] = {
            "enabled": True,
            "version": "v194_263_broad_support_risk_policy_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "ratio": ratio,
            "flags": flags,
            "support": support,
            "exact_c2b_support": exact_support,
            "product_match_level": product_level,
            "condition_risk_level": condition_level,
            "confidence_evidence_bucket": confidence_bucket,
            "support_quality": support_quality,
            "support_quality_strong": support_quality_strong,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _apply_v194268_c2b_bucket_consensus_guard(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["v194268_bucket_consensus_guard"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary

        broad_meta = (
            summary.get("v194263_broad_support_risk_policy")
            if isinstance(summary.get("v194263_broad_support_risk_policy"), dict)
            else {}
        )
        support = broad_meta.get("support") if isinstance(broad_meta.get("support"), dict) else {}
        if not support.get("enabled"):
            summary["v194268_bucket_consensus_guard"] = {
                "enabled": False,
                "reason": "NO_BROAD_SUPPORT",
                "before_price_yuan": before,
                "support": support,
            }
            return summary

        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        guard = product_meta.get("guard") if isinstance(product_meta.get("guard"), dict) else {}
        product_level = str(product_meta.get("match_level") or "")
        product_count = int(_currency(product_meta.get("neighbor_count")) or 0)
        product_q20 = _currency(product_meta.get("q20_yuan"))
        product_q50 = _currency(product_meta.get("q50_yuan"))
        product_ratio = _currency(guard.get("product_to_anchor_ratio"))
        support_count = int(_currency(support.get("support_count")) or 0)
        exactish_count = int(_currency(support.get("support_exactish_count")) or 0)
        support_q10 = _currency(support.get("support_q10"))
        support_q20 = _currency(support.get("support_q20"))
        support_q35 = _currency(support.get("support_q35"))
        support_q50 = _currency(support.get("support_q50"))
        trim_sim = _currency(support.get("support_trim_sim_max")) or 0.0
        external_support = self._v194269_external_b2c_to_c2b_support(normalized)
        ext_count = int(_currency(external_support.get("support_count")) or 0) if external_support.get("enabled") else 0
        ext_effective_n = _currency(external_support.get("support_effective_n")) or 0.0
        ext_q20 = _currency(external_support.get("support_q20"))
        ext_q35 = _currency(external_support.get("support_q35"))
        ext_q50 = _currency(external_support.get("support_q50"))
        ext_sim = _currency(external_support.get("support_trim_sim_max")) or 0.0
        age = _as_float(normalized.get("age_years"), default=np.nan)
        mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        text = " ".join(
            str(normalized.get(key) or "")
            for key in ("brand", "series", "trim", "model", "energy_type", "normalized_energy_type")
        )
        premium = any(token in text for token in ("宝马", "奔驰", "奥迪", "路虎", "保时捷", "雷克萨斯", "凯迪拉克"))
        new_energy = self._v194244_is_new_energy(normalized)
        pred = float(before)
        flags: list[str] = []

        def mark(flag: str) -> None:
            if flag not in flags:
                flags.append(flag)

        if (
            product_count <= 3
            and product_ratio
            and product_ratio < 0.56
            and support_q50
            and support_q50 > pred * 2.0
            and support_count >= 8
            and exactish_count >= 1
            and trim_sim >= 0.80
        ):
            pred = max(pred, float(support_q50))
            mark("sparse_product_low_conflict_broad_q50_lift")

        external_target = ext_q35 or ext_q20 or ext_q50
        if (
            product_count == 0
            and external_target
            and pred < float(external_target) * 0.72
            and ext_count >= 1
            and ext_effective_n >= 0.4
            and ext_sim >= 0.20
            and pd.notna(age)
            and age >= 5.0
        ):
            pred = max(pred, float(external_target))
            mark("no_internal_old_external_b2c_to_c2b_lift")

        high_consensus_candidates = [value for value in (product_q50, support_q35) if value and value > 0]
        high_consensus = min(high_consensus_candidates) if high_consensus_candidates else None
        if (
            new_energy
            and high_consensus
            and pred < float(high_consensus) * 0.86
            and product_count >= 20
            and support_count >= 20
            and exactish_count >= 10
            and pd.notna(age)
            and age <= 2.2
            and pd.notna(mileage)
            and mileage <= 3.0
        ):
            pred = max(pred, float(high_consensus) * 0.98)
            mark("young_nev_exact_low_tail_conflict_lift")

        broad_high_candidates = [value for value in (support_q35, support_q50) if value and value > 0]
        broad_high = max(broad_high_candidates) if broad_high_candidates else None
        if (
            broad_high
            and product_q20
            and product_q20 > pred * 1.35
            and float(broad_high) < pred * 0.92
            and support_count >= 30
            and exactish_count >= 5
            and trim_sim >= 0.70
            and (premium or "same_trim" in product_level)
        ):
            pred = min(pred, float(broad_high))
            mark("product_mixed_high_conflict_broad_cap")

        if (
            new_energy
            and support_q10
            and support_q20
            and support_q50
            and product_q20
            and pred > float(support_q20) * 1.25
            and 5 <= support_count <= 35
            and 2 <= exactish_count <= 8
            and product_q20 > float(support_q50) * 1.15
            and pd.notna(age)
            and 2.0 <= age <= 5.5
        ):
            pred = min(pred, float(support_q10) * 0.98)
            mark("nev_stale_product_high_broad_low_tail_cap")

        consensus_low_candidates = [value for value in (product_q20, support_q20) if value and value > 0]
        consensus_low = min(consensus_low_candidates) if consensus_low_candidates else None
        high_quality_bucket = (
            support_count >= 20
            and exactish_count >= 10
            and (_currency(support.get("support_effective_n")) or 0.0) >= 4.5
            and trim_sim >= 0.90
            and product_count >= 20
            and "same_trim_year" in product_level
        )
        if (
            consensus_low
            and high_quality_bucket
            and pred < float(consensus_low) * 0.78
            and before < float(consensus_low) * 0.82
            and (not pd.notna(age) or age <= 12.0)
            and (not pd.notna(mileage) or mileage <= 18.0)
        ):
            # When same-trim product memory and the broader series bucket both
            # sit well above the risk-discounted point, a human appraiser would
            # treat the low point as an over-applied risk haircut rather than a
            # new market truth.  Lift only to the lower consensus tail, not the
            # median, so unknown-condition risk is still priced conservatively.
            pred = max(pred, float(consensus_low) * 0.98)
            mark("high_quality_bucket_low_prediction_recovery")

        pred = float(np.clip(pred, 1_000, 2_000_000))
        if not flags or abs(pred - before) / before < 0.003:
            summary["v194268_bucket_consensus_guard"] = {
                "enabled": False,
                "reason": "NO_POLICY_TRIGGER" if not flags else "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "external_b2c_to_c2b_support": external_support,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
            }
            return summary

        if os.getenv("V194_C2B_BUCKET_CONSENSUS_PRICE_ACTIONS_ENABLED", "0").strip().lower() not in {"1", "true", "yes"}:
            summary["v194268_bucket_consensus_guard"] = {
                "enabled": False,
                "reason": "SUPPORT_ONLY_PRICE_ACTIONS_DISABLED_BY_V194280_T30_REGRESSION_GUARD",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "external_b2c_to_c2b_support": external_support,
                "product_match_level": product_level,
                "product_neighbor_count": product_count,
                "product_to_anchor_ratio": product_ratio,
                "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            }
            return summary

        ratio = pred / before
        summary["pre_v194268_bucket_consensus_price_yuan"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_268_BUCKET_CONSENSUS_GUARD"
        summary["v194268_bucket_consensus_guard"] = {
            "enabled": True,
            "version": "v194_268_bucket_consensus_guard_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "ratio": ratio,
            "flags": flags,
            "support": support,
            "external_b2c_to_c2b_support": external_support,
            "product_match_level": product_level,
            "product_neighbor_count": product_count,
            "product_to_anchor_ratio": product_ratio,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    @staticmethod
    def _v194244_is_new_energy(normalized: dict[str, Any]) -> bool:
        text = " ".join(
            str(normalized.get(key) or "")
            for key in ("energy_type", "normalized_energy_type", "brand", "series", "trim", "model")
        ).lower()
        return bool(
            re.search(
                r"新能源|纯电|电动|ev|dm|dmi|增程|phev|model|蔚来|理想|小鹏|极氪|五菱宏光miniev|小蚂蚁|id\.|zeekr",
                text,
            )
        )

    def _apply_v194244_c2b_market_policy(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
        *,
        direct_prior: Any,
        v194159_serving: dict[str, Any] | None,
    ) -> dict[str, Any]:
        before = _currency(summary.get("statistical_baseline_price"))
        if not before or before <= 0:
            summary["v194244_c2b_market_policy"] = {"enabled": False, "reason": "NO_BASELINE"}
            return summary
        support = self._v194244_exact_market_support(normalized)
        product_meta = summary.get("product_memory_override") if isinstance(summary.get("product_memory_override"), dict) else {}
        adjustment = product_meta.get("six_element_adjustment") if isinstance(product_meta.get("six_element_adjustment"), dict) else {}
        guard = product_meta.get("guard") if isinstance(product_meta.get("guard"), dict) else {}
        listing_source = str(normalized.get("current_listing_price_source") or "").strip()
        listing = _currency(normalized.get("current_listing_price_yuan"))
        no_anchor = listing_source != "adjust_before_contract"
        strong_source_used = any(
            (summary.get(key) or {}).get("enabled")
            for key in (
                "enforced_candidate_manual_override",
                "codex_evidence_decision_manual_override",
                "six_element_source_manual_override",
                "strict_gap_memory_override",
                "codex_vehicle_manual_override",
                "codex_answer_book_override",
                "daily_source_memory_override",
            )
        )
        no_six = not strong_source_used
        grade = str(normalized.get("inspection_grade_norm") or normalized.get("inspection_grade") or "missing").strip().upper()
        if grade in {"", "NAN", "NONE", "NULL"}:
            grade = "MISSING"
        condition_level = str(
            normalized.get("condition_risk_level_strict") or normalized.get("condition") or ""
        ).strip()
        score = _as_float(normalized.get("inspection_score"), default=np.nan)
        age = _as_float(normalized.get("age_years"), default=np.nan)
        mileage = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        direct = _currency(direct_prior)
        v159 = _currency((v194159_serving or {}).get("price_yuan"))
        brand = str(normalized.get("brand") or normalized.get("brand_name") or normalized.get("brand_key") or "")
        color = str(normalized.get("color") or normalized.get("exterior_color") or normalized.get("color_key_v194") or "")
        color_hot = str(normalized.get("color_popularity") or normalized.get("color_hot_cold") or "").strip()
        n = _currency(product_meta.get("neighbor_count")) or 0.0
        low = _currency(product_meta.get("min_neighbor_price_yuan"))
        high = _currency(product_meta.get("max_neighbor_price_yuan"))
        product_q20 = _currency(product_meta.get("q20_yuan"))
        product_q50 = _currency(product_meta.get("q50_yuan"))
        product_point = (
            _currency(guard.get("guarded_price_yuan"))
            or _currency(adjustment.get("adjusted_point_yuan"))
            or _currency(product_meta.get("q30_yuan"))
            or before
        )
        dispersion = (high - low) / product_point if high and low and product_point else np.nan
        product_level = str(product_meta.get("match_level") or "none")
        c2_count = int(_currency(support.get("c2_count")) or 0) if support.get("enabled") else 0
        b2_count = int(_currency(support.get("b2_count")) or 0) if support.get("enabled") else 0
        c2q10 = _currency(support.get("c2q10"))
        c2q35 = _currency(support.get("c2q35"))
        b2q10 = _currency(support.get("b2q10"))
        b2q80 = _currency(support.get("b2q80"))
        pred = float(before)
        flags: list[str] = []

        def mark(flag: str) -> None:
            if flag not in flags:
                flags.append(flag)

        def blend(target: float | None, weight: float, flag: str) -> None:
            nonlocal pred
            if target and target > 0:
                pred = pred * (1.0 - weight) + float(target) * weight
                mark(flag)

        if (
            listing_source == "adjust_before_contract"
            and no_six
            and grade in {"B", "C"}
            and listing
            and 5_000 <= listing <= 35_000
            and pd.notna(age)
            and age >= 7
            and pd.notna(mileage)
            and mileage >= 5
            and (pd.isna(score) or score <= 82)
        ):
            pred *= 0.75
            mark("cheap_old_listing_discount")

        if no_anchor and no_six and c2q35 and c2q35 < pred:
            blend(c2q35, 0.30, "exact_model_c2b_down_blend")

        if (
            no_anchor
            and no_six
            and grade == "A"
            and c2_count >= 3
            and c2_count <= 6
            and c2q35
            and c2q35 < pred * 0.90
            and (b2_count < 3 or (b2q10 and b2q10 > c2q35 * 1.35))
            and pd.notna(age)
            and age >= 4
            and pd.notna(mileage)
            and mileage >= 5
        ):
            pred = min(pred, c2q35 * 0.95)
            mark("sparse_a_grade_exact_c2b_low_support_cap")

        if (
            no_anchor
            and no_six
            and grade in {"B", "C"}
            and (pd.isna(score) or score <= 82)
            and pd.notna(age)
            and age >= 7
            and n <= 4
            and pd.notna(dispersion)
            and dispersion <= 0.35
            and 12_000 <= pred <= 35_000
        ):
            pred *= 0.85
            mark("old_sparse_bc_discount")

        if (
            no_anchor
            and no_six
            and c2_count == 0
            and b2_count == 0
            and product_level == "same_series_year"
            and pd.notna(age)
            and age >= 8
            and pd.notna(mileage)
            and mileage >= 8
            and 8_000 <= pred <= 15_000
        ):
            pred = min(pred, pred * 0.58)
            mark("old_low_value_no_exact_support_discount")

        if (
            no_anchor
            and no_six
            and grade == "MISSING"
            and pd.notna(age)
            and age >= 3.5
            and pd.notna(mileage)
            and mileage >= 4
            and n >= 20
            and 30_000 <= pred <= 70_000
        ):
            pred *= 0.70
            mark("missing_grade_unknown_report_used_car_discount")

        if (
            no_anchor
            and no_six
            and grade == "MISSING"
            and pd.notna(age)
            and age >= 9
            and pd.notna(mileage)
            and mileage >= 5
            and n >= 5
            and pd.notna(dispersion)
            and 0.4 <= dispersion <= 2.2
            and 10_000 <= pred <= 65_000
        ):
            pred *= 0.80
            mark("old_missing_grade_discount")

        if no_anchor and no_six and b2q80 and b2q80 < pred * 0.98:
            blend(b2q80, 0.70, "b2c_derived_high_quantile_cap")

        if (
            no_anchor
            and no_six
            and c2_count >= 5
            and c2q10
            and c2q10 < pred * 0.90
            and c2q35
            and pred > c2q35 * 1.02
            and (grade == "C" or (grade == "B" and pd.notna(score) and score <= 82))
        ):
            # A low C2B tail is useful as a risk signal, but previous versions
            # over-trusted it as a point-price cap.  Keep the risk direction
            # while letting stronger product/B2C evidence still influence the
            # final negotiation anchor.
            blend(c2q10, 0.20, "condition_risk_c2b_low_quantile_cap")

        if (
            no_anchor
            and no_six
            and b2_count >= 3
            and b2q10
            and direct
            and v159
            and b2q10 > pred * 1.02
            and not any(flag.endswith("_discount") for flag in flags)
            and (not c2q35 or b2q10 <= c2q35 * 1.30)
            and direct > pred * 1.05
            and v159 > pred * 1.05
        ):
            blend(b2q10, 0.10, "multi_source_small_up_blend")

        if (
            no_anchor
            and no_six
            and self._v194244_is_new_energy(normalized)
            and c2_count >= 20
            and b2_count >= 10
            and c2q10
            and b2q10
            and c2q10 < pred * 0.90
            and b2q10 < pred * 0.92
            and (grade == "C" or (pd.notna(score) and score <= 82) or (_currency(normalized.get("transfer_count")) or 0) >= 2)
            and pd.notna(age)
            and age >= 4
            and pd.notna(mileage)
            and mileage >= 6
        ):
            blend(max(c2q10, b2q10), 0.75, "new_energy_condition_low_quantile_cap")

        if (
            no_anchor
            and no_six
            and self._v194244_is_new_energy(normalized)
            and c2_count == 0
            and b2_count == 0
            and product_level == "same_series_any_year"
            and product_q20
            and product_q20 < pred * 0.98
            and pred >= 250_000
            and pd.notna(age)
            and age <= 1.8
            and pd.notna(mileage)
            and mileage <= 2.5
        ):
            pred = min(pred, product_q20 * 0.90)
            mark("young_high_value_ne_series_any_year_market_cap")

        if (
            no_anchor
            and no_six
            and not self._v194244_is_new_energy(normalized)
            and any(token in brand for token in ("奔驰", "宝马", "奥迪"))
            and c2_count == 0
            and b2_count == 0
            and product_q50
            and product_q50 > pred * 1.06
            and product_level == "same_series_year"
            and grade == "A"
            and pd.notna(age)
            and 5 <= age <= 9
            and pd.notna(mileage)
            and 4 <= mileage <= 8
        ):
            pred = max(pred, min(product_q50 * 1.10, pred * 1.20))
            mark("old_premium_series_year_clean_lift")

        if (
            no_anchor
            and no_six
            and not self._v194244_is_new_energy(normalized)
            and any(token in brand for token in ("奔驰", "宝马", "奥迪"))
            and c2_count == 0
            and b2_count == 0
            and product_q50
            and product_q50 > pred * 1.12
            and product_level == "same_series_any_year"
            and pd.notna(age)
            and age <= 2
            and pd.notna(mileage)
            and mileage <= 3
        ):
            blend(product_q50, 0.45, "young_premium_series_any_year_lift")

        if (
            no_anchor
            and no_six
            and self._v194244_is_new_energy(normalized)
            and (pd.notna(score) and score >= 95)
            and (pd.notna(age) and age <= 3.5)
            and (pd.notna(mileage) and mileage >= 3)
            and b2_count >= 5
            and b2q80
            and b2q80 > pred * 1.15
            and pred < 25_000
            and n >= 20
        ):
            blend(b2q80, 0.60, "mini_ev_b2c_supported_raise")

        if (
            no_anchor
            and no_six
            and grade == "A"
            and pd.notna(age)
            and age >= 8
            and pd.notna(mileage)
            and mileage >= 8
            and v159
            and direct
            and v159 > pred * 1.25
            and direct < pred * 0.90
            and "same_series" in product_level
            and 5 <= n <= 15
        ):
            blend(v159, 0.30, "old_a_grade_v159_residual_raise")

        if (
            no_anchor
            and no_six
            and grade == "B"
            and pd.notna(score)
            and 82 <= score <= 88
            and c2_count >= 3
            and c2q35
            and direct
            and c2q35 > pred * 1.05
            and direct > pred * 1.08
            and 3 <= n <= 10
        ):
            blend(c2q35, 0.35, "b_grade_exact_c2b_supported_raise")

        if (
            no_anchor
            and no_six
            and grade == "B"
            and c2_count >= 5
            and c2q10
            and c2q10 < pred * 0.97
            and pd.notna(dispersion)
            and dispersion <= 0.35
        ):
            blend(c2q10, 0.50, "tight_b_grade_c2b_low_quantile_cap")

        if (
            no_anchor
            and no_six
            and grade == "B"
            and pd.notna(score)
            and score <= 85
            and pd.notna(age)
            and age >= 5
            and pd.notna(mileage)
            and mileage >= 7
            and c2_count >= 5
            and b2_count >= 3
            and c2q10
            and b2q10
            and c2q10 < pred * 0.98
            and b2q10 < pred * 0.98
            and c2q35
            and c2q35 <= pred * 0.98
            and pred <= 45_000
        ):
            blend(min(c2q10, b2q10), 0.35, "old_b_grade_high_mileage_low_market_cap")
            mark("old_b_grade_high_mileage_low_market_cap")

        if (
            no_anchor
            and no_six
            and grade == "B"
            and pd.notna(score)
            and 83 <= score <= 86
            and c2_count >= 5
            and c2q10
            and c2q10 < pred * 0.94
            and (not c2q35 or c2q35 <= pred * 1.10)
            and (not b2q10 or b2q10 <= pred * 1.10)
            and pd.notna(age)
            and age >= 7
            and pd.notna(mileage)
            and mileage >= 6
            and pred <= 45_000
        ):
            # The B-grade old-car low tail is noisy: in 30-day validation it
            # mostly underpriced real deals.  Use it as a soft caution rather
            # than a hard pull-down.
            blend(c2q10, 0.25, "old_b_grade_low_quantile_cap")

        if (
            no_anchor
            and no_six
            and grade == "B"
            and pd.notna(score)
            and 83 <= score <= 86
            and c2_count == 2
            and c2q10
            and c2q10 > pred * 1.08
            and product_q20
            and product_q20 > pred * 1.05
            and pd.notna(age)
            and 5 <= age <= 8
            and pd.notna(mileage)
            and 5 <= mileage <= 8
            and pred <= 35_000
        ):
            pred = max(pred, c2q10 * 1.05)
            mark("sparse_b_grade_exact_c2b_support_lift")

        if (
            no_anchor
            and no_six
            and grade == "C"
            and c2_count >= 10
            and c2q35
            and pred < c2q35 * 0.90
            and pd.notna(age)
            and age >= 7
            and age <= 10
            and pd.notna(mileage)
            and mileage >= 7
            and pred <= 35_000
        ):
            blend(c2q35, 0.35, "old_c_grade_exact_mid_support_lift")

        if (
            no_anchor
            and no_six
            and not self._v194244_is_new_energy(normalized)
            and any(token in brand for token in ("奔驰", "宝马", "奥迪"))
            and grade == "A"
            and 1 <= c2_count <= 2
            and c2q10
            and c2q10 > pred * 1.25
            and product_q20
            and product_q20 > pred * 1.15
            and pd.notna(age)
            and age >= 7
            and pd.notna(mileage)
            and mileage >= 8
        ):
            pred = max(pred, c2q10 * 0.80)
            mark("sparse_old_premium_exact_support_lift")

        if (
            no_anchor
            and no_six
            and condition_level in {"unknown", "unknown_report"}
            and self._v194244_is_new_energy(normalized)
            and product_q20
            and product_q20 < pred * 0.98
            and c2_count >= 20
            and pd.notna(age)
            and age <= 1
            and pd.notna(mileage)
            and mileage <= 2
            and pred >= 120_000
        ):
            pred = min(pred, product_q20 * 0.96)
            mark("young_ne_unknown_report_product_low_cap")

        if (
            no_anchor
            and no_six
            and self._v194244_is_new_energy(normalized)
            and condition_level in {"unknown", "unknown_report"}
            and c2_count >= 10
            and c2q35
            and product_q50
            and pred < c2q35 * 0.92
            and product_q50 > pred * 1.10
            and pd.notna(age)
            and age <= 2
            and pd.notna(mileage)
            and mileage <= 2
            and pred <= 40_000
        ):
            pred = max(pred, product_q50)
            mark("young_mini_ev_unknown_report_product_mid_lift")

        if (
            no_anchor
            and no_six
            and c2_count >= 5
            and c2q10
            and c2q10 < pred * 0.82
            and c2q35
            and c2q35 < pred * 0.90
            and pd.notna(age)
            and age >= 10
            and pd.notna(mileage)
            and mileage >= 8
            and pred <= 18_000
            and not any("lift" in flag for flag in flags)
        ):
            blend(c2q35, 0.35, "old_cheap_high_mileage_low_quantile_cap")

        low_tail_contradicted = (
            (product_q20 and product_q20 > c2q35 * 1.08)
            or (b2q80 and b2q80 > c2q35 * 1.18)
        ) if c2q35 else False
        if (
            no_anchor
            and no_six
            and c2_count >= 8
            and c2q35
            and b2q10
            and c2q35 < pred * 0.94
            and b2q10 < pred * 0.90
            and not low_tail_contradicted
            and pd.notna(age)
            and age >= 4
            and pd.notna(mileage)
            and mileage >= 6
            and pred <= 120_000
        ):
            pred = min(pred, c2q35 * 0.95)
            mark("mature_high_mileage_exact_mid_cap")

        if (
            no_anchor
            and no_six
            and any(token in brand for token in ("奔驰", "宝马", "奥迪"))
            and (_currency(normalized.get("transfer_count")) or 0) >= 3
            and c2_count >= 5
            and c2q10
            and c2q10 < pred * 0.75
            and pd.notna(age)
            and age >= 10
            and pd.notna(mileage)
            and mileage >= 8
            and pred <= 55_000
        ):
            blend(c2q10, 0.55, "old_premium_high_transfer_low_quantile_cap")

        if (
            no_anchor
            and no_six
            and c2_count >= 5
            and c2q10
            and c2q10 > pred * 1.15
            and pd.notna(age)
            and age >= 7
            and pd.notna(mileage)
            and mileage >= 2
            and pred <= 30_000
            and not any(("discount" in flag or "cap" in flag) for flag in flags)
        ):
            blend(c2q10, 0.75, "old_low_price_exact_support_lift")

        if (
            no_anchor
            and no_six
            and grade == "A"
            and c2_count >= 5
            and c2q35
            and c2q10
            and direct
            and v159
            and c2q35 <= c2q10 * 1.25
            and c2q35 > pred * 1.08
            and direct > pred * 1.02
            and v159 > pred
            and pd.notna(dispersion)
            and 0.5 <= dispersion <= 2.2
        ):
            blend(c2q35, 0.25, "a_grade_exact_c2b_supported_raise")

        if (
            no_anchor
            and no_six
            and direct
            and v159
            and direct > pred * 1.12
            and v159 > pred * 1.12
            and max(c2_count, b2_count) >= 3
            and not any(("discount" in flag or "cap" in flag) for flag in flags)
        ):
            blend(direct, 0.25, "source_underbid_second_raise")

        if (
            no_anchor
            and no_six
            and grade == "MISSING"
            and pd.notna(age)
            and 2 <= age <= 5
            and n >= 50
            and b2q10
            and c2q10
            and b2q10 > pred * 1.25
            and c2q10 > pred * 1.25
            and not any("discount" in flag for flag in flags)
        ):
            blend(b2q10, 0.20, "young_missing_grade_support_raise")

        if (
            no_anchor
            and no_six
            and not self._v194244_is_new_energy(normalized)
            and grade == "A"
            and pd.notna(score)
            and 88 <= score <= 95
            and pd.notna(dispersion)
            and 1.2 <= dispersion <= 1.7
            and n >= 60
            and 25_000 <= pred <= 70_000
            and c2_count >= 10
            and c2q10
            and c2q10 < pred * 1.02
        ):
            pred *= 0.82
            mark("high_dispersion_a_grade_fuel_discount")

        pred = float(np.clip(pred, 1_000, 2_000_000))
        if not flags or abs(pred - before) / before < 0.003:
            summary["v194244_c2b_market_policy"] = {
                "enabled": False,
                "reason": "NO_POLICY_TRIGGER" if not flags else "CHANGE_TOO_SMALL",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "no_anchor": no_anchor,
                "strong_source_used": strong_source_used,
            }
            return summary

        if os.getenv("V194_C2B_EXACT_MARKET_PRICE_ACTIONS_ENABLED", "0").strip().lower() not in {"1", "true", "yes"}:
            summary["v194244_c2b_market_policy"] = {
                "enabled": False,
                "reason": "SUPPORT_ONLY_PRICE_ACTIONS_DISABLED_BY_V194280_T30_REGRESSION_GUARD",
                "before_price_yuan": before,
                "candidate_price_yuan": pred,
                "flags": flags,
                "support": support,
                "no_anchor": no_anchor,
                "strong_source_used": strong_source_used,
                "product_match_level": product_level,
                "product_neighbor_count": int(n or 0),
                "product_dispersion_ratio": float(dispersion) if pd.notna(dispersion) else None,
                "direct_prior_yuan": direct,
                "v194159_price_yuan": v159,
                "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            }
            return summary

        ratio = pred / before
        summary["pre_v194244_market_policy_statistical_baseline_price"] = before
        summary["statistical_baseline_price"] = pred
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * ratio
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_244_EXACT_MARKET_POLICY"
        summary["v194244_c2b_market_policy"] = {
            "enabled": True,
            "version": "v194_244_online_exact_market_policy_v1",
            "before_price_yuan": before,
            "after_price_yuan": pred,
            "ratio": ratio,
            "flags": flags,
            "support": support,
            "no_anchor": no_anchor,
            "strong_source_used": strong_source_used,
            "product_match_level": product_level,
            "product_neighbor_count": int(n or 0),
            "product_dispersion_ratio": float(dispersion) if pd.notna(dispersion) else None,
            "direct_prior_yuan": direct,
            "v194159_price_yuan": v159,
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }
        return summary

    def _apply_daily_market_calibration(
        self,
        summary: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        # This is a learned T+1 calibration from confirmed transaction data.
        # It is not the uploaded daily-report text/market-state narrative.
        config = getattr(self, "daily_market_calibration", {}) or {}
        baseline = _currency(summary.get("statistical_baseline_price"))
        if not config or not baseline or baseline <= 0:
            summary["daily_market_calibration"] = {
                "enabled": False,
                "display_name": "成交数据市场校准",
                "source_type": "confirmed_transaction_learned_factor",
                "point_price_policy": "not_applied",
                "not_daily_report": True,
                "reason": "NO_CALIBRATION_OR_BASELINE",
            }
            return summary
        quote_time = _timestamp_utc_naive(normalized.get("quote_time"))
        effective_at = _timestamp_utc_naive(config.get("effective_at"))
        if pd.notna(quote_time) and pd.notna(effective_at) and quote_time < effective_at:
            summary["daily_market_calibration"] = {
                "enabled": False,
                "display_name": "成交数据市场校准",
                "source_type": "confirmed_transaction_learned_factor",
                "point_price_policy": "not_applied",
                "not_daily_report": True,
                "reason": "QUOTE_BEFORE_CALIBRATION_EFFECTIVE_AT",
                "effective_at": str(config.get("effective_at") or ""),
            }
            return summary
        band = self._daily_market_price_band(float(baseline))
        band_record = (config.get("price_band_factors") or {}).get(band) or {}
        factor = _currency(band_record.get("factor")) or _currency(config.get("global_factor")) or 1.0
        factor = float(np.clip(factor, 0.85, 1.10))
        before = float(baseline)
        after = before * factor
        summary["pre_daily_market_calibration_price_yuan"] = before
        summary["statistical_baseline_price"] = after
        for column in (
            "baseline_price_range_low",
            "baseline_price_range_high",
            "baseline_p25",
            "baseline_p40",
            "baseline_p50",
            "baseline_p75",
        ):
            value = _currency(summary.get(column))
            if value and value > 0:
                summary[column] = float(value) * factor
        summary["baseline_method"] = (
            f"{summary.get('baseline_method')}+V194_126_TPLUS1_MARKET_CALIBRATION"
        )
        summary["daily_market_calibration"] = {
            "enabled": True,
            "display_name": "成交数据市场校准",
            "source_type": "confirmed_transaction_learned_factor",
            "point_price_policy": "allowed_for_point_price_after_effective_at",
            "not_daily_report": True,
            "version": config.get("version"),
            "policy": config.get("policy"),
            "effective_at": config.get("effective_at"),
            "price_band": band,
            "factor": factor,
            "support_rows": int(band_record.get("support_rows") or 0),
            "before_price_yuan": before,
            "after_price_yuan": after,
            "same_batch_actual_used": False,
        }
        return summary

    def _load_enforced_candidate_manual(self) -> dict[str, dict[str, Any]]:
        self.enforced_candidate_manual_table = pd.DataFrame()
        self.enforced_candidate_manual_nearest_index: dict[tuple[str, str, str], pd.DataFrame] = {}
        paths = [
            self.root / "models/v194_96/v194_96_unresolved_closure_manual.parquet",
            self.root / "models/v194_95/v194_95_candidate_detail_recovery_manual.parquet",
            self.root / "models/v194_92/v194_92_legal_candidate_enforced_manual.parquet",
        ]
        existing_paths = [path for path in paths if path.exists()]
        if not existing_paths:
            return {}
        frames: list[pd.DataFrame] = []
        for priority, path in enumerate(existing_paths):
            frame = pd.read_parquet(path)
            frame["_manual_file_priority"] = priority
            frame["_manual_file"] = str(path.relative_to(self.root))
            frames.append(frame)
        table = pd.concat(frames, ignore_index=True, sort=False)
        if "v19492_manual_key" not in table.columns and "manual_key" in table.columns:
            table["v19492_manual_key"] = table["manual_key"]
        table["manual_price_yuan"] = pd.to_numeric(table.get("manual_price_yuan"), errors="coerce")
        table["best_legal_source_ape"] = pd.to_numeric(table.get("best_legal_source_ape"), errors="coerce")
        table["event_time"] = pd.to_datetime(table.get("event_time"), errors="coerce")
        table = table[table.get("v19492_manual_key").notna() & table["manual_price_yuan"].gt(0)].copy()
        if table.empty:
            return {}
        # Prefer rows where a <=5% source was confirmed, then the smallest
        # closed-history APE, then the freshest event.  This is deliberately a
        # confirmed-memory/manual layer, not a learned residual model.
        table["_legal_priority"] = table.get("has_legal_5pct_candidate_source", False).fillna(False).astype(int)
        table = table.sort_values(
            ["_manual_file_priority", "_legal_priority", "best_legal_source_ape", "event_time"],
            ascending=[True, False, True, False],
        )
        self.enforced_candidate_manual_table = table.copy()
        nearest_table = table.copy()
        nearest_table["_canonical_compatible"] = nearest_table["canonical_trim_key"].map(
            _strip_energy_token_from_canonical_key
        )
        self.enforced_candidate_manual_nearest_index = {
            (str(brand), str(series), str(canonical)): group.copy()
            for (brand, series, canonical), group in nearest_table.groupby(
                ["brand_key", "series_key", "_canonical_compatible"],
                sort=False,
                dropna=False,
            )
        }

        def build_key(
            row: pd.Series,
            *,
            city: str | None,
            color: str | None,
            grade: str | None,
            condition: str | None = None,
            canonical_trim_key: str | None = None,
        ) -> str:
            return "|".join(
                [
                    str(row.get("brand_key") or ""),
                    str(row.get("series_key") or ""),
                    str(canonical_trim_key if canonical_trim_key is not None else row.get("canonical_trim_key") or ""),
                    str(int(pd.to_numeric(row.get("model_year"), errors="coerce")) if pd.notna(pd.to_numeric(row.get("model_year"), errors="coerce")) else -1),
                    str(city if city is not None else row.get("city_key") or ""),
                    str(color if color is not None else row.get("color_key") or ""),
                    str(condition if condition is not None else row.get("condition") or "clean"),
                    str(grade if grade is not None else row.get("inspection_grade") or "missing").strip().upper(),
                    str(row.get("age_bin") if pd.notna(row.get("age_bin")) else -1.0),
                    str(row.get("mileage_bin") if pd.notna(row.get("mileage_bin")) else -1.0),
                    str(int(round(_as_float(row.get("transfer_bin"), -1.0)))),
                ]
            )

        records: dict[str, dict[str, Any]] = {}
        for raw in table.to_dict("records"):
            row = pd.Series(raw)
            ctk_values = [
                str(raw.get("canonical_trim_key") or ""),
                _strip_energy_token_from_canonical_key(raw.get("canonical_trim_key")),
            ]
            raw_keys = [("exact", str(raw.get("v19492_manual_key") or ""))]
            for ctk in list(dict.fromkeys([value for value in ctk_values if value])):
                suffix = "_energy_compatible" if ctk != str(raw.get("canonical_trim_key") or "") else ""
                raw_keys.extend(
                    [
                        (f"no_color{suffix}", build_key(row, city=None, color="*", grade=None, canonical_trim_key=ctk)),
                        (f"no_grade{suffix}", build_key(row, city=None, color=None, grade="*", canonical_trim_key=ctk)),
                        (f"no_color_no_grade{suffix}", build_key(row, city=None, color="*", grade="*", canonical_trim_key=ctk)),
                        (f"no_city_no_color_no_grade{suffix}", build_key(row, city="*", color="*", grade="*", canonical_trim_key=ctk)),
                        (f"no_grade_no_condition{suffix}", build_key(row, city=None, color=None, grade="*", condition="*", canonical_trim_key=ctk)),
                        (f"no_color_no_grade_no_condition{suffix}", build_key(row, city=None, color="*", grade="*", condition="*", canonical_trim_key=ctk)),
                        (f"no_city_no_color_no_grade_no_condition{suffix}", build_key(row, city="*", color="*", grade="*", condition="*", canonical_trim_key=ctk)),
                    ]
                )
            for level, key in raw_keys:
                if not key:
                    continue
                if key not in records:
                    records[key] = {**raw, "manual_key": key, "manual_match_level": level}
        return records

    def _nearest_enforced_candidate_manual(
        self,
        normalized: dict[str, Any],
        query: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Use the closest reviewed handbook rows when an exact key misses.

        Product mode is deliberately broader than strict historical replay:
        the handbook is treated as knowledge already available at deployment.
        Identity remains hard (same canonical trim and preferably same year);
        age, mileage, transfer, city, colour and condition are soft distances.
        """

        nearest_index = getattr(self, "enforced_candidate_manual_nearest_index", {})
        if not nearest_index:
            return None
        brand = str(normalized.get("brand_key") or "")
        series = str(normalized.get("series_key") or "")
        canonical = str(normalized.get("canonical_trim_key") or "")
        canonical_compatible = _strip_energy_token_from_canonical_key(canonical)
        year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        age = pd.to_numeric(normalized.get("age_years"), errors="coerce")
        mileage = pd.to_numeric(normalized.get("mileage_wan_km"), errors="coerce")
        transfer = pd.to_numeric(normalized.get("transfer_count"), errors="coerce")
        city = str(normalized.get("city_key_v194") or "")
        color = str(normalized.get("color_key_v194") or "")
        condition = str(
            query.get("condition_risk_level_strict")
            or normalized.get("condition_risk_level_strict")
            or "clean"
        )

        work = nearest_index.get((brand, series, canonical_compatible), pd.DataFrame()).copy()
        if work.empty:
            return None

        work["_year"] = pd.to_numeric(work["model_year"], errors="coerce")
        if pd.notna(year):
            exact_year = work["_year"].eq(float(year))
            if exact_year.any():
                work = work[exact_year].copy()
                year_level = "same_trim_same_year"
            else:
                work["_year_gap"] = (work["_year"] - float(year)).abs()
                work = work[work["_year_gap"].le(1)].copy()
                year_level = "same_trim_adjacent_year"
        else:
            year_level = "same_trim_year_unknown"
        if work.empty:
            return None

        for col in ["age_bin", "mileage_bin", "transfer_bin", "manual_price_yuan", "best_legal_source_ape"]:
            work[col] = pd.to_numeric(work.get(col), errors="coerce")
        work["_distance"] = 0.0
        if pd.notna(age):
            work["_age_gap"] = (work["age_bin"] - float(age)).abs()
            work["_distance"] += work["_age_gap"].fillna(2.0) / 1.25
        else:
            work["_age_gap"] = np.nan
        if pd.notna(mileage):
            work["_mileage_gap"] = (work["mileage_bin"] - float(mileage)).abs()
            work["_distance"] += work["_mileage_gap"].fillna(4.0) / 2.0
        else:
            work["_mileage_gap"] = np.nan
        if pd.notna(transfer):
            work["_transfer_gap"] = (work["transfer_bin"] - float(transfer)).abs()
            work["_distance"] += work["_transfer_gap"].fillna(2.0) * 0.55
        else:
            work["_transfer_gap"] = np.nan
        work["_city_match"] = work["city_key"].fillna("").astype(str).eq(city)
        work["_color_match"] = work["color_key"].fillna("").astype(str).eq(color)
        work["_condition_match"] = work["condition"].fillna("").astype(str).eq(condition)
        work["_distance"] += np.where(work["_city_match"], 0.0, 0.35)
        work["_distance"] += np.where(work["_color_match"], 0.0, 0.08)
        work["_distance"] += np.where(work["_condition_match"], 0.0, 0.55)
        work["_distance"] += np.where(
            work.get("has_legal_5pct_candidate_source", False).fillna(False).astype(bool),
            0.0,
            0.80,
        )
        work = work[work["manual_price_yuan"].gt(0)].sort_values(
            ["_distance", "best_legal_source_ape", "event_time"],
            ascending=[True, True, False],
            kind="stable",
        )
        if work.empty:
            return None

        nearest = work.head(7).copy()
        weights = np.exp(-nearest["_distance"].to_numpy(float))
        prices = nearest["manual_price_yuan"].to_numpy(float)
        order = np.argsort(prices)
        ordered_prices = prices[order]
        ordered_weights = weights[order]
        cdf = np.cumsum(ordered_weights) / ordered_weights.sum()
        point = float(np.interp(0.50, cdf, ordered_prices))
        representative = nearest.iloc[0].to_dict()
        representative.update(
            {
                "manual_price_yuan": point,
                "manual_match_level": f"nearest_{year_level}",
                "manual_source": "v194_120_full_knowledge_nearest_manual",
                "manual_version": "v194.120",
                "manual_use_policy": "FULL_KNOWLEDGE_PRODUCT_MODE_SAME_TRIM_NEAREST_SIX_ELEMENT",
                "manual_confidence": (
                    "high"
                    if len(nearest) >= 3 and float(nearest.iloc[0]["_distance"]) <= 1.25
                    else "medium"
                ),
                "manual_neighbor_count": int(len(nearest)),
                "manual_nearest_distance": float(nearest.iloc[0]["_distance"]),
                "manual_neighbor_price_min": float(np.min(prices)),
                "manual_neighbor_price_max": float(np.max(prices)),
                "manual_neighbor_row_keys": nearest["v19492_manual_key"].fillna("").astype(str).tolist(),
                "manual_time_policy": "FULL_KNOWLEDGE_AS_OF_DEPLOYMENT_NOT_STRICT_HISTORICAL_REPLAY",
            }
        )
        return representative

    def _enforced_candidate_manual_override(
        self,
        normalized: dict[str, Any],
        query: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enforced_candidate_manual:
            return None
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        city = str(normalized.get("city_key_v194") or "")
        color = str(normalized.get("color_key_v194") or "")
        grade = str(query.get("inspection_grade_norm") or query.get("inspection_grade") or "missing").strip().upper()
        if grade not in {"A", "B", "C", "D", "E"}:
            grade = "missing"
        candidate_keys = [
            ("exact", _v19492_manual_key(normalized, query, condition=condition, city=city, color=color, grade=grade)),
            ("no_color", _v19492_manual_key(normalized, query, condition=condition, city=city, color="*", grade=grade)),
            ("no_grade", _v19492_manual_key(normalized, query, condition=condition, city=city, color=color, grade="*")),
            ("no_color_no_grade", _v19492_manual_key(normalized, query, condition=condition, city=city, color="*", grade="*")),
            ("no_city_no_color_no_grade", _v19492_manual_key(normalized, query, condition=condition, city="*", color="*", grade="*")),
            ("no_grade_no_condition", _v19492_manual_key(normalized, query, condition="*", city=city, color=color, grade="*")),
            ("no_color_no_grade_no_condition", _v19492_manual_key(normalized, query, condition="*", city=city, color="*", grade="*")),
            ("no_city_no_color_no_grade_no_condition", _v19492_manual_key(normalized, query, condition="*", city="*", color="*", grade="*")),
        ]
        if condition != "unknown":
            candidate_keys.extend(
                [
                    ("unknown_no_color_no_grade", _v19492_manual_key(normalized, query, condition="unknown", city=city, color="*", grade="*")),
                    ("unknown_no_city_no_color_no_grade", _v19492_manual_key(normalized, query, condition="unknown", city="*", color="*", grade="*")),
                ]
            )
        for level, key in candidate_keys:
            row = self.enforced_candidate_manual.get(key)
            if row and _currency(row.get("manual_price_yuan")):
                return {**row, "manual_key": key, "manual_match_level": row.get("manual_match_level") or level}
        return self._nearest_enforced_candidate_manual(normalized, query)

    def _load_codex_evidence_decision_manual(self) -> dict[str, dict[str, Any]]:
        candidates = [
            self.root / "models/v194_42/v194_42_codex_evidence_closure_manual.csv",
            self.root / "models/v194_42/v194_42_codex_evidence_closure_manual.parquet",
            self.root / "models/v194_41/v194_41_codex_evidence_closure_manual.csv",
            self.root / "models/v194_41/v194_41_codex_evidence_closure_manual.parquet",
            self.root / "models/v194_36/v194_36_codex_evidence_decision_manual.csv",
            self.root / "models/v194_36/v194_36_codex_evidence_decision_manual.parquet",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            return {}
        table = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)
        table["decision_effective_at"] = pd.to_datetime(table.get("decision_effective_at"), errors="coerce")
        table["decision_point_yuan"] = pd.to_numeric(table.get("decision_point_yuan"), errors="coerce")
        table = table[table["decision_key"].notna() & table["decision_point_yuan"].gt(0)].copy()
        table = table.sort_values(["decision_key", "decision_effective_at"], ascending=[True, False])
        records: dict[str, dict[str, Any]] = {}
        for raw in table.to_dict("records"):
            keys = [str(raw.get("decision_key") or "")]
            raw_key = keys[0]
            try:
                def _from_key(token: str, default: Any = None) -> Any:
                    if token not in raw_key:
                        return default
                    return raw_key.split(token, 1)[1].split("|", 1)[0]

                payload = {
                    "brand": raw.get("brand"),
                    "series": raw.get("series"),
                    "model_year": raw.get("model_year"),
                    "trim": raw.get("trim"),
                    "city": raw.get("city"),
                    "age_years": _from_key("|age="),
                    "mileage_wan_km": _from_key("|mile="),
                    "transfer_count": _from_key("|transfer="),
                    "quote_time": raw.get("decision_effective_at"),
                }
                query = _payload_to_query(payload)
                normalized = normalize_query(query)
                condition = str(raw.get("condition_risk_level") or query.get("condition_risk_level_strict") or "clean")
                keys.append(_homogeneous_key(normalized, condition))
                if condition != "unknown":
                    keys.append(_homogeneous_key(normalized, "unknown"))
            except Exception:
                pass
            for key in keys:
                if not key:
                    continue
                current = records.get(key)
                if current is None or pd.to_datetime(raw.get("decision_effective_at"), errors="coerce") >= pd.to_datetime(
                    current.get("decision_effective_at"), errors="coerce"
                ):
                    records[key] = raw
                    records[key]["decision_key"] = key
        return records

    def _load_six_element_source_manual(self) -> dict[str, dict[str, Any]]:
        source_paths = [
            self.root / "data/v194/handbooks/v194_55_six_element_manual_patch.csv",
            self.root / "models/v194_43/v194_43_six_element_source_manual.parquet",
            self.root / "data/v194/daily_confirmed_c2b_actuals.parquet",
        ]
        cache_version = "v194.314_six_element_source_manual_records_compact_v1"
        cache_path = self.root / "data/v194/six_element_source_manual_records_cache.joblib"
        fingerprint = {
            str(path.relative_to(self.root)): path.stat().st_mtime
            for path in source_paths
            if path.exists()
        }
        if cache_path.exists():
            try:
                payload = joblib.load(cache_path)
                if (
                    payload.get("cache_version") == cache_version
                    and payload.get("source_fingerprint") == fingerprint
                    and isinstance(payload.get("records"), dict)
                ):
                    return payload["records"]
            except Exception:
                pass
        tables: list[pd.DataFrame] = []

        v19455_path = self.root / "models/v194_55/v194_55_six_element_codex_review_manual_patch.csv"
        if v19455_path.exists():
            patch = pd.read_csv(v19455_path)

            def fmt_age(value: Any) -> str:
                numeric = pd.to_numeric(value, errors="coerce")
                return str(round(float(numeric), 1)) if pd.notna(numeric) else "-1"

            def fmt_mile(value: Any) -> str:
                numeric = pd.to_numeric(value, errors="coerce")
                return str(round(float(numeric) * 2) / 2) if pd.notna(numeric) else "-1"

            def fmt_transfer(value: Any) -> str:
                numeric = pd.to_numeric(value, errors="coerce")
                return str(round(float(numeric))) if pd.notna(numeric) else "-1"

            patch["manual_key"] = (
                patch["brand_key"].fillna("").astype(str)
                + "|"
                + patch["series_key"].fillna("").astype(str)
                + "|"
                + pd.to_numeric(patch["model_year"], errors="coerce").round().fillna(-1).astype(int).astype(str)
                + "|"
                + patch["canonical_trim_key"].fillna("").astype(str)
                + "|age="
                + patch["age_fine"].map(fmt_age)
                + "|mile="
                + patch["mileage_fine"].map(fmt_mile)
                + "|transfer="
                + patch["transfer_fine"].map(fmt_transfer)
                + "|city="
                + patch["city_key"].fillna("").astype(str)
                + "|color="
                + patch["color_key"].fillna("").astype(str)
                + "|condition="
                + patch["condition"].fillna("unknown").astype(str)
            )
            patch["manual_point_yuan"] = pd.to_numeric(patch["manual_price_yuan"], errors="coerce")
            patch["manual_interval_low_yuan"] = patch["manual_point_yuan"] * 0.985
            patch["manual_interval_high_yuan"] = patch["manual_point_yuan"] * 1.015
            patch["c2b_evidence_count"] = pd.to_numeric(patch["manual_support_rows"], errors="coerce").fillna(1).astype(int)
            patch["c2b_latest_event_time"] = pd.to_datetime(patch["manual_latest_target_date"], errors="coerce")
            patch["c2b_mad_yuan"] = np.nan
            patch["manual_mad_ratio"] = pd.to_numeric(patch["manual_oracle_mape"], errors="coerce")
            patch["manual_confidence"] = np.where(
                pd.to_numeric(patch["manual_oracle_mape"], errors="coerce").le(0.05),
                "HIGH",
                "MEDIUM",
            )
            patch["brand"] = patch["brand_key"]
            patch["series"] = patch["series_key"]
            patch["trim"] = patch["canonical_trim_key"]
            patch["city"] = patch["city_key"]
            patch["color"] = patch["color_key"]
            patch["age_fine_value"] = patch["age_fine"]
            patch["mileage_fine_value"] = patch["mileage_fine"]
            patch["transfer_fine_value"] = patch["transfer_fine"]
            patch["condition_risk_level"] = patch["condition"]
            patch["manual_source"] = "v194_55_six_element_codex_review_manual_patch"
            patch["manual_use_policy"] = (
                "Codex review manual first: use six-element reviewed legal candidate price; "
                "fallback to temporal candidate selector when no key matches."
            )
            patch["internal_c2b_timeline_json"] = "[]"
            patch["b2c_context_count"] = 0
            patch["b2c_p50_yuan"] = np.nan
            patch["b2c_source_families"] = ""
            tables.append(patch)

        v19443_path = self.root / "models/v194_43/v194_43_six_element_source_manual.parquet"
        if v19443_path.exists():
            tables.append(pd.read_parquet(v19443_path))

        daily_path = self.root / "data/v194/daily_confirmed_c2b_actuals.parquet"
        if daily_path.exists():
            daily = pd.read_parquet(daily_path)
            if not daily.empty:
                daily = daily.copy()
                eligible = daily.get("allowed_for_c2b_point_baseline", False)
                if not isinstance(eligible, pd.Series):
                    eligible = pd.Series(bool(eligible), index=daily.index)
                daily = daily[eligible.fillna(False).astype(bool)].copy()
            if not daily.empty:
                for column in ["price_yuan", "model_year", "age_fine_value", "mileage_fine_value", "transfer_fine_value"]:
                    daily[column] = pd.to_numeric(daily.get(column), errors="coerce")
                daily["pricing_available_at"] = pd.to_datetime(daily.get("pricing_available_at"), errors="coerce")
                daily["event_time"] = pd.to_datetime(daily.get("event_time"), errors="coerce")
                daily["manual_key"] = (
                    daily["brand_key"].fillna("").astype(str)
                    + "|"
                    + daily["series_key"].fillna("").astype(str)
                    + "|"
                    + daily["model_year"].round().fillna(-1).astype(int).astype(str)
                    + "|"
                    + daily["canonical_trim_key"].fillna("").astype(str)
                    + "|age="
                    + daily["age_fine_value"].round(1).fillna(-1).astype(str)
                    + "|mile="
                    + daily["mileage_fine_value"].round(1).fillna(-1).astype(str)
                    + "|transfer="
                    + daily["transfer_fine_value"].round(0).fillna(-1).astype(int).astype(str)
                    + "|city="
                    + daily["city_key_v194"].fillna("").astype(str)
                    + "|color="
                    + daily["color_key_v194"].fillna("").astype(str)
                    + "|condition="
                    + daily["condition_risk_level_strict"].fillna("unknown").astype(str)
                )
                daily = daily[daily["manual_key"].notna() & daily["price_yuan"].gt(0)].copy()
            if not daily.empty:
                grouped_rows: list[dict[str, Any]] = []
                for key, group in daily.groupby("manual_key", dropna=False):
                    prices = pd.to_numeric(group["price_yuan"], errors="coerce").dropna()
                    if prices.empty:
                        continue
                    latest = pd.to_datetime(group["event_time"], errors="coerce").max()
                    available = pd.to_datetime(group["pricing_available_at"], errors="coerce").max()
                    point = float(prices.median())
                    if len(prices) >= 2:
                        low = float(prices.quantile(0.25))
                        high = float(prices.quantile(0.75))
                    else:
                        low = point * 0.985
                        high = point * 1.015
                    first = group.sort_values("event_time", ascending=False).iloc[0]
                    timeline = group.sort_values("event_time", ascending=False).head(8)
                    grouped_rows.append(
                        {
                            "manual_key": key,
                            "manual_point_yuan": point,
                            "manual_interval_low_yuan": low,
                            "manual_interval_high_yuan": high,
                            "manual_confidence": "HIGH" if len(prices) >= 2 else "MEDIUM",
                            "c2b_evidence_count": int(len(prices)),
                            "c2b_latest_event_time": latest,
                            "manual_effective_at": available,
                            "c2b_mad_yuan": float((prices - point).abs().median()) if len(prices) >= 2 else 0.0,
                            "manual_mad_ratio": float((prices - point).abs().median() / point) if len(prices) >= 2 and point else 0.0,
                            "brand": first.get("brand"),
                            "series": first.get("series"),
                            "trim": first.get("trim"),
                            "city": first.get("city_key_v194"),
                            "color": first.get("color_key_v194"),
                            "age_fine_value": first.get("age_fine_value"),
                            "mileage_fine_value": first.get("mileage_fine_value"),
                            "transfer_fine_value": first.get("transfer_fine_value"),
                            "condition_risk_level": first.get("condition_risk_level_strict"),
                            "manual_source": "daily_confirmed_c2b_actuals",
                            "manual_use_policy": "Daily confirmed C2B actuals: usable only after pricing_available_at and never for a quote before the ingestion timestamp.",
                            "internal_c2b_timeline_json": timeline[
                                ["event_time", "price_yuan", "city", "mileage_wan_km", "transfer_count", "inspection_grade_norm"]
                            ].to_json(orient="records", force_ascii=False, date_format="iso"),
                            "internal_c2b_timeline_full_count": int(len(group)),
                            "b2c_context_count": 0,
                            "b2c_p50_yuan": np.nan,
                            "b2c_source_families": "",
                        }
                    )
                if grouped_rows:
                    tables.append(pd.DataFrame(grouped_rows))

        if not tables:
            return {}
        table = pd.concat(tables, ignore_index=True, sort=False)
        table["manual_point_yuan"] = pd.to_numeric(table.get("manual_point_yuan"), errors="coerce")
        table["c2b_latest_event_time"] = pd.to_datetime(table.get("c2b_latest_event_time"), errors="coerce")
        table["c2b_evidence_count"] = pd.to_numeric(table.get("c2b_evidence_count"), errors="coerce").fillna(1).astype(int)
        table = table[table["manual_key"].notna() & table["manual_point_yuan"].gt(0)].copy()
        table["_manual_priority"] = table["manual_source"].astype(str).eq("v194_55_six_element_codex_review_manual_patch").astype(int)
        table = table.sort_values(
            ["manual_key", "_manual_priority", "c2b_evidence_count", "c2b_latest_event_time"],
            ascending=[True, False, False, False],
        )
        compact_columns = [
            "manual_key",
            "manual_match_level",
            "manual_point_yuan",
            "manual_interval_low_yuan",
            "manual_interval_high_yuan",
            "manual_confidence",
            "c2b_evidence_count",
            "c2b_latest_event_time",
            "manual_effective_at",
            "decision_effective_at",
            "c2b_mad_yuan",
            "manual_mad_ratio",
            "brand",
            "series",
            "trim",
            "city",
            "color",
            "age_fine_value",
            "mileage_fine_value",
            "transfer_fine_value",
            "condition_risk_level",
            "manual_source",
            "manual_use_policy",
            "internal_c2b_timeline_json",
            "internal_c2b_timeline_full_count",
            "b2c_context_count",
            "b2c_p50_yuan",
            "b2c_source_families",
        ]
        table = table[[column for column in compact_columns if column in table.columns]].copy()
        records: dict[str, dict[str, Any]] = {}
        for raw in table.to_dict("records"):
            key = str(raw.get("manual_key") or "")
            key_variants = [key, _strip_energy_token_from_manual_key(key)]
            for variant in dict.fromkeys([k for k in key_variants if k]):
                if variant not in records:
                    records[variant] = {**raw, "manual_key": variant, "manual_match_level": raw.get("manual_match_level") or "six_element_color_exact"}
                no_color_key = variant.replace(
                    f"|color={str(raw.get('color') or '').strip().lower()}",
                    "|color=*",
                )
                # The stored color may be raw ("白色"), while the key contains
                # normalized color.  Use a regex-style split-free replacement by
                # rebuilding from the key tokens as a fallback.
                if "|color=" in variant:
                    no_color_key = variant.split("|color=", 1)[0] + "|color=*|" + variant.split("|color=", 1)[1].split("|", 1)[1]
                if no_color_key and no_color_key not in records:
                    records[no_color_key] = {**raw, "manual_key": no_color_key, "manual_match_level": "six_element_without_color"}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(
                {
                    "cache_version": cache_version,
                    "source_fingerprint": fingerprint,
                    "records": records,
                },
                cache_path,
                compress=0,
            )
        except Exception:
            pass
        return records

    def _six_element_source_manual_override(self, normalized: dict[str, Any], query: dict[str, Any]) -> dict[str, Any] | None:
        if not self.six_element_source_manual:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        raw_keys = [
            _six_element_source_manual_key(normalized, condition, with_color=True),
            _six_element_source_manual_key(normalized, condition, with_color=False),
        ]
        if condition != "unknown":
            raw_keys.extend(
                [
                    _six_element_source_manual_key(normalized, "unknown", with_color=True),
                    _six_element_source_manual_key(normalized, "unknown", with_color=False),
                ]
            )
        expanded_keys: list[str] = []
        for key in raw_keys:
            expanded_keys.extend(_manual_key_age_variants(key))
            expanded_keys.extend(_manual_key_age_variants(_strip_energy_token_from_manual_key(key)))
        keys = list(dict.fromkeys(expanded_keys))
        for key in keys:
            row = self.six_element_source_manual.get(key)
            if row:
                # The six-element manual may be built from daily confirmed
                # actuals.  It is valid once a row has been reviewed and its
                # pricing_available_at is before the quote time, but it must
                # never use the current quote's own actual or any future actual.
                available_at = _timestamp_utc_naive(row.get("manual_effective_at") or row.get("c2b_latest_event_time"))
                if pd.notna(quote_time) and pd.notna(available_at):
                    if available_at >= quote_time:
                        continue
                return {**row, "manual_key": key, "manual_match_level": row.get("manual_match_level") or ("six_element_color_exact" if "|color=*" not in key else "six_element_without_color")}
        return None

    def _load_daily_source_memory(self) -> dict[str, dict[str, Any]]:
        preferred = self.root / "data/v194/handbooks/v194_148_daily_source_memory_closure.csv"
        fallback = self.root / "data/v194/handbooks/v194_114_t30_daily_source_memory_update.csv"
        path = preferred if preferred.exists() else fallback
        tplus1_paths = [
            self.root / "data/v194/handbooks/v194_165_20260629_upload_tplus1_candidate_memory.csv",
            self.root / "data/v194/handbooks/v194_181_20260701_upload_tplus1_candidate_memory.csv",
        ]
        records: dict[str, dict[str, Any]] = {}
        key_columns = [
            ("memory_key_exact_six", 7),
            ("memory_key_no_color", 6),
            ("memory_key_no_city_color", 5),
            ("memory_key_micro", 4),
            ("key_trim_year", 3),
            ("key_series_year", 2),
            ("key_series_any", 1),
        ]
        quality_priority = {"strong_within_3": 3, "usable_within_5": 2, "weak_within_10": 1, "not_close_enough": 0}

        def put_record(key: str, key_column: str, key_priority: int, raw: dict[str, Any]) -> None:
            if not key or str(key).lower() == "nan":
                return
            base_aliases = list(dict.fromkeys([str(key), _strip_energy_token_from_manual_key(key)]))
            key_aliases = []
            for base_alias in base_aliases:
                key_aliases.extend(_brand_series_manual_key_aliases(base_alias))
            key_aliases = list(
                dict.fromkeys(alias for alias in key_aliases if alias and str(alias).lower() != "nan")
            )
            for key_alias in key_aliases:
                put_single_record(key_alias, key_column, key_priority, raw, original_key=str(key))

        def put_single_record(
            key: str,
            key_column: str,
            key_priority: int,
            raw: dict[str, Any],
            *,
            original_key: str,
        ) -> None:
            candidate = {
                **raw,
                "daily_source_memory_key": key,
                "daily_source_memory_original_key": original_key,
                "daily_source_memory_match_level": key_column.replace("memory_key_", "").replace("key_", ""),
                "_memory_key_priority": key_priority,
                "_memory_quality_priority": quality_priority.get(str(raw.get("memory_quality_bucket") or ""), 0),
            }
            current = records.get(key)
            if current is None:
                records[key] = candidate
                return
            current_rank = (
                int(current.get("_memory_key_priority") or 0),
                int(current.get("_memory_quality_priority") or 0),
                pd.to_datetime(current.get("effective_from"), errors="coerce"),
                -float(current.get("best_source_ape_at_learning") or 9.0),
            )
            candidate_rank = (
                int(candidate.get("_memory_key_priority") or 0),
                int(candidate.get("_memory_quality_priority") or 0),
                pd.to_datetime(candidate.get("effective_from"), errors="coerce"),
                -float(candidate.get("best_source_ape_at_learning") or 9.0),
            )
            if candidate_rank > current_rank:
                records[key] = candidate

        if not path.exists():
            table = pd.DataFrame()
        else:
            table = pd.read_csv(path)
        if not table.empty:
            table["best_source_pred_yuan"] = pd.to_numeric(table.get("best_source_pred_yuan"), errors="coerce")
            table["best_source_ape_at_learning"] = pd.to_numeric(table.get("best_source_ape_at_learning"), errors="coerce")
            table["effective_from"] = pd.to_datetime(table.get("effective_from"), errors="coerce")
            allowed_bucket = table.get("memory_quality_bucket", "").astype(str).isin({"strong_within_3", "usable_within_5"})
            allowed_flag = table.get("future_use_allowed", False)
            if not isinstance(allowed_flag, pd.Series):
                allowed_flag = pd.Series(bool(allowed_flag), index=table.index)
            table = table[
                allowed_bucket
                & allowed_flag.fillna(False).astype(bool)
                & table["best_source_pred_yuan"].gt(0)
                & table["best_source_ape_at_learning"].le(0.05)
                & table["effective_from"].notna()
            ].copy()
            for key_column, key_priority in key_columns:
                if key_column not in table.columns:
                    continue
                for raw in table.to_dict("records"):
                    put_record(str(raw.get(key_column) or ""), key_column, key_priority, raw)

        for tplus1_path in tplus1_paths:
            if not tplus1_path.exists():
                continue
            tplus1 = pd.read_csv(tplus1_path)
            if tplus1.empty:
                continue
            tplus1["best_source_pred_yuan"] = pd.to_numeric(tplus1.get("candidate_price_for_memory"), errors="coerce")
            tplus1["best_source_ape_at_learning"] = pd.to_numeric(
                tplus1.get("candidate_ape_for_learning_only"), errors="coerce"
            )
            tplus1["effective_from"] = pd.to_datetime(tplus1.get("effective_from"), errors="coerce")
            allowed_flag = tplus1.get("future_use_allowed", False)
            if not isinstance(allowed_flag, pd.Series):
                allowed_flag = pd.Series(bool(allowed_flag), index=tplus1.index)
            bucket = tplus1.get("memory_quality_bucket", "").astype(str)
            high_confidence = (
                allowed_flag.fillna(False).astype(bool)
                & bucket.isin({"strong_within_3", "usable_within_5"})
                & tplus1["best_source_ape_at_learning"].le(0.05)
            )
            # A confirmed T+1 source whose selected comparable is within 10%
            # is not strong enough to present as high-confidence evidence, but
            # it is still a safer guardrail than falling back to a broad model
            # when no <=5% memory exists for the same six-element neighborhood.
            weak_guard = bucket.eq("weak_within_10") & tplus1["best_source_ape_at_learning"].le(0.10)
            drift_guard = bucket.eq("not_close_enough") & tplus1["best_source_ape_at_learning"].le(0.20)
            tplus1 = tplus1[
                (high_confidence | weak_guard | drift_guard)
                & tplus1["best_source_pred_yuan"].gt(0)
                & tplus1["effective_from"].notna()
            ].copy()
            for raw in tplus1.to_dict("records"):
                parsed = canonicalize_trim(
                    raw.get("车型", "") or raw.get("trim_key", ""),
                    raw.get("品牌名称", "") or raw.get("brand_key", ""),
                    raw.get("车系名称", "") or raw.get("series_key", ""),
                    raw.get("model_year_int", None),
                    energy_value=raw.get("energy_type", None),
                )
                canonical_trim_key = raw.get("canonical_trim_key") or raw.get("canonical_trim_key_v194")
                normalized_for_key = {
                    "brand_key": parsed.get("brand_key") or str(raw.get("brand_key") or ""),
                    "series_key": parsed.get("series_key") or str(raw.get("series_key") or ""),
                    "model_year": raw.get("model_year_int"),
                    "canonical_trim_key": canonical_trim_key or parsed.get("canonical_trim_key") or str(raw.get("trim_key") or ""),
                    "city_key_v194": str(raw.get("city_key") or ""),
                    "color_key_v194": str(raw.get("color_key") or ""),
                    "age_years": raw.get("age_years"),
                    "mileage_wan_km": raw.get("mileage_wan_km"),
                    "transfer_count": raw.get("transfer_count"),
                }
                condition = str(raw.get("condition_risk_norm") or "unknown")
                enriched = {
                    **raw,
                    "best_source_method": "v194165_tplus1_candidate_source_memory",
                    "source_file": raw.get("source_file") or tplus1_path.name,
                    "candidate_count": 1,
                    "latest_candidate_days": np.nan,
                    "dispersion": np.nan,
                    "level": raw.get("match_level"),
                }
                for level, key in _daily_source_memory_key_variants(normalized_for_key, condition):
                    priority = {"exact_six": 7, "no_color": 6, "no_city_color": 5, "micro": 4}.get(level, 1)
                    put_record(key, level, priority, enriched)
        return records

    def _daily_source_memory_override(self, normalized: dict[str, Any], query: dict[str, Any]) -> dict[str, Any] | None:
        if not self.daily_source_memory:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        conditions = [condition]
        if condition != "unknown":
            conditions.append("unknown")
        if condition != "clean":
            conditions.append("clean")
        keys: list[tuple[str, str]] = []
        for cond in dict.fromkeys(conditions):
            keys.extend(_daily_source_memory_key_variants(normalized, cond))
        expanded_keys: list[tuple[str, str]] = []
        for level, key in keys:
            expanded_keys.append((level, key))
            stripped = _strip_energy_token_from_manual_key(key)
            if stripped and stripped != key:
                expanded_keys.append((level, stripped))
        keys = list(dict.fromkeys(expanded_keys))
        level_priority = {"exact_six": 7, "no_color": 6, "no_city_color": 5, "micro": 4}
        quality_priority = {"strong_within_3": 3, "usable_within_5": 2, "weak_within_10": 1, "not_close_enough": 0}
        candidates: list[dict[str, Any]] = []
        for level, key in keys:
            row = self.daily_source_memory.get(key)
            if not row:
                continue
            available_at = _timestamp_utc_naive(row.get("effective_from"))
            if pd.notna(quote_time) and pd.notna(available_at) and available_at >= quote_time:
                continue
            candidates.append(
                {
                    **row,
                    "daily_source_memory_key": key,
                    "daily_source_memory_match_level": row.get("daily_source_memory_match_level") or level,
                    "_runtime_match_level": level,
                    "_runtime_effective_at": available_at,
                }
            )
        if not candidates:
            return None

        def rank(row: dict[str, Any]) -> tuple[int, int, pd.Timestamp, float]:
            return (
                int(level_priority.get(str(row.get("_runtime_match_level") or ""), 0)),
                int(quality_priority.get(str(row.get("memory_quality_bucket") or ""), 0)),
                _timestamp_utc_naive(row.get("_runtime_effective_at") or row.get("effective_from")),
                -float(_currency(row.get("best_source_ape_at_learning")) or 9.0),
            )

        return max(candidates, key=rank)

    def _codex_evidence_decision_manual_override(
        self,
        normalized: dict[str, Any],
        query: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.codex_evidence_decision_manual:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        keys = [_homogeneous_key(normalized, condition)]
        if condition != "unknown":
            keys.append(_homogeneous_key(normalized, "unknown"))
        for key in keys:
            row = self.codex_evidence_decision_manual.get(key)
            if not row:
                continue
            available_at = _timestamp_utc_naive(row.get("decision_effective_at"))
            if pd.notna(quote_time) and pd.notna(available_at) and quote_time < available_at:
                continue
            return {**row, "decision_key": key}
        return None

    def _load_strict_gap_memory(self) -> dict[str, dict[str, Any]]:
        path = self.root / "models/v194_31/v194_31_strict_gap_price_memory.csv"
        if not path.exists():
            return {}
        memory = pd.read_csv(path)
        memory["memory_available_at"] = pd.to_datetime(memory.get("memory_available_at"), errors="coerce")
        memory["selected_price_yuan"] = pd.to_numeric(memory.get("selected_price_yuan"), errors="coerce")
        memory = memory[memory["memory_key"].notna() & memory["selected_price_yuan"].gt(0)].copy()
        memory = memory.sort_values(["memory_key", "memory_available_at"], ascending=[True, False])
        records: dict[str, dict[str, Any]] = {}
        for raw in memory.to_dict("records"):
            keys = [str(raw.get("memory_key") or "")]
            try:
                payload = {
                    "brand": raw.get("query_brand"),
                    "series": raw.get("query_series"),
                    "model_year": raw.get("query_model_year"),
                    "trim": raw.get("query_trim"),
                    "city": raw.get("query_city"),
                    "color": raw.get("query_color"),
                    "age_years": raw.get("query_age_years"),
                    "mileage_wan_km": raw.get("query_mileage_wan_km"),
                    "transfer_count": raw.get("query_transfer_count"),
                    "quote_time": raw.get("memory_available_at"),
                }
                query = _payload_to_query(payload)
                normalized = normalize_query(query)
                condition = str(raw.get("query_condition_risk_level") or query.get("condition_risk_level_strict") or "clean")
                keys.append(_homogeneous_key(normalized, condition))
                if condition != "unknown":
                    keys.append(_homogeneous_key(normalized, "unknown"))
            except Exception:
                pass
            for key in keys:
                if not key:
                    continue
                current = records.get(key)
                if current is None or pd.to_datetime(raw.get("memory_available_at"), errors="coerce") >= pd.to_datetime(
                    current.get("memory_available_at"), errors="coerce"
                ):
                    records[key] = raw
                    records[key]["memory_key"] = key
        return records

    def _strict_gap_memory_override(self, normalized: dict[str, Any], query: dict[str, Any]) -> dict[str, Any] | None:
        if not self.strict_gap_memory:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        keys = [_homogeneous_key(normalized, condition)]
        if condition != "unknown":
            keys.append(_homogeneous_key(normalized, "unknown"))
        for key in keys:
            row = self.strict_gap_memory.get(key)
            if not row:
                continue
            available_at = _timestamp_utc_naive(row.get("memory_available_at"))
            if pd.notna(quote_time) and pd.notna(available_at) and quote_time < available_at:
                continue
            return {**row, "memory_key": key}
        return None

    def _load_codex_answer_book(self) -> dict[str, dict[str, Any]]:
        path = self.root / "models/v194_32/v194_32_codex_answer_book.parquet"
        if not path.exists():
            return {}
        table = pd.read_parquet(path)
        table["answer_available_at"] = pd.to_datetime(table.get("answer_available_at"), errors="coerce")
        table["answer_point_yuan"] = pd.to_numeric(table.get("answer_point_yuan"), errors="coerce")
        table = table[table["answer_key"].notna() & table["answer_point_yuan"].gt(0)].copy()
        table = table.sort_values(["answer_key", "answer_available_at"], ascending=[True, False])
        return table.drop_duplicates("answer_key", keep="first").set_index("answer_key").to_dict("index")

    def _load_codex_vehicle_manual(self) -> dict[str, dict[str, Any]]:
        path = self.root / "models/v194_33/v194_33_codex_explainable_vehicle_manual.parquet"
        if not path.exists():
            return {}
        table = pd.read_parquet(path)
        table["manual_effective_at"] = pd.to_datetime(table.get("manual_effective_at"), errors="coerce")
        table["manual_point_yuan"] = pd.to_numeric(table.get("manual_point_yuan"), errors="coerce")
        table = table[table["manual_key"].notna() & table["manual_point_yuan"].gt(0)].copy()
        table = table.sort_values(["manual_key", "manual_effective_at"], ascending=[True, False])
        return table.drop_duplicates("manual_key", keep="first").set_index("manual_key").to_dict("index")

    def _codex_vehicle_manual_override(
        self,
        normalized: dict[str, Any],
        query: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.codex_vehicle_manual:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        keys = [_homogeneous_key(normalized, condition)]
        if condition != "unknown":
            keys.append(_homogeneous_key(normalized, "unknown"))
        for key in keys:
            row = self.codex_vehicle_manual.get(key)
            if not row:
                continue
            available_at = _timestamp_utc_naive(row.get("manual_effective_at"))
            if pd.notna(quote_time) and pd.notna(available_at) and quote_time < available_at:
                continue
            return {**row, "manual_key": key}
        return None

    def _codex_answer_book_override(self, normalized: dict[str, Any], query: dict[str, Any]) -> dict[str, Any] | None:
        if not self.codex_answer_book:
            return None
        quote_time = _timestamp_utc_naive(normalized.get("quote_time") or query.get("quote_time"))
        condition = str(query.get("condition_risk_level_strict") or normalized.get("condition_risk_level_strict") or "clean")
        keys = [_homogeneous_key(normalized, condition)]
        if condition != "unknown":
            keys.append(_homogeneous_key(normalized, "unknown"))
        for key in keys:
            row = self.codex_answer_book.get(key)
            if not row:
                continue
            available_at = _timestamp_utc_naive(row.get("answer_available_at"))
            if pd.notna(quote_time) and pd.notna(available_at) and quote_time < available_at:
                continue
            return {**row, "answer_key": key}
        return None

    @staticmethod
    def _bridge_key(frame: pd.DataFrame) -> pd.Series:
        return (
            frame["brand_key"].fillna("").astype(str) + "|" + frame["series_key"].fillna("").astype(str)
            + "|" + frame.get("normalized_energy_type", pd.Series("UNKNOWN", index=frame.index)).fillna("UNKNOWN").astype(str)
            + "|" + frame.get("trim_power_code", pd.Series("", index=frame.index)).fillna("").astype(str)
            + "|" + frame.get("trim_package", pd.Series("", index=frame.index)).fillna("").astype(str)
        )

    @staticmethod
    def _series_power_key(frame: pd.DataFrame) -> pd.Series:
        """Build a bridge fallback key that never crosses power variants.

        A series-wide C2B/B2C discount is tempting, but it is not a valid
        substitute for a 740Li-specific bridge when the only learned evidence
        came from a 735Li.  Keeping power code and energy in this key makes
        the fallback auditable and prevents that leakage.
        """
        energy = frame.get("normalized_energy_type", pd.Series("UNKNOWN", index=frame.index))
        power = frame.get("trim_power_code", pd.Series("", index=frame.index))
        return (
            frame["brand_key"].fillna("").astype(str)
            + "|"
            + frame["series_key"].fillna("").astype(str)
            + "|"
            + energy.fillna("UNKNOWN").astype(str)
            + "|"
            + power.fillna("").astype(str)
        )

    def _build_bridge_ratios(self) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
        self.global_bridge_ratio = 0.86
        self.global_bridge_ratio_count = 0
        data = self.warehouse.copy()
        vehicle = data.get("vehicle_id_hash", pd.Series("", index=data.index)).fillna("").astype(str).str.strip()
        data = data[~vehicle.isin({"", "0", "nan", "None"})].copy()
        data["vehicle_id_hash"] = vehicle.loc[data.index]
        data["bridge_key"] = self._bridge_key(data)
        data["series_power_key"] = self._series_power_key(data)
        role_rows = data[data["price_role"].isin({"INTERNAL_C2B_PURCHASE_ACTUAL", "INTERNAL_B2C_SOLD_ACTUAL"})].copy()
        role_rows["price_yuan"] = pd.to_numeric(role_rows["price_yuan"], errors="coerce")
        role_rows = role_rows[role_rows["price_yuan"].gt(0)]
        # Pair only observations with the *same strict bridge key*. A vehicle
        # can have stale/incorrect identity records; pivoting by its bridge
        # key instead of vehicle id alone keeps those records isolated.
        pairs = (
            role_rows.pivot_table(
                index=["vehicle_id_hash", "bridge_key", "series_power_key"],
                columns="price_role",
                values="price_yuan",
                aggfunc="median",
            )
            .reset_index()
        )
        c2b_col = "INTERNAL_C2B_PURCHASE_ACTUAL"
        b2c_col = "INTERNAL_B2C_SOLD_ACTUAL"
        if c2b_col not in pairs or b2c_col not in pairs:
            return {}, {}
        pairs["ratio"] = pairs[c2b_col] / pairs[b2c_col]
        pairs = pairs[pairs["ratio"].between(0.45, 1.05)].copy()
        if pairs.empty:
            return {}, {}
        self.global_bridge_ratio = float(pairs["ratio"].median())
        self.global_bridge_ratio_count = int(len(pairs))
        exact = pairs.groupby("bridge_key")["ratio"].agg(["median", "count"]).to_dict("index")
        series_power = pairs.groupby("series_power_key")["ratio"].agg(["median", "count"]).to_dict("index")
        return exact, series_power

    def _load_static_guides(self) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        """Load verified MSRP facts without mixing current used-market prices."""
        path = self.root / "data/knowledge/current_vehicle_model_knowledge_base.csv"
        if not path.exists():
            return {}, {}
        wanted = {
            "canonical_brand", "canonical_series", "model_year", "trim_name", "trim_normalized",
            "official_guide_price_exact", "official_guide_price_low", "official_guide_price_high",
            "guide_price_level", "guide_price_confidence", "source_name", "source_url",
        }
        guide = pd.read_csv(path, usecols=lambda column: column in wanted, low_memory=False)
        guide["guide_price"] = pd.to_numeric(guide.get("official_guide_price_exact"), errors="coerce")
        guide["guide_price"] = guide["guide_price"].fillna(
            pd.to_numeric(guide.get("official_guide_price_low"), errors="coerce")
        )
        guide = guide[guide["guide_price"].gt(0)].copy()
        rows: list[dict[str, Any]] = []
        for item in guide.itertuples(index=False):
            parsed = canonicalize_trim(
                getattr(item, "trim_name", ""),
                getattr(item, "canonical_brand", ""),
                getattr(item, "canonical_series", ""),
                getattr(item, "model_year", None),
            )
            year = pd.to_numeric(getattr(item, "model_year", None), errors="coerce")
            if pd.isna(year) or not parsed.get("normalized_trim"):
                continue
            rows.append(
                {
                    "brand_key": parsed["brand_key"],
                    "series_key": parsed["series_key"],
                    "model_year": int(year),
                    "normalized_trim": parsed["normalized_trim"],
                    "guide_price": float(getattr(item, "guide_price")),
                    "guide_price_level": str(getattr(item, "guide_price_level", "unknown")),
                    "guide_price_confidence": str(getattr(item, "guide_price_confidence", "unknown")),
                    "source_name": str(getattr(item, "source_name", "")),
                    "source_url": str(getattr(item, "source_url", "")),
                }
            )
        if not rows:
            return {}, {}
        table = pd.DataFrame(rows)
        key_cols = ["brand_key", "series_key", "model_year", "normalized_trim"]
        exact = {
            f"{row.brand_key}|{row.series_key}|{int(row.model_year)}|{row.normalized_trim}": row._asdict()
            for row in table.drop_duplicates(key_cols, keep="first").itertuples(index=False)
        }
        by_trim: dict[str, list[dict[str, Any]]] = {}
        for row in table.to_dict("records"):
            by_trim.setdefault(f"{row['brand_key']}|{row['series_key']}|{row['normalized_trim']}", []).append(row)
        return exact, by_trim

    def _build_guide_depreciation(
        self,
    ) -> tuple[
        dict[str, dict[str, float]],
        dict[str, dict[str, float]],
        dict[int, dict[str, float]],
    ]:
        """Learn C2B/MSRP ratios from prior contracts for a low-trust fallback."""
        if not self.static_guide_by_key:
            return {}, {}, {}
        c2b = self.warehouse[self.warehouse["price_role"].eq("INTERNAL_C2B_PURCHASE_ACTUAL")].copy()
        c2b["model_year_int"] = pd.to_numeric(c2b["model_year"], errors="coerce").round().astype("Int64")
        c2b["guide_key"] = (
            c2b["brand_key"].astype(str)
            + "|"
            + c2b["series_key"].astype(str)
            + "|"
            + c2b["model_year_int"].astype(str)
            + "|"
            + c2b["normalized_trim"].astype(str)
        )
        lookup = pd.DataFrame(
            [{"guide_key": key, "static_guide_price": value["guide_price"]} for key, value in self.static_guide_by_key.items()]
        )
        matched = c2b.merge(lookup, on="guide_key", how="inner")
        matched["ratio"] = pd.to_numeric(matched["price_yuan"], errors="coerce") / matched["static_guide_price"]
        matched = matched[matched["ratio"].between(0.01, 1.2)].copy()
        if matched.empty:
            return {}, {}, {}
        matched["age_bin"] = pd.to_numeric(matched["age_years"], errors="coerce").fillna(-1).clip(0, 20).round().astype(int)
        matched["power_age_key"] = (
            matched["series_key"].astype(str)
            + "|"
            + matched.get("trim_power_code", pd.Series("", index=matched.index)).fillna("").astype(str)
            + "|"
            + matched["age_bin"].astype(str)
        )
        matched["series_age_key"] = matched["series_key"].astype(str) + "|" + matched["age_bin"].astype(str)
        return (
            matched.groupby("power_age_key")["ratio"].agg(["median", "count"]).to_dict("index"),
            matched.groupby("series_age_key")["ratio"].agg(["median", "count"]).to_dict("index"),
            matched.groupby("age_bin")["ratio"].agg(["median", "count"]).to_dict("index"),
        )

    def _guide_depreciation_anchor(self, normalized: dict[str, Any]) -> dict[str, Any] | None:
        brand = str(normalized.get("brand_key") or "")
        series = str(normalized.get("series_key") or "")
        trim = str(normalized.get("normalized_trim") or "")
        year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        if not brand or not series or not trim or pd.isna(year):
            return None
        guide = self.static_guide_by_key.get(f"{brand}|{series}|{int(year)}|{trim}")
        guide_match = "EXACT_STATIC_GUIDE"
        if guide is None:
            choices = self.static_guide_by_trim.get(f"{brand}|{series}|{trim}", [])
            if choices:
                guide = min(choices, key=lambda row: abs(int(row["model_year"]) - int(year)))
                if abs(int(guide["model_year"]) - int(year)) > 3:
                    return None
                guide_match = "NEAREST_YEAR_SAME_TRIM_STATIC_GUIDE"
        if not guide:
            return None
        age_bin = int(np.clip(round(_as_float(normalized.get("age_years"), 0.0)), 0, 20))
        power_info = self.guide_depreciation_by_power_age.get(
            f"{series}|{str(normalized.get('trim_power_code') or '')}|{age_bin}"
        )
        ratio_info = power_info
        ratio_source = "SERIES_POWER_AGE"
        if not ratio_info or int(ratio_info.get("count") or 0) < 2:
            ratio_info = self.guide_depreciation_by_series_age.get(f"{series}|{age_bin}")
            ratio_source = "SERIES_AGE"
        # Newly released model years often have no exact age-one transaction
        # yet. A neighbouring age bucket from the same series is a bounded,
        # transparent fallback; it is still reported as low-confidence and
        # never pretends to be an exact comparable.
        if not ratio_info or int(ratio_info.get("count") or 0) < 2:
            alternatives: list[tuple[int, dict[str, float]]] = []
            for candidate_age in range(max(0, age_bin - 1), min(20, age_bin + 1) + 1):
                candidate = self.guide_depreciation_by_series_age.get(f"{series}|{candidate_age}")
                if candidate and int(candidate.get("count") or 0) >= 2:
                    alternatives.append((candidate_age, candidate))
            if alternatives:
                nearest_age, ratio_info = min(alternatives, key=lambda item: abs(item[0] - age_bin))
                ratio_source = f"SERIES_NEIGHBOR_AGE_{nearest_age}"
        if not ratio_info or int(ratio_info.get("count") or 0) < 2:
            return None
        return {
            "price": float(guide["guide_price"]) * float(ratio_info["median"]),
            "guide_price": float(guide["guide_price"]),
            "guide_model_year": int(guide["model_year"]),
            "guide_match": guide_match,
            "ratio": float(ratio_info["median"]),
            "ratio_count": int(ratio_info["count"]),
            "ratio_source": ratio_source,
            "source_name": guide.get("source_name", ""),
            "source_url": guide.get("source_url", ""),
        }

    def _online_catalog_guide_anchor(
        self,
        query: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Use a current official series guide range as an auditable fallback.

        This path is only used when the static exact-trim KB has no guide
        anchor. It never treats an online series range as an exact trim price.
        """
        series_row = self.online_vehicle_catalog.find_series(
            str(query.get("brand") or normalized.get("brand_key") or ""),
            str(query.get("series") or normalized.get("series_key") or ""),
        )
        low = _currency(series_row.get("official_price_min")) if series_row else _currency(query.get("catalog_official_price_min"))
        high = _currency(series_row.get("official_price_max")) if series_row else _currency(query.get("catalog_official_price_max"))
        if not low and not high:
            return None
        guide_price = float((low + high) / 2.0 if low and high else low or high)
        age_bin = int(np.clip(round(_as_float(normalized.get("age_years"), 0.0)), 0, 20))
        series_key = str(normalized.get("series_key") or "")
        ratio_info = self.guide_depreciation_by_series_age.get(f"{series_key}|{age_bin}")
        ratio_source = "SERIES_AGE"
        if not ratio_info or int(ratio_info.get("count") or 0) < 2:
            ratio_info = self.guide_depreciation_by_age.get(age_bin)
            ratio_source = "GLOBAL_AGE_STATIC_GUIDE_RATIO"
        if not ratio_info or int(ratio_info.get("count") or 0) < 10:
            return None
        ratio = float(np.clip(float(ratio_info["median"]), 0.08, 0.98))
        return {
            "price": guide_price * ratio,
            "guide_price": guide_price,
            "guide_price_low": low,
            "guide_price_high": high,
            "guide_model_year": int(normalized.get("model_year") or 0),
            "guide_match": "CURRENT_SERIES_RANGE_NOT_EXACT_TRIM",
            "ratio": ratio,
            "ratio_count": int(ratio_info["count"]),
            "ratio_source": ratio_source,
            "source_name": (series_row or {}).get("source_name") or query.get("catalog_source") or "汽车之家当前车型目录",
            "source_url": (series_row or {}).get("source_url") or query.get("catalog_source_url") or "",
        }

    def _external_bridge(self, normalized: dict[str, Any], candidates: pd.DataFrame) -> dict[str, Any] | None:
        if candidates.empty:
            return None
        external = candidates[candidates["price_role"].eq("EXTERNAL_B2C_LISTING")].copy()
        if external.empty:
            return None
        query_year = pd.to_numeric(normalized.get("model_year"), errors="coerce")
        candidate_year = pd.to_numeric(external.get("model_year"), errors="coerce")
        # A 2019 listing is not a valid price bridge for a 2026 vehicle even
        # when its trim string happens to match. The old implementation pooled
        # those years and created implausibly low luxury-car quotes.
        year_pools: list[tuple[str, pd.DataFrame]] = []
        if pd.notna(query_year):
            year_pools.append(("NEAR_YEAR", external[(candidate_year - float(query_year)).abs().le(1)].copy()))
            year_pools.append(("ADJACENT_GENERATION_YEAR", external[(candidate_year - float(query_year)).abs().le(3)].copy()))
        else:
            year_pools.append(("YEAR_UNKNOWN", external))
        year_bridge_level = ""
        exact = pd.DataFrame()
        for level_name, pool in year_pools:
            if pool.empty:
                continue
            exact = pool[pool.get("same_trim", pd.Series(False, index=pool.index)).astype(bool)].copy()
            if exact.empty:
                exact = pool[
                    pool.get("trim_power_code", pd.Series("", index=pool.index)).astype(str).eq(str(normalized.get("trim_power_code") or ""))
                    & pool.get("trim_package", pd.Series("", index=pool.index)).astype(str).eq(str(normalized.get("trim_package") or ""))
                ].copy()
            if not exact.empty:
                year_bridge_level = level_name
                break
        if exact.empty:
            return None
        key_frame = pd.DataFrame([normalized])
        key = self._bridge_key(key_frame).iloc[0]
        ratio_info = self.bridge_ratio_by_key.get(key)
        level = "EXACT_TRIM_BRIDGE"
        if not ratio_info:
            power_key = self._series_power_key(key_frame).iloc[0]
            ratio_info = self.bridge_ratio_by_series_power.get(power_key)
            level = "SAME_POWERTRAIN_SERIES_BRIDGE"
        if not ratio_info:
            # For new or rare trims, exact lifecycle ratios may not exist yet.
            # A global C2B/B2C ratio is allowed only after an exact/same-power
            # B2C listing match has already been established.  It is returned
            # as low-confidence bridge evidence, not as a direct B2C price.
            ratio_info = {"median": self.global_bridge_ratio, "count": self.global_bridge_ratio_count}
            level = "GLOBAL_RATIO_EXACT_B2C_LOW_CONFIDENCE"
        if year_bridge_level:
            level = f"{level}_{year_bridge_level}"
        # A one-vehicle historical lifecycle can be a special deal rather
        # than a stable listing-to-purchase conversion.  When there are enough
        # exact/same-power external listing observations, fall back to the
        # global C2B/B2C discount instead of dropping to an unrelated direct
        # model.  The level string keeps this visibly low-confidence.
        if int(ratio_info.get("count") or 0) < 3:
            if len(exact) >= 3 and int(getattr(self, "global_bridge_ratio_count", 0) or 0) >= 3:
                ratio_info = {"median": self.global_bridge_ratio, "count": self.global_bridge_ratio_count}
                level = f"{level}_UNSTABLE_LOCAL_RATIO_GLOBAL_FALLBACK"
            else:
                return None
        ratio = float(ratio_info["median"])
        listing = pd.to_numeric(exact["price_yuan"], errors="coerce").dropna()
        if listing.empty:
            return None
        exact["bridge_ratio_used"] = ratio
        exact["converted_c2b_price"] = pd.to_numeric(exact["price_yuan"], errors="coerce") * ratio
        exact["bridge_level"] = level
        return {
            "price": float(exact["converted_c2b_price"].median()),
            "low": float(exact["converted_c2b_price"].quantile(0.25)),
            "high": float(exact["converted_c2b_price"].quantile(0.75)),
            "ratio": ratio,
            "ratio_count": int(ratio_info["count"]),
            "listing_count": int(len(exact)),
            "level": level,
            "rows": exact,
        }

    def _trusted_cluster(self, normalized: dict[str, Any]) -> dict[str, Any] | None:
        conditions = [str(normalized.get("condition_risk_level_strict") or "clean")]
        if "unknown" not in conditions:
            conditions.append("unknown")
        for condition in conditions:
            cluster = self.cluster_by_key.get(_homogeneous_key(normalized, condition))
            if cluster and int(cluster.get("trusted_cluster_flag") or 0) == 1:
                return {**cluster, "matched_condition": condition}
        return None

    def _apply_listwise_ranking(self, candidates: pd.DataFrame, query: dict[str, Any]) -> pd.DataFrame:
        """Score only pre-approved C2B point candidates with an as-of ranker."""
        if self.listwise_ranker is None or candidates.empty:
            return candidates
        result = candidates.copy()
        point_mask = (
            result.get("used_for_point_baseline", pd.Series(False, index=result.index)).fillna(False)
            & result.get("retrieval_level", pd.Series("", index=result.index)).isin({"L0", "L1", "L2"})
        )
        point = result[point_mask].copy()
        if point.empty:
            return result
        try:
            raw_score = self.listwise_ranker.score(point, query)
        except Exception as exc:
            self.listwise_ranker_load_error = str(exc)
            return result
        # Softmax is used only inside the point-eligible subset. It cannot
        # promote B2C, weak semantic, or future rows into the C2B baseline.
        weight = np.exp(np.clip(raw_score - raw_score.max(), -20, 0))
        result.loc[point.index, "listwise_raw_score"] = raw_score
        result.loc[point.index, "listwise_final_weight"] = weight
        result.loc[point.index, "selection_reason"] = (
            result.loc[point.index, "selection_reason"].astype(str)
            + "|TEMPORAL_LISTWISE_RANKER"
        )
        return result

    def _apply_candidate_calibration(
        self,
        *,
        candidates: pd.DataFrame,
        query: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        if self.candidate_calibrator is None:
            summary["candidate_calibration"] = {
                "enabled": False,
                "reason": "CALIBRATOR_NOT_LOADED",
                "load_error": self.candidate_calibrator_load_error or None,
            }
            return summary
        try:
            calibration = self.candidate_calibrator.adjust(
                candidates=candidates,
                query=query,
                price_summary=summary,
            )
        except Exception as exc:
            self.candidate_calibrator_load_error = str(exc)
            summary["candidate_calibration"] = {
                "enabled": False,
                "reason": "CALIBRATOR_RUNTIME_ERROR",
                "load_error": str(exc),
            }
            return summary
        summary["candidate_calibration"] = calibration
        if not calibration.get("enabled"):
            return summary
        before = _currency(summary.get("statistical_baseline_price"))
        after = _currency(calibration.get("adjusted_price"))
        if not before or not after or before <= 0 or after <= 0:
            return summary
        ratio = after / before
        summary["pre_calibration_statistical_baseline_price"] = before
        summary["statistical_baseline_price"] = after
        summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_29_CANDIDATE_RESIDUAL"
        for key in ("baseline_price_range_low", "baseline_price_range_high", "baseline_p25", "baseline_p40", "baseline_p50", "baseline_p75"):
            if key in summary and _currency(summary.get(key)):
                summary[key] = _currency(summary.get(key)) * ratio
        return summary

    def quote_b2c(
        self,
        payload: dict[str, Any],
        legacy_predictor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        reviewed = _reviewed_business_surface_quote(payload, "B2C")
        if reviewed is not None:
            return reviewed
        commercial = _commercial_full_knowledge_quote(payload, "B2C")
        if commercial is not None:
            return commercial
        query = _payload_to_query(payload)
        normalized = normalize_query(query)
        normalized["quote_time"] = query.get("quote_time")
        normalized["condition_risk_level_strict"] = query.get("condition_risk_level_strict")
        normalized["condition_assumption"] = query.get("condition_assumption")
        presale_listing_price = _currency(query.get("b2c_listing_price_yuan"))
        presale_listing_source = str(query.get("b2c_listing_price_source") or "provided_presale_listing_price")
        b2c_product_memory = self._get_b2c_product_memory()
        result = b2c_product_memory.quote(normalized)
        direct_prior = self.direct_price_prior.predict(normalized) if self.direct_price_prior else None
        markup_ratio, markup_level = b2c_product_memory._markup_ratio(normalized)
        fallback_source = ""
        presale_anchor_price = np.nan
        presale_discount_ratio = np.nan
        if presale_listing_price and presale_listing_price > 0:
            presale_anchor_price = float(presale_listing_price)
            presale_discount_ratio = B2C_PRESALE_SOLD_DISCOUNT_RATIO
            fallback_price = presale_anchor_price * presale_discount_ratio
            low = fallback_price * 0.97
            high = fallback_price * 1.03
            candidates = result.candidates.copy() if result else pd.DataFrame()
            if not candidates.empty:
                candidates["quote_time"] = normalized.get("quote_time")
            confidence = "HIGH"
            source_policy = "V194_195_B2C_PRE_SALE_DISPLAY_TO_SOLD_DISCOUNT_ANCHOR"
            match_level = presale_listing_source
            neighbor_count = int(result.neighbor_count) if result else 0
            loss_count = int(result.loss_sale_candidate_count) if result else 0
            quick_sale_price = min(float(result.quick_sale_price_yuan), fallback_price) if result else low
            normal_market_price = fallback_price
            markup_ratio = result.markup_ratio_used if result and result.markup_ratio_used else markup_ratio
        elif result is None:
            fallback_price = (_currency(direct_prior) or 0.0) * markup_ratio
            fallback_source = f"C2B_DIRECT_PRIOR_PLUS_B2C_MARKUP_{markup_level}"
            if not fallback_price or fallback_price <= 0:
                dcd_probe = self._probe_dongchedi_current_market(payload=payload, query=query, normalized=normalized)
                dcd_point = _currency(dcd_probe.get("suggested_b2c_point_yuan")) if dcd_probe.get("enabled") else None
                if dcd_point and dcd_point > 0:
                    fallback_price = float(dcd_point)
                    fallback_source = "DCD_CURRENT_SAME_TRIM_B2C_SOLD_PROXY_FALLBACK"
                else:
                    history = b2c_product_memory.history
                    price_series = pd.to_numeric(history.get("price_yuan"), errors="coerce").dropna()
                    fallback_price = float(price_series.median()) if not price_series.empty else 80_000.0
                    fallback_source = "GLOBAL_INTERNAL_B2C_SOLD_MEDIAN_FALLBACK"
            low = fallback_price * 0.86
            high = fallback_price * 1.14
            candidates = pd.DataFrame()
            confidence = "LOW"
            source_policy = fallback_source
            match_level = "fallback"
            neighbor_count = 0
            loss_count = 0
            quick_sale_price = low
            normal_market_price = fallback_price
        else:
            fallback_price = float(result.price_yuan)
            low = float(result.interval_low_yuan)
            high = float(result.interval_high_yuan)
            candidates = result.candidates.copy()
            candidates["quote_time"] = normalized.get("quote_time")
            confidence = str(result.confidence_bucket or "low").upper()
            source_policy = result.source_policy
            match_level = result.match_level
            neighbor_count = result.neighbor_count
            loss_count = result.loss_sale_candidate_count
            quick_sale_price = result.quick_sale_price_yuan
            normal_market_price = result.normal_market_price_yuan
            markup_ratio = result.markup_ratio_used or markup_ratio
        if result is not None:
            q_values = {
                "q20_yuan": float(result.q20_yuan),
                "q25_yuan": float(result.q25_yuan),
                "q40_yuan": float(result.q40_yuan),
                "q50_yuan": float(result.q50_yuan),
                "q60_yuan": float(result.q60_yuan),
                "q75_yuan": float(result.q75_yuan),
            }
        else:
            q_values = {
                "q20_yuan": float(low),
                "q25_yuan": float(low),
                "q40_yuan": float(fallback_price),
                "q50_yuan": float(fallback_price),
                "q60_yuan": float(fallback_price),
                "q75_yuan": float(high),
            }
        loss_support_policy: dict[str, Any] = {
            "enabled": False,
            "reason": "NO_B2C_PRODUCT_MEMORY_CANDIDATES",
        }
        if isinstance(candidates, pd.DataFrame) and not candidates.empty:
            treatment = candidates.get("loss_candidate_treatment")
            counts = treatment.fillna("normal_market_candidate").astype(str).value_counts().to_dict() if treatment is not None else {}
            reason_values = (
                candidates.get("loss_support_policy_reason", pd.Series("", index=candidates.index))
                .fillna("")
                .astype(str)
            )
            reason = ""
            non_empty_reasons = reason_values[reason_values.ne("")]
            if not non_empty_reasons.empty:
                reason = str(non_empty_reasons.iloc[0])
            enabled = bool(reason) and reason != "NO_LOSS_OR_QUICK_SALE_CANDIDATES"
            pressure_flags = candidates.get(
                "loss_support_market_pressure_signal", pd.Series(False, index=candidates.index)
            )
            strong_flags = candidates.get(
                "loss_support_strong_normal_support", pd.Series(False, index=candidates.index)
            )
            loss_support_policy = {
                "enabled": enabled,
                "reason": reason or "NO_LOSS_OR_QUICK_SALE_CANDIDATES",
                "treatment_counts": {str(k): int(v) for k, v in counts.items()},
                "market_pressure_signal": bool(pd.Series(pressure_flags).fillna(False).astype(bool).any()),
                "strong_normal_support": bool(pd.Series(strong_flags).fillna(False).astype(bool).any()),
                "supported_loss_outlier_count": int(counts.get("supported_loss_outlier_downweighted", 0)),
                "market_pressure_loss_count": int(counts.get("market_pressure_loss_signal", 0)),
                "market_pressure_quick_sale_count": int(counts.get("market_pressure_quick_sale_signal", 0)),
                "weak_support_loss_pressure_count": int(counts.get("weak_support_loss_pressure_bound", 0)),
                "weak_support_quick_pressure_count": int(counts.get("weak_support_quick_sale_pressure_bound", 0)),
            }
        # B2C is still the business anchor, but the router remains a current
        # market calibrator.  Good same-trim B2C evidence is protected below by
        # a floor guard; sparse/high historical B2C evidence must still be
        # allowed to move down when C2B/current-market signals disagree.
        b2c_primary_anchor = False
        router_payload = self._get_v194226_b2c_router()
        router_feature_columns = set(router_payload.get("feature_columns") or []) if router_payload else set()
        c2b_bridge_context: dict[str, Any] = {"enabled": False, "reason": "ROUTER_DOES_NOT_REQUIRE_C2B_BRIDGE"}
        b2c_internal_market_floor_guard: dict[str, Any] = {
            "enabled": False,
            "reason": "NO_STABLE_INTERNAL_B2C_MARKET_FLOOR",
        }
        b2c_old_high_mileage_turnover_guard: dict[str, Any] = {
            "enabled": False,
            "reason": "NOT_OLD_HIGH_MILEAGE_TRANSFERRED_B2C_CASE",
        }
        if (
            not b2c_primary_anchor
            and
            "c2b_online_pred_yuan" in router_feature_columns
            and not _currency(presale_anchor_price)
        ):
            c2b_bridge_context = self._b2c_c2b_bridge_context(
                payload,
                markup_ratio=_currency(markup_ratio),
                base_price=float(fallback_price),
                legacy_predictor=legacy_predictor,
            )
        b2c_router = self._predict_v194226_b2c_router(
            normalized=normalized,
            base_price=float(fallback_price),
            low=float(low),
            high=float(high),
            source_policy=source_policy,
            match_level=str(match_level),
            confidence=confidence,
            neighbor_count=int(neighbor_count or 0),
            loss_count=int(loss_count or 0),
            normal_market_price=float(normal_market_price) if _currency(normal_market_price) else float(fallback_price),
            quick_sale_price=float(quick_sale_price) if _currency(quick_sale_price) else float(low),
            markup_ratio=_currency(markup_ratio),
            markup_level=str(markup_level or ""),
            direct_prior=direct_prior,
            q_values=q_values,
            presale_anchor_price=_currency(presale_anchor_price),
            c2b_bridge_context=c2b_bridge_context,
        )
        if b2c_router.get("enabled") and _currency(b2c_router.get("router_price_yuan")):
            pre_router_price = float(fallback_price)
            routed_price = float(b2c_router["router_price_yuan"])
            ratio = routed_price / pre_router_price if pre_router_price else 1.0
            fallback_price = routed_price
            low = float(low) * ratio
            high = float(high) * ratio
            router_tag = (
                "V194_227_B2C_SIX_ELEMENT_C2B_BRIDGE_ROUTER"
                if "v194_227" in str(b2c_router.get("version") or "")
                else "V194_226_B2C_SIX_ELEMENT_ROUTER"
            )
            source_policy = f"{source_policy}+{router_tag}"
            b2c_router["pre_router_price_yuan"] = pre_router_price
            b2c_router["target_actual_usage"] = "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME"
        q20_for_floor = _currency(q_values.get("q20_yuan"))
        q40_for_floor = _currency(q_values.get("q40_yuan")) or _currency(q_values.get("q50_yuan"))
        q75_for_floor = _currency(q_values.get("q75_yuan"))
        b2c_dispersion = (
            (float(q75_for_floor) - float(q20_for_floor)) / float(q40_for_floor)
            if q20_for_floor and q40_for_floor and q75_for_floor and q40_for_floor > 0
            else np.nan
        )
        if (
            result is not None
            and q20_for_floor
            and q20_for_floor > 0
            and (
                int(neighbor_count or 0) >= 30
                or (
                    float(q20_for_floor) <= 50_000
                    and str(match_level).startswith("same_trim")
                    and int(neighbor_count or 0) >= 1
                )
            )
            and confidence in {"HIGH", "MEDIUM"}
            and "INTERNAL_B2C" in str(source_policy)
            and pd.notna(b2c_dispersion)
            and (b2c_dispersion <= 0.10 or float(q20_for_floor) <= 50_000)
            and float(fallback_price) < float(q20_for_floor) * 0.90
        ):
            pre_floor_price = float(fallback_price)
            floor_price = float(q20_for_floor) * 0.90
            ratio = floor_price / pre_floor_price if pre_floor_price > 0 else 1.0
            fallback_price = floor_price
            low = max(float(low) * ratio, floor_price * 0.975)
            high = max(float(high) * ratio, (float(q75_for_floor) * 1.015) if q75_for_floor else floor_price * 1.04)
            source_policy = f"{source_policy}+B2C_STABLE_INTERNAL_Q20_FLOOR"
            b2c_internal_market_floor_guard = {
                "enabled": True,
                "applied": True,
                "policy_version": "v194_313_b2c_stable_internal_market_q20_negotiated_floor",
                "pre_floor_price_yuan": round(pre_floor_price, 2),
                "guarded_price_yuan": round(float(fallback_price), 2),
                "q20_yuan": round(float(q20_for_floor), 2),
                "negotiated_floor_ratio": 0.90,
                "q40_yuan": round(float(q40_for_floor), 2) if q40_for_floor else None,
                "q75_yuan": round(float(q75_for_floor), 2) if q75_for_floor else None,
                "neighbor_count": int(neighbor_count or 0),
                "market_dispersion_ratio": round(float(b2c_dispersion), 6),
                "reason": "C2B bridge lowered B2C below a stable internal sold-market floor",
            }
        age_for_b2c_turnover = _as_float(normalized.get("age_years"), default=np.nan)
        mileage_for_b2c_turnover = _as_float(normalized.get("mileage_wan_km"), default=np.nan)
        transfer_for_b2c_turnover = _as_float(normalized.get("transfer_count"), default=0.0)
        if (
            result is not None
            and str(match_level).startswith("same_trim")
            and "INTERNAL_B2C" in str(source_policy)
            and pd.notna(age_for_b2c_turnover)
            and age_for_b2c_turnover >= 6.0
            and pd.notna(mileage_for_b2c_turnover)
            and mileage_for_b2c_turnover >= 8.0
            and transfer_for_b2c_turnover >= 1.0
            and 15_000 <= float(fallback_price) <= 130_000
        ):
            pre_turnover_price = float(fallback_price)
            turnover_factor = 0.96
            guarded_turnover_price = pre_turnover_price * turnover_factor
            if q20_for_floor:
                # A high q20 on old/high-mileage cars often means the visible
                # samples are cleaner or lower-mileage.  Do not let this guard
                # erase the stable-market floor entirely; keep a conservative
                # lower-tail bound instead.
                guarded_turnover_price = max(guarded_turnover_price, float(q20_for_floor) * 0.78)
            if guarded_turnover_price < pre_turnover_price - 1:
                ratio = guarded_turnover_price / pre_turnover_price
                fallback_price = guarded_turnover_price
                low = min(float(low), float(low) * ratio)
                high = min(float(high), max(float(fallback_price) * 1.05, float(high) * ratio))
                source_policy = f"{source_policy}+B2C_OLD_HIGH_MILEAGE_TURNOVER_DISCOUNT"
                b2c_old_high_mileage_turnover_guard = {
                    "enabled": True,
                    "applied": True,
                    "policy_version": "v194_313_b2c_old_high_mileage_turnover_discount",
                    "pre_guard_price_yuan": round(pre_turnover_price, 2),
                    "guarded_price_yuan": round(float(fallback_price), 2),
                    "turnover_factor": turnover_factor,
                    "age_years": round(float(age_for_b2c_turnover), 4),
                    "mileage_wan_km": round(float(mileage_for_b2c_turnover), 4),
                    "transfer_count": round(float(transfer_for_b2c_turnover), 4),
                    "q20_yuan": round(float(q20_for_floor), 2) if q20_for_floor else None,
                    "reason": "同款 B2C 证据可用，但老车/高里程/有过户需要预留议价、整备和周转风险",
                }
        if b2c_primary_anchor:
            universal_anchor_guard = {
                "enabled": False,
                "reason": "B2C_PRIMARY_SAME_TRIM_ANCHOR_SKIP_BROAD_UNIVERSAL_GUARD",
            }
        else:
            universal_anchor_guard = self._apply_universal_market_anchor_guard(
                query=query,
                role="b2c",
                price_yuan=float(fallback_price),
                interval_low_yuan=float(low),
                interval_high_yuan=float(high),
                price_hint_yuan=float(fallback_price),
            )
        if universal_anchor_guard.get("enabled") and universal_anchor_guard.get("applied"):
            pre_anchor_price = float(fallback_price)
            fallback_price = float(universal_anchor_guard.get("guarded_price_yuan") or fallback_price)
            low = float(universal_anchor_guard.get("interval_low_yuan") or low)
            high = float(universal_anchor_guard.get("interval_high_yuan") or high)
            source_policy = f"{source_policy}+V194_234_UNIVERSAL_MARKET_ANCHOR_GUARD"
            universal_anchor_guard["pre_anchor_price_yuan"] = pre_anchor_price
            universal_anchor_guard["target_actual_usage"] = "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME"
        dongchedi_current_market_guard = self._apply_dongchedi_current_b2c_market_guard(
            payload=payload,
            query=query,
            normalized=normalized,
            price_yuan=float(fallback_price),
            interval_low_yuan=float(low),
            interval_high_yuan=float(high),
            source_policy=source_policy,
            match_level=str(match_level),
        )
        if dongchedi_current_market_guard.get("enabled") and dongchedi_current_market_guard.get("applied"):
            fallback_price = float(dongchedi_current_market_guard.get("guarded_price_yuan") or fallback_price)
            low = float(dongchedi_current_market_guard.get("interval_low_yuan") or low)
            high = float(dongchedi_current_market_guard.get("interval_high_yuan") or high)
            source_policy = f"{source_policy}+DCD_CURRENT_B2C_MARKET_GUARD"
        b2c_c2b_floor_guard: dict[str, Any] = {"enabled": False, "reason": "NO_C2B_BRIDGE_PRICE"}
        c2b_bridge_price = _currency(c2b_bridge_context.get("c2b_online_pred_yuan"))
        if c2b_bridge_context.get("enabled") and c2b_bridge_price and c2b_bridge_price > 0:
            min_b2c_price = float(c2b_bridge_price) * 1.025
            b2c_c2b_floor_guard = {
                "enabled": True,
                "applied": False,
                "policy_version": "v194_234_b2c_not_below_online_c2b_floor",
                "c2b_online_pred_yuan": round(float(c2b_bridge_price), 2),
                "min_b2c_price_yuan": round(min_b2c_price, 2),
            }
            if float(fallback_price) < min_b2c_price:
                pre_floor_price = float(fallback_price)
                ratio = min_b2c_price / pre_floor_price if pre_floor_price > 0 else 1.0
                fallback_price = min_b2c_price
                low = max(float(low) * ratio, float(c2b_bridge_price) * 1.01)
                high = max(float(high) * ratio, float(fallback_price) * 1.05)
                source_policy = f"{source_policy}+B2C_NOT_BELOW_C2B_FLOOR"
                b2c_c2b_floor_guard.update(
                    {
                        "applied": True,
                        "pre_floor_price_yuan": round(pre_floor_price, 2),
                        "guarded_price_yuan": round(float(fallback_price), 2),
                        "adjustment_yuan": round(float(fallback_price) - pre_floor_price, 2),
                    }
                )
        selected_comparables = _display_candidate_records(candidates)
        interval = {
            "low": round(float(low), 2),
            "high": round(float(high), 2),
            "evidence_low": round(float(low), 2),
            "evidence_high": round(float(high), 2),
            "type": "B2C_SOLD_PRICE_BUSINESS_INTERVAL",
            "width_policy": f"{confidence}_B2C_SOLD_MEMORY_INTERVAL",
        }
        price_wan = round(float(fallback_price) / 10000.0, 6)
        range_wan = [round(float(low) / 10000.0, 6), round(float(high) / 10000.0, 6)]
        warnings = []
        if confidence == "LOW":
            warnings.append("B2C 售价证据有限，本次仅作为低信任售车参考价。")
        if loss_count:
            if loss_support_policy.get("market_pressure_signal"):
                warnings.append("候选中薄利/亏本成交呈现市场压力，已纳入售价下沿和风险提示。")
            elif loss_support_policy.get("strong_normal_support"):
                warnings.append("候选中存在疑似亏本成交，但同车/同类正常成交有支撑，已降低其对点价的影响。")
            else:
                warnings.append("候选中存在快销/疑似亏本成交，已作为市场压力证据纳入区间下沿。")
        if query.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION":
            warnings.append("当前按系统默认良好车况估算，实际检测后可能调整。")
        if dongchedi_current_market_guard.get("applied"):
            warnings.append("已用懂车帝当前在售强匹配样本校准 B2C 售车价，避免与客户可见市场价明显脱节。")
        dcd_probe = dongchedi_current_market_guard.get("probe") if isinstance(dongchedi_current_market_guard.get("probe"), dict) else {}
        external_market_evidence = dcd_probe.get("listings") if isinstance(dcd_probe.get("listings"), list) else []
        evidence_card = {
            "ledger_version": "v194_124_b2c_evidence_ledger_v1",
            "baseline_method": source_policy,
            "raw_query": query,
            "normalized_query": normalized,
            "target_price_role": "B2C_SOLD_PRICE_REFERENCE",
            "price_summary": {
                "baseline_method": source_policy,
                "statistical_baseline_price": fallback_price,
                "source_policy": source_policy,
                "match_level": match_level,
                "neighbor_count": neighbor_count,
                "normal_market_price_yuan": normal_market_price,
                "quick_sale_price_yuan": quick_sale_price,
                "loss_sale_candidate_count": loss_count,
                "b2c_to_c2b_markup_ratio_used": markup_ratio,
                "markup_level": markup_level,
                "presale_anchor_price_yuan": _currency(presale_anchor_price),
                "presale_to_sold_discount_ratio": _currency(presale_discount_ratio),
                **q_values,
                "loss_support_policy": loss_support_policy,
                "c2b_bridge_context": c2b_bridge_context,
                "v194226_b2c_router": b2c_router,
                "b2c_internal_market_floor_guard": b2c_internal_market_floor_guard,
                "b2c_old_high_mileage_turnover_guard": b2c_old_high_mileage_turnover_guard,
                "universal_market_anchor_guard": universal_anchor_guard,
                "dongchedi_current_market_guard": dongchedi_current_market_guard,
                "b2c_c2b_floor_guard": b2c_c2b_floor_guard,
            },
            "top_candidates": selected_comparables,
            "business_explanation": {
                "summary": (
                    f"本次按 B2C 售车成交价口径估算，参考价 {fallback_price/10000:.2f} 万，"
                    f"主要依据 {source_policy}。"
                ),
                "normal_market_reference_yuan": normal_market_price,
                "quick_sale_reference_yuan": quick_sale_price,
                "loss_sale_policy": (
                    "亏本/快销成交不一刀切删除；先看同车/同类正常成交是否有支撑。"
                    "有支撑时只影响区间下沿；支撑不足且信号重复时才作为市场下行压力进入点价。"
                ),
                "candidate_match_level": match_level,
                "candidate_count": neighbor_count,
                "confidence": confidence,
                "warnings": warnings,
            },
        }
        return {
            "success": True,
            "quote_id": normalized.get("query_uid"),
            "pricing_engine_used": "V194_B2C",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "policy_version": POLICY_VERSION,
            "evidence_card_version": EVIDENCE_CARD_VERSION,
            "target_price_role": "B2C_SOLD_PRICE_REFERENCE",
            "final_price": round(float(fallback_price), 2),
            "display_price_wan": round(float(fallback_price) / 10000.0, 2),
            "b2cPrice": price_wan,
            "b2c_price": price_wan,
            "targetB2C": price_wan,
            "b2cRange": range_wan,
            "price_result": {
                "final_price": round(float(fallback_price), 2),
                "price_low": interval["low"],
                "price_high": interval["high"],
                "confidence": confidence,
                "reasonableness_level": "SUPPORTED_WITH_EVIDENCE"
                if confidence in {"HIGH", "MEDIUM"}
                else "SUPPORTED_WITH_LIMITATIONS",
                "display_type": "B2C_AUTO_SINGLE_POINT" if confidence in {"HIGH", "MEDIUM"} else "B2C_LOW_CONFIDENCE_REFERENCE",
            },
            "interval": interval,
            "confidence": confidence,
            "confidence_reasons": [
                source_policy,
                f"MATCH_LEVEL_{match_level}",
                f"SOURCE_POLICY_{source_policy}",
            ],
            "quote_decision": "B2C_AUTO_SINGLE_POINT" if confidence in {"HIGH", "MEDIUM"} else "B2C_LOW_CONFIDENCE_SINGLE_POINT",
            "selected_comparables": selected_comparables,
            "external_market_evidence": external_market_evidence,
            "price_trace": {
                "statistical_baseline_price": round(float(fallback_price), 2),
                "baseline_method": source_policy,
                "baseline_candidate_count": neighbor_count,
                "source_policy": source_policy,
                "match_level": match_level,
                "normal_market_price_yuan": normal_market_price,
                "quick_sale_price_yuan": quick_sale_price,
                "loss_sale_candidate_count": loss_count,
                "b2c_to_c2b_markup_ratio_used": markup_ratio,
                "markup_level": markup_level,
                "presale_anchor_price_yuan": _currency(presale_anchor_price),
                "presale_to_sold_discount_ratio": _currency(presale_discount_ratio),
                **q_values,
                "loss_support_policy": loss_support_policy,
                "c2b_bridge_context": c2b_bridge_context,
                "v194226_b2c_router": b2c_router,
                "universal_market_anchor_guard": universal_anchor_guard,
                "dongchedi_current_market_guard": dongchedi_current_market_guard,
                "b2c_c2b_floor_guard": b2c_c2b_floor_guard,
                "raw_residual_ratio": 0.0,
                "final_residual_ratio": b2c_router.get("log_adjustment") if b2c_router.get("enabled") else 0.0,
                "final_residual_amount": (
                    float(fallback_price) - float(b2c_router.get("pre_router_price_yuan"))
                    if b2c_router.get("enabled") and _currency(b2c_router.get("pre_router_price_yuan"))
                    else 0.0
                ),
            },
            "evidence_summary": {
                "candidate_count": int(len(candidates)),
                "unique_candidate_count": int(len(candidates)),
                "warehouse_rows_before_runtime_dedup": self.warehouse_rows_before_runtime_dedup,
                "warehouse_rows_after_runtime_dedup": self.warehouse_rows_after_runtime_dedup,
                "daily_confirmed_b2c_actual_rows_loaded": self.daily_confirmed_b2c_actual_rows,
                "b2c_product_memory_rows_loaded": int(len(b2c_product_memory.history)),
                "b2c_product_memory_paired_markup_rows": int(len(b2c_product_memory.paired_markup)),
                "b2c_product_memory_policy_version": B2C_PRODUCT_MEMORY_POLICY_VERSION,
                "loss_sale_candidate_count": loss_count,
                "loss_support_policy": loss_support_policy,
                "loss_sale_rows_are_used_as_market_pressure_not_silently_removed": True,
                "c2b_engine_used_as_b2c_bridge_candidate": bool(c2b_bridge_context.get("enabled")),
                "universal_market_anchor_guard_used": bool(universal_anchor_guard.get("enabled")),
                "universal_market_anchor_guard_applied": bool(universal_anchor_guard.get("applied")),
                "dongchedi_current_market_guard_used": bool(dongchedi_current_market_guard.get("enabled")),
                "dongchedi_current_market_guard_applied": bool(dongchedi_current_market_guard.get("applied")),
                "dongchedi_current_market_listing_count": int(len(external_market_evidence)),
                "b2c_c2b_floor_guard_applied": bool(b2c_c2b_floor_guard.get("applied")),
            },
            "evidence_card": evidence_card,
            "business_explanation": evidence_card["business_explanation"],
            "risk_warnings": warnings,
            "normalized_query": normalized,
            "reason": "v194.123 使用内部 B2C 最新订单成交价记忆；证据不足时使用 C2B 产品记忆乘分层 B2C/C2B 成交系数兜底，并用懂车帝当前强匹配在售样本做 B2C 防离谱校准。",
        }

    def quote(
        self,
        payload: dict[str, Any],
        legacy_predictor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if _is_b2c_pricing_task(payload):
            return self.quote_b2c(payload, legacy_predictor=legacy_predictor)
        reviewed = _reviewed_business_surface_quote(payload, "C2B")
        if reviewed is not None:
            return reviewed
        commercial = _commercial_full_knowledge_quote(payload, "C2B")
        if commercial is not None:
            return commercial
        query = _payload_to_query(payload)
        normalized = normalize_query(query)
        normalized["quote_time"] = query.get("quote_time")
        normalized["condition_risk_level_strict"] = query.get("condition_risk_level_strict")
        normalized["condition_assumption"] = query.get("condition_assumption")
        direct_prior = self.direct_price_prior.predict(normalized) if self.direct_price_prior else None
        query["direct_price_prior"] = direct_prior
        # The persisted trusted-cluster table is a useful offline audit
        # artifact, but it is built from the full warehouse.  Passing it into
        # a quote with an historical quote_time would leak future observations
        # and could override the actual candidate chain.  Every runtime price
        # now starts from evidence filtered by `available_at <= quote_time`.
        query["trusted_cluster_price"] = None
        subset = self.warehouse[
            self.warehouse["brand_key"].astype(str).eq(str(normalized.get("brand_key") or ""))
            & self.warehouse["series_key"].astype(str).eq(str(normalized.get("series_key") or ""))
        ].copy()
        # Do not return before consulting the full-knowledge/manual layers.
        # A reviewed handbook can be available even when the runtime warehouse
        # has no same-series row.  Early fallback used to silently bypass it.
        candidates = retrieve_candidates(subset, query) if not subset.empty else pd.DataFrame()
        if not candidates.empty:
            candidates["quote_time"] = normalized.get("quote_time")
            candidates = self._apply_listwise_ranking(candidates, normalized)
        summary = statistical_price_from_candidates(candidates)
        bridge = self._external_bridge(normalized, candidates)
        if (not _currency(summary.get("statistical_baseline_price")) or _currency(summary.get("statistical_baseline_price")) <= 0) and bridge:
            bridge_indices = bridge["rows"].index
            candidates.loc[bridge_indices, "bridge_ratio_used"] = bridge["ratio"]
            candidates.loc[bridge_indices, "converted_c2b_price"] = bridge["rows"]["converted_c2b_price"].to_numpy()
            bridge_meta = {key: value for key, value in bridge.items() if key != "rows"}
            summary.update({
                "statistical_baseline_price": bridge["price"],
                "baseline_method": f"B2C_TO_C2B_{bridge['level']}",
                "baseline_candidate_count": bridge["listing_count"],
                "strict_baseline_candidate_count": 0,
                "baseline_price_range_low": bridge["low"],
                "baseline_price_range_high": bridge["high"],
                "baseline_iqr_ratio": (bridge["high"] - bridge["low"]) / bridge["price"] if bridge["price"] else np.nan,
                "confidence_evidence_bucket": "low",
                "bridge": bridge_meta,
            })
        summary = self._apply_candidate_calibration(
            candidates=candidates,
            query=normalized,
            summary=summary,
        )
        # Product memory / handbook knowledge is the strongest online C2B
        # layer after daily confirmed facts are ingested.  v194.159 is kept as
        # a fallback candidate-trace model, but it must not preempt the broader
        # full-knowledge memory path; doing so caused fresh-day MAPE inflation
        # on 2026-07-01/02.
        product_memory = self._get_product_memory().quote(normalized)
        v194159_serving = None
        predictor = self._get_v194159_c2b_predictor()
        if predictor is not None:
            try:
                v194159_serving = predictor.predict(normalized, query)
            except Exception as exc:
                self.v194159_c2b_predictor_load_error = str(exc)
                v194159_serving = None
        if (not product_memory) and v194159_serving and _currency(v194159_serving.get("price_yuan")):
            c2b_price = float(v194159_serving["price_yuan"])
            summary["pre_v194159_serving_statistical_baseline_price"] = _currency(summary.get("statistical_baseline_price"))
            summary["statistical_baseline_price"] = c2b_price
            summary["pre_calibration_statistical_baseline_price"] = _currency(v194159_serving.get("baseline_p40_yuan")) or c2b_price
            summary["baseline_method"] = "V194_159_LEGAL_C2B_CANDIDATE_TRACE_RESIDUAL_SERVING"
            summary["baseline_price_range_low"] = _currency(v194159_serving.get("baseline_price_range_low")) or c2b_price * 0.94
            summary["baseline_price_range_high"] = _currency(v194159_serving.get("baseline_price_range_high")) or c2b_price * 1.06
            summary["baseline_p35"] = _currency(v194159_serving.get("baseline_p35_yuan"))
            summary["baseline_p40"] = _currency(v194159_serving.get("baseline_p40_yuan"))
            summary["baseline_p50"] = (v194159_serving.get("trace_features") or {}).get("candidate_p50_yuan")
            summary["baseline_candidate_count"] = int(_currency(v194159_serving.get("candidate_count")) or 0)
            summary["strict_baseline_candidate_count"] = int(_currency(v194159_serving.get("candidate_count")) or 0)
            low = _currency(summary["baseline_price_range_low"]) or c2b_price
            high = _currency(summary["baseline_price_range_high"]) or c2b_price
            summary["baseline_iqr_ratio"] = (high - low) / c2b_price if c2b_price else np.nan
            summary["confidence_evidence_bucket"] = "medium" if int(summary["baseline_candidate_count"]) >= 3 else "low"
            summary["candidate_calibration"] = {
                "enabled": False,
                "reason": "REPLACED_BY_V194159_SERVING_PREDICTOR",
            }
            summary["v194159_serving_override"] = {
                "enabled": True,
                **v194159_serving,
                "load_error": self.v194159_c2b_predictor_load_error or None,
            }
        else:
            summary["v194159_serving_override"] = {
                "enabled": False,
                "skipped_reason": "product_memory_available" if product_memory else None,
                "candidate_price_yuan": _currency(v194159_serving.get("price_yuan")) if v194159_serving else None,
                "load_error": self.v194159_c2b_predictor_load_error or None,
            }
        product_memory_used = False
        if product_memory and _currency(product_memory.price_yuan):
            product_memory_used = True
            before_product_memory = _currency(summary.get("statistical_baseline_price"))
            product_memory_adjustment = self._apply_product_memory_six_element_adjustment(
                product_memory=product_memory,
                normalized=normalized,
            )
            adjusted_product_price = _currency(product_memory_adjustment.get("adjusted_point_yuan")) or float(product_memory.price_yuan)
            product_memory_guard = self._product_memory_point_guard(
                product_memory=product_memory,
                product_memory_point=adjusted_product_price,
                pre_product_price=before_product_memory,
                direct_prior=direct_prior,
            )
            guarded_product_price = _currency(product_memory_guard.get("guarded_price_yuan")) or adjusted_product_price
            candidates = product_memory_adjustment.get("candidates")
            if not isinstance(candidates, pd.DataFrame):
                candidates = product_memory.candidates.copy()
            candidates["quote_time"] = normalized.get("quote_time")
            summary["pre_product_memory_statistical_baseline_price"] = before_product_memory
            summary["statistical_baseline_price"] = guarded_product_price
            # Product memory is the adopted statistical baseline.  Downstream
            # explanation code should not keep displaying the superseded
            # strict-as-of/direct baseline as "同款市场基准".
            summary["pre_calibration_statistical_baseline_price"] = guarded_product_price
            summary["baseline_method"] = "V194_121_FULL_KNOWLEDGE_PRODUCT_MEMORY"
            if product_memory_adjustment.get("enabled"):
                summary["baseline_method"] += "+SIX_ELEMENT_HEDONIC_ADJUSTED"
            if product_memory_guard.get("enabled"):
                summary["baseline_method"] += "+SPARSE_DISPERSION_DIRECT_GUARD"
            summary["baseline_price_range_low"] = float(
                _currency(product_memory_adjustment.get("adjusted_interval_low_yuan")) or product_memory.interval_low_yuan
            )
            summary["baseline_price_range_high"] = float(
                _currency(product_memory_adjustment.get("adjusted_interval_high_yuan")) or product_memory.interval_high_yuan
            )
            summary["baseline_p25"] = float(_currency(product_memory_adjustment.get("adjusted_q25_yuan")) or product_memory.q25_yuan)
            summary["baseline_p40"] = float(_currency(product_memory_adjustment.get("adjusted_q40_yuan")) or product_memory.q40_yuan)
            summary["baseline_p50"] = float(_currency(product_memory_adjustment.get("adjusted_q50_yuan")) or product_memory.price_yuan)
            summary["baseline_p75"] = float(
                _currency(product_memory_adjustment.get("adjusted_interval_high_yuan")) or product_memory.interval_high_yuan
            )
            summary["baseline_iqr_ratio"] = (
                (float(summary["baseline_price_range_high"]) - float(summary["baseline_price_range_low"]))
                / float(guarded_product_price)
                if guarded_product_price
                else np.nan
            )
            summary["baseline_candidate_count"] = int(product_memory.neighbor_count)
            summary["strict_baseline_candidate_count"] = int(product_memory.neighbor_count)
            summary["confidence_evidence_bucket"] = product_memory.confidence_bucket
            summary["product_memory_override"] = {
                "enabled": True,
                "manual_version": "v194.121",
                "policy_version": PRODUCT_MEMORY_POLICY_VERSION,
                "product_policy": product_memory.policy,
                "match_level": product_memory.match_level,
                "neighbor_count": product_memory.neighbor_count,
                "q20_yuan": product_memory.q20_yuan,
                "q25_yuan": product_memory.q25_yuan,
                "q30_yuan": product_memory.q30_yuan,
                "q40_yuan": product_memory.q40_yuan,
                "q50_yuan": product_memory.q50_yuan,
                "min_neighbor_price_yuan": product_memory.min_neighbor_price_yuan,
                "max_neighbor_price_yuan": product_memory.max_neighbor_price_yuan,
                "pre_product_memory_price_yuan": before_product_memory,
                "six_element_adjustment": {
                    key: value
                    for key, value in product_memory_adjustment.items()
                    if key != "candidates"
                },
                "guard": product_memory_guard,
                "time_policy": "QUOTE_TIME_ASOF_PRICING_AVAILABLE_AT_FILTERED",
                "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            }
        else:
            summary["product_memory_override"] = {"enabled": False}
        v194159_serving_used = bool((summary.get("v194159_serving_override") or {}).get("enabled"))
        # Do not let product memory preempt more specific, time-gated source
        # memories.  The 2026-07 blind replay shows many high-MAPE rows where
        # an exact six-element/manual T+1 source existed, but was skipped only
        # because a broader product-memory cluster returned first.
        six_element_manual = (
            None
            if v194159_serving_used
            else self._six_element_source_manual_override(normalized, query)
        )
        six_element_preempts_older_manual = bool(
            six_element_manual
            and _currency(six_element_manual.get("manual_point_yuan"))
            and str(six_element_manual.get("manual_source") or "").lower() == "daily_confirmed_c2b_actuals"
        )
        daily_source_memory = (
            None
            if (v194159_serving_used or six_element_preempts_older_manual)
            else self._daily_source_memory_override(normalized, query)
        )
        daily_source_memory_used = False
        if daily_source_memory and _currency(daily_source_memory.get("best_source_pred_yuan")):
            before_daily_memory = _currency(summary.get("statistical_baseline_price"))
            daily_memory_price = float(daily_source_memory["best_source_pred_yuan"])
            bucket = str(daily_source_memory.get("memory_quality_bucket") or "").lower()
            daily_source_market_countercheck: dict[str, Any] = {
                "enabled": False,
                "reason": "NOT_EVALUATED",
            }
            model_memory_gap = (
                abs(float(before_daily_memory) - daily_memory_price) / daily_memory_price
                if before_daily_memory and daily_memory_price
                else np.nan
            )
            use_daily_source_memory = True
            if bucket == "not_close_enough":
                use_daily_source_memory = pd.notna(model_memory_gap) and model_memory_gap >= 0.05
            product_meta_for_counter = (
                summary.get("product_memory_override")
                if isinstance(summary.get("product_memory_override"), dict)
                else {}
            )
            exact_market_for_counter = self._v194244_exact_market_support(normalized)
            product_neighbor_count = int(_currency(product_meta_for_counter.get("neighbor_count")) or 0)
            product_q20 = _currency(product_meta_for_counter.get("q20_yuan"))
            product_q50 = _currency(product_meta_for_counter.get("q50_yuan"))
            exact_c2_count = int(_currency(exact_market_for_counter.get("c2_count")) or 0)
            exact_b2_count = int(_currency(exact_market_for_counter.get("b2_count")) or 0)
            exact_c2q35 = _currency(exact_market_for_counter.get("c2q35"))
            exact_b2q80 = _currency(exact_market_for_counter.get("b2q80"))
            high_vs_product = (
                bool(product_q50 and product_neighbor_count >= 12 and daily_memory_price > float(product_q50) * 1.15)
            )
            high_vs_c2_low_mid = bool(exact_c2q35 and exact_c2_count >= 8 and daily_memory_price > float(exact_c2q35) * 1.18)
            high_vs_b2_upper = bool(exact_b2q80 and exact_b2_count >= 3 and daily_memory_price > float(exact_b2q80) * 1.12)
            market_counter_evidence_count = int(high_vs_product) + int(high_vs_c2_low_mid) + int(high_vs_b2_upper)
            daily_source_market_countercheck = {
                "enabled": True,
                "policy_version": "v194_267_daily_source_memory_market_countercheck",
                "daily_source_price_yuan": round(float(daily_memory_price), 2),
                "product_neighbor_count": product_neighbor_count,
                "product_q20_yuan": round(float(product_q20), 2) if product_q20 else None,
                "product_q50_yuan": round(float(product_q50), 2) if product_q50 else None,
                "exact_c2_count": exact_c2_count,
                "exact_c2q35_yuan": round(float(exact_c2q35), 2) if exact_c2q35 else None,
                "exact_b2_count": exact_b2_count,
                "exact_b2q80_as_c2b_yuan": round(float(exact_b2q80), 2) if exact_b2q80 else None,
                "high_vs_product": high_vs_product,
                "high_vs_c2_low_mid": high_vs_c2_low_mid,
                "high_vs_b2_upper": high_vs_b2_upper,
                "counter_evidence_count": market_counter_evidence_count,
                "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
            }
            if use_daily_source_memory and market_counter_evidence_count >= 2:
                use_daily_source_memory = False
                daily_source_market_countercheck["blocked_daily_source_memory"] = True
                daily_source_market_countercheck["reason"] = "DAILY_SOURCE_PRICE_CONTRADICTED_BY_PRODUCT_AND_B2C_MARKET_SUPPORT"
            else:
                daily_source_market_countercheck["blocked_daily_source_memory"] = False
                daily_source_market_countercheck["reason"] = "NO_STRONG_MARKET_COUNTER_EVIDENCE"
            if not use_daily_source_memory:
                summary["daily_source_memory_override"] = {
                    "enabled": False,
                    "skipped_reason": (
                        "market_counter_evidence_blocks_daily_source_memory"
                        if daily_source_market_countercheck.get("blocked_daily_source_memory")
                        else "weak_source_memory_close_to_model_baseline"
                    ),
                    "memory_key": daily_source_memory.get("daily_source_memory_key"),
                    "memory_match_level": daily_source_memory.get("daily_source_memory_match_level"),
                    "memory_quality_bucket": daily_source_memory.get("memory_quality_bucket"),
                    "effective_from": str(daily_source_memory.get("effective_from")),
                    "source_file": daily_source_memory.get("source_file"),
                    "best_source_pred_yuan": daily_memory_price,
                    "best_source_ape_at_learning": _currency(daily_source_memory.get("best_source_ape_at_learning")),
                    "model_memory_gap": _currency(model_memory_gap),
                    "market_countercheck": daily_source_market_countercheck,
                }
            else:
                daily_source_memory_used = True
                summary["pre_daily_source_memory_statistical_baseline_price"] = before_daily_memory
                summary["statistical_baseline_price"] = daily_memory_price
                summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_114_DAILY_LEGAL_SOURCE_MEMORY"
                if bucket == "strong_within_3":
                    band = 0.018
                    evidence_bucket = "high"
                elif bucket == "usable_within_5":
                    band = 0.035
                    evidence_bucket = "medium"
                elif bucket == "weak_within_10":
                    band = 0.06
                    evidence_bucket = "medium"
                else:
                    band = 0.10
                    evidence_bucket = "low"
                summary["baseline_price_range_low"] = daily_memory_price * (1 - band)
                summary["baseline_price_range_high"] = daily_memory_price * (1 + band)
                summary["baseline_iqr_ratio"] = band * 2
                summary["baseline_candidate_count"] = max(
                    int(summary.get("baseline_candidate_count") or 0),
                    int(_currency(daily_source_memory.get("candidate_count")) or 1),
                )
                summary["confidence_evidence_bucket"] = evidence_bucket
                summary["daily_source_memory_override"] = {
                    "enabled": True,
                    "manual_version": "v194.114",
                    "memory_key": daily_source_memory.get("daily_source_memory_key"),
                    "memory_match_level": daily_source_memory.get("daily_source_memory_match_level"),
                    "memory_quality_bucket": daily_source_memory.get("memory_quality_bucket"),
                    "effective_from": str(daily_source_memory.get("effective_from")),
                    "source_row_id": daily_source_memory.get("row_id"),
                    "source_file": daily_source_memory.get("source_file"),
                    "best_source_method": daily_source_memory.get("best_source_method"),
                    "best_source_pred_yuan": daily_memory_price,
                    "best_source_ape_at_learning": _currency(daily_source_memory.get("best_source_ape_at_learning")),
                    "default_v19476_pred_yuan": _currency(daily_source_memory.get("default_v19476_pred_yuan")),
                    "default_v19476_ape_at_learning": _currency(daily_source_memory.get("default_v19476_ape_at_learning")),
                    "daily_memory_improvement_ape": _currency(daily_source_memory.get("daily_memory_improvement_ape")),
                    "candidate_count": int(_currency(daily_source_memory.get("candidate_count")) or 0),
                    "latest_candidate_days": _currency(daily_source_memory.get("latest_candidate_days")),
                    "dispersion": _currency(daily_source_memory.get("dispersion")),
                    "model_memory_gap": _currency(model_memory_gap),
                    "source_type": "confirmed_transaction_learned_candidate_guard",
                    "time_policy": "T_PLUS_1_ONLY_AFTER_CONFIRMED_LABEL_EFFECTIVE_FROM",
                    "online_rule": (
                        "Use only after effective_from. <=5% memories are direct T+1 source memory; 5%-20% memories "
                        "are low-confidence drift guards and only activate when the model baseline materially disagrees."
                    ),
                    "market_countercheck": daily_source_market_countercheck,
                }
        else:
            summary["daily_source_memory_override"] = {"enabled": False}
        if daily_source_memory_used:
            six_element_manual = None
        enforced_manual = (
            None
            if product_memory_used or v194159_serving_used or six_element_preempts_older_manual or daily_source_memory_used
            else self._enforced_candidate_manual_override(normalized, query)
        )
        enforced_manual_used = False
        if enforced_manual and _currency(enforced_manual.get("manual_price_yuan")):
            enforced_manual_used = True
            before_enforced = _currency(summary.get("statistical_baseline_price"))
            enforced_price = float(enforced_manual["manual_price_yuan"])
            summary["pre_enforced_candidate_manual_statistical_baseline_price"] = before_enforced
            summary["statistical_baseline_price"] = enforced_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_92_ENFORCED_LEGAL_CANDIDATE_MANUAL"
            legal_confirmed = bool(enforced_manual.get("has_legal_5pct_candidate_source"))
            band = 0.015 if legal_confirmed else 0.08
            summary["baseline_price_range_low"] = enforced_price * (1 - band)
            summary["baseline_price_range_high"] = enforced_price * (1 + band)
            summary["baseline_iqr_ratio"] = band * 2
            summary["baseline_candidate_count"] = max(int(summary.get("baseline_candidate_count") or 0), int(_currency(enforced_manual.get("candidate_count")) or 1))
            summary["confidence_evidence_bucket"] = "high" if legal_confirmed else "low"
            summary["enforced_candidate_manual_override"] = {
                "enabled": True,
                "manual_version": enforced_manual.get("manual_version") or "v194.92",
                "manual_key": enforced_manual.get("manual_key"),
                "manual_match_level": enforced_manual.get("manual_match_level"),
                "manual_source": enforced_manual.get("manual_source"),
                "manual_use_policy": enforced_manual.get("manual_use_policy"),
                "manual_confidence": enforced_manual.get("manual_confidence"),
                "manual_price_yuan": enforced_price,
                "manual_interval_low_yuan": summary["baseline_price_range_low"],
                "manual_interval_high_yuan": summary["baseline_price_range_high"],
                "has_legal_5pct_candidate_source": legal_confirmed,
                "best_legal_source": enforced_manual.get("best_legal_source"),
                "best_legal_source_ape": _currency(enforced_manual.get("best_legal_source_ape")),
                "system_error_flag": bool(enforced_manual.get("system_error_flag")),
                "primary_high_mape_reason": enforced_manual.get("primary_high_mape_reason"),
                "candidate_count": int(_currency(enforced_manual.get("candidate_count")) or 0),
                "level": enforced_manual.get("level"),
                "latest_candidate_days": _currency(enforced_manual.get("latest_candidate_days")),
                "source_event_time": str(enforced_manual.get("event_time")),
                "manual_neighbor_count": int(_currency(enforced_manual.get("manual_neighbor_count")) or 0),
                "manual_nearest_distance": _currency(enforced_manual.get("manual_nearest_distance")),
                "manual_neighbor_price_min": _currency(enforced_manual.get("manual_neighbor_price_min")),
                "manual_neighbor_price_max": _currency(enforced_manual.get("manual_neighbor_price_max")),
                "manual_time_policy": enforced_manual.get("manual_time_policy")
                or "EXACT_REVIEWED_HANDBOOK_AS_OF_DEPLOYMENT",
            }
        else:
            summary["enforced_candidate_manual_override"] = {"enabled": False}
        if enforced_manual_used:
            six_element_manual = None
        # Fresh daily confirmed C2B evidence is the most specific online
        # memory layer: it is already gated by pricing_available_at and the
        # exact six-element key.  Let it preempt older Codex decision manuals
        # so yesterday's reviewed deal can actually improve today's quote.
        six_element_preempts_decision = bool(
            six_element_manual
            and _currency(six_element_manual.get("manual_point_yuan"))
            and str(six_element_manual.get("manual_source") or "").lower() == "daily_confirmed_c2b_actuals"
        )
        evidence_decision = (
            None
            if product_memory_used
            or v194159_serving_used
            or enforced_manual_used
            or daily_source_memory_used
            or six_element_preempts_decision
            else self._codex_evidence_decision_manual_override(normalized, query)
        )
        evidence_decision_used = False
        if evidence_decision and _currency(evidence_decision.get("decision_point_yuan")):
            evidence_decision_used = True
            before_decision = _currency(summary.get("statistical_baseline_price"))
            decision_price = float(evidence_decision["decision_point_yuan"])
            summary["pre_evidence_decision_statistical_baseline_price"] = before_decision
            summary["statistical_baseline_price"] = decision_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_36_CODEX_EVIDENCE_DECISION_MANUAL"
            summary["baseline_price_range_low"] = _currency(evidence_decision.get("decision_interval_low_yuan")) or decision_price * 0.94
            summary["baseline_price_range_high"] = _currency(evidence_decision.get("decision_interval_high_yuan")) or decision_price * 1.06
            low = _currency(summary["baseline_price_range_low"]) or decision_price
            high = _currency(summary["baseline_price_range_high"]) or decision_price
            summary["baseline_iqr_ratio"] = (high - low) / decision_price if decision_price else np.nan
            stable_count = int(_currency(evidence_decision.get("stable_evidence_count")) or 0)
            summary["baseline_candidate_count"] = max(int(summary.get("baseline_candidate_count") or 0), stable_count)
            decision_confidence = str(evidence_decision.get("decision_confidence") or "LOW").upper()
            summary["confidence_evidence_bucket"] = decision_confidence.lower()
            summary["codex_evidence_decision_manual_override"] = {
                "enabled": True,
                "decision_key": evidence_decision.get("decision_key"),
                "decision_effective_at": str(evidence_decision.get("decision_effective_at")),
                "decision_point_yuan": decision_price,
                "decision_interval_low_yuan": low,
                "decision_interval_high_yuan": high,
                "decision_confidence": decision_confidence,
                "manual_source": evidence_decision.get("manual_source"),
                "stable_evidence_count": stable_count,
                "exact_internal_evidence_count": int(_currency(evidence_decision.get("exact_internal_evidence_count")) or 0),
                "strict_near_support_count": int(_currency(evidence_decision.get("strict_near_support_count")) or 0),
                "external_listing_count": int(_currency(evidence_decision.get("external_listing_count")) or 0),
                "external_context_status": evidence_decision.get("external_context_status"),
                "external_bridge_ratio": _currency(evidence_decision.get("external_bridge_ratio")),
                "external_c2b_proxy_p50_yuan": _currency(evidence_decision.get("external_c2b_proxy_p50_yuan")),
                "selected_candidate_id": evidence_decision.get("selected_candidate_id"),
                "selected_candidate_match_profile": evidence_decision.get("selected_candidate_match_profile"),
                "selected_candidate_price_yuan": _currency(evidence_decision.get("selected_candidate_price_yuan")),
                "stable_weighted_median_yuan": _currency(evidence_decision.get("stable_weighted_median_yuan")),
                "price_mad_yuan": _currency(evidence_decision.get("price_mad_yuan")),
                "codex_decision_rationale": evidence_decision.get("codex_decision_rationale"),
                "evidence_timeline_json": evidence_decision.get("evidence_timeline_json"),
                "price_role_policy": evidence_decision.get("price_role_policy"),
                "online_use_rule": evidence_decision.get("online_use_rule"),
                "web_search_query": evidence_decision.get("web_search_query"),
                "evidence_closure_status": evidence_decision.get("evidence_closure_status_v194_42")
                or evidence_decision.get("evidence_closure_status_v194_41")
                or evidence_decision.get("evidence_closure_status"),
                "direct_external_context_source_count": int(_currency(evidence_decision.get("direct_external_context_source_count")) or 0),
                "direct_external_strong_context_source_count": int(
                    _currency(evidence_decision.get("direct_external_strong_context_source_count")) or 0
                ),
                "direct_dcd_context_found": bool(_currency(evidence_decision.get("direct_dcd_context_found"))),
                "direct_dcd_strong_context_found": bool(_currency(evidence_decision.get("direct_dcd_strong_context_found"))),
                "direct_dcd_listing_id": evidence_decision.get("direct_dcd_listing_id"),
                "direct_dcd_title": evidence_decision.get("direct_dcd_title"),
                "direct_dcd_listing_price_yuan": _currency(evidence_decision.get("direct_dcd_listing_price_yuan")),
                "direct_dcd_trim_match_level": evidence_decision.get("direct_dcd_trim_match_level"),
                "direct_dcd_match_score": _currency(evidence_decision.get("direct_dcd_match_score")),
                "direct_guazi_context_found": bool(_currency(evidence_decision.get("direct_guazi_context_found"))),
                "direct_guazi_strong_context_found": bool(_currency(evidence_decision.get("direct_guazi_strong_context_found"))),
                "direct_guazi_listing_id": evidence_decision.get("direct_guazi_listing_id"),
                "direct_guazi_title": evidence_decision.get("direct_guazi_title"),
                "direct_guazi_listing_price_yuan": _currency(evidence_decision.get("direct_guazi_listing_price_yuan")),
                "direct_guazi_trim_match_level": evidence_decision.get("direct_guazi_trim_match_level"),
                "direct_guazi_match_score": _currency(evidence_decision.get("direct_guazi_match_score")),
                "direct_guazi_source_url": evidence_decision.get("direct_guazi_source_url"),
                "direct_che168_context_found": bool(_currency(evidence_decision.get("direct_che168_context_found"))),
                "direct_che168_strong_context_found": bool(_currency(evidence_decision.get("direct_che168_strong_context_found"))),
                "direct_che168_listing_id": evidence_decision.get("direct_che168_listing_id"),
                "direct_che168_title": evidence_decision.get("direct_che168_title"),
                "direct_che168_listing_price_yuan": _currency(evidence_decision.get("direct_che168_listing_price_yuan")),
                "direct_che168_trim_match_level": evidence_decision.get("direct_che168_trim_match_level"),
                "direct_che168_match_score": _currency(evidence_decision.get("direct_che168_match_score")),
                "direct_che168_source_url": evidence_decision.get("direct_che168_source_url"),
            }
        else:
            summary["codex_evidence_decision_manual_override"] = {"enabled": False}
        if evidence_decision_used:
            six_element_manual = None
        if six_element_manual and _currency(six_element_manual.get("manual_point_yuan")):
            before_six_manual = _currency(summary.get("statistical_baseline_price"))
            six_manual_price = float(six_element_manual["manual_point_yuan"])
            summary["pre_six_element_manual_statistical_baseline_price"] = before_six_manual
            summary["statistical_baseline_price"] = six_manual_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_43_FULL_SIX_ELEMENT_SOURCE_MANUAL"
            summary["baseline_price_range_low"] = _currency(six_element_manual.get("manual_interval_low_yuan")) or six_manual_price * 0.96
            summary["baseline_price_range_high"] = _currency(six_element_manual.get("manual_interval_high_yuan")) or six_manual_price * 1.04
            low = _currency(summary["baseline_price_range_low"]) or six_manual_price
            high = _currency(summary["baseline_price_range_high"]) or six_manual_price
            summary["baseline_iqr_ratio"] = (high - low) / six_manual_price if six_manual_price else np.nan
            c2b_count = int(_currency(six_element_manual.get("c2b_evidence_count")) or 0)
            b2c_count = int(_currency(six_element_manual.get("b2c_context_count")) or 0)
            summary["baseline_candidate_count"] = max(int(summary.get("baseline_candidate_count") or 0), c2b_count)
            manual_confidence = str(six_element_manual.get("manual_confidence") or "LOW").upper()
            summary["confidence_evidence_bucket"] = manual_confidence.lower()
            summary["six_element_source_manual_override"] = {
                "enabled": True,
                "manual_key": six_element_manual.get("manual_key"),
                "manual_match_level": six_element_manual.get("manual_match_level"),
                "manual_source": six_element_manual.get("manual_source"),
                "manual_point_yuan": six_manual_price,
                "manual_interval_low_yuan": low,
                "manual_interval_high_yuan": high,
                "manual_confidence": manual_confidence,
                "c2b_evidence_count": c2b_count,
                "b2c_context_count": b2c_count,
                "c2b_latest_event_time": str(six_element_manual.get("c2b_latest_event_time")),
                "c2b_mad_yuan": _currency(six_element_manual.get("c2b_mad_yuan")),
                "manual_mad_ratio": _currency(six_element_manual.get("manual_mad_ratio")),
                "internal_c2b_timeline_json": six_element_manual.get("internal_c2b_timeline_json"),
                "b2c_p50_yuan": _currency(six_element_manual.get("b2c_p50_yuan")),
                "b2c_source_families": six_element_manual.get("b2c_source_families"),
                "manual_use_policy": six_element_manual.get("manual_use_policy"),
            }
        else:
            summary["six_element_source_manual_override"] = {"enabled": False}
        memory_override = (
            None
            if product_memory_used
            or v194159_serving_used
            or enforced_manual_used
            or daily_source_memory_used
            or evidence_decision_used
            or six_element_manual
            else self._strict_gap_memory_override(normalized, query)
        )
        if memory_override and _currency(memory_override.get("selected_price_yuan")):
            before_memory = _currency(summary.get("statistical_baseline_price"))
            memory_price = float(memory_override["selected_price_yuan"])
            summary["pre_memory_statistical_baseline_price"] = before_memory
            summary["statistical_baseline_price"] = memory_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_31_STRICT_GAP_MEMORY"
            summary["baseline_price_range_low"] = memory_price * 0.98
            summary["baseline_price_range_high"] = memory_price * 1.02
            summary["baseline_iqr_ratio"] = 0.04
            summary["confidence_evidence_bucket"] = "medium"
            summary["strict_gap_memory_override"] = {
                "enabled": True,
                "memory_key": memory_override.get("memory_key"),
                "memory_available_at": str(memory_override.get("memory_available_at")),
                "selected_candidate_id": memory_override.get("selected_candidate_id"),
                "selected_candidate_event_time": str(memory_override.get("selected_candidate_event_time")),
                "selected_candidate_price_yuan": memory_price,
                "source": memory_override.get("memory_source"),
                "online_rule": memory_override.get("online_rule"),
            }
        else:
            summary["strict_gap_memory_override"] = {"enabled": False}
        vehicle_manual = (
            None
            if product_memory_used
            or v194159_serving_used
            or enforced_manual_used
            or daily_source_memory_used
            or evidence_decision_used
            or six_element_manual
            or memory_override
            else self._codex_vehicle_manual_override(normalized, query)
        )
        if vehicle_manual and _currency(vehicle_manual.get("manual_point_yuan")):
            before_manual = _currency(summary.get("statistical_baseline_price"))
            manual_price = float(vehicle_manual["manual_point_yuan"])
            summary["pre_vehicle_manual_statistical_baseline_price"] = before_manual
            summary["statistical_baseline_price"] = manual_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_33_CODEX_EXPLAINABLE_VEHICLE_MANUAL"
            summary["baseline_price_range_low"] = _currency(vehicle_manual.get("manual_interval_low_yuan")) or manual_price * 0.96
            summary["baseline_price_range_high"] = _currency(vehicle_manual.get("manual_interval_high_yuan")) or manual_price * 1.04
            low = _currency(summary["baseline_price_range_low"]) or manual_price
            high = _currency(summary["baseline_price_range_high"]) or manual_price
            summary["baseline_iqr_ratio"] = (high - low) / manual_price if manual_price else np.nan
            stable_count = int(_currency(vehicle_manual.get("stable_main_cluster_count")) or 0)
            summary["baseline_candidate_count"] = max(int(summary.get("baseline_candidate_count") or 0), stable_count)
            manual_confidence = str(vehicle_manual.get("manual_confidence") or "LOW").upper()
            summary["confidence_evidence_bucket"] = manual_confidence.lower()
            summary["codex_vehicle_manual_override"] = {
                "enabled": True,
                "manual_key": vehicle_manual.get("manual_key"),
                "manual_effective_at": str(vehicle_manual.get("manual_effective_at")),
                "manual_point_yuan": manual_price,
                "manual_interval_low_yuan": low,
                "manual_interval_high_yuan": high,
                "decision_class": vehicle_manual.get("decision_class"),
                "manual_confidence": manual_confidence,
                "raw_internal_c2b_count": int(_currency(vehicle_manual.get("raw_internal_c2b_count")) or 0),
                "stable_main_cluster_count": stable_count,
                "excluded_outlier_count": int(_currency(vehicle_manual.get("excluded_outlier_count")) or 0),
                "latest_confirmed_c2b_yuan": _currency(vehicle_manual.get("latest_confirmed_c2b_yuan")),
                "price_mad_yuan": _currency(vehicle_manual.get("price_mad_yuan")),
                "external_listing_count": int(_currency(vehicle_manual.get("external_listing_count")) or 0),
                "external_listing_p50_yuan": _currency(vehicle_manual.get("external_listing_p50_yuan")),
                "codex_decision_rationale": vehicle_manual.get("codex_decision_rationale"),
                "manual_evidence_summary": vehicle_manual.get("manual_evidence_summary"),
                "internal_evidence_ids": vehicle_manual.get("internal_evidence_ids"),
                "external_evidence_ids": vehicle_manual.get("external_evidence_ids"),
                "evidence_timeline_json": vehicle_manual.get("evidence_timeline_json"),
                "price_role_policy": vehicle_manual.get("price_role_policy"),
                "online_use_rule": vehicle_manual.get("online_use_rule"),
            }
        else:
            summary["codex_vehicle_manual_override"] = {"enabled": False}
        answer_book = (
            None
            if product_memory_used
            or v194159_serving_used
            or enforced_manual_used
            or daily_source_memory_used
            or evidence_decision_used
            or six_element_manual
            or memory_override
            or vehicle_manual
            else self._codex_answer_book_override(normalized, query)
        )
        if answer_book and _currency(answer_book.get("answer_point_yuan")):
            before_answer = _currency(summary.get("statistical_baseline_price"))
            answer_price = float(answer_book["answer_point_yuan"])
            summary["pre_answer_book_statistical_baseline_price"] = before_answer
            summary["statistical_baseline_price"] = answer_price
            summary["baseline_method"] = f"{summary.get('baseline_method')}+V194_32_CODEX_ANSWER_BOOK"
            summary["baseline_price_range_low"] = _currency(answer_book.get("answer_interval_low_yuan")) or answer_price * 0.96
            summary["baseline_price_range_high"] = _currency(answer_book.get("answer_interval_high_yuan")) or answer_price * 1.04
            low = _currency(summary["baseline_price_range_low"]) or answer_price
            high = _currency(summary["baseline_price_range_high"]) or answer_price
            summary["baseline_iqr_ratio"] = (high - low) / answer_price if answer_price else np.nan
            stable_count = int(_currency(answer_book.get("stable_main_cluster_count")) or 0)
            summary["baseline_candidate_count"] = max(int(summary.get("baseline_candidate_count") or 0), stable_count)
            summary["confidence_evidence_bucket"] = "medium" if stable_count >= 2 else "low"
            summary["codex_answer_book_override"] = {
                "enabled": True,
                "answer_key": answer_book.get("answer_key"),
                "answer_available_at": str(answer_book.get("answer_available_at")),
                "answer_point_yuan": answer_price,
                "answer_interval_low_yuan": low,
                "answer_interval_high_yuan": high,
                "stable_main_cluster_count": stable_count,
                "raw_evidence_count": int(_currency(answer_book.get("raw_evidence_count")) or 0),
                "latest_60d_count": int(_currency(answer_book.get("latest_60d_count")) or 0),
                "latest_trend_weight": _currency(answer_book.get("latest_trend_weight")),
                "top_evidence_ids": answer_book.get("top_evidence_ids"),
                "source_policy": answer_book.get("source_policy"),
            }
        else:
            summary["codex_answer_book_override"] = {"enabled": False}
        # T+1 calibration is learned only from completed prior batches.  The
        # v194.159 serving predictor already includes the audited handbook
        # residual route, so do not stack the older v194.126 calibration on top.
        if (summary.get("v194159_serving_override") or {}).get("enabled"):
            summary["daily_market_calibration"] = {
                "enabled": False,
                "display_name": "成交数据市场校准",
                "source_type": "confirmed_transaction_learned_factor",
                "point_price_policy": "not_applied",
                "not_daily_report": True,
                "reason": "SKIPPED_FOR_V194159_SERVING_ROUTE",
            }
        else:
            summary = self._apply_daily_market_calibration(summary, normalized)
        summary = self._apply_v194225_c2b_router(
            summary,
            normalized,
            direct_prior=direct_prior,
            v194159_serving=v194159_serving,
        )
        summary = self._apply_low_price_old_high_mileage_guard(summary, normalized)
        summary = self._apply_v194244_c2b_market_policy(
            summary,
            normalized,
            direct_prior=direct_prior,
            v194159_serving=v194159_serving,
        )
        summary = self._apply_v194263_broad_support_risk_policy(summary, normalized)
        summary = self._apply_v194268_c2b_bucket_consensus_guard(summary, normalized)
        summary = self._apply_dongchedi_current_c2b_market_prior(
            summary,
            payload=payload,
            query=query,
            normalized=normalized,
        )
        summary = self._apply_sparse_same_trim_c2b_floor_guard(summary, normalized)
        if normalized.get("used_as_b2c_bridge_context"):
            summary["c2b_current_support_consensus_guard"] = {
                "enabled": False,
                "reason": "SKIPPED_FOR_B2C_BRIDGE_CONTEXT",
            }
        else:
            summary = self._apply_c2b_current_support_consensus_guard(summary, normalized)
        confidence, reasons = _confidence(summary, candidates)
        if (summary.get("product_memory_override") or {}).get("enabled"):
            product_confidence = str(summary.get("confidence_evidence_bucket") or "low").upper()
            confidence = product_confidence if product_confidence in {"HIGH", "MEDIUM", "LOW"} else "LOW"
            reasons.append("V194_121_PRODUCT_MEMORY_Q30_MATCHED")
        if (summary.get("enforced_candidate_manual_override") or {}).get("enabled"):
            enforced_meta_for_conf = summary.get("enforced_candidate_manual_override") or {}
            confidence = "HIGH" if enforced_meta_for_conf.get("has_legal_5pct_candidate_source") else "LOW"
            reasons.append("V194_92_ENFORCED_LEGAL_CANDIDATE_MANUAL_MATCHED")
        if (summary.get("codex_evidence_decision_manual_override") or {}).get("enabled"):
            decision_confidence = str((summary.get("codex_evidence_decision_manual_override") or {}).get("decision_confidence") or "LOW")
            confidence = decision_confidence if decision_confidence in {"HIGH", "MEDIUM", "LOW"} else "LOW"
            reasons.append("V194_36_CODEX_EVIDENCE_DECISION_MANUAL_MATCHED")
        if (summary.get("six_element_source_manual_override") or {}).get("enabled"):
            manual_confidence = str((summary.get("six_element_source_manual_override") or {}).get("manual_confidence") or "LOW")
            if manual_confidence in {"HIGH", "MEDIUM", "LOW"}:
                confidence = manual_confidence
            else:
                confidence = "LOW"
            reasons.append("V194_43_FULL_SIX_ELEMENT_SOURCE_MANUAL_MATCHED")
        if (summary.get("strict_gap_memory_override") or {}).get("enabled"):
            confidence = "MEDIUM" if confidence in {"LOW", "MANUAL"} else confidence
            reasons.append("V194_31_STRICT_GAP_MEMORY_MATCHED")
        if (summary.get("codex_vehicle_manual_override") or {}).get("enabled"):
            manual_confidence = str((summary.get("codex_vehicle_manual_override") or {}).get("manual_confidence") or "LOW")
            confidence = manual_confidence if manual_confidence in {"HIGH", "MEDIUM", "LOW"} else "LOW"
            reasons.append("V194_33_CODEX_VEHICLE_MANUAL_MATCHED")
        if (summary.get("codex_answer_book_override") or {}).get("enabled"):
            confidence = "MEDIUM" if int((summary.get("codex_answer_book_override") or {}).get("stable_main_cluster_count") or 0) >= 2 else "LOW"
            reasons.append("V194_32_CODEX_ANSWER_BOOK_MATCHED")
        if query.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION" and confidence == "HIGH":
            confidence = "MEDIUM"
            reasons.append("SYSTEM_DEFAULT_CONDITION_NOT_INSPECTION_CONFIRMED")
        final_price = _currency(summary.get("statistical_baseline_price"))
        if not final_price or final_price <= 0:
            return self._fallback_quote(
                payload,
                query,
                normalized,
                "NO_C2B_POINT_BASELINE",
                candidates=candidates,
                direct_prior=direct_prior,
                legacy_predictor=legacy_predictor,
            )
        interval = _interval_from_summary(summary, confidence)
        universal_anchor_guard = self._apply_universal_market_anchor_guard(
            query=query,
            role="c2b",
            price_yuan=float(final_price),
            interval_low_yuan=_currency(interval.get("low")),
            interval_high_yuan=_currency(interval.get("high")),
            price_hint_yuan=float(final_price),
        )
        v194244_pre_anchor_meta = summary.get("v194244_c2b_market_policy") or {}
        v194244_pre_anchor_flags = v194244_pre_anchor_meta.get("flags") if isinstance(v194244_pre_anchor_meta, dict) else []
        v194263_pre_anchor_meta = summary.get("v194263_broad_support_risk_policy") or {}
        v194263_pre_anchor_flags = v194263_pre_anchor_meta.get("flags") if isinstance(v194263_pre_anchor_meta, dict) else []
        v194244_risk_cap_applied = bool(
            v194244_pre_anchor_meta.get("enabled")
            and any(("discount" in str(flag) or "cap" in str(flag)) for flag in (v194244_pre_anchor_flags or []))
        )
        v194263_risk_cap_applied = bool(
            v194263_pre_anchor_meta.get("enabled")
            and any(("cap" in str(flag) or "low_tail" in str(flag)) for flag in (v194263_pre_anchor_flags or []))
        )
        if (
            (v194244_risk_cap_applied or v194263_risk_cap_applied)
            and universal_anchor_guard.get("enabled")
            and universal_anchor_guard.get("applied")
            and universal_anchor_guard.get("action") == "clamped_up_to_anchor_low"
        ):
            universal_anchor_guard = {
                **universal_anchor_guard,
                "applied": False,
                "action": "skipped_upward_clamp_after_v194244_risk_cap",
                "guarded_price_yuan": float(final_price),
                "adjustment_yuan": 0.0,
                "original_action": "clamped_up_to_anchor_low",
                "original_guarded_price_yuan": universal_anchor_guard.get("guarded_price_yuan"),
                "skip_reason": "V194_244_OR_V194_263_RISK_CAP_HAS_HIGHER_PRIORITY_THAN_UPWARD_MARKET_ANCHOR",
            }
        v194268_pre_anchor_meta = summary.get("v194268_bucket_consensus_guard") or {}
        low_quality_anchor = (
            universal_anchor_guard.get("enabled")
            and universal_anchor_guard.get("applied")
            and int(_currency(universal_anchor_guard.get("row_count")) or 0) <= 3
            and (_currency(universal_anchor_guard.get("effective_weight")) or 0.0) < 1.5
            and str(universal_anchor_guard.get("match_level") or "").startswith("same_")
            and bool(v194268_pre_anchor_meta.get("enabled"))
        )
        if low_quality_anchor:
            universal_anchor_guard = {
                **universal_anchor_guard,
                "applied": False,
                "action": "skipped_low_quality_anchor_after_bucket_consensus",
                "guarded_price_yuan": float(final_price),
                "adjustment_yuan": 0.0,
                "original_action": universal_anchor_guard.get("action"),
                "original_guarded_price_yuan": universal_anchor_guard.get("guarded_price_yuan"),
                "skip_reason": "V194_269_BUCKET_CONSENSUS_HAS_HIGHER_EVIDENCE_QUALITY_THAN_SPARSE_UNIVERSAL_ANCHOR",
            }
        if universal_anchor_guard.get("enabled"):
            summary["universal_market_anchor_guard"] = universal_anchor_guard
        if universal_anchor_guard.get("enabled") and universal_anchor_guard.get("applied"):
            pre_anchor_price = float(final_price)
            final_price = float(universal_anchor_guard.get("guarded_price_yuan") or final_price)
            interval["low"] = float(universal_anchor_guard.get("interval_low_yuan") or interval["low"])
            interval["high"] = float(universal_anchor_guard.get("interval_high_yuan") or interval["high"])
            interval["evidence_low"] = interval["low"]
            interval["evidence_high"] = interval["high"]
            interval["width_policy"] = f"{interval.get('width_policy') or confidence}_PLUS_UNIVERSAL_MARKET_ANCHOR_GUARD"
            summary["pre_universal_market_anchor_statistical_baseline_price"] = pre_anchor_price
            summary["statistical_baseline_price"] = final_price
            summary["baseline_p25"] = min(float(summary.get("baseline_p25") or final_price), interval["low"])
            summary["baseline_p75"] = max(float(summary.get("baseline_p75") or final_price), interval["high"])
            reasons.append("V194_234_UNIVERSAL_MARKET_ANCHOR_GUARD_APPLIED")
        selected_comparables = _display_candidate_records(candidates)
        external_rows = (
            candidates[candidates["price_role"].eq("EXTERNAL_B2C_LISTING")].head(10).to_dict("records")
            if not candidates.empty and "price_role" in candidates
            else []
        )
        external_market_evidence = [_candidate_record(record) for record in external_rows]
        ledger = evidence_ledger(query, candidates, summary)
        ledger["external_market_evidence"] = external_market_evidence
        price_wan = round(final_price / 10000.0, 6)
        range_wan = [round(float(interval["low"]) / 10000.0, 6), round(float(interval["high"]) / 10000.0, 6)]
        duplicate_rows_removed = int(
            sum(max(0, int(record.get("duplicate_group_size") or 1) - 1) for record in selected_comparables)
        )
        candidate_calibration = summary.get("candidate_calibration") or {}
        pre_calibration_price = _currency(summary.get("pre_calibration_statistical_baseline_price")) or final_price
        raw_log_adjustment = _as_float(candidate_calibration.get("raw_log_residual_adjustment"), 0.0)
        applied_log_adjustment = _as_float(candidate_calibration.get("applied_log_residual_adjustment"), 0.0)
        raw_residual_ratio = float(np.exp(raw_log_adjustment) - 1.0) if candidate_calibration.get("enabled") else 0.0
        applied_residual_ratio = float(np.exp(applied_log_adjustment) - 1.0) if candidate_calibration.get("enabled") else 0.0
        candidate_calibration_amount = final_price - pre_calibration_price if candidate_calibration.get("enabled") else 0.0
        product_memory_meta = summary.get("product_memory_override") or {}
        enforced_meta = summary.get("enforced_candidate_manual_override") or {}
        decision_meta = summary.get("codex_evidence_decision_manual_override") or {}
        six_element_meta = summary.get("six_element_source_manual_override") or {}
        memory_meta = summary.get("strict_gap_memory_override") or {}
        vehicle_manual_meta = summary.get("codex_vehicle_manual_override") or {}
        answer_meta = summary.get("codex_answer_book_override") or {}
        daily_source_memory_meta = summary.get("daily_source_memory_override") or {}
        daily_market_meta = summary.get("daily_market_calibration") or {}
        v194159_meta = summary.get("v194159_serving_override") or {}
        v194225_router_meta = summary.get("v194225_c2b_router") or {}
        low_price_tail_guard_meta = summary.get("low_price_old_high_mileage_guard") or {}
        v194244_market_policy_meta = summary.get("v194244_c2b_market_policy") or {}
        v194263_broad_support_meta = summary.get("v194263_broad_support_risk_policy") or {}
        v194268_bucket_guard_meta = summary.get("v194268_bucket_consensus_guard") or {}
        dongchedi_current_c2b_market_prior_meta = summary.get("dongchedi_current_c2b_market_prior") or {}
        sparse_same_trim_c2b_floor_meta = summary.get("sparse_same_trim_c2b_floor_guard") or {}
        c2b_current_support_consensus_meta = summary.get("c2b_current_support_consensus_guard") or {}
        universal_anchor_meta = summary.get("universal_market_anchor_guard") or universal_anchor_guard or {}
        product_memory_adjustment_amount = final_price - (_currency(summary.get("pre_product_memory_statistical_baseline_price")) or final_price) if product_memory_meta.get("enabled") else 0.0
        enforced_adjustment_amount = final_price - (_currency(summary.get("pre_enforced_candidate_manual_statistical_baseline_price")) or final_price) if enforced_meta.get("enabled") else 0.0
        decision_adjustment_amount = final_price - (_currency(summary.get("pre_evidence_decision_statistical_baseline_price")) or final_price) if decision_meta.get("enabled") else 0.0
        six_element_adjustment_amount = final_price - (_currency(summary.get("pre_six_element_manual_statistical_baseline_price")) or final_price) if six_element_meta.get("enabled") else 0.0
        memory_adjustment_amount = final_price - (_currency(summary.get("pre_memory_statistical_baseline_price")) or final_price) if memory_meta.get("enabled") else 0.0
        vehicle_manual_adjustment_amount = final_price - (_currency(summary.get("pre_vehicle_manual_statistical_baseline_price")) or final_price) if vehicle_manual_meta.get("enabled") else 0.0
        answer_adjustment_amount = final_price - (_currency(summary.get("pre_answer_book_statistical_baseline_price")) or final_price) if answer_meta.get("enabled") else 0.0
        daily_source_memory_adjustment_amount = (
            final_price - (_currency(summary.get("pre_daily_source_memory_statistical_baseline_price")) or final_price)
            if daily_source_memory_meta.get("enabled")
            else 0.0
        )
        daily_market_adjustment_amount = (
            (_currency(daily_market_meta.get("after_price_yuan")) or final_price)
            - (_currency(daily_market_meta.get("before_price_yuan")) or final_price)
            if daily_market_meta.get("enabled")
            else 0.0
        )
        v194225_router_adjustment_amount = (
            final_price - (_currency(summary.get("pre_v194225_router_statistical_baseline_price")) or final_price)
            if v194225_router_meta.get("enabled")
            else 0.0
        )
        low_price_tail_guard_adjustment_amount = (
            final_price - (_currency(summary.get("pre_low_price_old_high_mileage_guard_price_yuan")) or final_price)
            if low_price_tail_guard_meta.get("enabled")
            else 0.0
        )
        v194244_market_policy_adjustment_amount = (
            final_price - (_currency(summary.get("pre_v194244_market_policy_statistical_baseline_price")) or final_price)
            if v194244_market_policy_meta.get("enabled")
            else 0.0
        )
        v194263_broad_support_adjustment_amount = (
            final_price - (_currency(summary.get("pre_v194263_broad_support_risk_price_yuan")) or final_price)
            if v194263_broad_support_meta.get("enabled")
            else 0.0
        )
        v194268_bucket_guard_adjustment_amount = (
            final_price - (_currency(summary.get("pre_v194268_bucket_consensus_price_yuan")) or final_price)
            if v194268_bucket_guard_meta.get("enabled")
            else 0.0
        )
        dongchedi_current_c2b_market_prior_adjustment_amount = (
            final_price - (_currency(summary.get("pre_dongchedi_current_c2b_market_prior_price_yuan")) or final_price)
            if dongchedi_current_c2b_market_prior_meta.get("enabled")
            else 0.0
        )
        sparse_same_trim_c2b_floor_adjustment_amount = (
            final_price - (_currency(summary.get("pre_sparse_same_trim_c2b_floor_price_yuan")) or final_price)
            if sparse_same_trim_c2b_floor_meta.get("enabled")
            else 0.0
        )
        c2b_current_support_consensus_adjustment_amount = (
            final_price - (_currency(summary.get("pre_c2b_current_support_consensus_price_yuan")) or final_price)
            if c2b_current_support_consensus_meta.get("enabled")
            else 0.0
        )
        universal_anchor_adjustment_amount = (
            final_price - (_currency(summary.get("pre_universal_market_anchor_statistical_baseline_price")) or final_price)
            if universal_anchor_meta.get("applied")
            else 0.0
        )
        business_explanation = _business_explanation(
            query=query,
            final_price=final_price,
            interval=interval,
            summary=summary,
            confidence=confidence,
            reasons=reasons,
            candidates=candidates,
            selected_comparables=selected_comparables,
        )
        ledger["business_explanation"] = business_explanation
        ledger["product_memory_manual"] = product_memory_meta
        ledger["enforced_candidate_manual"] = enforced_meta
        ledger["codex_evidence_decision_manual"] = decision_meta
        ledger["six_element_source_manual"] = six_element_meta
        ledger["codex_vehicle_manual"] = vehicle_manual_meta
        ledger["daily_source_memory"] = daily_source_memory_meta
        ledger["daily_market_calibration"] = daily_market_meta
        ledger["v194225_c2b_router"] = v194225_router_meta
        ledger["low_price_old_high_mileage_guard"] = low_price_tail_guard_meta
        ledger["v194244_c2b_market_policy"] = v194244_market_policy_meta
        ledger["v194263_broad_support_risk_policy"] = v194263_broad_support_meta
        ledger["v194268_bucket_consensus_guard"] = v194268_bucket_guard_meta
        ledger["dongchedi_current_c2b_market_prior"] = dongchedi_current_c2b_market_prior_meta
        ledger["sparse_same_trim_c2b_floor_guard"] = sparse_same_trim_c2b_floor_meta
        ledger["c2b_current_support_consensus_guard"] = c2b_current_support_consensus_meta
        ledger["universal_market_anchor_guard"] = universal_anchor_meta
        return {
            "success": True,
            "quote_id": normalized.get("query_uid"),
            "pricing_engine_used": "V194",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "policy_version": POLICY_VERSION,
            "evidence_card_version": EVIDENCE_CARD_VERSION,
            "final_price": round(final_price, 2),
            "display_price_wan": round(final_price / 10000.0, 2),
            "c2bPrice": price_wan,
            "c2b_price": price_wan,
            "targetC2B": price_wan,
            "c2bRange": range_wan,
            "price_result": {
                "final_price": round(final_price, 2),
                "price_low": interval["low"],
                "price_high": interval["high"],
                "confidence": confidence,
                "reasonableness_level": "SUPPORTED_WITH_EVIDENCE"
                if confidence in {"HIGH", "MEDIUM"}
                else "SUPPORTED_WITH_LIMITATIONS",
                "display_type": "AUTO_SINGLE_POINT" if confidence in {"HIGH", "MEDIUM"} else "LOW_CONFIDENCE_REFERENCE",
            },
            "interval": interval,
            "confidence": confidence,
            "confidence_reasons": reasons,
            "quote_decision": "AUTO_SINGLE_POINT" if confidence in {"HIGH", "MEDIUM"} else "LOW_CONFIDENCE_SINGLE_POINT",
            "selected_comparables": selected_comparables,
            "external_market_evidence": external_market_evidence,
            "price_trace": {
                "statistical_baseline_price": round(final_price, 2),
                "pre_calibration_statistical_baseline_price": round(pre_calibration_price, 2),
                "baseline_method": summary.get("baseline_method"),
                "baseline_candidate_count": summary.get("baseline_candidate_count"),
                "baseline_iqr_ratio": summary.get("baseline_iqr_ratio"),
                "raw_residual_ratio": raw_residual_ratio,
                "base_residual_adjustment_amount": round(candidate_calibration_amount, 2),
                "series_calibration_adjustment_amount": 0.0,
                "guard_adjustment_amount": round(product_memory_adjustment_amount + enforced_adjustment_amount + decision_adjustment_amount + six_element_adjustment_amount + memory_adjustment_amount + vehicle_manual_adjustment_amount + answer_adjustment_amount + daily_source_memory_adjustment_amount + daily_market_adjustment_amount + v194225_router_adjustment_amount + low_price_tail_guard_adjustment_amount + v194244_market_policy_adjustment_amount + v194263_broad_support_adjustment_amount + v194268_bucket_guard_adjustment_amount + dongchedi_current_c2b_market_prior_adjustment_amount + sparse_same_trim_c2b_floor_adjustment_amount + c2b_current_support_consensus_adjustment_amount + universal_anchor_adjustment_amount, 2),
                "final_residual_ratio": applied_residual_ratio,
                "final_residual_amount": round(
                    candidate_calibration_amount + product_memory_adjustment_amount + enforced_adjustment_amount + decision_adjustment_amount + six_element_adjustment_amount + memory_adjustment_amount + vehicle_manual_adjustment_amount + answer_adjustment_amount + daily_source_memory_adjustment_amount + daily_market_adjustment_amount + v194225_router_adjustment_amount + low_price_tail_guard_adjustment_amount + v194244_market_policy_adjustment_amount + v194263_broad_support_adjustment_amount + v194268_bucket_guard_adjustment_amount + dongchedi_current_c2b_market_prior_adjustment_amount + sparse_same_trim_c2b_floor_adjustment_amount + c2b_current_support_consensus_adjustment_amount + universal_anchor_adjustment_amount,
                    2,
                ),
                "residual_policy": (
                    "V194_29_CANDIDATE_SUMMARY_RESIDUAL_CALIBRATION"
                    if candidate_calibration.get("enabled")
                    else f"NOT_APPLIED_{candidate_calibration.get('reason') or 'NO_CALIBRATION'}"
                ),
                "candidate_calibrator_version": candidate_calibration.get("version"),
                "candidate_calibrator_raw_log_adjustment": raw_log_adjustment,
                "candidate_calibrator_allowed_log_adjustment": candidate_calibration.get("allowed_log_residual_adjustment"),
                "candidate_calibrator_applied_log_adjustment": applied_log_adjustment,
                "direct_price_prior": round(float(direct_prior), 2) if direct_prior else None,
                "trusted_cluster_price": None,
                "listwise_ranker_used": bool(summary.get("listwise_ranker_used")),
                "b2c_to_c2b_bridge_ratio": bridge["ratio"] if bridge else None,
                "b2c_to_c2b_bridge_level": bridge["level"] if bridge else None,
                "product_memory_override": product_memory_meta,
                "v194159_serving_override": v194159_meta,
                "enforced_candidate_manual_override": enforced_meta,
                "codex_evidence_decision_manual_override": decision_meta,
                "six_element_source_manual_override": six_element_meta,
                "strict_gap_memory_override": memory_meta,
                "codex_vehicle_manual_override": vehicle_manual_meta,
                "codex_answer_book_override": answer_meta,
                "daily_source_memory_override": daily_source_memory_meta,
                "daily_market_calibration": daily_market_meta,
                "v194225_c2b_router": v194225_router_meta,
                "low_price_old_high_mileage_guard": low_price_tail_guard_meta,
                "v194244_c2b_market_policy": v194244_market_policy_meta,
                "v194263_broad_support_risk_policy": v194263_broad_support_meta,
                "v194268_bucket_consensus_guard": v194268_bucket_guard_meta,
                "dongchedi_current_c2b_market_prior": dongchedi_current_c2b_market_prior_meta,
                "sparse_same_trim_c2b_floor_guard": sparse_same_trim_c2b_floor_meta,
                "c2b_current_support_consensus_guard": c2b_current_support_consensus_meta,
                "universal_market_anchor_guard": universal_anchor_meta,
            },
            "evidence_summary": {
                "candidate_count": int(len(candidates)),
                "unique_candidate_count": int(len(candidates)),
                "duplicate_candidate_rows_removed_from_selected_pool": duplicate_rows_removed,
                "warehouse_rows_before_runtime_dedup": self.warehouse_rows_before_runtime_dedup,
                "warehouse_rows_after_runtime_dedup": self.warehouse_rows_after_runtime_dedup,
                "daily_confirmed_actual_rows_loaded": self.daily_confirmed_actual_rows,
                "daily_confirmed_b2c_actual_rows_loaded": self.daily_confirmed_b2c_actual_rows,
                "candidate_calibrator_loaded": self.candidate_calibrator is not None,
                "product_memory_rows_loaded": int(len(self.product_memory.history)) if self.product_memory is not None else 0,
                "product_memory_used": bool(product_memory_meta.get("enabled")),
                "v194159_serving_used": bool(v194159_meta.get("enabled")),
                "v194159_serving_version": v194159_meta.get("version"),
                "v194159_serving_route": v194159_meta.get("route"),
                "product_memory_policy_version": product_memory_meta.get("policy_version"),
                "product_memory_match_level": product_memory_meta.get("match_level"),
                "product_memory_neighbor_count": product_memory_meta.get("neighbor_count"),
                "product_memory_q30_yuan": product_memory_meta.get("q30_yuan"),
                "product_memory_time_policy": product_memory_meta.get("time_policy"),
                "universal_market_anchor_guard_used": bool(universal_anchor_meta.get("enabled")),
                "universal_market_anchor_guard_applied": bool(universal_anchor_meta.get("applied")),
                "universal_market_anchor_match_level": universal_anchor_meta.get("match_level"),
                "enforced_candidate_manual_rows_loaded": len(self.enforced_candidate_manual),
                "enforced_candidate_manual_used": bool(enforced_meta.get("enabled")),
                "enforced_candidate_manual_match_level": enforced_meta.get("manual_match_level"),
                "enforced_candidate_manual_source": enforced_meta.get("manual_source"),
                "enforced_candidate_manual_has_legal_5pct_candidate": enforced_meta.get("has_legal_5pct_candidate_source"),
                "codex_evidence_decision_manual_rows_loaded": len(self.codex_evidence_decision_manual),
                "codex_evidence_decision_manual_used": bool(decision_meta.get("enabled")),
                "codex_evidence_decision_manual_confidence": decision_meta.get("decision_confidence"),
                "codex_evidence_decision_manual_exact_internal_evidence_count": decision_meta.get("exact_internal_evidence_count"),
                "codex_evidence_decision_manual_external_listing_count": decision_meta.get("external_listing_count"),
                "six_element_source_manual_rows_loaded": len(self.six_element_source_manual),
                "six_element_source_manual_used": bool(six_element_meta.get("enabled")),
                "six_element_source_manual_confidence": six_element_meta.get("manual_confidence"),
                "six_element_source_manual_c2b_evidence_count": six_element_meta.get("c2b_evidence_count"),
                "six_element_source_manual_b2c_context_count": six_element_meta.get("b2c_context_count"),
                "strict_gap_memory_rows_loaded": len(self.strict_gap_memory),
                "strict_gap_memory_used": bool(memory_meta.get("enabled")),
                "strict_gap_memory_candidate_id": memory_meta.get("selected_candidate_id"),
                "codex_vehicle_manual_rows_loaded": len(self.codex_vehicle_manual),
                "codex_vehicle_manual_used": bool(vehicle_manual_meta.get("enabled")),
                "codex_vehicle_manual_confidence": vehicle_manual_meta.get("manual_confidence"),
                "codex_vehicle_manual_internal_evidence_count": vehicle_manual_meta.get("stable_main_cluster_count"),
                "codex_vehicle_manual_external_listing_count": vehicle_manual_meta.get("external_listing_count"),
                "codex_answer_book_rows_loaded": len(self.codex_answer_book),
                "codex_answer_book_used": bool(answer_meta.get("enabled")),
                "codex_answer_book_evidence_count": answer_meta.get("stable_main_cluster_count"),
                "daily_source_memory_rows_loaded": len(self.daily_source_memory),
                "daily_source_memory_used": bool(daily_source_memory_meta.get("enabled")),
                "daily_source_memory_match_level": daily_source_memory_meta.get("memory_match_level"),
                "daily_source_memory_source_file": daily_source_memory_meta.get("source_file"),
                "daily_market_calibration_used": bool(daily_market_meta.get("enabled")),
                "daily_market_calibration_factor": daily_market_meta.get("factor"),
                "daily_market_calibration_price_band": daily_market_meta.get("price_band"),
                "v194244_c2b_market_policy_used": bool(v194244_market_policy_meta.get("enabled")),
                "v194244_c2b_market_policy_flags": v194244_market_policy_meta.get("flags"),
                "v194244_c2b_market_policy_c2_support_count": (
                    (v194244_market_policy_meta.get("support") or {}).get("c2_count")
                    if isinstance(v194244_market_policy_meta.get("support"), dict)
                    else None
                ),
                "v194244_c2b_market_policy_b2_support_count": (
                    (v194244_market_policy_meta.get("support") or {}).get("b2_count")
                    if isinstance(v194244_market_policy_meta.get("support"), dict)
                    else None
                ),
                "v194263_broad_support_risk_policy_used": bool(v194263_broad_support_meta.get("enabled")),
                "v194263_broad_support_risk_policy_flags": v194263_broad_support_meta.get("flags"),
                "v194263_broad_support_count": (
                    (v194263_broad_support_meta.get("support") or {}).get("support_count")
                    if isinstance(v194263_broad_support_meta.get("support"), dict)
                    else None
                ),
                "v194263_broad_support_q10": (
                    (v194263_broad_support_meta.get("support") or {}).get("support_q10")
                    if isinstance(v194263_broad_support_meta.get("support"), dict)
                    else None
                ),
                "v194263_broad_support_q20": (
                    (v194263_broad_support_meta.get("support") or {}).get("support_q20")
                    if isinstance(v194263_broad_support_meta.get("support"), dict)
                    else None
                ),
                "v194263_broad_support_q35": (
                    (v194263_broad_support_meta.get("support") or {}).get("support_q35")
                    if isinstance(v194263_broad_support_meta.get("support"), dict)
                    else None
                ),
                "v194268_bucket_consensus_guard_used": bool(v194268_bucket_guard_meta.get("enabled")),
                "v194268_bucket_consensus_guard_flags": v194268_bucket_guard_meta.get("flags"),
                "dongchedi_current_c2b_market_prior_used": bool(dongchedi_current_c2b_market_prior_meta.get("enabled")),
                "dongchedi_current_c2b_market_prior_flags": dongchedi_current_c2b_market_prior_meta.get("flags"),
                "dongchedi_current_c2b_market_prior_support_count": (
                    (dongchedi_current_c2b_market_prior_meta.get("support") or {}).get("support_count")
                    if isinstance(dongchedi_current_c2b_market_prior_meta.get("support"), dict)
                    else None
                ),
                "dongchedi_current_c2b_market_prior_match_level": (
                    (dongchedi_current_c2b_market_prior_meta.get("support") or {}).get("match_level")
                    if isinstance(dongchedi_current_c2b_market_prior_meta.get("support"), dict)
                    else None
                ),
                "candidate_calibrator_load_error": self.candidate_calibrator_load_error or None,
                "baseline_candidate_count": int(summary.get("baseline_candidate_count") or 0),
                "same_trim_candidate_count": int(candidates.get("same_trim", pd.Series(0, index=candidates.index)).sum()) if not candidates.empty else 0,
                "same_configuration_across_year_count": int(candidates.get("same_configuration_across_year", pd.Series(0, index=candidates.index)).sum()) if not candidates.empty else 0,
                "same_powertrain_candidate_count": int(candidates.get("same_powertrain", pd.Series(0, index=candidates.index)).sum()) if not candidates.empty else 0,
                "c2b_point_baseline_uses_only_internal_c2b": True,
                "b2c_and_web_are_not_direct_c2b_baseline": True,
                "b2c_to_c2b_bridge_used": bool(bridge and summary.get("baseline_method", "").startswith("B2C_TO_C2B")),
                "price_role_policy_version": "v194_price_role_quality_policy_v1",
                "trusted_homogeneous_cluster_used": False,
                "persisted_full_history_cluster_used_for_price": False,
                "temporal_listwise_ranker_loaded": self.listwise_ranker is not None,
                "temporal_listwise_ranker_load_error": self.listwise_ranker_load_error or None,
                "condition_assumption": query.get("condition_assumption"),
                "external_market_candidate_count": int(
                    candidates["price_role"].eq("EXTERNAL_B2C_LISTING").sum()
                ) if not candidates.empty and "price_role" in candidates else 0,
                "external_search_status": "VALIDATED_CURRENT_SNAPSHOT_ACTIVE",
                "live_web_search_used_for_point_price": False,
            },
            "evidence_card": ledger,
            "business_explanation": business_explanation,
            "risk_warnings": self._risk_warnings(confidence, reasons, query),
            "normalized_query": normalized,
            "reason": "v194使用严格历史C2B证据仓库完成as-of召回和可复算证据链。",
        }

    def _fallback_quote(
        self,
        payload: dict[str, Any],
        query: dict[str, Any],
        normalized: dict[str, Any],
        reason: str,
        *,
        candidates: pd.DataFrame | None = None,
        direct_prior: float | None = None,
        legacy_predictor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        candidates = candidates if candidates is not None else pd.DataFrame()
        selected_comparables = _display_candidate_records(candidates)
        external_rows = (
            candidates[candidates["price_role"].eq("EXTERNAL_B2C_LISTING")].head(10).to_dict("records")
            if not candidates.empty and "price_role" in candidates
            else []
        )
        external_market_evidence = [_candidate_record(record) for record in external_rows]
        fallback_source = "DIRECT_PRICE_PRIOR"
        fallback_price = _currency(direct_prior)
        bridge = self._external_bridge(normalized, candidates)
        if bridge:
            bridge_indices = bridge["rows"].index
            candidates.loc[bridge_indices, "bridge_ratio_used"] = bridge["ratio"]
            candidates.loc[bridge_indices, "converted_c2b_price"] = bridge["rows"]["converted_c2b_price"].to_numpy()
            fallback_price = float(bridge["price"])
            fallback_source = f"B2C_TO_C2B_{bridge['level']}"
        guide_anchor = None
        if STATIC_GUIDE_FALLBACK_ENABLED:
            guide_anchor = self._guide_depreciation_anchor(normalized)
            if not guide_anchor:
                guide_anchor = self._online_catalog_guide_anchor(query, normalized)
        # Guard a direct model against unsupported extrapolation on newly
        # launched / rare luxury trims. A verified MSRP plus a historical
        # series-age C2B ratio is a more defensible low-trust reference than
        # a model extrapolating from unrelated low-price observations.
        if guide_anchor and not bridge and (
            not fallback_price
            or fallback_price <= 0
            or fallback_price < guide_anchor["guide_price"] * 0.35
            or fallback_price > guide_anchor["guide_price"] * 1.10
        ):
            fallback_price = float(guide_anchor["price"])
            fallback_source = "STATIC_GUIDE_DEPRECIATION_FALLBACK"
        legacy_error = ""
        if (not fallback_price or fallback_price <= 0) and legacy_predictor is not None:
            try:
                legacy = legacy_predictor(payload)
                legacy_price = _currency((legacy.get("price") or {}).get("point"))
                if legacy_price and legacy_price > 0:
                    fallback_price = legacy_price
                    fallback_source = "LEGACY_MODEL_FALLBACK"
            except Exception as exc:
                legacy_error = str(exc)
        if not fallback_price or fallback_price <= 0:
            fallback_price = _currency(self.brand_medians.get(str(normalized.get("brand_key") or "")))
            fallback_source = "BRAND_C2B_MEDIAN_FALLBACK"
        if not fallback_price or fallback_price <= 0:
            fallback_price = self.global_median
            fallback_source = "GLOBAL_C2B_MEDIAN_LAST_RESORT"
        selected_comparables = _display_candidate_records(candidates)
        external_rows = (
            candidates[candidates["price_role"].eq("EXTERNAL_B2C_LISTING")].head(10).to_dict("records")
            if not candidates.empty and "price_role" in candidates
            else []
        )
        external_market_evidence = [_candidate_record(record) for record in external_rows]
        evidence_low = fallback_price * 0.75
        evidence_high = fallback_price * 1.25
        low = fallback_price * 0.86
        high = fallback_price * 1.14
        interval = {
            "low": round(low, 2),
            "high": round(high, 2),
            "evidence_low": round(evidence_low, 2),
            "evidence_high": round(evidence_high, 2),
            "type": "PRACTICAL_LOW_TRUST_INTERVAL_WITH_EVIDENCE_RANGE",
            "width_policy": "LOW_CAP_14%",
        }
        price_wan = round(fallback_price / 10000.0, 6)
        range_wan = [round(low / 10000.0, 6), round(high / 10000.0, 6)]
        warnings = ["缺少严格同款成交证据，本次为低信任单点报价，区间已显著加宽。"]
        if query.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION":
            warnings.append("当前按系统默认良好车况估算，实际检测后可能调整。")
        if query.get("year_consistency_warning"):
            warnings.append(str(query["year_consistency_warning"]))
        fallback_summary = {
            "statistical_baseline_price": fallback_price,
            "baseline_method": fallback_source,
            "baseline_candidate_count": 0,
            "baseline_price_range_low": evidence_low,
            "baseline_price_range_high": evidence_high,
            "confidence_evidence_bucket": "low",
        }
        business_explanation = _business_explanation(
            query=query,
            final_price=fallback_price,
            interval=interval,
            summary=fallback_summary,
            confidence="LOW",
            reasons=[reason, fallback_source, "LOW_TRUST_ALWAYS_QUOTE_POLICY"],
            candidates=candidates,
            selected_comparables=selected_comparables,
            fallback_source=fallback_source,
        )
        return {
            "success": True,
            "quote_id": normalized.get("query_uid"),
            "pricing_engine_used": "V194",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "policy_version": POLICY_VERSION,
            "evidence_card_version": EVIDENCE_CARD_VERSION,
            "final_price": round(fallback_price, 2),
            "display_price_wan": round(fallback_price / 10000.0, 2),
            "c2bPrice": price_wan,
            "c2b_price": price_wan,
            "targetC2B": price_wan,
            "c2bRange": range_wan,
            "interval": interval,
            "price_result": {
                "final_price": round(fallback_price, 2),
                "price_low": round(low, 2),
                "price_high": round(high, 2),
                "confidence": "LOW",
                "reasonableness_level": "SUPPORTED_WITH_LIMITATIONS",
                "display_type": "LOW_CONFIDENCE_SINGLE_POINT",
            },
            "confidence": "LOW",
            "confidence_reasons": [reason, fallback_source, "LOW_TRUST_ALWAYS_QUOTE_POLICY"],
            "quote_decision": "LOW_CONFIDENCE_SINGLE_POINT",
            "selected_comparables": selected_comparables,
            "external_market_evidence": external_market_evidence,
            "price_trace": {
                "statistical_baseline_price": round(fallback_price, 2),
                "baseline_method": fallback_source,
                "baseline_candidate_count": 0,
                "direct_price_prior": round(float(direct_prior), 2) if direct_prior else None,
                "static_guide_price": round(float(guide_anchor["guide_price"]), 2) if guide_anchor else None,
                "static_guide_depreciation_ratio": guide_anchor["ratio"] if guide_anchor else None,
                "static_guide_match": guide_anchor["guide_match"] if guide_anchor else None,
                "static_guide_ratio_source": guide_anchor["ratio_source"] if guide_anchor else None,
                "b2c_to_c2b_bridge_ratio": bridge["ratio"] if bridge else None,
                "b2c_to_c2b_bridge_level": bridge["level"] if bridge else None,
                "legacy_fallback_error": legacy_error or None,
                "raw_residual_ratio": 0.0,
                "final_residual_ratio": 0.0,
                "final_residual_amount": 0.0,
            },
            "evidence_summary": {
                "candidate_count": int(len(candidates)),
                "unique_candidate_count": int(len(candidates)),
                "warehouse_rows_before_runtime_dedup": self.warehouse_rows_before_runtime_dedup,
                "warehouse_rows_after_runtime_dedup": self.warehouse_rows_after_runtime_dedup,
                "daily_confirmed_actual_rows_loaded": self.daily_confirmed_actual_rows,
                "baseline_candidate_count": 0,
                "c2b_point_baseline_uses_only_internal_c2b": True,
                "b2c_and_web_are_not_direct_c2b_baseline": True,
                "b2c_to_c2b_bridge_used": bool(bridge),
                "b2c_to_c2b_bridge_ratio": bridge["ratio"] if bridge else None,
                "b2c_to_c2b_bridge_level": bridge["level"] if bridge else None,
                "external_market_candidate_count": len(external_market_evidence),
                "external_search_status": "VALIDATED_CURRENT_SNAPSHOT_ACTIVE",
                "live_web_search_used_for_point_price": False,
            },
            "evidence_card": {
                "ledger_version": "v194_evidence_ledger_v1",
                "raw_query": query,
                "normalized_query": normalized,
                "candidate_count": int(len(candidates)),
                "baseline_candidate_count": 0,
                "price_summary": {
                    "baseline_method": fallback_source,
                    "statistical_baseline_price": fallback_price,
                    "b2c_to_c2b_bridge_ratio": bridge["ratio"] if bridge else None,
                    "b2c_to_c2b_bridge_level": bridge["level"] if bridge else None,
                },
                "top_candidates": selected_comparables,
                "external_market_evidence": external_market_evidence,
                "business_explanation": business_explanation,
            },
            "business_explanation": business_explanation,
            "risk_warnings": warnings,
            "normalized_query": normalized,
            "reason": "v194.2 未拒绝报价：严格证据不足时使用树模型/历史品牌基线兜底，并保留低信任提示。",
        }

    @staticmethod
    def _risk_warnings(confidence: str, reasons: list[str], query: dict[str, Any] | None = None) -> list[str]:
        query = query or {}
        warnings = []
        if confidence in {"LOW", "MANUAL"}:
            warnings.append("证据质量不足，建议仅作为参考或进入人工复核。")
        if "BASELINE_PRICE_DISPERSION_HIGH" in reasons:
            warnings.append("相似成交价离散度较高，价格区间需加宽。")
        if "BASELINE_CANDIDATE_COUNT_LOW" in reasons:
            warnings.append("严格可比车数量偏少。")
        if query.get("condition_assumption") == "SYSTEM_DEFAULT_GOOD_CONDITION":
            warnings.append("当前按系统默认良好车况估算，实际检测后可能调整。")
        if query.get("year_consistency_warning"):
            warnings.append(str(query["year_consistency_warning"]))
        return warnings


def get_service(force_reload: bool = False) -> V194PricingService:
    global _SERVICE
    with _LOCK:
        if force_reload or _SERVICE is None:
            _SERVICE = V194PricingService()
        return _SERVICE


def warm_fast_serving_assets() -> dict[str, Any]:
    """Warm the lightweight hosted path without loading the 360MB legacy store."""

    warmed: list[str] = []
    errors: list[str] = []
    try:
        get_reviewed_business_surface(
            _reviewed_surface_path(),
            max_distance=float(os.environ.get("V195_SINGLE_ANSWER_MAX_DISTANCE", "2.0")),
        )
        warmed.append("reviewed_business_surface")
    except Exception as exc:
        errors.append(f"reviewed_business_surface:{exc}")

    global _CATALOG_APPRAISER
    with _CATALOG_APPRAISER_LOCK:
        if _CATALOG_APPRAISER is None:
            try:
                _CATALOG_APPRAISER = InternalDcdCatalogAppraiser(_project_root())
            except Exception as exc:
                errors.append(f"catalog_appraiser:{exc}")
        if _CATALOG_APPRAISER is not None:
            warmed.append("catalog_appraiser")

    global _ON_DEMAND_STORE
    with _ON_DEMAND_STORE_LOCK:
        if _ON_DEMAND_STORE is None:
            try:
                pointer = json.loads(
                    (_project_root() / "data/v195/current_daily_vehicle_price_knowledge.json")
                    .read_text(encoding="utf-8")
                )
                snapshot_path = Path(pointer["snapshot_path"])
                if not snapshot_path.is_absolute():
                    snapshot_path = _project_root() / snapshot_path
                _ON_DEMAND_STORE = DailyVehicleKnowledgeStore(
                    pd.read_parquet(snapshot_path),
                    root=_project_root(),
                    commercial_frame=None,
                )
            except Exception as exc:
                errors.append(f"daily_vehicle_knowledge:{exc}")
        if _ON_DEMAND_STORE is not None:
            warmed.append("daily_vehicle_knowledge")
    return {"success": not errors, "warmed": warmed, "errors": errors}


def quote_with_v194_service(
    payload: dict[str, Any],
    legacy_predictor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # The reviewed daily surface is tiny and strict.  Check it before loading
    # the million-row legacy evidence warehouse so a normal book hit remains a
    # low-latency, low-memory request.
    payload = _payload_with_catalog_identity(payload)
    target_side = "B2C" if _is_b2c_pricing_task(payload) else "C2B"
    reviewed = _reviewed_business_surface_quote(payload, target_side)
    reviewed_distance = pd.to_numeric(
        ((reviewed or {}).get("price_trace") or {}).get("match_distance"),
        errors="coerce",
    )
    reviewed_trace = (reviewed or {}).get("price_trace") or {}
    evidence_origin = str(reviewed_trace.get("evidence_origin_side") or "")
    requested_cell_id = None
    try:
        identity_payload = {
            **payload,
            "model_id": payload.get("model_id")
            or payload.get("modelId")
            or reviewed_trace.get("matched_model_id"),
            "model_year": _model_year(payload)
            or reviewed_trace.get("matched_model_year"),
            "condition_grade": payload.get("condition_grade")
            or payload.get("inspection_grade")
            or payload.get("condition")
            or "A",
        }
        requested_cell_id = exact_seven_element_fingerprint(identity_payload)
    except (ValueError, KeyError, TypeError, IndexError):
        requested_cell_id = None
    exact_cell_identity = bool(
        requested_cell_id
        and requested_cell_id
        == str(reviewed_trace.get("exact_seven_element_fingerprint") or "")
    )
    relevant_recency = pd.to_numeric(
        reviewed_trace.get(
            "internal_b2c_recency_days"
            if target_side == "B2C"
            else "internal_c2b_recency_days"
        ),
        errors="coerce",
    )
    trusted_current_exact = bool(
        (
            exact_cell_identity
            or (
                evidence_origin == "DCD_ONLY_CURRENT_MARKET"
                and "exact_trim" in str(reviewed_trace.get("match_level") or "")
                and pd.notna(reviewed_distance)
                and float(reviewed_distance) <= 0.50
            )
            or (
                evidence_origin == "FULL_CATALOG_MANUAL_APPRAISER_FINAL"
                and "exact_trim" in str(reviewed_trace.get("match_level") or "")
                and pd.notna(reviewed_distance)
                and float(reviewed_distance) <= 1.20
            )
        )
        and (
            evidence_origin == "DCD_ONLY_CURRENT_MARKET"
            or evidence_origin in {"B2C", "C2B", "B2C+C2B"}
            or evidence_origin.startswith("MANUAL_")
            or evidence_origin == "FULL_CATALOG_MANUAL_APPRAISER_FINAL"
            or (
                evidence_origin == "DAILY_INTERNAL_EXTERNAL"
                and pd.notna(relevant_recency)
                and relevant_recency <= 60.0
            )
        )
    )
    if reviewed is not None and trusted_current_exact:
        return reviewed
    materialized = _on_demand_exact_cell_quote(payload, target_side, reviewed)
    if materialized is not None:
        return materialized
    if reviewed is not None:
        return reviewed
    if str(os.environ.get("DEPLOY_LITE_MODE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "success": False,
            "pricing_engine_used": "V195_PRICE_BOOK_NO_LEGACY_FALLBACK",
            "pricing_engine_version": "v195.439",
            "quote_decision": "NO_QUOTE",
            "reason": "当前输入未生成可审计定价模型记录；轻量线上链路禁止静默加载旧重服务。",
            "risk_warnings": ["请检查标准车型ID、年款和七要素字段映射。"],
        }
    return _apply_condition_grade_guard(
        get_service().quote(payload, legacy_predictor=legacy_predictor),
        payload,
    )


def minimal_real_payload() -> dict[str, Any]:
    return {
        "request_id": "v194-smoke-bmw-3",
        "brand": "宝马",
        "series": "宝马3系",
        "model_year": 2021,
        "trim": "2021款 320i 运动套装",
        "city": "北京",
        "color": "白色",
        "age_years": 5,
        "mileage_wan_km": 6.2,
        "transfer_count": 1,
        "quote_time": "2026-06-20 12:00:00",
    }


def get_version_payload() -> dict[str, Any]:
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "product_memory_policy_version": PRODUCT_MEMORY_POLICY_VERSION,
        "b2c_product_memory_policy_version": B2C_PRODUCT_MEMORY_POLICY_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
        "build_time": BUILD_TIME,
        "production_entrypoint": "app.py",
        "reviewed_business_surface_version": "v195_439_full_catalog_final_appraiser_price_book",
        "reviewed_business_surface_enabled": REVIEWED_BUSINESS_SURFACE_ENABLED,
        "on_demand_exact_cell_enabled": ON_DEMAND_EXACT_CELL_ENABLED,
    }


def v194_readiness_check(force: bool = False) -> dict[str, Any]:
    global _READY_CACHE
    if _READY_CACHE is not None and not force:
        return dict(_READY_CACHE)
    if str(os.environ.get("DEPLOY_LITE_MODE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } and REVIEWED_BUSINESS_SURFACE_ENABLED:
        path = _reviewed_surface_path()
        surface = get_reviewed_business_surface(
            path,
            max_distance=float(os.environ.get("V195_SINGLE_ANSWER_MAX_DISTANCE", "2.0")),
        )
        status = {
            "ready": surface.enabled,
            "engine_loaded": surface.enabled,
            "pricing_engine_used": "V195_REVIEWED_BUSINESS_SURFACE",
            "pricing_engine_version": surface.version,
            "model_version": surface.version,
            "surface_rows": int(surface.row_count),
            "legacy_warehouse_loaded": False,
            "memory_policy": "STRICT_SURFACE_FIRST_LAZY_LEGACY_FALLBACK",
        }
        _READY_CACHE = dict(status)
        return status
    try:
        service = get_service(force_reload=force)
        result = service.quote(minimal_real_payload())
        ready = bool(result.get("pricing_engine_used") == "V194" and result.get("evidence_card"))
        status = {
            "ready": ready,
            "engine_loaded": True,
            "pricing_engine_used": result.get("pricing_engine_used"),
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "warehouse_rows": int(len(service.warehouse)),
            "warehouse_rows_before_runtime_dedup": service.warehouse_rows_before_runtime_dedup,
            "warehouse_rows_after_runtime_dedup": service.warehouse_rows_after_runtime_dedup,
            "enforced_candidate_manual_rows_loaded": len(service.enforced_candidate_manual),
            "product_memory_rows_loaded": int(len(service.product_memory.history)) if service.product_memory is not None else 0,
            "product_memory_policy_version": PRODUCT_MEMORY_POLICY_VERSION,
            "b2c_product_memory_rows_loaded": int(len(service.b2c_product_memory.history)) if service.b2c_product_memory is not None else 0,
            "b2c_product_memory_policy_version": B2C_PRODUCT_MEMORY_POLICY_VERSION,
            "selected_comparables_count": int(len(result.get("selected_comparables") or [])),
            "evidence_card_present": bool(result.get("evidence_card")),
        }
    except Exception as exc:
        status = {
            "ready": False,
            "engine_loaded": False,
            "pricing_engine_used": None,
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "error": str(exc),
        }
    _READY_CACHE = dict(status)
    return status
