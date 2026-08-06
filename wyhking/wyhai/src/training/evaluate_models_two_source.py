from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

PRICE_BINS = [0, 50_000, 100_000, 200_000, 300_000, 500_000, np.inf]
PRICE_LABELS = ["<5万", "5-10万", "10-20万", "20-30万", "30-50万", ">50万"]


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred) & (y_true > 1000)
    if mask.sum() == 0:
        return {
            "sample_count": 0,
            "MAE": np.nan,
            "RMSE": np.nan,
            "MAPE": np.nan,
            "Median_APE": np.nan,
            "P90_APE": np.nan,
            "R2": np.nan,
        }
    yt = y_true[mask]
    yp = y_pred[mask]
    err = yp - yt
    ape = np.abs(err / yt)
    ss_res = np.sum(err**2)
    ss_tot = np.sum((yt - yt.mean()) ** 2)
    return {
        "sample_count": int(mask.sum()),
        "MAE": float(np.mean(np.abs(err))),
        "RMSE": float(np.sqrt(np.mean(err**2))),
        "MAPE": float(np.mean(ape)),
        "Median_APE": float(np.median(ape)),
        "P90_APE": float(np.quantile(ape, 0.9)),
        "R2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
    }


def add_eval_columns(df: pd.DataFrame, target_col: str, pred_col: str = "pred_price") -> pd.DataFrame:
    out = df.copy()
    out["true_price"] = pd.to_numeric(out[target_col], errors="coerce")
    out[pred_col] = pd.to_numeric(out[pred_col], errors="coerce")
    out["abs_error"] = (out[pred_col] - out["true_price"]).abs()
    out["ape"] = out["abs_error"] / out["true_price"].where(out["true_price"] > 1000)
    out["price_bucket"] = pd.cut(out["true_price"], PRICE_BINS, labels=PRICE_LABELS, include_lowest=True)
    return out


def _top_or_other(s: pd.Series, top_n: int) -> pd.Series:
    top = set(s.value_counts(dropna=False).head(top_n).index.astype(str))
    return s.astype(str).where(s.astype(str).isin(top), "其他")


def build_group_metrics(df: pd.DataFrame, group_cols: list[str], target_col: str, pred_col: str = "pred_price") -> pd.DataFrame:
    rows = []
    work = add_eval_columns(df, target_col, pred_col)
    for col in group_cols:
        if col not in work.columns:
            continue
        tmp = work.copy()
        if col == "brand":
            tmp["_group"] = _top_or_other(tmp[col], 20)
        elif col == "series":
            tmp["_group"] = _top_or_other(tmp[col], 50)
        elif col == "city":
            tmp["_group"] = _top_or_other(tmp[col], 20)
        else:
            tmp["_group"] = tmp[col].astype(object).where(tmp[col].notna(), "缺失").astype(str)
        for val, part in tmp.groupby("_group", dropna=False):
            metrics = regression_metrics(part["true_price"], part[pred_col])
            rows.append({
                "group_field": col,
                "group_value": val,
                **metrics,
            })
    return pd.DataFrame(rows).sort_values(["group_field", "sample_count"], ascending=[True, False])


def format_pct(value: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value * 100:.2f}%"


def write_metrics_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
