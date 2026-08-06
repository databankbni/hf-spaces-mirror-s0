from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .data import clean_text


CLEAN_LABELS = {"CLEAN_NORMAL_TRANSACTION", "GENUINE_LOW_VALUE_TRANSACTION"}
DIRTY_CANDIDATE_LABELS = {
    "SUSPECT_PLACEHOLDER",
    "SUSPECT_PARTIAL_PAYMENT",
    "SUSPECT_UNIT_ERROR",
    "SUSPECT_PRICE_SEMANTIC",
    "DUPLICATE_LIFECYCLE",
    "CONFLICTING_LIFECYCLE_RECORD",
    "ACCIDENT_OR_RESIDUAL_PRICE",
    "MANUAL_REVIEW_REQUIRED",
}


def _hash(parts: list[Any], prefix: str) -> str:
    raw = "|".join(clean_text(value) for value in parts)
    return prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _norm_text(value: Any) -> str:
    return re.sub(r"[\s\-_（）()款型版]+", "", clean_text(value)).lower()


def price_semantic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    source_file = result["source_file"].fillna("").astype(str)
    price_type = result["price_type"].fillna("").astype(str)
    result["raw_price_field"] = np.select(
        [
            price_type.eq("c2b_purchase_actual") & source_file.str.contains("v52_internal"),
            price_type.eq("c2b_purchase_actual"),
            price_type.eq("b2c_sold_actual") & source_file.str.contains("v52_internal"),
            price_type.eq("b2c_sold_actual"),
            price_type.eq("external_b2c_listing"),
        ],
        [
            "c2b_purchase_price_yuan",
            "收车合同价",
            "b2c_sold_price_yuan",
            "最新订单成交价",
            "挂牌价",
        ],
        default="unknown_price_field",
    )
    result["price_semantic"] = np.select(
        [
            price_type.eq("c2b_purchase_actual"),
            price_type.eq("b2c_sold_actual"),
            price_type.eq("external_b2c_listing"),
        ],
        [
            "FULL_PURCHASE_CONTRACT_PRICE",
            "FINAL_SOLD_ORDER_PRICE",
            "CURRENT_B2C_LISTING_PRICE",
        ],
        default="UNKNOWN_PRICE_SEMANTIC",
    )
    result["raw_price_value"] = pd.to_numeric(result["price"], errors="coerce")
    result["source_table"] = result["source_file"].fillna("").astype(str)
    result["source_record_id"] = result["source_row_id"].fillna("").astype(str)
    return result


class _DisjointSet:
    def __init__(self, size: int):
        self.parent = np.arange(size, dtype=np.int64)
        self.rank = np.zeros(size, dtype=np.int8)

    def find(self, value: int) -> int:
        parent = self.parent
        root = value
        while parent[root] != root:
            root = int(parent[root])
        while parent[value] != value:
            nxt = int(parent[value])
            parent[value] = root
            value = nxt
        return root

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def _union_duplicate_keys(dsu: _DisjointSet, keys: pd.Series) -> None:
    values = keys.fillna("").astype(str).to_numpy()
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    if len(order) < 2:
        return
    duplicate = (sorted_values[1:] == sorted_values[:-1]) & (sorted_values[1:] != "")
    for position in np.flatnonzero(duplicate):
        dsu.union(int(order[position]), int(order[position + 1]))


def canonicalize_lifecycles(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = frame.copy().reset_index(drop=True)
    event_minute = pd.to_datetime(result["event_time"], errors="coerce").dt.floor("min")
    signature_columns = pd.DataFrame(
        {
            "role": result["cluster_price_type"].fillna("").astype(str),
            "brand": result["brand_key"].fillna("").astype(str),
            "series": result["series_key"].fillna("").astype(str),
            "year": pd.to_numeric(result["model_year"], errors="coerce").fillna(-1).round().astype(int),
            "trim": result["trim_key"].fillna("").astype(str),
            "city": result["city_key"].fillna("").astype(str),
            "age": pd.to_numeric(result["age_years"], errors="coerce").round(2).fillna(-1),
            "mileage": pd.to_numeric(result["mileage_wan_km"], errors="coerce").round(2).fillna(-1),
            "transfer": pd.to_numeric(result["transfer_count"], errors="coerce").fillna(-1),
            "event": event_minute.astype(str),
            "price": pd.to_numeric(result["price"], errors="coerce").round(2).fillna(-1),
        }
    )
    result["_event_signature"] = signature_columns.astype(str).agg("|".join, axis=1).map(
        lambda value: _hash([value], "event_")
    )
    dsu = _DisjointSet(len(result))
    for column in ("vehicle_id_hash", "clue_id_hash", "listing_id", "_event_signature"):
        if column in result:
            _union_duplicate_keys(dsu, result[column])
    roots = np.array([dsu.find(index) for index in range(len(result))])
    root_to_id: dict[int, str] = {}
    observation_ids = result["observation_id"].astype(str).to_numpy()
    for root in np.unique(roots):
        members = observation_ids[roots == root]
        root_to_id[int(root)] = _hash([min(members)], "life_")
    result["canonical_lifecycle_id"] = [root_to_id[int(root)] for root in roots]

    role_key = ["canonical_lifecycle_id", "cluster_price_type"]
    result["_field_quality_score"] = (
        result["raw_clean_flag"].fillna(0).astype(float) * 4
        + result["candidate_clean_flag"].fillna(0).astype(float) * 3
        + result["dedup_keep_flag"].fillna(0).astype(float) * 2
        + result["trim_key"].fillna("").astype(str).ne("").astype(int)
        + result["condition_risk_level"].fillna("").astype(str).ne("unknown").astype(int)
    )
    result["_knowledge_order"] = pd.to_datetime(
        result["knowledge_available_at"], errors="coerce"
    )
    result = result.sort_values(
        [*role_key, "_field_quality_score", "_knowledge_order", "observation_id"],
        ascending=[True, True, False, True, True],
        kind="stable",
    )
    result["canonical_record_id"] = result.groupby(role_key)["observation_id"].transform("first")
    result["canonical_keep_flag"] = result["observation_id"].eq(
        result["canonical_record_id"]
    ).astype(int)

    audit_rows = []
    conflict_columns = ["brand_key", "series_key", "model_year", "trim_key", "price"]
    for (lifecycle, role), group in result.groupby(role_key, sort=False):
        conflicts = [
            column
            for column in conflict_columns
            if group[column].dropna().astype(str).nunique() > 1
        ]
        prices = pd.to_numeric(group["price"], errors="coerce").dropna()
        price_conflict = bool(
            len(prices)
            and prices.min() > 0
            and prices.max() / prices.min() > 1.05
        )
        canonical = group.iloc[0]
        audit_rows.append(
            {
                "canonical_lifecycle_id": lifecycle,
                "cluster_price_type": role,
                "canonical_record_id": canonical["canonical_record_id"],
                "merged_record_count": int(len(group)),
                "merged_source_record_ids": json.dumps(
                    group["observation_id"].astype(str).tolist(), ensure_ascii=False
                ),
                "merged_source_files": json.dumps(
                    sorted(group["source_file"].fillna("").astype(str).unique().tolist()),
                    ensure_ascii=False,
                ),
                "field_conflict_flags": "|".join(conflicts),
                "price_conflict_flag": int(price_conflict),
                "canonicalization_reason": (
                    "UNRESOLVED_FIELD_OR_PRICE_CONFLICT"
                    if conflicts or price_conflict
                    else "MERGED_DUPLICATE_SNAPSHOTS"
                    if len(group) > 1
                    else "UNIQUE_LIFECYCLE_RECORD"
                ),
                "canonical_brand": canonical.get("brand"),
                "canonical_series": canonical.get("series"),
                "canonical_model_year": canonical.get("model_year"),
                "canonical_trim": canonical.get("trim"),
                "canonical_price": canonical.get("price"),
                "canonical_event_time": canonical.get("event_time"),
            }
        )
    audit = pd.DataFrame(audit_rows)
    conflict_map = audit.set_index(role_key)[
        ["field_conflict_flags", "price_conflict_flag", "canonicalization_reason"]
    ]
    result = result.merge(conflict_map, left_on=role_key, right_index=True, how="left")
    result = result.sort_index()
    return result.drop(
        columns=["_field_quality_score", "_knowledge_order", "_event_signature"],
        errors="ignore",
    ), audit


def _historical_reference(canonical_c2b: pd.DataFrame) -> pd.DataFrame:
    result = canonical_c2b.sort_values(["event_time", "knowledge_available_at"]).copy()
    exact_keys = ["brand_key", "series_key", "model_year", "trim_key"]
    series_keys = ["brand_key", "series_key", "model_year"]
    result["prior_exact_count"] = result.groupby(exact_keys, dropna=False).cumcount()
    result["prior_series_count"] = result.groupby(series_keys, dropna=False).cumcount()
    result["prior_price_repeat_count"] = result.groupby("price", dropna=False).cumcount()
    result["prior_price_same_series_count"] = result.groupby(
        ["price", "series_key"], dropna=False
    ).cumcount()
    result["prior_unrelated_price_repeat_count"] = (
        result["prior_price_repeat_count"] - result["prior_price_same_series_count"]
    ).clip(lower=0)
    result["prior_exact_median"] = result.groupby(exact_keys, dropna=False)["price"].transform(
        lambda values: values.shift().expanding(min_periods=5).median()
    )
    result["prior_series_median"] = result.groupby(series_keys, dropna=False)["price"].transform(
        lambda values: values.shift().expanding(min_periods=10).median()
    )
    result["prior_market_median"] = result["prior_exact_median"].where(
        result["prior_exact_count"].ge(5), result["prior_series_median"]
    )
    result["actual_to_prior_median_ratio"] = pd.to_numeric(
        result["price"], errors="coerce"
    ) / result["prior_market_median"].replace(0, np.nan)
    return result[
        [
            "observation_id",
            "prior_exact_count",
            "prior_series_count",
            "prior_price_repeat_count",
            "prior_unrelated_price_repeat_count",
            "prior_exact_median",
            "prior_series_median",
            "prior_market_median",
            "actual_to_prior_median_ratio",
        ]
    ]


def attach_guide_price(frame: pd.DataFrame, kb: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    knowledge = kb.copy()
    knowledge["_brand"] = knowledge["canonical_brand"].map(_norm_text)
    knowledge["_series"] = knowledge["canonical_series"].map(_norm_text)
    knowledge["_trim"] = knowledge["trim_normalized"].map(_norm_text)
    knowledge["_year"] = pd.to_numeric(knowledge["model_year"], errors="coerce")
    for column in (
        "official_guide_price_exact",
        "official_guide_price_low",
        "official_guide_price_high",
    ):
        knowledge[column] = pd.to_numeric(knowledge[column], errors="coerce")
    knowledge["guide_price_reference"] = knowledge["official_guide_price_exact"].fillna(
        knowledge[["official_guide_price_low", "official_guide_price_high"]].mean(axis=1)
    )
    knowledge = (
        knowledge.sort_values(
            ["guide_price_confidence", "guide_price_level"],
            ascending=[True, True],
        )
        .drop_duplicates(["_brand", "_series", "_year", "_trim"])
    )
    result["_brand"] = result["brand"].map(_norm_text)
    result["_series"] = result["series"].map(_norm_text)
    result["_trim"] = result["trim"].map(_norm_text)
    result["_year"] = pd.to_numeric(result["model_year"], errors="coerce")
    result = result.merge(
        knowledge[
            [
                "_brand",
                "_series",
                "_year",
                "_trim",
                "guide_price_reference",
                "guide_price_level",
                "guide_price_confidence",
            ]
        ],
        on=["_brand", "_series", "_year", "_trim"],
        how="left",
    )
    return result.drop(columns=["_brand", "_series", "_trim", "_year"])


def label_price_quality(frame: pd.DataFrame, kb: pd.DataFrame) -> pd.DataFrame:
    result = price_semantic_columns(frame)
    canonical_c2b = result[
        result["cluster_price_type"].eq("C2B")
        & result["canonical_keep_flag"].eq(1)
    ].copy()
    historical = _historical_reference(canonical_c2b)
    result = result.merge(historical, on="observation_id", how="left")
    result = attach_guide_price(result, kb)
    price = pd.to_numeric(result["price"], errors="coerce")
    age = pd.to_numeric(result["age_years"], errors="coerce")
    prior = pd.to_numeric(result["prior_market_median"], errors="coerce")
    ratio = price / prior.replace(0, np.nan)
    guide = pd.to_numeric(result["guide_price_reference"], errors="coerce")
    guide_ratio = price / guide.replace(0, np.nan)
    event_time = pd.to_datetime(result["event_time"], errors="coerce")
    knowledge_time = pd.to_datetime(
        result["knowledge_available_at"], errors="coerce"
    )
    identity_invalid = (
        result["brand_key"].fillna("").astype(str).str.strip().eq("")
        | result["series_key"].fillna("").astype(str).str.strip().eq("")
    )
    event_time_invalid = (
        event_time.isna()
        | event_time.lt(pd.Timestamp("1990-01-01"))
        | (
            knowledge_time.notna()
            & event_time.gt(knowledge_time + pd.Timedelta(days=1))
        )
    )
    mileage = pd.to_numeric(result["mileage_wan_km"], errors="coerce")
    transfer = pd.to_numeric(result["transfer_count"], errors="coerce")
    feature_invalid = (
        age.isna()
        | ~age.between(0, 30)
        | mileage.isna()
        | ~mileage.between(0, 80)
        | transfer.isna()
        | ~transfer.between(0, 20)
    )
    incomplete_clean_core_record = (
        identity_invalid | event_time_invalid | feature_invalid
    )
    major_risk = result["condition_risk_level"].eq("major_risk")
    partial_keyword = result["raw_price_field"].str.contains(
        "订金|定金|首付|尾款|贷款|差额|佣金", regex=True, na=False
    )
    semantic_unknown = result["price_semantic"].eq("UNKNOWN_PRICE_SEMANTIC")
    invalid_business_range = price.lt(1_000) | price.gt(2_000_000)
    duplicate = result["canonical_keep_flag"].ne(1)
    lifecycle_conflict = result["canonicalization_reason"].eq(
        "UNRESOLVED_FIELD_OR_PRICE_CONFLICT"
    )
    token_signal = result["is_token_price"].fillna(False).astype(bool)
    repeated_unrelated = result["prior_unrelated_price_repeat_count"].fillna(0).ge(10)
    severe_low = ratio.lt(0.20) & result["prior_series_count"].fillna(0).ge(10)
    guide_severe_low = guide_ratio.lt(0.03) & age.lt(10) & guide.ge(80_000)
    unit_error = (
        price.lt(20_000)
        & prior.gt(50_000)
        & (
            (price.mul(10).sub(prior).abs() / prior).le(0.20)
            | (price.mul(100).sub(prior).abs() / prior).le(0.20)
        )
    )
    plausible_low = (
        price.lt(10_000)
        & ~major_risk
        & (
            prior.le(20_000)
            | (age.ge(12) & ratio.between(0.35, 1.75))
        )
    )
    placeholder = (
        token_signal
        & (repeated_unrelated | severe_low | guide_severe_low)
    )
    suspect_semantic = (
        ~major_risk
        & ~plausible_low
        & (severe_low | guide_severe_low)
    )
    result["price_quality_label"] = np.select(
        [
            duplicate,
            lifecycle_conflict,
            major_risk,
            partial_keyword,
            unit_error,
            placeholder,
            invalid_business_range,
            semantic_unknown,
            incomplete_clean_core_record,
            suspect_semantic,
            plausible_low,
        ],
        [
            "DUPLICATE_LIFECYCLE",
            "CONFLICTING_LIFECYCLE_RECORD",
            "ACCIDENT_OR_RESIDUAL_PRICE",
            "SUSPECT_PARTIAL_PAYMENT",
            "SUSPECT_UNIT_ERROR",
            "SUSPECT_PLACEHOLDER",
            "SUSPECT_PRICE_SEMANTIC",
            "SUSPECT_PRICE_SEMANTIC",
            "MANUAL_REVIEW_REQUIRED",
            "MANUAL_REVIEW_REQUIRED",
            "GENUINE_LOW_VALUE_TRANSACTION",
        ],
        default="CLEAN_NORMAL_TRANSACTION",
    )
    reason_parts = pd.DataFrame(
        {
            "DUPLICATE_SNAPSHOT": duplicate,
            "LIFECYCLE_CONFLICT": lifecycle_conflict,
            "MAJOR_CONDITION_RISK": major_risk,
            "PARTIAL_PAYMENT_FIELD": partial_keyword,
            "UNIT_MULTIPLE_MATCHES_PRIOR": unit_error,
            "TOKEN_AND_CROSS_MODEL_REPEAT": placeholder,
            "INVALID_BUSINESS_PRICE_RANGE": invalid_business_range,
            "UNKNOWN_PRICE_FIELD_SEMANTIC": semantic_unknown,
            "MISSING_BRAND_OR_SERIES": identity_invalid,
            "INVALID_OR_FUTURE_EVENT_TIME": event_time_invalid,
            "MISSING_OR_INVALID_VEHICLE_FEATURE": feature_invalid,
            "PRICE_BELOW_TIME_SAFE_PRIOR": severe_low,
            "PRICE_BELOW_GUIDE_SANITY_MONITOR": guide_severe_low,
            "LOW_VALUE_PLAUSIBLE_BY_HISTORY_OR_AGE": plausible_low,
        }
    )
    result["price_quality_reason_codes"] = reason_parts.apply(
        lambda row: "|".join(row.index[row.to_numpy(dtype=bool)].tolist())
        or "SOURCE_FIELD_CONFIRMED_AND_NO_QUALITY_RULE_TRIGGERED",
        axis=1,
    )
    result["clean_core_flag"] = (
        result["price_quality_label"].isin(CLEAN_LABELS)
        & result["canonical_keep_flag"].eq(1)
        & result["cluster_price_type"].eq("C2B")
        & ~incomplete_clean_core_record
    ).astype(int)
    result["suspect_scope_flag"] = (
        result["cluster_price_type"].eq("C2B")
        & result["clean_core_flag"].ne(1)
    ).astype(int)
    result["candidate_price_eligible_flag"] = (
        result["price_quality_label"].isin(CLEAN_LABELS)
        & result["canonical_keep_flag"].eq(1)
        & ~identity_invalid
        & ~event_time_invalid
    ).astype(int)
    return result


def assign_semantic_tier(candidates: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    year_gap = (
        pd.to_numeric(result["model_year"], errors="coerce")
        - pd.to_numeric(result["query_model_year"], errors="coerce")
    ).abs()
    condition_conflict = (
        result["condition_risk_level"].eq("major_risk")
        & result["query_condition"].fillna("").astype(str).ne("major_risk")
    )
    price_bad = result["candidate_price_eligible_flag"].fillna(0).ne(1)
    duplicate = result["canonical_keep_flag"].fillna(0).ne(1)
    hard_conflict = (
        result["same_brand"].ne(1)
        | result["same_series"].ne(1)
        | result["energy_conflict_flag"].eq(1)
        | condition_conflict
        | price_bad
        | duplicate
    )
    strict_geometry = (
        result["allowed_adjacent_trim"].eq(1)
        & year_gap.le(1)
        & result["age_difference"].le(2.0)
        & result["mileage_difference"].le(5.0)
        & result["transfer_difference"].le(3.0)
    )
    t1 = ~hard_conflict & strict_geometry & result["energy_known_flag"].eq(1)
    t2 = ~hard_conflict & strict_geometry & result["energy_known_flag"].ne(1)
    t3 = (
        ~hard_conflict
        & ~t1
        & ~t2
        & year_gap.le(2)
        & result["age_difference"].le(3.0)
        & result["mileage_difference"].le(8.0)
        & result["transfer_difference"].le(4.0)
        & (
            result["allowed_adjacent_trim"].eq(1)
            | result["retrieval_level"].isin(["L3", "L4"])
        )
    )
    t4 = (
        ~hard_conflict
        & ~t1
        & ~t2
        & ~t3
        & year_gap.le(5)
        & result["age_difference"].le(5.0)
        & result["mileage_difference"].le(15.0)
    )
    result["semantic_candidate_tier"] = np.select(
        [t1, t2, t3, t4],
        [
            "T1_STRICT_COMPARABLE",
            "T2_VALID_WITH_UNKNOWN_ENERGY",
            "T3_CONTROLLED_ADJACENT",
            "T4_LOOSE_FALLBACK",
        ],
        default="INELIGIBLE_SEMANTIC_CONFLICT",
    )
    result["semantic_tier_penalty"] = result["semantic_candidate_tier"].map(
        {
            "T1_STRICT_COMPARABLE": 1.00,
            "T2_VALID_WITH_UNKNOWN_ENERGY": 0.82,
            "T3_CONTROLLED_ADJACENT": 0.62,
            "T4_LOOSE_FALLBACK": 0.30,
            "INELIGIBLE_SEMANTIC_CONFLICT": 0.0,
        }
    )
    result["semantic_exclusion_reason"] = np.select(
        [
            price_bad,
            duplicate,
            result["same_brand"].ne(1),
            result["same_series"].ne(1),
            result["energy_conflict_flag"].eq(1),
            condition_conflict,
            year_gap.gt(5),
            result["age_difference"].gt(5.0),
            result["mileage_difference"].gt(15.0),
        ],
        [
            "candidate_price_quality_not_clean",
            "duplicate_lifecycle_record",
            "brand_conflict",
            "series_conflict",
            "explicit_energy_conflict",
            "major_condition_conflict",
            "model_year_distance_too_large",
            "age_distance_too_large",
            "mileage_distance_too_large",
        ],
        default="",
    )
    return result


@dataclass(frozen=True)
class QualitySummary:
    rows: int
    clean_rows: int
    suspect_rows: int
