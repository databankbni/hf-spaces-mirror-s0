from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold


KEY_LEVELS = [
    ("same_model_id", ["model_id"]),
    ("same_brand_series_year", ["brand_series_year"]),
    ("same_brand_series", ["brand_series"]),
    ("same_series", ["series"]),
    ("same_brand", ["brand"]),
]


def _safe_weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if mask.sum() == 0:
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def _group_stats(pool: pd.DataFrame, target_col: str, keys: list[str], prefix: str) -> pd.DataFrame:
    aggs = pool.groupby(keys, dropna=False).agg(
        mean=(target_col, "mean"),
        median=(target_col, "median"),
        min=(target_col, "min"),
        max=(target_col, "max"),
        std=(target_col, "std"),
        count=(target_col, "count"),
    )
    aggs.columns = [f"{prefix}_{c}" for c in aggs.columns]
    return aggs.reset_index()


def _merge_best_level(base: pd.DataFrame, pool: pd.DataFrame, target_col: str) -> pd.DataFrame:
    out = base.copy()
    out["_rid"] = np.arange(len(out))
    result = out[["_rid"]].copy()
    result["rag_match_level"] = "no_match"
    result["rag_top10_count"] = 0.0
    result["rag_top5_count"] = 0.0
    result["rag_confidence_score"] = 0.0
    result["rag_distance_mean"] = np.nan
    price_cols = [
        "rag_top1_price", "rag_top3_mean_price", "rag_top5_mean_price", "rag_top10_mean_price",
        "rag_top5_median_price", "rag_top10_median_price", "rag_top5_min_price",
        "rag_top5_max_price", "rag_top5_std_price"
    ]
    for c in price_cols:
        result[c] = np.nan

    for level_name, keys in KEY_LEVELS:
        if not all(k in out.columns and k in pool.columns for k in keys):
            continue
        stats = _group_stats(pool, target_col, keys, level_name)
        merged = out[["_rid"] + keys].merge(stats, on=keys, how="left")
        count_col = f"{level_name}_count"
        fill_mask = (result["rag_match_level"] == "no_match") & merged[count_col].fillna(0).gt(0)
        if not fill_mask.any():
            continue
        idx = merged.loc[fill_mask, "_rid"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_match_level"] = level_name
        result.loc[result["_rid"].isin(idx), "rag_top10_count"] = merged.loc[fill_mask, count_col].clip(upper=10).to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_count"] = merged.loc[fill_mask, count_col].clip(upper=5).to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top1_price"] = merged.loc[fill_mask, f"{level_name}_median"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top3_mean_price"] = merged.loc[fill_mask, f"{level_name}_mean"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_mean_price"] = merged.loc[fill_mask, f"{level_name}_mean"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top10_mean_price"] = merged.loc[fill_mask, f"{level_name}_mean"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_median_price"] = merged.loc[fill_mask, f"{level_name}_median"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top10_median_price"] = merged.loc[fill_mask, f"{level_name}_median"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_min_price"] = merged.loc[fill_mask, f"{level_name}_min"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_max_price"] = merged.loc[fill_mask, f"{level_name}_max"].to_numpy()
        result.loc[result["_rid"].isin(idx), "rag_top5_std_price"] = merged.loc[fill_mask, f"{level_name}_std"].fillna(0).to_numpy()

    level_score = {
        "same_model_id": 0.92,
        "same_brand_series_year": 0.78,
        "same_brand_series": 0.62,
        "same_series": 0.48,
        "same_brand": 0.32,
        "no_match": 0.0,
    }
    result["rag_confidence_score"] = result["rag_match_level"].map(level_score).fillna(0.0)
    result["rag_confidence"] = pd.cut(
        result["rag_confidence_score"],
        bins=[-0.01, 0.35, 0.65, 1.0],
        labels=["low", "medium", "high"],
    ).astype(str)
    result.loc[result["rag_match_level"] == "no_match", "rag_confidence"] = "no_match"
    return result.drop(columns=["_rid"])


def _same_count(base: pd.DataFrame, pool: pd.DataFrame, keys: list[str], out_col: str) -> pd.Series:
    if not all(k in base.columns and k in pool.columns for k in keys):
        return pd.Series(np.nan, index=base.index)
    counts = pool.groupby(keys, dropna=False).size().rename(out_col).reset_index()
    merged = base[keys].merge(counts, on=keys, how="left")
    return merged[out_col].fillna(0).astype(float)


def build_rag_features_for_split(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    test: pd.DataFrame,
    target_col: str,
    random_state: int = 42,
    n_splits: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = train.reset_index(drop=True)
    valid = valid.reset_index(drop=True)
    test = test.reset_index(drop=True)

    train_feats = []
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    for _, hold_idx in kf.split(train):
        hold = train.iloc[hold_idx].reset_index(drop=True)
        pool = train.drop(index=hold_idx).reset_index(drop=True)
        feats = _merge_best_level(hold, pool, target_col)
        feats.index = hold_idx
        train_feats.append(feats)
    train_rag = pd.concat(train_feats).sort_index().reset_index(drop=True)
    valid_rag = _merge_best_level(valid, train, target_col).reset_index(drop=True)
    test_rag = _merge_best_level(test, train, target_col).reset_index(drop=True)

    for name, keys in {
        "rag_same_model_id_count": ["model_id"],
        "rag_same_series_count": ["series"],
        "rag_same_city_count": ["city"],
        "rag_same_source_count": ["source_dataset"],
    }.items():
        train_rag[name] = _same_count(train, train, keys, name).to_numpy() - 1
        valid_rag[name] = _same_count(valid, train, keys, name).to_numpy()
        test_rag[name] = _same_count(test, train, keys, name).to_numpy()

    for frame in (train_rag, valid_rag, test_rag):
        frame["rag_same_model_id_count"] = frame["rag_same_model_id_count"].clip(lower=0)
        frame["rag_distance_mean"] = 1.0 - frame["rag_confidence_score"]

    return train_rag, valid_rag, test_rag

