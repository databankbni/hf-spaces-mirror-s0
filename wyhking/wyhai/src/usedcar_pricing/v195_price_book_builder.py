"""Build and evaluate the v195 multi-level production price book."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v195_b2c_anchor_repair import (
    AnchorRepairPolicy,
    apply_anchor_repair,
    mape,
    wmape,
)
from .v195_external_market_anchor import (
    calibrated_external_proxy,
    fit_external_market_calibration,
)
from .v195_price_book_schema import (
    compact,
    condition_bucket,
    mileage_bucket_km,
    normalize_color,
    registration_quarter,
    stable_hash,
    transfer_bucket,
)


LEVEL_KEYS: dict[int, list[str]] = {
    0: [
        "model_id_key",
        "model_year_key",
        "registration_quarter_key",
        "mileage_bucket_key",
        "city_key",
        "transfer_bucket_key",
        "color_bucket_key",
        "condition_bucket_key",
    ],
    1: [
        "model_id_key",
        "model_year_key",
        "registration_year_key",
        "mileage_bucket_key",
        "transfer_bucket_key",
        "condition_bucket_key",
    ],
    2: [
        "model_id_key",
        "model_year_key",
        "registration_year_key",
        "condition_bucket_key",
    ],
    3: ["model_id_key", "model_year_key", "condition_bucket_key"],
    4: ["model_id_key", "model_year_key"],
    5: ["model_id_key"],
}


def exclude_high_confidence_clearance_sales(
    b2c_truth: pd.DataFrame,
    c2b_truth: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove only strongly corroborated clearance sales from normal B2C anchors."""

    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("Asia/Shanghai").tz_convert("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    start = cutoff - pd.Timedelta(days=180)

    def latest_legal(frame: pd.DataFrame, side: str) -> pd.DataFrame:
        out = frame.copy()
        out["transaction_at"] = pd.to_datetime(
            out.get("transaction_at"), errors="coerce", utc=True
        )
        out["observed_at"] = pd.to_datetime(
            out.get("observed_at"), errors="coerce", utc=True
        )
        out["price"] = pd.to_numeric(out.get("price"), errors="coerce")
        out["model_id_numeric"] = pd.to_numeric(
            _coalesce(out, ["model_id", "model_id_int"]), errors="coerce"
        )
        out["model_year_numeric"] = pd.to_numeric(
            _coalesce(out, ["model_year", "model_year_store", "model_year_int"]),
            errors="coerce",
        )
        eligible = out.get(
            "eligible_for_transaction_target", pd.Series(False, index=out.index)
        ).fillna(False).astype(bool)
        vehicle_ids = out.get(
            "source_vehicle_id", pd.Series(index=out.index, dtype=object)
        )
        out = out.loc[
            eligible
            & out["price"].between(3_000, 1_000_000)
            & out["transaction_at"].ge(start)
            & out["transaction_at"].lt(cutoff)
            & out["observed_at"].lt(cutoff)
            & vehicle_ids.notna()
        ].copy()
        out = out.sort_values("transaction_at", kind="stable").drop_duplicates(
            "source_vehicle_id", keep="last"
        )
        return out.rename(columns={"price": f"{side}_price"})

    b2c_latest = latest_legal(b2c_truth, "b2c")
    c2b_latest = latest_legal(c2b_truth, "c2b")
    if b2c_latest.empty or c2b_latest.empty:
        return b2c_truth.copy(), pd.DataFrame()

    contracts = c2b_latest[
        ["source_vehicle_id", "c2b_price", "model_id_numeric", "model_year_numeric"]
    ].rename(
        columns={
            "model_id_numeric": "c2b_model_id_numeric",
            "model_year_numeric": "c2b_model_year_numeric",
        }
    )
    audit = b2c_latest.merge(
        contracts,
        on="source_vehicle_id",
        how="left",
        validate="one_to_one",
    )
    audit["sale_to_contract_ratio"] = audit["b2c_price"].div(audit["c2b_price"])
    audit["strict_same_model_pair"] = (
        audit["model_id_numeric"].eq(audit["c2b_model_id_numeric"])
        & audit["model_year_numeric"].eq(audit["c2b_model_year_numeric"])
    )
    normal_support = audit.loc[
        audit["c2b_price"].isna() | audit["b2c_price"].gt(audit["c2b_price"])
    ]
    support = (
        normal_support.groupby(
            ["model_id_numeric", "model_year_numeric"], dropna=False
        )["b2c_price"]
        .agg(
            supported_count="count",
            supported_q20=lambda values: values.quantile(0.20),
        )
        .reset_index()
    )
    audit = audit.merge(
        support,
        on=["model_id_numeric", "model_year_numeric"],
        how="left",
    )
    extreme_loss = audit["strict_same_model_pair"] & audit[
        "sale_to_contract_ratio"
    ].le(0.82)
    corroborated_disposal = (
        audit["strict_same_model_pair"]
        & audit["sale_to_contract_ratio"].le(0.93)
        & audit["supported_count"].fillna(0).ge(3)
        & audit["b2c_price"].lt(audit["supported_q20"] * 0.88)
    )
    audit["high_confidence_clearance"] = (extreme_loss | corroborated_disposal).fillna(
        False
    )
    audit["clearance_reason"] = np.select(
        [extreme_loss, corroborated_disposal],
        ["EXTREME_LOSS_VS_OWN_CONTRACT", "CONTRACT_AND_RECENT_MARKET_CORROBORATED"],
        default="",
    )

    clearance_ids = set(
        audit.loc[audit["high_confidence_clearance"], "source_vehicle_id"].astype(str)
    )
    filtered = b2c_truth.copy()
    source_ids = filtered.get(
        "source_vehicle_id", pd.Series("", index=filtered.index)
    ).astype(str)
    clearance_mask = source_ids.isin(clearance_ids)
    if clearance_mask.any():
        filtered.loc[clearance_mask, "eligible_for_transaction_target"] = False
        if "eligible_for_clean_eval" in filtered:
            filtered.loc[clearance_mask, "eligible_for_clean_eval"] = False
        flags = filtered.get("quality_flags", pd.Series("", index=filtered.index))
        flags = flags.fillna("").astype(str)
        filtered.loc[clearance_mask, "quality_flags"] = flags.loc[clearance_mask].map(
            lambda value: ";".join(
                item
                for item in (value, "HIGH_CONFIDENCE_CLEARANCE_NOT_NORMAL_MARKET")
                if item
            )
        )
    return filtered, audit.loc[audit["high_confidence_clearance"]].reset_index(drop=True)


def _coalesce(frame: pd.DataFrame, columns: list[str], default: Any = "") -> pd.Series:
    output = pd.Series(default, index=frame.index)
    for column in columns:
        if column not in frame:
            continue
        values = frame[column]
        valid = values.notna() & values.astype(str).ne("")
        output = output.where(~valid, values)
    return output


def _add_keys(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    model_id = pd.to_numeric(_coalesce(out, ["model_id", "model_id_int"]), errors="coerce")
    model_year = pd.to_numeric(
        _coalesce(out, ["model_year", "model_year_store", "model_year_int"]), errors="coerce"
    )
    registration = pd.to_datetime(
        _coalesce(out, ["registration_date", "first_registration_date"]), errors="coerce"
    )
    mileage_km = pd.to_numeric(
        _coalesce(out, ["mileage_km"], np.nan), errors="coerce"
    )
    if mileage_km.isna().all():
        mileage_km = pd.to_numeric(
            _coalesce(out, ["mileage_wan_km", "mileage_wan_km_store"], np.nan),
            errors="coerce",
        ) * 10_000.0
    city = _coalesce(out, ["city", "city_store"])
    transfer = _coalesce(out, ["transfer_count", "transfer_count_store"], np.nan)
    color = _coalesce(out, ["color_raw", "color", "color_store"])
    condition = _coalesce(
        out,
        [
            "inspection_grade",
            "inspection_grade_norm",
            "condition_grade",
            "condition",
            "condition_risk_level_strict",
        ],
    )
    out["model_id_key"] = model_id.fillna(0).astype(int).astype(str)
    out["model_year_key"] = model_year.fillna(0).astype(int).astype(str)
    out["registration_quarter_key"] = registration.map(registration_quarter)
    out["registration_year_key"] = registration.dt.year.fillna(0).astype(int).astype(str)
    out["mileage_bucket_key"] = mileage_km.map(lambda value: mileage_bucket_km(value, 10_000))
    out["city_key"] = city.map(compact).replace("", "UNKNOWN")
    out["transfer_bucket_key"] = transfer.map(transfer_bucket)
    out["color_bucket_key"] = color.map(normalize_color)
    out["condition_bucket_key"] = condition.map(condition_bucket)
    out["model_id_numeric"] = model_id.astype("Int64")
    out["model_year_numeric"] = model_year.astype("Int64")
    out["registration_date_normalized"] = registration
    out["mileage_km_normalized"] = mileage_km
    return out


def _canonical_key(frame: pd.DataFrame, level: int) -> pd.Series:
    keys = LEVEL_KEYS[level]
    if frame.empty:
        return pd.Series(index=frame.index, dtype="object", name="canonical_key")
    raw = frame[keys].fillna("UNKNOWN").astype(str).agg("|".join, axis=1)
    return raw.map(lambda value: stable_hash([level, value], "book"))


def _aggregate_window(
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    days: int,
    level: int,
) -> pd.DataFrame:
    start = cutoff - pd.Timedelta(days=days)
    subset = frame.loc[
        frame["transaction_at"].lt(cutoff) & frame["transaction_at"].ge(start)
    ].copy()
    if subset.empty:
        return pd.DataFrame()
    subset["canonical_key"] = _canonical_key(subset, level)
    grouped = subset.groupby("canonical_key", sort=False)
    base = grouped["price"].agg(["count", "median"]).rename(
        columns={"count": f"count_{days}", "median": f"point_{days}"}
    )
    base[f"low_{days}"] = grouped["price"].quantile(0.25)
    base[f"high_{days}"] = grouped["price"].quantile(0.75)
    base[f"latest_at_{days}"] = grouped["transaction_at"].max()
    return base.reset_index()


def _build_side(
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    side: str,
) -> pd.DataFrame:
    prepared = _add_keys(frame)
    prepared["transaction_at"] = pd.to_datetime(
        prepared["transaction_at"], errors="coerce", utc=True
    )
    prepared["observed_at"] = pd.to_datetime(
        prepared.get("observed_at"), errors="coerce", utc=True
    )
    prepared["price"] = pd.to_numeric(prepared["price"], errors="coerce")
    prepared = prepared.loc[
        prepared["eligible_for_transaction_target"].fillna(False).astype(bool)
        & prepared["price"].between(3_000, 1_000_000)
        & prepared["model_id_numeric"].fillna(0).gt(0)
        & prepared["transaction_at"].lt(cutoff)
        & prepared["observed_at"].lt(cutoff)
        & prepared["transaction_at"].ge(cutoff - pd.Timedelta(days=180))
    ].copy()
    outputs: list[pd.DataFrame] = []
    for level in LEVEL_KEYS:
        prepared["canonical_key"] = _canonical_key(prepared, level)
        metadata_columns = [
            "canonical_key",
            "model_id_numeric",
            "model_year_numeric",
            *LEVEL_KEYS[level],
        ]
        metadata = prepared[metadata_columns].drop_duplicates("canonical_key", keep="last")
        windows = [
            _aggregate_window(prepared, cutoff=cutoff, days=days, level=level)
            for days in (30, 90, 180)
        ]
        windows = [window for window in windows if not window.empty]
        if not windows:
            continue
        aggregated = windows[0]
        for window in windows[1:]:
            aggregated = aggregated.merge(window, on="canonical_key", how="outer")
        aggregated = metadata.merge(aggregated, on="canonical_key", how="inner")
        count30 = pd.to_numeric(aggregated.get("count_30", 0), errors="coerce").fillna(0)
        count90 = pd.to_numeric(aggregated.get("count_90", 0), errors="coerce").fillna(0)
        count180 = pd.to_numeric(aggregated.get("count_180", 0), errors="coerce").fillna(0)
        use30 = count30.ge(2)
        use90 = ~use30 & count90.ge(3)
        selected_window = np.select([use30, use90], [30, 90], default=180)
        aggregated["selected_window_days"] = selected_window
        for target, prefix in (
            ("price_point", "point"),
            ("price_low", "low"),
            ("price_high", "high"),
            ("sample_count", "count"),
        ):
            aggregated[target] = np.select(
                [use30, use90],
                [
                    pd.to_numeric(aggregated.get(f"{prefix}_30"), errors="coerce"),
                    pd.to_numeric(aggregated.get(f"{prefix}_90"), errors="coerce"),
                ],
                default=pd.to_numeric(aggregated.get(f"{prefix}_180"), errors="coerce"),
            )
        latest = pd.to_datetime(aggregated.get("latest_at_180"), errors="coerce", utc=True)
        aggregated["recency_days"] = (cutoff - latest).dt.total_seconds() / 86_400.0
        aggregated["confidence"] = np.select(
            [
                count30.ge(5) | count90.ge(8),
                count30.ge(2) | count90.ge(3) | count180.ge(5),
            ],
            ["HIGH", "MEDIUM"],
            default="LOW",
        )
        aggregated["key_level"] = level
        aggregated["side"] = side
        aggregated["key_components"] = aggregated[LEVEL_KEYS[level]].astype(str).apply(
            lambda row: json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True), axis=1
        )
        outputs.append(
            aggregated[
                [
                    "key_level",
                    "canonical_key",
                    "key_components",
                    "model_id_numeric",
                    "model_year_numeric",
                    "side",
                    "price_point",
                    "price_low",
                    "price_high",
                    "sample_count",
                    "selected_window_days",
                    "recency_days",
                    "confidence",
                ]
            ]
        )
    return pd.concat(outputs, ignore_index=True, sort=False) if outputs else pd.DataFrame()


def _external_counts(root: Path) -> pd.DataFrame:
    path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
    columns = [
        "model_id",
        "model_year",
        "dongchedi_count",
        "autohome_count",
        "guazi_count",
        "total_listing_count",
    ]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame["model_id_numeric"] = pd.to_numeric(frame["model_id"], errors="coerce").astype("Int64")
    frame["model_year_numeric"] = pd.to_numeric(frame["model_year"], errors="coerce").astype("Int64")
    counts = frame.groupby(["model_id_numeric", "model_year_numeric"], dropna=False)[
        ["dongchedi_count", "autohome_count", "guazi_count", "total_listing_count"]
    ].median().reset_index()
    return counts.rename(
        columns={
            "dongchedi_count": "dcd_external_count",
            "autohome_count": "autohome_count",
            "guazi_count": "guazi_count",
            "total_listing_count": "external_listing_count",
        }
    )


def build_price_book(
    b2c_truth: pd.DataFrame,
    c2b_truth: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    external_counts: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("Asia/Shanghai").tz_convert("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    filtered_b2c_truth, clearance_audit = exclude_high_confidence_clearance_sales(
        b2c_truth,
        c2b_truth,
        cutoff=cutoff,
    )
    b2c = _build_side(filtered_b2c_truth, cutoff=cutoff, side="b2c")
    c2b = _build_side(c2b_truth, cutoff=cutoff, side="c2b")
    metadata = pd.concat(
        [
            b2c[[
                "key_level",
                "canonical_key",
                "key_components",
                "model_id_numeric",
                "model_year_numeric",
            ]],
            c2b[[
                "key_level",
                "canonical_key",
                "key_components",
                "model_id_numeric",
                "model_year_numeric",
            ]],
        ],
        ignore_index=True,
    ).drop_duplicates(["key_level", "canonical_key"], keep="first")

    def side_columns(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        return frame.rename(
            columns={
                "price_point": f"{prefix}_point",
                "price_low": f"{prefix}_low",
                "price_high": f"{prefix}_high",
                "sample_count": f"{prefix}_count",
                "selected_window_days": f"{prefix}_window_days",
                "recency_days": f"{prefix}_recency_days",
                "confidence": f"{prefix}_confidence",
            }
        )[[
            "key_level",
            "canonical_key",
            f"{prefix}_point",
            f"{prefix}_low",
            f"{prefix}_high",
            f"{prefix}_count",
            f"{prefix}_window_days",
            f"{prefix}_recency_days",
            f"{prefix}_confidence",
        ]]

    book = metadata.merge(
        side_columns(b2c, "b2c"), on=["key_level", "canonical_key"], how="left"
    ).merge(side_columns(c2b, "c2b"), on=["key_level", "canonical_key"], how="left")
    if external_counts is not None and not external_counts.empty:
        book = book.merge(
            external_counts,
            on=["model_id_numeric", "model_year_numeric"],
            how="left",
        )
    for column in (
        "dcd_external_count",
        "autohome_count",
        "guazi_count",
        "external_listing_count",
    ):
        if column not in book:
            book[column] = 0.0
        book[column] = pd.to_numeric(book[column], errors="coerce").fillna(0.0)
    book["knowledge_cell_id"] = book["canonical_key"]
    book["sample_count"] = book[["b2c_count", "c2b_count"]].fillna(0).sum(axis=1)
    book["internal_b2c_count"] = book["b2c_count"].fillna(0).astype(int)
    book["internal_c2b_count"] = book["c2b_count"].fillna(0).astype(int)
    book["source_mix"] = book.apply(
        lambda row: json.dumps(
            {
                "internal_b2c": int(row["internal_b2c_count"]),
                "internal_c2b": int(row["internal_c2b_count"]),
                "dongchedi_listing": int(row["dcd_external_count"]),
                "autohome_listing": int(row["autohome_count"]),
                "guazi_listing": int(row["guazi_count"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        axis=1,
    )
    book["expected_b2c_transaction_price"] = book["b2c_point"]
    book["b2c_transaction_low"] = book["b2c_low"]
    book["b2c_transaction_high"] = book["b2c_high"]
    book["expected_final_acquisition_price"] = book["c2b_point"]
    book["final_acquisition_low"] = book["c2b_low"]
    book["final_acquisition_high"] = book["c2b_high"]
    book["suggested_listing_price"] = np.nan
    book["listing_price_low"] = np.nan
    book["listing_price_high"] = np.nan
    book["max_c2b_acquisition_price"] = np.nan
    book["suggested_first_offer"] = np.nan
    book["suggested_acquisition_price"] = np.nan
    book["price_ladder_status"] = "NOT_GENERATED_STAGE3"
    book["manual_override_flag"] = False
    book["quote_eligible"] = False
    book["reference_evidence_only"] = True
    book["override_type"] = ""
    book["override_reason"] = ""
    book["price_source"] = "RECENT_INTERNAL_REFERENCE_EVIDENCE"
    book["owner"] = "SYSTEM_V195"
    book["reason"] = (
        "Hierarchical internal reference evidence only; never quote this raw median directly. "
        "same_series_year is not a main anchor."
    )
    book["effective_date"] = cutoff.isoformat()
    book["expire_date"] = (cutoff + pd.Timedelta(days=7)).isoformat()
    book["version"] = f"v195_price_book_{cutoff.strftime('%Y%m%d')}"
    book["data_cutoff"] = cutoff.isoformat()
    book = book.sort_values(["key_level", "canonical_key"], kind="stable").reset_index(
        drop=True
    )
    book.attrs["high_confidence_clearance_count"] = int(len(clearance_audit))
    book.attrs["high_confidence_clearance_audit"] = clearance_audit
    return book


def lookup_price_book(frame: pd.DataFrame, book: pd.DataFrame, side: str) -> pd.DataFrame:
    prepared = _add_keys(frame)
    result = pd.DataFrame(index=frame.index)
    result["price_book_anchor_yuan"] = np.nan
    result["price_book_low_yuan"] = np.nan
    result["price_book_high_yuan"] = np.nan
    result["price_book_sample_count"] = 0
    result["price_book_hit_level"] = -1
    result["price_book_confidence"] = "MISSING"
    for level in LEVEL_KEYS:
        pending = result["price_book_hit_level"].lt(0)
        if not pending.any():
            break
        keys = _canonical_key(prepared.loc[pending], level)
        level_book = book.loc[
            book["key_level"].eq(level) & book[f"{side}_point"].notna()
        ].set_index("canonical_key")
        matched = keys.isin(level_book.index)
        if not matched.any():
            continue
        query_indices = keys.index[matched]
        rows = level_book.loc[keys.loc[matched].to_numpy()]
        result.loc[query_indices, "price_book_anchor_yuan"] = rows[f"{side}_point"].to_numpy()
        result.loc[query_indices, "price_book_low_yuan"] = rows[f"{side}_low"].to_numpy()
        result.loc[query_indices, "price_book_high_yuan"] = rows[f"{side}_high"].to_numpy()
        result.loc[query_indices, "price_book_sample_count"] = rows[f"{side}_count"].to_numpy()
        result.loc[query_indices, "price_book_hit_level"] = level
        result.loc[query_indices, "price_book_confidence"] = rows[
            f"{side}_confidence"
        ].to_numpy()
    return result


def _apply_blend(
    frame: pd.DataFrame,
    lookup: pd.DataFrame,
    policy: dict[str, Any],
    *,
    base_column: str,
) -> tuple[np.ndarray, np.ndarray]:
    base = pd.to_numeric(frame[base_column], errors="coerce").to_numpy(dtype=float)
    anchor = pd.to_numeric(lookup["price_book_anchor_yuan"], errors="coerce").to_numpy(dtype=float)
    count = pd.to_numeric(lookup["price_book_sample_count"], errors="coerce").fillna(0).to_numpy()
    level = pd.to_numeric(lookup["price_book_hit_level"], errors="coerce").fillna(99).to_numpy()
    eligible = (
        np.isfinite(anchor)
        & (count >= int(policy["min_count"]))
        & (level <= int(policy["max_level"]))
    )
    delta = np.clip(
        anchor - base,
        -float(policy["cap_ratio"]) * base,
        float(policy["cap_ratio"]) * base,
    )
    predicted = np.where(eligible, base + float(policy["alpha"]) * delta, base)
    return predicted, eligible


def _select_blend(
    frame: pd.DataFrame,
    lookup: pd.DataFrame,
    *,
    base_column: str,
) -> tuple[dict[str, Any], pd.DataFrame]:
    base_score = mape(frame["actual_yuan"], frame[base_column])
    rows: list[dict[str, Any]] = [
        {
            "max_level": -1,
            "min_count": 999,
            "alpha": 0.0,
            "cap_ratio": 0.0,
            "selection_mape": base_score,
            "coverage": 0.0,
        }
    ]
    for max_level in range(0, 6):
        for min_count in (1, 2, 3, 5, 8, 12):
            for alpha in (0.15, 0.25, 0.35, 0.50, 0.65, 0.80, 1.00):
                for cap in (0.03, 0.05, 0.08, 0.12, 0.16, 0.20, 0.30):
                    trial = {
                        "max_level": max_level,
                        "min_count": min_count,
                        "alpha": alpha,
                        "cap_ratio": cap,
                    }
                    predicted, eligible = _apply_blend(
                        frame, lookup, trial, base_column=base_column
                    )
                    rows.append(
                        {
                            **trial,
                            "selection_mape": mape(frame["actual_yuan"], predicted),
                            "coverage": float(eligible.mean()),
                        }
                    )
    selection = pd.DataFrame(rows).sort_values(
        ["selection_mape", "coverage", "max_level", "min_count"],
        ascending=[True, False, True, False],
        kind="stable",
    )
    challenger = selection.iloc[0].to_dict()
    challenger_pred, _ = _apply_blend(
        frame, lookup, challenger, base_column=base_column
    )
    daily = pd.DataFrame(
        {
            "day": pd.to_datetime(frame["day"], errors="coerce").dt.normalize(),
            "actual": pd.to_numeric(frame["actual_yuan"], errors="coerce"),
            "base": pd.to_numeric(frame[base_column], errors="coerce"),
            "challenger": challenger_pred,
        }
    )
    daily["base_ape"] = (daily["base"] - daily["actual"]).abs() / daily["actual"]
    daily["challenger_ape"] = (
        daily["challenger"] - daily["actual"]
    ).abs() / daily["actual"]
    daily_metrics = daily.groupby("day")[["base_ape", "challenger_ape"]].mean()
    daily_win_rate = float(
        daily_metrics["challenger_ape"].lt(daily_metrics["base_ape"]).mean()
    )
    improvement = base_score - float(challenger["selection_mape"])
    promote = bool(improvement >= 0.0005 and daily_win_rate >= 0.60)
    challenger["selection_improvement"] = improvement
    challenger["daily_win_rate"] = daily_win_rate
    challenger["promote"] = promote
    if promote:
        policy = challenger
    else:
        policy = {
            "max_level": -1,
            "min_count": 999,
            "alpha": 0.0,
            "cap_ratio": 0.0,
            "selection_mape": base_score,
            "coverage": 0.0,
            "promote": False,
            "promotion_rejected_reason": (
                "Requires at least 0.05 percentage-point selection MAPE improvement "
                "and at least 60% daily win rate."
            ),
            "challenger": challenger,
        }
    return policy, selection


def _metric(frame: pd.DataFrame, before: np.ndarray, after: np.ndarray, used: np.ndarray) -> dict[str, Any]:
    actual = frame["actual_yuan"]
    before_ape = np.abs(before - actual.to_numpy(dtype=float)) / actual.to_numpy(dtype=float)
    after_ape = np.abs(after - actual.to_numpy(dtype=float)) / actual.to_numpy(dtype=float)
    return {
        "n": int(len(frame)),
        "before_mape": mape(actual, before),
        "after_mape": mape(actual, after),
        "before_wmape": wmape(actual, before),
        "after_wmape": wmape(actual, after),
        "before_p50_ape": float(np.quantile(before_ape, 0.50)),
        "after_p50_ape": float(np.quantile(after_ape, 0.50)),
        "before_p90_ape": float(np.quantile(before_ape, 0.90)),
        "after_p90_ape": float(np.quantile(after_ape, 0.90)),
        "price_book_hit_count": int(used.sum()),
        "price_book_hit_rate": float(used.mean()),
    }


def _load_truth(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = root / "data/v195/multi_source_truth"
    b2c = pd.read_parquet(base / "price_type=INTERNAL_B2C_TRANSACTION/part-000.parquet")
    c2b = pd.read_parquet(base / "price_type=INTERNAL_C2B_TRANSACTION/part-000.parquet")
    return b2c, c2b


def build_and_evaluate_price_book(
    root: Path,
    output_book: Path,
    output_dir: Path,
) -> dict[str, Any]:
    b2c_truth, c2b_truth = _load_truth(root)
    external = _external_counts(root)
    selection_cutoff = pd.Timestamp("2026-06-26", tz="Asia/Shanghai")
    test_cutoff = pd.Timestamp("2026-07-03", tz="Asia/Shanghai")
    latest_confirmed = max(
        pd.to_datetime(b2c_truth["transaction_at"], errors="coerce", utc=True).max(),
        pd.to_datetime(c2b_truth["transaction_at"], errors="coerce", utc=True).max(),
    )
    current_cutoff = (
        latest_confirmed.tz_convert("Asia/Shanghai").normalize() + pd.Timedelta(days=1)
    )
    selection_book = build_price_book(
        b2c_truth, c2b_truth, cutoff=selection_cutoff, external_counts=external
    )
    test_book = build_price_book(
        b2c_truth, c2b_truth, cutoff=test_cutoff, external_counts=external
    )
    current_book = build_price_book(
        b2c_truth, c2b_truth, cutoff=current_cutoff, external_counts=external
    )

    b2c = pd.read_csv(
        root / "results/traces/v194_355_b2c_30d_champion_trace.csv", low_memory=False
    )
    b2c["day"] = pd.to_datetime(b2c["day"], errors="coerce").dt.normalize()
    b2c_train = b2c.loc[b2c["day"] < pd.Timestamp("2026-06-26")].copy()
    b2c_selection = b2c.loc[
        (b2c["day"] >= pd.Timestamp("2026-06-26"))
        & (b2c["day"] < pd.Timestamp("2026-07-03"))
    ].copy()
    b2c_test = b2c.loc[b2c["day"] >= pd.Timestamp("2026-07-03")].copy()
    policy_payload = json.loads(
        (root / "models/v195/v195_b2c_anchor_repair.policy.json").read_text(encoding="utf-8")
    )
    anchor_policy = AnchorRepairPolicy(**policy_payload)
    selection_calibration = fit_external_market_calibration(
        b2c_train, base_column="champion_pred_yuan", actual_column="actual_yuan"
    )
    selection_proxy = calibrated_external_proxy(
        b2c_selection, selection_calibration, base_column="champion_pred_yuan"
    )
    b2c_selection["v195_anchor_repaired_yuan"], _, _ = apply_anchor_repair(
        b2c_selection,
        selection_proxy,
        anchor_policy,
        base_column="champion_pred_yuan",
    )
    pretest = pd.concat([b2c_train, b2c_selection], ignore_index=True, sort=False)
    final_calibration = fit_external_market_calibration(
        pretest, base_column="champion_pred_yuan", actual_column="actual_yuan"
    )
    test_proxy = calibrated_external_proxy(
        b2c_test, final_calibration, base_column="champion_pred_yuan"
    )
    b2c_test["v195_anchor_repaired_yuan"], _, _ = apply_anchor_repair(
        b2c_test, test_proxy, anchor_policy, base_column="champion_pred_yuan"
    )

    c2b_selection = pd.read_csv(
        root / "results/features/v194_367_c2b_strict_trim_oof_replay.csv", low_memory=False
    )
    c2b_selection["day"] = pd.to_datetime(c2b_selection["day"], errors="coerce").dt.normalize()
    c2b_selection = c2b_selection.loc[c2b_selection["day"] < pd.Timestamp("2026-07-03")].copy()
    c2b_selection["v195_c2b_base_yuan"] = c2b_selection["strict_trim_c2b_pred_yuan"]
    c2b_test = pd.read_csv(
        root / "results/traces/v194_369_c2b_90d_listing_discount_trace.csv", low_memory=False
    )
    c2b_test["day"] = pd.to_datetime(c2b_test["day"], errors="coerce").dt.normalize()
    c2b_test["v195_c2b_base_yuan"] = c2b_test["listing_discount_c2b_pred_yuan"]

    b2c_selection_lookup = lookup_price_book(b2c_selection, selection_book, "b2c")
    b2c_test_lookup = lookup_price_book(b2c_test, test_book, "b2c")
    c2b_selection_lookup = lookup_price_book(c2b_selection, selection_book, "c2b")
    c2b_test_lookup = lookup_price_book(c2b_test, test_book, "c2b")
    b2c_policy, b2c_grid = _select_blend(
        b2c_selection,
        b2c_selection_lookup,
        base_column="v195_anchor_repaired_yuan",
    )
    c2b_policy, c2b_grid = _select_blend(
        c2b_selection,
        c2b_selection_lookup,
        base_column="v195_c2b_base_yuan",
    )
    b2c_after, b2c_used = _apply_blend(
        b2c_test, b2c_test_lookup, b2c_policy, base_column="v195_anchor_repaired_yuan"
    )
    c2b_after, c2b_used = _apply_blend(
        c2b_test, c2b_test_lookup, c2b_policy, base_column="v195_c2b_base_yuan"
    )
    b2c_before = b2c_test["v195_anchor_repaired_yuan"].to_numpy(dtype=float)
    c2b_before = c2b_test["v195_c2b_base_yuan"].to_numpy(dtype=float)
    b2c_metrics = _metric(b2c_test, b2c_before, b2c_after, b2c_used)
    c2b_metrics = _metric(c2b_test, c2b_before, c2b_after, c2b_used)

    output_book.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    current_book.to_parquet(output_book, index=False)
    snapshot_path = (
        output_book.parent
        / "snapshots"
        / f"daily_vehicle_price_knowledge_snapshot_{current_cutoff.strftime('%Y%m%d')}.parquet"
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    current_book.to_parquet(snapshot_path, index=False)
    b2c_grid.to_csv(output_dir / "b2c_price_book_policy_selection.csv", index=False)
    c2b_grid.to_csv(output_dir / "c2b_price_book_policy_selection.csv", index=False)
    b2c_trace = b2c_test.copy()
    b2c_trace = pd.concat([b2c_trace.reset_index(drop=True), b2c_test_lookup.reset_index(drop=True)], axis=1)
    b2c_trace["v195_price_book_b2c_pred_yuan"] = b2c_after
    b2c_trace["v195_price_book_used"] = b2c_used
    b2c_trace.to_csv(output_dir / "v195_price_book_b2c_test_trace.csv", index=False, encoding="utf-8-sig")
    c2b_trace = c2b_test.copy()
    c2b_trace = pd.concat([c2b_trace.reset_index(drop=True), c2b_test_lookup.reset_index(drop=True)], axis=1)
    c2b_trace["v195_price_book_c2b_pred_yuan"] = c2b_after
    c2b_trace["v195_price_book_used"] = c2b_used
    c2b_trace.to_csv(output_dir / "v195_price_book_c2b_test_trace.csv", index=False, encoding="utf-8-sig")

    report = {
        "schema_version": "v195.production_price_book.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_data_cutoff": current_cutoff.isoformat(),
        "history_max_days": 180,
        "same_series_year_primary_anchor_rows": 0,
        "price_book_rows": int(len(current_book)),
        "hierarchical_reference_rows": int(len(current_book)),
        "exact_level0_reference_rows": int(current_book["key_level"].eq(0).sum()),
        "independent_seven_element_quote_rows": 0,
        "raw_internal_median_is_direct_quote": False,
        "rows_by_level": {
            str(key): int(value)
            for key, value in current_book["key_level"].value_counts().sort_index().items()
        },
        "internal_b2c_cells": int(current_book["b2c_point"].notna().sum()),
        "internal_c2b_cells": int(current_book["c2b_point"].notna().sum()),
        "b2c_policy": b2c_policy,
        "c2b_policy": c2b_policy,
        "test_window": ["2026-07-03", "2026-07-09"],
        "b2c_test_metrics": b2c_metrics,
        "c2b_test_metrics": c2b_metrics,
        "manual_override_count": 0,
        "price_ladder_status": "PENDING_STAGE4",
        "output_book": str(output_book),
        "daily_vehicle_price_knowledge_snapshot": str(snapshot_path),
        "acceptance": {
            "same_series_year_not_primary": True,
            "max_history_days_le_180": True,
            "selection_precedes_test": True,
            "b2c_not_worse": b2c_metrics["after_mape"] <= b2c_metrics["before_mape"],
            "c2b_not_worse": c2b_metrics["after_mape"] <= c2b_metrics["before_mape"],
        },
    }
    report["acceptance"]["status"] = (
        "PASS" if all(report["acceptance"].values()) else "FAIL"
    )
    (output_dir / "production_price_book_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
