from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from .v192_1_pricing import weighted_quantile


TIER_INDEX = {
    "T1_STRICT_COMPARABLE": 1,
    "T2_VALID_WITH_UNKNOWN_ENERGY": 2,
    "T3_CONTROLLED_ADJACENT": 3,
    "T4_LOOSE_FALLBACK": 4,
}


def candidate_weights(group: pd.DataFrame) -> pd.DataFrame:
    result = group.copy()
    score = pd.to_numeric(result["ranker_score"], errors="coerce").fillna(-999).to_numpy()
    ranker_weight = np.exp(np.clip(score - np.nanmax(score), -20, 0))
    prices = pd.to_numeric(result["adjusted_candidate_price"], errors="coerce").to_numpy()
    log_price = np.log(np.clip(prices, 1, None))
    center = np.nanmedian(log_price)
    mad = np.nanmedian(np.abs(log_price - center))
    scale = max(float(mad) * 1.4826, 0.03)
    outlier_penalty = np.exp(-np.maximum(np.abs(log_price - center) / scale - 2.5, 0))
    raw = (
        ranker_weight
        * pd.to_numeric(result["time_decay"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["source_quality"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["retrieval_level_base"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["distance_penalty"], errors="coerce").fillna(0).to_numpy()
        * pd.to_numeric(result["semantic_tier_penalty"], errors="coerce").fillna(0).to_numpy()
        * outlier_penalty
    )
    if raw.sum() <= 0:
        raw = np.ones(len(result), dtype=float)
    result["ranker_weight"] = ranker_weight
    result["outlier_penalty"] = outlier_penalty
    result["raw_pricing_weight"] = raw
    result["normalized_pricing_weight"] = raw / raw.sum()
    return result


def _eligible(group: pd.DataFrame, max_tier: int = 4) -> pd.DataFrame:
    result = group.copy()
    result["_tier_index"] = result["semantic_candidate_tier"].map(TIER_INDEX).fillna(99)
    result = result[result["_tier_index"].le(max_tier)].copy()
    return result.sort_values(
        ["_tier_index", "ranker_score", "days_since_transaction"],
        ascending=[True, False, True],
        kind="stable",
    )


def query_statistics(
    group: pd.DataFrame,
    top_k: int,
    *,
    max_tier: int = 4,
) -> tuple[dict[str, Any], pd.DataFrame]:
    eligible = _eligible(group, max_tier=max_tier)
    strict = eligible[eligible["_tier_index"].le(3)]
    if len(strict) >= min(5, top_k):
        top = strict.head(top_k).copy()
    else:
        top = eligible.head(top_k).copy()
    metadata = group.iloc[0]
    prefix = f"k{top_k}"
    base = {
        "query_id": str(metadata["query_id"]),
        "query_time": metadata["query_time"],
        "actual_price": float(metadata["query_actual_price"]),
        "brand": metadata["query_brand"],
        "series": metadata["query_series"],
        "model_year": metadata["query_model_year"],
        "trim": metadata["query_trim"],
        "city": metadata["query_city"],
        "color": metadata["query_color"],
        "age_years": metadata["query_age_years"],
        "mileage_wan_km": metadata["query_mileage_wan_km"],
        "transfer_count": metadata["query_transfer_count"],
        "condition_risk_level": metadata["query_condition"],
        "candidate_count": int(len(group)),
    }
    if top.empty:
        for name in (
            "pricing_candidate_count",
            "candidate_price_p25",
            "candidate_price_p50",
            "candidate_price_p75",
            "candidate_dispersion",
            "latest_candidate_days",
            "source_family_count",
            "exact_candidate_count",
            "candidate_weight_sum",
        ):
            base[f"{name}_{prefix}"] = 0 if "count" in name or "sum" in name else np.nan
        base.update(
            {
                f"best_retrieval_level_{prefix}": "",
                f"max_semantic_tier_{prefix}": "",
                f"candidate_ids_{prefix}": "[]",
                f"candidate_weights_{prefix}": "[]",
            }
        )
        for method in ("weighted_p25", "weighted_p30", "weighted_p40", "weighted_median", "trimmed_mean"):
            base[f"{method}_{prefix}"] = np.nan
        return base, top
    weighted = candidate_weights(top)
    prices = pd.to_numeric(weighted["adjusted_candidate_price"], errors="coerce").to_numpy()
    weights = pd.to_numeric(weighted["normalized_pricing_weight"], errors="coerce").to_numpy()
    p25, p50, p75 = np.nanquantile(prices, [0.25, 0.50, 0.75])
    order = np.argsort(prices)
    trim_start = int(math.floor(len(prices) * 0.10))
    trim_end = max(trim_start + 1, int(math.ceil(len(prices) * 0.90)))
    trimmed = prices[order][trim_start:trim_end]
    base.update(
        {
            f"pricing_candidate_count_{prefix}": int(len(weighted)),
            f"candidate_price_p25_{prefix}": float(p25),
            f"candidate_price_p50_{prefix}": float(p50),
            f"candidate_price_p75_{prefix}": float(p75),
            f"candidate_dispersion_{prefix}": float((p75 - p25) / p50) if p50 > 0 else np.nan,
            f"latest_candidate_days_{prefix}": float(
                pd.to_numeric(weighted["days_since_transaction"], errors="coerce").min()
            ),
            f"source_family_count_{prefix}": int(weighted["cluster_price_type"].nunique()),
            f"exact_candidate_count_{prefix}": int(
                weighted["retrieval_level"].isin(["L0", "L1", "L2"]).sum()
            ),
            f"best_retrieval_level_{prefix}": str(weighted["retrieval_level"].iloc[0]),
            f"max_semantic_tier_{prefix}": str(
                weighted.sort_values("_tier_index")["semantic_candidate_tier"].iloc[-1]
            ),
            f"candidate_ids_{prefix}": json.dumps(
                weighted["candidate_id"].astype(str).tolist(), ensure_ascii=False
            ),
            f"candidate_weights_{prefix}": json.dumps(
                [
                    {
                        "candidate_id": str(row["candidate_id"]),
                        "weight": float(row["normalized_pricing_weight"]),
                        "tier": str(row["semantic_candidate_tier"]),
                    }
                    for row in weighted.to_dict("records")
                ],
                ensure_ascii=False,
            ),
            f"candidate_weight_sum_{prefix}": float(
                weighted["normalized_pricing_weight"].sum()
            ),
            f"weighted_p25_{prefix}": weighted_quantile(prices, weights, 0.25),
            f"weighted_p30_{prefix}": weighted_quantile(prices, weights, 0.30),
            f"weighted_p40_{prefix}": weighted_quantile(prices, weights, 0.40),
            f"weighted_median_{prefix}": weighted_quantile(prices, weights, 0.50),
            f"trimmed_mean_{prefix}": float(np.mean(trimmed)) if len(trimmed) else np.nan,
        }
    )
    return base, weighted


def build_statistical_table(
    frame: pd.DataFrame,
    top_k_values: tuple[int, ...] = (5, 10, 15),
    *,
    max_tier: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    weight_parts: list[pd.DataFrame] = []
    for query_id, group in frame.groupby("query_id", sort=False):
        combined: dict[str, Any] = {}
        for top_k in top_k_values:
            result, weights = query_statistics(group, top_k, max_tier=max_tier)
            combined.update(result)
            if not weights.empty:
                weights = weights.copy()
                weights["pricing_top_k"] = top_k
                weight_parts.append(weights)
        rows.append(combined)
    return pd.DataFrame(rows), (
        pd.concat(weight_parts, ignore_index=True) if weight_parts else pd.DataFrame()
    )


def bind_selected_metadata(table: pd.DataFrame, statistical_method: str) -> pd.DataFrame:
    result = table.copy()
    match = re_method(statistical_method)
    top_k = match[1]
    suffix = f"k{top_k}"
    result["statistical_method"] = statistical_method
    result["statistical_baseline_price"] = result[statistical_method]
    for name in (
        "pricing_candidate_count",
        "candidate_price_p25",
        "candidate_price_p50",
        "candidate_price_p75",
        "candidate_dispersion",
        "latest_candidate_days",
        "source_family_count",
        "exact_candidate_count",
        "best_retrieval_level",
        "max_semantic_tier",
        "candidate_ids",
        "candidate_weights",
        "candidate_weight_sum",
    ):
        result[name] = result[f"{name}_{suffix}"]
    return result


def re_method(method: str) -> tuple[str, int]:
    if "_k" not in method:
        raise ValueError(f"Statistical method lacks TopK suffix: {method}")
    base, raw_top_k = method.rsplit("_k", 1)
    return base, int(raw_top_k)

