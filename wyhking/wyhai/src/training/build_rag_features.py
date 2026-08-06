from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold


@dataclass
class RagConfig:
    top_k_values: tuple[int, ...] = (1, 3, 5, 10)
    min_candidates: int = 3
    max_candidates_per_level: int = 2500
    random_state: int = 42


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if mask.sum() == 0:
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def _score_candidates(query: pd.Series, cand: pd.DataFrame) -> pd.Series:
    score = pd.Series(0.0, index=cand.index)
    if "model_id" in cand and pd.notna(query.get("model_id")):
        score += (cand["model_id"] == query["model_id"]).astype(float) * 3.0
    if "brand_series" in cand and pd.notna(query.get("brand_series")):
        score += (cand["brand_series"] == query["brand_series"]).astype(float) * 2.0
    if "series" in cand and pd.notna(query.get("series")):
        score += (cand["series"] == query["series"]).astype(float) * 1.2
    if "city" in cand and pd.notna(query.get("city")):
        score += (cand["city"] == query["city"]).astype(float) * 0.3
    if "color" in cand and pd.notna(query.get("color")):
        score += (cand["color"] == query["color"]).astype(float) * 0.1
    if "energy_type_inferred" in cand and pd.notna(query.get("energy_type_inferred")):
        score += (cand["energy_type_inferred"] == query["energy_type_inferred"]).astype(float) * 0.2

    for col, weight, scale in [
        ("car_age_proxy", 0.5, 5.0),
        ("mileage_wan_km", 0.8, 10.0),
        ("transfer_count", 0.2, 3.0),
        ("guide_price_mid_wan", 0.5, 20.0),
    ]:
        if col in cand and pd.notna(query.get(col)):
            diff = (cand[col].astype(float) - float(query[col])).abs()
            score += np.maximum(0, weight * (1 - diff / scale))
    return score


def _candidate_levels(query: pd.Series, pool: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    levels: list[tuple[str, pd.DataFrame]] = []
    if "model_id" in pool and pd.notna(query.get("model_id")):
        levels.append(("same_model_id", pool[pool["model_id"] == query["model_id"]]))
    if "brand_series_year" in pool and pd.notna(query.get("brand_series_year")):
        levels.append(("same_brand_series_year", pool[pool["brand_series_year"] == query["brand_series_year"]]))
    if {"brand_series", "model_year"}.issubset(pool.columns) and pd.notna(query.get("brand_series")) and pd.notna(query.get("model_year")):
        levels.append(
            (
                "same_brand_series_year_pm1",
                pool[
                    (pool["brand_series"] == query["brand_series"])
                    & ((pool["model_year"].astype(float) - float(query["model_year"])).abs() <= 1)
                ],
            )
        )
    if "brand_series" in pool and pd.notna(query.get("brand_series")):
        levels.append(("same_brand_series", pool[pool["brand_series"] == query["brand_series"]]))
    if "series" in pool and pd.notna(query.get("series")):
        levels.append(("same_series", pool[pool["series"] == query["series"]]))
    if "brand" in pool and pd.notna(query.get("brand")):
        levels.append(("same_brand", pool[pool["brand"] == query["brand"]]))
    return levels


def build_rag_features_for_frame(
    target_df: pd.DataFrame,
    pool_df: pd.DataFrame,
    target_col: str,
    sample_id_col: str = "pricing_order_id",
    config: RagConfig | None = None,
) -> pd.DataFrame:
    """Fast hierarchical comparable features.

    This is intentionally aggregation-first instead of brute-force pairwise
    retrieval. It preserves the no-self / OOF split behavior while keeping the
    experiment practical on ~70k rows.
    """
    config = config or RagConfig()
    pool = pool_df.copy()
    pool = pool[pool[target_col].notna() & (pool[target_col] > 1000)]

    level_keys: list[tuple[str, list[str]]] = [
        ("same_model_id", ["model_id"]),
        ("same_brand_series_year", ["brand_series_year"]),
        ("same_brand_series", ["brand_series"]),
        ("same_series", ["series"]),
        ("same_brand", ["brand"]),
    ]

    aggs = {}
    for level, keys in level_keys:
        if not set(keys).issubset(pool.columns):
            continue
        g = pool.groupby(keys, dropna=False)[target_col].agg(["count", "mean", "median", "min", "max", "std"]).reset_index()
        g = g.rename(
            columns={
                "count": f"{level}_count",
                "mean": f"{level}_mean",
                "median": f"{level}_median",
                "min": f"{level}_min",
                "max": f"{level}_max",
                "std": f"{level}_std",
            }
        )
        aggs[level] = (keys, g)

    out = target_df[[sample_id_col]].copy()
    work = target_df[[sample_id_col] + [c for _, keys in level_keys for c in keys if c in target_df.columns]].copy()
    for level, (keys, agg) in aggs.items():
        work = work.merge(agg, on=keys, how="left")

    rows = []
    for _, row in work.iterrows():
        chosen = None
        for level, _ in level_keys:
            count = row.get(f"{level}_count")
            if pd.notna(count) and count >= config.min_candidates:
                chosen = level
                break
        if chosen is None:
            chosen = "no_match"
            count = 0
            mean = median = mn = mx = std = np.nan
        else:
            count = int(row.get(f"{chosen}_count", 0) or 0)
            mean = row.get(f"{chosen}_mean")
            median = row.get(f"{chosen}_median")
            mn = row.get(f"{chosen}_min")
            mx = row.get(f"{chosen}_max")
            std = row.get(f"{chosen}_std")
        if chosen in {"same_model_id", "same_brand_series_year"} and count >= 10:
            conf, score = "high", 3.5
        elif chosen in {"same_model_id", "same_brand_series_year", "same_brand_series"} and count >= 5:
            conf, score = "medium", 2.2
        elif chosen == "no_match":
            conf, score = "no_match", 0.0
        else:
            conf, score = "low", 1.0
        rec = {
            sample_id_col: row[sample_id_col],
            "rag_match_level": chosen,
            "rag_confidence": conf,
            "rag_confidence_score": score,
            "rag_candidate_count": count,
            "rag_same_model_id_count": int(0 if pd.isna(row.get("same_model_id_count", 0)) else row.get("same_model_id_count", 0)),
            "rag_same_series_count": int(0 if pd.isna(row.get("same_series_count", 0)) else row.get("same_series_count", 0)),
            "rag_same_city_count": 0,
            "rag_distance_mean": float(1 / (1 + score)) if score else np.nan,
        }
        for k in config.top_k_values:
            top_count = min(count, k)
            rec.update(
                {
                    f"rag_top{k}_mean_price": mean,
                    f"rag_top{k}_median_price": median,
                    f"rag_top{k}_min_price": mn,
                    f"rag_top{k}_max_price": mx,
                    f"rag_top{k}_std_price": 0.0 if pd.isna(std) and top_count > 0 else std,
                    f"rag_top{k}_count": top_count,
                }
            )
        rows.append(rec)
    return pd.DataFrame(rows)


def build_oof_rag_features(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str,
    sample_id_col: str = "pricing_order_id",
    n_splits: int = 5,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    train_parts = []
    for _, idx in kf.split(train_df):
        fold_target = train_df.iloc[idx]
        pool = train_df.drop(train_df.index[idx])
        train_parts.append(build_rag_features_for_frame(fold_target, pool, target_col, sample_id_col))
    train_rag = pd.concat(train_parts, ignore_index=True)
    valid_rag = build_rag_features_for_frame(valid_df, train_df, target_col, sample_id_col)
    test_rag = build_rag_features_for_frame(test_df, train_df, target_col, sample_id_col)
    return train_rag, valid_rag, test_rag
