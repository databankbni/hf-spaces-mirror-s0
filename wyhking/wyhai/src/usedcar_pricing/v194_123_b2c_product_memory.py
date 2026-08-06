"""v194.124 B2C sold-price product memory.

This module is the B2C counterpart of the v194.121 C2B product-memory layer.
It prices retail/sale scenarios from internal B2C sold actuals first, and only
falls back to a C2B->B2C markup bridge when sold evidence is thin.

Loss-making or quick-sale rows are not discarded.  They are marked as a lower
market regime and can drive the quick-sale lower bound, while normal sold
evidence remains the central reference when both regimes are present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v194_121_product_memory import _trim_match_key
from .v194_price_policy import weighted_quantile


B2C_PRODUCT_MEMORY_POLICY_VERSION = "v194_267_internal_b2c_sold_memory_plus_loss_support_policy"


@dataclass(frozen=True)
class B2CProductMemoryResult:
    price_yuan: float
    interval_low_yuan: float
    interval_high_yuan: float
    confidence_bucket: str
    match_level: str
    neighbor_count: int
    q20_yuan: float
    q25_yuan: float
    q40_yuan: float
    q50_yuan: float
    q60_yuan: float
    q75_yuan: float
    quick_sale_price_yuan: float
    normal_market_price_yuan: float
    loss_sale_candidate_count: int
    markup_ratio_used: float | None
    source_policy: str
    candidates: pd.DataFrame


class V194123B2CProductMemory:
    def __init__(self, warehouse: pd.DataFrame, c2b_product_memory: Any | None = None) -> None:
        self.c2b_product_memory = c2b_product_memory
        self.history = self._normalize_b2c_history(warehouse)
        self.external_listing = self._normalize_external_listing_history(warehouse)
        self.paired_markup = self._build_markup_table(warehouse)
        if not self.history.empty and not self.paired_markup.empty:
            ratio_by_vehicle = (
                self.paired_markup[["vehicle_id_hash", "b2c_to_c2b_markup_ratio"]]
                .dropna()
                .drop_duplicates("vehicle_id_hash", keep="last")
            )
            self.history = self.history.merge(ratio_by_vehicle, on="vehicle_id_hash", how="left")
        self.global_markup_ratio = self._safe_median(self.paired_markup.get("b2c_to_c2b_markup_ratio"))
        if not self.global_markup_ratio or not np.isfinite(self.global_markup_ratio):
            self.global_markup_ratio = 1.09
        self.group_maps = self._build_group_maps(self.history)
        self.external_group_maps = self._build_group_maps(self.external_listing)
        self.markup_maps = self._build_markup_maps(self.paired_markup)

    @staticmethod
    def _safe_median(values: Any) -> float | None:
        series = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if series.empty:
            return None
        return float(series.median())

    @staticmethod
    def _normalize_common(frame: pd.DataFrame) -> pd.DataFrame:
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
            "vehicle_id_hash",
            "runtime_candidate_lifecycle_key",
            "runtime_candidate_transaction_fingerprint",
            "brand",
            "series",
            "trim",
            "normalized_energy_type",
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
            "allowed_for_b2c_market_reference",
            "allowed_for_c2b_bridge_input",
            "market_clean_flag",
            "candidate_clean_flag",
            "clean_for_memory_flag",
            "runtime_candidate_dedup_keep_flag",
        ]:
            if flag not in data.columns:
                data[flag] = False
        data["canonical_trim_match_key"] = data["canonical_trim_key"].map(_trim_match_key)
        return data

    @classmethod
    def _normalize_b2c_history(cls, frame: pd.DataFrame) -> pd.DataFrame:
        data = cls._normalize_common(frame)
        role_ok = data["price_role"].eq("INTERNAL_B2C_SOLD_ACTUAL")
        clean_ok = (
            data["allowed_for_b2c_market_reference"].fillna(False).astype(bool)
            | data["allowed_for_c2b_bridge_input"].fillna(False).astype(bool)
            | data["market_clean_flag"].fillna(False).astype(bool)
            | data["candidate_clean_flag"].fillna(False).astype(bool)
            | data["clean_for_memory_flag"].fillna(False).astype(bool)
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
        data["_b2c_memory_dedup_key"] = data["runtime_candidate_transaction_fingerprint"].where(
            data["runtime_candidate_transaction_fingerprint"].str.len().gt(0),
            data["runtime_candidate_lifecycle_key"],
        )
        data["_b2c_memory_dedup_key"] = data["_b2c_memory_dedup_key"].where(
            data["_b2c_memory_dedup_key"].str.len().gt(0),
            data["observation_id"],
        )
        data["_event_sort"] = pd.to_datetime(data["event_time"], errors="coerce")
        data = data.sort_values(["_b2c_memory_dedup_key", "_event_sort"], ascending=[True, False])
        non_empty = data["_b2c_memory_dedup_key"].astype(str).str.len().gt(0)
        data = pd.concat(
            [
                data[non_empty].drop_duplicates("_b2c_memory_dedup_key", keep="first"),
                data[~non_empty],
            ],
            ignore_index=False,
        ).reset_index(drop=True)
        return data

    @classmethod
    def _normalize_external_listing_history(cls, frame: pd.DataFrame) -> pd.DataFrame:
        data = cls._normalize_common(frame)
        role_ok = data["price_role"].eq("EXTERNAL_B2C_LISTING")
        clean_ok = data["allowed_for_b2c_market_reference"].fillna(False).astype(bool) | data[
            "allowed_for_c2b_bridge_input"
        ].fillna(False).astype(bool)
        clean = (
            role_ok
            & clean_ok
            & data["price_yuan"].gt(1000)
            & data["brand_key"].ne("")
            & data["series_key"].ne("")
            & data["canonical_trim_key"].ne("")
        )
        data = data[clean].copy()
        if data.empty:
            return data
        data["original_listing_price_yuan"] = pd.to_numeric(data["price_yuan"], errors="coerce")
        # External listing is an asking price.  Use it only after a conservative
        # listing-to-sold discount and only as fallback/context; internal sold
        # actuals remain first priority.
        data["listing_to_sold_discount"] = 0.96
        data["price_yuan"] = data["original_listing_price_yuan"] * data["listing_to_sold_discount"]
        data["price_role"] = "EXTERNAL_B2C_LISTING_TO_B2C_SOLD_PROXY"
        data["_b2c_external_dedup_key"] = data["observation_id"].where(
            data["observation_id"].str.len().gt(0),
            data["runtime_candidate_lifecycle_key"],
        )
        data["_event_sort"] = pd.to_datetime(data["event_time"], errors="coerce")
        data = data.sort_values(["_b2c_external_dedup_key", "_event_sort"], ascending=[True, False])
        non_empty = data["_b2c_external_dedup_key"].astype(str).str.len().gt(0)
        data = pd.concat(
            [
                data[non_empty].drop_duplicates("_b2c_external_dedup_key", keep="first"),
                data[~non_empty],
            ],
            ignore_index=False,
        ).reset_index(drop=True)
        return data

    @classmethod
    def _build_markup_table(cls, frame: pd.DataFrame) -> pd.DataFrame:
        data = cls._normalize_common(frame)
        data = data[data["vehicle_id_hash"].str.len().gt(0) & data["price_yuan"].gt(1000)].copy()
        if data.empty:
            return pd.DataFrame()
        b2c = data[data["price_role"].eq("INTERNAL_B2C_SOLD_ACTUAL")].copy()
        c2b = data[data["price_role"].eq("INTERNAL_C2B_PURCHASE_ACTUAL")].copy()
        if b2c.empty or c2b.empty:
            return pd.DataFrame()
        b2c = b2c.sort_values("event_time").groupby("vehicle_id_hash", as_index=False).tail(1)
        c2b = c2b.sort_values("event_time").groupby("vehicle_id_hash", as_index=False).tail(1)
        keep_columns = [
            "vehicle_id_hash",
            "brand_key",
            "series_key",
            "canonical_trim_match_key",
            "model_year",
            "city_key",
            "price_yuan",
            "event_time",
        ]
        pairs = b2c[keep_columns].merge(
            c2b[["vehicle_id_hash", "price_yuan", "event_time"]],
            on="vehicle_id_hash",
            suffixes=("_b2c", "_c2b"),
        )
        if pairs.empty:
            return pairs
        pairs["b2c_to_c2b_markup_ratio"] = pd.to_numeric(pairs["price_yuan_b2c"], errors="coerce") / pd.to_numeric(
            pairs["price_yuan_c2b"], errors="coerce"
        )
        pairs = pairs[
            pairs["b2c_to_c2b_markup_ratio"].between(0.72, 1.85)
            & pairs["price_yuan_b2c"].gt(1000)
            & pairs["price_yuan_c2b"].gt(1000)
        ].copy()
        pairs["loss_sale_ratio_flag"] = pairs["b2c_to_c2b_markup_ratio"].lt(1.00)
        pairs["thin_margin_or_quick_sale_flag"] = pairs["b2c_to_c2b_markup_ratio"].lt(1.03)
        return pairs.reset_index(drop=True)

    @staticmethod
    def _build_group_maps(history: pd.DataFrame) -> dict[str, dict[tuple[Any, ...], np.ndarray]]:
        specs = {
            "same_trim_year": ["brand_key", "series_key", "canonical_trim_match_key", "model_year"],
            "same_trim_any_year": ["brand_key", "series_key", "canonical_trim_match_key"],
            "same_series_year": ["brand_key", "series_key", "model_year"],
            "same_series_any_year": ["brand_key", "series_key"],
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

    @staticmethod
    def _build_markup_maps(markup: pd.DataFrame) -> dict[str, dict[tuple[Any, ...], float]]:
        if markup.empty:
            return {}
        specs = {
            "same_trim_year": ["brand_key", "series_key", "canonical_trim_match_key", "model_year"],
            "same_trim_any_year": ["brand_key", "series_key", "canonical_trim_match_key"],
            "same_series_year": ["brand_key", "series_key", "model_year"],
            "same_series_any_year": ["brand_key", "series_key"],
            "brand": ["brand_key"],
        }
        maps: dict[str, dict[tuple[Any, ...], float]] = {}
        for name, columns in specs.items():
            current: dict[tuple[Any, ...], float] = {}
            for key, group in markup.groupby(columns, sort=False, dropna=False):
                ratios = pd.to_numeric(group["b2c_to_c2b_markup_ratio"], errors="coerce").dropna()
                if len(ratios) >= (3 if name != "brand" else 10):
                    current[key if isinstance(key, tuple) else (key,)] = float(ratios.median())
            maps[name] = current
        return maps

    def _markup_ratio(self, query: dict[str, Any]) -> tuple[float, str]:
        query = {**query, "canonical_trim_match_key": _trim_match_key(query.get("canonical_trim_key"))}
        levels = [
            ("same_trim_year", ["brand_key", "series_key", "canonical_trim_match_key", "model_year"]),
            ("same_trim_any_year", ["brand_key", "series_key", "canonical_trim_match_key"]),
            ("same_series_year", ["brand_key", "series_key", "model_year"]),
            ("same_series_any_year", ["brand_key", "series_key"]),
            ("brand", ["brand_key"]),
        ]
        for level, columns in levels:
            key = tuple(query.get(column) for column in columns)
            ratio = self.markup_maps.get(level, {}).get(key)
            if ratio and np.isfinite(ratio):
                return float(np.clip(ratio, 0.88, 1.38)), level
        return float(np.clip(self.global_markup_ratio, 0.92, 1.32)), "global"

    def _candidate_pool(self, query: dict[str, Any]) -> tuple[str, pd.DataFrame]:
        if self.history.empty:
            return "none", self.history.iloc[0:0].copy()
        query = {**query, "canonical_trim_match_key": _trim_match_key(query.get("canonical_trim_key"))}
        levels = [
            ("same_trim_year", ["brand_key", "series_key", "canonical_trim_match_key", "model_year"], 1),
            ("same_trim_any_year", ["brand_key", "series_key", "canonical_trim_match_key"], 3),
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
            if len(pool) >= min_rows:
                return level, pool
        return "none", self.history.iloc[0:0].copy()

    def _external_candidate_pool(self, query: dict[str, Any]) -> tuple[str, pd.DataFrame]:
        if self.external_listing.empty:
            return "none", self.external_listing.iloc[0:0].copy()
        query = {**query, "canonical_trim_match_key": _trim_match_key(query.get("canonical_trim_key"))}
        levels = [
            ("same_trim_year", ["brand_key", "series_key", "canonical_trim_match_key", "model_year"], 2),
            ("same_trim_any_year", ["brand_key", "series_key", "canonical_trim_match_key"], 4),
        ]
        for level, columns, min_rows in levels:
            key = tuple(query.get(column) for column in columns)
            idx = self.external_group_maps.get(level, {}).get(key, np.array([], dtype=int))
            if len(idx) == 0:
                continue
            pool = self.external_listing.loc[idx].copy()
            pool = self._filter_asof(pool, query)
            if pool.empty:
                continue
            if len(pool) >= min_rows:
                return f"external_listing_{level}", pool
        return "none", self.external_listing.iloc[0:0].copy()

    @staticmethod
    def _match_mask(frame: pd.DataFrame, query: dict[str, Any], columns: list[str]) -> pd.Series:
        mask = pd.Series(True, index=frame.index)
        for column in columns:
            value = query.get(column)
            if column == "canonical_trim_match_key":
                value = _trim_match_key(query.get("canonical_trim_key"))
            if column == "model_year":
                mask &= pd.to_numeric(frame.get(column), errors="coerce").eq(pd.to_numeric(value, errors="coerce"))
            else:
                mask &= frame.get(column, pd.Series("", index=frame.index)).astype(str).eq(str(value or ""))
        return mask.fillna(False)

    def _loss_support_context(self, query: dict[str, Any], scored_pool: pd.DataFrame) -> dict[str, Any]:
        """Classify low-margin sold rows as supported outliers or market pressure.

        A loss/near-loss B2C sale can mean two very different things:
        an isolated disposal row, or a genuine current-market pressure signal.
        The online B2C point price should only move meaningfully when the signal
        is repeated and not contradicted by recent legal same-vehicle support.
        """

        context: dict[str, Any] = {
            "enabled": False,
            "strong_normal_support": False,
            "medium_normal_support": False,
            "pressure_signal": False,
            "reason": "NO_LOSS_OR_QUICK_SALE_CANDIDATES",
        }
        if scored_pool.empty:
            return context
        ratio = pd.to_numeric(
            scored_pool.get("b2c_to_c2b_markup_ratio", pd.Series(np.nan, index=scored_pool.index)),
            errors="coerce",
        )
        loss_mask = ratio.lt(1.00).fillna(False)
        quick_mask = ratio.lt(1.03).fillna(False)
        if not bool(loss_mask.any() or quick_mask.any()):
            return context

        candidate_level = str(query.get("_candidate_level") or "")
        weights = pd.to_numeric(scored_pool.get("weight"), errors="coerce").fillna(0.0)
        total_weight = float(weights.sum()) if len(weights) else 0.0
        quick_weight_share = float(weights[quick_mask].sum() / total_weight) if total_weight > 0 else 0.0
        loss_weight_share = float(weights[loss_mask].sum() / total_weight) if total_weight > 0 else 0.0
        prices = pd.to_numeric(scored_pool.get("price_yuan"), errors="coerce")
        quick_price = float(prices[quick_mask].median()) if bool(quick_mask.any()) else np.nan
        normal_mask = (ratio.ge(1.03) | ratio.isna()).fillna(False)
        legal_pair_mask = ratio.ge(1.00).fillna(False)
        normal_price = float(prices[normal_mask].median()) if bool(normal_mask.any()) else np.nan
        quick_vs_normal = quick_price / normal_price if np.isfinite(quick_price) and np.isfinite(normal_price) and normal_price > 0 else np.nan
        normal_count = int(normal_mask.sum())
        legal_pair_count = int(legal_pair_mask.sum())
        quick_count = int(quick_mask.sum())
        loss_count = int(loss_mask.sum())
        exact_level = candidate_level in {"same_trim_year", "same_trim_any_year"}
        series_year_level = candidate_level == "same_series_year"
        strong_support = (
            (exact_level and (legal_pair_count >= 2 or normal_count >= 4))
            or (series_year_level and normal_count >= 10)
            or (not exact_level and normal_count >= 18 and quick_weight_share < 0.10)
        )
        medium_support = strong_support or (
            (exact_level and normal_count >= 2)
            or (series_year_level and normal_count >= 6)
            or (normal_count >= 12 and quick_weight_share < 0.18)
        )
        pressure_signal = bool(
            quick_count >= 2
            and not strong_support
            and (
                quick_weight_share >= 0.12
                or loss_weight_share >= 0.06
                or (np.isfinite(quick_vs_normal) and quick_vs_normal <= 0.96)
            )
        )
        if strong_support:
            reason = "NORMAL_LEGAL_SUPPORT_CONTRADICTS_LOSS_OR_QUICK_SALE"
        elif pressure_signal:
            reason = "REPEATED_LOSS_OR_QUICK_SALE_WITH_WEAK_NORMAL_SUPPORT"
        elif medium_support:
            reason = "MEDIUM_NORMAL_SUPPORT_PARTIALLY_CONSTRAINS_LOSS_SIGNAL"
        else:
            reason = "WEAK_SUPPORT_KEEP_LOSS_AS_PRESSURE_BOUND"
            pressure_signal = bool(quick_count >= 1 and quick_weight_share >= 0.08)
        context.update(
            {
                "enabled": True,
                "strong_normal_support": bool(strong_support),
                "medium_normal_support": bool(medium_support),
                "pressure_signal": bool(pressure_signal),
                "reason": reason,
                "candidate_loss_count": loss_count,
                "candidate_quick_count": quick_count,
                "candidate_loss_weight_share": round(loss_weight_share, 6),
                "candidate_quick_weight_share": round(quick_weight_share, 6),
                "candidate_quick_vs_normal_price_ratio": round(float(quick_vs_normal), 6)
                if np.isfinite(quick_vs_normal)
                else None,
                "b2c_legal_same_trim_year_count": legal_pair_count if candidate_level == "same_trim_year" else 0,
                "b2c_legal_same_trim_any_year_count": legal_pair_count if exact_level else 0,
                "b2c_normal_same_trim_any_year_count": normal_count if exact_level else 0,
                "b2c_normal_same_series_year_count": normal_count if series_year_level else 0,
                "b2c_quick_same_trim_any_year_count": quick_count if exact_level else 0,
                "b2c_quick_same_series_year_count": quick_count if series_year_level else 0,
                "c2b_same_trim_year_count": 0,
                "c2b_same_trim_any_year_count": 0,
                "c2b_same_series_year_count": 0,
                "c2b_same_series_any_year_count": 0,
            }
        )
        return context

        quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce")
        history = self._filter_asof(self.history, query)
        if not history.empty and pd.notna(quote_time):
            history = history[pd.to_datetime(history["event_time"], errors="coerce").ge(quote_time - pd.Timedelta(days=365))]
        c2b_history = pd.DataFrame()
        if self.c2b_product_memory is not None and hasattr(self.c2b_product_memory, "history"):
            c2b_history = self.c2b_product_memory._filter_asof(self.c2b_product_memory.history, query)
            if not c2b_history.empty and pd.notna(quote_time):
                c2b_history = c2b_history[
                    pd.to_datetime(c2b_history["event_time"], errors="coerce").ge(quote_time - pd.Timedelta(days=365))
                ]

        query = {**query, "canonical_trim_match_key": _trim_match_key(query.get("canonical_trim_key"))}
        same_trim_year = ["brand_key", "series_key", "canonical_trim_match_key", "model_year"]
        same_trim_any_year = ["brand_key", "series_key", "canonical_trim_match_key"]
        same_series_year = ["brand_key", "series_key", "model_year"]
        same_series_any_year = ["brand_key", "series_key"]

        def b2c_counts(columns: list[str]) -> tuple[int, int, int]:
            if history.empty:
                return 0, 0, 0
            subset = history[self._match_mask(history, query, columns)].copy()
            if subset.empty:
                return 0, 0, 0
            subset_ratio = pd.to_numeric(subset.get("b2c_to_c2b_markup_ratio"), errors="coerce")
            legal_pair_count = int(subset_ratio.ge(1.00).sum())
            normal_or_unpaired_count = int((subset_ratio.ge(1.03) | subset_ratio.isna()).sum())
            quick_or_loss_count = int(subset_ratio.lt(1.03).sum())
            return legal_pair_count, normal_or_unpaired_count, quick_or_loss_count

        def c2b_count(columns: list[str]) -> int:
            if c2b_history.empty:
                return 0
            return int(self._match_mask(c2b_history, query, columns).sum())

        b2c_legal_trim_year, b2c_normal_trim_year, b2c_quick_trim_year = b2c_counts(same_trim_year)
        b2c_legal_trim_any, b2c_normal_trim_any, b2c_quick_trim_any = b2c_counts(same_trim_any_year)
        b2c_legal_series_year, b2c_normal_series_year, b2c_quick_series_year = b2c_counts(same_series_year)
        b2c_legal_series_any, b2c_normal_series_any, b2c_quick_series_any = b2c_counts(same_series_any_year)
        c2b_trim_year = c2b_count(same_trim_year)
        c2b_trim_any = c2b_count(same_trim_any_year)
        c2b_series_year = c2b_count(same_series_year)
        c2b_series_any = c2b_count(same_series_any_year)

        weights = pd.to_numeric(scored_pool.get("weight"), errors="coerce").fillna(0.0)
        total_weight = float(weights.sum()) if len(weights) else 0.0
        quick_weight_share = float(weights[quick_mask].sum() / total_weight) if total_weight > 0 else 0.0
        loss_weight_share = float(weights[loss_mask].sum() / total_weight) if total_weight > 0 else 0.0
        prices = pd.to_numeric(scored_pool.get("price_yuan"), errors="coerce")
        quick_price = float(prices[quick_mask].median()) if bool(quick_mask.any()) else np.nan
        normal_price = float(prices[~quick_mask].median()) if bool((~quick_mask).any()) else np.nan
        quick_vs_normal = quick_price / normal_price if np.isfinite(quick_price) and np.isfinite(normal_price) and normal_price > 0 else np.nan

        strong_support = (
            b2c_legal_trim_year >= 2
            or b2c_legal_trim_any >= 3
            or b2c_normal_trim_any >= 5
            or b2c_normal_series_year >= 10
            or c2b_trim_year >= 3
            or c2b_trim_any >= 5
            or c2b_series_year >= 12
        )
        medium_support = (
            strong_support
            or b2c_normal_trim_any >= 3
            or b2c_normal_series_year >= 6
            or b2c_normal_series_any >= 18
            or c2b_trim_any >= 3
            or c2b_series_year >= 8
            or c2b_series_any >= 25
        )
        repeated_quick_pressure = (
            int(quick_mask.sum()) >= 2
            and (
                quick_weight_share >= 0.12
                or (np.isfinite(quick_vs_normal) and quick_vs_normal <= 0.96)
                or b2c_quick_trim_any >= 2
                or b2c_quick_series_year >= 4
            )
        )
        pressure_signal = bool(repeated_quick_pressure and not strong_support)
        if strong_support:
            reason = "NORMAL_LEGAL_SUPPORT_CONTRADICTS_LOSS_OR_QUICK_SALE"
        elif pressure_signal:
            reason = "REPEATED_LOSS_OR_QUICK_SALE_WITH_WEAK_NORMAL_SUPPORT"
        elif medium_support:
            reason = "MEDIUM_NORMAL_SUPPORT_PARTIALLY_CONSTRAINS_LOSS_SIGNAL"
        else:
            reason = "WEAK_SUPPORT_KEEP_LOSS_AS_PRESSURE_BOUND"
            pressure_signal = bool(int(quick_mask.sum()) >= 1 and quick_weight_share >= 0.08)

        context.update(
            {
                "enabled": True,
                "strong_normal_support": bool(strong_support),
                "medium_normal_support": bool(medium_support),
                "pressure_signal": bool(pressure_signal),
                "reason": reason,
                "candidate_loss_count": int(loss_mask.sum()),
                "candidate_quick_count": int(quick_mask.sum()),
                "candidate_loss_weight_share": round(loss_weight_share, 6),
                "candidate_quick_weight_share": round(quick_weight_share, 6),
                "candidate_quick_vs_normal_price_ratio": round(float(quick_vs_normal), 6)
                if np.isfinite(quick_vs_normal)
                else None,
                "b2c_legal_same_trim_year_count": b2c_legal_trim_year,
                "b2c_legal_same_trim_any_year_count": b2c_legal_trim_any,
                "b2c_normal_same_trim_any_year_count": b2c_normal_trim_any,
                "b2c_normal_same_series_year_count": b2c_normal_series_year,
                "b2c_quick_same_trim_any_year_count": b2c_quick_trim_any,
                "b2c_quick_same_series_year_count": b2c_quick_series_year,
                "c2b_same_trim_year_count": c2b_trim_year,
                "c2b_same_trim_any_year_count": c2b_trim_any,
                "c2b_same_series_year_count": c2b_series_year,
                "c2b_same_series_any_year_count": c2b_series_any,
            }
        )
        return context

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
        return out.loc[keep.fillna(False)].copy()

    @staticmethod
    def _as_float(value: Any, default: float = np.nan) -> float:
        numeric = pd.to_numeric(value, errors="coerce")
        return default if pd.isna(numeric) else float(numeric)

    @classmethod
    def _listing_anchor_price(cls, query: dict[str, Any]) -> float | None:
        for key in (
            "b2c_listing_price_yuan",
            "current_listing_price_yuan",
            "current_display_price_yuan",
            "first_listing_price_yuan",
            "first_display_price_yuan",
            "listing_price_yuan",
        ):
            value = cls._as_float(query.get(key))
            if np.isfinite(value) and value > 1000:
                return float(value)
        return None

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
        quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce")
        event_time = pd.to_datetime(out["event_time"], errors="coerce")
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
            "same_series_year": 0.50,
            "same_series_any_year": 0.30,
        }.get(level, 0.10)
        out["weight"] = (
            level_prior
            * np.exp(-out["age_gap"].fillna(3.0) / 0.80)
            * np.exp(-out["mileage_gap"].fillna(6.0) / 1.50)
            * np.exp(-out["transfer_gap"].fillna(2.0) * 0.35)
            * np.exp(-out["year_gap"].fillna(2.0) * 0.50)
            * np.exp(-out["days_gap_abs"].fillna(365.0) / 180.0)
        )
        out["weight"] *= np.where(out["same_city"], 1.18, 0.92)
        out["weight"] *= np.where(out["same_color"], 1.04, 1.0)
        out["weight"] *= np.where(out["same_condition"], 1.05, 0.90)
        # Paired vehicle analysis shows about 7% of internal B2C sold rows are
        # below C2B cost. They are real market signals, but should not dominate
        # the normal retail central price unless they are the freshest exact
        # evidence for the current query.
        paired_ratio = pd.to_numeric(out.get("b2c_to_c2b_markup_ratio", pd.Series(np.nan, index=out.index)), errors="coerce")
        out["loss_sale_candidate_flag"] = paired_ratio.lt(1.00).fillna(False)
        out["quick_sale_candidate_flag"] = paired_ratio.lt(1.03).fillna(False)
        loss_context = self._loss_support_context({**query, "_candidate_level": level}, out)
        out["loss_support_policy_reason"] = loss_context.get("reason", "")
        out["loss_support_strong_normal_support"] = bool(loss_context.get("strong_normal_support", False))
        out["loss_support_market_pressure_signal"] = bool(loss_context.get("pressure_signal", False))
        out["loss_candidate_treatment"] = "normal_market_candidate"
        loss_normal_multiplier = 0.62
        quick_normal_multiplier = 1.00
        quick_sale_multiplier = 1.20
        normal_quick_multiplier = 0.95
        if loss_context.get("enabled"):
            if loss_context.get("strong_normal_support"):
                loss_normal_multiplier = 0.20
                quick_normal_multiplier = 0.85
                quick_sale_multiplier = 1.28
                out.loc[out["loss_sale_candidate_flag"], "loss_candidate_treatment"] = "supported_loss_outlier_downweighted"
                out.loc[
                    out["quick_sale_candidate_flag"] & ~out["loss_sale_candidate_flag"],
                    "loss_candidate_treatment",
                ] = "supported_quick_sale_lower_bound"
            elif loss_context.get("pressure_signal"):
                loss_normal_multiplier = 0.88
                quick_normal_multiplier = 1.12
                quick_sale_multiplier = 1.55
                normal_quick_multiplier = 0.90
                out.loc[out["loss_sale_candidate_flag"], "loss_candidate_treatment"] = "market_pressure_loss_signal"
                out.loc[
                    out["quick_sale_candidate_flag"] & ~out["loss_sale_candidate_flag"],
                    "loss_candidate_treatment",
                ] = "market_pressure_quick_sale_signal"
            elif loss_context.get("medium_normal_support"):
                loss_normal_multiplier = 0.38
                quick_normal_multiplier = 0.94
                quick_sale_multiplier = 1.34
                out.loc[out["loss_sale_candidate_flag"], "loss_candidate_treatment"] = "medium_supported_loss_downweighted"
                out.loc[
                    out["quick_sale_candidate_flag"] & ~out["loss_sale_candidate_flag"],
                    "loss_candidate_treatment",
                ] = "medium_supported_quick_sale_signal"
            else:
                loss_normal_multiplier = 0.70
                quick_normal_multiplier = 1.05
                quick_sale_multiplier = 1.45
                out.loc[out["loss_sale_candidate_flag"], "loss_candidate_treatment"] = "weak_support_loss_pressure_bound"
                out.loc[
                    out["quick_sale_candidate_flag"] & ~out["loss_sale_candidate_flag"],
                    "loss_candidate_treatment",
                ] = "weak_support_quick_sale_pressure_bound"
        normal_multiplier = np.ones(len(out), dtype=float)
        normal_multiplier = np.where(out["loss_sale_candidate_flag"], loss_normal_multiplier, normal_multiplier)
        normal_multiplier = np.where(
            out["quick_sale_candidate_flag"] & ~out["loss_sale_candidate_flag"],
            quick_normal_multiplier,
            normal_multiplier,
        )
        quick_multiplier = np.where(out["quick_sale_candidate_flag"], quick_sale_multiplier, normal_quick_multiplier)
        out["normal_market_weight"] = out["weight"] * normal_multiplier
        out["quick_sale_weight"] = out["weight"] * quick_multiplier
        out = out.sort_values("weight", ascending=False, kind="stable").head(160).copy()
        out["retrieval_level"] = level
        out["final_retrieval_weight"] = out["weight"]
        out["used_for_point_baseline"] = True
        out["used_for_interval"] = True
        out["strict_point_candidate"] = level in {"same_trim_year", "same_trim_any_year"}
        out["fallback_point_candidate"] = level in {"same_series_year", "same_series_any_year"}
        out["selection_reason"] = "V194_123_B2C_SOLD_PRODUCT_MEMORY"
        out["same_trim"] = level in {"same_trim_year", "same_trim_any_year"}
        out["same_configuration_across_year"] = level in {"same_trim_any_year"}
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
    def _fresh_exact_top_price(scored: pd.DataFrame) -> float | None:
        if scored.empty:
            return None
        top = scored.sort_values("weight", ascending=False).head(1).iloc[0]
        if (
            str(top.get("retrieval_level")) == "same_trim_year"
            and bool(top.get("same_city"))
            and bool(top.get("same_color"))
            and float(top.get("age_gap") if pd.notna(top.get("age_gap")) else 999) <= 0.15
            and float(top.get("mileage_gap") if pd.notna(top.get("mileage_gap")) else 999) <= 0.20
            and float(top.get("transfer_gap") if pd.notna(top.get("transfer_gap")) else 999) <= 0.10
            and float(top.get("days_gap_abs") if pd.notna(top.get("days_gap_abs")) else 999) <= 7
        ):
            price = pd.to_numeric(top.get("price_yuan"), errors="coerce")
            if pd.notna(price) and price > 1000:
                return float(price)
        return None

    def quote(self, normalized_query: dict[str, Any]) -> B2CProductMemoryResult | None:
        level, pool = self._candidate_pool(normalized_query)
        scored = self._score_pool(normalized_query, pool, level)
        markup_ratio, markup_level = self._markup_ratio(normalized_query)
        if scored.empty and self.c2b_product_memory is not None:
            external_level, external_pool = self._external_candidate_pool(normalized_query)
            external_scored = self._score_pool(normalized_query, external_pool, external_level.replace("external_listing_", ""))
            if not external_scored.empty:
                prices = pd.to_numeric(external_scored["price_yuan"], errors="coerce").to_numpy(dtype=float)
                weights = pd.to_numeric(external_scored["normal_market_weight"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                q25 = weighted_quantile(prices, weights, 0.25)
                q50 = weighted_quantile(prices, weights, 0.50)
                q75 = weighted_quantile(prices, weights, 0.75)
                if np.isfinite(q50) and q50 > 0:
                    external_scored["selection_reason"] = "V194_123_EXTERNAL_LISTING_TO_B2C_SOLD_PROXY_FALLBACK"
                    return B2CProductMemoryResult(
                        price_yuan=float(q50),
                        interval_low_yuan=float(q25 if np.isfinite(q25) and q25 > 0 else q50 * 0.90),
                        interval_high_yuan=float(q75 if np.isfinite(q75) and q75 > q50 else q50 * 1.12),
                        confidence_bucket="medium" if len(external_scored) >= 8 and external_level in {"external_listing_same_trim_year", "external_listing_same_trim_any_year"} else "low",
                        match_level=external_level,
                        neighbor_count=int(len(external_scored)),
                        q20_yuan=float(q25 if np.isfinite(q25) else q50 * 0.90),
                        q25_yuan=float(q25 if np.isfinite(q25) else q50 * 0.90),
                        q40_yuan=float(weighted_quantile(prices, weights, 0.40)),
                        q50_yuan=float(q50),
                        q60_yuan=float(weighted_quantile(prices, weights, 0.60)),
                        q75_yuan=float(q75 if np.isfinite(q75) else q50 * 1.12),
                        quick_sale_price_yuan=float(q25 if np.isfinite(q25) and q25 > 0 else q50 * 0.90),
                        normal_market_price_yuan=float(q50),
                        loss_sale_candidate_count=0,
                        markup_ratio_used=None,
                        source_policy="EXTERNAL_LISTING_TO_B2C_SOLD_PROXY_FALLBACK",
                        candidates=external_scored,
                    )
            c2b_result = self.c2b_product_memory.quote(normalized_query)
            if c2b_result and c2b_result.price_yuan:
                price = float(c2b_result.price_yuan) * markup_ratio
                low = float(c2b_result.interval_low_yuan) * markup_ratio
                high = float(c2b_result.interval_high_yuan) * markup_ratio
                candidates = c2b_result.candidates.copy()
                candidates["price_role"] = "INTERNAL_C2B_PURCHASE_ACTUAL_AS_B2C_MARKUP_BRIDGE"
                candidates["converted_b2c_price"] = pd.to_numeric(candidates["price_yuan"], errors="coerce") * markup_ratio
                candidates["price_yuan"] = candidates["converted_b2c_price"]
                candidates["bridge_markup_ratio_used"] = markup_ratio
                candidates["selection_reason"] = "V194_123_C2B_TO_B2C_MARKUP_FALLBACK"
                return B2CProductMemoryResult(
                    price_yuan=float(price),
                    interval_low_yuan=float(low),
                    interval_high_yuan=float(high),
                    confidence_bucket="low" if c2b_result.confidence_bucket == "low" else "medium",
                    match_level=f"c2b_markup_{c2b_result.match_level}_{markup_level}",
                    neighbor_count=int(c2b_result.neighbor_count),
                    q20_yuan=float(low),
                    q25_yuan=float(low),
                    q40_yuan=float(price),
                    q50_yuan=float(price),
                    q60_yuan=float(price),
                    q75_yuan=float(high),
                    quick_sale_price_yuan=float(low),
                    normal_market_price_yuan=float(price),
                    loss_sale_candidate_count=0,
                    markup_ratio_used=float(markup_ratio),
                    source_policy="C2B_PRODUCT_MEMORY_PLUS_SEGMENT_B2C_MARKUP",
                    candidates=candidates,
                )
        if scored.empty:
            return None
        prices = pd.to_numeric(scored["price_yuan"], errors="coerce").to_numpy(dtype=float)
        weights = pd.to_numeric(scored["normal_market_weight"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        quick_weights = pd.to_numeric(scored["quick_sale_weight"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        q20 = weighted_quantile(prices, quick_weights, 0.20)
        q25 = weighted_quantile(prices, quick_weights, 0.25)
        q40 = weighted_quantile(prices, weights, 0.40)
        q50 = weighted_quantile(prices, weights, 0.50)
        q60 = weighted_quantile(prices, weights, 0.60)
        q75 = weighted_quantile(prices, weights, 0.75)
        if not np.isfinite(q50) or q50 <= 0:
            return None
        top_price = self._fresh_exact_top_price(scored)
        if top_price:
            point = top_price
            source_policy = "LATEST_FRESH_EXACT_INTERNAL_B2C_SOLD_NEIGHBOR"
        elif level in {"same_trim_year", "same_trim_any_year"}:
            point = q50
            source_policy = "NORMAL_INTERNAL_B2C_SOLD_WEIGHTED_MEDIAN"
        else:
            point = q40
            source_policy = "FALLBACK_INTERNAL_B2C_SOLD_CONSERVATIVE_P40"
        low = q20 if np.isfinite(q20) and q20 > 0 else point * 0.90
        high = q75 if np.isfinite(q75) and q75 > low else point * 1.12
        # B2C is the primary retail anchor.  Once we have same-trim B2C sold
        # evidence, C2B can provide a profit floor only in the service layer; it
        # must not cap the retail point downward.  The old cap is exactly what
        # caused good same-trim B2C evidence to be pulled toward low C2B memory.
        c2b_cap_applied = False
        listing_anchor = self._listing_anchor_price(normalized_query)
        if not top_price and listing_anchor:
            listing_to_memory_ratio = listing_anchor / point if point else np.inf
            source = str(normalized_query.get("b2c_listing_price_source") or "").lower()
            is_current_display = any(token in source for token in ("latest", "current", "adjusted"))
            # 最新展板价/调价后价格是 B2C 售价链路中报价前已存在的强业务锚；
            # 首次展板价则只能当弱参考，避免初始高挂牌污染成交点价。
            ratio_allowed = (0.35 <= listing_to_memory_ratio <= 2.20) if is_current_display else (0.55 <= listing_to_memory_ratio <= 1.10)
            if ratio_allowed:
                disposal = str(normalized_query.get("b2c_disposal_flag") or "").strip() in {"1", "true", "True", "是"}
                listing_reference = listing_anchor * (1.00 if is_current_display else (0.95 if disposal else 0.97))
                if np.isfinite(listing_reference) and listing_reference > 1000:
                    point = float(listing_reference)
                    low = min(low, point * 0.94)
                    high = max(point * 1.06, min(high, point * 1.18))
                    suffix = "WITH_CURRENT_LISTING_ANCHOR" if is_current_display else "WITH_LISTING_ANCHOR_DISCOUNT"
                    source_policy = f"{source_policy}_{suffix}"
        spread = (high - low) / point if point else np.inf
        confidence = (
            "high"
            if len(scored) >= 12 and spread <= 0.16 and level in {"same_trim_year", "same_trim_any_year"}
            else "medium"
            if len(scored) >= 5 and spread <= 0.26
            else "low"
        )
        return B2CProductMemoryResult(
            price_yuan=float(point),
            interval_low_yuan=float(low),
            interval_high_yuan=float(high),
            confidence_bucket=confidence,
            match_level=level,
            neighbor_count=int(len(scored)),
            q20_yuan=float(q20),
            q25_yuan=float(q25),
            q40_yuan=float(q40),
            q50_yuan=float(q50),
            q60_yuan=float(q60),
            q75_yuan=float(q75),
            quick_sale_price_yuan=float(q25 if np.isfinite(q25) and q25 > 0 else low),
            normal_market_price_yuan=float(q50),
            loss_sale_candidate_count=int(scored["loss_sale_candidate_flag"].sum()),
            markup_ratio_used=float(markup_ratio) if c2b_cap_applied else None,
            source_policy=source_policy,
            candidates=scored,
        )
