from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostRanker

from .v192_1_retrieval import retrieval_feature_columns


CATEGORICAL_COLUMNS = [
    "query_brand",
    "query_series",
    "query_model_year",
    "query_trim",
    "query_city",
    "query_color",
    "query_condition",
    "retrieval_level",
    "cluster_price_type",
    "brand",
    "series",
    "model_year",
    "trim",
    "city",
    "color_norm",
    "condition_risk_level",
]


def add_pool_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    group = result.groupby("query_id", sort=False)["adjusted_candidate_price"]
    stats = group.agg(
        pool_count="size",
        pool_min="min",
        pool_p10=lambda values: values.quantile(0.10),
        pool_p25=lambda values: values.quantile(0.25),
        pool_p50="median",
        pool_p75=lambda values: values.quantile(0.75),
        pool_p90=lambda values: values.quantile(0.90),
        pool_max="max",
        pool_std="std",
    ).reset_index()
    result = result.merge(stats, on="query_id", how="left")
    result["pool_dispersion"] = (
        result["pool_p75"] - result["pool_p25"]
    ) / result["pool_p50"].replace(0, np.nan)
    result["candidate_vs_pool_median_log"] = np.log(
        pd.to_numeric(result["adjusted_candidate_price"], errors="coerce").clip(lower=1)
        / pd.to_numeric(result["pool_p50"], errors="coerce").clip(lower=1)
    )
    result["candidate_price_percentile"] = group.rank(method="average", pct=True)
    result["year_difference"] = (
        pd.to_numeric(result["model_year"], errors="coerce")
        - pd.to_numeric(result["query_model_year"], errors="coerce")
    ).abs()
    result["days_since_transaction_log"] = np.log1p(
        pd.to_numeric(result["days_since_transaction"], errors="coerce").clip(lower=0)
    )
    return result


def fit_category_maps(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    maps = {}
    for column in CATEGORICAL_COLUMNS:
        if column not in frame:
            continue
        values = frame[column].fillna("__MISSING__").astype(str)
        maps[column] = {value: index for index, value in enumerate(sorted(values.unique()), start=1)}
    return maps


def encode_features(
    frame: pd.DataFrame,
    category_maps: dict[str, dict[str, int]],
) -> tuple[pd.DataFrame, list[str]]:
    result = add_pool_features(frame)
    for column, mapping in category_maps.items():
        values = result[column].fillna("__MISSING__").astype(str)
        result[f"{column}__code"] = values.map(mapping).fillna(0).astype("int32")
    features = retrieval_feature_columns() + [
        "pool_count",
        "pool_min",
        "pool_p10",
        "pool_p25",
        "pool_p50",
        "pool_p75",
        "pool_p90",
        "pool_max",
        "pool_std",
        "pool_dispersion",
        "candidate_vs_pool_median_log",
        "candidate_price_percentile",
        "year_difference",
        "days_since_transaction_log",
    ] + [f"{column}__code" for column in category_maps]
    features = [column for column in features if column in result]
    for column in features:
        result[column] = (
            pd.to_numeric(result[column], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(-999.0)
        )
    return result, features


def deterministic_group_sample(frame: pd.DataFrame, max_groups: int = 25_000, max_rank: int = 50) -> pd.DataFrame:
    result = frame[frame["retrieval_rank"].le(max_rank)].copy()
    groups = result[["query_id", "query_time"]].drop_duplicates().sort_values("query_time")
    if len(groups) > max_groups:
        groups = groups.tail(max_groups)
    return result[result["query_id"].isin(groups["query_id"])].copy()


def sort_groups(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["query_id", "retrieval_rank"], kind="stable").reset_index(drop=True)


def group_sizes(frame: pd.DataFrame) -> list[int]:
    return frame.groupby("query_id", sort=False).size().astype(int).tolist()


def train_lightgbm_ranker(frame: pd.DataFrame, features: list[str], seed: int) -> lgb.LGBMRanker:
    train = sort_groups(frame)
    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=220,
        learning_rate=0.045,
        num_leaves=63,
        min_child_samples=100,
        subsample=0.90,
        colsample_bytree=0.85,
        reg_alpha=0.05,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=-1,
        verbosity=-1,
    )
    model.fit(
        train[features],
        train["graded_relevance"].astype(int),
        group=group_sizes(train),
    )
    return model


def train_catboost_ranker(frame: pd.DataFrame, features: list[str], seed: int) -> CatBoostRanker:
    train = sort_groups(frame)
    group_codes = pd.factorize(train["query_id"], sort=False)[0]
    model = CatBoostRanker(
        loss_function="YetiRank",
        iterations=180,
        depth=8,
        learning_rate=0.055,
        l2_leaf_reg=5.0,
        random_seed=seed,
        verbose=False,
        thread_count=-1,
        allow_writing_files=False,
    )
    model.fit(
        train[features],
        train["graded_relevance"].astype(float),
        group_id=group_codes,
    )
    return model


def dcg(relevance: np.ndarray, k: int) -> float:
    values = relevance[:k]
    if len(values) == 0:
        return 0.0
    return float(np.sum((2.0**values - 1.0) / np.log2(np.arange(2, len(values) + 2))))


def ranker_metrics(frame: pd.DataFrame, score_column: str, model_name: str, window: str) -> dict[str, Any]:
    ranked = frame.sort_values(["query_id", score_column], ascending=[True, False], kind="stable")
    recall5 = []
    recall10 = []
    ndcg10 = []
    top1_ape = []
    top10_price_ape = []
    golden_exists = []
    for _, group in ranked.groupby("query_id", sort=False):
        relevance = group["graded_relevance"].to_numpy(dtype=float)
        ideal = np.sort(relevance)[::-1]
        has_golden = bool((group["comparable_label"] == "GOLDEN_COMPARABLE").any())
        golden_exists.append(has_golden)
        recall5.append(bool((group.head(5)["comparable_label"] == "GOLDEN_COMPARABLE").any()))
        recall10.append(bool((group.head(10)["comparable_label"] == "GOLDEN_COMPARABLE").any()))
        ideal_dcg = dcg(ideal, 10)
        ndcg10.append(dcg(relevance, 10) / ideal_dcg if ideal_dcg > 0 else 0.0)
        actual = float(group["query_actual_price"].iloc[0])
        top1 = float(group["adjusted_candidate_price"].iloc[0])
        top1_ape.append(abs(top1 - actual) / actual)
        top = group.copy()
        if "semantic_valid_flag" in top:
            top = top[top["semantic_valid_flag"].eq(1)]
        if "invalid_candidate_flag" in top:
            top = top[top["invalid_candidate_flag"].ne(1)]
        top = top.head(10).copy()
        if top.empty:
            top10_price_ape.append(np.nan)
            continue
        scores = pd.to_numeric(top[score_column], errors="coerce").to_numpy(dtype=float)
        scores = np.exp(np.clip(scores - np.nanmax(scores), -20, 0))
        weights = scores * pd.to_numeric(top["time_decay"], errors="coerce").fillna(0).to_numpy()
        order = np.argsort(top["adjusted_candidate_price"].to_numpy(dtype=float))
        prices = top["adjusted_candidate_price"].to_numpy(dtype=float)[order]
        weights = weights[order]
        if weights.sum() <= 0:
            price = float(np.median(prices))
        else:
            cumulative = np.cumsum(weights)
            price = float(prices[np.searchsorted(cumulative, cumulative[-1] * 0.5)])
        top10_price_ape.append(abs(price - actual) / actual)
    return {
        "model": model_name,
        "window": window,
        "queries": int(frame["query_id"].nunique()),
        "golden_candidate_available_rate": float(np.mean(golden_exists)),
        "Recall@5": float(np.mean(recall5)),
        "Recall@10": float(np.mean(recall10)),
        "NDCG@10": float(np.mean(ndcg10)),
        "Top1_candidate_MAPE": float(np.mean(top1_ape)),
        "Top10_weighted_price_MAPE": float(np.nanmean(top10_price_ape)),
    }


def save_ranker_bundle(
    path: Path,
    model: Any,
    model_type: str,
    features: list[str],
    category_maps: dict[str, dict[str, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "model_type": model_type,
            "features": features,
            "category_maps": category_maps,
        },
        path,
    )
