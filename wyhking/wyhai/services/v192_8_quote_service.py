from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

try:
    from usedcar_pricing.data import build_role_pairs, load_observations
    from usedcar_pricing.v191_1 import TemporalObservationIndex
    from usedcar_pricing.v192_1_retrieval import LazyComparableRetriever
    from usedcar_pricing.v192_4_business import (
        add_evidence_features,
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
    from usedcar_pricing.v192_7_business import (
        add_v192_7_candidate_price_roles,
    )
    from usedcar_pricing.v192_8_service import (
        QuoteStateStore,
        V1928PricingService,
    )
    from usedcar_pricing.v192_12_semantics import (
        canonicalize_trim,
        normalize_energy_type,
    )
except ModuleNotFoundError:
    from src.usedcar_pricing.data import build_role_pairs, load_observations
    from src.usedcar_pricing.v191_1 import TemporalObservationIndex
    from src.usedcar_pricing.v192_1_retrieval import LazyComparableRetriever
    from src.usedcar_pricing.v192_4_business import (
        add_evidence_features,
        select_final_candidates,
        selected_query_statistics,
    )
    from src.usedcar_pricing.v192_5_business import (
        add_v192_5_evidence_features,
        build_v192_5_intervals,
        compute_v192_5_confidence,
    )
    from src.usedcar_pricing.v192_6_business import (
        apply_v192_6_interval_confidence,
        compute_v192_6_confidence,
        risk_warnings_v192_6,
    )
    from src.usedcar_pricing.v192_7_business import (
        add_v192_7_candidate_price_roles,
    )
    from src.usedcar_pricing.v192_8_service import (
        QuoteStateStore,
        V1928PricingService,
    )
    from src.usedcar_pricing.v192_12_semantics import (
        canonicalize_trim,
        normalize_energy_type,
    )


ROOT = Path(__file__).resolve().parents[1]
_ENGINE: "HistoricalV1928PricingEngine | None" = None
_ENGINE_LOCK = threading.Lock()

QUALITY_RUNTIME_COLUMNS = [
    "observation_id",
    "canonical_lifecycle_id",
    "canonical_keep_flag",
    "candidate_price_eligible_flag",
    "price_quality_label",
    "price_quality_reason_codes",
]

RELATIONSHIP_RUNTIME_COLUMNS = [
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
]


def _key(value: Any) -> str:
    return re.sub(r"[\s\-_（）()]+", "", str(value or "").strip()).lower()


def _year(value: Any) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _clean_trim_text(value: Any, brand: Any = "", series: Any = "") -> str:
    text = str(value or "").strip()
    for token in (brand, series):
        token_text = str(token or "").strip()
        if token_text:
            text = text.replace(token_text, " ")
    text = re.sub(r"(19|20)\d{2}\s*款?", " ", text)
    text = re.sub(r"款$", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _read_parquet_columns(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(path).schema.names)
        selected = [column for column in columns if column in available]
        return pd.read_parquet(path, columns=selected)
    except Exception:
        frame = pd.read_parquet(path)
        selected = [column for column in columns if column in frame.columns]
        return frame[selected].copy()


class HistoricalV1928PricingEngine:
    def __init__(self, root: Path = ROOT) -> None:
        from scripts.run_v192_6_pipeline import score_price_layers_cached
        from scripts.run_v192_7_pipeline import enrich_retrieved_candidates

        self.root = root
        observations = load_observations(
            str(
                root
                / "data/knowledge/v185_market_price/"
                "vehicle_source_price_observation.parquet"
            )
        )
        pairs = build_role_pairs(observations)
        self.retriever = LazyComparableRetriever(observations, pairs)
        self.quality = _read_parquet_columns(
            root / "results/v192_2/v192_2_observation_quality.parquet",
            QUALITY_RUNTIME_COLUMNS,
        )
        self.relationships = _read_parquet_columns(
            root / "data/v192_4/v192_4_trim_relationship_quality.parquet",
            RELATIONSHIP_RUNTIME_COLUMNS,
        )
        self.score_price_layers = score_price_layers_cached
        self.enrich_candidates = enrich_retrieved_candidates
        calibration = pd.read_csv(
            root / "results/audit/v192_2_series_calibration_oof_audit.csv"
        ).sort_values("target_window")
        self.calibration = (
            calibration.groupby("series", as_index=False)
            .tail(1)
            .set_index("series")
        )

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = _normalized_query(payload)
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
        stats = selected_query_statistics(selected)
        adjustment, calibration_meta = self._series_adjustment(
            query["series"]
        )
        old_trace = pd.DataFrame(
            {
                "query_id": [query_id],
                "series_calibration_clipped_adjustment": [adjustment],
            }
        )
        scored = self.score_price_layers(stats, old_trace)
        scored = add_evidence_features(scored, selected)
        scored["condition_information_complete"] = int(
            query["condition_risk_level"]
            in {"clean", "minor_defect", "major_risk"}
        )
        scored["energy_information_complete"] = int(
            query["query_energy_type"] != "UNKNOWN"
            and float(scored["unknown_energy_strict_weight"].iloc[0])
            <= 1e-12
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
        residual_trace = _v192_12_residual_trace_fields(row)
        trace = {
            "statistical_baseline_price": row["statistical_baseline_price"],
            **residual_trace,
            "base_residual_adjustment_amount": (
                row["base_residual_output_price"]
                - row["base_residual_input_price"]
            ),
            "low_price_adjustment_amount": 0.0,
            "series_calibration_adjustment_amount": (
                row["series_calibration_output_price"]
                - row["series_calibration_input_price"]
            ),
            "raw_price_before_guard": row["raw_price_before_guard"],
        }
        evidence_summary = {
            "source_family_count": row.get("source_family_count_v192_5"),
            "same_city_weight": row.get("same_city_weight"),
            "recent_90d_weight": row.get("evidence_weight_within_90d"),
            "same_trim_candidate_count": row.get("same_trim_candidate_count"),
            "same_trim_weight": row.get("same_trim_weight"),
            "exact_energy_confirmed_count": row.get(
                "exact_energy_confirmed_count"
            ),
            "exact_energy_unknown_count": row.get("exact_energy_unknown_count"),
            "display_candidate_count": row.get("display_candidate_count_v192_12"),
            "candidate_condition_match_weight": row.get(
                "candidate_condition_match_weight"
            ),
        }
        card = {
            "quote_id": query_id,
            "vehicle": query,
            "selected_comparables": comparables,
            "price_trace": trace,
            "series_calibration": calibration_meta,
            "risk_warnings": warnings,
        }
        return {
            "quote_id": query_id,
            "final_price": row["raw_price_before_guard"],
            "interval": {
                "low": row["business_interval_low"],
                "high": row["business_interval_high"],
                "type": row["interval_type"],
            },
            "confidence": row["quote_evidence_confidence"],
            "reasonableness_level": row.get(
                "price_reasonableness_level",
                "SUPPORTED_WITH_LIMITATIONS",
            ),
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
                "eligible_count": int(
                    all_candidates["_tier_index_v192_4"].le(5).sum()
                ),
                "selected_count": len(selected),
                "baseline_candidate_count": int(
                    selected["used_for_statistical_baseline_v192_12"].sum()
                    if "used_for_statistical_baseline_v192_12" in selected
                    else len(selected)
                ),
                "selection_mode": reconciliation.iloc[0][
                    "selection_mode_v192_4"
                ],
            },
            "series_calibration": calibration_meta,
        }

    def _series_adjustment(
        self, series: str
    ) -> tuple[float, dict[str, Any]]:
        if series not in self.calibration.index:
            return 0.0, {"status": "DISABLED", "reason": "NO_OOF_HISTORY"}
        item = self.calibration.loc[series]
        enabled = bool(item["enabled"])
        adjustment = float(item["factor_log"]) if enabled else 0.0
        return adjustment, {
            "status": "ENABLED" if enabled else "DISABLED",
            "history_window": f"{int(item['prior_months'])} rolling months",
            "sample_count": int(item["prior_rows"]),
            "rolling_month_count": int(item["prior_months"]),
            "evaluated_folds": int(item["evaluated_folds"]),
            "historical_baseline_mean_bias": float(item["factor_log"]),
            "raw_calibration_ratio": float(np.expm1(item["factor_log"])),
            "clipped_calibration_ratio": float(np.expm1(adjustment)),
        }


def _normalized_query(payload: dict[str, Any]) -> dict[str, Any]:
    now = pd.Timestamp(
        payload.get("prediction_time") or datetime.now()
    )
    model_year = _year(
        payload.get("modelYear")
        or payload.get("model_year")
        or payload.get("vehicle_model_year")
    )
    registration_year = _year(
        payload.get("regDate") or payload.get("reg_date")
    )
    age = payload.get("age_years")
    if age is None and registration_year:
        age = max(now.year - registration_year, 0)
    trim = _clean_trim_text(
        payload.get("trim") or payload.get("model") or "",
        payload.get("brand"),
        payload.get("series"),
    )
    canonical = canonicalize_trim(
        trim,
        payload.get("brand"),
        payload.get("series"),
        model_year,
    )
    is_new_energy = payload.get("is_new_energy")
    energy_meta = normalize_energy_type(
        payload.get("query_energy_type") or payload.get("energy_type") or is_new_energy,
        brand=payload.get("brand"),
        series=payload.get("series"),
        trim=trim,
        is_new_energy=is_new_energy,
    )
    energy = energy_meta["energy_type"]
    return {
        "query_id": str(payload.get("request_id") or uuid.uuid4()),
        "prediction_time": now,
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
        "trim_power_code": canonical["trim_power_code"],
        "trim_wheelbase": canonical["trim_wheelbase"],
        "trim_package": canonical["trim_package"],
        "trim_drivetrain": canonical["trim_drivetrain"],
        "trim_generation_marker": canonical["trim_generation_marker"],
        "city": str(payload.get("city") or ""),
        "color_norm": str(payload.get("color") or ""),
        "age_years": float(age or 0),
        "mileage_wan_km": float(
            payload.get("mileage_wan_km", payload.get("mileage", 0))
            or 0
        ),
        "transfer_count": float(
            payload.get("transfer_count", payload.get("transfer", 0))
            or 0
        ),
        "condition_risk_level": str(
            payload.get("condition_risk_level") or "unknown"
        ),
        "brand_key": _key(payload.get("brand")),
        "series_key": _key(payload.get("series")),
        "trim_key": canonical["canonical_trim_key"],
        "trim_group_key": canonical["trim_power_code"] or _key(trim),
        "city_key": _key(payload.get("city")),
        "is_new_energy": is_new_energy,
        "query_energy_type": energy,
        "energy_normalization_source": energy_meta[
            "energy_normalization_source"
        ],
        "energy_normalization_confidence": energy_meta[
            "energy_normalization_confidence"
        ],
        "lifecycle_id": str(payload.get("lifecycle_id") or ""),
        "vehicle_id_hash": str(payload.get("vehicle_id") or ""),
        "clue_id_hash": str(payload.get("clue_id") or ""),
        "listing_id": str(payload.get("listing_id") or ""),
    }


def _comparable(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": item["candidate_id"],
        "candidate_vehicle_id": item.get("candidate_vehicle_id"),
        "source_row_id": item.get("source_row_id"),
        "vehicle": (
            f"{item['brand']} {item['series']} "
            f"{item['model_year']} {item['trim']}"
        ),
        "brand": item.get("brand"),
        "series": item.get("series"),
        "model_year": item.get("model_year"),
        "trim": item.get("trim"),
        "raw_trim": item.get("raw_trim"),
        "normalized_trim": item.get("normalized_trim"),
        "canonical_trim_key": item.get("canonical_trim_key"),
        "canonicalization_reason": item.get("canonicalization_reason"),
        "canonicalization_confidence": item.get("canonicalization_confidence"),
        "trim_power_code": item.get("trim_power_code"),
        "trim_wheelbase": item.get("trim_wheelbase"),
        "trim_package": item.get("trim_package"),
        "query_canonical_trim_key": item.get("query_canonical_trim_key"),
        "city": item.get("city"),
        "color": item.get("color_norm") or item.get("color_raw"),
        "mileage_wan_km": item.get("mileage_wan_km"),
        "transfer_count": item.get("transfer_count"),
        "transaction_time": item.get("transaction_time"),
        "event_time": item.get("event_time"),
        "listing_start_time": item.get("listing_start_time"),
        "sold_time": item.get("sold_time"),
        "retrieval_level": item.get("retrieval_level"),
        "retrieval_rank": item.get("retrieval_rank"),
        "retrieval_stage_rank": item.get("retrieval_stage_rank_v192_12"),
        "final_pricing_rank": item.get("final_pricing_rank_v192_12"),
        "candidate_business_role": item.get("candidate_business_role_v192_12"),
        "used_for_statistical_baseline": item.get(
            "used_for_statistical_baseline_v192_12"
        ),
        "ranker_score": item.get("ranker_score"),
        "rule_score": item.get("rule_score"),
        "time_decay": item.get("time_decay"),
        "same_brand": item.get("same_brand"),
        "same_series": item.get("same_series"),
        "same_trim": item.get("same_trim"),
        "trim_power_code_match": item.get("trim_power_code_match"),
        "trim_power_code_conflict": item.get("trim_power_code_conflict"),
        "semantic_similarity_reason": item.get("v192_12_similarity_reason"),
        "city_match": item.get("city_match"),
        "color_match": item.get("color_match"),
        "condition_match": item.get("condition_match"),
        "age_difference": item.get("age_difference"),
        "mileage_difference": item.get("mileage_difference"),
        "transfer_difference": item.get("transfer_difference"),
        "days_since_transaction": item.get("days_since_transaction"),
        "semantic_tier": item.get("semantic_candidate_tier_v192_4"),
        "semantic_exclusion_reason": item.get(
            "semantic_exclusion_reason_v192_4"
        ),
        "energy_type": item.get("candidate_energy_type"),
        "condition": item.get("condition_risk_level"),
        "source_family": item.get("source_family"),
        "source_type": item.get("source_type"),
        "source_platform": item.get("source_platform_v192_6"),
        "source_file": item.get("source_file"),
        "source_url": item.get("source_url"),
        "price_type": item.get("price_type"),
        "cluster_price_type": item.get("cluster_price_type"),
        "original_price": item.get("original_price_v192_6"),
        "original_price_role": item.get("original_price_role_v192_6"),
        "conversion_method": item.get("conversion_method_v192_6"),
        "conversion_ratio": item.get("conversion_ratio_final_v192_7"),
        "conversion_ratio_raw": item.get("conversion_ratio_raw_v192_7"),
        "conversion_guard_applied": item.get(
            "conversion_guard_applied_v192_7"
        ),
        "conversion_warning_reason": item.get(
            "conversion_warning_reason_v192_7"
        ),
        "converted_c2b_price": item.get(
            "converted_c2b_equivalent_price_v192_6"
        ),
        "final_weight": item.get("final_normalized_weight_v192_4"),
        "accept_reason": item.get("final_accept_reason_codes_v192_4"),
        "reject_reason": item.get("final_reject_reason_codes_v192_4"),
        "price_quality_label": item.get("price_quality_label"),
        "price_quality_reason_codes": item.get("price_quality_reason_codes"),
    }


def _v192_12_residual_trace_fields(row: dict[str, Any]) -> dict[str, Any]:
    base_input = float(row.get("base_residual_input_price") or 0)
    raw_ratio = float(row.get("base_residual_raw_adjustment") or 0)
    final_ratio = float(row.get("base_residual_clipped_adjustment") or 0)
    raw_amount = base_input * float(np.exp(raw_ratio) - 1.0) if base_input else 0.0
    final_amount = (
        float(row.get("base_residual_output_price") or 0)
        - float(row.get("base_residual_input_price") or 0)
    )
    clip_low = float(row.get("base_residual_clip_lower") or 0)
    clip_high = float(row.get("base_residual_clip_upper") or 0)
    rejection_reasons = []
    if abs(raw_ratio) > 1e-12 and abs(final_ratio) <= 1e-12:
        rejection_reasons.append("EVIDENCE_QUALITY_CLIP_ZERO")
    if row.get("evidence_quality_for_model_adjustment") == "very_low":
        rejection_reasons.append("STRICT_COMPARABLE_WEIGHT_INSUFFICIENT")
    if float(row.get("t4_fallback_weight") or 0) > 0.20:
        rejection_reasons.append("T4_WEIGHT_TOO_HIGH")
    return {
        "raw_residual_ratio": raw_ratio,
        "raw_residual_amount": raw_amount,
        "evidence_quality": row.get("evidence_quality_for_model_adjustment"),
        "allowed_clip_range": [clip_low, clip_high],
        "final_residual_ratio": final_ratio,
        "final_residual_amount": final_amount,
        "residual_rejection_reason_codes": rejection_reasons,
    }


def get_engine() -> HistoricalV1928PricingEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = HistoricalV1928PricingEngine()
    return _ENGINE


def quote_with_v1928_service(
    payload: dict[str, Any],
    legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    store_path = Path(
        payload.get("_quote_state_store_path")
        or ROOT / "data/runtime/v192_8_quote_state.sqlite"
    )
    service = V1928PricingService(
        engine=get_engine(),
        state_store=QuoteStateStore(store_path),
        legacy_fallback=legacy_pricing_callable,
    )
    result = service.quote(payload)
    if result.get("final_price") is not None:
        result["c2bPrice"] = round(float(result["final_price"]) / 10000, 2)
    return result
