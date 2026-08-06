from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


RANDOM_STATE = 42
PRICE_BINS = [0, 50_000, 100_000, 200_000, 300_000, 500_000, np.inf]
PRICE_LABELS = ["<5万", "5-10万", "10-20万", "20-30万", "30-50万", ">50万"]


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_training_data(prepared_dir: str | Path) -> pd.DataFrame:
    prepared_dir = Path(prepared_dir)
    parquet_path = prepared_dir / "data/processed/pricing_training_wide_enriched.parquet"
    csv_path = prepared_dir / "data/processed/pricing_training_wide_enriched.csv"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f"未找到 enriched 宽表: {parquet_path} 或 {csv_path}")


def normalize_bool_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            vals = set(out[col].dropna().astype(str).str.lower().unique()[:10])
            if vals and vals <= {"true", "false", "1", "0", "nan"}:
                out[col] = out[col].map(lambda x: np.nan if pd.isna(x) else str(x).lower() in {"true", "1"})
    return out


def add_price_bucket(df: pd.DataFrame, target_col: str) -> pd.Series:
    return pd.cut(df[target_col], bins=PRICE_BINS, labels=PRICE_LABELS, include_lowest=True)


def safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true > 1000
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_pred[mask] - y_true[mask]) / y_true[mask])))


def regression_metrics(y_true: Iterable[float], y_pred: Iterable[float]) -> dict:
    y_true = np.asarray(list(y_true), dtype=float)
    y_pred = np.asarray(list(y_pred), dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred) & (y_true > 1000)
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    if len(y_true) == 0:
        return {
            "n": 0,
            "MAE": np.nan,
            "RMSE": np.nan,
            "MAPE": np.nan,
            "Median_APE": np.nan,
            "P90_APE": np.nan,
            "R2": np.nan,
        }
    err = y_pred - y_true
    ape = np.abs(err / y_true)
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "n": int(len(y_true)),
        "MAE": float(np.mean(np.abs(err))),
        "RMSE": float(np.sqrt(np.mean(err**2))),
        "MAPE": float(np.mean(ape)),
        "Median_APE": float(np.median(ape)),
        "P90_APE": float(np.quantile(ape, 0.9)),
        "R2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
    }


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if max_rows is not None:
        df = df.head(max_rows)
    if df.empty:
        return "_无数据_"
    cols = list(df.columns)
    rows = ["| " + " | ".join(map(str, cols)) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                if math.isnan(v):
                    vals.append("")
                elif abs(v) < 1:
                    vals.append(f"{v:.4f}")
                else:
                    vals.append(f"{v:.2f}")
            else:
                vals.append(str(v))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join(rows)


def write_json(path: str | Path, data: dict | list) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(value))
    return value.strip("_") or "unknown"

