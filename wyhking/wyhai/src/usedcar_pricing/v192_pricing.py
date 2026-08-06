from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd


LEVEL_INDEX = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (values > 0) & (weights > 0)
    if not valid.any():
        return np.nan
    values = values[valid]
    weights = weights[valid]
    order = np.argsort(values, kind="stable")
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    return float(values[np.searchsorted(cumulative, quantile * cumulative[-1], side="left")])


def candidate_weights(group: pd.DataFrame) -> pd.DataFrame:
    result = group.copy()
    score = pd.to_numeric(result["ranker_score"], errors="coerce").fillna(-999).to_numpy(dtype=float)
    ranker_weight = np.exp(np.clip(score - np.nanmax(score), -20, 0))
    price = pd.to_numeric(result["adjusted_candidate_price"], errors="coerce").to_numpy(dtype=float)
    log_price = np.log(np.clip(price, 1, None))
    median = np.nanmedian(log_price)
    mad = np.nanmedian(np.abs(log_price - median))
    scale = max(mad * 1.4826, 0.03)
    outlier_z = np.abs(log_price - median) / scale
    outlier_penalty = np.exp(-np.maximum(outlier_z - 2.5, 0.0))
    raw = (
        ranker_weight
        * pd.to_numeric(result["time_decay"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["source_quality"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["retrieval_level_base"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["distance_penalty"], errors="coerce").fillna(0).to_numpy()
        * outlier_penalty
    )
    if raw.sum() <= 0:
        raw = np.ones(len(result), dtype=float)
    result["ranker_weight"] = ranker_weight
    result["outlier_penalty"] = outlier_penalty
    result["raw_pricing_weight"] = raw
    result["normalized_pricing_weight"] = raw / raw.sum()
    return result


def local_regression_price(group: pd.DataFrame) -> tuple[float, dict[str, Any] | None]:
    if len(group) < 5:
        return np.nan, None
    features = pd.DataFrame(
        {
            "age": pd.to_numeric(group["age_years"], errors="coerce"),
            "mileage": pd.to_numeric(group["mileage_wan_km"], errors="coerce"),
            "transfer": pd.to_numeric(group["transfer_count"], errors="coerce"),
            "city_match": pd.to_numeric(group["city_match"], errors="coerce"),
            "color_match": pd.to_numeric(group["color_match"], errors="coerce"),
            "condition_match": pd.to_numeric(group["condition_match"], errors="coerce"),
        }
    ).fillna(0.0)
    target = np.log(pd.to_numeric(group["adjusted_candidate_price"], errors="coerce").clip(lower=1))
    weights = pd.to_numeric(group["normalized_pricing_weight"], errors="coerce").fillna(0).to_numpy()
    if np.unique(target.round(6)).size < 2:
        return float(np.exp(target.iloc[0])), {
            "constant_log_price": float(target.iloc[0]),
            "feature_columns": list(features.columns),
        }
    x = features.to_numpy(dtype=float)
    y = target.to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    sqrt_weight = np.sqrt(np.maximum(weights, 1e-6))
    weighted_design = design * sqrt_weight[:, None]
    weighted_target = y * sqrt_weight
    penalty = np.eye(design.shape[1]) * 2.0
    penalty[0, 0] = 0.0
    coefficients_all = np.linalg.solve(
        weighted_design.T @ weighted_design + penalty,
        weighted_design.T @ weighted_target,
    )
    query = pd.DataFrame(
        [
            {
                "age": float(group["query_age_years"].iloc[0] or 0),
                "mileage": float(group["query_mileage_wan_km"].iloc[0] or 0),
                "transfer": float(group["query_transfer_count"].iloc[0] or 0),
                "city_match": 1.0,
                "color_match": 1.0,
                "condition_match": 1.0,
            }
        ]
    )
    query_vector = np.r_[1.0, query.iloc[0].to_numpy(dtype=float)]
    prediction_log = float(query_vector @ coefficients_all)
    return float(np.exp(prediction_log)), {
        "intercept": float(coefficients_all[0]),
        "coefficients": {
            column: float(value)
            for column, value in zip(features.columns, coefficients_all[1:])
        },
        "query_features": {column: float(query.iloc[0][column]) for column in query.columns},
        "feature_columns": list(features.columns),
    }


def query_statistical_prices(
    group: pd.DataFrame,
    top_k: int,
    *,
    compute_local: bool,
) -> tuple[dict[str, Any], pd.DataFrame]:
    top = group.sort_values("ranker_score", ascending=False, kind="stable").head(top_k).copy()
    weighted = candidate_weights(top)
    prices = pd.to_numeric(weighted["adjusted_candidate_price"], errors="coerce").to_numpy(dtype=float)
    weights = pd.to_numeric(weighted["normalized_pricing_weight"], errors="coerce").to_numpy(dtype=float)
    order = np.argsort(prices)
    trim_start = int(math.floor(len(prices) * 0.10))
    trim_end = max(trim_start + 1, int(math.ceil(len(prices) * 0.90)))
    trimmed = prices[order][trim_start:trim_end]
    p25, p50, p75 = np.nanquantile(prices, [0.25, 0.50, 0.75])
    local_price, local_trace = local_regression_price(weighted) if compute_local else (np.nan, None)
    result = {
        "query_id": str(group["query_id"].iloc[0]),
        "query_time": group["query_time"].iloc[0],
        "actual_price": float(group["query_actual_price"].iloc[0]),
        "brand": group["query_brand"].iloc[0],
        "series": group["query_series"].iloc[0],
        "model_year": group["query_model_year"].iloc[0],
        "trim": group["query_trim"].iloc[0],
        "city": group["query_city"].iloc[0],
        "color": group["query_color"].iloc[0],
        "age_years": group["query_age_years"].iloc[0],
        "mileage_wan_km": group["query_mileage_wan_km"].iloc[0],
        "transfer_count": group["query_transfer_count"].iloc[0],
        "condition_risk_level": group["query_condition"].iloc[0],
        "candidate_count": int(len(group)),
        "pricing_candidate_count": int(len(top)),
        "candidate_price_p25": float(p25),
        "candidate_price_p50": float(p50),
        "candidate_price_p75": float(p75),
        "candidate_dispersion": float((p75 - p25) / p50) if p50 > 0 else np.nan,
        "latest_candidate_days": float(pd.to_numeric(top["days_since_transaction"], errors="coerce").min()),
        "best_retrieval_level": str(top["retrieval_level"].iloc[0]),
        "best_retrieval_level_index": int(top["retrieval_level"].map(LEVEL_INDEX).min()),
        "source_family_count": int(top["cluster_price_type"].nunique()),
        "exact_candidate_count": int(top["retrieval_level"].isin(["L0", "L1", "L2"]).sum()),
        "weighted_median": weighted_quantile(prices, weights, 0.50),
        "weighted_p40": weighted_quantile(prices, weights, 0.40),
        "trimmed_mean": float(np.mean(trimmed)) if len(trimmed) else np.nan,
        "local_regression": local_price,
        "local_regression_trace": json.dumps(local_trace, ensure_ascii=False) if local_trace else "",
        "top_k": top_k,
    }
    return result, weighted


def build_statistical_table(frame: pd.DataFrame, top_k_values: tuple[int, ...] = (5, 10, 15)) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = {}
    weight_parts = []
    for query_id, group in frame.groupby("query_id", sort=False):
        base = None
        for top_k in top_k_values:
            result, weights = query_statistical_prices(group, top_k, compute_local=top_k == 10)
            if base is None:
                base = {key: value for key, value in result.items() if key not in {"weighted_median", "weighted_p40", "trimmed_mean", "local_regression", "top_k"}}
            for method in ("weighted_median", "weighted_p40", "trimmed_mean"):
                base[f"{method}_k{top_k}"] = result[method]
            if top_k == 10:
                base["local_regression_k10"] = result["local_regression"]
                base["local_regression_trace_k10"] = result["local_regression_trace"]
            weights = weights.copy()
            weights["query_id"] = query_id
            weights["pricing_top_k"] = top_k
            weight_parts.append(
                weights[
                    [
                        "query_id",
                        "candidate_id",
                        "retrieval_level",
                        "cluster_price_type",
                        "adjusted_candidate_price",
                        "ranker_score",
                        "ranker_weight",
                        "time_decay",
                        "source_quality",
                        "retrieval_level_base",
                        "distance_penalty",
                        "outlier_penalty",
                        "raw_pricing_weight",
                        "normalized_pricing_weight",
                        "pricing_top_k",
                    ]
                ]
            )
        rows[query_id] = base
    return pd.DataFrame(rows.values()), pd.concat(weight_parts, ignore_index=True)
