from __future__ import annotations

import numpy as np
import pandas as pd


def apply_human_review_rules(
    df: pd.DataFrame,
    pred_col: str = "pred_price",
    companion_pred_col: str | None = None,
) -> pd.DataFrame:
    out = df.copy()
    reasons: list[list[str]] = [[] for _ in range(len(out))]

    def add(mask, reason: str) -> None:
        idx = np.where(mask.fillna(False).to_numpy() if hasattr(mask, "fillna") else np.asarray(mask))[0]
        for i in idx:
            reasons[i].append(reason)

    if "rag_confidence" in out.columns:
        add(out["rag_confidence"].astype(str).isin(["low", "no_match"]), "可比样本低置信或无匹配")
    if "guide_price_match_level" in out.columns:
        add(out["guide_price_match_level"].astype(str).eq("unmatched"), "指导价未匹配")
    if "model_sample_count" in out.columns:
        add(pd.to_numeric(out["model_sample_count"], errors="coerce").fillna(0) < 5, "车型样本数少于5")
    add(pd.to_numeric(out[pred_col], errors="coerce") < 50_000, "预测价低于5万")
    add(pd.to_numeric(out[pred_col], errors="coerce") > 500_000, "预测价高于50万")
    if "rag_top5_median_price" in out.columns:
        rag = pd.to_numeric(out["rag_top5_median_price"], errors="coerce")
        pred = pd.to_numeric(out[pred_col], errors="coerce")
        add((rag > 1000) & ((pred - rag).abs() / rag > 0.25), "预测价与可比样本中位数偏差超过25%")
    if "guide_price_mid_wan" in out.columns:
        guide = pd.to_numeric(out["guide_price_mid_wan"], errors="coerce") * 10_000
        pred = pd.to_numeric(out[pred_col], errors="coerce")
        add((guide > 1000) & ((pred / guide < 0.15) | (pred / guide > 1.5)), "预测价与指导价比例异常")
    if "age_for_training" in out.columns:
        age = pd.to_numeric(out["age_for_training"], errors="coerce")
        add((age < 0) | (age > 20), "车龄异常")
    if companion_pred_col and companion_pred_col in out.columns:
        pred = pd.to_numeric(out[pred_col], errors="coerce")
        comp = pd.to_numeric(out[companion_pred_col], errors="coerce")
        add(pred < comp * 0.97, "B2C预测价低于C2B预测价")
    if "sale_price_source" in out.columns:
        add(out["sale_price_source"].astype(str).eq("定价师首次销售价"), "销售价来源为定价师首次销售价")

    out["human_review_reasons"] = ["；".join(r) for r in reasons]
    out["need_human_review"] = out["human_review_reasons"].astype(bool)
    return out

