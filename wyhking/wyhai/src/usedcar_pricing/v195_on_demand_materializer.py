"""On-demand v195 price-cell materialization for unseen vehicle inputs.

The daily snapshot covers combinations observed before its cutoff.  A new
combination must not inherit the final prices of the nearest cell.  This
module rebuilds the price ladder from strict same-trim evidence, current
three-source listings and the Level-5 online fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v195_external_market_anchor import (
    ExternalMarketCalibration,
    calibrated_external_proxy,
    fit_external_market_calibration,
)
from .v195_manual_override_engine import ManualOverrideRegistry
from .v195_price_book_schema import QuoteDecision, compact
from .v195_price_book_schema import EvaluationMode
from .v195_price_ladder_solver import (
    ORDERED_FIELDS,
    hierarchy_violations,
    load_ladder_config,
)
from .v195_production_pricing_engine import RawPricingInputs, V195ProductionPricingEngine
from .v195_residual_price_book import DailyResidualPriceBook


@dataclass(frozen=True)
class OnDemandMaterializationPolicy:
    high_external_blend: float = 0.20
    medium_external_blend: float = 0.08
    high_external_cap_ratio: float = 0.12
    medium_external_cap_ratio: float = 0.06
    comparable_blend: float = 0.15
    comparable_cap_ratio: float = 0.10
    strong_comparable_max_distance: float = 0.55
    strong_comparable_max_recency_days: float = 60.0
    c2b_direct_evidence_blend: float = 0.25
    c2b_direct_evidence_cap_ratio: float = 0.10
    auto_quote_consensus_gap_ratio: float = 0.08
    auto_quote_max_external_dispersion: float = 0.18


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed) or not np.isfinite(float(parsed)):
        return None
    return float(parsed)


def _integer(value: Any) -> int:
    parsed = _number(value)
    return int(parsed) if parsed is not None else 0


def _timestamp(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Asia/Shanghai")
    return parsed.tz_convert("UTC")


def _strict_identity_is_usable(payload: dict[str, Any]) -> bool:
    model_id = _integer(payload.get("model_id") or payload.get("modelId"))
    model_year = _integer(payload.get("model_year") or payload.get("modelYear"))
    trim = compact(
        payload.get("trim")
        or payload.get("model")
        or payload.get("standard_vehicle")
        or payload.get("standardVehicle")
        or ""
    )
    return bool(
        model_id > 0
        and model_year > 0
        and trim
        and trim not in {"other", "unknown", "未知", "其他", "0", "null", "none"}
    )


def _flatten_listing_quote(quote: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "listing_price_yuan": quote.get("listing_price_yuan"),
        "source_weighted_listing_price_yuan": quote.get(
            "source_weighted_listing_price_yuan"
        ),
        "source_count": quote.get("source_count", 0),
        "same_year_source_count": quote.get("same_year_source_count", 0),
        "total_listing_count": quote.get("total_listing_count", 0),
        "cross_source_dispersion_ratio": quote.get(
            "cross_source_dispersion_ratio"
        ),
        "listing_confidence": quote.get("confidence", ""),
        "safe_for_transaction_calibration": quote.get(
            "safe_for_transaction_calibration", False
        ),
        "exact_dcd_vehicle_match": quote.get("exact_dcd_vehicle_match", False),
        "exact_dcd_vehicle_listing_yuan": quote.get(
            "exact_dcd_vehicle_listing_yuan"
        ),
        "exact_dcd_vehicle_sku_id": quote.get("exact_dcd_vehicle_sku_id"),
        "exact_dcd_vehicle_distance": quote.get("exact_dcd_vehicle_distance"),
        "exact_dcd_to_market_gap_ratio": quote.get(
            "exact_dcd_to_market_gap_ratio"
        ),
    }
    for source in ("dongchedi", "autohome", "guazi"):
        part = next(
            (
                item
                for item in quote.get("sources", [])
                if str(item.get("source") or "") == source
            ),
            {},
        )
        row[f"{source}_median_yuan"] = part.get("price_median_yuan")
        row[f"{source}_count"] = part.get("matched_count", 0)
        row[f"{source}_match_level"] = part.get("match_level", "")
    return row


def _fit_calibration(root: Path, cutoff: pd.Timestamp) -> ExternalMarketCalibration:
    path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
    requested = [
        "day",
        "actual_yuan",
        "champion_pred_yuan",
        "v195_anchor_repaired_yuan",
        "pred_yuan",
        "dongchedi_median_yuan",
        "autohome_median_yuan",
        "guazi_median_yuan",
    ]
    available = set(pd.read_csv(path, nrows=0).columns)
    frame = pd.read_csv(
        path,
        usecols=[column for column in requested if column in available],
        low_memory=False,
    )
    frame["day"] = pd.to_datetime(frame.get("day"), errors="coerce")
    local_cutoff = cutoff.tz_convert("Asia/Shanghai").tz_localize(None).normalize()
    frame = frame.loc[frame["day"].lt(local_cutoff)].copy()
    base_columns = [
        column
        for column in (
            "v195_anchor_repaired_yuan",
            "champion_pred_yuan",
            "pred_yuan",
        )
        if column in frame
    ]
    frame["calibration_base_yuan"] = np.nan
    for column in base_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        frame["calibration_base_yuan"] = frame["calibration_base_yuan"].fillna(values)
    legal = (
        pd.to_numeric(frame.get("actual_yuan"), errors="coerce").between(
            3_000, 1_000_000
        )
        & frame["calibration_base_yuan"].between(3_000, 1_000_000)
    )
    return fit_external_market_calibration(
        frame.loc[legal].copy(),
        base_column="calibration_base_yuan",
        actual_column="actual_yuan",
    )


def _bounded_blend(
    base: float,
    evidence: float,
    *,
    alpha: float,
    cap_ratio: float,
) -> float:
    delta = float(np.clip(evidence - base, -cap_ratio * base, cap_ratio * base))
    return float(base + alpha * delta)


def _asking_to_transaction_ratio(listing_yuan: float) -> float:
    """Current asking-to-deal discount learned from recent legal B2C pairs."""

    if listing_yuan <= 30_000:
        return 0.965
    if listing_yuan <= 80_000:
        return 0.970
    if listing_yuan <= 200_000:
        return 0.975
    if listing_yuan <= 300_000:
        return 0.965
    return 0.950


def _condition_factor(value: Any) -> float:
    key = str(value or "UNKNOWN").strip().upper()
    return {
        "A": 1.00,
        "B": 0.97,
        "C": 0.91,
        "D": 0.83,
        "E": 0.74,
        "CLEAN": 1.00,
        "MINOR_DEFECT": 0.96,
        "MAJOR_DEFECT": 0.86,
        "UNKNOWN": 0.98,
    }.get(key, 0.98)


def _comparable_adjustment(
    payload: dict[str, Any], comparable: dict[str, Any]
) -> tuple[float, dict[str, Any]]:
    query_registration = pd.to_datetime(
        payload.get("registration_date")
        or payload.get("first_registration_date")
        or payload.get("regDate"),
        errors="coerce",
    )
    candidate_registration = pd.to_datetime(
        comparable.get("registration_date_normalized"), errors="coerce"
    )
    registration_month_delta = 0.0
    if pd.notna(query_registration) and pd.notna(candidate_registration):
        registration_month_delta = float(
            (query_registration.year - candidate_registration.year) * 12
            + query_registration.month
            - candidate_registration.month
        )
    query_mileage = _number(payload.get("mileage_km"))
    if query_mileage is None:
        mileage_wan = _number(payload.get("mileage_wan_km") or payload.get("mileage"))
        query_mileage = mileage_wan * 10_000.0 if mileage_wan is not None else None
    candidate_mileage = _number(comparable.get("mileage_km_normalized"))
    mileage_delta_wan = (
        (query_mileage - candidate_mileage) / 10_000.0
        if query_mileage is not None and candidate_mileage is not None
        else 0.0
    )
    query_transfer = _number(
        payload.get("transfer_count") or payload.get("transfer") or 0
    )
    candidate_transfer = _number(comparable.get("transfer_bucket_key"))
    transfer_delta = (
        float(query_transfer - candidate_transfer)
        if query_transfer is not None and candidate_transfer is not None
        else 0.0
    )
    registration_factor = (1.005 ** max(registration_month_delta, 0.0)) * (
        0.994 ** max(-registration_month_delta, 0.0)
    )
    mileage_factor = np.exp(-0.030 * max(mileage_delta_wan, 0.0)) * np.exp(
        0.015 * max(-mileage_delta_wan, 0.0)
    )
    transfer_factor = (0.985 ** max(transfer_delta, 0.0)) * (
        1.006 ** max(-transfer_delta, 0.0)
    )
    query_condition = (
        payload.get("condition_grade")
        or payload.get("inspection_grade")
        or payload.get("condition")
        or "UNKNOWN"
    )
    candidate_condition = comparable.get("condition_bucket_key") or "UNKNOWN"
    condition_factor = _condition_factor(query_condition) / _condition_factor(
        candidate_condition
    )
    factor = float(
        np.clip(
            registration_factor * mileage_factor * transfer_factor * condition_factor,
            0.68,
            1.28,
        )
    )
    return factor, {
        "factor": factor,
        "registration_month_delta": registration_month_delta,
        "mileage_delta_wan_km": mileage_delta_wan,
        "transfer_delta": transfer_delta,
        "registration_factor": float(registration_factor),
        "mileage_factor": float(mileage_factor),
        "transfer_factor": float(transfer_factor),
        "condition_factor": float(condition_factor),
    }


class ExternalOnDemandMaterializer:
    """Build one unseen price cell without broad-series price inheritance."""

    def __init__(
        self,
        root: Path,
        *,
        cutoff: Any,
        listing_service: Any | None = None,
        calibration: ExternalMarketCalibration | None = None,
        spread_calibration: dict[str, Any] | None = None,
        residual_price_book: DailyResidualPriceBook | None = None,
        policy: OnDemandMaterializationPolicy | None = None,
    ) -> None:
        self.root = root
        self.cutoff = _timestamp(cutoff)
        if listing_service is None:
            from services.third_party_listing_price_service import (
                ThirdPartyListingPriceService,
            )

            listing_service = ThirdPartyListingPriceService(root)
        self.listing_service = listing_service
        self.calibration = calibration or _fit_calibration(root, self.cutoff)
        self.residual_price_book = residual_price_book or DailyResidualPriceBook.load(
            root,
            cutoff=self.cutoff,
        )
        self.policy = policy or OnDemandMaterializationPolicy()
        ladder_config = load_ladder_config(root / "config/v195_price_ladder.json")
        if spread_calibration:
            ladder_config["observed_spread_budget"] = spread_calibration
        self.ladder_config = ladder_config
        self.engine = V195ProductionPricingEngine(ladder_config)
        self.manual_registry = ManualOverrideRegistry.load(
            root / "data/manual_price_book/manual_price_book_active.csv",
            as_of=self.cutoff,
            mode=EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE,
        )
        self.dcd_c2b_ratios: dict[str, float] = {}
        self.default_dcd_c2b_ratio = 0.84
        try:
            manifest = json.loads(
                (root / "models/v195_390/v195_390_unified_single_answer_price_book.json")
                .read_text(encoding="utf-8")
            )
            self.dcd_c2b_ratios = {
                str(key): float(value)
                for key, value in (manifest.get("dcd_to_c2b_ratio_by_listing_band") or {}).items()
            }
            self.default_dcd_c2b_ratio = float(
                manifest.get("default_dcd_to_c2b_ratio") or 0.84
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            pass

    def _ensure_spread_calibration(self) -> None:
        if self.ladder_config.get("observed_spread_budget"):
            return
        from .v195_daily_vehicle_knowledge import (
            build_spread_calibration_from_truth,
        )

        truth_root = self.root / "data/v195/multi_source_truth"
        b2c = pd.read_parquet(
            truth_root / "price_type=INTERNAL_B2C_TRANSACTION/part-000.parquet"
        )
        c2b = pd.read_parquet(
            truth_root / "price_type=INTERNAL_C2B_TRANSACTION/part-000.parquet"
        )
        self.ladder_config["observed_spread_budget"] = (
            build_spread_calibration_from_truth(
                b2c,
                c2b,
                cutoff=self.cutoff,
            )
        )
        self.engine = V195ProductionPricingEngine(self.ladder_config)

    def materialize(
        self,
        payload: dict[str, Any],
        *,
        fallback_b2c_yuan: float | None,
        fallback_c2b_yuan: float | None,
        comparable: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not _strict_identity_is_usable(payload):
            return {
                "knowledge_lookup_route": "MISS_INVALID_STRICT_IDENTITY",
                "quote_decision": QuoteDecision.NO_QUOTE.value,
                "reason": "MODEL_ID_MODEL_YEAR_OR_TRIM_MISSING",
            }
        self._ensure_spread_calibration()

        # A reviewed unbucketed row is the final appraiser decision for this
        # exact model/date/mileage/city/transfer/color/condition combination.
        # It must run before any statistical fallback or external-price blend.
        from .v195_daily_vehicle_knowledge import exact_seven_element_fingerprint

        exact_fingerprint = exact_seven_element_fingerprint(payload)
        manual_match = self.manual_registry.match({-1: exact_fingerprint})
        if manual_match is not None:
            values = manual_match.values
            required = {
                "suggested_listing_price",
                "listing_price_low",
                "listing_price_high",
                "expected_b2c_transaction_price",
                "b2c_transaction_low",
                "b2c_transaction_high",
                "max_c2b_acquisition_price",
                "suggested_first_offer",
                "expected_final_acquisition_price",
                "final_acquisition_low",
                "final_acquisition_high",
                "suggested_acquisition_price",
            }
            if not required.issubset(values):
                return {
                    "knowledge_lookup_route": "MANUAL_APPRAISER_EXACT_CELL_INVALID",
                    "quote_decision": QuoteDecision.NO_QUOTE.value,
                    "reason": "MANUAL_OVERRIDE_MISSING_COMPLETE_PRICE_LADDER",
                    "manual_override_id": manual_match.override_id,
                }
            field_map = {
                "recommended_listing_price_high": "listing_price_high",
                "recommended_listing_price": "suggested_listing_price",
                "recommended_listing_price_low": "listing_price_low",
                "expected_b2c_transaction_price_high": "b2c_transaction_high",
                "expected_b2c_transaction_price": "expected_b2c_transaction_price",
                "expected_b2c_transaction_price_low": "b2c_transaction_low",
                "max_c2b_acquisition_price": "max_c2b_acquisition_price",
                "expected_final_c2b_price_high": "final_acquisition_high",
                "expected_final_c2b_price": "expected_final_acquisition_price",
                "recommended_acquisition_price": "suggested_acquisition_price",
                "expected_final_c2b_price_low": "final_acquisition_low",
                "recommended_first_offer": "suggested_first_offer",
            }
            reviewed_ladder = {
                output: float(values[source]) for output, source in field_map.items()
            }
            violations = hierarchy_violations(
                reviewed_ladder,
                minimum_gap=float(
                    self.ladder_config["minimum_b2c_to_max_c2b_gap"]
                ),
            )
            if violations:
                return {
                    "knowledge_lookup_route": "MANUAL_APPRAISER_EXACT_CELL_INVALID",
                    "quote_decision": QuoteDecision.NO_QUOTE.value,
                    "reason": "MANUAL_OVERRIDE_PRICE_ORDER_INVALID",
                    "manual_override_id": manual_match.override_id,
                    "hierarchy_violations": violations,
                }
            engine_quote = self.engine.quote(
                RawPricingInputs(
                    expected_b2c_transaction_price=reviewed_ladder[
                        "expected_b2c_transaction_price"
                    ],
                    expected_final_c2b_price=reviewed_ladder[
                        "expected_final_c2b_price"
                    ],
                    external_listing_anchor=reviewed_ladder[
                        "recommended_listing_price"
                    ],
                    external_listing_dispersion=None,
                    condition_grade=str(
                        payload.get("condition_grade")
                        or payload.get("inspection_grade")
                        or payload.get("condition")
                        or "UNKNOWN"
                    ),
                    confidence="HIGH",
                )
            )
            return {
                **reviewed_ladder,
                "knowledge_lookup_route": "MANUAL_APPRAISER_EXACT_CELL",
                "quote_decision": QuoteDecision.AUTO_QUOTE.value,
                "knowledge_confidence": "HIGH",
                "b2c_pricing_route": "MANUAL_EXACT_TRANSACTION_REVIEW",
                "c2b_pricing_route": "MANUAL_EXACT_TRANSACTION_AND_PROFIT_REVIEW",
                "raw_b2c_anchor_yuan": reviewed_ladder[
                    "expected_b2c_transaction_price"
                ],
                "raw_c2b_anchor_yuan": reviewed_ladder[
                    "expected_final_c2b_price"
                ],
                "listing_price_yuan": reviewed_ladder[
                    "recommended_listing_price"
                ],
                "external_b2c_proxy_yuan": None,
                "external_source_count": 0,
                "external_same_year_source_count": 0,
                "external_source_dispersion": None,
                "external_anchor_confidence": "RECORDED_IN_REVIEW_LEDGER",
                "external_is_asking_price": True,
                "manual_override_flag": True,
                "manual_override": json.dumps(
                    {
                        "override_id": manual_match.override_id,
                        "version": manual_match.version,
                        "reason": manual_match.reason,
                        "canonical_key": exact_fingerprint,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "source_evidence_refs": json.dumps(
                    {
                        "manual_override_id": manual_match.override_id,
                        "review_reason": manual_match.reason,
                        "exact_seven_element_fingerprint": exact_fingerprint,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "raw_prices": json.dumps(
                    reviewed_ladder, ensure_ascii=False, sort_keys=True
                ),
                "projected_prices": json.dumps(
                    reviewed_ladder, ensure_ascii=False, sort_keys=True
                ),
                "adjustment_amount": json.dumps(
                    {field: 0.0 for field in reviewed_ladder},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "business_cost_inputs": engine_quote["cost_inputs"],
                "requested_final_c2b_price": reviewed_ladder[
                    "expected_final_c2b_price"
                ],
                "profitable_c2b_ceiling": reviewed_ladder[
                    "max_c2b_acquisition_price"
                ],
                "hierarchy_violation_count": 0,
                "constraint_triggered": False,
                "constraint_reason": [],
                "projection_version": "manual_appraiser_exact_ladder_v1",
            }

        fallback_b2c = _number(fallback_b2c_yuan)
        fallback_c2b = _number(fallback_c2b_yuan)
        catalog_b2c_support = _integer(
            payload.get("catalog_appraiser_b2c_support")
        )
        catalog_c2b_support = _integer(
            payload.get("catalog_appraiser_c2b_support")
        )
        catalog_c2b_recency = _number(
            payload.get("catalog_appraiser_c2b_recency_days")
        )
        catalog_anchor_present = bool(
            payload.get("catalog_appraiser_identity_key")
        )
        registration = pd.to_datetime(
            payload.get("registration_date")
            or payload.get("first_registration_date")
            or payload.get("regDate"),
            errors="coerce",
        )
        cutoff_local = self.cutoff.tz_convert("Asia/Shanghai").tz_localize(None)
        vehicle_age_years = (
            (cutoff_local - registration).days / 365.25
            if pd.notna(registration)
            else 99.0
        )
        comparable = comparable or {}
        comparable_distance = _number(comparable.get("knowledge_comparable_distance"))
        comparable_factor, comparable_adjustment = _comparable_adjustment(
            payload, comparable
        ) if comparable else (1.0, {})
        comparable_b2c = _number(comparable.get("expected_b2c_transaction_price"))
        comparable_c2b = _number(comparable.get("expected_final_c2b_price"))
        if comparable_b2c is not None:
            comparable_b2c *= comparable_factor
        if comparable_c2b is not None:
            comparable_c2b *= comparable_factor

        try:
            listing_quote = self.listing_service.quote(payload)
        except Exception as exc:
            listing_quote = {
                "enabled": False,
                "reason": f"THREE_SOURCE_RETRIEVAL_ERROR:{type(exc).__name__}",
                "error": str(exc),
            }
        listing = _flatten_listing_quote(listing_quote) if listing_quote.get("enabled") else {}
        external_b2c: float | None = None
        external_dispersion = _number(
            listing.get("cross_source_dispersion_ratio")
        )
        exact_dcd_listing = _number(listing.get("exact_dcd_vehicle_listing_yuan"))
        exact_dcd_gap = _number(listing.get("exact_dcd_to_market_gap_ratio"))
        exact_dcd_trusted = bool(
            exact_dcd_listing is not None
            and (exact_dcd_gap is None or exact_dcd_gap <= 0.20)
        )
        if exact_dcd_trusted:
            external_b2c = exact_dcd_listing * _asking_to_transaction_ratio(
                exact_dcd_listing
            )
        elif listing:
            calibration_base = fallback_b2c or _number(
                listing.get("listing_price_yuan")
            )
            proxy_input = pd.DataFrame(
                [
                    {
                        "day": self.cutoff.tz_convert("Asia/Shanghai").date(),
                        "calibration_base_yuan": calibration_base,
                        **listing,
                    }
                ]
            )
            proxy = calibrated_external_proxy(
                proxy_input,
                self.calibration,
                base_column="calibration_base_yuan",
            ).iloc[0]
            external_b2c = _number(proxy.get("external_b2c_proxy_yuan"))
            if external_dispersion is None:
                external_dispersion = _number(
                    proxy.get("external_source_dispersion")
                )

        b2c = fallback_b2c
        b2c_route = "MODEL_FALLBACK_L5" if b2c is not None else ""
        strong_comparable = bool(
            comparable_b2c is not None
            and comparable_distance is not None
            and comparable_distance <= self.policy.strong_comparable_max_distance
            and (
                _number(comparable.get("b2c_internal_recency_days"))
                if _number(comparable.get("b2c_internal_recency_days")) is not None
                else 9_999.0
            ) <= self.policy.strong_comparable_max_recency_days
            and str(comparable.get("b2c_pricing_route") or "").startswith("INTERNAL_")
        )
        if b2c is None and strong_comparable:
            b2c = comparable_b2c
            b2c_route = "STRICT_MODEL_YEAR_COMPARABLE_ADJUSTED"
        elif b2c is not None and strong_comparable:
            b2c = _bounded_blend(
                b2c,
                comparable_b2c,
                alpha=self.policy.comparable_blend,
                cap_ratio=self.policy.comparable_cap_ratio,
            )
            b2c_route = "MODEL_PLUS_STRICT_COMPARABLE_GUARD"

        source_count = _integer(listing.get("source_count"))
        same_year_source_count = _integer(listing.get("same_year_source_count"))
        listing_confidence = str(listing.get("listing_confidence") or "").upper()
        external_high = bool(
            external_b2c is not None
            and source_count >= 2
            and same_year_source_count >= 2
            and external_dispersion is not None
            and external_dispersion <= self.policy.auto_quote_max_external_dispersion
        )
        external_medium = bool(
            external_b2c is not None
            and (same_year_source_count >= 1 or exact_dcd_trusted)
            and listing_confidence in {"HIGH", "MEDIUM"}
        )
        external_primary_without_internal = bool(
            catalog_b2c_support == 0
            and not strong_comparable
            and vehicle_age_years <= 3.0
            and external_b2c is not None
            and (external_high or exact_dcd_trusted)
        )
        if external_primary_without_internal:
            b2c = external_b2c
            b2c_route = "CALIBRATED_STRICT_EXTERNAL_PRIMARY_NO_INTERNAL_B2C"
        elif b2c is None and external_b2c is not None:
            b2c = external_b2c
            b2c_route = "CALIBRATED_STRICT_THREE_SOURCE_ONLY"
        elif b2c is not None and exact_dcd_trusted:
            b2c = _bounded_blend(
                b2c,
                external_b2c,
                alpha=0.80 if catalog_b2c_support <= 3 else 0.60,
                cap_ratio=0.25,
            )
            b2c_route += "+LIVE_EXACT_DCD_VEHICLE_PRIMARY_GUARD"
        elif (
            b2c is not None
            and external_b2c is not None
            and catalog_anchor_present
            and 0 < catalog_b2c_support <= 3
            and external_high
        ):
            b2c = _bounded_blend(
                b2c,
                external_b2c,
                alpha=0.50,
                cap_ratio=0.25,
            )
            b2c_route += "+SPARSE_INTERNAL_STRONG_EXTERNAL_GUARD"
        elif (
            b2c is not None
            and external_b2c is not None
            and catalog_anchor_present
            and 3 < catalog_b2c_support <= 7
            and external_high
        ):
            b2c = _bounded_blend(
                b2c,
                external_b2c,
                alpha=0.35,
                cap_ratio=0.20,
            )
            b2c_route += "+LIMITED_INTERNAL_EXTERNAL_GUARD"
        elif b2c is not None and external_high:
            b2c = _bounded_blend(
                b2c,
                external_b2c,
                alpha=self.policy.high_external_blend,
                cap_ratio=self.policy.high_external_cap_ratio,
            )
            b2c_route += "+HIGH_THREE_SOURCE_GUARD"
        elif b2c is not None and external_medium:
            if exact_dcd_trusted:
                b2c = _bounded_blend(
                    b2c,
                    external_b2c,
                    alpha=0.60 if catalog_b2c_support <= 3 else 0.45,
                    cap_ratio=0.20,
                )
                b2c_route += "+EXACT_DCD_VEHICLE_TRANSACTION_GUARD"
            else:
                b2c = _bounded_blend(
                    b2c,
                    external_b2c,
                    alpha=self.policy.medium_external_blend,
                    cap_ratio=self.policy.medium_external_cap_ratio,
                )
                b2c_route += "+MEDIUM_THREE_SOURCE_GUARD"

        residual_correction = self.residual_price_book.correction(
            "B2C",
            payload.get("model_id") or payload.get("modelId"),
        )
        if b2c is not None and exact_dcd_trusted:
            # A current same-vehicle/near-exact listing is more current than a
            # model-level residual. Keep the transaction estimate below its
            # asking price.
            b2c = min(b2c, float(exact_dcd_listing) * 0.995)
            b2c_route += "+LIVE_EXACT_LISTING_HIERARCHY_GUARD"
        elif b2c is not None and not external_primary_without_internal:
            b2c *= residual_correction.factor
            b2c_route += "+TMINUS1_RESIDUAL_PRICE_BOOK"

        c2b = None
        c2b_route = ""
        if b2c is not None:
            from .v195_daily_vehicle_knowledge import _spread_ratio

            model_id = payload.get("model_id") or payload.get("modelId")
            spread = _spread_ratio(
                b2c,
                self.ladder_config.get("observed_spread_budget", {}),
                "spread_ratio_median",
                model_id,
            )
            c2b = b2c * (1.0 - spread)
            c2b_route = "B2C_MINUS_MODEL_SHRUNK_CONFIRMED_SPREAD"
            if (
                fallback_b2c is None
                and fallback_c2b is None
                and _number(listing.get("listing_price_yuan")) is not None
            ):
                listing_value = float(_number(listing.get("listing_price_yuan")))
                band = str(
                    int(
                        np.digitize(
                            [listing_value],
                            [30_000, 50_000, 80_000, 120_000, 200_000, 300_000],
                        )[0]
                    )
                )
                external_c2b = listing_value * self.dcd_c2b_ratios.get(
                    band, self.default_dcd_c2b_ratio
                )
                c2b = min(c2b, external_c2b)
                c2b_route += "+CALIBRATED_LISTING_TO_C2B_EXTERNAL_ONLY"
            direct_c2b = fallback_c2b
            if direct_c2b is None and strong_comparable:
                direct_c2b = comparable_c2b
            if direct_c2b is not None:
                direct_alpha = self.policy.c2b_direct_evidence_blend
                if (
                    catalog_anchor_present
                    and catalog_c2b_support >= 3
                    and catalog_c2b_recency is not None
                    and catalog_c2b_recency <= 120
                ):
                    direct_alpha = (
                        1.0
                        if catalog_c2b_support >= 3
                        and catalog_c2b_recency <= 90
                        else 0.75
                    )
                if direct_alpha >= 1.0:
                    c2b = float(direct_c2b)
                else:
                    c2b = _bounded_blend(
                        c2b,
                        direct_c2b,
                        alpha=direct_alpha,
                        cap_ratio=0.15
                        if direct_alpha > self.policy.c2b_direct_evidence_blend
                        else self.policy.c2b_direct_evidence_cap_ratio,
                    )
                c2b_route += "+BOUNDED_DIRECT_ACCEPTANCE_EVIDENCE"
            c2b_residual = self.residual_price_book.correction("C2B", model_id)
            c2b *= c2b_residual.factor
            c2b_route += "+TMINUS1_RESIDUAL_PRICE_BOOK"
            c2b = min(c2b, b2c * 0.985)

        if b2c is None or c2b is None or b2c <= 0 or c2b <= 0:
            return {
                "knowledge_lookup_route": "MISS_WITHOUT_PRICE_EVIDENCE",
                "quote_decision": QuoteDecision.NO_QUOTE.value,
                "listing_evidence": listing_quote,
                "comparable_evidence": comparable,
            }

        consensus_gap = (
            abs(external_b2c - fallback_b2c) / fallback_b2c
            if external_b2c is not None and fallback_b2c is not None
            else None
        )
        if strong_comparable and fallback_b2c is not None and fallback_c2b is not None:
            knowledge_confidence = "MEDIUM"
        elif external_high and fallback_b2c is not None and fallback_c2b is not None:
            knowledge_confidence = "MEDIUM"
        else:
            knowledge_confidence = "LOW"
        auto_quote = bool(
            external_high
            and fallback_b2c is not None
            and fallback_c2b is not None
            and consensus_gap is not None
            and consensus_gap <= self.policy.auto_quote_consensus_gap_ratio
            and strong_comparable
        )
        quote_decision = (
            QuoteDecision.AUTO_QUOTE.value
            if auto_quote
            else QuoteDecision.LOW_CONFIDENCE.value
            if knowledge_confidence == "MEDIUM"
            else QuoteDecision.MANUAL_REVIEW.value
        )
        quote = self.engine.quote(
            RawPricingInputs(
                expected_b2c_transaction_price=float(b2c),
                expected_final_c2b_price=float(c2b),
                external_listing_anchor=_number(listing.get("listing_price_yuan")),
                external_listing_dispersion=external_dispersion,
                condition_grade=str(
                    payload.get("condition_grade")
                    or payload.get("inspection_grade")
                    or payload.get("condition")
                    or "UNKNOWN"
                ),
                confidence=knowledge_confidence,
            )
        )
        result = {
            **{field: quote[field] for field in ORDERED_FIELDS},
            "knowledge_lookup_route": "ON_DEMAND_STRICT_PRICE_CELL",
            "quote_decision": quote_decision,
            "knowledge_confidence": knowledge_confidence,
            "b2c_pricing_route": b2c_route,
            "c2b_pricing_route": c2b_route,
            "raw_b2c_anchor_yuan": float(b2c),
            "raw_c2b_anchor_yuan": float(c2b),
            "listing_price_yuan": _number(listing.get("listing_price_yuan")),
            "exact_dcd_vehicle_match": exact_dcd_trusted,
            "exact_dcd_vehicle_listing_yuan": exact_dcd_listing,
            "exact_dcd_vehicle_sku_id": listing.get("exact_dcd_vehicle_sku_id"),
            "external_b2c_proxy_yuan": external_b2c,
            "external_source_count": source_count,
            "external_same_year_source_count": same_year_source_count,
            "external_source_dispersion": external_dispersion,
            "external_anchor_confidence": listing_confidence or "MISSING",
            "external_is_asking_price": True,
            "residual_correction": json.dumps(
                residual_correction.__dict__, ensure_ascii=False, sort_keys=True
            ),
            "comparable_adjustment": json.dumps(
                comparable_adjustment, ensure_ascii=False, sort_keys=True
            ),
            "source_evidence_refs": json.dumps(
                {
                    "external": listing_quote,
                    "comparable_cell_id": comparable.get("knowledge_cell_id"),
                    "comparable_distance": comparable_distance,
                    "level5_fallback_used": bool(
                        fallback_b2c is not None or fallback_c2b is not None
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            "raw_prices": json.dumps(
                quote["raw_prices"], ensure_ascii=False, sort_keys=True
            ),
            "projected_prices": json.dumps(
                quote["projected_prices"], ensure_ascii=False, sort_keys=True
            ),
            "adjustment_amount": json.dumps(
                quote["adjustment_amount"], ensure_ascii=False, sort_keys=True
            ),
            "business_cost_inputs": quote["cost_inputs"],
            "requested_final_c2b_price": quote["requested_final_c2b_price"],
            "profitable_c2b_ceiling": quote["profitable_c2b_ceiling"],
            "c2b_profitability_clamp_used": quote[
                "c2b_profitability_clamp_used"
            ],
            "b2c_anchor_repair_used": quote["b2c_anchor_repair_used"],
            "b2c_anchor_repair_reason": quote["b2c_anchor_repair_reason"],
            "constraint_triggered": quote["constraint_triggered"],
            "constraint_reason": json.dumps(
                quote["constraint_reason"], ensure_ascii=False
            ),
            "projection_version": quote["projection_version"],
            "hierarchy_violation_count": len(
                hierarchy_violations(
                    quote["projected_prices"],
                    minimum_gap=float(
                        self.ladder_config["minimum_b2c_to_max_c2b_gap"]
                    ),
                )
            ),
            "data_cutoff": self.cutoff.isoformat(),
            "evaluation_mode": "PRODUCTION_DAILY_KNOWLEDGE",
            "same_series_year_primary_anchor": False,
        }
        return result
