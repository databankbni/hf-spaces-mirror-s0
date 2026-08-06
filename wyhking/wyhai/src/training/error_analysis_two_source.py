from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.training.evaluate_models_two_source import add_eval_columns, build_group_metrics


DEFAULT_GROUPS = [
    "source_dataset",
    "sale_price_source",
    "price_bucket",
    "city",
    "brand",
    "series",
    "guide_price_match_level",
    "rag_confidence",
    "rag_match_level",
    "energy_type_inferred",
    "has_real_car_age",
]


def write_error_analysis(prediction_csv: str | Path, target_col: str, output_csv: str | Path) -> pd.DataFrame:
    df = pd.read_csv(prediction_csv)
    metrics = build_group_metrics(df, [c for c in DEFAULT_GROUPS if c in df.columns], target_col)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output_csv, index=False, encoding="utf-8-sig")
    return metrics


def write_top_errors(prediction_csv: str | Path, target_col: str, output_csv: str | Path, n: int = 200) -> pd.DataFrame:
    df = pd.read_csv(prediction_csv)
    scored = add_eval_columns(df, target_col)
    top = scored.sort_values("ape", ascending=False).head(n)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(output_csv, index=False, encoding="utf-8-sig")
    return top

