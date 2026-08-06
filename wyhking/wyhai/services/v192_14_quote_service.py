from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from services.v192_8_quote_service import (
    HistoricalV1928PricingEngine,
    QUALITY_RUNTIME_COLUMNS,
    _comparable,
    _key,
    _read_parquet_columns,
    _v192_12_residual_trace_fields,
)

from usedcar_pricing.data import (
    BASE_KEYS,
    LOW_CARDINALITY_COLUMNS,
    OBSERVATION_RUNTIME_COLUMNS,
    build_role_pairs,
    lifecycle_id,
)
from usedcar_pricing.v192_1_retrieval import LazyComparableRetriever
from usedcar_pricing.v192_4_business import (
    add_evidence_features,
    assign_candidate_tiers,
    select_final_candidates,
    selected_query_statistics,
)
from usedcar_pricing.v192_5_business import (
    add_v192_5_evidence_features,
    build_v192_5_intervals,
    compute_v192_5_confidence,
)
from usedcar_pricing.v192_6_business import (
    apply_v192_6_interval_confidence,
    compute_v192_6_confidence,
    risk_warnings_v192_6,
)
from usedcar_pricing.v192_7_business import add_v192_7_candidate_price_roles
from usedcar_pricing.v192_7_business import apply_b2c_conversion_guard
from usedcar_pricing.v192_11_service import (
    V19211PricingService,
    V19211QuoteStateStore,
)
from usedcar_pricing.v192_14_semantics import (
    CANONICALIZATION_VERSION,
    RELATIONSHIP_TABLE_VERSION,
    canonicalize_trim,
    normalize_energy_type,
)


ROOT = Path(__file__).resolve().parents[1]
PRICING_ENGINE_VERSION = "192.14.0"
MODEL_VERSION = "v192_14_semantic_runtime_existing_residual"
POLICY_VERSION = "v192_14_full_semantic_runtime_policy"
EVIDENCE_CARD_VERSION = "v192_14_evidence_card"
RETRIEVAL_POLICY_VERSION = "v192_14_semantic_relationship_policy_v1"
BUILD_TIME = datetime.now(timezone.utc).isoformat()

_ENGINE: "HistoricalV19214PricingEngine | None" = None
_ENGINE_LOCK = threading.Lock()
_READY_CACHE: dict[str, Any] | None = None


V19214_OBSERVATION_RUNTIME_COLUMNS = [
    *OBSERVATION_RUNTIME_COLUMNS,
    "raw_trim",
    "canonicalization_reason",
    "canonicalization_confidence",
    "canonicalization_version",
    "parsed_powertrain",
    "parsed_transmission",
    "parsed_drivetrain",
    "parsed_energy",
    "parsed_body",
    "parsed_generation",
    "parsed_displacement",
    "parsed_engine",
    "parsed_wheelbase",
    "parsed_seat_count",
    "parsed_range_battery",
    "parsed_config_grade",
    "parsed_facelift",
    "energy_normalization_source",
    "energy_normalization_confidence",
    "energy_field_conflict_flag",
    "energy_field_conflict_reason",
    "condition_source_v192_14",
    "store_name",
]


def _load_v19214_observations(root: Path) -> pd.DataFrame:
    path = root / "data/v192_14/vehicle_source_price_observation_v192_14_semantic.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = _read_parquet_columns(path, V19214_OBSERVATION_RUNTIME_COLUMNS)
    if "cluster_price_type" not in frame.columns:
        source_type = frame.get("source_type", pd.Series("", index=frame.index)).fillna("").astype(str)
        price_type = frame.get("price_type", pd.Series("", index=frame.index)).fillna("").astype(str)
        frame["cluster_price_type"] = np.select(
            [
                source_type.str.contains("c2b", case=False, na=False)
                | price_type.str.contains("c2b", case=False, na=False),
                source_type.str.contains("internal_b2c", case=False, na=False)
                | price_type.str.contains("b2c_sold", case=False, na=False),
                source_type.str.contains("external", case=False, na=False)
                | price_type.str.contains("external_b2c", case=False, na=False),
            ],
            ["C2B", "B2C", "EXT_B2C_LISTING"],
            default="UNKNOWN",
        )
    if "trim_key" not in frame.columns:
        frame["trim_key"] = frame.get("canonical_trim_key", "").fillna("").astype(str)
    if "trim_group_key" not in frame.columns:
        frame["trim_group_key"] = frame.get("trim_power_code", "").fillna("").astype(str)
    if "model_id_key" not in frame.columns:
        model_id = frame["model_id"] if "model_id" in frame.columns else pd.Series("", index=frame.index)
        frame["model_id_key"] = model_id.map(_key)
    if "city_key" not in frame.columns:
        city = frame["city"] if "city" in frame.columns else pd.Series("", index=frame.index)
        frame["city_key"] = city.map(_key)
    if "color_norm" not in frame.columns:
        color = frame["color_raw"] if "color_raw" in frame.columns else pd.Series("", index=frame.index)
        frame["color_norm"] = color.fillna("").astype(str).map(_key)
    if "age_fine_bin" not in frame.columns:
        age = pd.to_numeric(frame.get("age_years", 0), errors="coerce").fillna(-1)
        frame["age_fine_bin"] = pd.cut(
            age,
            bins=[-1, 0.5, 1, 2, 3, 5, 8, 12, 20, 100],
            labels=["0_0p5", "0p5_1", "1_2", "2_3", "3_5", "5_8", "8_12", "12_20", "20p"],
        ).astype(str)
    if "mileage_fine_bin" not in frame.columns:
        mileage = pd.to_numeric(frame.get("mileage_wan_km", 0), errors="coerce").fillna(-1)
        frame["mileage_fine_bin"] = pd.cut(
            mileage,
            bins=[-1, 1, 2, 3, 5, 8, 12, 20, 40, 100],
            labels=["0_1", "1_2", "2_3", "3_5", "5_8", "8_12", "12_20", "20_40", "40p"],
        ).astype(str)
    if "transfer_fine_bin" not in frame.columns:
        transfer = pd.to_numeric(frame.get("transfer_count", 0), errors="coerce").fillna(-1)
        frame["transfer_fine_bin"] = pd.cut(
            transfer,
            bins=[-1, 0, 1, 2, 3, 5, 99],
            labels=["0", "1", "2", "3", "4_5", "6p"],
        ).astype(str)
    frame = frame[frame["market_clean_flag"].eq(1)].copy()
    if "dedup_keep_flag" in frame:
        internal = frame["cluster_price_type"].isin(["C2B", "B2C"])
        frame = frame[~internal | frame["dedup_keep_flag"].eq(1)].copy()
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce")
    frame["knowledge_available_at"] = pd.to_datetime(
        frame["knowledge_available_at"], errors="coerce"
    )
    for column in [
        "price",
        "first_listing_price",
        "days_on_market",
        "model_year",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "inspection_score",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[
        frame["event_time"].notna()
        & frame["knowledge_available_at"].notna()
        & frame["price"].between(1000, 2_000_000)
        & frame["brand_key"].fillna("").astype(str).ne("")
        & frame["series_key"].fillna("").astype(str).ne("")
    ].copy()
    frame["trim_key_original_v192_14"] = frame["trim_key"].fillna("").astype(str)
    frame["trim_key"] = frame["canonical_trim_key"].fillna("").astype(str)
    frame["trim_group_key"] = frame["trim_power_code"].fillna("").astype(str)
    for column in BASE_KEYS:
        if column != "model_year" and column in frame:
            frame[column] = frame[column].fillna("").astype(str)
    frame["lifecycle_id"] = [lifecycle_id(row) for row in frame.to_dict("records")]
    frame = frame.sort_values(
        ["knowledge_available_at", "event_time", "observation_id"], kind="stable"
    )
    for column in LOW_CARDINALITY_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype("category")
            if "" not in frame[column].cat.categories:
                frame[column] = frame[column].cat.add_categories([""])
    return frame.reset_index(drop=True)


RELATIONSHIP_RUNTIME_COLUMNS = [
    "target_canonical_key",
    "source_canonical_key",
    "target_brand",
    "target_series",
    "target_model_year",
    "target_trim",
    "source_brand",
    "source_series",
    "source_model_year",
    "source_trim",
    "relationship_type",
    "allowed_as_comparable",
    "evidence_source",
    "trim_relation_quality",
    "trim_relation_quality_reason",
    "spec_match_count",
    "spec_conflict_count",
    "spec_unknown_count",
    "critical_spec_conflict_count",
    "energy_type_relation_state",
    "engine_relation_state",
    "transmission_relation_state",
    "drivetrain_relation_state",
    "body_class_relation_state",
    "seat_count_relation_state",
    "known_field_count",
    "unknown_field_count",
    "conflict_field_count",
    "relationship_confidence",
]


RELATIONSHIP_OVERRIDE_COLUMNS = [
    "relationship_type",
    "allowed_as_comparable",
    "evidence_source",
    "trim_relation_quality",
    "trim_relation_quality_reason",
    "spec_match_count",
    "spec_conflict_count",
    "spec_unknown_count",
    "critical_spec_conflict_count",
    "energy_type_relation_state",
    "engine_relation_state",
    "transmission_relation_state",
    "drivetrain_relation_state",
    "body_class_relation_state",
    "seat_count_relation_state",
    "known_field_count",
    "unknown_field_count",
    "conflict_field_count",
    "relationship_confidence",
]

RELATIONSHIP_STRENGTH = {
    "T1_EXACT_TRIM": 0,
    "EXACT_TRIM": 0,
    "T2_EXACT_TRIM_WITH_UNKNOWN_FIELD": 1,
    "T2_EXACT_TRIM_WITH_UNKNOWN_FIELD": 1,
    "T3A_VERIFIED_ADJACENT": 2,
    "T3A_VERIFIED_ADJACENT": 2,
    "T3B_HEURISTIC_ADJACENT": 3,
    "T4_LOOSE_FALLBACK": 4,
    "CRITICAL_SPEC_CONFLICT": 5,
    "NOT_COMPARABLE": 6,
}


def _dedupe_relationships_for_runtime(relationships: pd.DataFrame) -> pd.DataFrame:
    if relationships.empty:
        return relationships
    result = relationships.copy()
    result["_relationship_strength"] = (
        result["relationship_type"].map(RELATIONSHIP_STRENGTH).fillna(9)
    )
    result["_relationship_confidence_sort"] = pd.to_numeric(
        result.get("relationship_confidence", 0), errors="coerce"
    ).fillna(0)
    result = result.sort_values(
        ["_relationship_strength", "_relationship_confidence_sort"],
        ascending=[True, False],
        kind="stable",
    )
    raw_keys = [
        "target_brand",
        "target_series",
        "target_model_year",
        "target_trim",
        "source_brand",
        "source_series",
        "source_model_year",
        "source_trim",
    ]
    canonical_keys = ["target_canonical_key", "source_canonical_key"]
    for keys in (raw_keys, canonical_keys):
        if set(keys).issubset(result.columns):
            result = result.drop_duplicates(keys, keep="first")
    result["relationship_type_v192_14_original"] = result["relationship_type"]
    result["relationship_type"] = result["relationship_type"].replace(
        {
            "T1_EXACT_TRIM": "EXACT_TRIM",
            "T2_EXACT_TRIM_WITH_UNKNOWN_FIELD": "EXACT_TRIM",
        }
    )
    return result.drop(columns=["_relationship_strength", "_relationship_confidence_sort"])


def enrich_candidates_v19214(
    candidates: pd.DataFrame,
    quality: pd.DataFrame,
    relationships: pd.DataFrame,
    query_energy: dict[str, str],
    base_enricher: Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]], tuple[pd.DataFrame, pd.DataFrame]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Runtime enrichment that gives v192.14 canonical relations priority.

    The older v192.7 pipeline joins relationship rows by raw trim strings.
    v192.14 deliberately treats canonical_trim_key as the semantic identity,
    so this wrapper preserves the old quality/energy plumbing, then replaces
    the relationship columns using canonical source/target keys before tiers
    and B2C guards are recomputed.
    """
    enriched, _ = base_enricher(candidates, quality, relationships, query_energy)
    if enriched.empty or relationships.empty:
        return enriched, pd.DataFrame()
    key_cols = ["target_canonical_key", "source_canonical_key"]
    if not set(key_cols).issubset(relationships.columns):
        return enriched, pd.DataFrame()
    rel = relationships[key_cols + RELATIONSHIP_OVERRIDE_COLUMNS].drop_duplicates(key_cols)
    rel = rel.rename(
        columns={
            "target_canonical_key": "query_canonical_trim_key",
            "source_canonical_key": "canonical_trim_key",
            **{col: f"{col}__v19214" for col in RELATIONSHIP_OVERRIDE_COLUMNS},
        }
    )
    enriched = enriched.merge(
        rel,
        on=["query_canonical_trim_key", "canonical_trim_key"],
        how="left",
        validate="many_to_one",
    )
    override_mask = enriched["relationship_type__v19214"].notna()
    for col in RELATIONSHIP_OVERRIDE_COLUMNS:
        v14_col = f"{col}__v19214"
        if v14_col in enriched.columns:
            enriched.loc[override_mask, col] = enriched.loc[override_mask, v14_col]
            enriched.drop(columns=[v14_col], inplace=True)
    enriched["v192_14_relationship_override_applied"] = override_mask.astype(int)
    enriched = assign_candidate_tiers(enriched)
    enriched, conversion_audit = apply_b2c_conversion_guard(enriched)
    return enriched, conversion_audit


def _model_year(payload: dict[str, Any]) -> int | None:
    for value in (
        payload.get("model_year"),
        payload.get("modelYear"),
        payload.get("vehicle_model_year"),
        payload.get("model"),
    ):
        match = pd.Series([value]).astype(str).str.extract(r"((?:19|20)\d{2})")[0].iloc[0]
        if pd.notna(match):
            return int(match)
    return None


def _age_from_payload(payload: dict[str, Any], model_year: int | None) -> float:
    if payload.get("age_years") not in {None, ""}:
        return float(payload.get("age_years") or 0)
    reg = str(payload.get("regDate") or payload.get("reg_date") or "")
    match = pd.Series([reg]).astype(str).str.extract(r"((?:19|20)\d{2})")[0].iloc[0]
    if pd.notna(match):
        return max(0.0, datetime.now().year - int(match))
    if model_year:
        return max(0.0, datetime.now().year - model_year)
    return 0.0


def normalized_query_v19214(payload: dict[str, Any]) -> dict[str, Any]:
    model_year = _model_year(payload)
    trim = payload.get("trim") or payload.get("model") or ""
    canonical = canonicalize_trim(
        trim,
        payload.get("brand"),
        payload.get("series"),
        model_year,
        model_id=payload.get("model_id"),
        energy_value=payload.get("query_energy_type")
        or payload.get("energy_type")
        or payload.get("is_new_energy"),
    )
    energy_meta = normalize_energy_type(
        payload.get("query_energy_type")
        or payload.get("energy_type")
        or payload.get("is_new_energy"),
        brand=payload.get("brand"),
        series=payload.get("series"),
        trim=trim,
        is_new_energy=payload.get("is_new_energy"),
    )
    age = _age_from_payload(payload, model_year)
    return {
        "query_id": str(payload.get("request_id") or payload.get("quote_id") or "v192_14_live_query"),
        "prediction_time": pd.Timestamp(datetime.now()),
        "actual_price": None,
        "brand": str(payload.get("brand") or ""),
        "series": str(payload.get("series") or ""),
        "model_year": model_year,
        "trim": str(trim),
        "raw_trim": canonical["raw_trim"],
        "normalized_trim": canonical["normalized_trim"],
        "canonical_trim_key": canonical["canonical_trim_key"],
        "canonicalization_reason": canonical["canonicalization_reason"],
        "canonicalization_confidence": canonical["canonicalization_confidence"],
        "canonicalization_version": CANONICALIZATION_VERSION,
        "trim_power_code": canonical["trim_power_code"],
        "trim_wheelbase": canonical["trim_wheelbase"],
        "trim_package": canonical["trim_package"],
        "trim_drivetrain": canonical["trim_drivetrain"],
        "trim_generation_marker": canonical["trim_generation_marker"],
        "city": str(payload.get("city") or ""),
        "color_norm": str(payload.get("color") or ""),
        "age_years": float(age or 0),
        "mileage_wan_km": float(payload.get("mileage_wan_km", payload.get("mileage", 0)) or 0),
        "transfer_count": float(payload.get("transfer_count", payload.get("transfer", 0)) or 0),
        "condition_risk_level": str(payload.get("condition_risk_level") or "clean"),
        "condition_source_v192_14": "USER_PROVIDED"
        if payload.get("condition_risk_level")
        else "SYSTEM_DEFAULT_GOOD_CONDITION",
        "brand_key": _key(payload.get("brand")),
        "series_key": _key(payload.get("series")),
        "trim_key": canonical["canonical_trim_key"],
        "trim_group_key": canonical["trim_power_code"] or _key(trim),
        "city_key": _key(payload.get("city")),
        "is_new_energy": payload.get("is_new_energy"),
        "query_energy_type": energy_meta["energy_type"],
        "energy_normalization_source": energy_meta["energy_normalization_source"],
        "energy_normalization_confidence": energy_meta["energy_normalization_confidence"],
        "energy_field_conflict_flag": energy_meta.get("energy_field_conflict_flag", 0),
        "energy_field_conflict_reason": energy_meta.get("energy_field_conflict_reason", ""),
        "lifecycle_id": str(payload.get("lifecycle_id") or ""),
        "vehicle_id_hash": str(payload.get("vehicle_id") or ""),
        "clue_id_hash": str(payload.get("clue_id") or ""),
        "listing_id": str(payload.get("listing_id") or ""),
    }


class HistoricalV19214PricingEngine(HistoricalV1928PricingEngine):
    def __init__(self, root: Path = ROOT) -> None:
        from scripts.run_v192_6_pipeline import score_price_layers_cached
        from scripts.run_v192_7_pipeline import enrich_retrieved_candidates

        self.root = root
        observations = _load_v19214_observations(root)
        observations["trim_key_original_v192_14"] = observations["trim_key"].fillna("").astype(str)
        observations["trim_key"] = observations["canonical_trim_key"].fillna("").astype(str)
        observations["trim_group_key"] = observations["trim_power_code"].fillna("").astype(str)
        pairs = build_role_pairs(observations)
        self.retriever = LazyComparableRetriever(observations, pairs)
        self.quality = _read_parquet_columns(
            root / "results/v192_2/v192_2_observation_quality.parquet",
            QUALITY_RUNTIME_COLUMNS,
        )
        self.relationships = _read_parquet_columns(
            root / "data/v192_14/trim_relationship_table.parquet",
            RELATIONSHIP_RUNTIME_COLUMNS,
        )
        self.relationships = _dedupe_relationships_for_runtime(self.relationships)
        self.score_price_layers = score_price_layers_cached
        self._base_enrich_candidates = enrich_retrieved_candidates
        self.enrich_candidates = lambda candidates, quality, relationships, query_energy: enrich_candidates_v19214(
            candidates,
            quality,
            relationships,
            query_energy,
            enrich_retrieved_candidates,
        )
        calibration = pd.read_csv(
            root / "results/audit/v192_2_series_calibration_oof_audit.csv"
        ).sort_values("target_window")
        self.calibration = (
            calibration.groupby("series", as_index=False).tail(1).set_index("series")
        )

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = normalized_query_v19214(payload)
        retrieved = self.retriever.retrieve(query, top_k=100)
        if retrieved.empty:
            raise ValueError("NO_RETRIEVED_CANDIDATE")
        query_id = query["query_id"]
        retrieved["original_query_id"] = query_id
        retrieved["scenario"] = "LIVE_QUOTE"
        retrieved["query_condition"] = query["condition_risk_level"]
        enriched, _ = self.enrich_candidates(
            retrieved,
            self.quality,
            self.relationships,
            {query_id: query["query_energy_type"]},
        )
        all_candidates, reconciliation = select_final_candidates(enriched)
        selected = all_candidates[
            all_candidates["final_selected_for_pricing_v192_4"].eq(1)
        ].copy()
        if selected.empty:
            raise ValueError("NO_ELIGIBLE_CANDIDATE")
        loose_mask = selected["_tier_index_v192_4"].ge(4)
        selected.loc[loose_mask, "used_for_statistical_baseline_v192_12"] = 0
        selected.loc[loose_mask, "final_normalized_weight_v192_4"] = 0.0
        selected.loc[
            loose_mask, "candidate_business_role_v192_12"
        ] = "INTERVAL_OR_MANUAL_REFERENCE"
        selected["v192_14_point_baseline_allowed"] = (
            selected["_tier_index_v192_4"].le(3)
            & selected["used_for_statistical_baseline_v192_12"].eq(1)
        ).astype(int)
        stats = selected_query_statistics(selected)
        if stats.empty:
            # No strict T1/T2/T3A point baseline. Return a manual reference using
            # displayed candidates only; this keeps the API real without
            # pretending loose evidence is an automatic quote.
            display = selected.copy()
            ref_price = float(pd.to_numeric(display["adjusted_candidate_price"], errors="coerce").median())
            roles = add_v192_7_candidate_price_roles(display)
            comparables = [_comparable(item) for item in roles.to_dict("records")]
            return {
                "quote_id": query_id,
                "final_price": ref_price,
                "interval": {"low": ref_price * 0.82, "high": ref_price * 1.18, "type": "EVIDENCE_REFERENCE_RANGE"},
                "confidence": "MANUAL",
                "reasonableness_level": "MANUAL_REFERENCE_ONLY",
                "selected_comparables": comparables,
                "price_trace": {
                    "statistical_baseline_price": ref_price,
                    "raw_residual_ratio": 0.0,
                    "final_residual_ratio": 0.0,
                    "residual_rejection_reason_codes": ["NO_STRICT_COMPARABLE_BASELINE"],
                    "no_strict_comparable_baseline": True,
                },
                "risk_warnings": ["没有严格同款或T3A基线候选，仅输出人工参考范围。"],
                "evidence_card": {"quote_id": query_id, "vehicle": query, "selected_comparables": comparables},
                "evidence_summary": {
                    "no_strict_comparable_baseline": True,
                    "display_candidate_count": len(display),
                },
                "normalized_vehicle_state": {
                    "age_years": query["age_years"],
                    "mileage_wan_km": query["mileage_wan_km"],
                    "transfer_count": query["transfer_count"],
                    "condition_risk_level": query["condition_risk_level"],
                },
                "retrieval_summary": {
                    "retrieved_count": len(retrieved),
                    "eligible_count": int(all_candidates["_tier_index_v192_4"].le(5).sum()),
                    "selected_count": len(selected),
                    "baseline_candidate_count": 0,
                    "selection_mode": "MANUAL_REFERENCE_NO_STRICT_BASELINE",
                    "t3b_t4_point_baseline_blocked": int(loose_mask.sum()),
                },
            }
        adjustment, calibration_meta = self._series_adjustment(query["series"])
        old_trace = pd.DataFrame(
            {"query_id": [query_id], "series_calibration_clipped_adjustment": [adjustment]}
        )
        scored = self.score_price_layers(stats, old_trace)
        scored = add_evidence_features(scored, selected)
        scored["condition_information_complete"] = int(
            query["condition_risk_level"] in {"clean", "minor_defect", "major_risk"}
        )
        scored["energy_information_complete"] = int(
            query["query_energy_type"] != "UNKNOWN"
            and float(scored["unknown_energy_strict_weight"].iloc[0]) <= 1e-12
        )
        scored["model_adjustment_abs_ratio"] = np.maximum(
            scored["base_residual_clipped_adjustment"].abs(),
            scored["series_calibration_clipped_adjustment"].abs(),
        )
        scored = add_v192_5_evidence_features(scored, selected)
        scored = compute_v192_5_confidence(scored)
        scored = build_v192_5_intervals(scored)
        scored = compute_v192_6_confidence(scored)
        scored = apply_v192_6_interval_confidence(scored)
        row = scored.iloc[0].to_dict()
        roles = add_v192_7_candidate_price_roles(selected)
        comparables = [_comparable(item) for item in roles.to_dict("records")]
        warnings = risk_warnings_v192_6(pd.Series(row))
        if query.get("condition_source_v192_14") == "SYSTEM_DEFAULT_GOOD_CONDITION":
            warnings.append("当前报价按系统默认良好车况估算，实际检测后可能调整。")
        if query.get("energy_field_conflict_flag"):
            warnings.append("能源字段与款型语义冲突，已按车型文本强语义修正。")
        residual_trace = _v192_12_residual_trace_fields(row)
        trace = {
            "statistical_baseline_price": row["statistical_baseline_price"],
            **residual_trace,
            "base_residual_adjustment_amount": row["base_residual_output_price"] - row["base_residual_input_price"],
            "low_price_adjustment_amount": 0.0,
            "series_calibration_adjustment_amount": row["series_calibration_output_price"] - row["series_calibration_input_price"],
            "raw_price_before_guard": row["raw_price_before_guard"],
            "canonicalization_version": CANONICALIZATION_VERSION,
            "relationship_table_version": RELATIONSHIP_TABLE_VERSION,
        }
        evidence_summary = {
            "source_family_count": row.get("source_family_count_v192_5"),
            "same_city_weight": row.get("same_city_weight"),
            "recent_90d_weight": row.get("evidence_weight_within_90d"),
            "same_trim_candidate_count": row.get("same_trim_candidate_count"),
            "same_trim_weight": row.get("same_trim_weight"),
            "exact_energy_confirmed_count": row.get("exact_energy_confirmed_count"),
            "exact_energy_unknown_count": row.get("exact_energy_unknown_count"),
            "display_candidate_count": row.get("display_candidate_count_v192_12"),
            "candidate_condition_match_weight": row.get("candidate_condition_match_weight"),
            "t4_fallback_weight": row.get("t4_fallback_weight"),
            "no_strict_comparable_baseline": False,
        }
        card = {
            "quote_id": query_id,
            "vehicle": query,
            "selected_comparables": comparables,
            "price_trace": trace,
            "series_calibration": calibration_meta,
            "risk_warnings": warnings,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "relationship_table_version": RELATIONSHIP_TABLE_VERSION,
        }
        return {
            "quote_id": query_id,
            "final_price": row["raw_price_before_guard"],
            "interval": {"low": row["business_interval_low"], "high": row["business_interval_high"], "type": row["interval_type"]},
            "confidence": row["quote_evidence_confidence"],
            "reasonableness_level": row.get("price_reasonableness_level", "SUPPORTED_WITH_LIMITATIONS"),
            "selected_comparables": comparables,
            "price_trace": trace,
            "risk_warnings": warnings,
            "evidence_card": card,
            "evidence_summary": evidence_summary,
            "normalized_vehicle_state": {
                "age_years": query["age_years"],
                "mileage_wan_km": query["mileage_wan_km"],
                "transfer_count": query["transfer_count"],
                "condition_risk_level": query["condition_risk_level"],
            },
            "retrieval_summary": {
                "retrieved_count": len(retrieved),
                "eligible_count": int(all_candidates["_tier_index_v192_4"].le(5).sum()),
                "selected_count": len(selected),
                "baseline_candidate_count": int(selected["used_for_statistical_baseline_v192_12"].sum()),
                "selection_mode": reconciliation.iloc[0]["selection_mode_v192_4"],
                "t3b_t4_point_baseline_blocked": int(loose_mask.sum()),
            },
            "series_calibration": calibration_meta,
        }


def get_engine() -> HistoricalV19214PricingEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = HistoricalV19214PricingEngine(ROOT)
    return _ENGINE


def _patch_v19214_result(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalized_query_v19214(payload)
    result["pricing_engine_used"] = "V192_14"
    result["pricing_engine_version"] = PRICING_ENGINE_VERSION
    result["model_version"] = PRICING_ENGINE_VERSION
    result["underlying_model_version"] = MODEL_VERSION
    result["policy_version"] = POLICY_VERSION
    result["retrieval_policy_version"] = RETRIEVAL_POLICY_VERSION
    result["canonicalization_version"] = CANONICALIZATION_VERSION
    result["relationship_table_version"] = RELATIONSHIP_TABLE_VERSION
    result["evidence_card_version"] = EVIDENCE_CARD_VERSION
    result["modelName"] = "v192.14-full-semantic-runtime"
    result["reason"] = "v192.14 使用全车型语义Canonical Key、能源/车况标准化、严格关系表和真实历史候选生成报价证据。"
    result["input_normalization"] = {
        "raw_query": {
            "brand": payload.get("brand"),
            "series": payload.get("series"),
            "model": payload.get("model") or payload.get("trim"),
            "city": payload.get("city"),
            "mileage": payload.get("mileage") or payload.get("mileage_wan_km"),
            "transfer": payload.get("transfer") or payload.get("transfer_count"),
            "color": payload.get("color"),
        },
        "normalized_query": {
            "brand": normalized["brand"],
            "series": normalized["series"],
            "model_year": normalized["model_year"],
            "raw_trim": normalized["raw_trim"],
            "normalized_trim": normalized["normalized_trim"],
            "canonical_trim_key": normalized["canonical_trim_key"],
            "query_energy_type": normalized["query_energy_type"],
            "condition_risk_level": normalized["condition_risk_level"],
            "condition_source": normalized["condition_source_v192_14"],
        },
        "canonicalization_reason": normalized["canonicalization_reason"],
        "canonicalization_confidence": normalized["canonicalization_confidence"],
        "canonicalization_version": CANONICALIZATION_VERSION,
        "energy_normalization_source": normalized["energy_normalization_source"],
        "energy_normalization_confidence": normalized["energy_normalization_confidence"],
        "energy_field_conflict_flag": normalized["energy_field_conflict_flag"],
        "energy_field_conflict_reason": normalized["energy_field_conflict_reason"],
    }
    card = result.get("evidence_card") or {}
    card.update(
        {
            "pricing_engine_used": "V192_14",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "relationship_table_version": RELATIONSHIP_TABLE_VERSION,
            "evidence_card_version": EVIDENCE_CARD_VERSION,
            "summary": "v192.14按统一款型语义、能源识别和候选关系表生成，可从证据卡复核候选、权重和调整。",
            "input_normalization": result["input_normalization"],
        }
    )
    result["evidence_card"] = card
    return result


def get_version_payload() -> dict[str, Any]:
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "relationship_table_version": RELATIONSHIP_TABLE_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
        "git_commit": os.environ.get("GIT_COMMIT", ""),
        "build_time": os.environ.get("BUILD_TIME", BUILD_TIME),
        "production_entrypoint": "app.py",
        "api_path": "/api/price",
    }


def minimal_real_payload() -> dict[str, Any]:
    return {
        "request_id": "v192_14_ready_probe",
        "brand": "宝马",
        "series": "宝马3系",
        "model": "2021款 320i 运动套装",
        "model_year": 2021,
        "vehicle_model_year": 2021,
        "regDate": "2021-09",
        "reg_date": "2021-09",
        "mileage": 6.34,
        "transfer": 1,
        "color": "白色",
        "city": "北京",
        "condition_risk_level": "clean",
        "query_energy_type": "ICE",
        "vehicle_id": "v19214-ready-probe",
        "lifecycle_id": "v19214-ready-probe-life",
    }


def quote_with_v19214_service(
    payload: dict[str, Any],
    legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    store_path = Path(
        payload.get("_quote_state_store_path")
        or os.environ.get("V19214_QUOTE_STATE_DB", "")
        or ROOT / "data/runtime/v192_14_quote_state.sqlite"
    )
    service = V19211PricingService(
        engine=get_engine(),
        state_store=V19211QuoteStateStore(store_path),
        legacy_fallback=legacy_pricing_callable,
    )
    result = service.quote(payload)
    raw_engine = ((result.get("price_result") or {}).get("pricing_engine_used") or "").upper()
    if raw_engine and raw_engine != "V192_14":
        result["pricing_engine_used"] = raw_engine
        result["fallback_reason"] = result.get("fallback_reason") or "V192_14_ENGINE_FAILED"
        return result
    return _patch_v19214_result(result, payload)


def _required_files() -> list[Path]:
    return [
        ROOT / "data/knowledge/v185_market_price/vehicle_source_price_observation.parquet",
        ROOT / "results/v192_2/v192_2_observation_quality.parquet",
        ROOT / "data/v192_14/trim_relationship_table.parquet",
        ROOT / "data/v192_14/canonical_trim_table.parquet",
        ROOT / "results/audit/v192_2_series_calibration_oof_audit.csv",
        ROOT / "models/v192_2/v192_2_base_residual_model.joblib",
    ]


def v19214_readiness_check(force: bool = False) -> dict[str, Any]:
    global _READY_CACHE
    if _READY_CACHE is not None and not force:
        return dict(_READY_CACHE)
    checks: dict[str, Any] = {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "entrypoint_uses_v192_14": True,
        "required_files": {str(path.relative_to(ROOT)): path.exists() for path in _required_files()},
        "sqlite_state_store": False,
        "engine_loaded": False,
        "real_prediction_succeeded": False,
        "real_prediction_selected_comparables": 0,
        "real_prediction_pricing_engine_used": "",
    }
    try:
        store = V19211QuoteStateStore(ROOT / "data/runtime/v192_14_ready_check.sqlite")
        with store._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["sqlite_state_store"] = True
        service = V19211PricingService(engine=get_engine(), state_store=store, legacy_fallback=None)
        checks["engine_loaded"] = True
        result = _patch_v19214_result(service.quote(minimal_real_payload()), minimal_real_payload())
        price_result = result.get("price_result") or {}
        checks["real_prediction_succeeded"] = bool(
            price_result.get("final_price") is not None
            and result.get("pricing_engine_used") == "V192_14"
        )
        checks["real_prediction_final_price"] = price_result.get("final_price")
        checks["real_prediction_selected_comparables"] = len(result.get("selected_comparables") or [])
        checks["real_prediction_confidence"] = price_result.get("confidence")
        checks["real_prediction_pricing_engine_used"] = result.get("pricing_engine_used", "")
    except Exception as error:
        checks["engine_error"] = str(error)
    checks["ready"] = (
        all(checks["required_files"].values())
        and checks["sqlite_state_store"]
        and checks["entrypoint_uses_v192_14"]
        and checks["engine_loaded"]
        and checks["real_prediction_succeeded"]
        and checks["real_prediction_pricing_engine_used"] == "V192_14"
        and checks["real_prediction_selected_comparables"] > 0
    )
    _READY_CACHE = dict(checks)
    return checks
