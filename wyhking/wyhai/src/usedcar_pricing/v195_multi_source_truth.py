"""Build the v195 source-normalized price truth and evidence dataset."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .v195_price_book_schema import (
    PriceType,
    TRUTH_COLUMNS,
    compact,
    fuzzy_listing_signature,
    normalize_trim,
    stable_hash,
    strict_identity_key,
    text,
    vehicle_signature,
)


FRESH_LISTING_DAYS = 14


def _numeric(series: pd.Series, scale: float = 1.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce") * scale


def _datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _registration_datetime(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip()
    normalized = normalized.str.replace(
        r"^((?:19|20)\d{2})年$", r"\1-01-01", regex=True
    )
    normalized = normalized.str.replace(
        r"^((?:19|20)\d{2})年(\d{1,2})月$", r"\1-\2-01", regex=True
    )
    return pd.to_datetime(normalized, errors="coerce")


def _bool(series: pd.Series, default: bool = False) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(default)
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    result = pd.Series(default, index=series.index, dtype=bool)
    result.loc[normalized.isin({"true", "1", "yes", "y", "是"})] = True
    result.loc[normalized.isin({"false", "0", "no", "n", "否"})] = False
    return result


def _record_ids(frame: pd.DataFrame, candidates: list[str], source: str) -> pd.Series:
    output = pd.Series("", index=frame.index, dtype=object)
    for column in candidates:
        if column not in frame:
            continue
        values = frame[column].fillna("").astype(str).str.strip()
        output = output.where(output.ne(""), values)
    missing = output.eq("")
    if missing.any():
        output.loc[missing] = [
            stable_hash([source, index], "record") for index in frame.index[missing]
        ]
    return output


def _quality_flags(
    frame: pd.DataFrame,
    *,
    price: pd.Series,
    identity_key: pd.Series,
    observed_at: pd.Series,
    transaction: bool,
    freshness_cutoff: pd.Timestamp,
    extra_flags: dict[str, pd.Series] | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    flags: list[list[str]] = [[] for _ in range(len(frame))]

    def add(mask: pd.Series | np.ndarray, code: str) -> None:
        values = np.asarray(mask, dtype=bool)
        for position in np.flatnonzero(values):
            flags[int(position)].append(code)

    max_price = 1_000_000 if transaction else 2_000_000
    valid_price = price.between(3_000, max_price)
    add(price.isna(), "PRICE_MISSING")
    add(price.notna() & ~valid_price, "PRICE_OUT_OF_RANGE")
    add(identity_key.eq(""), "STRICT_IDENTITY_MISSING")
    add(observed_at.isna(), "OBSERVED_AT_MISSING")
    fresh = observed_at.ge(freshness_cutoff) if not transaction else pd.Series(True, index=frame.index)
    if not transaction:
        add(~fresh, "STALE_SNAPSHOT")
        add(pd.Series(True, index=frame.index), "LISTING_PRICE_NOT_TRANSACTION_TARGET")
    for code, mask in (extra_flags or {}).items():
        add(mask, code)

    quality = pd.Series(["|".join(items) for items in flags], index=frame.index)
    target_eligible = valid_price & transaction
    clean_eligible = valid_price & identity_key.ne("") & observed_at.notna()
    online_eligible = clean_eligible & fresh
    return quality, target_eligible, clean_eligible, online_eligible


def _base_output(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(pd.NA, index=index, dtype=object) for column in TRUTH_COLUMNS})


def _finalize(
    out: pd.DataFrame,
    *,
    freshness_cutoff: pd.Timestamp,
    transaction: bool,
    extra_flags: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    out["trim_normalized"] = [
        normalize_trim(trim, brand=brand, series=series)
        for trim, brand, series in zip(out["trim"], out["brand"], out["series"])
    ]
    out["strict_identity_key"] = [
        strict_identity_key(
            model_id=model_id,
            brand=brand,
            series=series,
            trim=trim,
            model_year=year,
        )
        for model_id, brand, series, trim, year in zip(
            out["model_id"], out["brand"], out["series"], out["trim"], out["model_year"]
        )
    ]
    out["vehicle_signature"] = [
        vehicle_signature(
            identity_key=identity,
            registration_date=registration,
            mileage_km_value=mileage,
            city=city,
            transfer_count=transfer,
            color=color,
        )
        for identity, registration, mileage, city, transfer, color in zip(
            out["strict_identity_key"],
            out["registration_date"],
            out["mileage_km"],
            out["city"],
            out["transfer_count"],
            out["color"],
        )
    ]
    listing = ~out["price_type"].isin(
        {PriceType.INTERNAL_B2C_TRANSACTION.value, PriceType.INTERNAL_C2B_TRANSACTION.value}
    )
    fuzzy = pd.Series("", index=out.index, dtype=object)
    if listing.any():
        fuzzy.loc[listing] = [
            fuzzy_listing_signature(
                brand=brand,
                series=series,
                trim=trim,
                model_year=year,
                registration_date=registration,
                mileage_km_value=mileage,
                city=city,
                color=color,
                price=price,
            )
            for brand, series, trim, year, registration, mileage, city, color, price in zip(
                out.loc[listing, "brand"],
                out.loc[listing, "series"],
                out.loc[listing, "trim"],
                out.loc[listing, "model_year"],
                out.loc[listing, "registration_date"],
                out.loc[listing, "mileage_km"],
                out.loc[listing, "city"],
                out.loc[listing, "color"],
                out.loc[listing, "price"],
            )
        ]
    out["fuzzy_vehicle_signature"] = fuzzy
    quality, target, clean, online = _quality_flags(
        out,
        price=pd.to_numeric(out["price"], errors="coerce"),
        identity_key=out["strict_identity_key"].fillna("").astype(str),
        observed_at=pd.to_datetime(out["observed_at"], errors="coerce", utc=True),
        transaction=transaction,
        freshness_cutoff=freshness_cutoff,
        extra_flags=extra_flags,
    )
    out["data_quality_flags"] = quality
    out["eligible_for_transaction_target"] = target
    out["eligible_for_clean_eval"] = clean
    out["eligible_for_online_quote"] = online
    out["cross_source_cluster_id"] = ""
    out["dedup_weight"] = 1.0
    return out[TRUTH_COLUMNS].reset_index(drop=True)


def _internal(path: Path, price_type: PriceType, freshness_cutoff: pd.Timestamp) -> pd.DataFrame:
    columns = [
        "daily_business_event_key",
        "daily_source_row_hash",
        "vehicle_id",
        "model_id",
        "series_key",
        "brand",
        "series",
        "canonical_trim_key",
        "trim",
        "model_year",
        "first_registration_date",
        "mileage_wan_km",
        "city",
        "transfer_count",
        "color_raw",
        "inspection_grade_norm",
        "inspection_grade",
        "price_yuan",
        "event_time",
        "pricing_available_at",
        "knowledge_available_at",
        "runtime_candidate_dedup_keep_flag",
        "market_clean_flag",
        "is_token_price",
    ]
    available = set(pd.read_parquet(path, columns=[]).columns)
    # pandas cannot expose parquet columns through columns=[] on every engine.
    if not available:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(path).schema_arrow.names)
    frame = pd.read_parquet(path, columns=[column for column in columns if column in available])
    out = _base_output(frame.index)
    out["source"] = "dongchedi_internal"
    out["source_record_id"] = _record_ids(
        frame, ["daily_business_event_key", "daily_source_row_hash", "vehicle_id"], "internal"
    )
    out["source_vehicle_id"] = frame.get("vehicle_id", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["model_id"] = pd.to_numeric(frame.get("model_id"), errors="coerce").astype("Int64")
    out["source_model_id"] = out["model_id"].astype(object)
    out["series_id"] = frame.get("series_key", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["brand"] = frame.get("brand", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["series"] = frame.get("series", pd.Series("", index=frame.index)).fillna("").astype(str)
    trim = frame.get("canonical_trim_key", pd.Series("", index=frame.index)).fillna("").astype(str)
    fallback_trim = frame.get("trim", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["trim"] = trim.where(trim.ne(""), fallback_trim)
    out["model_year"] = pd.to_numeric(frame.get("model_year"), errors="coerce").astype("Int64")
    out["registration_date"] = pd.to_datetime(frame.get("first_registration_date"), errors="coerce")
    out["mileage_km"] = _numeric(frame.get("mileage_wan_km"), 10_000.0)
    out["city"] = frame.get("city", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["transfer_count"] = pd.to_numeric(frame.get("transfer_count"), errors="coerce").astype("Int64")
    out["color"] = frame.get("color_raw", pd.Series("", index=frame.index)).fillna("").astype(str)
    grade = frame.get("inspection_grade_norm", pd.Series("", index=frame.index)).fillna("").astype(str)
    fallback_grade = frame.get("inspection_grade", pd.Series("", index=frame.index)).fillna("").astype(str)
    out["condition_grade"] = grade.where(grade.ne(""), fallback_grade)
    out["price"] = _numeric(frame.get("price_yuan"))
    out["price_type"] = price_type.value
    pricing_at = _datetime(frame.get("pricing_available_at", pd.Series(pd.NaT, index=frame.index)))
    knowledge_at = _datetime(frame.get("knowledge_available_at", pd.Series(pd.NaT, index=frame.index)))
    out["observed_at"] = pricing_at.where(pricing_at.notna(), knowledge_at)
    out["transaction_at"] = _datetime(frame.get("event_time", pd.Series(pd.NaT, index=frame.index)))
    out["source_confidence"] = "HIGHEST_INTERNAL_TRANSACTION"
    extra = {
        "SOURCE_DEDUP_REJECTED": ~_bool(
            frame.get("runtime_candidate_dedup_keep_flag", pd.Series(False, index=frame.index))
        ),
        "MARKET_CLEAN_REJECTED": ~_bool(
            frame.get("market_clean_flag", pd.Series(False, index=frame.index))
        ),
        "TOKEN_PRICE": _bool(frame.get("is_token_price", pd.Series(False, index=frame.index))),
    }
    finalized = _finalize(
        out, freshness_cutoff=freshness_cutoff, transaction=True, extra_flags=extra
    )
    rejected = (
        extra["SOURCE_DEDUP_REJECTED"] | extra["MARKET_CLEAN_REJECTED"] | extra["TOKEN_PRICE"]
    ).to_numpy()
    finalized.loc[rejected, "eligible_for_transaction_target"] = False
    finalized.loc[rejected, "eligible_for_clean_eval"] = False
    finalized.loc[rejected, "eligible_for_online_quote"] = False
    return finalized


def _dongchedi(path: Path, freshness_cutoff: pd.Timestamp) -> pd.DataFrame:
    columns = [
        "sku_id",
        "brand",
        "series",
        "series_id",
        "standard_vehicle",
        "trim",
        "model_year",
        "first_registration_time",
        "mileage_wan_km",
        "city",
        "transfer_count",
        "color",
        "listing_price_yuan",
        "fetched_at",
        "allowed_for_historical_backtest",
        "allowed_for_online_current_quote",
    ]
    frame = pd.read_parquet(path, columns=columns)
    out = _base_output(frame.index)
    out["source"] = "dongchedi"
    out["source_record_id"] = frame["sku_id"].fillna("").astype(str)
    out["source_vehicle_id"] = out["source_record_id"]
    out["model_id"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    out["source_model_id"] = pd.NA
    out["series_id"] = frame["series_id"].fillna("").astype(str)
    out["brand"] = frame["brand"].fillna("").astype(str)
    out["series"] = frame["series"].fillna("").astype(str)
    out["trim"] = frame["trim"].fillna("").astype(str).where(
        frame["trim"].fillna("").astype(str).ne(""), frame["standard_vehicle"].fillna("").astype(str)
    )
    out["model_year"] = pd.to_numeric(frame["model_year"], errors="coerce").astype("Int64")
    out["registration_date"] = pd.to_datetime(frame["first_registration_time"], errors="coerce")
    out["mileage_km"] = _numeric(frame["mileage_wan_km"], 10_000.0)
    out["city"] = frame["city"].fillna("").astype(str)
    out["transfer_count"] = pd.to_numeric(frame["transfer_count"], errors="coerce").astype("Int64")
    out["color"] = frame["color"].fillna("").astype(str)
    out["condition_grade"] = ""
    out["price"] = _numeric(frame["listing_price_yuan"])
    out["price_type"] = PriceType.DONGCHEDI_LISTING.value
    out["observed_at"] = _datetime(frame["fetched_at"])
    out["transaction_at"] = pd.NaT
    out["source_confidence"] = "TRUSTED_EXTERNAL_LISTING"
    extra = {
        "MODEL_ID_UNMAPPED": pd.Series(True, index=frame.index),
        "SOURCE_HISTORICAL_DISABLED": ~_bool(frame["allowed_for_historical_backtest"]),
        "SOURCE_ONLINE_DISABLED": ~_bool(frame["allowed_for_online_current_quote"]),
    }
    finalized = _finalize(
        out, freshness_cutoff=freshness_cutoff, transaction=False, extra_flags=extra
    )
    finalized.loc[extra["SOURCE_HISTORICAL_DISABLED"].to_numpy(), "eligible_for_clean_eval"] = False
    finalized.loc[extra["SOURCE_ONLINE_DISABLED"].to_numpy(), "eligible_for_online_quote"] = False
    return finalized


def _autohome(path: Path, freshness_cutoff: pd.Timestamp) -> pd.DataFrame:
    columns = [
        "listing_id",
        "carname",
        "display_name",
        "model_year",
        "price_yuan",
        "mileage_wan_km",
        "first_register_date",
        "city_name",
        "transfer_count",
        "brand_id",
        "series_id",
        "spec_id",
        "snapshot_date",
        "allowed_for_historical_backtest",
        "allowed_for_online_current_quote",
    ]
    frame = pd.read_parquet(path, columns=columns)
    title = frame["display_name"].fillna("").astype(str).where(
        frame["display_name"].fillna("").astype(str).ne(""), frame["carname"].fillna("").astype(str)
    )
    extracted_series = title.str.replace(r"\s*20\d{2}款.*$", "", regex=True).str.strip()
    out = _base_output(frame.index)
    out["source"] = "autohome"
    out["source_record_id"] = frame["listing_id"].fillna("").astype(str)
    out["source_vehicle_id"] = out["source_record_id"]
    out["model_id"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    out["source_model_id"] = frame["spec_id"].astype(object)
    out["series_id"] = frame["series_id"].fillna("").astype(str)
    out["brand"] = frame["brand_id"].fillna("").astype(str)
    out["series"] = extracted_series
    out["trim"] = title
    out["model_year"] = pd.to_numeric(frame["model_year"], errors="coerce").astype("Int64")
    out["registration_date"] = _registration_datetime(frame["first_register_date"])
    out["mileage_km"] = _numeric(frame["mileage_wan_km"], 10_000.0)
    out["city"] = frame["city_name"].fillna("").astype(str)
    out["transfer_count"] = pd.to_numeric(frame["transfer_count"], errors="coerce").astype("Int64")
    out["color"] = ""
    out["condition_grade"] = ""
    out["price"] = _numeric(frame["price_yuan"])
    out["price_type"] = PriceType.AUTOHOME_LISTING.value
    out["observed_at"] = _datetime(frame["snapshot_date"])
    out["transaction_at"] = pd.NaT
    out["source_confidence"] = "EXTERNAL_LISTING"
    extra = {
        "MODEL_ID_UNMAPPED": pd.Series(True, index=frame.index),
        "BRAND_NAME_UNAVAILABLE_SOURCE_ID_ONLY": pd.Series(True, index=frame.index),
        "SOURCE_HISTORICAL_DISABLED": ~_bool(frame["allowed_for_historical_backtest"]),
        "SOURCE_ONLINE_DISABLED": ~_bool(frame["allowed_for_online_current_quote"]),
    }
    finalized = _finalize(
        out, freshness_cutoff=freshness_cutoff, transaction=False, extra_flags=extra
    )
    finalized.loc[extra["SOURCE_HISTORICAL_DISABLED"].to_numpy(), "eligible_for_clean_eval"] = False
    finalized.loc[extra["SOURCE_ONLINE_DISABLED"].to_numpy(), "eligible_for_online_quote"] = False
    return finalized


def _guazi(path: Path, freshness_cutoff: pd.Timestamp) -> pd.DataFrame:
    columns = [
        "source_name",
        "listing_id",
        "canonical_brand",
        "canonical_series",
        "trim_name",
        "trim_normalized",
        "display_name",
        "model_year",
        "city",
        "listing_price_yuan",
        "mileage_wan_km",
        "register_month",
        "transfer_count",
        "color",
        "condition_grade",
        "snapshot_date",
        "allowed_for_historical_backtest",
        "allowed_for_online_current_quote",
    ]
    frame = pd.read_parquet(path, columns=columns)
    out = _base_output(frame.index)
    out["source"] = "guazi"
    out["source_record_id"] = frame["listing_id"].fillna("").astype(str)
    out["source_vehicle_id"] = out["source_record_id"]
    out["model_id"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    out["source_model_id"] = pd.NA
    out["series_id"] = ""
    out["brand"] = frame["canonical_brand"].fillna("").astype(str)
    out["series"] = frame["canonical_series"].fillna("").astype(str)
    trim = frame["trim_name"].fillna("").astype(str)
    out["trim"] = trim.where(trim.ne(""), frame["display_name"].fillna("").astype(str))
    out["model_year"] = pd.to_numeric(frame["model_year"], errors="coerce").astype("Int64")
    out["registration_date"] = pd.to_datetime(frame["register_month"], errors="coerce")
    out["mileage_km"] = _numeric(frame["mileage_wan_km"], 10_000.0)
    out["city"] = frame["city"].fillna("").astype(str)
    out["transfer_count"] = pd.to_numeric(frame["transfer_count"], errors="coerce").astype("Int64")
    out["color"] = frame["color"].fillna("").astype(str)
    out["condition_grade"] = frame["condition_grade"].fillna("").astype(str)
    out["price"] = _numeric(frame["listing_price_yuan"])
    out["price_type"] = PriceType.GUAZI_LISTING.value
    out["observed_at"] = _datetime(frame["snapshot_date"])
    out["transaction_at"] = pd.NaT
    out["source_confidence"] = "EXTERNAL_LISTING"
    extra = {
        "MODEL_ID_UNMAPPED": pd.Series(True, index=frame.index),
        "SOURCE_HISTORICAL_DISABLED": ~_bool(frame["allowed_for_historical_backtest"]),
        "SOURCE_ONLINE_DISABLED": ~_bool(frame["allowed_for_online_current_quote"]),
    }
    finalized = _finalize(
        out, freshness_cutoff=freshness_cutoff, transaction=False, extra_flags=extra
    )
    finalized.loc[extra["SOURCE_HISTORICAL_DISABLED"].to_numpy(), "eligible_for_clean_eval"] = False
    finalized.loc[extra["SOURCE_ONLINE_DISABLED"].to_numpy(), "eligible_for_online_quote"] = False
    return finalized


def _source_summary(frame: pd.DataFrame) -> dict[str, Any]:
    flags = frame["data_quality_flags"].fillna("").astype(str).str.get_dummies(sep="|")
    return {
        "row_count": int(len(frame)),
        "unique_source_record_count": int(frame["source_record_id"].nunique()),
        "source_duplicate_rows_after_first": int(
            frame.duplicated(["source", "source_record_id"], keep="first").sum()
        ),
        "transaction_target_eligible_rows": int(frame["eligible_for_transaction_target"].sum()),
        "clean_eval_eligible_rows_before_query_cutoff": int(frame["eligible_for_clean_eval"].sum()),
        "online_quote_eligible_rows": int(frame["eligible_for_online_quote"].sum()),
        "strict_identity_coverage": float(frame["strict_identity_key"].ne("").mean()),
        "model_id_coverage": float(
            pd.to_numeric(frame["model_id"], errors="coerce").gt(0).fillna(False).mean()
        ),
        "fuzzy_signature_coverage": float(frame["fuzzy_vehicle_signature"].ne("").mean()),
        "quality_flag_counts": {
            column: int(flags[column].sum()) for column in flags.columns if column
        },
        "observed_at_min": (
            pd.to_datetime(frame["observed_at"], utc=True, errors="coerce").min().isoformat()
            if pd.to_datetime(frame["observed_at"], utc=True, errors="coerce").notna().any()
            else None
        ),
        "observed_at_max": (
            pd.to_datetime(frame["observed_at"], utc=True, errors="coerce").max().isoformat()
            if pd.to_datetime(frame["observed_at"], utc=True, errors="coerce").notna().any()
            else None
        ),
    }


def _assign_cross_source_clusters(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    compact_rows = pd.concat(
        [
            frame.loc[
                frame["fuzzy_vehicle_signature"].ne(""),
                ["source", "source_record_id", "fuzzy_vehicle_signature"],
            ]
            for frame in frames.values()
            if frame["price_type"].iloc[0].endswith("_LISTING")
        ],
        ignore_index=True,
    )
    if compact_rows.empty:
        return {"candidate_cluster_count": 0, "clustered_rows": 0, "effective_rows_after_weighting": 0.0}
    group_size = compact_rows.groupby("fuzzy_vehicle_signature").size()
    source_count = compact_rows.groupby("fuzzy_vehicle_signature")["source"].nunique()
    source_max = compact_rows.groupby(["fuzzy_vehicle_signature", "source"]).size().groupby(level=0).max()
    eligible_signatures = group_size.index[
        source_count.reindex(group_size.index).ge(2)
        & source_max.reindex(group_size.index).eq(1)
    ]
    cluster_map = {
        signature: stable_hash([signature], "xsrc") for signature in eligible_signatures
    }
    weight_map = {signature: 1.0 / float(group_size.loc[signature]) for signature in eligible_signatures}
    for frame in frames.values():
        signature = frame["fuzzy_vehicle_signature"]
        matched = signature.isin(cluster_map)
        frame.loc[matched, "cross_source_cluster_id"] = signature.loc[matched].map(cluster_map)
        frame.loc[matched, "dedup_weight"] = signature.loc[matched].map(weight_map).astype(float)
    clustered_rows = int(compact_rows["fuzzy_vehicle_signature"].isin(eligible_signatures).sum())
    return {
        "candidate_cluster_count": len(eligible_signatures),
        "clustered_rows": clustered_rows,
        "effective_rows_after_weighting": float(
            sum(frame["dedup_weight"].sum() for frame in frames.values())
        ),
        "policy": (
            "Cross-source cluster requires the same strict trim-preserving fuzzy signature, "
            "at least two sources, and at most one row per source. Evidence rows are retained "
            "but cluster weights sum to one."
        ),
    }


def build_multi_source_truth(root: Path, output_dir: Path, report_path: Path) -> dict[str, Any]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    report_path = report_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC")
    freshness_cutoff = now - pd.Timedelta(days=FRESH_LISTING_DAYS)

    builders: list[tuple[str, Callable[[], pd.DataFrame]]] = [
        (
            PriceType.INTERNAL_B2C_TRANSACTION.value,
            lambda: _internal(
                root / "data/v194/daily_confirmed_b2c_sold_actuals.parquet",
                PriceType.INTERNAL_B2C_TRANSACTION,
                freshness_cutoff,
            ),
        ),
        (
            PriceType.INTERNAL_C2B_TRANSACTION.value,
            lambda: _internal(
                root / "data/v194/daily_confirmed_c2b_actuals.parquet",
                PriceType.INTERNAL_C2B_TRANSACTION,
                freshness_cutoff,
            ),
        ),
        (
            PriceType.DONGCHEDI_LISTING.value,
            lambda: _dongchedi(
                root / "data/external/dongchedi_current_usedcar_market.parquet",
                freshness_cutoff,
            ),
        ),
        (
            PriceType.AUTOHOME_LISTING.value,
            lambda: _autohome(
                root / "data/external/autohome_current_usedcar_market.parquet",
                freshness_cutoff,
            ),
        ),
        (
            PriceType.GUAZI_LISTING.value,
            lambda: _guazi(
                root / "data/knowledge/v54_guazi_used_market_listing_snapshot.parquet",
                freshness_cutoff,
            ),
        ),
    ]
    frames: dict[str, pd.DataFrame] = {}
    source_report: dict[str, Any] = {}
    for price_type, builder in builders:
        frame = builder()
        frame = frame.drop_duplicates(["source", "source_record_id"], keep="last").reset_index(drop=True)
        frames[price_type] = frame
        source_report[price_type] = _source_summary(frame)

    cross_source = _assign_cross_source_clusters(frames)
    files: dict[str, str] = {}
    for price_type, frame in frames.items():
        partition = output_dir / f"price_type={price_type}"
        partition.mkdir(parents=True, exist_ok=True)
        output = partition / "part-000.parquet"
        frame.to_parquet(output, index=False)
        files[price_type] = str(output)

    total_rows = sum(len(frame) for frame in frames.values())
    report = {
        "schema_version": "v195.multi_source_truth.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_cutoff": max(
            pd.to_datetime(frame["observed_at"], utc=True, errors="coerce").max()
            for frame in frames.values()
        ).isoformat(),
        "fresh_listing_days": FRESH_LISTING_DAYS,
        "freshness_cutoff": freshness_cutoff.isoformat(),
        "truth_columns": TRUTH_COLUMNS,
        "total_rows_after_source_dedup": int(total_rows),
        "partition_files": files,
        "source_summary": source_report,
        "cross_source_dedup": cross_source,
        "price_type_policy": {
            "transaction_targets": [
                PriceType.INTERNAL_B2C_TRANSACTION.value,
                PriceType.INTERNAL_C2B_TRANSACTION.value,
            ],
            "listing_evidence_only": [
                PriceType.DONGCHEDI_LISTING.value,
                PriceType.AUTOHOME_LISTING.value,
                PriceType.GUAZI_LISTING.value,
            ],
            "external_listing_direct_target_forbidden": True,
        },
        "identity_policy": {
            "primary": "model_id + model_year when internal model_id exists",
            "external": "strict normalized trim preserving numeric configuration tokens",
            "same_series_year_primary_anchor_forbidden": True,
            "other_unknown_exact_match_forbidden": True,
        },
        "acceptance": {
            "all_price_types_materialized": set(files)
            == {
                PriceType.INTERNAL_B2C_TRANSACTION.value,
                PriceType.INTERNAL_C2B_TRANSACTION.value,
                PriceType.DONGCHEDI_LISTING.value,
                PriceType.AUTOHOME_LISTING.value,
                PriceType.GUAZI_LISTING.value,
            },
            "external_transaction_target_rows": int(
                sum(
                    frame["eligible_for_transaction_target"].sum()
                    for price_type, frame in frames.items()
                    if price_type.endswith("_LISTING")
                )
            ),
            "status": "PASS",
        },
    }
    if report["acceptance"]["external_transaction_target_rows"] != 0:
        report["acceptance"]["status"] = "FAIL"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
