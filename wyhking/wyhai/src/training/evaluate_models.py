from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import PRICE_BINS, PRICE_LABELS, regression_metrics


def evaluate_predictions(df: pd.DataFrame, y_col: str, pred_col: str) -> dict:
    return regression_metrics(df[y_col].to_numpy(), df[pred_col].to_numpy())


def grouped_error(df: pd.DataFrame, y_col: str, pred_col: str, group_col: str, top_n: int | None = None) -> pd.DataFrame:
    work = df.copy()
    if group_col not in work.columns:
        return pd.DataFrame(columns=["group", "n", "MAE", "RMSE", "MAPE", "Median_APE", "P90_APE", "R2"])
    if top_n is not None and work[group_col].nunique(dropna=True) > top_n:
        top = set(work[group_col].value_counts().head(top_n).index)
        work[group_col] = work[group_col].where(work[group_col].isin(top), "其他")
    rows = []
    for key, part in work.groupby(group_col, dropna=False):
        m = regression_metrics(part[y_col], part[pred_col])
        rows.append({"group": key, **m})
    return pd.DataFrame(rows).sort_values(["n", "MAPE"], ascending=[False, True])


def add_error_columns(df: pd.DataFrame, y_col: str, pred_col: str) -> pd.DataFrame:
    out = df.copy()
    out["true_price"] = out[y_col]
    out["pred_price"] = out[pred_col]
    out["abs_error"] = (out[pred_col] - out[y_col]).abs()
    out["ape"] = out["abs_error"] / out[y_col].where(out[y_col] > 1000)
    out["price_bucket"] = pd.cut(out[y_col], bins=PRICE_BINS, labels=PRICE_LABELS, include_lowest=True)
    if "model_sample_count" in out.columns:
        out["sample_count_bucket"] = pd.cut(
            out["model_sample_count"].fillna(0),
            bins=[-1, 4, 20, 100, np.inf],
            labels=["<5", "5-20", "20-100", ">100"],
        )
    return out

