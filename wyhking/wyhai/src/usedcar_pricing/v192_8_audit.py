from __future__ import annotations

import json
from typing import Any, Iterable

import pandas as pd


SCENARIO_STATUSES = {
    "SUCCESS",
    "NO_RETRIEVED_CANDIDATE",
    "NO_ELIGIBLE_CANDIDATE",
    "NO_PRICE_RESULT",
    "MODEL_FAILURE",
}


def canonical_ids(values: Iterable[Any]) -> list[str]:
    return sorted(
        {
            str(value)
            for value in values
            if value is not None and str(value).strip()
        }
    )


def candidate_change(
    original: Iterable[Any],
    counterfactual: Iterable[Any],
) -> dict[str, Any]:
    original_ids = canonical_ids(original)
    counterfactual_ids = canonical_ids(counterfactual)
    original_set = set(original_ids)
    counterfactual_set = set(counterfactual_ids)
    union = original_set | counterfactual_set
    overlap = original_set & counterfactual_set
    return {
        "original_candidate_ids": json.dumps(
            original_ids, ensure_ascii=False
        ),
        "counterfactual_candidate_ids": json.dumps(
            counterfactual_ids, ensure_ascii=False
        ),
        "added_count": len(counterfactual_set - original_set),
        "removed_count": len(original_set - counterfactual_set),
        "overlap_count": len(overlap),
        "overlap_ratio": len(overlap) / len(union) if union else 1.0,
    }


def scenario_status(
    *,
    attempted: bool,
    retrieved_count: int,
    eligible_count: int,
    price: Any,
    guard_price: Any,
    model_failure: bool = False,
) -> str:
    if not attempted or model_failure:
        return "MODEL_FAILURE"
    if retrieved_count <= 0:
        return "NO_RETRIEVED_CANDIDATE"
    if eligible_count <= 0:
        return "NO_ELIGIBLE_CANDIDATE"
    if pd.isna(price):
        return "NO_PRICE_RESULT"
    if pd.isna(guard_price):
        return "MODEL_FAILURE"
    return "SUCCESS"


def temporal_safety_flags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    knowledge = pd.to_datetime(
        result["knowledge_available_at"], errors="coerce"
    )
    transaction = pd.to_datetime(
        result["candidate_transaction_time"], errors="coerce"
    )
    query_time = pd.to_datetime(result["query_time"], errors="coerce")
    result["future_evidence_flag"] = (
        knowledge.gt(query_time) | transaction.ge(query_time)
    ).astype(int)
    result["target_candidate_flag"] = (
        result["candidate_id"].astype(str)
        == result["original_query_id"].astype(str)
    ).astype(int)
    candidate_lifecycle = result[
        "candidate_lifecycle_id"
    ].fillna("").astype(str)
    query_lifecycle = result["query_lifecycle_id"].fillna("").astype(str)
    result["same_lifecycle_flag"] = (
        candidate_lifecycle.ne("")
        & query_lifecycle.ne("")
        & candidate_lifecycle.eq(query_lifecycle)
    ).astype(int)
    candidate_vehicle = result[
        "candidate_vehicle_id"
    ].fillna("").astype(str)
    query_vehicle = result["query_vehicle_id"].fillna("").astype(str)
    result["same_vehicle_flag"] = (
        candidate_vehicle.ne("")
        & query_vehicle.ne("")
        & candidate_vehicle.eq(query_vehicle)
    ).astype(int)
    duplicate_key = candidate_lifecycle.where(
        candidate_lifecycle.ne(""),
        result["candidate_id"].astype(str),
    )
    result["duplicate_candidate_lifecycle_flag"] = (
        result.assign(_candidate_key=duplicate_key)
        .duplicated(["query_id", "_candidate_key"], keep=False)
        .astype(int)
    )
    return result
