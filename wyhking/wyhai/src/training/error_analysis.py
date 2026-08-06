from __future__ import annotations

from pathlib import Path

import pandas as pd

from .evaluate_models import add_error_columns, grouped_error
from .utils import ensure_dir


GROUP_SPECS = [
    ("price_bucket", None, "price_bucket"),
    ("brand", 20, "brand"),
    ("series", 50, "series"),
    ("city", 20, "city"),
    ("sample_count_bucket", None, "sample_count"),
    ("guide_price_match_level", None, "guide_price_status"),
    ("rag_confidence", None, "rag_confidence"),
    ("energy_type_inferred", None, "energy_type"),
]


def write_error_analysis(task: str, pred_df: pd.DataFrame, y_col: str, pred_col: str, output_dir: str | Path) -> dict:
    output_dir = ensure_dir(output_dir)
    work = add_error_columns(pred_df, y_col, pred_col)
    outputs = {}
    for col, top_n, suffix in GROUP_SPECS:
        if col not in work.columns:
            continue
        grouped = grouped_error(work, y_col, pred_col, col, top_n=top_n)
        path = output_dir / f"{task}_error_by_{suffix}.csv"
        grouped.to_csv(path, index=False)
        outputs[suffix] = str(path)
    wanted = [
        "pricing_order_id",
        "brand",
        "series",
        "vehicle_model",
        "model_id",
        "city",
        "model_year",
        "car_age_proxy",
        "mileage_wan_km",
        "transfer_count",
        "guide_price_mid_wan",
        "guide_price_match_level",
        "guide_price_match_confidence",
        "true_price",
        "pred_price",
        "abs_error",
        "ape",
        "rag_confidence_score",
        "need_human_review",
        "human_review_reasons",
    ]
    top_cols = [c for c in wanted if c in work.columns]
    top = work.sort_values("ape", ascending=False).head(200)[top_cols]
    top_path = output_dir / f"{task}_top_error_samples.csv"
    top.to_csv(top_path, index=False)
    outputs["top_error_samples"] = str(top_path)
    return outputs

