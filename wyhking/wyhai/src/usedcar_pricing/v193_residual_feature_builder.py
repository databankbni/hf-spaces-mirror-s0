from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


RESIDUAL_FEATURE_VERSION = "v193_residual_feature_builder_v1"


FEATURE_COLUMNS = [
    "statistical_baseline_price",
    "candidate_count",
    "T1_weight",
    "T2_weight",
    "T3A_weight",
    "T3B_weight",
    "T4_weight",
    "same_trim_weight",
    "same_city_weight",
    "recent_90d_weight",
    "recent_180d_weight",
    "source_family_count",
    "price_dispersion",
    "interval_width_ratio",
    "semantic_similarity_score",
    "relation_confidence",
    "dirty_data_risk_score",
    "web_evidence_count",
    "web_evidence_price_gap",
    "series_historical_error",
    "price_band_historical_error",
    "mileage",
    "vehicle_age",
    "transfer_count",
]


def build_residual_features(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    for column in FEATURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if "actual_c2b_price" in frame.columns:
        actual = pd.to_numeric(frame["actual_c2b_price"], errors="coerce")
        baseline = pd.to_numeric(frame["statistical_baseline_price"], errors="coerce")
        frame["target_residual"] = np.where((actual > 0) & (baseline > 0), actual / baseline - 1.0, np.nan)
    frame["residual_feature_version"] = RESIDUAL_FEATURE_VERSION
    return frame


def residual_policy_from_comparison(comparison: pd.DataFrame) -> dict[str, Any]:
    if comparison.empty or "variant" not in comparison.columns:
        return {"residual_enabled": False, "reason": "NO_COMPARISON"}
    base = comparison[comparison["variant"].eq("A_v192_16_baseline_only")]
    new = comparison[comparison["variant"].eq("C_v193_baseline_new_residual")]
    if base.empty or new.empty:
        return {"residual_enabled": False, "reason": "MISSING_ABLATION"}
    base_mape = float(base.iloc[0].get("MAPE", np.inf))
    new_mape = float(new.iloc[0].get("MAPE", np.inf))
    base_p90 = float(base.iloc[0].get("P90_APE", np.inf))
    new_p90 = float(new.iloc[0].get("P90_APE", np.inf))
    enabled = new_mape < base_mape * 0.98 and new_p90 <= base_p90 * 1.02
    return {
        "residual_enabled": bool(enabled),
        "reason": "ENABLED_VALIDATED_LIFT" if enabled else "DISABLED_NO_STABLE_LIFT",
        "baseline_mape": base_mape,
        "new_residual_mape": new_mape,
        "baseline_p90": base_p90,
        "new_residual_p90": new_p90,
    }

