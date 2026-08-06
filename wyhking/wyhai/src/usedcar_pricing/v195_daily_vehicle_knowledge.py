"""Daily materialized vehicle-price knowledge for production quoting.

The model is deliberately the last fallback here.  Every observed
six-elements-plus-condition cell is materialized from confirmed T-1 evidence
and receives a complete, constrained price ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .v195_external_market_anchor import (
    calibrated_external_proxy,
    fit_external_market_calibration,
)
from .v195_manual_override_engine import (
    ManualOverrideRegistry,
    apply_override_value,
    local_reference_adjustment,
)
from .v195_price_book_builder import (
    LEVEL_KEYS,
    _add_keys,
    _canonical_key,
    build_price_book,
    lookup_price_book,
)
from .v195_price_book_schema import (
    EvaluationMode,
    QuoteDecision,
    compact,
    mileage_bucket_km,
    registration_month,
    stable_hash,
)
from .v195_price_ladder_solver import (
    ORDERED_FIELDS,
    business_cost_inputs,
    hierarchy_violations,
    load_ladder_config,
    price_band,
)
from .v195_production_pricing_engine import (
    RawPricingInputs,
    V195ProductionPricingEngine,
)


EXACT_CELL_COLUMNS = [
    "model_id_key",
    "model_year_key",
    "registration_month_key",
    "mileage_5000_key",
    "city_key",
    "transfer_bucket_key",
    "color_bucket_key",
    "condition_bucket_key",
]

EXTERNAL_COLUMNS = [
    "listing_price_yuan",
    "source_weighted_listing_price_yuan",
    "source_count",
    "same_year_source_count",
    "total_listing_count",
    "cross_source_dispersion_ratio",
    "listing_confidence",
    "safe_for_transaction_calibration",
    "dongchedi_median_yuan",
    "dongchedi_count",
    "dongchedi_match_level",
    "autohome_median_yuan",
    "autohome_count",
    "autohome_match_level",
    "guazi_median_yuan",
    "guazi_count",
    "guazi_match_level",
]


@dataclass(frozen=True)
class DailyKnowledgeBuildConfig:
    history_days: int = 180
    universe_days: int = 180
    snapshot_ttl_days: int = 2
    auto_quote_max_external_dispersion: float = 0.25
    auto_quote_max_internal_recency_days: float = 45.0
    auto_quote_min_exact_internal_count: int = 2
    include_full_active_universe: bool = True


def _timestamp(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Asia/Shanghai")
    return parsed.tz_convert("UTC")


def _first_present(frame: pd.DataFrame, columns: Iterable[str], default: Any = "") -> pd.Series:
    result = pd.Series(default, index=frame.index, dtype=object)
    assigned = pd.Series(False, index=frame.index)
    for column in columns:
        if column not in frame:
            continue
        values = frame[column]
        present = values.notna() & values.astype(str).str.strip().ne("")
        use = present & ~assigned
        result.loc[use] = values.loc[use]
        assigned |= use
    return result


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    return pd.to_numeric(_first_present(frame, columns, np.nan), errors="coerce")


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, pd.Series):
        value = value.dropna().iloc[-1] if value.notna().any() else default
    number = pd.to_numeric(value, errors="coerce")
    return int(number) if pd.notna(number) and np.isfinite(float(number)) else default


def _read_csv_columns(path: Path, requested: Iterable[str]) -> pd.DataFrame:
    available = set(pd.read_csv(path, nrows=0).columns)
    usecols = [column for column in requested if column in available]
    return pd.read_csv(path, usecols=usecols, low_memory=False)


def _truth_vehicle_metadata(truth: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "source_vehicle_id",
        "model_id",
        "brand",
        "series",
        "trim",
        "model_year",
        "registration_date",
        "mileage_km",
        "city",
        "transfer_count",
        "color",
        "condition_grade",
        "transaction_at",
    ]
    available = [column for column in columns if column in truth]
    metadata = truth[available].copy()
    metadata["source_vehicle_id"] = metadata["source_vehicle_id"].astype(str)
    metadata["transaction_at"] = pd.to_datetime(
        metadata.get("transaction_at"), errors="coerce", utc=True
    )
    return metadata.sort_values("transaction_at", kind="stable").drop_duplicates(
        "source_vehicle_id", keep="last"
    )


def enrich_trace_with_truth(trace: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Restore six-element fields dropped by historical evaluation traces."""

    out = trace.copy()
    vehicle_id = _first_present(
        out,
        ["vehicle_id_condition_query", "vehicle_id", "source_vehicle_id"],
    ).astype(str)
    out["_knowledge_vehicle_id"] = vehicle_id
    metadata = _truth_vehicle_metadata(truth).add_suffix("_truth")
    out = out.merge(
        metadata,
        left_on="_knowledge_vehicle_id",
        right_on="source_vehicle_id_truth",
        how="left",
        validate="many_to_one",
    )

    aliases: dict[str, list[str]] = {
        "model_id": ["model_id_truth", "model_id", "model_id_int"],
        "brand": ["brand_truth", "brand", "brand_store"],
        "series": ["series_truth", "series", "series_store"],
        "trim": ["trim_truth", "trim", "canonical_trim_key", "trim_store"],
        "model_year": [
            "model_year_truth",
            "model_year",
            "model_year_store",
            "model_year_int",
        ],
        "registration_date": [
            "registration_date_truth",
            "first_registration_date",
            "registration_date",
        ],
        "mileage_km": ["mileage_km_truth", "mileage_km"],
        "city": ["city_truth", "city", "city_store"],
        "transfer_count": [
            "transfer_count_truth",
            "transfer_count",
            "transfer_count_store",
        ],
        "color": ["color_truth", "color", "color_raw"],
        "condition_grade": [
            "condition_grade_truth",
            "inspection_grade",
            "condition_grade",
        ],
    }
    for target, candidates in aliases.items():
        out[target] = _first_present(out, candidates, np.nan)
    missing_mileage = pd.to_numeric(out["mileage_km"], errors="coerce").isna()
    mileage_wan = _numeric(out, ["mileage_wan_km_store", "mileage_wan_km"])
    out.loc[missing_mileage, "mileage_km"] = mileage_wan.loc[missing_mileage] * 10_000.0
    return out


def prepare_knowledge_cells(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "first_registration_date" not in out and "registration_date" in out:
        out["first_registration_date"] = out["registration_date"]
    if "mileage_km" in out and "mileage_wan_km" not in out:
        out["mileage_wan_km"] = pd.to_numeric(out["mileage_km"], errors="coerce") / 10_000.0
    if "condition_grade" in out and "inspection_grade" not in out:
        out["inspection_grade"] = out["condition_grade"]
    prepared = _add_keys(out)
    prepared["registration_month_key"] = prepared["registration_date_normalized"].map(
        registration_month
    )
    prepared["mileage_5000_key"] = prepared["mileage_km_normalized"].map(
        lambda value: mileage_bucket_km(value, 5_000)
    )
    exact = prepared[EXACT_CELL_COLUMNS].fillna("UNKNOWN").astype(str).agg("|".join, axis=1)
    prepared["knowledge_cell_id"] = exact.map(
        lambda value: stable_hash(["v195", value], "knowledge")
    )
    prepared["legacy_l0_canonical_key"] = _canonical_key(prepared, 0)
    prepared["brand_normalized"] = _first_present(
        prepared, ["brand", "brand_store", "brand_truth"]
    ).astype(str)
    prepared["series_normalized"] = _first_present(
        prepared, ["series", "series_store", "series_truth"]
    ).astype(str)
    prepared["trim_normalized_display"] = _first_present(
        prepared, ["trim", "canonical_trim_key", "trim_store", "trim_truth"]
    ).astype(str)
    return prepared


def exact_seven_element_fingerprint(payload: dict[str, Any]) -> str:
    """Unbucketed runtime identity for one price answer.

    Snapshot buckets remain useful for retrieving evidence.  They are not
    precise enough to cache a final answer because two mileages inside the
    same 5,000 km bucket still require independent adjustments.
    """

    prepared = _add_keys(pd.DataFrame([payload])).iloc[0]
    registration = pd.to_datetime(
        payload.get("registration_date")
        or payload.get("first_registration_date")
        or payload.get("regDate"),
        errors="coerce",
    )
    mileage_km = pd.to_numeric(payload.get("mileage_km"), errors="coerce")
    if pd.isna(mileage_km):
        mileage_wan = pd.to_numeric(
            payload.get("mileage_wan_km") or payload.get("mileage"), errors="coerce"
        )
        mileage_km = mileage_wan * 10_000.0 if pd.notna(mileage_wan) else np.nan
    transfer = pd.to_numeric(
        payload.get("transfer_count")
        if payload.get("transfer_count") is not None
        else payload.get("transfer"),
        errors="coerce",
    )
    trim = payload.get("trim") or payload.get("standard_vehicle") or payload.get("model")
    return stable_hash(
        [
            "v195-exact-seven-elements-v2",
            prepared.get("model_id_numeric"),
            prepared.get("model_year_numeric"),
            compact(trim or ""),
            registration.date().isoformat() if pd.notna(registration) else "UNKNOWN",
            int(round(float(mileage_km))) if pd.notna(mileage_km) else "UNKNOWN",
            compact(payload.get("city") or payload.get("city_name") or ""),
            int(transfer) if pd.notna(transfer) else "UNKNOWN",
            compact(payload.get("color") or payload.get("color_raw") or ""),
            compact(
                payload.get("condition_grade")
                or payload.get("inspection_grade")
                or payload.get("condition")
                or "UNKNOWN"
            ),
        ],
        "exact7",
    )


def _legal_truth(
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    days: int,
) -> pd.DataFrame:
    transaction_at = pd.to_datetime(frame["transaction_at"], errors="coerce", utc=True)
    observed_at = pd.to_datetime(frame.get("observed_at"), errors="coerce", utc=True)
    price = pd.to_numeric(frame["price"], errors="coerce")
    eligible = frame["eligible_for_transaction_target"].fillna(False).astype(bool)
    return frame.loc[
        eligible
        & price.between(3_000, 1_000_000)
        & transaction_at.lt(cutoff)
        & observed_at.lt(cutoff)
        & transaction_at.ge(cutoff - pd.Timedelta(days=days))
    ].copy()


def build_cell_universe(
    b2c_truth: pd.DataFrame,
    c2b_truth: pd.DataFrame,
    *,
    cutoff: Any,
    query_frames: Iterable[pd.DataFrame] = (),
    universe_days: int = 365,
    include_truth_cells: bool = True,
) -> pd.DataFrame:
    cutoff_utc = _timestamp(cutoff)
    sources = [frame.copy() for frame in query_frames if not frame.empty]
    if include_truth_cells:
        sources = [
            _legal_truth(b2c_truth, cutoff=cutoff_utc, days=universe_days),
            _legal_truth(c2b_truth, cutoff=cutoff_utc, days=universe_days),
            *sources,
        ]
    if not sources:
        raise ValueError("At least one truth or query frame is required for materialization")
    prepared_frames: list[pd.DataFrame] = []
    for frame in sources:
        prepared = prepare_knowledge_cells(frame)
        prepared["_representative_time"] = pd.to_datetime(
            _first_present(prepared, ["transaction_at", "event_time", "day"], pd.NaT),
            errors="coerce",
            utc=True,
        )
        prepared_frames.append(prepared)
    combined = pd.concat(prepared_frames, ignore_index=True, sort=False)
    combined = combined.loc[
        pd.to_numeric(combined["model_id_numeric"], errors="coerce").fillna(0).gt(0)
    ].copy()
    combined = combined.sort_values("_representative_time", kind="stable").drop_duplicates(
        "knowledge_cell_id", keep="last"
    )
    keep = [
        "knowledge_cell_id",
        "legacy_l0_canonical_key",
        *EXACT_CELL_COLUMNS,
        "model_id_numeric",
        "model_year_numeric",
        "registration_date_normalized",
        "mileage_km_normalized",
        "brand_normalized",
        "series_normalized",
        "trim_normalized_display",
        *sorted({column for columns in LEVEL_KEYS.values() for column in columns}),
    ]
    return combined[list(dict.fromkeys(keep))].reset_index(drop=True)


def _lookup_hierarchy(frame: pd.DataFrame, book: pd.DataFrame, side: str) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    result["price_book_anchor_yuan"] = np.nan
    result["price_book_low_yuan"] = np.nan
    result["price_book_high_yuan"] = np.nan
    result["price_book_sample_count"] = 0
    result["price_book_recency_days"] = np.nan
    result["price_book_hit_level"] = -1
    result["price_book_confidence"] = "MISSING"
    for level in LEVEL_KEYS:
        pending = result["price_book_hit_level"].lt(0)
        if not pending.any():
            break
        keys = _canonical_key(frame.loc[pending], level)
        level_book = book.loc[
            book["key_level"].eq(level) & book[f"{side}_point"].notna()
        ].set_index("canonical_key")
        matched = keys.isin(level_book.index)
        if not matched.any():
            continue
        query_indices = keys.index[matched]
        rows = level_book.loc[keys.loc[matched].to_numpy()]
        result.loc[query_indices, "price_book_anchor_yuan"] = rows[
            f"{side}_point"
        ].to_numpy()
        result.loc[query_indices, "price_book_low_yuan"] = rows[
            f"{side}_low"
        ].to_numpy()
        result.loc[query_indices, "price_book_high_yuan"] = rows[
            f"{side}_high"
        ].to_numpy()
        result.loc[query_indices, "price_book_sample_count"] = rows[
            f"{side}_count"
        ].to_numpy()
        result.loc[query_indices, "price_book_recency_days"] = rows[
            f"{side}_recency_days"
        ].to_numpy()
        result.loc[query_indices, "price_book_hit_level"] = level
        result.loc[query_indices, "price_book_confidence"] = rows[
            f"{side}_confidence"
        ].to_numpy()
    return result


def _load_trace_queries(
    root: Path,
    b2c_truth: pd.DataFrame,
    c2b_truth: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    common_columns = [
        "role",
        "day",
        "raw_index",
        "event_time",
        "brand",
        "series",
        "trim",
        "model_year",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "city",
        "color",
        "condition",
        "actual_yuan",
        "pred_yuan",
        "vehicle_id",
        "vehicle_id_condition_query",
        "model_id",
        "model_id_int",
        "canonical_trim_key",
        "brand_store",
        "series_store",
        "trim_store",
        "model_year_store",
        "city_store",
        "color_raw",
        "first_registration_date",
        "mileage_wan_km_store",
        "transfer_count_store",
        "inspection_grade",
        "condition_risk_level_strict",
        *EXTERNAL_COLUMNS,
    ]
    b2c_path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
    b2c = _read_csv_columns(
        b2c_path,
        [*common_columns, "champion_pred_yuan", "v195_anchor_repaired_yuan"],
    )
    b2c["day"] = pd.to_datetime(b2c["day"], errors="coerce")
    b2c = enrich_trace_with_truth(b2c, b2c_truth)
    b2c["fallback_b2c_yuan"] = _numeric(
        b2c, ["v195_anchor_repaired_yuan", "champion_pred_yuan", "pred_yuan"]
    )
    b2c["fallback_c2b_yuan"] = np.nan
    b2c["external_base_yuan"] = b2c["fallback_b2c_yuan"]
    b2c["query_side"] = "B2C"

    c2b_path = root / "results/traces/v194_369_c2b_90d_listing_discount_trace.csv"
    c2b = _read_csv_columns(
        c2b_path,
        [
            *common_columns,
            "b2c_transaction_pred_yuan",
            "dongchedi_b2c_guard_after_yuan",
            "listing_discount_c2b_pred_yuan",
            "strict_trim_c2b_pred_yuan",
        ],
    )
    c2b["day"] = pd.to_datetime(c2b["day"], errors="coerce")
    c2b = enrich_trace_with_truth(c2b, c2b_truth)
    c2b["fallback_b2c_yuan"] = _numeric(
        c2b, ["b2c_transaction_pred_yuan", "dongchedi_b2c_guard_after_yuan"]
    )
    c2b["fallback_c2b_yuan"] = _numeric(
        c2b,
        [
            "listing_discount_c2b_pred_yuan",
            "strict_trim_c2b_pred_yuan",
            "pred_yuan",
        ],
    )
    c2b["external_base_yuan"] = c2b["fallback_b2c_yuan"]
    c2b["query_side"] = "C2B"

    cutoff_local_day = cutoff.tz_convert("Asia/Shanghai").tz_localize(None).normalize()
    b2c = b2c.loc[b2c["day"].lt(cutoff_local_day)].copy()
    c2b = c2b.loc[c2b["day"].lt(cutoff_local_day)].copy()
    return b2c, c2b


def _external_evidence(
    b2c_queries: pd.DataFrame,
    c2b_queries: pd.DataFrame,
    *,
    mode: EvaluationMode,
) -> pd.DataFrame:
    if mode == EvaluationMode.CLEAN_ROLLING_EVAL:
        # Only current snapshots are available.  They cannot be backdated into
        # historical clean evaluation.
        return pd.DataFrame(columns=["knowledge_cell_id"])
    calibration_rows = b2c_queries.loc[
        pd.to_numeric(b2c_queries.get("actual_yuan"), errors="coerce").between(
            3_000, 1_000_000
        )
        & b2c_queries["fallback_b2c_yuan"].between(3_000, 1_000_000)
    ].copy()
    if calibration_rows.empty:
        return pd.DataFrame(columns=["knowledge_cell_id"])
    calibration = fit_external_market_calibration(
        calibration_rows,
        base_column="fallback_b2c_yuan",
        actual_column="actual_yuan",
    )
    combined = pd.concat([b2c_queries, c2b_queries], ignore_index=True, sort=False)
    combined = prepare_knowledge_cells(combined)
    proxies = calibrated_external_proxy(
        combined,
        calibration,
        base_column="external_base_yuan",
    )
    combined = combined.drop(
        columns=[column for column in proxies.columns if column in combined.columns],
        errors="ignore",
    )
    combined = pd.concat([combined.reset_index(drop=True), proxies.reset_index(drop=True)], axis=1)
    for column in EXTERNAL_COLUMNS:
        if column not in combined:
            combined[column] = np.nan
    confidence_rank = {"": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    combined["_confidence_rank"] = (
        combined["external_anchor_confidence"]
        .fillna("")
        .astype(str)
        .str.upper()
        .map(confidence_rank)
        .fillna(0)
    )
    combined = combined.sort_values(
        ["knowledge_cell_id", "_confidence_rank", "total_listing_count"],
        kind="stable",
    ).drop_duplicates("knowledge_cell_id", keep="last")
    keep = [
        "knowledge_cell_id",
        "external_b2c_proxy_yuan",
        "external_source_count",
        "external_source_dispersion",
        "external_anchor_confidence",
        *EXTERNAL_COLUMNS,
    ]
    return combined[keep].reset_index(drop=True)


def _fallback_evidence(queries: pd.DataFrame) -> pd.DataFrame:
    if queries.empty:
        return pd.DataFrame(columns=["knowledge_cell_id"])
    prepared = prepare_knowledge_cells(queries)
    grouped = prepared.groupby("knowledge_cell_id", sort=False)
    output = grouped[["fallback_b2c_yuan", "fallback_c2b_yuan"]].median().reset_index()
    output["fallback_query_count"] = grouped.size().to_numpy()
    return output


def _spread_ratio(
    price: float,
    calibration: dict[str, Any],
    field: str,
    model_id: Any | None = None,
) -> float:
    model = calibration.get("model_ids", {}).get(str(_integer(model_id)), {})
    model_value = pd.to_numeric(model.get(field), errors="coerce")
    if pd.notna(model_value) and _integer(model.get("n")) >= 2:
        return float(np.clip(model_value, 0.02, 0.35))
    band = calibration.get("price_bands", {}).get(price_band(float(price)), {})
    value = pd.to_numeric(band.get(field), errors="coerce")
    if pd.isna(value):
        fallback = (
            calibration.get("overall_spread_ratio_median")
            if field.endswith("median")
            else calibration.get("overall_spread_ratio_q25")
        )
        value = pd.to_numeric(fallback, errors="coerce")
    return float(np.clip(value if pd.notna(value) else 0.08, 0.02, 0.35))


def build_spread_calibration_from_truth(
    b2c_truth: pd.DataFrame,
    c2b_truth: pd.DataFrame,
    *,
    cutoff: Any,
    lookback_days: int = 90,
) -> dict[str, Any]:
    """Rebuild the B2C-C2B spread using only confirmed pre-cutoff vehicles."""

    cutoff_utc = _timestamp(cutoff)

    def latest(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        out = frame.loc[
            frame["eligible_for_transaction_target"].fillna(False).astype(bool)
        ].copy()
        out["transaction_at"] = pd.to_datetime(
            out["transaction_at"], errors="coerce", utc=True
        )
        out["observed_at"] = pd.to_datetime(
            out.get("observed_at"), errors="coerce", utc=True
        )
        out["price"] = pd.to_numeric(out["price"], errors="coerce")
        out = out.loc[
            out["transaction_at"].lt(cutoff_utc)
            & out["observed_at"].lt(cutoff_utc)
            & out["price"].between(3_000, 1_000_000)
            & out["source_vehicle_id"].notna()
        ]
        out = out.sort_values("transaction_at", kind="stable").drop_duplicates(
            "source_vehicle_id", keep="last"
        )
        model_id = pd.to_numeric(
            out.get("model_id", out.get("model_id_int")), errors="coerce"
        )
        out[f"{prefix}_model_id"] = model_id.astype("Int64")
        return out[
            ["source_vehicle_id", "transaction_at", "price", f"{prefix}_model_id"]
        ].rename(
            columns={"transaction_at": f"{prefix}_time", "price": f"{prefix}_price"}
        )

    paired = latest(b2c_truth, "b2c").merge(
        latest(c2b_truth, "c2b"),
        on="source_vehicle_id",
        how="inner",
        validate="one_to_one",
    )
    start = cutoff_utc - pd.Timedelta(days=lookback_days)
    paired = paired.loc[
        (paired["b2c_time"].ge(start) | paired["c2b_time"].ge(start))
        & paired["b2c_model_id"].eq(paired["c2b_model_id"])
        & paired["b2c_price"].gt(paired["c2b_price"])
        & paired["b2c_price"].div(paired["c2b_price"]).lt(2.0)
    ].copy()
    if paired.empty:
        raise ValueError("No legal pre-cutoff B2C/C2B vehicle pairs for spread calibration")
    paired["spread_ratio"] = (
        paired["b2c_price"] - paired["c2b_price"]
    ) / paired["b2c_price"]
    paired["spread_yuan"] = paired["b2c_price"] - paired["c2b_price"]
    paired["price_band"] = paired["b2c_price"].map(price_band)
    bands: dict[str, Any] = {}
    for band, group in paired.groupby("price_band", sort=False):
        bands[str(band)] = {
            "n": int(len(group)),
            "spread_ratio_q25": float(group["spread_ratio"].quantile(0.25)),
            "spread_ratio_median": float(group["spread_ratio"].median()),
            "spread_yuan_q25": float(group["spread_yuan"].quantile(0.25)),
            "spread_yuan_median": float(group["spread_yuan"].median()),
        }
    model_ids: dict[str, Any] = {}
    for model_id, group in paired.groupby("b2c_model_id", sort=False):
        if pd.isna(model_id) or len(group) < 2:
            continue
        band_name = price_band(float(group["b2c_price"].median()))
        prior = bands.get(band_name, {})
        prior_q25 = float(
            prior.get("spread_ratio_q25", paired["spread_ratio"].quantile(0.25))
        )
        prior_median = float(
            prior.get("spread_ratio_median", paired["spread_ratio"].median())
        )
        weight = float(len(group) / (len(group) + 5.0))
        model_ids[str(int(model_id))] = {
            "n": int(len(group)),
            "shrinkage_weight": weight,
            "spread_ratio_q25": float(
                weight * group["spread_ratio"].quantile(0.25)
                + (1.0 - weight) * prior_q25
            ),
            "spread_ratio_median": float(
                weight * group["spread_ratio"].median()
                + (1.0 - weight) * prior_median
            ),
        }
    return {
        "version": "v195_recent_internal_spread_budget_tminus1_v1",
        "data_cutoff": cutoff_utc.isoformat(),
        "lookback_days": lookback_days,
        "matched_vehicle_count": int(len(paired)),
        "overall_spread_ratio_q25": float(paired["spread_ratio"].quantile(0.25)),
        "overall_spread_ratio_median": float(paired["spread_ratio"].median()),
        "overall_spread_yuan_q25": float(paired["spread_yuan"].quantile(0.25)),
        "overall_spread_yuan_median": float(paired["spread_yuan"].median()),
        "price_bands": bands,
        "model_ids": model_ids,
        "target_leakage_policy": (
            "Rebuilt from confirmed paired transactions strictly before cutoff."
        ),
    }


def _confidence(row: pd.Series) -> str:
    b2_exact = str(row.get("b2c_pricing_route")) == "INTERNAL_EXACT_CELL"
    c2_exact = str(row.get("c2b_pricing_route")) == "INTERNAL_EXACT_CELL"
    external = str(row.get("external_anchor_confidence") or "").upper()
    if b2_exact and c2_exact:
        return "HIGH"
    if (b2_exact or c2_exact) and external in {"HIGH", "MEDIUM"}:
        return "HIGH"
    if b2_exact or c2_exact or external == "HIGH":
        return "MEDIUM"
    return "LOW"


def _quote_decision(row: pd.Series, config: DailyKnowledgeBuildConfig) -> str:
    confidence = str(row["knowledge_confidence"])
    dispersion = pd.to_numeric(row.get("external_source_dispersion"), errors="coerce")
    b2_level = pd.to_numeric(row.get("b2c_knowledge_level"), errors="coerce")
    c2_level = pd.to_numeric(row.get("c2b_knowledge_level"), errors="coerce")
    exact = bool(b2_level == 0 or c2_level == 0)
    if confidence == "HIGH" and exact and (
        pd.isna(dispersion) or float(dispersion) <= config.auto_quote_max_external_dispersion
    ):
        return QuoteDecision.AUTO_QUOTE.value
    if confidence in {"HIGH", "MEDIUM"}:
        return QuoteDecision.LOW_CONFIDENCE.value
    if _integer(row.get("model_id_numeric")) > 0:
        return QuoteDecision.MANUAL_REVIEW.value
    return QuoteDecision.NO_QUOTE.value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _anchor_routes(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    max_recency = float(out.attrs.get("max_internal_recency_days", 45.0))
    min_exact_count = int(out.attrs.get("min_exact_internal_count", 2))
    b2_recency = pd.to_numeric(
        out.get("b2c_internal_recency_days", pd.Series(0.0, index=out.index)),
        errors="coerce",
    )
    c2_recency = pd.to_numeric(
        out.get("c2b_internal_recency_days", pd.Series(0.0, index=out.index)),
        errors="coerce",
    )
    b2_exact = (
        out["b2c_knowledge_level"].eq(0)
        & out["b2c_internal_anchor_yuan"].notna()
        & pd.to_numeric(out.get("b2c_internal_count"), errors="coerce").fillna(0).ge(
            min_exact_count
        )
        & out.get("b2c_internal_confidence", "LOW").isin(["HIGH", "MEDIUM"])
        & b2_recency.le(max_recency)
    )
    c2_exact = (
        out["c2b_knowledge_level"].eq(0)
        & out["c2b_internal_anchor_yuan"].notna()
        & pd.to_numeric(out.get("c2b_internal_count"), errors="coerce").fillna(0).ge(
            min_exact_count
        )
        & out.get("c2b_internal_confidence", "LOW").isin(["HIGH", "MEDIUM"])
        & c2_recency.le(max_recency)
    )
    b2_fallback = pd.to_numeric(out["fallback_b2c_yuan"], errors="coerce")
    c2_fallback = pd.to_numeric(out["fallback_c2b_yuan"], errors="coerce")
    external = pd.to_numeric(out["external_b2c_proxy_yuan"], errors="coerce")
    b2_internal = pd.to_numeric(out["b2c_internal_anchor_yuan"], errors="coerce")
    c2_internal = pd.to_numeric(out["c2b_internal_anchor_yuan"], errors="coerce")

    b2 = b2_internal.where(b2_exact)
    b2_route = pd.Series("", index=out.index, dtype=object)
    b2_route.loc[b2_exact] = "INTERNAL_EXACT_CELL"
    use = b2.isna() & b2_fallback.notna()
    b2.loc[use] = b2_fallback.loc[use]
    b2_route.loc[use] = "MODEL_FALLBACK_L5"
    use = b2.isna() & external.notna()
    b2.loc[use] = external.loc[use]
    b2_route.loc[use] = "CALIBRATED_THREE_SOURCE_LISTING"
    use = b2.isna() & b2_internal.notna()
    b2.loc[use] = b2_internal.loc[use]
    b2_route.loc[use] = "INTERNAL_STRICT_TRIM_BACKOFF"

    ratios = pd.Series(
        [
            _spread_ratio(
                value,
                out.attrs["spread_calibration"],
                "spread_ratio_median",
                model_id,
            )
            for value, model_id in zip(
                b2.fillna(50_000), out.get("model_id_numeric", pd.Series(0, index=out.index))
            )
        ],
        index=out.index,
    )
    c2 = b2 * (1.0 - ratios)
    c2_route = pd.Series(
        "B2C_MINUS_MODEL_SHRUNK_RECENT_SPREAD", index=out.index, dtype=object
    )
    direct_c2 = c2_internal.where(c2_exact).fillna(c2_fallback)
    use = c2.notna() & direct_c2.notna()
    direct_delta = (direct_c2 - c2).clip(lower=-0.10 * c2, upper=0.10 * c2)
    c2.loc[use] = c2.loc[use] + 0.25 * direct_delta.loc[use]
    c2_route.loc[use] += "+BOUNDED_DIRECT_ACCEPTANCE_EVIDENCE"
    use = c2.isna() & direct_c2.notna()
    c2.loc[use] = direct_c2.loc[use]
    c2_route.loc[use] = "DIRECT_C2B_ONLY_WHEN_B2C_UNAVAILABLE"
    use = c2.isna() & c2_internal.notna()
    c2.loc[use] = c2_internal.loc[use]
    c2_route.loc[use] = "INTERNAL_STRICT_TRIM_BACKOFF"

    use = b2.isna() & c2.notna()
    ratios = pd.Series(
        [
            _spread_ratio(
                value,
                out.attrs["spread_calibration"],
                "spread_ratio_median",
                model_id,
            )
            for value, model_id in zip(
                c2.fillna(50_000), out.get("model_id_numeric", pd.Series(0, index=out.index))
            )
        ],
        index=out.index,
    )
    b2.loc[use] = c2.loc[use] / (1.0 - ratios.loc[use])
    b2_route.loc[use] = "C2B_PLUS_RECENT_INTERNAL_SPREAD"
    out["raw_b2c_anchor_yuan"] = b2
    out["raw_c2b_anchor_yuan"] = c2
    out["b2c_pricing_route"] = b2_route
    out["c2b_pricing_route"] = c2_route
    return out


def _apply_manual_override(
    row: pd.Series,
    registry: ManualOverrideRegistry,
) -> tuple[float, float, float | None, dict[str, Any] | None]:
    match = registry.match(
        {
            0: str(row["legacy_l0_canonical_key"]),
            -1: str(row["knowledge_cell_id"]),
        }
    )
    b2 = float(row["raw_b2c_anchor_yuan"])
    c2 = float(row["raw_c2b_anchor_yuan"])
    listing = pd.to_numeric(row.get("listing_price_yuan"), errors="coerce")
    if match is None:
        return b2, c2, float(listing) if pd.notna(listing) else None, None
    values = match.values
    local_factor, local_adjustment = local_reference_adjustment(
        match,
        registration_date=row.get("registration_date_normalized"),
        mileage_km=row.get("mileage_km_normalized"),
    )
    controls = {
        "override_type": match.override_type,
        "delta_yuan": match.delta_yuan,
        "floor_yuan": match.floor_yuan,
        "cap_yuan": match.cap_yuan,
    }
    b2 = apply_override_value(
        b2,
        replacement=(
            values["expected_b2c_transaction_price"] * local_factor
            if "expected_b2c_transaction_price" in values
            else None
        ),
        **controls,
    )
    c2 = apply_override_value(
        c2,
        replacement=(
            values["expected_final_acquisition_price"] * local_factor
            if "expected_final_acquisition_price" in values
            else None
        ),
        **controls,
    )
    if pd.notna(listing):
        listing = apply_override_value(
            float(listing),
            replacement=(
                values["suggested_listing_price"] * local_factor
                if "suggested_listing_price" in values
                else None
            ),
            **controls,
        )
    elif values.get("suggested_listing_price") is not None:
        listing = values["suggested_listing_price"] * local_factor
    return (
        b2,
        c2,
        float(listing) if pd.notna(listing) else None,
        {
            "override_id": match.override_id,
            "override_type": match.override_type,
            "version": match.version,
            "reason": match.reason,
            **local_adjustment,
        },
    )


def materialize_daily_knowledge(
    root: Path,
    *,
    cutoff: Any,
    mode: EvaluationMode = EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE,
    query_frames: Iterable[pd.DataFrame] = (),
    config: DailyKnowledgeBuildConfig | None = None,
) -> pd.DataFrame:
    config = config or DailyKnowledgeBuildConfig()
    cutoff_utc = _timestamp(cutoff)
    truth_root = root / "data/v195/multi_source_truth"
    b2c_truth = pd.read_parquet(
        truth_root / "price_type=INTERNAL_B2C_TRANSACTION/part-000.parquet"
    )
    c2b_truth = pd.read_parquet(
        truth_root / "price_type=INTERNAL_C2B_TRANSACTION/part-000.parquet"
    )
    b2c_queries, c2b_queries = _load_trace_queries(
        root, b2c_truth, c2b_truth, cutoff=cutoff_utc
    )
    supplied_queries = [frame.copy() for frame in query_frames if not frame.empty]
    universe_queries = (
        [b2c_queries, c2b_queries, *supplied_queries]
        if config.include_full_active_universe
        else supplied_queries
    )
    universe = build_cell_universe(
        b2c_truth,
        c2b_truth,
        cutoff=cutoff_utc,
        query_frames=universe_queries,
        universe_days=config.universe_days,
        include_truth_cells=config.include_full_active_universe,
    )
    hierarchy_book = build_price_book(b2c_truth, c2b_truth, cutoff=cutoff_utc)
    clearance_audit = hierarchy_book.attrs.get("high_confidence_clearance_audit")
    if isinstance(clearance_audit, pd.DataFrame) and not clearance_audit.empty:
        audit_path = root / "results/audits/v195_394_high_confidence_clearance_audit.csv"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        clearance_audit.to_csv(audit_path, index=False, encoding="utf-8-sig")
    b2_lookup = _lookup_hierarchy(universe, hierarchy_book, "b2c").rename(
        columns={
            "price_book_anchor_yuan": "b2c_internal_anchor_yuan",
            "price_book_low_yuan": "b2c_internal_low_yuan",
            "price_book_high_yuan": "b2c_internal_high_yuan",
            "price_book_sample_count": "b2c_internal_count",
            "price_book_recency_days": "b2c_internal_recency_days",
            "price_book_hit_level": "b2c_knowledge_level",
            "price_book_confidence": "b2c_internal_confidence",
        }
    )
    c2_lookup = _lookup_hierarchy(universe, hierarchy_book, "c2b").rename(
        columns={
            "price_book_anchor_yuan": "c2b_internal_anchor_yuan",
            "price_book_low_yuan": "c2b_internal_low_yuan",
            "price_book_high_yuan": "c2b_internal_high_yuan",
            "price_book_sample_count": "c2b_internal_count",
            "price_book_recency_days": "c2b_internal_recency_days",
            "price_book_hit_level": "c2b_knowledge_level",
            "price_book_confidence": "c2b_internal_confidence",
        }
    )
    cells = pd.concat(
        [universe.reset_index(drop=True), b2_lookup, c2_lookup], axis=1
    )
    fallback = _fallback_evidence(
        pd.concat([b2c_queries, c2b_queries, *supplied_queries], ignore_index=True, sort=False)
    )
    external = _external_evidence(b2c_queries, c2b_queries, mode=mode)
    cells = cells.merge(fallback, on="knowledge_cell_id", how="left", validate="one_to_one")
    cells = cells.merge(external, on="knowledge_cell_id", how="left", validate="one_to_one")
    for column in (
        "fallback_b2c_yuan",
        "fallback_c2b_yuan",
        "external_b2c_proxy_yuan",
        "listing_price_yuan",
        "external_source_dispersion",
    ):
        if column not in cells:
            cells[column] = np.nan

    spread = build_spread_calibration_from_truth(
        b2c_truth,
        c2b_truth,
        cutoff=cutoff_utc,
    )
    cells.attrs["spread_calibration"] = spread
    cells.attrs["max_internal_recency_days"] = config.auto_quote_max_internal_recency_days
    cells.attrs["min_exact_internal_count"] = config.auto_quote_min_exact_internal_count
    cells = _anchor_routes(cells)
    cells["knowledge_confidence"] = cells.apply(_confidence, axis=1)

    ladder_config = load_ladder_config(root / "config/v195_price_ladder.json")
    ladder_config["observed_spread_budget"] = spread
    engine = V195ProductionPricingEngine(ladder_config)
    registry = ManualOverrideRegistry.load(
        root / "data/manual_price_book/manual_price_book_active.csv",
        as_of=cutoff_utc,
        mode=mode,
    )
    records: list[dict[str, Any]] = []
    for _, row in cells.iterrows():
        b2, c2, listing, override = _apply_manual_override(row, registry)
        if not np.isfinite(b2) or not np.isfinite(c2) or b2 <= 0 or c2 <= 0:
            records.append({field: np.nan for field in ORDERED_FIELDS})
            continue
        dispersion = pd.to_numeric(row.get("external_source_dispersion"), errors="coerce")
        quote = engine.quote(
            RawPricingInputs(
                expected_b2c_transaction_price=b2,
                expected_final_c2b_price=c2,
                external_listing_anchor=listing,
                external_listing_dispersion=(
                    float(dispersion) if pd.notna(dispersion) else None
                ),
                condition_grade=str(row["condition_bucket_key"]),
                confidence=str(row["knowledge_confidence"]),
            )
        )
        records.append(
            {
                **{field: quote[field] for field in ORDERED_FIELDS},
                "raw_prices": _json(quote["raw_prices"]),
                "projected_prices": _json(quote["projected_prices"]),
                "adjustment_amount": _json(quote["adjustment_amount"]),
                "cost_inputs": _json(quote["cost_inputs"]),
                "constraint_triggered": quote["constraint_triggered"],
                "constraint_reason": _json(quote["constraint_reason"]),
                "projection_version": quote["projection_version"],
                "hierarchy_violation_count": len(
                    hierarchy_violations(
                        quote["projected_prices"],
                        minimum_gap=float(ladder_config["minimum_b2c_to_max_c2b_gap"]),
                    )
                ),
                "b2c_anchor_repair_used": quote["b2c_anchor_repair_used"],
                "manual_override_flag": override is not None,
                "manual_override": _json(override or {}),
            }
        )
    ladder = pd.DataFrame(records)
    cells = pd.concat([cells.reset_index(drop=True), ladder.reset_index(drop=True)], axis=1)
    cells["quote_decision"] = cells.apply(lambda row: _quote_decision(row, config), axis=1)
    cells.loc[cells[ORDERED_FIELDS].isna().any(axis=1), "quote_decision"] = (
        QuoteDecision.NO_QUOTE.value
    )
    cells["source_evidence_refs"] = cells.apply(
        lambda row: _json(
            {
                "b2c_route": row["b2c_pricing_route"],
                "c2b_route": row["c2b_pricing_route"],
                "b2c_internal_level": int(row["b2c_knowledge_level"]),
                "c2b_internal_level": int(row["c2b_knowledge_level"]),
                "b2c_internal_count": int(row["b2c_internal_count"]),
                "c2b_internal_count": int(row["c2b_internal_count"]),
                "external_source_count": int(
                    _integer(row.get("external_source_count"))
                ),
                "external_is_asking_price": True,
            }
        ),
        axis=1,
    )
    version_day = cutoff_utc.tz_convert("Asia/Shanghai").strftime("%Y%m%d")
    cells["schema_version"] = "v195.daily_vehicle_price_knowledge.v1"
    cells["snapshot_version"] = f"v195_daily_vehicle_price_knowledge_{version_day}"
    cells["evaluation_mode"] = mode.value
    cells["data_cutoff"] = cutoff_utc.isoformat()
    cells["effective_from"] = cutoff_utc.isoformat()
    cells["expire_at"] = (cutoff_utc + pd.Timedelta(days=config.snapshot_ttl_days)).isoformat()
    cells["generated_at"] = datetime.now(timezone.utc).isoformat()
    cells["same_series_year_primary_anchor"] = False
    return cells


def write_daily_snapshot(
    frame: pd.DataFrame,
    root: Path,
    *,
    cutoff: Any,
    mode: EvaluationMode,
) -> dict[str, Any]:
    cutoff_utc = _timestamp(cutoff)
    day = cutoff_utc.tz_convert("Asia/Shanghai").strftime("%Y%m%d")
    snapshot_dir = root / "data/v195/snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    versioned = snapshot_dir / f"daily_vehicle_price_knowledge_full_{day}.parquet"
    temporary = versioned.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(versioned)
    digest = hashlib.sha256(versioned.read_bytes()).hexdigest()
    pointer_path = root / "data/v195/current_daily_vehicle_price_knowledge.json"
    previous: str | None = None
    if pointer_path.exists():
        try:
            previous = json.loads(pointer_path.read_text(encoding="utf-8")).get("snapshot_path")
        except (OSError, ValueError, TypeError):
            previous = None
    manifest = {
        "schema_version": "v195.daily_vehicle_price_knowledge.manifest.v1",
        "snapshot_path": str(versioned),
        "previous_snapshot_path": previous,
        "sha256": digest,
        "row_count": int(len(frame)),
        "data_cutoff": cutoff_utc.isoformat(),
        "evaluation_mode": mode.value,
        "auto_quote_count": int(frame["quote_decision"].eq("AUTO_QUOTE").sum()),
        "manual_or_low_count": int(
            frame["quote_decision"].isin(["LOW_CONFIDENCE", "MANUAL_REVIEW"]).sum()
        ),
        "no_quote_count": int(frame["quote_decision"].eq("NO_QUOTE").sum()),
        "hierarchy_violation_count": int(frame["hierarchy_violation_count"].sum()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    pointer_temp = pointer_path.with_suffix(".tmp.json")
    pointer_temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer_temp.replace(pointer_path)
    return manifest


class DailyVehicleKnowledgeStore:
    """Snapshot-first lookup with on-demand strict-cell materialization."""

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        root: Path | None = None,
        materializer: Any | None = None,
        commercial_frame: pd.DataFrame | None = None,
    ) -> None:
        self.frame = frame.copy()
        self._exact = self.frame.set_index("knowledge_cell_id", drop=False)
        self.root = root
        self._materializer = materializer
        self._commercial = (
            commercial_frame.set_index("knowledge_cell_id", drop=False)
            if commercial_frame is not None and not commercial_frame.empty
            else pd.DataFrame()
        )
        self._materialized_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._materialized_cache_size = 2_048

    @classmethod
    def load_current(cls, root: Path) -> "DailyVehicleKnowledgeStore":
        pointer = json.loads(
            (root / "data/v195/current_daily_vehicle_price_knowledge.json").read_text(
                encoding="utf-8"
            )
        )
        path = Path(pointer["snapshot_path"])
        if not path.is_absolute():
            path = root / path
        commercial_path = root / "data/v195/supervised_commercial_price_ladder.parquet"
        commercial = pd.read_parquet(commercial_path) if commercial_path.exists() else None
        return cls(pd.read_parquet(path), root=root, commercial_frame=commercial)

    def lookup(
        self,
        payload: dict[str, Any],
        *,
        fallback_b2c_yuan: float | None = None,
        fallback_c2b_yuan: float | None = None,
        target_side: str | None = None,
        materialize_on_miss: bool = True,
        allow_trusted_snapshot_hit: bool = True,
    ) -> dict[str, Any]:
        query = prepare_knowledge_cells(pd.DataFrame([payload])).iloc[0]
        snapshot_cell_id = str(query["knowledge_cell_id"])
        cell_id = exact_seven_element_fingerprint(payload)
        if target_side is None:
            task = str(payload.get("pricing_task") or payload.get("price_role") or "").upper()
            if "C2B" in task or "PURCHASE" in task or fallback_c2b_yuan is not None:
                target_side = "C2B"
            else:
                target_side = "B2C"
        target_side = str(target_side).upper()
        if not self._commercial.empty and cell_id in self._commercial.index:
            row = self._commercial.loc[cell_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            return {
                **row.to_dict(),
                "knowledge_lookup_route": "SUPERVISED_COMMERCIAL_EXACT_CELL",
                "knowledge_cell_evidence_level": f"FULL_KNOWLEDGE_EXACT_{target_side}",
                "quote_decision": QuoteDecision.AUTO_QUOTE.value,
            }
        if cell_id in self._materialized_cache:
            cached = self._materialized_cache.pop(cell_id)
            self._materialized_cache[cell_id] = cached
            return {**cached, "knowledge_lookup_route": "ON_DEMAND_EXACT_CELL_CACHE_HIT"}
        comparable: dict[str, Any] | None = None
        if snapshot_cell_id in self._exact.index:
            row = self._exact.loc[snapshot_cell_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            side_prefix = "c2b" if target_side == "C2B" else "b2c"
            exact_internal = bool(
                _integer(row.get(f"{side_prefix}_knowledge_level"), -1) == 0
                and str(row.get(f"{side_prefix}_pricing_route") or "")
                == "INTERNAL_EXACT_CELL"
                and pd.notna(row.get(f"{side_prefix}_internal_anchor_yuan"))
            )
            trusted_materialized = bool(
                exact_internal
                and _integer(row.get("hierarchy_violation_count"), 0) == 0
            )
            if trusted_materialized and allow_trusted_snapshot_hit:
                return {
                    **row.to_dict(),
                    "knowledge_lookup_route": "TRUSTED_MATERIALIZED_CELL_HIT",
                    "knowledge_cell_evidence_level": f"EXACT_INTERNAL_{target_side}",
                }
            comparable = row.to_dict()
            comparable["knowledge_comparable_distance"] = 0.0
        model_id = _integer(query["model_id_numeric"])
        model_year = _integer(query["model_year_numeric"])
        candidates = self.frame.loc[
            self.frame["model_id_numeric"].eq(model_id)
            & self.frame["model_year_numeric"].eq(model_year)
        ].copy()
        if comparable is None and not candidates.empty:
            query_registration = pd.to_datetime(
                query["registration_date_normalized"], errors="coerce"
            )
            registration = pd.to_datetime(
                candidates["registration_date_normalized"], errors="coerce"
            )
            registration_distance = (
                (registration - query_registration).abs().dt.days.fillna(3650) / 365.0
            )
            query_mileage = pd.to_numeric(
                query["mileage_km_normalized"], errors="coerce"
            )
            mileage_distance = (
                pd.to_numeric(candidates["mileage_km_normalized"], errors="coerce")
                .sub(float(query_mileage) if pd.notna(query_mileage) else 0.0)
                .abs()
                .fillna(200_000)
                / 50_000.0
            )
            candidates["_distance"] = registration_distance + mileage_distance
            candidates["_distance"] += 0.25 * ~candidates["city_key"].eq(
                query["city_key"]
            )
            candidates["_distance"] += 0.15 * ~candidates[
                "condition_bucket_key"
            ].eq(query["condition_bucket_key"])
            row = candidates.sort_values("_distance", kind="stable").iloc[0]
            comparable = row.drop(labels=["_distance"]).to_dict()
            comparable["knowledge_comparable_distance"] = float(row["_distance"])

        fallback_b2c_yuan = fallback_b2c_yuan or pd.to_numeric(
            payload.get("fallback_b2c_yuan"), errors="coerce"
        )
        fallback_c2b_yuan = fallback_c2b_yuan or pd.to_numeric(
            payload.get("fallback_c2b_yuan"), errors="coerce"
        )
        if not materialize_on_miss:
            return {
                "knowledge_lookup_route": "MISS_REQUIRES_ON_DEMAND_MATERIALIZATION",
                "quote_decision": QuoteDecision.NO_QUOTE.value,
                "knowledge_cell_id": cell_id,
                "strict_model_year_comparable_found": comparable is not None,
                "comparable_cell_id": (
                    comparable.get("knowledge_cell_id") if comparable else None
                ),
            }
        if self._materializer is None:
            if self.root is None:
                return {
                    "knowledge_lookup_route": "MISS_MATERIALIZER_UNAVAILABLE",
                    "quote_decision": QuoteDecision.NO_QUOTE.value,
                    "knowledge_cell_id": cell_id,
                }
            from .v195_on_demand_materializer import ExternalOnDemandMaterializer

            cutoff = self.frame.get("data_cutoff", pd.Series(dtype=object)).dropna()
            cutoff_value = cutoff.iloc[-1] if not cutoff.empty else pd.Timestamp.now(tz="UTC")
            self._materializer = ExternalOnDemandMaterializer(
                self.root,
                cutoff=cutoff_value,
            )
        result = self._materializer.materialize(
            payload,
            fallback_b2c_yuan=(
                float(fallback_b2c_yuan)
                if pd.notna(fallback_b2c_yuan)
                else None
            ),
            fallback_c2b_yuan=(
                float(fallback_c2b_yuan)
                if pd.notna(fallback_c2b_yuan)
                else None
            ),
            comparable=comparable,
        )
        result["knowledge_cell_id"] = cell_id
        result["requested_knowledge_cell_id"] = cell_id
        result["snapshot_evidence_cell_id"] = snapshot_cell_id
        result["strict_model_year_comparable_found"] = comparable is not None
        if result.get("knowledge_lookup_route") in {
            "ON_DEMAND_STRICT_PRICE_CELL",
            "MANUAL_APPRAISER_EXACT_CELL",
        }:
            self._materialized_cache[cell_id] = dict(result)
            while len(self._materialized_cache) > self._materialized_cache_size:
                self._materialized_cache.popitem(last=False)
        return result
