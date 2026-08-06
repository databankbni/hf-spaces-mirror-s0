"""Evaluate and materialize the v195 six-price ladder."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v195_b2c_anchor_repair import mape, wmape
from .v195_cost_calibration import build_recent_spread_calibration
from .v195_price_ladder_solver import (
    ORDERED_FIELDS,
    business_cost_inputs,
    hierarchy_violations,
    load_ladder_config,
)
from .v195_production_pricing_engine import (
    RawPricingInputs,
    V195ProductionPricingEngine,
)


def _number(row: pd.Series, columns: list[str]) -> float | None:
    for column in columns:
        value = pd.to_numeric(row.get(column), errors="coerce")
        if pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
            return float(value)
    return None


def _external_listing_anchor(row: pd.Series) -> float | None:
    weighted = _number(
        row,
        ["weighted_listing_yuan_ext90", "source_weighted_listing_price_yuan", "listing_price_yuan"],
    )
    if weighted is not None:
        return weighted
    values = [
        value
        for value in (
            _number(row, ["dongchedi_median_yuan"]),
            _number(row, ["autohome_median_yuan"]),
            _number(row, ["guazi_median_yuan"]),
        )
        if value is not None
    ]
    return float(np.median(values)) if values else None


def _confidence(row: pd.Series) -> str:
    for column in ("listing_confidence_ext90", "listing_confidence", "confidence"):
        value = str(row.get(column) or "").upper()
        if value in {"HIGH", "MEDIUM", "LOW"}:
            return value
    return "LOW"


def _condition(row: pd.Series) -> str:
    for column in ("inspection_grade", "condition"):
        value = str(row.get(column) or "").upper()
        if value.startswith(("A", "B", "C")):
            return value[0]
    return "UNKNOWN"


def _ladder_record(
    row: pd.Series,
    *,
    engine: V195ProductionPricingEngine,
    b2c_price: float,
    c2b_price: float,
    external_listing: float | None,
    external_dispersion: float | None,
) -> dict[str, Any]:
    quote = engine.quote(
        RawPricingInputs(
            expected_b2c_transaction_price=b2c_price,
            expected_final_c2b_price=c2b_price,
            external_listing_anchor=external_listing,
            external_listing_dispersion=external_dispersion,
            condition_grade=_condition(row),
            confidence=_confidence(row),
        )
    )
    violations = hierarchy_violations(
        quote["projected_prices"],
        minimum_gap=float(engine.config["minimum_b2c_to_max_c2b_gap"]),
    )
    return {
        **{field: quote[field] for field in ORDERED_FIELDS},
        "b2c_anchor_repair_used": quote["b2c_anchor_repair_used"],
        "b2c_anchor_repair_reason": quote["b2c_anchor_repair_reason"],
        "original_b2c_anchor": quote["original_b2c_anchor"],
        "b2c_repaired_anchor": quote["b2c_repaired_anchor"],
        "constraint_triggered": quote["constraint_triggered"],
        "constraint_reason": json.dumps(quote["constraint_reason"], ensure_ascii=False),
        "raw_prices": json.dumps(quote["raw_prices"], ensure_ascii=False, sort_keys=True),
        "projected_prices": json.dumps(
            quote["projected_prices"], ensure_ascii=False, sort_keys=True
        ),
        "adjustment_amount": json.dumps(
            quote["adjustment_amount"], ensure_ascii=False, sort_keys=True
        ),
        "cost_inputs": json.dumps(quote["cost_inputs"], ensure_ascii=False, sort_keys=True),
        "projection_version": quote["projection_version"],
        "weighted_squared_adjustment": quote["weighted_squared_adjustment"],
        "hierarchy_violation_count": len(violations),
        "hierarchy_violations": json.dumps(violations, ensure_ascii=False),
        "engine_version": quote["engine_version"],
    }


def _test_artifact(
    root: Path,
    engine: V195ProductionPricingEngine,
) -> pd.DataFrame:
    trace = pd.read_csv(
        root
        / "artifacts/v195_production_pricing_book/stage3/v195_price_book_c2b_test_trace.csv",
        low_memory=False,
    )
    anchor = pd.read_csv(
        root / "results/audit/v195_b2c_anchor_repair_audit.csv", low_memory=False
    )
    latest_c2b = pd.read_csv(
        root / "results/traces/v195_376_c2b_segmented_ensemble_trace.csv",
        low_memory=False,
    )
    trace["day"] = pd.to_datetime(trace["day"], errors="coerce").dt.normalize()
    latest_c2b["day"] = pd.to_datetime(
        latest_c2b["day"], errors="coerce"
    ).dt.normalize()
    trace = trace.merge(
        latest_c2b[["day", "raw_index", "v195_376_c2b_pred_yuan"]],
        on=["day", "raw_index"],
        how="left",
        validate="one_to_one",
    )
    if trace["v195_376_c2b_pred_yuan"].isna().any():
        raise RuntimeError("v195.376 C2B production prediction coverage mismatch")
    trace["_trace_id_key"] = trace["_trace_id"].astype(str)
    anchor["_trace_id_key"] = anchor["query_uid"].astype(str)
    trace = trace.merge(
        anchor[["_trace_id_key", "repaired_b2c_anchor", "anchor_status"]],
        on="_trace_id_key",
        how="left",
        validate="one_to_one",
    )
    records: list[dict[str, Any]] = []
    for _, row in trace.iterrows():
        b2c_price = float(row["repaired_b2c_anchor"])
        c2b_price = float(row["v195_376_c2b_pred_yuan"])
        dispersion = pd.to_numeric(
            row.get("cross_source_dispersion_ext90", row.get("cross_source_dispersion_ratio")),
            errors="coerce",
        )
        record = _ladder_record(
            row,
            engine=engine,
            b2c_price=b2c_price,
            c2b_price=c2b_price,
            external_listing=_external_listing_anchor(row),
            external_dispersion=float(dispersion) if pd.notna(dispersion) else None,
        )
        record.update(
            {
                "raw_index": row.get("raw_index"),
                "query_uid": row.get("_trace_id"),
                "day": row.get("day"),
                "brand": row.get("brand"),
                "series": row.get("series"),
                "trim": row.get("trim"),
                "model_id": row.get("model_id"),
                "actual_c2b_yuan": row.get("actual_yuan"),
                "raw_c2b_model_prediction": c2b_price,
                "c2b_model_version": "v195_376_c2b_segmented_ensemble",
                "stage2_repaired_b2c_anchor": b2c_price,
                "stage2_anchor_status": row.get("anchor_status"),
                "external_listing_anchor": _external_listing_anchor(row),
                "external_listing_dispersion": (
                    float(dispersion) if pd.notna(dispersion) else np.nan
                ),
            }
        )
        records.append(record)
    return pd.DataFrame(records)


def _materialize_current_book(
    root: Path,
    engine: V195ProductionPricingEngine,
) -> pd.DataFrame:
    del engine
    pointer_path = root / "data/v195/current_daily_vehicle_price_knowledge.json"
    if not pointer_path.exists():
        raise RuntimeError(
            "Daily vehicle-price knowledge must be built before the production ladder"
        )
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    snapshot_path = Path(pointer["snapshot_path"])
    if not snapshot_path.is_absolute():
        snapshot_path = root / snapshot_path
    book = pd.read_parquet(snapshot_path)
    missing = [column for column in ORDERED_FIELDS if column not in book]
    if missing:
        raise RuntimeError(f"Daily knowledge snapshot is missing ladder fields: {missing}")
    if book[ORDERED_FIELDS].isna().any().any():
        raise RuntimeError("Daily knowledge snapshot contains incomplete price ladders")
    result = book.copy()
    result["price_ladder_status"] = "MATERIALIZED_FROM_DAILY_VEHICLE_KNOWLEDGE"
    result["production_ladder_source"] = str(snapshot_path)
    return result


def run_price_ladder_evaluation(root: Path, output_dir: Path) -> dict[str, Any]:
    config_path = root / "config/v195_price_ladder.json"
    config = load_ladder_config(config_path)
    pointer = json.loads(
        (root / "data/v195/current_daily_vehicle_price_knowledge.json").read_text(
            encoding="utf-8"
        )
    )
    production_cutoff = pd.Timestamp(pointer["data_cutoff"]).tz_convert("Asia/Shanghai")
    cost_calibration_path = root / "models/v195/v195_recent_spread_calibration.json"
    cost_calibration = build_recent_spread_calibration(
        root, cost_calibration_path, cutoff=production_cutoff
    )
    config["observed_spread_budget"] = cost_calibration
    engine = V195ProductionPricingEngine(config)
    artifact = _test_artifact(root, engine)
    current_book = _materialize_current_book(root, engine)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "constraint_projection_trace.csv"
    artifact_path = output_dir / "six_price_prediction_artifact.csv"
    artifact.to_csv(trace_path, index=False, encoding="utf-8-sig")
    artifact.to_csv(artifact_path, index=False, encoding="utf-8-sig")
    ladder_book_path = root / "data/v195/production_price_book_ladder.parquet"
    ladder_snapshot_path = (
        root
        / "data/v195/snapshots"
        / f"daily_vehicle_price_ladder_snapshot_{production_cutoff.strftime('%Y%m%d')}.parquet"
    )
    current_book.to_parquet(ladder_book_path, index=False)
    current_book.to_parquet(ladder_snapshot_path, index=False)

    actual = pd.to_numeric(artifact["actual_c2b_yuan"], errors="coerce")
    before = pd.to_numeric(artifact["raw_c2b_model_prediction"], errors="coerce")
    after = pd.to_numeric(artifact["expected_final_c2b_price"], errors="coerce")
    interval_checks = (
        artifact["recommended_listing_price_low"].le(
            artifact["recommended_listing_price"]
        )
        & artifact["recommended_listing_price"].le(
            artifact["recommended_listing_price_high"]
        )
        & artifact["expected_b2c_transaction_price_low"].le(
            artifact["expected_b2c_transaction_price"]
        )
        & artifact["expected_b2c_transaction_price"].le(
            artifact["expected_b2c_transaction_price_high"]
        )
        & artifact["expected_final_c2b_price_low"].le(
            artifact["expected_final_c2b_price"]
        )
        & artifact["expected_final_c2b_price"].le(
            artifact["expected_final_c2b_price_high"]
        )
    )
    report = {
        "schema_version": "v195.hierarchy_acceptance.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "config_status": config["status"],
        "cost_calibration_path": str(cost_calibration_path),
        "cost_calibration": cost_calibration,
        "test_rows": int(len(artifact)),
        "current_price_book_rows": int(len(current_book)),
        "hierarchy_violation_count": int(artifact["hierarchy_violation_count"].sum()),
        "interval_violation_count": int((~interval_checks).sum()),
        "constraint_trigger_count": int(artifact["constraint_triggered"].sum()),
        "b2c_anchor_repair_count": int(artifact["b2c_anchor_repair_used"].sum()),
        "c2b_before_mape": mape(actual, before),
        "c2b_after_mape": mape(actual, after),
        "c2b_before_wmape": wmape(actual, before),
        "c2b_after_wmape": wmape(actual, after),
        "expected_final_c2b_changed_rows": int((after - before).abs().gt(1e-6).sum()),
        "outputs": {
            "six_price_prediction_artifact": str(artifact_path),
            "constraint_projection_trace": str(trace_path),
            "production_price_book_ladder": str(ladder_book_path),
            "daily_vehicle_price_ladder_snapshot": str(ladder_snapshot_path),
        },
        "acceptance": {
            "hierarchy_zero_violations": int(artifact["hierarchy_violation_count"].sum()) == 0,
            "interval_zero_violations": int((~interval_checks).sum()) == 0,
            "c2b_point_not_degraded": mape(actual, after) <= mape(actual, before) + 1e-12,
            "c2b_point_preserved": int((after - before).abs().gt(1e-6).sum()) == 0,
            "all_current_cells_have_six_prices": bool(
                current_book[ORDERED_FIELDS].notna().all().all()
            ),
            "complete_projection_trace": bool(
                artifact[
                    [
                        "raw_prices",
                        "projected_prices",
                        "adjustment_amount",
                        "projection_version",
                    ]
                ].notna().all().all()
            ),
        },
    }
    report["acceptance"]["status"] = (
        "PASS" if all(report["acceptance"].values()) else "FAIL"
    )
    (output_dir / "hierarchy_acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
