"""Separated evaluation modes for the v195 daily price knowledge engine."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v195_daily_vehicle_knowledge import (
    DailyKnowledgeBuildConfig,
    _load_trace_queries,
    materialize_daily_knowledge,
    prepare_knowledge_cells,
)
from .v195_price_book_schema import EvaluationMode


TARGET_COLUMNS = [
    "actual_yuan",
    "actual_yuan_store",
    "actual_c2b_yuan",
    "price_yuan",
    "price",
]


def _metric(frame: pd.DataFrame) -> dict[str, Any]:
    actual = pd.to_numeric(frame["actual_yuan"], errors="coerce")
    predicted = pd.to_numeric(frame["knowledge_prediction_yuan"], errors="coerce")
    baseline = pd.to_numeric(frame["fallback_prediction_yuan"], errors="coerce")
    valid = actual.between(3_000, 1_000_000) & predicted.between(3_000, 1_000_000)
    actual = actual.loc[valid]
    predicted = predicted.loc[valid]
    baseline = baseline.loc[valid]
    ape = (predicted - actual).abs() / actual
    baseline_ape = (baseline - actual).abs() / actual
    top_count = max(1, int(np.ceil(len(ape) * 0.10)))
    top_index = ape.nlargest(top_count).index
    top_mask = ape.index.isin(top_index)
    decision = frame.loc[valid, "quote_decision"].fillna("NO_QUOTE").astype(str)
    auto = decision.eq("AUTO_QUOTE")
    result = {
        "n": int(len(actual)),
        "coverage": float(valid.mean()),
        "baseline_mape": float(baseline_ape.mean()),
        "mape": float(ape.mean()),
        "wmape": float((predicted - actual).abs().sum() / actual.sum()),
        "median_ape": float(ape.median()),
        "p90_ape": float(ape.quantile(0.90)),
        "top10_ape_contribution": float(ape.loc[top_mask].sum() / ape.sum()),
        "remaining90_mape": float(ape.loc[~top_mask].mean()),
        "auto_quote_coverage": float(auto.mean()),
        "auto_quote_mape": (
            float(ape.loc[auto.to_numpy()].mean()) if auto.any() else None
        ),
        "low_or_manual_coverage": float(
            decision.isin(["LOW_CONFIDENCE", "MANUAL_REVIEW"]).mean()
        ),
        "no_quote_coverage": float(decision.eq("NO_QUOTE").mean()),
        "decision_counts": {
            str(key): int(value) for key, value in decision.value_counts().items()
        },
    }
    return result


def _attach_predictions(
    query: pd.DataFrame,
    knowledge: pd.DataFrame,
    *,
    side: str,
    mode: EvaluationMode,
) -> pd.DataFrame:
    prepared = prepare_knowledge_cells(query)
    prediction_column = (
        "expected_b2c_transaction_price"
        if side == "B2C"
        else "expected_final_c2b_price"
    )
    fallback_column = "fallback_b2c_yuan" if side == "B2C" else "fallback_c2b_yuan"
    evidence_columns = [
        "knowledge_cell_id",
        prediction_column,
        "quote_decision",
        "knowledge_confidence",
        "b2c_pricing_route",
        "c2b_pricing_route",
        "b2c_knowledge_level",
        "c2b_knowledge_level",
        "b2c_internal_anchor_yuan",
        "b2c_internal_low_yuan",
        "b2c_internal_high_yuan",
        "b2c_internal_count",
        "b2c_internal_recency_days",
        "c2b_internal_anchor_yuan",
        "c2b_internal_low_yuan",
        "c2b_internal_high_yuan",
        "c2b_internal_count",
        "c2b_internal_recency_days",
        "external_source_count",
        "external_source_dispersion",
        "source_evidence_refs",
    ]
    available = [column for column in evidence_columns if column in knowledge]
    result = prepared.merge(
        knowledge[available],
        on="knowledge_cell_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_knowledge"),
    )
    result["pricing_side"] = side
    result["evaluation_mode"] = mode.value
    result["knowledge_prediction_yuan"] = pd.to_numeric(
        result[prediction_column], errors="coerce"
    )
    result["fallback_prediction_yuan"] = pd.to_numeric(
        result[fallback_column], errors="coerce"
    )
    result["knowledge_hit"] = result["knowledge_prediction_yuan"].notna()
    return result


def _write_mode(
    root: Path,
    mode: EvaluationMode,
    trace: pd.DataFrame,
    report: dict[str, Any],
) -> None:
    directory = root / "artifacts/v195_production_pricing_book/stage5" / mode.value
    directory.mkdir(parents=True, exist_ok=True)
    trace.to_csv(directory / "pricing_replay_trace.csv", index=False, encoding="utf-8-sig")
    (directory / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_stage5_evaluation(
    root: Path,
    *,
    current_cutoff: Any = "2026-07-10 23:59:59+08:00",
    test_start: str = "2026-07-03",
) -> dict[str, Any]:
    truth_root = root / "data/v195/multi_source_truth"
    b2c_truth = pd.read_parquet(
        truth_root / "price_type=INTERNAL_B2C_TRANSACTION/part-000.parquet"
    )
    c2b_truth = pd.read_parquet(
        truth_root / "price_type=INTERNAL_C2B_TRANSACTION/part-000.parquet"
    )
    cutoff = pd.Timestamp(current_cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("Asia/Shanghai")
    b2c, c2b = _load_trace_queries(
        root,
        b2c_truth,
        c2b_truth,
        cutoff=cutoff.tz_convert("UTC"),
    )
    b2c = b2c.loc[b2c["day"].ge(pd.Timestamp(test_start))].copy()
    c2b = c2b.loc[c2b["day"].ge(pd.Timestamp(test_start))].copy()

    production_book = pd.read_parquet(
        root / "data/v195/snapshots/daily_vehicle_price_knowledge_full_20260710.parquet"
    )
    production_trace = pd.concat(
        [
            _attach_predictions(
                b2c,
                production_book,
                side="B2C",
                mode=EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE,
            ),
            _attach_predictions(
                c2b,
                production_book,
                side="C2B",
                mode=EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE,
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    production_report = {
        "mode": EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE.value,
        "meaning": (
            "Current T-1 knowledge replay for operational readiness. Historical labels are "
            "now confirmed knowledge; this is not clean historical generalization."
        ),
        "data_cutoff": str(current_cutoff),
        "b2c": _metric(production_trace.loc[production_trace["pricing_side"].eq("B2C")]),
        "c2b": _metric(production_trace.loc[production_trace["pricing_side"].eq("C2B")]),
        "hierarchy_violation_count": int(
            pd.to_numeric(production_book["hierarchy_violation_count"], errors="coerce")
            .fillna(0)
            .sum()
        ),
    }
    _write_mode(
        root,
        EvaluationMode.PRODUCTION_DAILY_KNOWLEDGE,
        production_trace,
        production_report,
    )

    clean_traces: list[pd.DataFrame] = []
    days = sorted(set(b2c["day"].dt.normalize()) | set(c2b["day"].dt.normalize()))
    for day in days:
        day_b2c = b2c.loc[b2c["day"].dt.normalize().eq(day)].copy()
        day_c2b = c2b.loc[c2b["day"].dt.normalize().eq(day)].copy()
        safe_queries = [
            frame.drop(columns=TARGET_COLUMNS, errors="ignore")
            for frame in (day_b2c, day_c2b)
            if not frame.empty
        ]
        day_cutoff = pd.Timestamp(day).tz_localize("Asia/Shanghai")
        knowledge = materialize_daily_knowledge(
            root,
            cutoff=day_cutoff,
            mode=EvaluationMode.CLEAN_ROLLING_EVAL,
            query_frames=safe_queries,
            config=DailyKnowledgeBuildConfig(include_full_active_universe=False),
        )
        if not day_b2c.empty:
            clean_traces.append(
                _attach_predictions(
                    day_b2c,
                    knowledge,
                    side="B2C",
                    mode=EvaluationMode.CLEAN_ROLLING_EVAL,
                )
            )
        if not day_c2b.empty:
            clean_traces.append(
                _attach_predictions(
                    day_c2b,
                    knowledge,
                    side="C2B",
                    mode=EvaluationMode.CLEAN_ROLLING_EVAL,
                )
            )
    clean_trace = pd.concat(clean_traces, ignore_index=True, sort=False)
    clean_report = {
        "mode": EvaluationMode.CLEAN_ROLLING_EVAL.value,
        "meaning": "Each day rebuilds internal knowledge and spread strictly through T-1.",
        "test_window": [str(min(days).date()), str(max(days).date())],
        "external_snapshot_policy": (
            "Current-only third-party snapshots are excluded because historical availability "
            "cannot be proven."
        ),
        "query_target_columns_removed_before_materialization": TARGET_COLUMNS,
        "b2c": _metric(clean_trace.loc[clean_trace["pricing_side"].eq("B2C")]),
        "c2b": _metric(clean_trace.loc[clean_trace["pricing_side"].eq("C2B")]),
    }
    _write_mode(
        root,
        EvaluationMode.CLEAN_ROLLING_EVAL,
        clean_trace,
        clean_report,
    )

    oracle_traces: list[pd.DataFrame] = []
    for side, query in (("B2C", b2c), ("C2B", c2b)):
        prepared = prepare_knowledge_cells(query)
        oracle = prepared.groupby("knowledge_cell_id", sort=False)["actual_yuan"].median()
        prepared["knowledge_prediction_yuan"] = prepared["knowledge_cell_id"].map(oracle)
        prepared["fallback_prediction_yuan"] = (
            prepared["fallback_b2c_yuan"] if side == "B2C" else prepared["fallback_c2b_yuan"]
        )
        prepared["quote_decision"] = "POST_HOC_ONLY"
        prepared["pricing_side"] = side
        prepared["evaluation_mode"] = EvaluationMode.POST_HOC_ORACLE.value
        oracle_traces.append(prepared)
    oracle_trace = pd.concat(oracle_traces, ignore_index=True, sort=False)
    oracle_report = {
        "mode": EvaluationMode.POST_HOC_ORACLE.value,
        "meaning": "Same-cell target medians computed with test labels; diagnostic upper bound only.",
        "may_be_used_online": False,
        "b2c": _metric(oracle_trace.loc[oracle_trace["pricing_side"].eq("B2C")]),
        "c2b": _metric(oracle_trace.loc[oracle_trace["pricing_side"].eq("C2B")]),
    }
    _write_mode(
        root,
        EvaluationMode.POST_HOC_ORACLE,
        oracle_trace,
        oracle_report,
    )

    summary = {
        "schema_version": "v195.daily_vehicle_price_knowledge.evaluation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_daily_knowledge": production_report,
        "clean_rolling_eval": clean_report,
        "post_hoc_oracle": oracle_report,
        "acceptance": {
            "production_b2c_mape_lt_5pct": production_report["b2c"]["mape"] < 0.05,
            "production_c2b_mape_lt_5pct": production_report["c2b"]["mape"] < 0.05,
            "production_full_coverage": (
                production_report["b2c"]["coverage"] == 1.0
                and production_report["c2b"]["coverage"] == 1.0
            ),
            "hierarchy_zero_violations": production_report["hierarchy_violation_count"] == 0,
            "clean_b2c_mape_lt_5pct": clean_report["b2c"]["mape"] < 0.05,
            "clean_c2b_mape_lt_5pct": clean_report["c2b"]["mape"] < 0.05,
        },
    }
    summary["acceptance"]["production_status"] = (
        "PASS"
        if all(
            summary["acceptance"][key]
            for key in (
                "production_b2c_mape_lt_5pct",
                "production_c2b_mape_lt_5pct",
                "production_full_coverage",
                "hierarchy_zero_violations",
            )
        )
        else "FAIL"
    )
    summary["acceptance"]["clean_status"] = (
        "PASS"
        if summary["acceptance"]["clean_b2c_mape_lt_5pct"]
        and summary["acceptance"]["clean_c2b_mape_lt_5pct"]
        else "NOT_YET_PASS"
    )
    stage5 = root / "artifacts/v195_production_pricing_book/stage5"
    (stage5 / "stage5_evaluation_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
