from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .data import PARENT_KEYS, clean_text
from .v191_1 import TemporalObservationIndex, bridge_statistics
from .v192_12_semantics import (
    add_v192_12_candidate_similarity,
    normalize_energy_type,
)


LEVEL_BASE_SCORE = {"L0": 1.00, "L1": 0.92, "L2": 0.82, "L3": 0.68, "L4": 0.54, "L5": 0.38}
SOURCE_QUALITY = {"C2B": 1.00, "B2C": 0.90, "EXT_B2C_LISTING": 0.72}


class ComparableRetriever:
    def __init__(self, observations: pd.DataFrame, temporal_index: TemporalObservationIndex):
        self.observations = observations
        self.temporal_index = temporal_index
        self.exact: dict[tuple[Any, ...], pd.DataFrame] = {}
        self.series_year: dict[tuple[Any, ...], pd.DataFrame] = {}
        self.series: dict[tuple[Any, ...], pd.DataFrame] = {}
        for key, group in observations.groupby(
            ["cluster_price_type", "brand_key", "series_key", "model_year", "trim_key"],
            dropna=False,
            sort=False,
        ):
            self.exact[key] = group.sort_values("knowledge_available_at")
        for key, group in observations.groupby(
            ["cluster_price_type", "brand_key", "series_key", "model_year"],
            dropna=False,
            sort=False,
        ):
            self.series_year[key] = group.sort_values("knowledge_available_at")
        for key, group in observations.groupby(
            ["cluster_price_type", "brand_key", "series_key"],
            dropna=False,
            sort=False,
        ):
            self.series[key] = group.sort_values("knowledge_available_at")

    @staticmethod
    def _prefix_tail(
        frame: pd.DataFrame | None,
        cutoff: pd.Timestamp,
        limit: int,
    ) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        times = frame["knowledge_available_at"].to_numpy(dtype="datetime64[ns]")
        position = int(np.searchsorted(times, np.datetime64(cutoff), side="right"))
        return frame.iloc[max(0, position - limit) : position]

    @staticmethod
    def _level(frame: pd.DataFrame, query: dict[str, Any]) -> pd.Series:
        same_year = pd.to_numeric(frame["model_year"], errors="coerce").eq(
            pd.to_numeric(pd.Series([query.get("model_year")]), errors="coerce").iloc[0]
        )
        candidate_trim_key = (
            frame["canonical_trim_key"]
            if "canonical_trim_key" in frame
            else frame["trim_key"]
        )
        same_trim = candidate_trim_key.fillna("").astype(str).eq(
            str(query.get("canonical_trim_key") or query.get("trim_key") or "")
        )
        same_city = frame["city_key"].fillna("").astype(str).eq(str(query.get("city_key") or ""))
        age_gap = (
            pd.to_numeric(frame["age_years"], errors="coerce") - float(query.get("age_years") or 0)
        ).abs()
        mileage_gap = (
            pd.to_numeric(frame["mileage_wan_km"], errors="coerce")
            - float(query.get("mileage_wan_km") or 0)
        ).abs()
        return pd.Series(
            np.select(
                [
                    same_trim & same_year & same_city & age_gap.le(1.0) & mileage_gap.le(2.0),
                    same_trim & same_year & age_gap.le(1.0) & mileage_gap.le(2.0),
                    same_trim & same_year,
                    same_year & ~same_trim,
                    pd.to_numeric(frame["model_year"], errors="coerce")
                    .sub(float(query.get("model_year") or 0))
                    .abs()
                    .le(2),
                ],
                ["L0", "L1", "L2", "L3", "L4"],
                default="L5",
            ),
            index=frame.index,
        )

    def retrieve(self, query: pd.Series | dict[str, Any], top_k: int = 100) -> pd.DataFrame:
        value = dict(query)
        cutoff = pd.Timestamp(value["prediction_time"])
        query_id = clean_text(value.get("query_id"))
        query_lifecycle_id = clean_text(value.get("lifecycle_id"))
        query_vehicle_id = clean_text(value.get("vehicle_id_hash"))
        query_clue_id = clean_text(value.get("clue_id_hash"))
        query_listing_id = clean_text(value.get("listing_id"))
        pools = []
        for role in ("C2B", "B2C", "EXT_B2C_LISTING"):
            exact_key = (
                role,
                value.get("brand_key"),
                value.get("series_key"),
                value.get("model_year"),
                value.get("trim_key"),
            )
            year_key = (role, value.get("brand_key"), value.get("series_key"), value.get("model_year"))
            series_key = (role, value.get("brand_key"), value.get("series_key"))
            pools.extend(
                [
                    self._prefix_tail(self.exact.get(exact_key), cutoff, 250),
                    self._prefix_tail(self.series_year.get(year_key), cutoff, 300),
                    self._prefix_tail(self.series.get(series_key), cutoff, 600),
                ]
            )
        nonempty_pools = [pool for pool in pools if not pool.empty]
        if not nonempty_pools:
            return pd.DataFrame()
        frame = pd.concat(nonempty_pools, ignore_index=True)
        if frame.empty:
            return frame
        frame = frame.drop_duplicates("observation_id").copy()
        legal = (
            frame["knowledge_available_at"].le(cutoff)
            & frame["event_time"].lt(cutoff)
            & frame["observation_id"].astype(str).ne(query_id)
        )
        if query_lifecycle_id:
            legal &= frame["lifecycle_id"].fillna("").astype(str).ne(query_lifecycle_id)
        if query_vehicle_id:
            legal &= frame["vehicle_id_hash"].fillna("").astype(str).ne(query_vehicle_id)
        if query_clue_id:
            legal &= frame["clue_id_hash"].fillna("").astype(str).ne(query_clue_id)
        if query_listing_id:
            legal &= frame["listing_id"].fillna("").astype(str).ne(query_listing_id)
        frame = frame[legal].copy()
        if frame.empty:
            return frame

        exact_b2c, _ = self.temporal_index.role_frames(value, "B2C")
        bridges = bridge_statistics(self.temporal_index.pair_frame(value), exact_b2c)
        purchase_ratio = bridges["purchase_to_sold_ratio"]
        listing_ratio = bridges["listing_to_sold_ratio"]

        frame = add_v192_12_candidate_similarity(frame, value)
        frame["retrieval_level"] = self._level(frame, value)
        frame["age_difference"] = (
            pd.to_numeric(frame["age_years"], errors="coerce") - float(value.get("age_years") or 0)
        ).abs()
        frame["mileage_difference"] = (
            pd.to_numeric(frame["mileage_wan_km"], errors="coerce")
            - float(value.get("mileage_wan_km") or 0)
        ).abs()
        frame["transfer_difference"] = (
            pd.to_numeric(frame["transfer_count"], errors="coerce")
            - float(value.get("transfer_count") or 0)
        ).abs()
        frame["city_match"] = frame["city_key"].fillna("").astype(str).eq(str(value.get("city_key") or "")).astype(int)
        frame["color_match"] = frame["color_norm"].fillna("").astype(str).eq(str(value.get("color_norm") or "")).astype(int)
        frame["condition_match"] = (
            frame["condition_risk_level"]
            .fillna("")
            .astype(str)
            .eq(str(value.get("condition_risk_level") or ""))
            .astype(int)
        )
        if "normalized_energy_type" in frame:
            candidate_energy_type = frame["normalized_energy_type"].fillna("UNKNOWN").astype(str)
        else:
            candidate_energy_type = pd.Series(
                [
                    normalize_energy_type(
                        row.get("is_new_energy"),
                        brand=row.get("brand"),
                        series=row.get("series"),
                        trim=row.get("trim"),
                        is_new_energy=row.get("is_new_energy"),
                    )["energy_type"]
                    for row in frame.to_dict("records")
                ],
                index=frame.index,
            )
        query_energy_type = str(
            value.get("query_energy_type")
            or normalize_energy_type(
                value.get("is_new_energy"),
                brand=value.get("brand"),
                series=value.get("series"),
                trim=value.get("trim"),
                is_new_energy=value.get("is_new_energy"),
            )["energy_type"]
        )
        frame["candidate_energy_type"] = candidate_energy_type
        frame["candidate_is_new_energy"] = np.where(
            candidate_energy_type.eq("ICE"),
            0,
            np.where(candidate_energy_type.eq("UNKNOWN"), np.nan, 1),
        )
        frame["energy_known_flag"] = (
            candidate_energy_type.ne("UNKNOWN") & (query_energy_type != "UNKNOWN")
        ).astype(int)
        frame["energy_match"] = (
            frame["energy_known_flag"].eq(1)
            & candidate_energy_type.eq(query_energy_type)
        ).astype(int)
        frame["energy_conflict_flag"] = (
            frame["energy_known_flag"].eq(1)
            & candidate_energy_type.ne(query_energy_type)
        ).astype(int)
        query_trim_group = str(value.get("trim_group_key") or "")
        frame["allowed_adjacent_trim"] = (
            frame["same_trim"].eq(1)
            | frame["trim_power_code_match"].eq(1)
            | (
                frame["trim_group_key"].fillna("").astype(str).eq(query_trim_group)
                & bool(query_trim_group)
            )
        ).astype(int)
        frame["same_brand"] = frame["brand_key"].fillna("").astype(str).eq(
            str(value.get("brand_key") or "")
        ).astype(int)
        frame["same_series"] = frame["series_key"].fillna("").astype(str).eq(
            str(value.get("series_key") or "")
        ).astype(int)
        frame["days_since_transaction"] = (
            cutoff - pd.to_datetime(frame["event_time"], errors="coerce")
        ).dt.total_seconds() / 86400.0
        role = frame["cluster_price_type"]
        frame["adjusted_candidate_price"] = np.select(
            [
                role.eq("C2B"),
                role.eq("B2C"),
                role.eq("EXT_B2C_LISTING"),
            ],
            [
                pd.to_numeric(frame["price"], errors="coerce"),
                pd.to_numeric(frame["price"], errors="coerce") * purchase_ratio,
                pd.to_numeric(frame["price"], errors="coerce") / listing_ratio * purchase_ratio,
            ],
            default=np.nan,
        )
        frame["bridge_ratio_used"] = np.select(
            [role.eq("C2B"), role.eq("B2C"), role.eq("EXT_B2C_LISTING")],
            [1.0, purchase_ratio, purchase_ratio / listing_ratio],
            default=np.nan,
        )
        frame["retrieval_level_base"] = frame["retrieval_level"].map(LEVEL_BASE_SCORE).fillna(0.0)
        frame["source_quality"] = frame["cluster_price_type"].map(SOURCE_QUALITY).fillna(0.5)
        frame["time_decay"] = np.exp(-frame["days_since_transaction"].clip(lower=0) / 365.0)
        frame["distance_penalty"] = np.exp(
            -frame["age_difference"].fillna(9) / 2.5
            -frame["mileage_difference"].fillna(99) / 6.0
            -frame["transfer_difference"].fillna(9) / 4.0
        )
        frame["condition_penalty"] = np.where(frame["condition_match"].eq(1), 1.0, 0.78)
        frame["rule_score"] = (
            frame["retrieval_level_base"]
            * frame["source_quality"]
            * frame["time_decay"]
            * frame["distance_penalty"]
            * frame["condition_penalty"]
            * frame["v192_12_semantic_similarity_multiplier"]
            * (1.0 + frame["city_match"] * 0.05 + frame["color_match"] * 0.02)
        )
        frame["invalid_candidate_flag"] = (
            frame["adjusted_candidate_price"].isna()
            | frame["adjusted_candidate_price"].le(0)
            | (
                frame["condition_risk_level"].eq("major_risk")
                & (str(value.get("condition_risk_level") or "") != "major_risk")
            )
        ).astype(int)
        frame["retrieval_exclusion_reason"] = np.where(
            frame["invalid_candidate_flag"].eq(1),
            "invalid_price_or_major_condition_conflict",
            "",
        )
        frame = frame.sort_values(
            [
                "invalid_candidate_flag",
                "same_trim",
                "trim_power_code_match",
                "rule_score",
                "retrieval_level_base",
                "days_since_transaction",
            ],
            ascending=[True, False, False, False, False, True],
            kind="stable",
        )
        # One lifecycle can contribute listing and sold observations. Keep only
        # its strongest representation so it cannot be counted twice.
        frame = frame.drop_duplicates("lifecycle_id", keep="first").head(top_k).copy()
        frame["retrieval_rank"] = np.arange(1, len(frame) + 1)
        frame["query_id"] = query_id
        frame["query_time"] = cutoff
        frame["query_actual_price"] = value.get("actual_price")
        frame["query_brand"] = value.get("brand")
        frame["query_series"] = value.get("series")
        frame["query_model_year"] = value.get("model_year")
        frame["query_trim"] = value.get("trim")
        frame["query_city"] = value.get("city")
        frame["query_color"] = value.get("color_norm")
        frame["query_age_years"] = value.get("age_years")
        frame["query_mileage_wan_km"] = value.get("mileage_wan_km")
        frame["query_transfer_count"] = value.get("transfer_count")
        frame["query_condition"] = value.get("condition_risk_level")
        frame["query_lifecycle_id"] = query_lifecycle_id
        frame["query_vehicle_id"] = query_vehicle_id
        frame["query_clue_id"] = query_clue_id
        frame["query_listing_id"] = query_listing_id
        frame["query_is_new_energy"] = value.get("is_new_energy")
        frame["query_energy_type"] = query_energy_type
        frame["query_canonical_trim_key"] = value.get("canonical_trim_key")
        frame["query_normalized_trim"] = value.get("normalized_trim")
        frame["query_trim_group"] = value.get("trim_group_key")
        frame["candidate_vehicle_id"] = frame["vehicle_id_hash"].fillna("").astype(str)
        frame["candidate_id"] = frame["observation_id"].astype(str)
        frame["source_family"] = frame["source_type"].astype(str)
        frame["transaction_time"] = frame["event_time"]
        frame["candidate_price"] = pd.to_numeric(frame["price"], errors="coerce")
        return frame


class LazyComparableRetriever:
    """On-demand retrieval for full production-sized observation tables.

    The original `ComparableRetriever` eagerly materializes every exact,
    series-year, and series group at process startup. That is fine for offline
    experiments but too heavy for a Hugging Face Space with the full history.
    This class keeps the same scoring and candidate schema while narrowing the
    candidate pool by the query brand/series at request time.
    """

    def __init__(self, observations: pd.DataFrame, role_pairs: pd.DataFrame):
        self.observations = observations.sort_values(
            ["knowledge_available_at", "event_time", "observation_id"],
            kind="stable",
        ).reset_index(drop=True)
        self.role_pairs = role_pairs.sort_values("pair_available_at").reset_index(drop=True)

    @staticmethod
    def _tail(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
        if frame.empty:
            return frame
        return frame.sort_values("knowledge_available_at", kind="stable").tail(limit)

    def _role_pools(self, frame: pd.DataFrame, value: dict[str, Any]) -> list[pd.DataFrame]:
        pools: list[pd.DataFrame] = []
        for role in ("C2B", "B2C", "EXT_B2C_LISTING"):
            role_frame = frame[frame["cluster_price_type"].astype(str).eq(role)]
            if role_frame.empty:
                continue
            trim_column = (
                role_frame["canonical_trim_key"]
                if "canonical_trim_key" in role_frame
                else role_frame["trim_key"]
            )
            query_trim_key = str(
                value.get("canonical_trim_key") or value.get("trim_key") or ""
            )
            exact = role_frame[
                pd.to_numeric(role_frame["model_year"], errors="coerce").eq(
                    float(value.get("model_year") or -1)
                )
                & trim_column.fillna("").astype(str).eq(query_trim_key)
            ]
            year = role_frame[
                pd.to_numeric(role_frame["model_year"], errors="coerce").eq(
                    float(value.get("model_year") or -1)
                )
            ]
            pools.extend(
                [
                    self._tail(exact, 250),
                    self._tail(year, 300),
                    self._tail(role_frame, 600),
                ]
            )
        return pools

    def _pair_frame(self, value: dict[str, Any], cutoff: pd.Timestamp) -> pd.DataFrame:
        if self.role_pairs.empty:
            return self.role_pairs
        frame = self.role_pairs[
            pd.to_datetime(self.role_pairs["pair_available_at"], errors="coerce").le(cutoff)
        ]
        if frame.empty:
            return frame
        exact = frame.copy()
        for column in PARENT_KEYS:
            if column in exact:
                query_value = (
                    value.get("canonical_trim_key")
                    if column == "trim_key" and value.get("canonical_trim_key")
                    else value.get(column)
                )
                exact = exact[
                    exact[column].fillna("").astype(str).eq(
                        str(query_value or "")
                    )
                ]
        if len(exact) >= 8:
            return exact
        same_series = frame[
            frame["brand_key"].fillna("").astype(str).eq(str(value.get("brand_key") or ""))
            & frame["series_key"].fillna("").astype(str).eq(str(value.get("series_key") or ""))
        ]
        if len(same_series) >= 8:
            return same_series
        return frame

    def _exact_b2c(self, value: dict[str, Any], cutoff: pd.Timestamp) -> pd.DataFrame:
        frame = self.observations
        result = frame[
            frame["cluster_price_type"].astype(str).eq("B2C")
            & frame["brand_key"].fillna("").astype(str).eq(str(value.get("brand_key") or ""))
            & frame["series_key"].fillna("").astype(str).eq(str(value.get("series_key") or ""))
            & pd.to_numeric(frame["model_year"], errors="coerce").eq(
                float(value.get("model_year") or -1)
            )
            & (
                frame["canonical_trim_key"]
                if "canonical_trim_key" in frame
                else frame["trim_key"]
            ).fillna("").astype(str).eq(
                str(value.get("canonical_trim_key") or value.get("trim_key") or "")
            )
            & pd.to_datetime(frame["knowledge_available_at"], errors="coerce").le(cutoff)
            & pd.to_datetime(frame["event_time"], errors="coerce").lt(cutoff)
        ]
        return result.copy()

    def retrieve(self, query: pd.Series | dict[str, Any], top_k: int = 100) -> pd.DataFrame:
        value = dict(query)
        cutoff = pd.Timestamp(value["prediction_time"])
        query_id = clean_text(value.get("query_id"))
        query_lifecycle_id = clean_text(value.get("lifecycle_id"))
        query_vehicle_id = clean_text(value.get("vehicle_id_hash"))
        query_clue_id = clean_text(value.get("clue_id_hash"))
        query_listing_id = clean_text(value.get("listing_id"))

        series_pool = self.observations[
            self.observations["brand_key"].fillna("").astype(str).eq(str(value.get("brand_key") or ""))
            & self.observations["series_key"].fillna("").astype(str).eq(str(value.get("series_key") or ""))
            & pd.to_datetime(self.observations["knowledge_available_at"], errors="coerce").le(cutoff)
            & pd.to_datetime(self.observations["event_time"], errors="coerce").lt(cutoff)
        ]
        pools = [pool for pool in self._role_pools(series_pool, value) if not pool.empty]
        if not pools:
            return pd.DataFrame()
        frame = pd.concat(pools, ignore_index=True).drop_duplicates("observation_id").copy()
        if frame.empty:
            return frame

        legal = frame["observation_id"].astype(str).ne(query_id)
        if query_lifecycle_id:
            legal &= frame["lifecycle_id"].fillna("").astype(str).ne(query_lifecycle_id)
        if query_vehicle_id:
            legal &= frame["vehicle_id_hash"].fillna("").astype(str).ne(query_vehicle_id)
        if query_clue_id:
            legal &= frame["clue_id_hash"].fillna("").astype(str).ne(query_clue_id)
        if query_listing_id:
            legal &= frame["listing_id"].fillna("").astype(str).ne(query_listing_id)
        frame = frame[legal].copy()
        if frame.empty:
            return frame

        frame = add_v192_12_candidate_similarity(frame, value)
        exact_b2c = self._exact_b2c(value, cutoff)
        bridges = bridge_statistics(self._pair_frame(value, cutoff), exact_b2c)
        purchase_ratio = bridges["purchase_to_sold_ratio"]
        listing_ratio = bridges["listing_to_sold_ratio"]

        frame["retrieval_level"] = ComparableRetriever._level(frame, value)
        frame["age_difference"] = (
            pd.to_numeric(frame["age_years"], errors="coerce") - float(value.get("age_years") or 0)
        ).abs()
        frame["mileage_difference"] = (
            pd.to_numeric(frame["mileage_wan_km"], errors="coerce")
            - float(value.get("mileage_wan_km") or 0)
        ).abs()
        frame["transfer_difference"] = (
            pd.to_numeric(frame["transfer_count"], errors="coerce")
            - float(value.get("transfer_count") or 0)
        ).abs()
        frame["city_match"] = frame["city_key"].fillna("").astype(str).eq(str(value.get("city_key") or "")).astype(int)
        frame["color_match"] = frame["color_norm"].fillna("").astype(str).eq(str(value.get("color_norm") or "")).astype(int)
        frame["condition_match"] = (
            frame["condition_risk_level"]
            .fillna("")
            .astype(str)
            .eq(str(value.get("condition_risk_level") or ""))
            .astype(int)
        )
        if "normalized_energy_type" in frame:
            candidate_energy_type = frame["normalized_energy_type"].fillna("UNKNOWN").astype(str)
        else:
            candidate_energy_type = pd.Series(
                [
                    normalize_energy_type(
                        row.get("is_new_energy"),
                        brand=row.get("brand"),
                        series=row.get("series"),
                        trim=row.get("trim"),
                        is_new_energy=row.get("is_new_energy"),
                    )["energy_type"]
                    for row in frame.to_dict("records")
                ],
                index=frame.index,
            )
        query_energy_type = str(
            value.get("query_energy_type")
            or normalize_energy_type(
                value.get("is_new_energy"),
                brand=value.get("brand"),
                series=value.get("series"),
                trim=value.get("trim"),
                is_new_energy=value.get("is_new_energy"),
            )["energy_type"]
        )
        frame["candidate_energy_type"] = candidate_energy_type
        frame["candidate_is_new_energy"] = np.where(
            candidate_energy_type.eq("ICE"),
            0,
            np.where(candidate_energy_type.eq("UNKNOWN"), np.nan, 1),
        )
        frame["energy_known_flag"] = (
            candidate_energy_type.ne("UNKNOWN") & (query_energy_type != "UNKNOWN")
        ).astype(int)
        frame["energy_match"] = (
            frame["energy_known_flag"].eq(1) & candidate_energy_type.eq(query_energy_type)
        ).astype(int)
        frame["energy_conflict_flag"] = (
            frame["energy_known_flag"].eq(1) & candidate_energy_type.ne(query_energy_type)
        ).astype(int)
        query_trim_group = str(value.get("trim_group_key") or "")
        frame["allowed_adjacent_trim"] = (
            frame["same_trim"].eq(1)
            | frame["trim_power_code_match"].eq(1)
            | (
                frame["trim_group_key"].fillna("").astype(str).eq(query_trim_group)
                & bool(query_trim_group)
            )
        ).astype(int)
        frame["same_brand"] = frame["brand_key"].fillna("").astype(str).eq(str(value.get("brand_key") or "")).astype(int)
        frame["same_series"] = frame["series_key"].fillna("").astype(str).eq(str(value.get("series_key") or "")).astype(int)
        frame["days_since_transaction"] = (
            cutoff - pd.to_datetime(frame["event_time"], errors="coerce")
        ).dt.total_seconds() / 86400.0
        role = frame["cluster_price_type"].astype(str)
        frame["adjusted_candidate_price"] = np.select(
            [role.eq("C2B"), role.eq("B2C"), role.eq("EXT_B2C_LISTING")],
            [
                pd.to_numeric(frame["price"], errors="coerce"),
                pd.to_numeric(frame["price"], errors="coerce") * purchase_ratio,
                pd.to_numeric(frame["price"], errors="coerce") / listing_ratio * purchase_ratio,
            ],
            default=np.nan,
        )
        frame["bridge_ratio_used"] = np.select(
            [role.eq("C2B"), role.eq("B2C"), role.eq("EXT_B2C_LISTING")],
            [1.0, purchase_ratio, purchase_ratio / listing_ratio],
            default=np.nan,
        )
        frame["retrieval_level_base"] = frame["retrieval_level"].map(LEVEL_BASE_SCORE).fillna(0.0)
        frame["source_quality"] = role.map(SOURCE_QUALITY).fillna(0.5)
        frame["time_decay"] = np.exp(-frame["days_since_transaction"].clip(lower=0) / 365.0)
        frame["distance_penalty"] = np.exp(
            -frame["age_difference"].fillna(9) / 2.5
            -frame["mileage_difference"].fillna(99) / 6.0
            -frame["transfer_difference"].fillna(9) / 4.0
        )
        frame["condition_penalty"] = np.where(frame["condition_match"].eq(1), 1.0, 0.78)
        frame["rule_score"] = (
            frame["retrieval_level_base"]
            * frame["source_quality"]
            * frame["time_decay"]
            * frame["distance_penalty"]
            * frame["condition_penalty"]
            * frame["v192_12_semantic_similarity_multiplier"]
            * (1.0 + frame["city_match"] * 0.05 + frame["color_match"] * 0.02)
        )
        frame["invalid_candidate_flag"] = (
            frame["adjusted_candidate_price"].isna()
            | frame["adjusted_candidate_price"].le(0)
            | (
                frame["condition_risk_level"].astype(str).eq("major_risk")
                & (str(value.get("condition_risk_level") or "") != "major_risk")
            )
        ).astype(int)
        frame["retrieval_exclusion_reason"] = np.where(
            frame["invalid_candidate_flag"].eq(1),
            "invalid_price_or_major_condition_conflict",
            "",
        )
        frame = frame.sort_values(
            [
                "invalid_candidate_flag",
                "same_trim",
                "trim_power_code_match",
                "rule_score",
                "retrieval_level_base",
                "days_since_transaction",
            ],
            ascending=[True, False, False, False, False, True],
            kind="stable",
        )
        frame = frame.drop_duplicates("lifecycle_id", keep="first").head(top_k).copy()
        frame["retrieval_rank"] = np.arange(1, len(frame) + 1)
        frame["query_id"] = query_id
        frame["query_time"] = cutoff
        frame["query_actual_price"] = value.get("actual_price")
        frame["query_brand"] = value.get("brand")
        frame["query_series"] = value.get("series")
        frame["query_model_year"] = value.get("model_year")
        frame["query_trim"] = value.get("trim")
        frame["query_city"] = value.get("city")
        frame["query_color"] = value.get("color_norm")
        frame["query_age_years"] = value.get("age_years")
        frame["query_mileage_wan_km"] = value.get("mileage_wan_km")
        frame["query_transfer_count"] = value.get("transfer_count")
        frame["query_condition"] = value.get("condition_risk_level")
        frame["query_lifecycle_id"] = query_lifecycle_id
        frame["query_vehicle_id"] = query_vehicle_id
        frame["query_clue_id"] = query_clue_id
        frame["query_listing_id"] = query_listing_id
        frame["query_is_new_energy"] = value.get("is_new_energy")
        frame["query_energy_type"] = query_energy_type
        frame["query_canonical_trim_key"] = value.get("canonical_trim_key")
        frame["query_normalized_trim"] = value.get("normalized_trim")
        frame["query_trim_group"] = value.get("trim_group_key")
        frame["candidate_vehicle_id"] = frame["vehicle_id_hash"].fillna("").astype(str)
        frame["candidate_id"] = frame["observation_id"].astype(str)
        frame["source_family"] = frame["source_type"].astype(str)
        frame["transaction_time"] = frame["event_time"]
        frame["candidate_price"] = pd.to_numeric(frame["price"], errors="coerce")
        return frame


def add_offline_labels(candidates: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    actual = pd.to_numeric(result["query_actual_price"], errors="coerce")
    adjusted = pd.to_numeric(result["adjusted_candidate_price"], errors="coerce")
    result["adjusted_candidate_ape"] = (adjusted - actual).abs() / actual.replace(0, np.nan)
    invalid = result["invalid_candidate_flag"].eq(1)
    condition_conflict = (
        result["condition_risk_level"].eq("major_risk")
        & result["query_condition"].fillna("").astype(str).ne("major_risk")
    )
    year_gap = (
        pd.to_numeric(result["model_year"], errors="coerce")
        - pd.to_numeric(result["query_model_year"], errors="coerce")
    ).abs()
    semantic_valid = (
        result["same_brand"].eq(1)
        & result["same_series"].eq(1)
        & result["energy_match"].eq(1)
        & ~condition_conflict
        & result["allowed_adjacent_trim"].eq(1)
        & year_gap.le(1)
        & result["age_difference"].le(2.0)
        & result["mileage_difference"].le(5.0)
    )
    price_close_semantically_invalid = (
        ~semantic_valid & result["adjusted_candidate_ape"].le(0.10) & ~invalid
    )
    result["semantic_valid_flag"] = semantic_valid.astype(int)
    result["semantic_invalid_reason"] = np.select(
        [
            result["same_brand"].ne(1),
            result["same_series"].ne(1),
            result["energy_conflict_flag"].eq(1),
            result["energy_known_flag"].ne(1),
            condition_conflict,
            result["allowed_adjacent_trim"].ne(1),
            year_gap.gt(1),
            result["age_difference"].gt(2.0),
            result["mileage_difference"].gt(5.0),
        ],
        [
            "brand_conflict",
            "series_conflict",
            "energy_type_conflict",
            "energy_type_unknown",
            "major_condition_conflict",
            "trim_not_allowed_by_trim_group",
            "model_year_distance",
            "age_distance",
            "mileage_distance",
        ],
        default="",
    )
    result["comparable_label"] = np.select(
        [
            invalid,
            price_close_semantically_invalid,
            semantic_valid & result["adjusted_candidate_ape"].le(0.05),
            semantic_valid & result["adjusted_candidate_ape"].le(0.10),
            result["adjusted_candidate_ape"].gt(0.15),
        ],
        [
            "INVALID",
            "PRICE_CLOSE_BUT_SEMANTICALLY_INVALID",
            "GOLDEN_COMPARABLE",
            "WEAK_POSITIVE",
            "HARD_NEGATIVE",
        ],
        default="NEUTRAL_10_15",
    )
    result["graded_relevance"] = result["comparable_label"].map(
        {
            "GOLDEN_COMPARABLE": 3,
            "WEAK_POSITIVE": 2,
            "NEUTRAL_10_15": 1,
            "PRICE_CLOSE_BUT_SEMANTICALLY_INVALID": 0,
            "HARD_NEGATIVE": 0,
            "INVALID": 0,
        }
    )
    return result


def retrieval_feature_columns() -> list[str]:
    return [
        "retrieval_rank",
        "retrieval_level_base",
        "rule_score",
        "source_quality",
        "time_decay",
        "distance_penalty",
        "condition_penalty",
        "age_difference",
        "mileage_difference",
        "transfer_difference",
        "city_match",
        "color_match",
        "condition_match",
        "days_since_transaction",
        "bridge_ratio_used",
        "adjusted_candidate_price",
        "query_age_years",
        "query_mileage_wan_km",
        "query_transfer_count",
    ]
