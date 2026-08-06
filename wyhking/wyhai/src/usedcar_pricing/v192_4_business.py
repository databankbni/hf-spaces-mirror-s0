from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .v192_1_pricing import weighted_quantile


TIER_INDEX = {
    "T1_STRICT_COMPARABLE": 1,
    "T2_VALID_WITH_UNKNOWN_ENERGY": 2,
    "T3A_VERIFIED_ADJACENT": 3,
    "T3B_HEURISTIC_ADJACENT": 4,
    "T4_LOOSE_FALLBACK": 5,
    "INELIGIBLE_SEMANTIC_CONFLICT": 99,
}
TIER_PENALTY = {
    "T1_STRICT_COMPARABLE": 1.00,
    "T2_VALID_WITH_UNKNOWN_ENERGY": 0.82,
    "T3A_VERIFIED_ADJACENT": 0.64,
    "T3B_HEURISTIC_ADJACENT": 0.38,
    "T4_LOOSE_FALLBACK": 0.22,
    "INELIGIBLE_SEMANTIC_CONFLICT": 0.0,
}
SPEC_FIELDS = (
    "energy_type",
    "engine",
    "transmission",
    "drivetrain",
    "body_class",
    "seat_count",
)
CRITICAL_SPEC_FIELDS = (
    "energy_type",
    "engine",
    "transmission",
    "drivetrain",
)
ONLINE_CONFIDENCE_FEATURES = (
    "exact_trim_weight",
    "t3a_verified_weight",
    "t3b_heuristic_weight",
    "t4_fallback_weight",
    "final_selected_candidate_count",
    "candidate_dispersion",
    "evidence_weight_within_30d",
    "evidence_weight_within_90d",
    "evidence_weight_within_180d",
    "same_city_weight",
    "source_family_count",
    "condition_information_complete",
    "energy_information_complete",
    "interval_width_ratio",
    "model_adjustment_abs_ratio",
)


def _known(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "nan", "null", "0"}


def tri_state(left: Any, right: Any) -> str:
    if not _known(left) or not _known(right):
        return "UNKNOWN"
    return "MATCH" if str(left).strip().lower() == str(right).strip().lower() else "CONFLICT"


def classify_trim_relationships(relationships: pd.DataFrame) -> pd.DataFrame:
    result = relationships.copy()
    for field in SPEC_FIELDS:
        result[f"{field}_relation_state"] = [
            tri_state(left, right)
            for left, right in zip(
                result[f"target_{field}"],
                result[f"source_{field}"],
            )
        ]
    state_columns = [f"{field}_relation_state" for field in SPEC_FIELDS]
    critical_columns = [
        f"{field}_relation_state" for field in CRITICAL_SPEC_FIELDS
    ]
    result["spec_match_count"] = result[state_columns].eq("MATCH").sum(axis=1)
    result["spec_conflict_count"] = result[state_columns].eq("CONFLICT").sum(axis=1)
    result["spec_unknown_count"] = result[state_columns].eq("UNKNOWN").sum(axis=1)
    result["critical_spec_conflict_count"] = result[critical_columns].eq(
        "CONFLICT"
    ).sum(axis=1)
    adjacent = result["relationship_type"].isin(
        [
            "SAME_POWERTRAIN_ADJACENT_CONFIG",
            "SAME_GENERATION_ADJACENT_YEAR",
            "SUCCESSOR_PREDECESSOR",
        ]
    )
    explicit_source = result["evidence_source"].eq(
        "STATIC_KB_AND_TRIM_SPEC_COMPARISON"
    )
    t3a = (
        adjacent
        & result["allowed_as_comparable"].eq(1)
        & explicit_source
        & result["spec_conflict_count"].eq(0)
        & result["spec_unknown_count"].le(2)
        & result["spec_match_count"].ge(4)
    )
    t3b = (
        adjacent
        & result["allowed_as_comparable"].eq(1)
        & ~t3a
        & result["critical_spec_conflict_count"].eq(0)
    )
    result["trim_relation_quality"] = np.select(
        [
            result["relationship_type"].eq("EXACT_TRIM"),
            t3a,
            t3b,
            result["critical_spec_conflict_count"].gt(0),
            result["spec_conflict_count"].gt(0),
        ],
        [
            "EXACT",
            "T3A_VERIFIED_ADJACENT",
            "T3B_HEURISTIC_ADJACENT",
            "CRITICAL_SPEC_CONFLICT",
            "NONCRITICAL_SPEC_CONFLICT",
        ],
        default="UNVERIFIED_RELATIONSHIP",
    )
    result["trim_relation_quality_reason"] = np.select(
        [
            result["relationship_type"].eq("EXACT_TRIM"),
            t3a,
            t3b & ~explicit_source,
            t3b & result["spec_unknown_count"].gt(2),
            result["critical_spec_conflict_count"].gt(0),
            result["spec_conflict_count"].gt(0),
        ],
        [
            "EXACT_TRIM_IDENTITY",
            "EXPLICIT_RELATION_WITH_AT_LEAST_FOUR_MATCHED_SPECS",
            "YEAR_OR_TEXT_HEURISTIC_WITHOUT_FULL_STATIC_KB_SUPPORT",
            "EXPLICIT_RELATION_BUT_TOO_MANY_UNKNOWN_SPEC_FIELDS",
            "EXPLICIT_CRITICAL_SPEC_CONFLICT",
            "EXPLICIT_NONCRITICAL_SPEC_CONFLICT",
        ],
        default="NO_VERIFIED_ADJACENT_RELATIONSHIP",
    )
    return result


def assign_candidate_tiers(candidates: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    energy_known = (
        result["query_energy_type"].ne("UNKNOWN")
        & result["candidate_energy_type"].ne("UNKNOWN")
    )
    energy_conflict = (
        energy_known
        & result["query_energy_type"].ne(result["candidate_energy_type"])
    )
    major_condition_conflict = (
        result["condition_risk_level"].eq("major_risk")
        & result["query_condition"].fillna("").ne("major_risk")
    )
    price_bad = result["candidate_price_eligible_flag"].fillna(0).ne(1)
    duplicate = result["canonical_keep_flag"].fillna(0).ne(1)
    critical_spec_conflict = result["critical_spec_conflict_count"].fillna(0).gt(0)
    hard_conflict = (
        result["same_brand"].ne(1)
        | result["same_series"].ne(1)
        | energy_conflict
        | critical_spec_conflict
        | major_condition_conflict
        | price_bad
        | duplicate
    )
    strict_geometry = (
        result["age_difference"].le(2.0)
        & result["mileage_difference"].le(5.0)
        & result["transfer_difference"].le(3.0)
    )
    exact = result["relationship_type"].eq("EXACT_TRIM")
    t1 = ~hard_conflict & exact & strict_geometry & energy_known
    t2 = ~hard_conflict & exact & strict_geometry & ~energy_known
    adjacent_geometry = (
        result["age_difference"].le(3.0)
        & result["mileage_difference"].le(8.0)
        & result["transfer_difference"].le(4.0)
    )
    t3a = (
        ~hard_conflict
        & ~t1
        & ~t2
        & adjacent_geometry
        & result["trim_relation_quality"].eq("T3A_VERIFIED_ADJACENT")
    )
    t3b = (
        ~hard_conflict
        & ~t1
        & ~t2
        & ~t3a
        & adjacent_geometry
        & result["trim_relation_quality"].eq("T3B_HEURISTIC_ADJACENT")
    )
    year_gap = (
        pd.to_numeric(result["query_model_year"], errors="coerce")
        - pd.to_numeric(result["model_year"], errors="coerce")
    ).abs()
    t4 = (
        ~hard_conflict
        & ~t1
        & ~t2
        & ~t3a
        & ~t3b
        & year_gap.le(5)
        & result["age_difference"].le(5.0)
        & result["mileage_difference"].le(15.0)
    )
    result["semantic_candidate_tier_v192_4"] = np.select(
        [t1, t2, t3a, t3b, t4],
        [
            "T1_STRICT_COMPARABLE",
            "T2_VALID_WITH_UNKNOWN_ENERGY",
            "T3A_VERIFIED_ADJACENT",
            "T3B_HEURISTIC_ADJACENT",
            "T4_LOOSE_FALLBACK",
        ],
        default="INELIGIBLE_SEMANTIC_CONFLICT",
    )
    result["semantic_tier_penalty_v192_4"] = result[
        "semantic_candidate_tier_v192_4"
    ].map(TIER_PENALTY)
    result["semantic_exclusion_reason_v192_4"] = np.select(
        [
            price_bad,
            duplicate,
            result["same_brand"].ne(1),
            result["same_series"].ne(1),
            energy_conflict,
            critical_spec_conflict,
            major_condition_conflict,
            year_gap.gt(5),
            result["age_difference"].gt(5.0),
            result["mileage_difference"].gt(15.0),
        ],
        [
            "candidate_price_quality_not_eligible",
            "duplicate_lifecycle_record",
            "brand_conflict",
            "series_conflict",
            "explicit_energy_conflict",
            "explicit_critical_spec_conflict",
            "major_condition_conflict",
            "model_year_distance_too_large",
            "age_distance_too_large",
            "mileage_distance_too_large",
        ],
        default="",
    )
    return result


def _compute_weights(group: pd.DataFrame) -> pd.DataFrame:
    result = group.copy()
    score = pd.to_numeric(result["ranker_score"], errors="coerce").fillna(-999)
    ranker_weight = np.exp(np.clip(score - score.max(), -20, 0))
    prices = pd.to_numeric(
        result["adjusted_candidate_price"], errors="coerce"
    ).to_numpy()
    log_price = np.log(np.clip(prices, 1, None))
    center = np.nanmedian(log_price)
    mad = np.nanmedian(np.abs(log_price - center))
    scale = max(float(mad) * 1.4826, 0.03)
    outlier_penalty = np.exp(
        -np.maximum(np.abs(log_price - center) / scale - 2.5, 0)
    )
    raw = (
        ranker_weight.to_numpy()
        * pd.to_numeric(result["time_decay"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["source_quality"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["retrieval_level_base"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["distance_penalty"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["semantic_tier_penalty_v192_4"], errors="coerce").fillna(0).to_numpy()
        * outlier_penalty
    )
    if raw.sum() <= 0:
        raw = np.ones(len(result), dtype=float)
    result["ranker_weight_v192_4"] = ranker_weight.to_numpy()
    result["outlier_penalty_v192_4"] = outlier_penalty
    result["raw_pricing_weight_v192_4"] = raw
    result["final_normalized_weight_v192_4"] = raw / raw.sum()
    return result


def _baseline_subset(display: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    strict = display[display["_tier_index_v192_4"].le(3)].copy()
    if not strict.empty:
        return strict, "STRICT_T1_T2_T3A_BASELINE_ALLOW_FEWER_THAN_TOP10"
    t3b = display[display["_tier_index_v192_4"].eq(4)].copy()
    if not t3b.empty:
        return t3b.head(min(3, len(t3b))), "T3B_LOW_WEIGHT_BASELINE_NO_STRICT"
    loose = display[display["_tier_index_v192_4"].eq(5)].copy()
    if not loose.empty:
        return loose.head(1), "T4_MANUAL_REFERENCE_ONLY_NO_STRICT"
    return display.head(0).copy(), "NO_ELIGIBLE_BASELINE"


def baseline_candidates(selected: pd.DataFrame) -> pd.DataFrame:
    if selected.empty:
        return selected
    if "used_for_statistical_baseline_v192_12" not in selected:
        return selected
    baseline = selected[
        selected["used_for_statistical_baseline_v192_12"].eq(1)
    ].copy()
    return baseline if not baseline.empty else selected.head(0).copy()


def select_final_candidates(
    candidates: pd.DataFrame, top_k: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = candidates.copy()
    result["_tier_index_v192_4"] = result[
        "semantic_candidate_tier_v192_4"
    ].map(TIER_INDEX).fillna(99)
    result["final_selected_for_pricing_v192_4"] = 0
    result["used_for_statistical_baseline_v192_12"] = 0
    result["candidate_business_role_v192_12"] = "NOT_SELECTED"
    result["final_pricing_rank_v192_12"] = np.nan
    result["retrieval_stage_rank_v192_12"] = result.get("retrieval_rank", np.nan)
    result["final_normalized_weight_v192_4"] = 0.0
    result["final_accept_reason_codes_v192_4"] = ""
    result["final_reject_reason_codes_v192_4"] = ""
    summaries: list[dict[str, Any]] = []
    selected_parts: list[pd.DataFrame] = []
    for query_id, group in result.groupby("query_id", sort=False):
        eligible = group[group["_tier_index_v192_4"].le(5)].sort_values(
            ["_tier_index_v192_4", "ranker_score", "days_since_transaction"],
            ascending=[True, False, True],
            kind="stable",
        )
        strict = eligible[eligible["_tier_index_v192_4"].le(3)]
        selected = eligible.head(top_k).copy()
        baseline, mode = _baseline_subset(selected)
        if not selected.empty:
            selected["used_for_statistical_baseline_v192_12"] = 0
            selected["candidate_business_role_v192_12"] = "MANUAL_REFERENCE"
            if not baseline.empty:
                baseline = _compute_weights(baseline)
                selected.loc[
                    baseline.index, "used_for_statistical_baseline_v192_12"
                ] = 1
                selected.loc[
                    baseline.index, "candidate_business_role_v192_12"
                ] = "BASELINE_POINT_PRICE"
                selected.loc[
                    baseline.index, "final_normalized_weight_v192_4"
                ] = baseline["final_normalized_weight_v192_4"]
            selected.loc[
                selected["candidate_business_role_v192_12"].eq("MANUAL_REFERENCE")
                & selected["_tier_index_v192_4"].isin([3, 4, 5]),
                "candidate_business_role_v192_12",
            ] = "INTERVAL_OR_MANUAL_REFERENCE"
            selected["final_pricing_rank_v192_12"] = np.arange(1, len(selected) + 1)
            selected_parts.append(selected)
            indices = selected.index
            result.loc[indices, "final_selected_for_pricing_v192_4"] = 1
            result.loc[
                indices, "used_for_statistical_baseline_v192_12"
            ] = selected["used_for_statistical_baseline_v192_12"]
            result.loc[
                indices, "candidate_business_role_v192_12"
            ] = selected["candidate_business_role_v192_12"]
            result.loc[
                indices, "final_pricing_rank_v192_12"
            ] = selected["final_pricing_rank_v192_12"]
            result.loc[indices, "final_normalized_weight_v192_4"] = selected[
                "final_normalized_weight_v192_4"
            ]
            tier_reason = {
                "T1_STRICT_COMPARABLE": "EXACT_TRIM",
                "T2_VALID_WITH_UNKNOWN_ENERGY": "ENERGY_UNKNOWN_OTHERWISE_STRICT",
                "T3A_VERIFIED_ADJACENT": "VERIFIED_ADJACENT_RELATION",
                "T3B_HEURISTIC_ADJACENT": "HEURISTIC_ADJACENT_FALLBACK",
                "T4_LOOSE_FALLBACK": "LOOSE_FALLBACK_INSUFFICIENT_STRICT_COUNT",
            }
            accept = selected.apply(
                lambda row: "|".join(
                    [
                        "FINAL_TOPK_BY_V192_4_SEMANTIC_TIER_AND_RANKER",
                        tier_reason[row["semantic_candidate_tier_v192_4"]],
                        "SAME_CITY" if row["city_match"] == 1 else "NATIONAL_EVIDENCE",
                        "WITHIN_90D"
                        if row["days_since_transaction"] <= 90
                        else "OLDER_THAN_90D",
                        row.get("candidate_business_role_v192_12", ""),
                    ]
                ),
                axis=1,
            )
            result.loc[indices, "final_accept_reason_codes_v192_4"] = accept
        baseline_indices = baseline.index if not baseline.empty else pd.Index([])
        not_selected = group.index.difference(selected.index)
        result.loc[not_selected, "final_reject_reason_codes_v192_4"] = result.loc[
            not_selected
        ].apply(
            lambda row: (
                row["semantic_exclusion_reason_v192_4"]
                if row["_tier_index_v192_4"] > 5
                else "T3B_T4_NOT_USED_FOR_POINT_BASELINE"
                if row["_tier_index_v192_4"] >= 4
                and mode == "STRICT_T1_T2_T3A_BASELINE_ALLOW_FEWER_THAN_TOP10"
                else "BELOW_FINAL_TOPK_CUTOFF"
            ),
            axis=1,
        )
        display_not_baseline = selected.index.difference(baseline_indices)
        result.loc[
            display_not_baseline,
            "final_reject_reason_codes_v192_4",
        ] = "DISPLAYED_AS_INTERVAL_OR_MANUAL_REFERENCE_NOT_POINT_BASELINE"
        weight_sum = result.loc[
            group.index, "final_normalized_weight_v192_4"
        ].sum()
        summaries.append(
            {
                "query_id": query_id,
                "candidate_rows": len(group),
                "eligible_rows": len(eligible),
                "strict_rows": len(strict),
                "baseline_rows_v192_12": int(
                    result.loc[
                        group.index, "used_for_statistical_baseline_v192_12"
                    ].sum()
                ),
                "display_rows_v192_12": int(
                    result.loc[
                        group.index, "final_selected_for_pricing_v192_4"
                    ].sum()
                ),
                "final_selected_rows": int(
                    result.loc[
                        group.index, "final_selected_for_pricing_v192_4"
                    ].sum()
                ),
                "final_weight_sum": float(weight_sum),
                "selection_mode_v192_4": mode,
                "rejected_positive_weight_count": int(
                    (
                        result.loc[
                            group.index, "final_selected_for_pricing_v192_4"
                        ].eq(0)
                        & result.loc[
                            group.index, "final_normalized_weight_v192_4"
                        ].gt(0)
                    ).sum()
                ),
                "selected_missing_accept_reason_count": int(
                    (
                        result.loc[
                            group.index, "final_selected_for_pricing_v192_4"
                        ].eq(1)
                        & result.loc[
                            group.index, "final_accept_reason_codes_v192_4"
                        ].eq("")
                    ).sum()
                ),
                "weight_sum_pass": int(
                    abs(weight_sum - 1.0) <= 1e-9
                    if len(selected)
                    else weight_sum == 0
                ),
            }
        )
    selected_frame = (
        pd.concat(selected_parts, ignore_index=True)
        if selected_parts
        else pd.DataFrame()
    )
    return result, pd.DataFrame(summaries)


def selected_query_statistics(selected: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for query_id, group in selected.groupby("query_id", sort=False):
        display_group = group
        group = baseline_candidates(group)
        if group.empty:
            continue
        prices = pd.to_numeric(
            group["adjusted_candidate_price"], errors="coerce"
        ).to_numpy()
        weights = pd.to_numeric(
            group["final_normalized_weight_v192_4"], errors="coerce"
        ).to_numpy()
        quantiles = {
            f"candidate_price_p{int(q * 100)}": weighted_quantile(
                prices, weights, q
            )
            for q in (0.10, 0.25, 0.40, 0.50, 0.75, 0.90)
        }
        metadata = group.iloc[0]

        def weight_of(tier: str) -> float:
            return float(
                group.loc[
                    group["semantic_candidate_tier_v192_4"].eq(tier),
                    "final_normalized_weight_v192_4",
                ].sum()
            )

        tier_sorted = group.sort_values("_tier_index_v192_4")
        max_tier_v192_4 = tier_sorted[
            "semantic_candidate_tier_v192_4"
        ].iloc[-1]
        model_tier = {
            "T3A_VERIFIED_ADJACENT": "T3_CONTROLLED_ADJACENT",
            "T3B_HEURISTIC_ADJACENT": "T3_CONTROLLED_ADJACENT",
        }.get(max_tier_v192_4, max_tier_v192_4)
        rows.append(
            {
                "query_id": query_id,
                "query_time": metadata["query_time"],
                "actual_price": metadata["query_actual_price"],
                "brand": metadata["query_brand"],
                "series": metadata["query_series"],
                "model_year": metadata["query_model_year"],
                "trim": metadata["query_trim"],
                "city": metadata["query_city"],
                "color": metadata["query_color"],
                "age_years": metadata["query_age_years"],
                "mileage_wan_km": metadata["query_mileage_wan_km"],
                "transfer_count": metadata["query_transfer_count"],
                "condition_risk_level": metadata["query_condition"],
                "query_energy_type": metadata["query_energy_type"],
                "pricing_candidate_count": len(group),
                "display_candidate_count_v192_12": len(display_group),
                **quantiles,
                "candidate_dispersion": (
                    (quantiles["candidate_price_p75"] - quantiles["candidate_price_p25"])
                    / max(quantiles["candidate_price_p50"], 1)
                ),
                "statistical_baseline_price": quantiles[
                    "candidate_price_p40"
                ],
                "latest_candidate_days": float(
                    group["days_since_transaction"].min()
                ),
                "source_family_count": int(
                    group["source_family"].nunique(dropna=True)
                ),
                "same_trim_candidate_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .isin(["T1_STRICT_COMPARABLE", "T2_VALID_WITH_UNKNOWN_ENERGY"])
                    .sum()
                ),
                "same_trim_weight": (
                    weight_of("T1_STRICT_COMPARABLE")
                    + weight_of("T2_VALID_WITH_UNKNOWN_ENERGY")
                ),
                "exact_energy_confirmed_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T1_STRICT_COMPARABLE")
                    .sum()
                ),
                "exact_energy_confirmed_weight": weight_of("T1_STRICT_COMPARABLE"),
                "exact_energy_unknown_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T2_VALID_WITH_UNKNOWN_ENERGY")
                    .sum()
                ),
                "exact_energy_unknown_weight": weight_of(
                    "T2_VALID_WITH_UNKNOWN_ENERGY"
                ),
                "exact_candidate_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T1_STRICT_COMPARABLE")
                    .sum()
                ),
                "best_retrieval_level": tier_sorted[
                    "retrieval_level"
                ].iloc[0],
                "max_semantic_tier_v192_4": max_tier_v192_4,
                "max_semantic_tier": model_tier,
                "strict_semantic_weight": (
                    weight_of("T1_STRICT_COMPARABLE")
                    + weight_of("T2_VALID_WITH_UNKNOWN_ENERGY")
                    + weight_of("T3A_VERIFIED_ADJACENT")
                ),
                "exact_trim_weight": weight_of("T1_STRICT_COMPARABLE"),
                "unknown_energy_strict_weight": weight_of(
                    "T2_VALID_WITH_UNKNOWN_ENERGY"
                ),
                "t3a_verified_weight": weight_of("T3A_VERIFIED_ADJACENT"),
                "t3b_heuristic_weight": weight_of("T3B_HEURISTIC_ADJACENT"),
                "t4_fallback_weight": weight_of("T4_LOOSE_FALLBACK"),
            }
        )
    return pd.DataFrame(rows)


def add_evidence_features(
    trace: pd.DataFrame, selected: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for query_id, raw_group in selected.groupby("query_id", sort=False):
        group = baseline_candidates(raw_group)
        if group.empty:
            group = raw_group.head(0).copy()
        weight = pd.to_numeric(
            group["final_normalized_weight_v192_4"], errors="coerce"
        ).fillna(0)

        def weighted(mask: pd.Series) -> float:
            return float(weight[mask].sum())

        rows.append(
            {
                "query_id": query_id,
                "final_selected_candidate_count": len(group),
                "display_candidate_count_v192_12": len(raw_group),
                "evidence_weight_within_30d": weighted(
                    group["days_since_transaction"].le(30)
                ),
                "evidence_weight_within_90d": weighted(
                    group["days_since_transaction"].le(90)
                ),
                "evidence_weight_within_180d": weighted(
                    group["days_since_transaction"].le(180)
                ),
                "same_city_weight": weighted(group["city_match"].eq(1)),
                "internal_c2b_weight": weighted(
                    group["cluster_price_type"].eq("C2B")
                ),
                "internal_b2c_weight": weighted(
                    group["cluster_price_type"].eq("B2C")
                ),
                "external_listing_weight": weighted(
                    group["cluster_price_type"].eq("EXT_B2C_LISTING")
                ),
                "exact_trim_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T1_STRICT_COMPARABLE")
                    .sum()
                ),
                "t3a_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T3A_VERIFIED_ADJACENT")
                    .sum()
                ),
                "t3b_count": int(
                    group["semantic_candidate_tier_v192_4"]
                    .eq("T3B_HEURISTIC_ADJACENT")
                    .sum()
                ),
                "same_city_count": int(group["city_match"].eq(1).sum()),
                "within_90d_count": int(
                    group["days_since_transaction"].le(90).sum()
                ),
                "spec_unknown_weight": float(
                    (
                        weight
                        * group["spec_unknown_count"].fillna(6).div(6)
                    ).sum()
                ),
            }
        )
    return trace.merge(pd.DataFrame(rows), on="query_id", how="left")


def compute_quote_evidence_confidence(trace: pd.DataFrame) -> pd.DataFrame:
    result = trace.copy()
    result["condition_information_complete"] = result[
        "condition_risk_level"
    ].isin(["clean", "minor_defect", "major_risk"]).astype(int)
    result["energy_information_complete"] = result[
        "query_energy_type"
    ].isin(["ICE", "HEV", "PHEV", "BEV", "EREV"]).astype(int)
    result["model_adjustment_abs_ratio"] = result[
        "base_residual_clipped_adjustment"
    ].fillna(0).abs()
    no_quote = result["raw_price_before_guard"].isna()
    manual = (
        no_quote
        | result["final_selected_candidate_count"].fillna(0).lt(2)
        | result["candidate_dispersion"].fillna(np.inf).gt(0.65)
        | result["t4_fallback_weight"].fillna(0).gt(0.50)
    )
    fallback_weight = (
        result["t3b_heuristic_weight"].fillna(0)
        + result["t4_fallback_weight"].fillna(0)
    )
    fallback_too_heavy = fallback_weight.gt(0.12)
    high = (
        ~manual
        & ~fallback_too_heavy
        & result["final_selected_candidate_count"].ge(8)
        & (
            result["exact_trim_weight"]
            + result["t3a_verified_weight"]
        ).ge(0.85)
        & result["exact_trim_weight"].ge(0.45)
        & result["candidate_dispersion"].le(0.15)
        & result["evidence_weight_within_90d"].ge(0.60)
        & result["source_family_count"].ge(2)
        & result["same_city_weight"].ge(0.10)
        & result["condition_information_complete"].eq(1)
        & result["energy_information_complete"].eq(1)
        & result["model_adjustment_abs_ratio"].le(0.05)
    )
    medium = (
        ~manual
        & ~fallback_too_heavy
        & ~high
        & result["final_selected_candidate_count"].ge(5)
        & (
            result["exact_trim_weight"]
            + result["t3a_verified_weight"]
        ).ge(0.70)
        & result["candidate_dispersion"].le(0.25)
        & result["evidence_weight_within_180d"].ge(0.60)
        & result["energy_information_complete"].eq(1)
        & result["model_adjustment_abs_ratio"].le(0.10)
    )
    result["quote_evidence_confidence_pre_interval"] = np.select(
        [manual, high, medium],
        ["MANUAL", "HIGH", "MEDIUM"],
        default="LOW",
    )
    result["quote_evidence_confidence_reason"] = result.apply(
        _confidence_reason, axis=1
    )
    return result


def _confidence_reason(row: pd.Series) -> str:
    reasons = []
    if pd.isna(row.get("raw_price_before_guard")):
        reasons.append("NO_PRICE")
    if row.get("final_selected_candidate_count", 0) < 5:
        reasons.append("LIMITED_CANDIDATE_COUNT")
    if row.get("candidate_dispersion", np.inf) > 0.25:
        reasons.append("HIGH_CANDIDATE_DISPERSION")
    if row.get("t3b_heuristic_weight", 0) > 0.12:
        reasons.append("USES_T3B_HEURISTIC")
    if row.get("t4_fallback_weight", 0) > 0.08:
        reasons.append("USES_T4_FALLBACK")
    if row.get("same_city_weight", 0) < 0.10:
        reasons.append("LIMITED_SAME_CITY_EVIDENCE")
    if row.get("evidence_weight_within_90d", 0) < 0.60:
        reasons.append("LIMITED_RECENT_EVIDENCE")
    if row.get("source_family_count", 0) < 2:
        reasons.append("SINGLE_SOURCE_FAMILY")
    if row.get("condition_information_complete", 0) == 0:
        reasons.append("CONDITION_INFORMATION_INCOMPLETE")
    if row.get("energy_information_complete", 0) == 0:
        reasons.append("ENERGY_INFORMATION_INCOMPLETE")
    return "|".join(reasons) if reasons else "STRONG_ONLINE_EVIDENCE"


def build_business_intervals(trace: pd.DataFrame) -> pd.DataFrame:
    result = trace.copy()
    price = result["raw_price_before_guard"]
    dispersion = result["candidate_dispersion"].fillna(0.60).clip(0, 1.5)
    model_adjustment = result["model_adjustment_abs_ratio"].fillna(0)
    proposed_width = np.maximum(
        0.08,
        np.maximum(1.10 * dispersion, 1.20 * model_adjustment),
    )
    low_price = price.lt(30_000)
    absolute_width = np.where(
        price.lt(10_000),
        3_000 / price.clip(lower=1),
        np.where(price.lt(20_000), 4_000 / price.clip(lower=1), 5_000 / price.clip(lower=1)),
    )
    proportional_width = proposed_width
    mixed_width = np.where(
        low_price,
        np.maximum(np.minimum(absolute_width, 0.30), proportional_width),
        proportional_width,
    )
    result["interval_candidate_absolute_width_ratio"] = absolute_width
    result["interval_candidate_proportional_width_ratio"] = proportional_width
    result["interval_candidate_mixed_width_ratio"] = mixed_width
    confidence = result["quote_evidence_confidence_pre_interval"].copy()
    high_too_wide = confidence.eq("HIGH") & (mixed_width > 0.15)
    confidence.loc[high_too_wide] = "MEDIUM"
    medium_too_wide = confidence.eq("MEDIUM") & (mixed_width > 0.25)
    confidence.loc[medium_too_wide] = "LOW"
    price_outside_p10_p90 = ~price.between(
        result["candidate_price_p10"], result["candidate_price_p90"]
    )
    high_outside_p25_p75 = confidence.eq("HIGH") & ~price.between(
        result["candidate_price_p25"], result["candidate_price_p75"]
    )
    confidence.loc[high_outside_p25_p75] = "MEDIUM"
    confidence.loc[price_outside_p10_p90 & price.notna()] = "LOW"
    result["interval_confidence_downgrade_reason"] = np.select(
        [
            price_outside_p10_p90 & price.notna(),
            high_outside_p25_p75,
            high_too_wide,
            medium_too_wide,
        ],
        [
            "FINAL_PRICE_OUTSIDE_CANDIDATE_P10_P90",
            "HIGH_PRICE_OUTSIDE_CANDIDATE_P25_P75",
            "HIGH_INTERVAL_REQUIRED_WIDTH_EXCEEDS_15_PERCENT",
            "MEDIUM_INTERVAL_REQUIRED_WIDTH_EXCEEDS_25_PERCENT",
        ],
        default="",
    )
    result["quote_evidence_confidence"] = confidence
    auto = confidence.isin(["HIGH", "MEDIUM"]) & price.notna()
    max_width = confidence.map(
        {"HIGH": 0.15, "MEDIUM": 0.25}
    ).fillna(np.inf)
    auto_width = np.minimum(mixed_width, max_width)
    evidence_low = result["candidate_price_p10"]
    evidence_high = result["candidate_price_p90"]
    fallback_half = np.maximum(mixed_width / 2, 0.15)
    result["interval_type"] = np.where(
        auto, "AUTO_QUOTE_INTERVAL", "EVIDENCE_REFERENCE_RANGE"
    )
    result["interval_method"] = np.where(
        auto & low_price,
        "MIXED_ABSOLUTE_AND_PROPORTIONAL",
        np.where(auto, "PROPORTIONAL_EVIDENCE_CALIBRATED", "CANDIDATE_P10_P90"),
    )
    result["business_interval_low"] = np.where(
        auto,
        price * (1 - auto_width / 2),
        evidence_low.fillna(price * (1 - fallback_half)),
    )
    result["business_interval_high"] = np.where(
        auto,
        price * (1 + auto_width / 2),
        evidence_high.fillna(price * (1 + fallback_half)),
    )
    result["business_interval_low"] = result[
        "business_interval_low"
    ].clip(lower=0)
    result["business_interval_width_ratio"] = (
        result["business_interval_high"] - result["business_interval_low"]
    ) / price
    result["interval_display_label"] = np.where(
        auto, "合理报价区间", "证据参考范围"
    )
    return result


def apply_serving_guard(
    raw_price: float,
    raw_confidence: str,
    *,
    reference_price: float | None = None,
    reference_confidence: str | None = None,
    age_increased: bool = False,
    mileage_increased: bool = False,
    transfer_increased: bool = False,
    condition_worsened: bool = False,
    evidence_weakened: bool = False,
) -> dict[str, Any]:
    if raw_price is None or not np.isfinite(raw_price):
        return {
            "raw_price_before_guard": None,
            "guard_rule": "NO_QUOTE",
            "guard_triggered": False,
            "guard_adjustment": 0.0,
            "final_price_after_guard": None,
            "quote_evidence_confidence_after_guard": "MANUAL",
        }
    final = float(raw_price)
    rules = []
    if reference_price is not None and np.isfinite(reference_price):
        cap = float(reference_price)
        if mileage_increased and not age_increased:
            cap = min(cap, float(reference_price))
        if transfer_increased:
            cap = min(cap, float(reference_price) * 0.995)
        if condition_worsened:
            cap = min(cap, float(reference_price) * 0.98)
        if age_increased or mileage_increased or transfer_increased or condition_worsened:
            if final > cap:
                final = cap
                rules.append("DETERIORATION_MONOTONIC_PRICE_CAP")
    confidence_order = {"MANUAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    confidence = raw_confidence
    if evidence_weakened and reference_confidence:
        if confidence_order.get(confidence, 0) > confidence_order.get(
            reference_confidence, 0
        ):
            confidence = reference_confidence
            rules.append("WEAKER_EVIDENCE_CONFIDENCE_CAP")
    return {
        "raw_price_before_guard": float(raw_price),
        "guard_rule": "|".join(rules) if rules else "NO_GUARD_TRIGGERED",
        "guard_triggered": bool(rules),
        "guard_adjustment": final - float(raw_price),
        "final_price_after_guard": final,
        "quote_evidence_confidence_after_guard": confidence,
    }


def evaluation_target_quality(label: Any) -> str:
    text = str(label or "")
    if text in {"VERIFIED_NORMAL_TRANSACTION", "VERIFIED_SPECIAL_LOW_VALUE"}:
        return "SOURCE_FIELD_CONFIRMED"
    if text in {"PLAUSIBLE_UNVERIFIED", "PLAUSIBLE_LOW_VALUE_UNVERIFIED"}:
        return "PLAUSIBLE_UNVERIFIED"
    if text == "SPECIAL_CONDITION_OR_RESIDUAL":
        return "SPECIAL_CONDITION"
    if text in {
        "SUSPECT_PRICE_SEMANTIC",
        "SUSPECT_PARTIAL_PAYMENT",
        "SUSPECT_PLACEHOLDER",
        "SUSPECT_UNIT_ERROR",
        "MANUAL_REVIEW_REQUIRED",
    }:
        return "SUSPECT_PRICE"
    return "PLAUSIBLE_UNVERIFIED"
