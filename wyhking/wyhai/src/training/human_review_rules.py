from __future__ import annotations

import numpy as np
import pandas as pd


def apply_human_review_rules(df: pd.DataFrame, pred_col: str, target_name: str) -> pd.DataFrame:
    out = df.copy()
    reasons = []
    for _, row in out.iterrows():
        row_reasons = []
        if str(row.get("rag_confidence", "no_match")) in {"low", "no_match", "nan"}:
            row_reasons.append("RAG低置信或无匹配")
        if str(row.get("guide_price_match_level", "unmatched")) == "unmatched":
            row_reasons.append("指导价未匹配")
        if float(row.get("model_sample_count", 0) or 0) < 5:
            row_reasons.append("车型样本少于5条")
        price = row.get(pred_col)
        if pd.notna(price):
            if price < 50_000:
                row_reasons.append("低价车误差风险")
            if price > 500_000:
                row_reasons.append("高价车误差风险")
        rag_med = row.get("rag_top5_median_price")
        if pd.notna(price) and pd.notna(rag_med) and rag_med > 1000:
            if abs(price - rag_med) / rag_med > 0.25:
                row_reasons.append("预测价与可比样本中位价差异过大")
        gp = row.get("guide_price_mid_wan")
        if pd.notna(price) and pd.notna(gp) and gp > 0:
            ratio = (price / 10000) / gp
            if ratio < 0.15 or ratio > 1.2:
                row_reasons.append("预测价与指导价比例异常")
        if pd.notna(row.get("car_age_proxy")) and (row.get("car_age_proxy") < 0 or row.get("car_age_proxy") > 20):
            row_reasons.append("车龄proxy异常")
        reasons.append("；".join(row_reasons))
    out["human_review_reasons"] = reasons
    out["need_human_review"] = out["human_review_reasons"].astype(str).str.len() > 0
    return out

