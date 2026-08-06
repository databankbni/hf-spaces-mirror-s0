from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def regression_metrics(actual: pd.Series, prediction: pd.Series) -> dict[str, Any]:
    actual = pd.to_numeric(actual, errors="coerce")
    prediction = pd.to_numeric(prediction, errors="coerce")
    valid = actual.gt(0) & prediction.notna() & np.isfinite(prediction)
    actual = actual[valid]
    prediction = prediction[valid]
    if actual.empty:
        return {
            "rows": 0,
            "coverage": 0.0,
            "MAPE": np.nan,
            "WMAPE": np.nan,
            "Median_APE": np.nan,
            "P90_APE": np.nan,
            "APE_GT5_RATE": np.nan,
        }
    ape = (prediction - actual).abs() / actual
    return {
        "rows": int(valid.sum()),
        "coverage": float(valid.mean()),
        "MAPE": float(ape.mean()),
        "WMAPE": float((prediction - actual).abs().sum() / actual.sum()),
        "Median_APE": float(ape.median()),
        "P90_APE": float(ape.quantile(0.90)),
        "APE_GT5_RATE": float(ape.gt(0.05).mean()),
    }


def metric_row(
    frame: pd.DataFrame,
    prediction_column: str,
    scope: str,
    *,
    actual_column: str = "actual_price",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "scope": scope,
        "prediction_column": prediction_column,
        **regression_metrics(frame[actual_column], frame[prediction_column]),
    }
    if extra:
        result.update(extra)
    return result

