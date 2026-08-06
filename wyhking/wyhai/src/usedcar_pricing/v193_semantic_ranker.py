from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


RANKER_VERSION = "v193_semantic_ranker_v1"
TIER_BASE_SCORE = {
    "T1_EXACT_TRIM": 1.0,
    "T2_EXACT_UNKNOWN_FIELD": 0.86,
    "T3A_VERIFIED_ADJACENT": 0.7,
    "T3B_HEURISTIC_ADJACENT": 0.4,
    "T4_LOOSE_FALLBACK": 0.18,
    "NOT_COMPARABLE": 0.0,
}


def semantic_rank_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    rel = frame.get("relationship_type", pd.Series("T4_LOOSE_FALLBACK", index=frame.index)).fillna("T4_LOOSE_FALLBACK").astype(str)
    source = frame.get("source_family", frame.get("source_type", pd.Series("", index=frame.index))).fillna("").astype(str).str.lower()
    dirty = frame.get("dirty_flag", frame.get("runtime_dirty_flag", pd.Series(0, index=frame.index))).fillna(0).astype(int)
    days = pd.to_numeric(frame.get("days_since_transaction", frame.get("time_distance_days", pd.Series(999, index=frame.index))), errors="coerce").fillna(999)
    mileage = pd.to_numeric(frame.get("mileage_distance", pd.Series(0, index=frame.index)), errors="coerce").fillna(0).abs()
    city_match = pd.to_numeric(frame.get("city_match", pd.Series(0, index=frame.index)), errors="coerce").fillna(0)
    similarity = pd.to_numeric(frame.get("semantic_similarity_score", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    score = rel.map(TIER_BASE_SCORE).fillna(0.0).astype(float)
    score += np.minimum(0.15, similarity * 0.15)
    score += np.where(city_match.gt(0), 0.05, 0.0)
    score += np.exp(-days.clip(lower=0) / 180.0) * 0.08
    score -= np.minimum(0.12, mileage / 30.0)
    score -= np.where(source.str.contains("external|autohome|web", regex=True), 0.04, 0.0)
    score = np.where(dirty.eq(1), 0.0, score)
    frame["days_since_transaction"] = days
    frame["mileage_distance"] = mileage
    frame["v193_semantic_rank_score"] = np.round(score, 6)
    frame["can_enter_baseline_v193"] = (
        dirty.eq(0)
        & rel.isin(["T1_EXACT_TRIM", "T2_EXACT_UNKNOWN_FIELD", "T3A_VERIFIED_ADJACENT"])
        & ~source.str.contains("external_web_unverified", regex=False)
    ).astype(int)
    frame["used_for_baseline"] = frame["can_enter_baseline_v193"].astype(bool)
    frame["used_for_interval"] = (dirty.eq(0) & rel.ne("NOT_COMPARABLE")).astype(bool)
    frame["used_for_manual_reference"] = frame["used_for_interval"]
    frame["blocked_from_baseline_reason"] = np.select(
        [
            dirty.eq(1),
            rel.isin(["T3B_HEURISTIC_ADJACENT", "T4_LOOSE_FALLBACK"]),
            rel.eq("NOT_COMPARABLE"),
            source.str.contains("external_web_unverified", regex=False),
        ],
        [
            "DIRTY_DATA",
            "WEAK_SEMANTIC_RELATION",
            "NOT_COMPARABLE",
            "UNVERIFIED_EXTERNAL_WEB",
        ],
        default="",
    )
    frame["candidate_group_v193"] = np.select(
        [
            frame["used_for_baseline"],
            frame["used_for_interval"] & ~frame["used_for_baseline"],
            frame["used_for_manual_reference"],
        ],
        ["baseline_candidates", "interval_only_candidates", "manual_reference_candidates"],
        default="blocked_candidates",
    )
    frame["semantic_ranker_version"] = RANKER_VERSION
    return frame.sort_values(
        ["used_for_baseline", "v193_semantic_rank_score", "days_since_transaction", "mileage_distance"],
        ascending=[False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def evidence_strength_from_candidates(candidates: pd.DataFrame) -> float:
    if candidates.empty:
        return 0.0
    ranked = semantic_rank_candidates(candidates)
    baseline = ranked[ranked["used_for_baseline"]]
    if baseline.empty:
        return 0.0
    dispersion = 0.0
    if "c2b_converted_price" in baseline:
        price = pd.to_numeric(baseline["c2b_converted_price"], errors="coerce").dropna()
        if len(price) >= 2 and price.median() > 0:
            dispersion = float((price.quantile(0.75) - price.quantile(0.25)) / price.median())
    count_score = min(1.0, len(baseline) / 5)
    tier_score = float(baseline["v193_semantic_rank_score"].mean())
    return round(max(0.0, min(1.0, 0.55 * tier_score + 0.35 * count_score - 0.25 * dispersion)), 6)
