from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_12_semantics import add_v192_12_semantic_columns


BASE_KEYS = [
    "brand_key",
    "series_key",
    "model_year",
    "trim_key",
    "color_norm",
    "city_key",
    "age_fine_bin",
    "mileage_fine_bin",
    "transfer_fine_bin",
    "condition_risk_level",
]
PARENT_KEYS = ["brand_key", "series_key", "model_year", "trim_key", "condition_risk_level"]

OBSERVATION_RUNTIME_COLUMNS = [
    "observation_id",
    "source_type",
    "price_type",
    "price",
    "event_time",
    "knowledge_available_at",
    "brand",
    "series",
    "model_id",
    "model_year",
    "trim",
    "city",
    "brand_key",
    "series_key",
    "model_id_key",
    "trim_key",
    "trim_group_key",
    "canonical_trim_key",
    "normalized_trim",
    "normalized_energy_type",
    "trim_power_code",
    "trim_wheelbase",
    "trim_package",
    "trim_drivetrain",
    "city_key",
    "color_raw",
    "color_norm",
    "age_fine_bin",
    "mileage_fine_bin",
    "transfer_fine_bin",
    "age_years",
    "mileage_wan_km",
    "transfer_count",
    "inspection_grade",
    "inspection_score",
    "condition_risk_level",
    "is_accident",
    "is_flood",
    "is_fire",
    "is_odometer_abnormal",
    "is_new_energy",
    "vehicle_id_hash",
    "clue_id_hash",
    "listing_id",
    "listing_start_time",
    "sold_time",
    "purchase_contract_time",
    "first_listing_price",
    "days_on_market",
    "dedup_keep_flag",
    "candidate_clean_flag",
    "clean_for_memory_flag",
    "market_clean_flag",
    "cluster_price_type",
    "source_file",
    "source_row_id",
    "source_url",
]

LOW_CARDINALITY_COLUMNS = [
    "source_type",
    "price_type",
    "brand",
    "series",
    "city",
    "brand_key",
    "series_key",
    "model_id_key",
    "trim_key",
    "trim_group_key",
    "city_key",
    "color_raw",
    "color_norm",
    "age_fine_bin",
    "mileage_fine_bin",
    "transfer_fine_bin",
    "inspection_grade",
    "condition_risk_level",
    "is_accident",
    "is_flood",
    "is_fire",
    "is_odometer_abnormal",
    "is_new_energy",
    "cluster_price_type",
]


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"nan", "none", "<na>", "unknown"} else value


def lifecycle_id(row: pd.Series | dict[str, Any]) -> str:
    value = dict(row)
    for key in ("vehicle_id_hash", "clue_id_hash", "listing_id"):
        candidate = clean_text(value.get(key))
        if candidate:
            return candidate
    raw = "|".join(
        clean_text(value.get(key))
        for key in ("brand_key", "series_key", "model_year", "trim_key", "event_time", "price")
    )
    return "anon_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _available_parquet_columns(path: str) -> list[str] | None:
    try:
        import pyarrow.parquet as pq

        return pq.ParquetFile(path).schema.names
    except Exception:
        return None


def load_observations(path: str) -> pd.DataFrame:
    available = _available_parquet_columns(path)
    if available:
        columns = [column for column in OBSERVATION_RUNTIME_COLUMNS if column in available]
        frame = pd.read_parquet(path, columns=columns)
    else:
        frame = pd.read_parquet(path)
    frame = frame[frame["market_clean_flag"].eq(1)].copy()
    if "dedup_keep_flag" in frame:
        internal = frame["cluster_price_type"].isin(["C2B", "B2C"])
        frame = frame[~internal | frame["dedup_keep_flag"].eq(1)].copy()
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce")
    frame["knowledge_available_at"] = pd.to_datetime(frame["knowledge_available_at"], errors="coerce")
    numeric = [
        "price",
        "first_listing_price",
        "days_on_market",
        "model_year",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "inspection_score",
    ]
    for column in numeric:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[
        frame["event_time"].notna()
        & frame["knowledge_available_at"].notna()
        & frame["price"].between(1000, 2_000_000)
        & frame["brand_key"].fillna("").astype(str).ne("")
        & frame["series_key"].fillna("").astype(str).ne("")
    ].copy()
    frame = add_v192_12_semantic_columns(frame)
    frame["trim_key_original_v192_12"] = frame["trim_key"].fillna("").astype(str)
    frame["trim_key"] = frame["canonical_trim_key"].fillna("").astype(str)
    if "trim_group_key" in frame:
        frame["trim_group_key"] = frame["trim_power_code"].fillna("").astype(str)
    for column in BASE_KEYS:
        if column != "model_year":
            frame[column] = frame[column].fillna("").astype(str)
    frame["lifecycle_id"] = [lifecycle_id(row) for row in frame.to_dict("records")]
    frame = frame.sort_values(["knowledge_available_at", "event_time", "observation_id"], kind="stable")
    for column in LOW_CARDINALITY_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype("category")
            if "" not in frame[column].cat.categories:
                frame[column] = frame[column].cat.add_categories([""])
    return frame.reset_index(drop=True)


def build_role_pairs(observations: pd.DataFrame) -> pd.DataFrame:
    internal = observations[
        observations["cluster_price_type"].isin(["C2B", "B2C"])
        & observations["lifecycle_id"].ne("")
    ].copy()
    c2b = (
        internal[internal["cluster_price_type"].eq("C2B")]
        .sort_values(["lifecycle_id", "event_time"])
        .groupby("lifecycle_id", as_index=False)
        .last()
    )
    b2c = (
        internal[internal["cluster_price_type"].eq("B2C")]
        .sort_values(["lifecycle_id", "event_time"])
        .groupby("lifecycle_id", as_index=False)
        .last()
    )
    columns = [
        "lifecycle_id",
        *PARENT_KEYS,
        "price",
        "event_time",
        "knowledge_available_at",
        "first_listing_price",
        "days_on_market",
        "observation_id",
    ]
    paired = c2b[columns].merge(b2c[columns], on="lifecycle_id", suffixes=("_c2b", "_b2c"))
    for key in PARENT_KEYS:
        paired[key] = paired[f"{key}_b2c"].where(
            paired[f"{key}_b2c"].fillna("").astype(str).ne(""),
            paired[f"{key}_c2b"],
        )
    paired["pair_available_at"] = paired[
        ["knowledge_available_at_c2b", "knowledge_available_at_b2c"]
    ].max(axis=1)
    paired["purchase_to_sold_ratio"] = paired["price_c2b"] / paired["price_b2c"].replace(0, np.nan)
    paired = paired[paired["purchase_to_sold_ratio"].between(0.50, 1.05)].copy()
    return paired.sort_values("pair_available_at").reset_index(drop=True)


@dataclass(frozen=True)
class Window:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


def strict_windows(latest_complete_day: str, rolling_months: int = 6) -> tuple[Window, Window, list[Window]]:
    test_end = pd.Timestamp(latest_complete_day).normalize() + pd.Timedelta(days=1)
    test_start = test_end - pd.Timedelta(days=30)
    calibration_start = test_start - pd.Timedelta(days=30)
    test = Window("latest_complete_30d", test_start, test_end)
    calibration = Window("previous_30d_calibration", calibration_start, test_start)
    rolling: list[Window] = []
    end = test_end
    for index in range(rolling_months):
        start = end - pd.Timedelta(days=30)
        rolling.append(Window(f"rolling_month_{rolling_months-index}", start, end))
        end = start
    rolling.reverse()
    return test, calibration, rolling


def query_frame(observations: pd.DataFrame, window: Window) -> pd.DataFrame:
    result = observations[
        observations["cluster_price_type"].eq("C2B")
        & observations["event_time"].ge(window.start)
        & observations["event_time"].lt(window.end)
    ].copy()
    result = result.rename(
        columns={
            "observation_id": "query_id",
            "event_time": "prediction_time",
            "price": "actual_price",
        }
    )
    result["window"] = window.name
    return result.reset_index(drop=True)
