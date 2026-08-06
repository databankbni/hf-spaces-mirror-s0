"""B2C anchor repair with temporally selected external evidence policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


SELECTION_START = pd.Timestamp("2026-06-26")
TEST_START = pd.Timestamp("2026-07-03")


@dataclass(frozen=True)
class AnchorRepairPolicy:
    version: str
    min_source_count: int
    max_source_dispersion: float
    min_proxy_uplift_ratio: float
    alpha: float
    cap_ratio: float
    selection_b2c_mape: float
    selection_b2c_mape_ceiling: float
    selection_inversion_before: int
    selection_inversion_after: int
    selection_b2c_coverage: float
    selection_c2b_coverage: float
    selection_rule: str


def mape(actual: pd.Series, predicted: np.ndarray | pd.Series) -> float:
    actual_values = pd.to_numeric(actual, errors="coerce").to_numpy(dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    return float(np.mean(np.abs(predicted_values - actual_values) / actual_values))


def wmape(actual: pd.Series, predicted: np.ndarray | pd.Series) -> float:
    actual_values = pd.to_numeric(actual, errors="coerce").to_numpy(dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    return float(np.abs(predicted_values - actual_values).sum() / actual_values.sum())


def apply_anchor_repair(
    frame: pd.DataFrame,
    proxy: pd.DataFrame,
    policy: AnchorRepairPolicy | dict[str, Any],
    *,
    base_column: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = asdict(policy) if isinstance(policy, AnchorRepairPolicy) else policy
    base = pd.to_numeric(frame[base_column], errors="coerce").to_numpy(dtype=float)
    candidate = pd.to_numeric(proxy["external_b2c_proxy_yuan"], errors="coerce").to_numpy(dtype=float)
    source_count = pd.to_numeric(proxy["external_source_count"], errors="coerce").fillna(0).to_numpy()
    dispersion = pd.to_numeric(proxy["external_source_dispersion"], errors="coerce").to_numpy(dtype=float)
    dispersion_safe = (source_count < 2) | (
        np.isfinite(dispersion) & (dispersion <= float(values["max_source_dispersion"]))
    )
    applied = (
        np.isfinite(candidate)
        & np.isfinite(base)
        & (source_count >= int(values["min_source_count"]))
        & dispersion_safe
        & (candidate / base >= 1.0 + float(values["min_proxy_uplift_ratio"]))
    )
    raw_delta = float(values["alpha"]) * np.clip(
        candidate - base,
        0.0,
        float(values["cap_ratio"]) * base,
    )
    delta = np.where(applied, raw_delta, 0.0)
    repaired = np.where(applied, base + delta, base)
    return repaired, applied, delta


def _select_policy(
    b2c_tune: pd.DataFrame,
    b2c_proxy: pd.DataFrame,
    c2b_selection: pd.DataFrame,
    c2b_proxy: pd.DataFrame,
) -> tuple[AnchorRepairPolicy, pd.DataFrame]:
    base_b2c_mape = mape(b2c_tune["actual_yuan"], b2c_tune["champion_pred_yuan"])
    ceiling = base_b2c_mape + 0.0002
    inversion_before = int(
        (c2b_selection["actual_yuan"] > c2b_selection["b2c_transaction_pred_yuan"]).sum()
    )
    rows: list[dict[str, Any]] = []
    for min_source_count in (1, 2):
        for max_dispersion in (0.12, 0.18, 0.25):
            for uplift in (0.00, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.12):
                for alpha in (0.15, 0.25, 0.35, 0.50, 0.65, 0.80, 1.00):
                    for cap in (0.02, 0.03, 0.05, 0.08, 0.12, 0.20, 0.30):
                        trial = {
                            "min_source_count": min_source_count,
                            "max_source_dispersion": max_dispersion,
                            "min_proxy_uplift_ratio": uplift,
                            "alpha": alpha,
                            "cap_ratio": cap,
                        }
                        b2c_pred, b2c_applied, _ = apply_anchor_repair(
                            b2c_tune, b2c_proxy, trial, base_column="champion_pred_yuan"
                        )
                        c2b_anchor, c2b_applied, _ = apply_anchor_repair(
                            c2b_selection,
                            c2b_proxy,
                            trial,
                            base_column="b2c_transaction_pred_yuan",
                        )
                        score = mape(b2c_tune["actual_yuan"], b2c_pred)
                        inversion_after = int((c2b_selection["actual_yuan"] > c2b_anchor).sum())
                        rows.append(
                            {
                                **trial,
                                "selection_b2c_mape": score,
                                "selection_b2c_mape_ceiling": ceiling,
                                "eligible_under_b2c_ceiling": score <= ceiling,
                                "selection_inversion_before": inversion_before,
                                "selection_inversion_after": inversion_after,
                                "selection_b2c_coverage": float(b2c_applied.mean()),
                                "selection_c2b_coverage": float(c2b_applied.mean()),
                            }
                        )
    selection = pd.DataFrame(rows)
    eligible = selection.loc[selection["eligible_under_b2c_ceiling"]].copy()
    if eligible.empty:
        raise RuntimeError("No anchor policy satisfied the B2C safety ceiling")
    selected = eligible.sort_values(
        [
            "selection_inversion_after",
            "selection_b2c_mape",
            "selection_c2b_coverage",
            "alpha",
            "cap_ratio",
        ],
        ascending=[True, True, True, True, True],
        kind="stable",
    ).iloc[0]
    policy = AnchorRepairPolicy(
        version="v195_b2c_anchor_repair_v1",
        min_source_count=int(selected["min_source_count"]),
        max_source_dispersion=float(selected["max_source_dispersion"]),
        min_proxy_uplift_ratio=float(selected["min_proxy_uplift_ratio"]),
        alpha=float(selected["alpha"]),
        cap_ratio=float(selected["cap_ratio"]),
        selection_b2c_mape=float(selected["selection_b2c_mape"]),
        selection_b2c_mape_ceiling=float(selected["selection_b2c_mape_ceiling"]),
        selection_inversion_before=int(selected["selection_inversion_before"]),
        selection_inversion_after=int(selected["selection_inversion_after"]),
        selection_b2c_coverage=float(selected["selection_b2c_coverage"]),
        selection_c2b_coverage=float(selected["selection_c2b_coverage"]),
        selection_rule=(
            "Minimize C2B inversion on the selection window subject to B2C selection MAPE "
            "being no more than 0.02 percentage points above its baseline; never use test labels."
        ),
    )
    return policy, selection


def _metrics(
    frame: pd.DataFrame,
    before: np.ndarray | pd.Series,
    after: np.ndarray,
    applied: np.ndarray,
) -> dict[str, Any]:
    actual = frame["actual_yuan"]
    before_values = np.asarray(before, dtype=float)
    after_values = np.asarray(after, dtype=float)
    before_ape = np.abs(before_values - actual.to_numpy(dtype=float)) / actual.to_numpy(dtype=float)
    after_ape = np.abs(after_values - actual.to_numpy(dtype=float)) / actual.to_numpy(dtype=float)
    return {
        "n": int(len(frame)),
        "before_mape": mape(actual, before_values),
        "after_mape": mape(actual, after_values),
        "before_wmape": wmape(actual, before_values),
        "after_wmape": wmape(actual, after_values),
        "before_p50_ape": float(np.quantile(before_ape, 0.50)),
        "after_p50_ape": float(np.quantile(after_ape, 0.50)),
        "before_p90_ape": float(np.quantile(before_ape, 0.90)),
        "after_p90_ape": float(np.quantile(after_ape, 0.90)),
        "repair_count": int(applied.sum()),
        "repair_coverage": float(applied.mean()),
    }


def run_anchor_repair(
    root: Path,
    output_dir: Path,
    audit_csv: Path,
    repair_table: Path,
    model_dir: Path,
) -> dict[str, Any]:
    b2c_path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
    c2b_path = root / "results/features/v194_367_c2b_strict_trim_oof_replay.csv"
    b2c = pd.read_csv(b2c_path, low_memory=False)
    c2b = pd.read_csv(c2b_path, low_memory=False)
    b2c["day"] = pd.to_datetime(b2c["day"], errors="coerce").dt.normalize()
    c2b["day"] = pd.to_datetime(c2b["day"], errors="coerce").dt.normalize()
    b2c_train = b2c.loc[b2c["day"] < SELECTION_START].copy()
    b2c_tune = b2c.loc[(b2c["day"] >= SELECTION_START) & (b2c["day"] < TEST_START)].copy()
    b2c_test = b2c.loc[b2c["day"] >= TEST_START].copy()
    c2b_selection = c2b.loc[c2b["day"] < TEST_START].copy()
    c2b_test = c2b.loc[c2b["day"] >= TEST_START].copy()

    selection_calibration = fit_external_market_calibration(
        b2c_train, base_column="champion_pred_yuan", actual_column="actual_yuan"
    )
    b2c_tune_proxy = calibrated_external_proxy(
        b2c_tune, selection_calibration, base_column="champion_pred_yuan"
    )
    c2b_selection_proxy = calibrated_external_proxy(
        c2b_selection, selection_calibration, base_column="b2c_transaction_pred_yuan"
    )
    policy, selection_grid = _select_policy(
        b2c_tune, b2c_tune_proxy, c2b_selection, c2b_selection_proxy
    )

    pretest = pd.concat([b2c_train, b2c_tune], ignore_index=True, sort=False)
    final_calibration = fit_external_market_calibration(
        pretest, base_column="champion_pred_yuan", actual_column="actual_yuan"
    )
    b2c_test_proxy = calibrated_external_proxy(
        b2c_test, final_calibration, base_column="champion_pred_yuan"
    )
    c2b_test_proxy = calibrated_external_proxy(
        c2b_test, final_calibration, base_column="b2c_transaction_pred_yuan"
    )
    b2c_repaired, b2c_applied, b2c_delta = apply_anchor_repair(
        b2c_test, b2c_test_proxy, policy, base_column="champion_pred_yuan"
    )
    c2b_repaired, c2b_applied, c2b_delta = apply_anchor_repair(
        c2b_test, c2b_test_proxy, policy, base_column="b2c_transaction_pred_yuan"
    )

    b2c_metrics = _metrics(
        b2c_test,
        b2c_test["champion_pred_yuan"].to_numpy(dtype=float),
        b2c_repaired,
        b2c_applied,
    )
    inversion_before = c2b_test["actual_yuan"].to_numpy(dtype=float) > c2b_test[
        "b2c_transaction_pred_yuan"
    ].to_numpy(dtype=float)
    inversion_after = c2b_test["actual_yuan"].to_numpy(dtype=float) > c2b_repaired

    query_uid = c2b_test.get("_trace_id", c2b_test.get("raw_index", c2b_test.index)).astype(str)
    audit = pd.DataFrame(
        {
            "query_uid": query_uid,
            "day": c2b_test["day"].astype(str),
            "brand": c2b_test.get("brand", ""),
            "series": c2b_test.get("series", ""),
            "trim": c2b_test.get("trim", ""),
            "model_id": c2b_test.get("model_id"),
            "old_b2c_anchor": c2b_test["b2c_transaction_pred_yuan"].to_numpy(dtype=float),
            "actual_c2b": c2b_test["actual_yuan"].to_numpy(dtype=float),
            "external_b2c_proxy": c2b_test_proxy["external_b2c_proxy_yuan"].to_numpy(dtype=float),
            "external_source_count": c2b_test_proxy["external_source_count"].to_numpy(dtype=int),
            "external_source_dispersion": c2b_test_proxy["external_source_dispersion"].to_numpy(dtype=float),
            "repaired_b2c_anchor": c2b_repaired,
            "repair_delta": c2b_delta,
            "repair_applied": c2b_applied,
            "inversion_before": inversion_before,
            "inversion_after": inversion_after,
        }
    )
    audit["repair_reason"] = np.where(
        audit["repair_applied"],
        "CALIBRATED_EXTERNAL_LISTING_CONSENSUS_ABOVE_OLD_ANCHOR",
        "NO_SAFE_UPWARD_REPAIR_EVIDENCE",
    )
    audit["anchor_status"] = np.select(
        [
            audit["inversion_before"] & ~audit["inversion_after"],
            audit["inversion_after"],
            audit["repair_applied"],
        ],
        [
            "REPAIRED_ABOVE_ACTUAL_C2B_POST_HOC",
            "ANCHOR_UNRELIABLE_POST_HOC",
            "REPAIRED_SAFE_POST_HOC",
        ],
        default="UNCHANGED_SAFE_POST_HOC",
    )
    audit["constraint_safe_to_apply_post_hoc"] = ~audit["inversion_after"]
    audit["evaluation_mode"] = "PRODUCTION_DAILY_KNOWLEDGE"
    audit["future_c2b_label_used_for_prediction"] = False
    audit["actual_c2b_used_only_for_post_hoc_audit"] = True
    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    repair_table.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_csv, index=False, encoding="utf-8-sig")
    audit.to_parquet(repair_table, index=False)

    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    selection_grid.to_csv(
        output_dir / "b2c_anchor_repair_policy_selection.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (model_dir / "v195_external_market_calibration.json").write_text(
        json.dumps(final_calibration.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (model_dir / "v195_b2c_anchor_repair.policy.json").write_text(
        json.dumps(asdict(policy), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    inversion_report = {
        "schema_version": "v195.b2c_anchor_inversion.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_window": ["2026-06-26", "2026-07-02"],
        "test_window": ["2026-07-03", "2026-07-09"],
        "selection": {
            "n": int(len(c2b_selection)),
            "before_count": policy.selection_inversion_before,
            "after_count": policy.selection_inversion_after,
            "repair_coverage": policy.selection_c2b_coverage,
        },
        "test": {
            "n": int(len(c2b_test)),
            "before_count": int(inversion_before.sum()),
            "before_rate": float(inversion_before.mean()),
            "after_count": int(inversion_after.sum()),
            "after_rate": float(inversion_after.mean()),
            "resolved_count": int((inversion_before & ~inversion_after).sum()),
            "remaining_unreliable_count": int(inversion_after.sum()),
            "repair_count": int(c2b_applied.sum()),
            "repair_coverage": float(c2b_applied.mean()),
        },
        "constraint_policy": (
            "Remaining unreliable anchors must not force C2B downward. They route to anchor repair, "
            "manual review, or a lower-confidence price-book level before hierarchy projection."
        ),
        "audit_csv": str(audit_csv),
        "repair_table": str(repair_table),
    }
    acceptance_checks = {
        "external_listing_not_target": True,
        "test_labels_excluded_from_selection": True,
        "anchor_never_lowered": bool(
            np.isfinite(b2c_delta).all()
            and np.isfinite(c2b_delta).all()
            and (b2c_delta >= -1e-9).all()
            and (c2b_delta >= -1e-9).all()
        ),
        "source_dispersion_guard_enabled": bool(policy.max_source_dispersion <= 0.25),
        "b2c_holdout_not_worse": bool(
            b2c_metrics["after_mape"] <= b2c_metrics["before_mape"]
            and b2c_metrics["after_wmape"] <= b2c_metrics["before_wmape"]
        ),
    }
    backtest = {
        "schema_version": "v195.b2c_anchor_repair_backtest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": asdict(policy),
        "source_calibration": final_calibration.to_dict(),
        "CLEAN_ROLLING_EVAL": {
            "status": "NOT_STAGE5_CERTIFIED",
            "repair_enabled": False,
            "reason": (
                "The available DCD/Autohome/Guazi snapshots are current snapshots and are marked "
                "historical-backtest disabled. They cannot be replayed before observed_at."
            ),
            "baseline_latest7_mape": b2c_metrics["before_mape"],
        },
        "PRODUCTION_DAILY_KNOWLEDGE": {
            "status": "OFFLINE_CHALLENGER_NOT_DEPLOYED",
            "test_window": ["2026-07-03", "2026-07-09"],
            "metrics": b2c_metrics,
            "external_listing_used_as_target": False,
            "test_labels_used_for_policy_selection": False,
            "meets_b2c_under_5pct": bool(b2c_metrics["after_mape"] < 0.05),
            "meets_b2c_4_7pct_safety_target": bool(b2c_metrics["after_mape"] <= 0.047),
        },
        "POST_HOC_ORACLE": {
            "status": "NOT_RUN_IN_STAGE2",
            "may_not_replace_clean_report": True,
        },
        "acceptance": {
            **acceptance_checks,
            "status": "PASS" if all(acceptance_checks.values()) else "FAIL",
        },
    }
    for payload, name in (
        (inversion_report, "b2c_anchor_inversion_report.json"),
        (backtest, "b2c_anchor_repair_backtest.json"),
        (final_calibration.to_dict(), "source_listing_calibration_report.json"),
    ):
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {
        "inversion_report": inversion_report,
        "backtest": backtest,
        "calibration": final_calibration.to_dict(),
    }
