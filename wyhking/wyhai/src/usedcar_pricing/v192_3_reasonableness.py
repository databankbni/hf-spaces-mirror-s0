from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd

from .data import clean_text
from .v192_1_pricing import weighted_quantile


ENERGY_TYPES = {"ICE", "HEV", "PHEV", "BEV", "EREV", "UNKNOWN"}
TIER_INDEX = {
    "T1_STRICT_COMPARABLE": 1,
    "T2_VALID_WITH_UNKNOWN_ENERGY": 2,
    "T3_CONTROLLED_ADJACENT": 3,
    "T4_LOOSE_FALLBACK": 4,
    "INELIGIBLE_SEMANTIC_CONFLICT": 99,
}
TIER_PENALTY = {
    "T1_STRICT_COMPARABLE": 1.00,
    "T2_VALID_WITH_UNKNOWN_ENERGY": 0.82,
    "T3_CONTROLLED_ADJACENT": 0.62,
    "T4_LOOSE_FALLBACK": 0.30,
    "INELIGIBLE_SEMANTIC_CONFLICT": 0.0,
}


def normalize_text(value: Any) -> str:
    return re.sub(r"[\s\-_（）()款型版]+", "", clean_text(value)).lower()


def normalize_energy(value: Any) -> str:
    text = clean_text(value).upper()
    aliases = {
        "ICE": "ICE",
        "燃油": "ICE",
        "汽油": "ICE",
        "柴油": "ICE",
        "FUEL": "ICE",
        "BEV": "BEV",
        "纯电": "BEV",
        "ELECTRIC": "BEV",
        "PHEV": "PHEV",
        "插混": "PHEV",
        "插电混动": "PHEV",
        "EREV": "EREV",
        "增程": "EREV",
        "HEV": "HEV",
        "油电混合": "HEV",
        "HYBRID": "HEV",
    }
    return aliases.get(text, "UNKNOWN")


def infer_energy_from_text(value: Any) -> str:
    text = clean_text(value)
    lowered = text.lower()
    if re.search(r"增程|erev|range.?extender", lowered):
        return "EREV"
    if re.search(
        r"插混|插电|phev|dm[\-_ ]?i|dm[\-_ ]?p|hi4[\-_ ]?t|e[\-_ ]?hybrid|dht[\-_ ]?phev|535le",
        lowered,
    ):
        return "PHEV"
    if re.search(r"双擎|油电混合|\bhev\b|e:hev|锐[·\-]?混动|智能电混双擎", lowered):
        return "HEV"
    if re.search(
        r"纯电|\bbev\b|磷酸铁锂|三元锂|\d{2,3}\s?kwh|\d{3,4}\s?km|续航|后轮驱动版|全轮驱动版",
        lowered,
    ):
        return "BEV"
    if re.search(r"(^|[^a-z])ev([^a-z]|$)", lowered):
        return "BEV"
    return "UNKNOWN"


def build_kb_energy_map(kb: pd.DataFrame) -> pd.DataFrame:
    result = kb.copy()
    result["_brand"] = result["canonical_brand"].map(normalize_text)
    result["_series"] = result["canonical_series"].map(normalize_text)
    result["_year"] = pd.to_numeric(result["model_year"], errors="coerce")
    result["_trim"] = result["trim_name"].fillna(
        result.get("trim_normalized", "")
    ).map(normalize_text)
    result["kb_energy_type"] = result["powertrain_type"].map(normalize_energy)
    result["kb_body_class"] = result["body_class"].fillna("unknown").astype(str)
    result["kb_gearbox"] = result["gearbox"].fillna("").astype(str)
    result["kb_displacement"] = result["displacement"].fillna("").astype(str)
    result["kb_confidence_score"] = pd.to_numeric(
        result.get("confidence_score"), errors="coerce"
    ).fillna(0)
    result = result.sort_values(
        ["_brand", "_series", "_year", "_trim", "kb_confidence_score"],
        ascending=[True, True, True, True, False],
    ).drop_duplicates(["_brand", "_series", "_year", "_trim"])
    return result[
        [
            "_brand",
            "_series",
            "_year",
            "_trim",
            "kb_energy_type",
            "kb_body_class",
            "kb_gearbox",
            "kb_displacement",
            "source_name",
            "source_url",
            "kb_confidence_score",
        ]
    ]


def standardize_observation_energy(
    observations: pd.DataFrame, kb_map: pd.DataFrame
) -> pd.DataFrame:
    result = observations.copy()
    result["_brand"] = result["brand"].map(normalize_text)
    result["_series"] = result["series"].map(normalize_text)
    result["_year"] = pd.to_numeric(result["model_year"], errors="coerce")
    result["_trim"] = result["trim"].map(normalize_text)
    result = result.merge(
        kb_map,
        on=["_brand", "_series", "_year", "_trim"],
        how="left",
    )
    raw = result["is_new_energy"].fillna("").astype(str).str.strip()
    raw_specific = raw.map(normalize_energy)
    trim_inferred = result["trim"].map(infer_energy_from_text)
    kb_energy = result["kb_energy_type"].fillna("UNKNOWN")
    raw_ice = raw.str.lower().isin(
        ["否", "燃油", "燃油车", "0", "0.0", "false", "ice"]
    )
    raw_nev = raw.str.lower().isin(
        ["是", "新能源", "新能源车", "1", "1.0", "true", "new_energy"]
    )
    result["energy_type_standardized"] = np.select(
        [
            kb_energy.ne("UNKNOWN"),
            trim_inferred.ne("UNKNOWN"),
            raw_specific.ne("UNKNOWN"),
            raw_ice,
            raw_nev,
        ],
        [kb_energy, trim_inferred, raw_specific, "ICE", "UNKNOWN"],
        default="UNKNOWN",
    )
    result["energy_mapping_source"] = np.select(
        [
            kb_energy.ne("UNKNOWN"),
            trim_inferred.ne("UNKNOWN"),
            raw_specific.ne("UNKNOWN"),
            raw_ice,
            raw_nev,
        ],
        [
            "STATIC_KB_EXACT_TRIM",
            "TRIM_TEXT_SEMANTICS",
            "RAW_EXPLICIT_POWERTRAIN",
            "RAW_NEGATIVE_OR_FUEL",
            "RAW_NEW_ENERGY_UNRESOLVED_SUBTYPE",
        ],
        default="MISSING_OR_UNRESOLVED",
    )
    result["energy_raw_conflict_flag"] = (
        raw_ice
        & result["energy_type_standardized"].isin(["HEV", "PHEV", "BEV", "EREV"])
    ).astype(int)
    result["energy_mapping_error_flag"] = (
        ~result["energy_type_standardized"].isin(ENERGY_TYPES)
    ).astype(int)
    return result


def _extract_engine(value: Any) -> str:
    text = clean_text(value).upper()
    matches = re.findall(r"(?<!\d)(\d\.\d)\s*([TL])", text)
    if matches:
        return "".join(matches[0])
    return ""


def _extract_transmission(value: Any) -> str:
    text = clean_text(value).upper()
    for token in ("DCT", "CVT", "AMT", "AT", "MT"):
        if re.search(rf"(^|[^A-Z]){token}([^A-Z]|$)", text):
            return token
    if "手动" in text:
        return "MT"
    if "自动" in text:
        return "AT"
    return ""


def _extract_drivetrain(value: Any) -> str:
    text = clean_text(value)
    for token in ("四驱", "全轮驱动", "后驱", "后轮驱动", "前驱", "前轮驱动", "两驱"):
        if token in text:
            return token
    return ""


def _extract_seats(value: Any) -> str:
    match = re.search(r"([2-9])\s*座", clean_text(value))
    return match.group(1) if match else ""


def _core_trim(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"改款|新款|经典|纪念|特别|限量", "", text)
    return text


def build_trim_relationships(
    candidates: pd.DataFrame, kb_map: pd.DataFrame
) -> pd.DataFrame:
    pair_columns = [
        "query_brand",
        "query_series",
        "query_model_year",
        "query_trim",
        "brand",
        "series",
        "model_year",
        "trim",
    ]
    pairs = candidates[pair_columns].drop_duplicates().copy()
    for prefix, brand, series, year, trim in (
        ("target", "query_brand", "query_series", "query_model_year", "query_trim"),
        ("source", "brand", "series", "model_year", "trim"),
    ):
        pairs[f"_{prefix}_brand"] = pairs[brand].map(normalize_text)
        pairs[f"_{prefix}_series"] = pairs[series].map(normalize_text)
        pairs[f"_{prefix}_year"] = pd.to_numeric(pairs[year], errors="coerce")
        pairs[f"_{prefix}_trim"] = pairs[trim].map(normalize_text)
        lookup = kb_map.rename(
            columns={
                "_brand": f"_{prefix}_brand",
                "_series": f"_{prefix}_series",
                "_year": f"_{prefix}_year",
                "_trim": f"_{prefix}_trim",
                "kb_energy_type": f"{prefix}_energy_type",
                "kb_body_class": f"{prefix}_body_class",
                "kb_gearbox": f"{prefix}_gearbox",
                "kb_displacement": f"{prefix}_displacement",
                "source_name": f"{prefix}_kb_source_name",
                "source_url": f"{prefix}_kb_source_url",
                "kb_confidence_score": f"{prefix}_kb_confidence_score",
            }
        )
        pairs = pairs.merge(
            lookup,
            on=[
                f"_{prefix}_brand",
                f"_{prefix}_series",
                f"_{prefix}_year",
                f"_{prefix}_trim",
            ],
            how="left",
        )
        text_energy = pairs[trim].map(infer_energy_from_text)
        pairs[f"{prefix}_energy_type"] = pairs[
            f"{prefix}_energy_type"
        ].fillna("UNKNOWN").where(
            pairs[f"{prefix}_energy_type"].fillna("UNKNOWN").ne("UNKNOWN"),
            text_energy,
        )
        pairs[f"{prefix}_engine"] = pairs[f"{prefix}_displacement"].fillna("")
        missing_engine = pairs[f"{prefix}_engine"].eq("")
        pairs.loc[missing_engine, f"{prefix}_engine"] = pairs.loc[
            missing_engine, trim
        ].map(_extract_engine)
        pairs[f"{prefix}_transmission"] = pairs[
            f"{prefix}_gearbox"
        ].fillna("")
        missing_transmission = pairs[f"{prefix}_transmission"].eq("")
        pairs.loc[missing_transmission, f"{prefix}_transmission"] = pairs.loc[
            missing_transmission, trim
        ].map(_extract_transmission)
        pairs[f"{prefix}_drivetrain"] = pairs[trim].map(_extract_drivetrain)
        pairs[f"{prefix}_seat_count"] = pairs[trim].map(_extract_seats)
    same_brand = pairs["_target_brand"].eq(pairs["_source_brand"])
    same_series = pairs["_target_series"].eq(pairs["_source_series"])
    same_trim = pairs["_target_trim"].eq(pairs["_source_trim"])
    year_gap = (pairs["_target_year"] - pairs["_source_year"]).abs()
    energy_known = (
        pairs["target_energy_type"].ne("UNKNOWN")
        & pairs["source_energy_type"].ne("UNKNOWN")
    )
    same_energy = (
        pairs["target_energy_type"].eq(pairs["source_energy_type"])
        | ~energy_known
    )
    body_known = (
        pairs["target_body_class"].fillna("unknown").ne("unknown")
        & pairs["source_body_class"].fillna("unknown").ne("unknown")
    )
    same_body = (
        pairs["target_body_class"].eq(pairs["source_body_class"])
        | ~body_known
    )

    def compatible(left: pd.Series, right: pd.Series) -> pd.Series:
        left_value = left.fillna("").astype(str)
        right_value = right.fillna("").astype(str)
        return left_value.eq(right_value) | left_value.eq("") | right_value.eq("")

    same_engine = compatible(pairs["target_engine"], pairs["source_engine"])
    same_transmission = compatible(
        pairs["target_transmission"], pairs["source_transmission"]
    )
    same_drivetrain = compatible(
        pairs["target_drivetrain"], pairs["source_drivetrain"]
    )
    same_seats = compatible(
        pairs["target_seat_count"], pairs["source_seat_count"]
    )
    exact = same_brand & same_series & same_trim & year_gap.eq(0)
    adjacent_year = (
        same_brand
        & same_series
        & same_trim
        & year_gap.between(1, 1)
        & same_energy
        & same_body
    )
    successor = (
        same_brand
        & same_series
        & year_gap.le(2)
        & pairs["query_trim"].map(_core_trim).eq(pairs["trim"].map(_core_trim))
        & same_energy
        & same_body
    )
    adjacent_config = (
        same_brand
        & same_series
        & ~same_trim
        & year_gap.le(1)
        & same_energy
        & same_body
        & same_engine
        & same_transmission
        & same_drivetrain
        & same_seats
        & (
            pairs["target_engine"].fillna("").ne("")
            | pairs["target_transmission"].fillna("").ne("")
        )
        & (
            pairs["source_engine"].fillna("").ne("")
            | pairs["source_transmission"].fillna("").ne("")
        )
    )
    not_comparable = (
        ~same_brand
        | ~same_series
        | (energy_known & ~pairs["target_energy_type"].eq(pairs["source_energy_type"]))
        | (body_known & ~pairs["target_body_class"].eq(pairs["source_body_class"]))
    )
    pairs["relationship_type"] = np.select(
        [exact, adjacent_year, successor, adjacent_config, not_comparable],
        [
            "EXACT_TRIM",
            "SAME_GENERATION_ADJACENT_YEAR",
            "SUCCESSOR_PREDECESSOR",
            "SAME_POWERTRAIN_ADJACENT_CONFIG",
            "NOT_COMPARABLE",
        ],
        default="UNKNOWN_RELATIONSHIP",
    )
    pairs["same_engine"] = same_engine.astype(int)
    pairs["same_transmission"] = same_transmission.astype(int)
    pairs["same_drivetrain"] = same_drivetrain.astype(int)
    pairs["same_energy_type"] = same_energy.astype(int)
    pairs["same_body_type"] = same_body.astype(int)
    pairs["same_seat_count"] = same_seats.astype(int)
    pairs["configuration_difference_level"] = np.select(
        [exact, adjacent_year | successor, adjacent_config],
        ["none", "low", "medium"],
        default="unknown_or_high",
    )
    pairs["allowed_as_comparable"] = pairs["relationship_type"].isin(
        [
            "EXACT_TRIM",
            "SAME_POWERTRAIN_ADJACENT_CONFIG",
            "SAME_GENERATION_ADJACENT_YEAR",
            "SUCCESSOR_PREDECESSOR",
        ]
    ).astype(int)
    pairs["evidence_source"] = np.select(
        [
            exact,
            pairs["target_kb_source_name"].notna()
            & pairs["source_kb_source_name"].notna(),
            adjacent_year | successor | adjacent_config,
        ],
        [
            "INTERNAL_EXACT_TRIM_IDENTITY",
            "STATIC_KB_AND_TRIM_SPEC_COMPARISON",
            "CONTROLLED_TRIM_TEXT_AND_YEAR_HEURISTIC",
        ],
        default="NO_POSITIVE_RELATIONSHIP_EVIDENCE",
    )
    return pairs.rename(
        columns={
            "brand": "source_brand",
            "series": "source_series",
            "model_year": "source_model_year",
            "trim": "source_trim",
            "query_brand": "target_brand",
            "query_series": "target_series",
            "query_model_year": "target_model_year",
            "query_trim": "target_trim",
        }
    )


def assign_v192_3_tiers(
    candidates: pd.DataFrame, relationships: pd.DataFrame
) -> pd.DataFrame:
    result = candidates.copy()
    relation_keys_left = [
        "query_brand",
        "query_series",
        "query_model_year",
        "query_trim",
        "brand",
        "series",
        "model_year",
        "trim",
    ]
    relationship_columns = relationships.rename(
        columns={
            "target_brand": "query_brand",
            "target_series": "query_series",
            "target_model_year": "query_model_year",
            "target_trim": "query_trim",
            "source_brand": "brand",
            "source_series": "series",
            "source_model_year": "model_year",
            "source_trim": "trim",
        }
    )
    keep = relation_keys_left + [
        "relationship_type",
        "allowed_as_comparable",
        "evidence_source",
        "target_energy_type",
        "source_energy_type",
        "same_engine",
        "same_transmission",
        "same_drivetrain",
        "same_energy_type",
        "same_body_type",
        "same_seat_count",
        "configuration_difference_level",
    ]
    result = result.merge(
        relationship_columns[keep],
        on=relation_keys_left,
        how="left",
        validate="many_to_one",
    )
    result["relationship_type"] = result["relationship_type"].fillna(
        "UNKNOWN_RELATIONSHIP"
    )
    result["allowed_as_comparable"] = result[
        "allowed_as_comparable"
    ].fillna(0).astype(int)
    result["query_energy_type"] = result["query_energy_type"].fillna(
        result["target_energy_type"]
    ).fillna("UNKNOWN")
    result["candidate_energy_type"] = result[
        "candidate_energy_type"
    ].fillna(result["source_energy_type"]).fillna("UNKNOWN")
    energy_known = (
        result["query_energy_type"].ne("UNKNOWN")
        & result["candidate_energy_type"].ne("UNKNOWN")
    )
    energy_conflict = (
        energy_known
        & result["query_energy_type"].ne(result["candidate_energy_type"])
    )
    condition_conflict = (
        result["condition_risk_level"].eq("major_risk")
        & result["query_condition"].fillna("").ne("major_risk")
    )
    price_bad = result["candidate_price_eligible_flag"].fillna(0).ne(1)
    duplicate = result["canonical_keep_flag"].fillna(0).ne(1)
    hard_conflict = (
        result["same_brand"].ne(1)
        | result["same_series"].ne(1)
        | energy_conflict
        | condition_conflict
        | price_bad
        | duplicate
    )
    strict_geometry = (
        result["age_difference"].le(2.0)
        & result["mileage_difference"].le(5.0)
        & result["transfer_difference"].le(3.0)
    )
    exact_relation = result["relationship_type"].eq("EXACT_TRIM")
    t1 = ~hard_conflict & exact_relation & strict_geometry & energy_known
    t2 = ~hard_conflict & exact_relation & strict_geometry & ~energy_known
    t3 = (
        ~hard_conflict
        & ~t1
        & ~t2
        & result["allowed_as_comparable"].eq(1)
        & result["relationship_type"].isin(
            [
                "SAME_POWERTRAIN_ADJACENT_CONFIG",
                "SAME_GENERATION_ADJACENT_YEAR",
                "SUCCESSOR_PREDECESSOR",
            ]
        )
        & result["age_difference"].le(3.0)
        & result["mileage_difference"].le(8.0)
        & result["transfer_difference"].le(4.0)
    )
    year_gap = (
        pd.to_numeric(result["query_model_year"], errors="coerce")
        - pd.to_numeric(result["model_year"], errors="coerce")
    ).abs()
    t4 = (
        ~hard_conflict
        & ~t1
        & ~t2
        & ~t3
        & year_gap.le(5)
        & result["age_difference"].le(5.0)
        & result["mileage_difference"].le(15.0)
    )
    result["semantic_candidate_tier_v192_3"] = np.select(
        [t1, t2, t3, t4],
        [
            "T1_STRICT_COMPARABLE",
            "T2_VALID_WITH_UNKNOWN_ENERGY",
            "T3_CONTROLLED_ADJACENT",
            "T4_LOOSE_FALLBACK",
        ],
        default="INELIGIBLE_SEMANTIC_CONFLICT",
    )
    result["semantic_tier_penalty"] = result[
        "semantic_candidate_tier_v192_3"
    ].map(TIER_PENALTY)
    result["semantic_exclusion_reason_v192_3"] = np.select(
        [
            price_bad,
            duplicate,
            result["same_brand"].ne(1),
            result["same_series"].ne(1),
            energy_conflict,
            condition_conflict,
            result["relationship_type"].eq("NOT_COMPARABLE"),
            result["relationship_type"].eq("UNKNOWN_RELATIONSHIP"),
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
            "major_condition_conflict",
            "trim_relationship_not_comparable",
            "trim_relationship_not_verified",
            "model_year_distance_too_large",
            "age_distance_too_large",
            "mileage_distance_too_large",
        ],
        default="",
    )
    result["preliminary_ranker_selected"] = result[
        "selected_for_pricing"
    ].fillna(0).astype(int)
    result["preliminary_ranker_reason_codes"] = result[
        "selection_reason_codes"
    ].fillna("").astype(str)
    return result


def compute_candidate_weights(group: pd.DataFrame) -> pd.DataFrame:
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
        * pd.to_numeric(result["semantic_tier_penalty"], errors="coerce").fillna(0).to_numpy()
        * outlier_penalty
    )
    if raw.sum() <= 0:
        raw = np.ones(len(result), dtype=float)
    result["ranker_weight_v192_3"] = ranker_weight.to_numpy()
    result["outlier_penalty_v192_3"] = outlier_penalty
    result["raw_pricing_weight_v192_3"] = raw
    result["final_normalized_weight"] = raw / raw.sum()
    return result


def select_final_candidates(
    candidates: pd.DataFrame, top_k: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = candidates.copy()
    result["_tier_index_v192_3"] = result[
        "semantic_candidate_tier_v192_3"
    ].map(TIER_INDEX).fillna(99)
    result["final_selected_for_pricing"] = 0
    result["final_normalized_weight"] = 0.0
    result["final_accept_reason_codes"] = ""
    result["final_reject_reason_codes"] = ""
    summaries: list[dict[str, Any]] = []
    selected_parts: list[pd.DataFrame] = []
    for query_id, group in result.groupby("query_id", sort=False):
        eligible = group[group["_tier_index_v192_3"].le(4)].sort_values(
            ["_tier_index_v192_3", "ranker_score", "days_since_transaction"],
            ascending=[True, False, True],
            kind="stable",
        )
        strict = eligible[eligible["_tier_index_v192_3"].le(3)]
        if len(strict) >= min(5, top_k):
            selected = strict.head(top_k).copy()
            selection_mode = "STRICT_T1_T2_T3_ONLY"
        else:
            selected = eligible.head(top_k).copy()
            selection_mode = "STRICT_PLUS_T4_FALLBACK"
        if not selected.empty:
            selected = compute_candidate_weights(selected)
            selected_parts.append(selected)
            indices = selected.index
            result.loc[indices, "final_selected_for_pricing"] = 1
            result.loc[indices, "final_normalized_weight"] = selected[
                "final_normalized_weight"
            ]
            accept = selected.apply(
                lambda row: "|".join(
                    [
                        "FINAL_TOPK_BY_SEMANTIC_TIER_AND_RANKER",
                        "EXACT_TRIM"
                        if row["semantic_candidate_tier_v192_3"]
                        == "T1_STRICT_COMPARABLE"
                        else "ENERGY_UNKNOWN_OTHERWISE_STRICT"
                        if row["semantic_candidate_tier_v192_3"]
                        == "T2_VALID_WITH_UNKNOWN_ENERGY"
                        else "RELATIONSHIP_TABLE_APPROVED"
                        if row["semantic_candidate_tier_v192_3"]
                        == "T3_CONTROLLED_ADJACENT"
                        else "T4_FALLBACK_INSUFFICIENT_STRICT_COUNT",
                        "SAME_CITY" if row["city_match"] == 1 else "NATIONAL_EVIDENCE",
                        "WITHIN_90D"
                        if row["days_since_transaction"] <= 90
                        else "OLDER_THAN_90D",
                    ]
                ),
                axis=1,
            )
            result.loc[indices, "final_accept_reason_codes"] = accept
        not_selected = group.index.difference(selected.index)
        reject = result.loc[not_selected].apply(
            lambda row: (
                row["semantic_exclusion_reason_v192_3"]
                if row["_tier_index_v192_3"] > 4
                else "T4_NOT_NEEDED_BECAUSE_STRICT_POOL_SUFFICIENT"
                if row["semantic_candidate_tier_v192_3"]
                == "T4_LOOSE_FALLBACK"
                and selection_mode == "STRICT_T1_T2_T3_ONLY"
                else "BELOW_FINAL_TOPK_CUTOFF"
            ),
            axis=1,
        )
        result.loc[not_selected, "final_reject_reason_codes"] = reject
        selected_weight = result.loc[
            group.index, "final_normalized_weight"
        ].sum()
        summaries.append(
            {
                "query_id": query_id,
                "candidate_rows": len(group),
                "eligible_rows": len(eligible),
                "strict_rows": len(strict),
                "final_selected_rows": int(
                    result.loc[group.index, "final_selected_for_pricing"].sum()
                ),
                "final_weight_sum": float(selected_weight),
                "selection_mode": selection_mode,
                "rejected_positive_weight_count": int(
                    (
                        result.loc[group.index, "final_selected_for_pricing"].eq(0)
                        & result.loc[group.index, "final_normalized_weight"].gt(0)
                    ).sum()
                ),
                "selected_missing_accept_reason_count": int(
                    (
                        result.loc[group.index, "final_selected_for_pricing"].eq(1)
                        & result.loc[group.index, "final_accept_reason_codes"].eq("")
                    ).sum()
                ),
                "weight_sum_pass": int(
                    abs(selected_weight - 1.0) <= 1e-9
                    if len(selected)
                    else selected_weight == 0
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
        prices = pd.to_numeric(
            group["adjusted_candidate_price"], errors="coerce"
        ).to_numpy()
        weights = pd.to_numeric(
            group["final_normalized_weight"], errors="coerce"
        ).to_numpy()
        p10 = weighted_quantile(prices, weights, 0.10)
        p25 = weighted_quantile(prices, weights, 0.25)
        p40 = weighted_quantile(prices, weights, 0.40)
        p50 = weighted_quantile(prices, weights, 0.50)
        p75 = weighted_quantile(prices, weights, 0.75)
        p90 = weighted_quantile(prices, weights, 0.90)
        metadata = group.iloc[0]
        strict_weight = group.loc[
            group["semantic_candidate_tier_v192_3"].isin(
                [
                    "T1_STRICT_COMPARABLE",
                    "T2_VALID_WITH_UNKNOWN_ENERGY",
                    "T3_CONTROLLED_ADJACENT",
                ]
            ),
            "final_normalized_weight",
        ].sum()
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
                "candidate_price_p10": p10,
                "candidate_price_p25": p25,
                "candidate_price_p40": p40,
                "candidate_price_p50": p50,
                "candidate_price_p75": p75,
                "candidate_price_p90": p90,
                "candidate_dispersion": (
                    (p75 - p25) / p50 if p50 and p50 > 0 else np.nan
                ),
                "statistical_baseline_price": p40,
                "latest_candidate_days": group[
                    "days_since_transaction"
                ].min(),
                "source_family_count": group["cluster_price_type"].nunique(),
                "exact_candidate_count": group[
                    "semantic_candidate_tier_v192_3"
                ].eq("T1_STRICT_COMPARABLE").sum(),
                "best_retrieval_level": group.sort_values(
                    [
                        "_tier_index_v192_3",
                        "ranker_score",
                        "days_since_transaction",
                    ],
                    ascending=[True, False, True],
                )["retrieval_level"].iloc[0],
                "max_semantic_tier": group.sort_values(
                    "_tier_index_v192_3"
                )["semantic_candidate_tier_v192_3"].iloc[-1],
                "strict_semantic_weight": strict_weight,
            }
        )
    return pd.DataFrame(rows)


def new_price_quality_label(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    verified_contract = result["price_semantic"].eq(
        "FULL_PURCHASE_CONTRACT_PRICE"
    ) & result["raw_price_field"].isin(
        ["收车合同价", "c2b_purchase_price_yuan"]
    )
    old = result["price_quality_label"]
    result["price_quality_confidence_label"] = np.select(
        [
            old.eq("CLEAN_NORMAL_TRANSACTION") & verified_contract,
            old.eq("GENUINE_LOW_VALUE_TRANSACTION") & verified_contract,
            old.eq("CLEAN_NORMAL_TRANSACTION"),
            old.eq("GENUINE_LOW_VALUE_TRANSACTION"),
            old.eq("ACCIDENT_OR_RESIDUAL_PRICE"),
            old.eq("CONFLICTING_LIFECYCLE_RECORD"),
            old.eq("DUPLICATE_LIFECYCLE"),
        ],
        [
            "VERIFIED_NORMAL_TRANSACTION",
            "VERIFIED_SPECIAL_LOW_VALUE",
            "PLAUSIBLE_UNVERIFIED",
            "PLAUSIBLE_LOW_VALUE_UNVERIFIED",
            "SPECIAL_CONDITION_OR_RESIDUAL",
            "MANUAL_REVIEW_REQUIRED",
            "MANUAL_REVIEW_REQUIRED",
        ],
        default=old,
    )
    result["verification_basis"] = np.select(
        [
            old.eq("ACCIDENT_OR_RESIDUAL_PRICE"),
            old.eq("CONFLICTING_LIFECYCLE_RECORD"),
            old.eq("DUPLICATE_LIFECYCLE"),
            verified_contract,
        ],
        [
            "CONDITION_OR_RESIDUAL_FLAG",
            "UNRESOLVED_LIFECYCLE_CONFLICT",
            "DUPLICATE_LIFECYCLE_REQUIRES_REVIEW",
            "ORIGINAL_FULL_PURCHASE_CONTRACT_FIELD",
        ],
        default="RULE_SCREENING_ONLY_NOT_INDEPENDENTLY_VERIFIED",
    )
    return result


def evidence_reasonableness(
    trace: pd.DataFrame, selected: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for query_id, group in selected.groupby("query_id", sort=False):
        weight = pd.to_numeric(
            group["final_normalized_weight"], errors="coerce"
        ).fillna(0)

        def weight_where(mask: pd.Series) -> float:
            return float(weight[mask].sum())

        newest = group["days_since_transaction"].min()
        recent = group[group["days_since_transaction"].le(90)]
        recent_median = (
            weighted_quantile(
                recent["adjusted_candidate_price"].to_numpy(),
                recent["final_normalized_weight"].to_numpy(),
                0.50,
            )
            if len(recent)
            else np.nan
        )
        rows.append(
            {
                "query_id": query_id,
                "final_selected_candidate_count": len(group),
                "exact_trim_weight": weight_where(
                    group["semantic_candidate_tier_v192_3"].eq(
                        "T1_STRICT_COMPARABLE"
                    )
                ),
                "unknown_energy_strict_weight": weight_where(
                    group["semantic_candidate_tier_v192_3"].eq(
                        "T2_VALID_WITH_UNKNOWN_ENERGY"
                    )
                ),
                "legal_adjacent_weight": weight_where(
                    group["semantic_candidate_tier_v192_3"].eq(
                        "T3_CONTROLLED_ADJACENT"
                    )
                ),
                "t4_fallback_weight": weight_where(
                    group["semantic_candidate_tier_v192_3"].eq(
                        "T4_LOOSE_FALLBACK"
                    )
                ),
                "evidence_weight_within_30d": weight_where(
                    group["days_since_transaction"].le(30)
                ),
                "evidence_weight_within_90d": weight_where(
                    group["days_since_transaction"].le(90)
                ),
                "evidence_weight_within_180d": weight_where(
                    group["days_since_transaction"].le(180)
                ),
                "same_city_weight": weight_where(group["city_match"].eq(1)),
                "internal_c2b_weight": weight_where(
                    group["cluster_price_type"].eq("C2B")
                ),
                "internal_b2c_weight": weight_where(
                    group["cluster_price_type"].eq("B2C")
                ),
                "external_listing_weight": weight_where(
                    group["cluster_price_type"].eq("EXT_B2C_LISTING")
                ),
                "latest_evidence_days": newest,
                "recent_transaction_median": recent_median,
                "exact_trim_count": int(
                    group["semantic_candidate_tier_v192_3"]
                    .eq("T1_STRICT_COMPARABLE")
                    .sum()
                ),
                "legal_adjacent_count": int(
                    group["semantic_candidate_tier_v192_3"]
                    .eq("T3_CONTROLLED_ADJACENT")
                    .sum()
                ),
                "same_city_count": int(group["city_match"].eq(1).sum()),
                "within_90d_count": int(
                    group["days_since_transaction"].le(90).sum()
                ),
                "internal_c2b_count": int(
                    group["cluster_price_type"].eq("C2B").sum()
                ),
                "internal_b2c_count": int(
                    group["cluster_price_type"].eq("B2C").sum()
                ),
                "external_listing_count": int(
                    group["cluster_price_type"].eq(
                        "EXT_B2C_LISTING"
                    ).sum()
                ),
            }
        )
    evidence = pd.DataFrame(rows)
    result = trace.merge(evidence, on="query_id", how="left")
    result["price_within_candidate_p10_p90"] = result["final_price"].between(
        result["candidate_price_p10"], result["candidate_price_p90"]
    ).astype(int)
    result["price_within_candidate_p25_p75"] = result["final_price"].between(
        result["candidate_price_p25"], result["candidate_price_p75"]
    ).astype(int)
    result["final_vs_statistical_baseline_ratio"] = (
        result["final_price"] / result["statistical_baseline_price"] - 1
    )
    result["final_vs_recent_median_ratio"] = (
        result["final_price"] / result["recent_transaction_median"] - 1
    )
    verified = result["price_quality_confidence_label"].isin(
        ["VERIFIED_NORMAL_TRANSACTION", "VERIFIED_SPECIAL_LOW_VALUE"]
    )
    strong = (
        result["final_price"].notna()
        & result["price_within_candidate_p25_p75"].eq(1)
        & (result["exact_trim_weight"] + result["legal_adjacent_weight"]).ge(0.70)
        & result["evidence_weight_within_90d"].ge(0.50)
        & result["t4_fallback_weight"].le(1e-12)
        & verified
    )
    supported = (
        result["final_price"].notna()
        & result["price_within_candidate_p10_p90"].eq(1)
        & (result["exact_trim_weight"] + result["legal_adjacent_weight"]).ge(0.50)
        & result["t4_fallback_weight"].le(0.15)
    )
    weak = (
        result["final_price"].notna()
        & result["price_within_candidate_p10_p90"].eq(1)
    )
    manual = (
        result["final_price"].isna()
        | result["t4_fallback_weight"].gt(0.25)
        | result["price_quality_confidence_label"].isin(
            [
                "SUSPECT_PRICE_SEMANTIC",
                "SUSPECT_PARTIAL_PAYMENT",
                "SUSPECT_PLACEHOLDER",
                "SUSPECT_UNIT_ERROR",
                "SPECIAL_CONDITION_OR_RESIDUAL",
                "MANUAL_REVIEW_REQUIRED",
            ]
        )
    )
    result["price_reasonableness_level"] = np.select(
        [manual, strong, supported, weak],
        [
            "MANUAL_REVIEW",
            "STRONGLY_SUPPORTED",
            "SUPPORTED_WITH_LIMITATIONS",
            "WEAKLY_SUPPORTED",
        ],
        default="INSUFFICIENT_EVIDENCE",
    )
    result["business_confidence"] = result[
        "price_reasonableness_level"
    ].map(
        {
            "STRONGLY_SUPPORTED": "High",
            "SUPPORTED_WITH_LIMITATIONS": "Medium",
            "WEAKLY_SUPPORTED": "Low",
            "INSUFFICIENT_EVIDENCE": "Manual",
            "MANUAL_REVIEW": "Manual",
        }
    )
    t4 = result["t4_fallback_weight"].fillna(0).gt(0)
    result.loc[t4, "business_confidence"] = "Manual"
    current_market = (
        result["evidence_weight_within_90d"].ge(0.60)
        & (
            result["internal_b2c_weight"]
            + result["external_listing_weight"]
        ).ge(0.15)
        & result["source_family_count"].ge(2)
    )
    result["market_positioning_text"] = np.where(
        current_market,
        "当前市场行情参考",
        "基于历史内部C2B市场证据",
    )
    return result


def risk_warnings(row: pd.Series) -> list[str]:
    warnings = []
    if row.get("exact_trim_count", 0) == 0:
        warnings.append("精确同款成交不足")
    if row.get("same_city_weight", 0) < 0.30:
        warnings.append("主要证据来自全国")
    if row.get("evidence_weight_within_90d", 0) < 0.50:
        warnings.append("近期证据不足")
    if row.get("unknown_energy_strict_weight", 0) > 0:
        warnings.append("能源信息不完整")
    if row.get("legal_adjacent_weight", 0) > 0:
        warnings.append("使用了关系表确认的相邻款型")
    if row.get("t4_fallback_weight", 0) > 0:
        warnings.append("使用了宽松兜底证据")
    if row.get("price_quality_confidence_label") in {
        "PLAUSIBLE_UNVERIFIED",
        "PLAUSIBLE_LOW_VALUE_UNVERIFIED",
    }:
        warnings.append("价格语义未独立核验")
    return warnings


def json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def row_json(record: dict[str, Any]) -> str:
    return json.dumps(
        {key: json_safe(value) for key, value in record.items()},
        ensure_ascii=False,
    )
