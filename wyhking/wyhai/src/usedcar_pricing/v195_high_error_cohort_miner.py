"""Daily tail-error registry and review-only override candidate generator."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v195_price_book_schema import condition_bucket, stable_hash


def _bool(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=bool)
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(default)
    return values.fillna("").astype(str).str.lower().isin({"true", "1", "yes", "是"})


def _numeric(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _tail_mask(ape: pd.Series, fraction: float = 0.10) -> pd.Series:
    count = int(np.ceil(len(ape) * fraction))
    selected = ape.nlargest(count).index
    return pd.Series(ape.index.isin(selected), index=ape.index)


def _tail_summary(actual: pd.Series, predicted: pd.Series) -> dict[str, Any]:
    ape = (predicted - actual).abs() / actual
    mask = _tail_mask(ape)
    return {
        "n": int(len(ape)),
        "overall_mape": float(ape.mean()),
        "p50_ape": float(ape.quantile(0.50)),
        "p90_ape": float(ape.quantile(0.90)),
        "top10_count": int(mask.sum()),
        "top10_mape": float(ape.loc[mask].mean()),
        "top10_ape_contribution": float(ape.loc[mask].sum() / ape.sum()),
        "remaining90_mape": float(ape.loc[~mask].mean()),
    }


def _cohort(frame: pd.DataFrame) -> pd.Series:
    actual = _numeric(frame, "actual_yuan")
    repaired_b2c = _numeric(frame, "repaired_b2c_anchor")
    model_id = _numeric(frame, "model_id", 0).fillna(0)
    strict_available = _bool(frame, "strict_trim_available")
    inspection_score = _numeric(frame, "inspection_score")
    dispersion = _numeric(frame, "cross_source_dispersion_ratio")
    listing_count = _numeric(frame, "total_listing_count", 0).fillna(0)
    base = _numeric(frame, "final_prediction_yuan")
    listing = _numeric(frame, "weighted_listing_yuan_ext90")
    low_price = actual.le(30_000)
    inversion = actual.gt(repaired_b2c)
    missing_identity = model_id.le(0)
    trim_error = ~strict_available
    condition_hidden = inspection_score.isna()
    source_bias = dispersion.gt(0.25)
    market_shift = listing.notna() & base.gt(0) & (listing / base).sub(1.0).abs().gt(0.30)
    sparse = listing_count.lt(3)
    return pd.Series(
        np.select(
            [
                inversion,
                missing_identity,
                condition_hidden,
                trim_error,
                low_price,
                source_bias,
                market_shift,
                sparse,
            ],
            [
                "B2C_ANCHOR_LOW",
                "EXACT_KEY_MISSING",
                "CONDITION_HIDDEN",
                "TRIM_MATCH_ERROR",
                "LOW_PRICE_RESIDUAL_VEHICLE",
                "SOURCE_BIAS",
                "MARKET_SHIFT",
                "SPARSE_VEHICLE",
            ],
            default="UNKNOWN",
        ),
        index=frame.index,
    )


def mine_tail_errors(
    root: Path,
    output_dir: Path,
    tail_registry_path: Path,
    candidates_path: Path,
    high_error_price_book_path: Path,
    c2b_audit_path: Path,
) -> dict[str, Any]:
    c2b_path = output_dir / "v195_price_book_c2b_test_trace.csv"
    b2c_path = output_dir / "v195_price_book_b2c_test_trace.csv"
    anchor_audit_path = root / "results/audit/v195_b2c_anchor_repair_audit.csv"
    c2b = pd.read_csv(c2b_path, low_memory=False)
    b2c = pd.read_csv(b2c_path, low_memory=False)
    anchor = pd.read_csv(anchor_audit_path, low_memory=False)
    c2b["_trace_id_key"] = c2b["_trace_id"].astype(str)
    anchor["_trace_id_key"] = anchor["query_uid"].astype(str)
    c2b = c2b.merge(
        anchor[
            [
                "_trace_id_key",
                "repaired_b2c_anchor",
                "anchor_status",
                "constraint_safe_to_apply_post_hoc",
            ]
        ],
        on="_trace_id_key",
        how="left",
        validate="one_to_one",
    )
    latest_c2b = pd.read_csv(
        root / "results/traces/v195_376_c2b_segmented_ensemble_trace.csv",
        low_memory=False,
    )
    c2b["day"] = pd.to_datetime(c2b["day"], errors="coerce").dt.normalize()
    latest_c2b["day"] = pd.to_datetime(
        latest_c2b["day"], errors="coerce"
    ).dt.normalize()
    c2b = c2b.merge(
        latest_c2b[["day", "raw_index", "v195_376_c2b_pred_yuan"]],
        on=["day", "raw_index"],
        how="left",
        validate="one_to_one",
    )
    if c2b["v195_376_c2b_pred_yuan"].isna().any():
        raise RuntimeError("v195.376 C2B tail-audit coverage mismatch")
    c2b["pricing_side"] = "C2B"
    c2b["final_prediction_yuan"] = _numeric(c2b, "v195_376_c2b_pred_yuan")
    c2b["ape"] = (
        c2b["final_prediction_yuan"] - _numeric(c2b, "actual_yuan")
    ).abs() / _numeric(c2b, "actual_yuan")
    c2b["is_top10_tail"] = _tail_mask(c2b["ape"])
    c2b["error_cohort"] = _cohort(c2b)
    c2b["prediction_direction"] = np.where(
        c2b["final_prediction_yuan"] < _numeric(c2b, "actual_yuan"),
        "UNDER",
        "OVER",
    )

    b2c["pricing_side"] = "B2C"
    b2c["final_prediction_yuan"] = _numeric(b2c, "v195_price_book_b2c_pred_yuan")
    b2c["ape"] = (
        b2c["final_prediction_yuan"] - _numeric(b2c, "actual_yuan")
    ).abs() / _numeric(b2c, "actual_yuan")
    b2c["is_top10_tail"] = _tail_mask(b2c["ape"])
    b2c["error_cohort"] = np.select(
        [
            _numeric(b2c, "model_id", 0).fillna(0).le(0),
            _numeric(b2c, "inspection_score").isna(),
            _numeric(b2c, "actual_yuan").le(30_000),
            _numeric(b2c, "cross_source_dispersion_ratio").gt(0.25),
            ~b2c.get("b2c_match_level", pd.Series("", index=b2c.index)).fillna("").astype(str).str.contains("same_trim"),
        ],
        [
            "EXACT_KEY_MISSING",
            "CONDITION_HIDDEN",
            "LOW_PRICE_RESIDUAL_VEHICLE",
            "SOURCE_BIAS",
            "TRIM_MATCH_ERROR",
        ],
        default="UNKNOWN",
    )
    b2c["prediction_direction"] = np.where(
        b2c["final_prediction_yuan"] < _numeric(b2c, "actual_yuan"),
        "UNDER",
        "OVER",
    )

    registry_columns = [
        "pricing_side",
        "day",
        "raw_index",
        "brand",
        "series",
        "trim",
        "model_id",
        "model_year",
        "city",
        "inspection_grade",
        "actual_yuan",
        "final_prediction_yuan",
        "ape",
        "is_top10_tail",
        "error_cohort",
        "prediction_direction",
    ]
    registry_frames = []
    for frame in (b2c, c2b):
        selected = frame.loc[frame["is_top10_tail"]].copy()
        for column in registry_columns:
            if column not in selected:
                selected[column] = pd.NA
        selected = selected[registry_columns]
        selected["tail_error_id"] = [
            stable_hash(
                [side, day, raw_index, model_id], "tail"
            )
            for side, day, raw_index, model_id in zip(
                selected["pricing_side"],
                selected["day"],
                selected["raw_index"],
                selected["model_id"],
            )
        ]
        selected["evaluation_mode"] = "POST_HOC_ORACLE"
        selected["human_review_required"] = True
        selected["evidence_refs"] = selected["raw_index"].map(
            lambda value: json.dumps(
                {
                    "trace": str(c2b_path if frame is c2b else b2c_path),
                    "raw_index": None if pd.isna(value) else int(value),
                },
                ensure_ascii=False,
            )
        )
        registry_frames.append(selected)
    registry = pd.concat(registry_frames, ignore_index=True, sort=False)
    registry["day"] = pd.to_datetime(registry["day"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )

    c2b_top = c2b.loc[c2b["is_top10_tail"]].copy()
    c2b_top["condition_key"] = c2b_top.get(
        "inspection_grade", pd.Series("", index=c2b_top.index)
    ).map(condition_bucket)
    c2b_top["model_id_key"] = _numeric(c2b_top, "model_id", 0).fillna(0).astype(int)
    c2b_top["model_year_key"] = _numeric(c2b_top, "model_year", 0).fillna(0).astype(int)
    selection_history = pd.read_csv(
        root / "results/features/v194_367_c2b_strict_trim_oof_replay.csv",
        low_memory=False,
    )
    selection_history["day"] = pd.to_datetime(
        selection_history["day"], errors="coerce"
    ).dt.normalize()
    selection_history = selection_history.loc[
        selection_history["day"] < pd.Timestamp("2026-07-03")
    ].copy()
    selection_history["final_prediction_yuan"] = _numeric(
        selection_history, "strict_trim_c2b_pred_yuan"
    )
    selection_history["ape"] = (
        selection_history["final_prediction_yuan"]
        - _numeric(selection_history, "actual_yuan")
    ).abs() / _numeric(selection_history, "actual_yuan")
    selection_history = selection_history.loc[
        _tail_mask(selection_history["ape"])
    ].copy()
    selection_history["model_id_key"] = _numeric(
        selection_history, "model_id", 0
    ).fillna(0).astype(int)
    selection_history["model_year_key"] = _numeric(
        selection_history, "model_year", 0
    ).fillna(0).astype(int)
    selection_history["condition_key"] = selection_history.get(
        "inspection_grade", pd.Series("", index=selection_history.index)
    ).map(condition_bucket)
    selection_history["prediction_direction"] = np.where(
        selection_history["final_prediction_yuan"]
        < _numeric(selection_history, "actual_yuan"),
        "UNDER",
        "OVER",
    )
    selection_history["tail_period"] = "SELECTION"
    c2b_top["tail_period"] = "TEST"
    recurring_pool = pd.concat(
        [selection_history, c2b_top], ignore_index=True, sort=False
    )
    candidate_columns = [
        "override_candidate_id",
        "approval_status",
        "override_type",
        "key_level",
        "canonical_key",
        "model_id",
        "model_year",
        "condition_grade",
        "error_cohort",
        "tail_sample_count",
        "selection_tail_count",
        "test_tail_count",
        "direction_consistency",
        "recommended_delta_ratio",
        "recommended_delta_yuan_at_group_median",
        "supporting_actual_median_yuan",
        "supporting_prediction_median_yuan",
        "post_hoc_before_mape",
        "post_hoc_candidate_mape",
        "expected_mape_improvement_oracle",
        "risk",
        "ttl_days",
        "human_review_required",
        "evaluation_mode",
        "may_enter_active_registry_automatically",
        "reason",
        "evidence_refs",
        "created_at",
    ]
    candidates: list[dict[str, Any]] = []
    recurring_model_count = 0
    directionally_consistent_count = 0
    for keys, group in recurring_pool.groupby(
        ["model_id_key", "model_year_key"], dropna=False
    ):
        model_id, model_year = keys
        selection_count = int(group["tail_period"].eq("SELECTION").sum())
        test_count = int(group["tail_period"].eq("TEST").sum())
        if selection_count <= 0 or test_count <= 0:
            continue
        recurring_model_count += 1
        direction_counts = group["prediction_direction"].value_counts()
        direction_consistency = float(direction_counts.max() / len(group))
        if direction_consistency < 1.0:
            continue
        directionally_consistent_count += 1
        condition_values = group["condition_key"].dropna().astype(str).unique()
        condition = condition_values[0] if len(condition_values) == 1 else "UNKNOWN"
        cohort_values = group.get(
            "error_cohort", pd.Series("RECURRENT_MODEL_ERROR", index=group.index)
        ).dropna().astype(str)
        cohort = cohort_values.mode().iloc[0] if not cohort_values.empty else "RECURRENT_MODEL_ERROR"
        base = group["final_prediction_yuan"].to_numpy(dtype=float)
        actual = _numeric(group, "actual_yuan").to_numpy(dtype=float)
        raw_ratio = np.median(actual / base) - 1.0
        support = len(group)
        shrinkage = support / (support + 5.0)
        delta_ratio = float(np.clip(raw_ratio * shrinkage, -0.15, 0.15))
        candidate = base * (1.0 + delta_ratio)
        before_mape = float(np.mean(np.abs(base - actual) / actual))
        after_mape = float(np.mean(np.abs(candidate - actual) / actual))
        canonical_key = stable_hash(
            [int(model_id), int(model_year), condition], "high_error"
        )
        candidates.append(
            {
                "override_candidate_id": stable_hash(
                    [canonical_key, cohort, "2026-07-09"], "candidate"
                ),
                "approval_status": "PENDING",
                "override_type": "DELTA",
                "key_level": 3,
                "canonical_key": canonical_key,
                "model_id": int(model_id),
                "model_year": int(model_year),
                "condition_grade": condition,
                "error_cohort": cohort,
                "tail_sample_count": support,
                "selection_tail_count": selection_count,
                "test_tail_count": test_count,
                "direction_consistency": direction_consistency,
                "recommended_delta_ratio": delta_ratio,
                "recommended_delta_yuan_at_group_median": float(np.median(base) * delta_ratio),
                "supporting_actual_median_yuan": float(np.median(actual)),
                "supporting_prediction_median_yuan": float(np.median(base)),
                "post_hoc_before_mape": before_mape,
                "post_hoc_candidate_mape": after_mape,
                "expected_mape_improvement_oracle": before_mape - after_mape,
                "risk": "HIGH" if support < 3 else "MEDIUM",
                "ttl_days": 7,
                "human_review_required": True,
                "evaluation_mode": "POST_HOC_ORACLE",
                "may_enter_active_registry_automatically": False,
                "reason": f"Repeated top-10% C2B error cohort: {cohort}",
                "evidence_refs": json.dumps(
                    group["raw_index"].dropna().astype(int).tolist(), ensure_ascii=False
                ),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    candidates_frame = pd.DataFrame(candidates, columns=candidate_columns)
    if not candidates_frame.empty:
        candidates_frame = candidates_frame.sort_values(
            ["tail_sample_count", "expected_mape_improvement_oracle"],
            ascending=[False, False],
            kind="stable",
        )

    tail_registry_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    high_error_price_book_path.parent.mkdir(parents=True, exist_ok=True)
    c2b_audit_path.parent.mkdir(parents=True, exist_ok=True)
    registry.to_parquet(tail_registry_path, index=False)
    candidates_frame.to_parquet(candidates_path, index=False)
    candidates_frame.to_csv(high_error_price_book_path, index=False, encoding="utf-8-sig")
    c2b_top.to_csv(c2b_audit_path, index=False, encoding="utf-8-sig")

    c2b_summary = _tail_summary(
        _numeric(c2b, "actual_yuan"), c2b["final_prediction_yuan"]
    )
    b2c_summary = _tail_summary(
        _numeric(b2c, "actual_yuan"), b2c["final_prediction_yuan"]
    )
    report = {
        "schema_version": "v195.tail_error_registry.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": ["2026-07-03", "2026-07-09"],
        "b2c": b2c_summary,
        "c2b": c2b_summary,
        "c2b_cohort_counts": {
            str(key): int(value)
            for key, value in c2b_top["error_cohort"].value_counts().items()
        },
        "registry_rows": int(len(registry)),
        "override_candidate_rows": int(len(candidates_frame)),
        "pending_candidate_rows": int(candidates_frame["approval_status"].eq("PENDING").sum()),
        "automatic_activation_count": 0,
        "cross_window_recurring_model_count": recurring_model_count,
        "directionally_consistent_recurring_model_count": directionally_consistent_count,
        "test_tail_singleton_model_count": int(c2b_top["model_id_key"].nunique())
        - recurring_model_count,
        "outputs": {
            "tail_error_registry": str(tail_registry_path),
            "override_candidates": str(candidates_path),
            "high_error_price_book": str(high_error_price_book_path),
            "c2b_top_error10_audit": str(c2b_audit_path),
        },
        "acceptance": {
            "all_candidates_pending": bool(
                candidates_frame.empty
                or candidates_frame["approval_status"].eq("PENDING").all()
            ),
            "all_candidates_require_review": bool(
                candidates_frame.empty or candidates_frame["human_review_required"].all()
            ),
            "oracle_candidates_not_active": bool(
                candidates_frame.empty
                or ~candidates_frame["may_enter_active_registry_automatically"].any()
            ),
            "top10_rows_complete": int(c2b_top["is_top10_tail"].sum())
            == c2b_summary["top10_count"],
        },
    }
    report["acceptance"]["status"] = (
        "PASS" if all(report["acceptance"].values()) else "FAIL"
    )
    (output_dir / "tail_error_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
