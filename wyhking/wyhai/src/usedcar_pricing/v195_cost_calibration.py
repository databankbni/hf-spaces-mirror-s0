"""Calibrate the default total spread budget from recent matched transactions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .v195_price_ladder_solver import price_band


def _legal_latest(path: Path, role: str) -> pd.DataFrame:
    columns = [
        "vehicle_id",
        "event_time",
        "price_yuan",
        "runtime_candidate_dedup_keep_flag",
        "market_clean_flag",
        "is_token_price",
    ]
    frame = pd.read_parquet(path, columns=columns)
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce", utc=True)
    frame["price_yuan"] = pd.to_numeric(frame["price_yuan"], errors="coerce")
    legal = (
        frame["runtime_candidate_dedup_keep_flag"].fillna(False).astype(bool)
        & frame["market_clean_flag"].fillna(False).astype(bool)
        & ~frame["is_token_price"].fillna(False).astype(bool)
        & frame["price_yuan"].between(3_000, 1_000_000)
        & frame["vehicle_id"].notna()
    )
    frame = frame.loc[legal, ["vehicle_id", "event_time", "price_yuan"]].copy()
    frame = frame.sort_values("event_time", kind="stable").drop_duplicates(
        "vehicle_id", keep="last"
    )
    return frame.rename(
        columns={"event_time": f"{role}_time", "price_yuan": f"{role}_price"}
    )


def build_recent_spread_calibration(
    root: Path,
    output_path: Path,
    *,
    cutoff: pd.Timestamp | None = None,
    lookback_days: int = 90,
    quantile: float = 0.25,
) -> dict[str, Any]:
    b2c = _legal_latest(
        root / "data/v194/daily_confirmed_b2c_sold_actuals.parquet", "b2c"
    )
    c2b = _legal_latest(
        root / "data/v194/daily_confirmed_c2b_actuals.parquet", "c2b"
    )
    if cutoff is None:
        latest = max(b2c["b2c_time"].max(), c2b["c2b_time"].max())
        cutoff = latest.tz_convert("Asia/Shanghai").normalize() + pd.Timedelta(days=1)
    elif cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("Asia/Shanghai")
    else:
        cutoff = cutoff.tz_convert("Asia/Shanghai")
    cutoff_utc = cutoff.tz_convert("UTC")
    start = cutoff_utc - pd.Timedelta(days=lookback_days)
    paired = b2c.merge(c2b, on="vehicle_id", how="inner", validate="one_to_one")
    paired = paired.loc[
        (paired["b2c_time"].ge(start) | paired["c2b_time"].ge(start))
        & paired["b2c_time"].lt(cutoff_utc)
        & paired["c2b_time"].lt(cutoff_utc)
        & paired["b2c_price"].gt(paired["c2b_price"])
        & paired["b2c_price"].div(paired["c2b_price"]).lt(2.0)
    ].copy()
    paired["spread_ratio"] = (
        paired["b2c_price"] - paired["c2b_price"]
    ) / paired["b2c_price"]
    paired["spread_yuan"] = paired["b2c_price"] - paired["c2b_price"]
    paired["price_band"] = paired["b2c_price"].map(price_band)
    bands: dict[str, Any] = {}
    for band, group in paired.groupby("price_band", sort=False):
        bands[str(band)] = {
            "n": int(len(group)),
            "spread_ratio_q25": float(group["spread_ratio"].quantile(quantile)),
            "spread_ratio_median": float(group["spread_ratio"].median()),
            "spread_yuan_q25": float(group["spread_yuan"].quantile(quantile)),
            "spread_yuan_median": float(group["spread_yuan"].median()),
        }
    report = {
        "version": "v195_recent_internal_spread_budget_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_cutoff": cutoff.isoformat(),
        "lookback_days": lookback_days,
        "quantile_used_for_default_max_c2b_budget": quantile,
        "matched_vehicle_count": int(len(paired)),
        "overall_spread_ratio_q25": float(paired["spread_ratio"].quantile(quantile)),
        "overall_spread_ratio_median": float(paired["spread_ratio"].median()),
        "overall_spread_yuan_q25": float(paired["spread_yuan"].quantile(quantile)),
        "overall_spread_yuan_median": float(paired["spread_yuan"].median()),
        "price_bands": bands,
        "usage": (
            "Default total cost plus minimum-profit budget for max C2B only. "
            "Explicit user cost/profit overrides bypass this calibration."
        ),
        "target_leakage_policy": (
            "This is PRODUCTION_DAILY_KNOWLEDGE configuration through T-1; Stage-5 clean replay "
            "must rebuild it at every historical cutoff."
        ),
        "acceptance": {
            "matched_vehicle_count_sufficient": len(paired) >= 1_000,
            "all_price_bands_present": len(bands) == 6,
        },
    }
    report["acceptance"]["status"] = (
        "PASS" if all(report["acceptance"].values()) else "FAIL"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
