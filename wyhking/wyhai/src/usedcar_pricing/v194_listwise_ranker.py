"""Runtime feature builder for the temporal v194 listwise candidate ranker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CATEGORICAL = [
    "query_series", "query_trim_key", "query_city", "query_condition", "query_grade",
    "candidate_city", "candidate_condition", "candidate_grade", "retrieval_level", "match_profile",
]
NUMERIC = [
    "candidate_log_price", "query_year", "query_age", "query_mileage", "query_transfer",
    "candidate_year", "candidate_age", "candidate_mileage", "candidate_transfer",
    "query_inspection_score", "candidate_inspection_score", "inspection_score_gap",
    "age_gap", "mileage_gap", "transfer_gap", "days_since", "city_match", "color_match",
    "condition_match", "same_trim", "same_model_year", "same_power_code", "same_trim_package",
    "same_powertrain", "observable_match_count", "rolling_candidate_score", "price_relative_log",
    "price_relative_abs", "price_percentile", "candidate_rank",
]
FEATURES = NUMERIC + CATEGORICAL


def _num(frame: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(frame.get(name, pd.Series(default, index=frame.index)), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def build_features(candidates: pd.DataFrame, query: dict[str, Any]) -> pd.DataFrame:
    """Create inference-only features from an as-of candidate list and query."""
    data = candidates.copy()
    if data.empty:
        return pd.DataFrame(columns=FEATURES)
    query_grade = str(query.get("inspection_grade_norm") or "missing")
    text = {
        "query_series": str(query.get("series") or ""),
        "query_trim_key": str(query.get("canonical_trim_key") or ""),
        "query_city": str(query.get("city") or ""),
        "query_condition": str(query.get("condition_risk_level_strict") or "unknown"),
        "query_grade": query_grade,
        "candidate_city": data.get("city", pd.Series("", index=data.index)),
        "candidate_condition": data.get("condition_risk_level_strict", pd.Series("unknown", index=data.index)),
        "candidate_grade": data.get("inspection_grade_norm", pd.Series("missing", index=data.index)),
        "retrieval_level": data.get("retrieval_level", pd.Series("", index=data.index)),
        "match_profile": data.get("candidate_match_profile", pd.Series("", index=data.index)),
    }
    for name, value in text.items():
        if isinstance(value, pd.Series):
            data[name] = value.fillna("missing").astype(str)
        else:
            data[name] = str(value or "missing")
    ranking_source = (
        data["heuristic_retrieval_weight"]
        if "heuristic_retrieval_weight" in data
        else data.get("final_retrieval_weight", pd.Series(0.0, index=data.index))
    )
    rank_source = data["final_rank"] if "final_rank" in data else data.get("candidate_rank", pd.Series(0.0, index=data.index))
    mapping = {
        "candidate_log_price": np.log(_num(data, "price_yuan", 1000).clip(lower=1000)),
        "query_year": _num(pd.DataFrame({"v": [query.get("model_year")] * len(data)}, index=data.index), "v"),
        "query_age": _num(pd.DataFrame({"v": [query.get("age_years")] * len(data)}, index=data.index), "v"),
        "query_mileage": _num(pd.DataFrame({"v": [query.get("mileage_wan_km")] * len(data)}, index=data.index), "v"),
        "query_transfer": _num(pd.DataFrame({"v": [query.get("transfer_count")] * len(data)}, index=data.index), "v"),
        "candidate_year": _num(data, "model_year"),
        "candidate_age": _num(data, "age_years"),
        "candidate_mileage": _num(data, "mileage_wan_km"),
        "candidate_transfer": _num(data, "transfer_count"),
        "query_inspection_score": _num(pd.DataFrame({"v": [query.get("inspection_score")] * len(data)}, index=data.index), "v", -1.0),
        "candidate_inspection_score": _num(data, "inspection_score", -1.0),
        "inspection_score_gap": (
            _num(pd.DataFrame({"v": [query.get("inspection_score")] * len(data)}, index=data.index), "v", -1.0)
            - _num(data, "inspection_score", -1.0)
        ).abs(),
        "age_gap": _num(data, "age_difference"),
        "mileage_gap": _num(data, "mileage_difference"),
        "transfer_gap": _num(data, "transfer_difference"),
        "days_since": _num(data, "days_since_transaction"),
        "city_match": _num(data, "city_match"),
        "color_match": _num(data, "color_match"),
        "condition_match": _num(data, "condition_match"),
        "same_trim": _num(data, "same_trim"),
        "same_model_year": _num(data, "same_model_year"),
        "same_power_code": _num(data, "same_power_code"),
        "same_trim_package": _num(data, "same_trim_package"),
        "same_powertrain": _num(data, "same_powertrain"),
        "observable_match_count": _num(data, "observable_match_count"),
        "rolling_candidate_score": pd.to_numeric(ranking_source, errors="coerce").fillna(0.0),
        "candidate_rank": pd.to_numeric(rank_source, errors="coerce").fillna(0.0),
    }
    for name, value in mapping.items():
        data[name] = value
    price = _num(data, "price_yuan", 1000).clip(lower=1000)
    median = price.median() if len(price) else 1000.0
    data["price_relative_log"] = np.log(price / max(float(median), 1000.0))
    data["price_relative_abs"] = data["price_relative_log"].abs()
    data["price_percentile"] = price.rank(pct=True)
    return data[FEATURES]


class V194ListwiseRanker:
    def __init__(self, model_path: Path) -> None:
        from catboost import CatBoostRanker

        self.model_path = model_path
        self.model = CatBoostRanker()
        self.model.load_model(str(model_path))

    def score(self, candidates: pd.DataFrame, query: dict[str, Any]) -> pd.Series:
        if candidates.empty:
            return pd.Series(dtype=float, index=candidates.index)
        features = build_features(candidates, query)
        return pd.Series(self.model.predict(features), index=candidates.index, dtype=float)
