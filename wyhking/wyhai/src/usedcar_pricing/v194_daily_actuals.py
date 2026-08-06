"""Append-only ingestion of confirmed internal C2B actuals.

The module makes the live timing rule executable: a realised transaction may
help a later quote only after it is confirmed and ingested.  It never changes
the quote that preceded the transaction and it keeps rejected source rows in
the audit output instead of silently dropping them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v194_price_policy import build_evidence_warehouse


DAILY_FILENAME = "daily_confirmed_c2b_actuals.parquet"

ALIASES: dict[str, tuple[str, ...]] = {
    "price": ("收车合同价", "c2b_purchase_price_yuan", "收车价", "成交价", "最新订单成交价", "price"),
    "event_time": ("收车合同签订时间", "purchase_contract_time", "成交时间", "订单成交时间", "event_time", "target_date"),
    "brand": ("品牌", "品牌名称", "brand", "brand_name"),
    "series": ("车系", "车系名称", "series", "series_name"),
    "model_year": ("车型年款", "model_year", "year", "年款"),
    "model_id": ("车型ID", "model_id", "modelId", "标准车型ID"),
    "trim": ("车型", "款型", "trim", "model", "车辆名称"),
    "energy_type": ("能源类型", "energy_type", "energyType", "动力类型"),
    "city": ("城市", "车源所在城市", "city", "所在城市"),
    "color_raw": ("颜色", "外观颜色", "color", "车身颜色"),
    "first_registration_date": ("首次上牌时间", "首次登记时间", "first_registration_date", "regDate", "reg_date"),
    "mileage_wan_km": ("里程", "mileage_wan_km", "表显里程", "行驶里程"),
    "transfer_count": ("过户次数", "transfer_count", "过户"),
    "inspection_grade": ("最新检测报告评级", "inspection_grade", "检测评级"),
    "inspection_score": ("最新检测报告分数", "inspection_score", "检测分数"),
    "is_accident": ("是否事故车", "is_accident"),
    "is_flood": ("是否泡水车", "is_flood"),
    "is_fire": ("是否火烧车", "is_fire"),
    "is_odometer_abnormal": ("是否调表车", "is_odometer_abnormal"),
    "vehicle_id": ("vehicle_id", "车辆ID", "车源ID", "车源货品ID"),
    "clue_id": ("clue_id", "线索ID", "车源商品ID"),
    "order_id": ("order_id", "订单ID", "合同ID", "收车合同ID"),
}


def _column(frame: pd.DataFrame, field: str) -> pd.Series:
    for column in ALIASES[field]:
        if column in frame.columns:
            return frame[column]
    return pd.Series(np.nan, index=frame.index)


def _hash_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "0", "nan", "none", "null"}:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def _price_yuan(value: Any, unit: str) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return np.nan
    value_float = float(number)
    if unit == "wan" or (unit == "auto" and 0 < value_float < 1_000):
        return value_float * 10_000
    return value_float


def _source_row_hash(frame: pd.DataFrame) -> pd.Series:
    columns = ["event_time", "price", "brand", "series", "model_year", "trim", "city", "mileage_wan_km", "transfer_count", "vehicle_id_hash", "clue_id_hash"]
    material = frame[columns].fillna("").astype(str).agg("|".join, axis=1)
    return material.map(lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()[:24])


def business_event_dedup_key(frame: pd.DataFrame, role: str) -> pd.Series:
    """Stable transaction identity across overlapping export snapshots."""
    vehicle = frame.get("vehicle_id_hash", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    clue = frame.get("clue_id_hash", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    identity = pd.Series(
        np.where(vehicle.ne(""), "VEHICLE|" + vehicle, "CLUE|" + clue),
        index=frame.index,
    )
    event = pd.to_datetime(frame.get("event_time"), errors="coerce")
    valid = (vehicle.ne("") | clue.ne("")) & event.notna()
    fallback = frame.get("daily_source_row_hash", pd.Series(frame.index.astype(str), index=frame.index)).fillna("").astype(str)
    result = str(role).upper() + "|" + identity + "|" + event.astype(str)
    return result.where(valid, str(role).upper() + "|ROW|" + fallback)


def normalize_confirmed_actuals(
    source: pd.DataFrame,
    *,
    ingested_at: Any,
    source_name: str = "daily_confirmed_internal_c2b",
    price_unit: str = "auto",
) -> pd.DataFrame:
    """Convert a daily confirmed-C2B file into a quality-gated evidence table."""
    if price_unit not in {"auto", "yuan", "wan"}:
        raise ValueError("price_unit must be auto, yuan, or wan")
    ingested = pd.to_datetime(ingested_at, errors="coerce")
    if pd.isna(ingested):
        raise ValueError("ingested_at must be a valid timestamp")
    result = pd.DataFrame(index=source.index)
    for field in ALIASES:
        result[field] = _column(source, field)
    result["price"] = result["price"].map(lambda value: _price_yuan(value, price_unit))
    result["event_time"] = pd.to_datetime(result["event_time"], errors="coerce")
    result["first_registration_date"] = pd.to_datetime(result["first_registration_date"], errors="coerce")
    result["model_year"] = pd.to_numeric(result["model_year"], errors="coerce")
    result["mileage_wan_km"] = pd.to_numeric(result["mileage_wan_km"], errors="coerce")
    result["transfer_count"] = pd.to_numeric(result["transfer_count"], errors="coerce")
    result["age_years"] = (
        (result["event_time"] - result["first_registration_date"]).dt.total_seconds()
        / (365.25 * 86400.0)
    )
    result.loc[result["age_years"].lt(0) | result["age_years"].gt(40), "age_years"] = np.nan
    result["vehicle_id_hash"] = result["vehicle_id"].map(_hash_identifier)
    result["clue_id_hash"] = result["clue_id"].map(_hash_identifier)
    result["listing_id"] = result["order_id"].map(_hash_identifier)
    result["source_type"] = "internal_c2b_purchase"
    result["price_type"] = "c2b_purchase_actual"
    result["knowledge_available_at"] = ingested
    # Unlike a historical batch import, this is a live update.  The fact is
    # eligible only after confirmation/ingestion, never retroactively at its
    # contract time.
    result["pricing_available_at"] = ingested
    result["daily_actual_available_at_rule"] = "CONFIRMED_INGESTION_TIMESTAMP"
    result["source_url"] = ""
    result["dedup_keep_flag"] = True
    result["candidate_clean_flag"] = True
    result["clean_for_memory_flag"] = True
    result["market_clean_flag"] = True
    result["is_token_price"] = False
    result["source_file_name"] = source_name
    result["observation_id"] = [f"daily_c2b_{source_name}_{i}" for i in result.index]
    normalized = build_evidence_warehouse(result)
    normalized["pricing_available_at"] = ingested
    normalized["runtime_candidate_lifecycle_key"] = (
        np.where(
            normalized["vehicle_id_hash"].astype(str).ne(""),
            "VEHICLE|" + normalized["vehicle_id_hash"].astype(str) + "|" + normalized["event_time"].astype(str) + "|" + normalized["price_yuan"].astype(str),
            "CLUE|" + normalized["clue_id_hash"].astype(str) + "|" + normalized["event_time"].astype(str) + "|" + normalized["price_yuan"].astype(str),
        )
    )
    normalized["runtime_candidate_transaction_fingerprint"] = normalized["runtime_candidate_lifecycle_key"]
    normalized["runtime_candidate_market_listing_fingerprint"] = normalized["runtime_candidate_lifecycle_key"]
    normalized["runtime_candidate_dedup_keep_flag"] = True
    normalized["daily_source_row_hash"] = _source_row_hash(normalized)
    normalized["daily_business_event_key"] = business_event_dedup_key(normalized, "C2B")
    # A source row can be retained for audit while being ineligible for an
    # automatic C2B baseline.  `build_evidence_warehouse` has already applied
    # price, identity and condition gates.
    normalized["daily_actual_ingestion_status"] = np.where(
        normalized["allowed_for_c2b_point_baseline"].fillna(False),
        "ELIGIBLE_FOR_FUTURE_C2B_RETRIEVAL",
        "RETAINED_AUDIT_NOT_ELIGIBLE",
    )
    return normalized


def append_confirmed_actuals(
    source: pd.DataFrame,
    *,
    root: Path,
    ingested_at: Any,
    source_name: str,
    price_unit: str = "auto",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append new facts, returning (new_rows, full_daily_store)."""
    target = root / "data" / "v194" / DAILY_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    new_rows = normalize_confirmed_actuals(
        source, ingested_at=ingested_at, source_name=source_name, price_unit=price_unit
    )
    existing = pd.read_parquet(target) if target.exists() else pd.DataFrame()
    combined = pd.concat([existing, new_rows], ignore_index=True, sort=False)
    combined["daily_business_event_key"] = business_event_dedup_key(combined, "C2B")
    dedup_key = "daily_business_event_key"
    # The same transaction is present in overlapping exports whenever a later
    # inspection snapshot changes. Keep the latest snapshot, but count the
    # business event only once.
    combined = combined.drop_duplicates(dedup_key, keep="last")
    combined.to_parquet(target, index=False)
    return new_rows, combined
