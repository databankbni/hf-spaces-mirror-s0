from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .data import clean_text
from .v191_1 import TemporalObservationIndex, bridge_statistics


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
        same_trim = frame["trim_key"].fillna("").astype(str).eq(str(query.get("trim_key") or ""))
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
        frame = frame[
            frame["knowledge_available_at"].le(cutoff)
            & frame["event_time"].lt(cutoff)
            & frame["observation_id"].astype(str).ne(query_id)
        ].copy()
        if frame.empty:
            return frame

        exact_b2c, _ = self.temporal_index.role_frames(value, "B2C")
        bridges = bridge_statistics(self.temporal_index.pair_frame(value), exact_b2c)
        purchase_ratio = bridges["purchase_to_sold_ratio"]
        listing_ratio = bridges["listing_to_sold_ratio"]

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
                "rule_score",
                "retrieval_level_base",
                "days_since_transaction",
            ],
            ascending=[True, False, False, True],
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
    result["comparable_label"] = np.select(
        [
            invalid,
            result["adjusted_candidate_ape"].le(0.05),
            result["adjusted_candidate_ape"].le(0.10),
            result["adjusted_candidate_ape"].gt(0.15),
        ],
        ["invalid", "golden_comparable", "weak_positive", "hard_negative"],
        default="neutral_10_15",
    )
    result["graded_relevance"] = result["comparable_label"].map(
        {
            "golden_comparable": 3,
            "weak_positive": 2,
            "neutral_10_15": 1,
            "hard_negative": 0,
            "invalid": 0,
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
