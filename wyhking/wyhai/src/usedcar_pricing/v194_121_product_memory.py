"""v194.121 product-memory pricing layer.

This module implements the product-mode handbook policy that performed best
in the T-30 replay:

- use all clean internal C2B knowledge available in the deployment warehouse;
- filter by quote_time/pricing_available_at when a historical quote_time is
  supplied, so blind-day replays cannot see future confirmed transactions;
- use same trim/year, same trim, same series/year, then same series neighbors;
- choose a conservative C2B weighted quantile instead of a raw latest price;
- keep the candidate cloud and policy explicit for explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import numpy as np
import pandas as pd

from .v194_price_policy import weighted_quantile


PRODUCT_MEMORY_POLICY_VERSION = "v194_142_full_knowledge_sparse_identity_fallback_neighbor_q30"


def _trim_match_key(value: Any) -> str:
    """Canonical trim key used for product-memory retrieval.

    Older warehouse builds and fresh daily ingestions sometimes differ only by
    an explicit energy marker inside the canonical key, e.g.
    ``...|ICE|1.5|...`` vs ``...|1.5|...``.  For retrieval we keep the original
    canonical key for display/audit, but use this energy-marker-tolerant key
    inside the same brand/series/year boundary so newly ingested same-trim
    evidence is not missed.
    """

    text = str(value or "").strip()
    for token in ("ICE", "BEV", "PHEV", "HEV", "EREV", "UNKNOWN"):
        text = text.replace(f"|{token}|", "|")
    while "||" in text:
        text = text.replace("||", "|")
    return text.strip("|")


@dataclass(frozen=True)
class ProductMemoryResult:
    price_yuan: float
    interval_low_yuan: float
    interval_high_yuan: float
    confidence_bucket: str
    match_level: str
    neighbor_count: int
    q20_yuan: float
    q25_yuan: float
    q30_yuan: float
    q40_yuan: float
    q50_yuan: float
    min_neighbor_price_yuan: float
    max_neighbor_price_yuan: float
    policy: str
    candidates: pd.DataFrame


class V194121ProductMemory:
    def __init__(self, warehouse: pd.DataFrame) -> None:
        self.history = self._normalize_history(warehouse)
        self.global_median = self._safe_median(self.history.get("price_yuan"))
        if not self.global_median:
            self.global_median = 50_000.0
        self.brand_medians = (
            pd.to_numeric(self.history.get("price_yuan"), errors="coerce")
            .groupby(self.history.get("brand_key"))
            .median()
            .to_dict()
            if not self.history.empty and "brand_key" in self.history
            else {}
        )
        self.group_maps = self._build_group_maps(self.history)

    @staticmethod
    def _safe_median(values: Any) -> float | None:
        series = pd.to_numeric(values, errors="coerce").dropna()
        if series.empty:
            return None
        return float(series.median())

    @staticmethod
    def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
        data = frame.copy()
        rename = {
            "city_key_v194": "city_key",
            "color_key_v194": "color_key",
            "condition_risk_level_strict": "condition",
            "inspection_grade_norm": "inspection_grade",
        }
        data = data.rename(columns={k: v for k, v in rename.items() if k in data.columns and v not in data.columns})
        for column in [
            "brand_key",
            "series_key",
            "canonical_trim_key",
            "city_key",
            "color_key",
            "condition",
            "inspection_grade",
            "source_file",
            "observation_id",
            "source_type",
            "price_role",
            "runtime_candidate_lifecycle_key",
            "runtime_candidate_transaction_fingerprint",
        ]:
            if column not in data.columns:
                data[column] = ""
            data[column] = data[column].fillna("").astype(str)
        for column in [
            "price_yuan",
            "model_year",
            "age_years",
            "mileage_wan_km",
            "transfer_count",
            "source_row_id",
            "raw_index",
        ]:
            if column not in data.columns:
                data[column] = np.nan
            data[column] = pd.to_numeric(data[column], errors="coerce")
        for column in ["event_time", "knowledge_available_at", "pricing_available_at"]:
            if column not in data.columns:
                data[column] = pd.NaT
            data[column] = pd.to_datetime(data[column], errors="coerce")
        for flag in [
            "allowed_for_c2b_point_baseline",
            "clean_for_memory_flag",
            "market_clean_flag",
            "candidate_clean_flag",
            "runtime_candidate_dedup_keep_flag",
        ]:
            if flag not in data.columns:
                data[flag] = False
        role_ok = data["price_role"].eq("INTERNAL_C2B_PURCHASE_ACTUAL")
        clean_ok = (
            data["allowed_for_c2b_point_baseline"].fillna(False).astype(bool)
            | data["clean_for_memory_flag"].fillna(False).astype(bool)
            | data["market_clean_flag"].fillna(False).astype(bool)
            | data["candidate_clean_flag"].fillna(False).astype(bool)
        )
        dedup_ok = data["runtime_candidate_dedup_keep_flag"].fillna(True).astype(bool)
        clean = (
            role_ok
            & clean_ok
            & dedup_ok
            & data["price_yuan"].gt(1000)
            & data["brand_key"].ne("")
            & data["series_key"].ne("")
            & data["canonical_trim_key"].ne("")
        )
        data = data[clean].copy()
        if data.empty:
            return data
        data["canonical_trim_match_key"] = data["canonical_trim_key"].map(_trim_match_key)
        data["_product_memory_dedup_key"] = data["runtime_candidate_transaction_fingerprint"].where(
            data["runtime_candidate_transaction_fingerprint"].str.len().gt(0),
            data["runtime_candidate_lifecycle_key"],
        )
        data["_product_memory_dedup_key"] = data["_product_memory_dedup_key"].where(
            data["_product_memory_dedup_key"].str.len().gt(0),
            data["observation_id"],
        )
        data["_event_sort"] = pd.to_datetime(data["event_time"], errors="coerce")
        data = data.sort_values(["_product_memory_dedup_key", "_event_sort"], ascending=[True, False])
        non_empty = data["_product_memory_dedup_key"].astype(str).str.len().gt(0)
        data = pd.concat(
            [
                data[non_empty].drop_duplicates("_product_memory_dedup_key", keep="first"),
                data[~non_empty],
            ],
            ignore_index=False,
        ).reset_index(drop=True)
        return data

    @staticmethod
    def _build_group_maps(history: pd.DataFrame) -> dict[str, dict[tuple[Any, ...], np.ndarray]]:
        specs = {
            "same_trim_year": ["brand_key", "series_key", "canonical_trim_match_key", "model_year"],
            "same_trim_any_year": ["brand_key", "series_key", "canonical_trim_match_key"],
            "same_series_year": ["brand_key", "series_key", "model_year"],
            "same_series_any_year": ["brand_key", "series_key"],
            "same_trim_year_sparse": ["brand_key", "series_key", "canonical_trim_match_key", "model_year"],
            "same_trim_any_year_sparse": ["brand_key", "series_key", "canonical_trim_match_key"],
            "same_series_year_sparse": ["brand_key", "series_key", "model_year"],
            "same_series_any_year_sparse": ["brand_key", "series_key"],
        }
        maps: dict[str, dict[tuple[Any, ...], np.ndarray]] = {}
        if history.empty:
            return {name: {} for name in specs}
        for name, columns in specs.items():
            current: dict[tuple[Any, ...], np.ndarray] = {}
            for key, group in history.groupby(columns, sort=False, dropna=False):
                current[key if isinstance(key, tuple) else (key,)] = group.index.to_numpy()
            maps[name] = current
        return maps

    def _candidate_pool(self, query: dict[str, Any]) -> tuple[str, pd.DataFrame]:
        if self.history.empty:
            return "none", self.history.iloc[0:0].copy()
        query = {**query, "canonical_trim_match_key": _trim_match_key(query.get("canonical_trim_key"))}
        levels = [
            ("same_trim_year", ["brand_key", "series_key", "canonical_trim_match_key", "model_year"], 2),
            ("same_trim_any_year", ["brand_key", "series_key", "canonical_trim_match_key"], 4),
            # Sparse fallback: a single legal same-trim/same-series candidate is
            # usually more defensible than dropping into an unrelated direct
            # prior.  Keep these levels low-confidence, but do not silently
            # return None when the knowledge base has sparse same-identity
            # evidence.
            ("same_trim_year_sparse", ["brand_key", "series_key", "canonical_trim_match_key", "model_year"], 1),
            ("same_trim_any_year_sparse", ["brand_key", "series_key", "canonical_trim_match_key"], 1),
        ]
        for level, columns, min_rows in levels:
            key = tuple(query.get(column) for column in columns)
            idx = self.group_maps.get(level, {}).get(key, np.array([], dtype=int))
            if len(idx) == 0:
                continue
            pool = self.history.loc[idx].copy()
            pool = self._filter_asof(pool, query)
            if pool.empty:
                continue
            source_file = str(query.get("source_file") or "")
            raw_index = self._as_float(query.get("raw_index"))
            if source_file and np.isfinite(raw_index) and "source_file" in pool.columns and "raw_index" in pool.columns:
                pool = pool[
                    pool["source_file"].astype(str).ne(source_file)
                    | pd.to_numeric(pool["raw_index"], errors="coerce").ne(raw_index)
                ].copy()
            for id_col in ("goods_id", "product_id"):
                if id_col in pool.columns and query.get(id_col) is not None:
                    query_id = self._as_float(query.get(id_col))
                    if np.isfinite(query_id):
                        pool = pool[pd.to_numeric(pool[id_col], errors="coerce").ne(query_id)].copy()
            if len(pool) >= min_rows:
                return level, pool
        return "none", self.history.iloc[0:0].copy()

    @staticmethod
    def _filter_asof(pool: pd.DataFrame, query: dict[str, Any]) -> pd.DataFrame:
        quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce", utc=True)
        if pd.isna(quote_time):
            return pool
        out = pool.copy()
        event_time = pd.to_datetime(out.get("event_time"), errors="coerce", utc=True)
        available_at = pd.to_datetime(out.get("pricing_available_at"), errors="coerce", utc=True)
        knowledge_at = pd.to_datetime(out.get("knowledge_available_at"), errors="coerce", utc=True)
        effective_available = available_at.where(available_at.notna(), knowledge_at)
        keep = event_time.lt(quote_time) & effective_available.lt(quote_time)
        max_age_days = V194121ProductMemory._as_float(
            os.environ.get("V194_PRODUCT_MEMORY_MAX_AGE_DAYS"), 180.0
        )
        if not np.isfinite(max_age_days) or max_age_days <= 0:
            max_age_days = 180.0
        # Product memory is a current transaction anchor, not an archive
        # lookup. Older deals may remain available for audit/training but must
        # not directly set today's point price.
        keep &= event_time.ge(quote_time - pd.Timedelta(days=max_age_days))
        return out.loc[keep.fillna(False)].copy()

    @staticmethod
    def _as_float(value: Any, default: float = np.nan) -> float:
        numeric = pd.to_numeric(value, errors="coerce")
        return default if pd.isna(numeric) else float(numeric)

    def _score_pool(self, query: dict[str, Any], pool: pd.DataFrame, level: str) -> pd.DataFrame:
        if pool.empty:
            return pool.copy()
        out = pool.copy()
        query_age = self._as_float(query.get("age_years"))
        query_mileage = self._as_float(query.get("mileage_wan_km"))
        query_transfer = self._as_float(query.get("transfer_count"))
        query_year = self._as_float(query.get("model_year"))
        out["age_gap"] = (pd.to_numeric(out["age_years"], errors="coerce") - query_age).abs()
        out["mileage_gap"] = (pd.to_numeric(out["mileage_wan_km"], errors="coerce") - query_mileage).abs()
        out["transfer_gap"] = (pd.to_numeric(out["transfer_count"], errors="coerce") - query_transfer).abs()
        out["year_gap"] = (pd.to_numeric(out["model_year"], errors="coerce") - query_year).abs()
        # Runtime requests may carry timezone-aware ISO strings while historical
        # observations are often stored as timezone-naive local timestamps.
        # Normalize both sides to UTC before computing freshness so the product
        # memory works for real API payloads and offline CSV replays alike.
        quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce", utc=True)
        event_time = pd.to_datetime(out["event_time"], errors="coerce", utc=True)
        if pd.isna(quote_time):
            out["days_gap_abs"] = 180.0
        else:
            out["days_gap_abs"] = (event_time - quote_time).dt.days.abs().fillna(365.0)
        out["same_city"] = out["city_key"].astype(str).eq(str(query.get("city_key_v194") or query.get("city_key") or ""))
        out["same_color"] = out["color_key"].astype(str).eq(str(query.get("color_key_v194") or query.get("color_key") or ""))
        out["same_condition"] = out["condition"].astype(str).eq(str(query.get("condition_risk_level_strict") or query.get("condition") or "clean"))
        level_prior = {
            "same_trim_year": 1.00,
            "same_trim_any_year": 0.82,
            "same_series_year": 0.52,
            "same_series_any_year": 0.32,
            "same_trim_year_sparse": 0.72,
            "same_trim_any_year_sparse": 0.58,
            "same_series_year_sparse": 0.30,
            "same_series_any_year_sparse": 0.18,
        }.get(level, 0.10)
        time_half_life_days = self._as_float(os.environ.get("V194_PRODUCT_MEMORY_TIME_HALF_LIFE_DAYS"), 120.0)
        if not np.isfinite(time_half_life_days) or time_half_life_days <= 0:
            time_half_life_days = 210.0
        out["weight"] = (
            level_prior
            * np.exp(-out["age_gap"].fillna(3.0) / 0.85)
            * np.exp(-out["mileage_gap"].fillna(6.0) / 1.65)
            * np.exp(-out["transfer_gap"].fillna(2.0) * 0.38)
            * np.exp(-out["year_gap"].fillna(2.0) * 0.55)
            * np.exp(-out["days_gap_abs"].fillna(365.0) / time_half_life_days)
        )
        out["weight"] *= np.where(out["same_city"], 1.15, 0.92)
        out["weight"] *= np.where(out["same_color"], 1.03, 1.0)
        out["weight"] *= np.where(out["same_condition"], 1.06, 0.90)
        out = out.sort_values("weight", ascending=False, kind="stable").head(120).copy()
        out["retrieval_level"] = level
        out["final_retrieval_weight"] = out["weight"]
        out["used_for_point_baseline"] = True
        out["used_for_interval"] = True
        out["strict_point_candidate"] = level in {
            "same_trim_year",
            "same_trim_any_year",
            "same_trim_year_sparse",
            "same_trim_any_year_sparse",
        }
        out["fallback_point_candidate"] = level in {
            "same_series_year",
            "same_series_any_year",
            "same_series_year_sparse",
            "same_series_any_year_sparse",
        }
        out["selection_reason"] = "V194_121_FULL_KNOWLEDGE_PRODUCT_MEMORY_Q30"
        out["same_trim"] = level in {
            "same_trim_year",
            "same_trim_any_year",
            "same_trim_year_sparse",
            "same_trim_any_year_sparse",
        }
        out["same_configuration_across_year"] = level in {"same_trim_any_year", "same_trim_any_year_sparse"}
        out["same_powertrain"] = True
        out["condition_risk_level_strict"] = out["condition"]
        out["city_match"] = out["same_city"]
        out["color_match"] = out["same_color"]
        out["condition_match"] = out["same_condition"]
        out["age_difference"] = out["age_gap"]
        out["mileage_difference"] = out["mileage_gap"]
        out["transfer_difference"] = out["transfer_gap"]
        out["final_rank"] = np.arange(1, len(out) + 1)
        return out

    @staticmethod
    def _band_from_price(value: float) -> str:
        if not np.isfinite(value):
            return "unknown"
        if value < 10_000:
            return "0_1w"
        if value < 20_000:
            return "1_2w"
        if value < 30_000:
            return "2_3w"
        if value < 50_000:
            return "3_5w"
        if value < 100_000:
            return "5_10w"
        if value < 300_000:
            return "10_30w"
        return "30w_plus"

    def quote(self, normalized_query: dict[str, Any]) -> ProductMemoryResult | None:
        level, pool = self._candidate_pool(normalized_query)
        scored = self._score_pool(normalized_query, pool, level)
        if scored.empty:
            return None
        prices = pd.to_numeric(scored["price_yuan"], errors="coerce").to_numpy(dtype=float)
        weights = pd.to_numeric(scored["weight"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        q20 = weighted_quantile(prices, weights, 0.20)
        q25 = weighted_quantile(prices, weights, 0.25)
        q30 = weighted_quantile(prices, weights, 0.30)
        q40 = weighted_quantile(prices, weights, 0.40)
        q50 = weighted_quantile(prices, weights, 0.50)
        if not np.isfinite(q30) or q30 <= 0:
            return None
        # Keep the deployment policy simple and auditable: normal C2B uses q30.
        # Low residual cars remain a low-confidence specialist segment, but
        # still get a single point rather than falling back to an unrelated
        # model.
        band = self._band_from_price(q40)
        if band in {"0_1w", "1_2w", "2_3w"}:
            point = q35 = weighted_quantile(prices, weights, 0.35)
            policy = "UNDER3W_PRODUCT_MEMORY_Q35_LOW_VALUE_RESIDUAL"
        else:
            point = q30
            policy = "NORMAL_PRICE_C2B_CONSERVATIVE_Q30"
        low = weighted_quantile(prices, weights, 0.20)
        high = weighted_quantile(prices, weights, 0.60)
        if not np.isfinite(low) or low <= 0:
            low = point * 0.90
        if not np.isfinite(high) or high <= low:
            high = point * 1.10
        spread = (high - low) / point if point else np.inf
        confidence = (
            "high"
            if len(scored) >= 15 and spread <= 0.12 and level in {"same_trim_year", "same_trim_any_year"}
            else "medium"
            if len(scored) >= 6 and spread <= 0.22
            else "low"
        )
        return ProductMemoryResult(
            price_yuan=float(point),
            interval_low_yuan=float(low),
            interval_high_yuan=float(high),
            confidence_bucket=confidence,
            match_level=level,
            neighbor_count=int(len(scored)),
            q20_yuan=float(q20),
            q25_yuan=float(q25),
            q30_yuan=float(q30),
            q40_yuan=float(q40),
            q50_yuan=float(q50),
            min_neighbor_price_yuan=float(np.nanmin(prices)),
            max_neighbor_price_yuan=float(np.nanmax(prices)),
            policy=policy,
            candidates=scored,
        )
