from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .data import BASE_KEYS, PARENT_KEYS, clean_text


ROLE_PREFIX = {"B2C": "b2c", "C2B": "c2b", "EXT_B2C_LISTING": "external_listing"}


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if np.isfinite(result) else default


def _json_time(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.isoformat()


def weighted_log_blend(components: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        component
        for component in components
        if _number(component.get("value")) not in (None, 0)
        and (_number(component.get("weight"), 0.0) or 0.0) > 0
    ]
    if not valid:
        return {"value": None, "source_count": 0, "disagreement_ratio": None, "components": []}
    values = np.array([float(component["value"]) for component in valid], dtype=float)
    weights = np.array([float(component["weight"]) for component in valid], dtype=float)
    log_values = np.log(values)
    center = np.median(log_values)
    clipped = np.clip(log_values, center - 0.20, center + 0.20)
    normalized = weights / weights.sum()
    value = float(np.exp(np.sum(clipped * normalized)))
    enriched = []
    for component, normalized_weight, raw_log, clipped_log in zip(valid, normalized, log_values, clipped):
        enriched.append(
            {
                **component,
                "normalized_weight": float(normalized_weight),
                "raw_log_value": float(raw_log),
                "clipped_log_value": float(clipped_log),
                "log_clip_applied": bool(not math.isclose(raw_log, clipped_log, abs_tol=1e-12)),
            }
        )
    return {
        "value": value,
        "source_count": len(valid),
        "disagreement_ratio": float((values.max() - values.min()) / value),
        "components": enriched,
    }


def source_weight(count: float, latest_days: float | None, dispersion: float | None, factor: float) -> float:
    latest = 9999.0 if latest_days is None else max(0.0, latest_days)
    spread = 0.60 if dispersion is None else min(max(dispersion, 0.0), 0.70)
    evidence = min(math.log1p(max(count, 0.0)), math.log(21.0)) / math.log(21.0)
    recency = math.exp(-latest / 180.0)
    stability = min(max(1.0 - spread, 0.15), 1.0)
    return float(evidence * recency * stability * factor)


def observation_record(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    return {
        "observation_id": clean_text(value.get("observation_id")),
        "lifecycle_id": clean_text(value.get("lifecycle_id")),
        "source_family": clean_text(value.get("source_type")),
        "price_role": clean_text(value.get("cluster_price_type")),
        "raw_price": _number(value.get("price")),
        "first_listing_price": _number(value.get("first_listing_price")),
        "event_time": _json_time(value.get("event_time")),
        "knowledge_available_at": _json_time(value.get("knowledge_available_at")),
        "brand": value.get("brand"),
        "series": value.get("series"),
        "model_year": _number(value.get("model_year")),
        "trim": value.get("trim"),
        "city": value.get("city"),
        "color": value.get("color_norm"),
        "age_years": _number(value.get("age_years")),
        "mileage_wan_km": _number(value.get("mileage_wan_km")),
        "transfer_count": _number(value.get("transfer_count")),
        "condition_risk_level": value.get("condition_risk_level"),
        "days_on_market": _number(value.get("days_on_market")),
    }


class TemporalObservationIndex:
    def __init__(self, observations: pd.DataFrame, role_pairs: pd.DataFrame):
        self.observations = observations
        self.role_pairs = role_pairs.sort_values("pair_available_at").reset_index(drop=True)
        self.exact: dict[tuple[Any, ...], pd.DataFrame] = {}
        self.parent: dict[tuple[Any, ...], pd.DataFrame] = {}
        for key, group in observations.groupby(["cluster_price_type", *BASE_KEYS], dropna=False, sort=False):
            self.exact[key] = group.sort_values("knowledge_available_at")
        for key, group in observations.groupby(["cluster_price_type", *PARENT_KEYS], dropna=False, sort=False):
            self.parent[key] = group.sort_values("knowledge_available_at")
        self.pair_parent: dict[tuple[Any, ...], pd.DataFrame] = {}
        for key, group in role_pairs.groupby(PARENT_KEYS, dropna=False, sort=False):
            if not isinstance(key, tuple):
                key = (key,)
            self.pair_parent[key] = group.sort_values("pair_available_at")

    @staticmethod
    def _prefix(frame: pd.DataFrame | None, time_column: str, cutoff: pd.Timestamp) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        values = frame[time_column].to_numpy(dtype="datetime64[ns]")
        position = int(np.searchsorted(values, np.datetime64(cutoff), side="right"))
        return frame.iloc[:position]

    def role_frames(self, query: pd.Series | dict[str, Any], role: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        value = dict(query)
        cutoff = pd.Timestamp(value["prediction_time"])
        query_id = clean_text(value.get("query_id"))
        exact_key = (role, *(value.get(key) for key in BASE_KEYS))
        parent_key = (role, *(value.get(key) for key in PARENT_KEYS))
        exact = self._prefix(self.exact.get(exact_key), "knowledge_available_at", cutoff)
        parent = self._prefix(self.parent.get(parent_key), "knowledge_available_at", cutoff)
        if query_id:
            if not exact.empty:
                exact = exact[exact["observation_id"].astype(str).ne(query_id)]
            if not parent.empty:
                parent = parent[parent["observation_id"].astype(str).ne(query_id)]
        return exact, parent

    def pair_frame(self, query: pd.Series | dict[str, Any]) -> pd.DataFrame:
        value = dict(query)
        cutoff = pd.Timestamp(value["prediction_time"])
        key = tuple(value.get(column) for column in PARENT_KEYS)
        result = self._prefix(self.pair_parent.get(key), "pair_available_at", cutoff)
        if len(result) >= 8:
            return result
        return self._prefix(self.role_pairs, "pair_available_at", cutoff)


def robust_role_statistics(
    exact: pd.DataFrame,
    parent: pd.DataFrame,
    prediction_time: pd.Timestamp,
    role: str,
) -> dict[str, Any]:
    def stats(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {
                "count": 0,
                "unique_lifecycle_count": 0,
                "p25": None,
                "p50": None,
                "p75": None,
                "dispersion": None,
                "latest_days": None,
                "recent90_count": 0,
                "recent90_p50": None,
            }
        price = pd.to_numeric(frame["price"], errors="coerce").dropna()
        if price.empty:
            return {"count": 0, "unique_lifecycle_count": 0}
        p25, p50, p75 = (float(price.quantile(q)) for q in (0.25, 0.50, 0.75))
        latest = pd.to_datetime(frame["event_time"], errors="coerce").max()
        recent = frame[pd.to_datetime(frame["event_time"], errors="coerce").ge(prediction_time - pd.Timedelta(days=90))]
        return {
            "count": int(len(price)),
            "unique_lifecycle_count": int(frame["lifecycle_id"].nunique()),
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "dispersion": float((p75 - p25) / p50) if p50 > 0 else None,
            "latest_days": float((prediction_time - latest).total_seconds() / 86400.0) if pd.notna(latest) else None,
            "recent90_count": int(len(recent)),
            "recent90_p50": _number(pd.to_numeric(recent["price"], errors="coerce").median()),
        }

    exact_stats = stats(exact)
    parent_stats = stats(parent)
    exact_count = exact_stats.get("count", 0)
    exact_dispersion = exact_stats.get("dispersion")
    prior_strength = 4.0 if exact_dispersion is not None and exact_dispersion <= 0.15 else 8.0
    if exact_dispersion is None or exact_dispersion > 0.30:
        prior_strength = 14.0
    exact_weight = exact_count / (exact_count + prior_strength) if exact_count else 0.0
    if parent_stats.get("p50") is None:
        exact_weight = 1.0 if exact_stats.get("p50") is not None else 0.0

    def shrink(column: str) -> float | None:
        exact_value = exact_stats.get(column)
        parent_value = parent_stats.get(column)
        if exact_value is None:
            return parent_value
        if parent_value is None:
            return exact_value
        return float(exact_value * exact_weight + parent_value * (1.0 - exact_weight))

    center = shrink("p50")
    low = shrink("p25")
    high = shrink("p75")
    recent = exact_stats.get("recent90_p50") or parent_stats.get("recent90_p50")
    recent_count = exact_stats.get("recent90_count", 0)
    trend = 1.0
    if center and recent:
        trend = min(max(recent / center, 0.90), 1.10)
    point = None if center is None else float(center * trend)
    latest_candidates = [value for value in (exact_stats.get("latest_days"), parent_stats.get("latest_days")) if value is not None]
    latest_days = min(latest_candidates) if latest_candidates else None
    effective_count = exact_count + min(parent_stats.get("count", 0) * 0.25, 20.0)
    return {
        "role": role,
        "exact_stats": exact_stats,
        "parent_stats": parent_stats,
        "prior_strength": prior_strength,
        "exact_shrinkage_weight": exact_weight,
        "parent_borrowed": bool(parent_stats.get("p50") is not None and exact_weight < 0.80),
        "shrunk_center": center,
        "shrunk_low": low,
        "shrunk_high": high,
        "recent90_trend_factor": trend,
        "point_after_trend": point,
        "effective_evidence_count": float(effective_count),
        "latest_days": latest_days,
        "dispersion": exact_stats.get("dispersion") if exact_stats.get("dispersion") is not None else parent_stats.get("dispersion"),
    }


def listing_statistics(exact_b2c: pd.DataFrame, prediction_time: pd.Timestamp) -> dict[str, Any]:
    if exact_b2c.empty:
        return {"count": 0, "center": None, "low": None, "high": None, "latest_days": None, "dispersion": None}
    frame = exact_b2c[
        pd.to_numeric(exact_b2c["first_listing_price"], errors="coerce").between(3000, 2_000_000)
    ].copy()
    if frame.empty:
        return {"count": 0, "center": None, "low": None, "high": None, "latest_days": None, "dispersion": None}
    values = pd.to_numeric(frame["first_listing_price"], errors="coerce")
    low, center, high = (float(values.quantile(q)) for q in (0.25, 0.50, 0.75))
    latest = pd.to_datetime(frame["event_time"], errors="coerce").max()
    return {
        "count": int(len(frame)),
        "center": center,
        "low": low,
        "high": high,
        "latest_days": float((prediction_time - latest).total_seconds() / 86400.0),
        "dispersion": float((high - low) / center) if center > 0 else None,
    }


def bridge_statistics(pair_frame: pd.DataFrame, exact_b2c: pd.DataFrame) -> dict[str, Any]:
    purchase_ratio = 0.92
    purchase_count = 0
    purchase_p25 = 0.90
    purchase_p75 = 0.94
    if not pair_frame.empty:
        ratio = pd.to_numeric(pair_frame["purchase_to_sold_ratio"], errors="coerce").dropna()
        if len(ratio):
            purchase_ratio = float(ratio.median())
            purchase_p25 = float(ratio.quantile(0.25))
            purchase_p75 = float(ratio.quantile(0.75))
            purchase_count = int(len(ratio))
    listing_ratio = 1.04
    listing_count = 0
    if not exact_b2c.empty:
        ratio = (
            pd.to_numeric(exact_b2c["first_listing_price"], errors="coerce")
            / pd.to_numeric(exact_b2c["price"], errors="coerce").replace(0, np.nan)
        )
        ratio = ratio[ratio.between(0.85, 1.50)].dropna()
        if len(ratio):
            listing_ratio = float(ratio.median())
            listing_count = int(len(ratio))
    return {
        "purchase_to_sold_ratio": float(min(max(purchase_ratio, 0.60), 1.02)),
        "purchase_to_sold_count": purchase_count,
        "purchase_to_sold_p25": purchase_p25,
        "purchase_to_sold_p75": purchase_p75,
        "listing_to_sold_ratio": float(min(max(listing_ratio, 1.00), 1.25)),
        "listing_to_sold_count": listing_count,
    }


def _raw_query(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "brand": query.get("brand"),
        "series": query.get("series"),
        "model_year": _number(query.get("model_year")),
        "trim": query.get("trim"),
        "color": query.get("color_raw") or query.get("color_norm"),
        "city": query.get("city"),
        "age_years": _number(query.get("age_years")),
        "mileage_wan_km": _number(query.get("mileage_wan_km")),
        "transfer_count": _number(query.get("transfer_count")),
        "condition_risk_level": query.get("condition_risk_level"),
        "prediction_time": _json_time(query.get("prediction_time")),
    }


def _normalized_query(query: dict[str, Any]) -> dict[str, Any]:
    return {key: query.get(key) for key in BASE_KEYS}


def calculate_v191_1(
    query: pd.Series | dict[str, Any],
    index: TemporalObservationIndex,
    *,
    include_raw_observations: bool = False,
) -> dict[str, Any]:
    value = dict(query)
    prediction_time = pd.Timestamp(value["prediction_time"])
    role_results: dict[str, Any] = {}
    raw_observations: list[dict[str, Any]] = []
    exact_frames: dict[str, pd.DataFrame] = {}
    parent_frames: dict[str, pd.DataFrame] = {}
    for role in ROLE_PREFIX:
        exact, parent = index.role_frames(value, role)
        exact_frames[role] = exact
        parent_frames[role] = parent
        role_results[role] = robust_role_statistics(exact, parent, prediction_time, role)
        if include_raw_observations:
            combined = pd.concat([exact.assign(match_scope="exact"), parent.assign(match_scope="parent")])
            combined = combined.drop_duplicates("observation_id")
            raw_observations.extend(
                [{**observation_record(row), "match_scope": row["match_scope"]} for _, row in combined.iterrows()]
            )

    pair_frame = index.pair_frame(value)
    bridges = bridge_statistics(pair_frame, exact_frames["B2C"])
    listing = listing_statistics(exact_frames["B2C"], prediction_time)
    purchase_ratio = bridges["purchase_to_sold_ratio"]
    listing_ratio = bridges["listing_to_sold_ratio"]

    b2c = role_results["B2C"]
    c2b = role_results["C2B"]
    external = role_results["EXT_B2C_LISTING"]
    b2c_point = b2c["point_after_trend"]
    c2b_point = c2b["point_after_trend"]
    external_sold = None if external["point_after_trend"] is None else external["point_after_trend"] / listing_ratio
    internal_listing_sold = None if listing["center"] is None else listing["center"] / listing_ratio
    retail_components = [
        {
            "component": "internal_b2c_sold",
            "value": b2c_point,
            "weight": source_weight(b2c["effective_evidence_count"], b2c["latest_days"], b2c["dispersion"], 1.0),
            "source_family": "internal_b2c_lifecycle",
            "derived": False,
        },
        {
            "component": "internal_first_listing_sold_equivalent",
            "value": internal_listing_sold,
            "weight": source_weight(listing["count"], listing["latest_days"], listing["dispersion"], 0.8),
            "source_family": "internal_b2c_lifecycle",
            "derived": True,
        },
        {
            "component": "external_listing_sold_equivalent",
            "value": external_sold,
            "weight": source_weight(
                external["effective_evidence_count"], external["latest_days"], external["dispersion"], 0.7
            ),
            "source_family": "external_b2c_listing",
            "derived": True,
        },
    ]
    retail = weighted_log_blend(retail_components)
    retail_from_c2b_bridge = False
    if retail["value"] is None and c2b_point is not None:
        retail["value"] = c2b_point / purchase_ratio
        retail["source_count"] = 1
        retail["disagreement_ratio"] = 0.0
        retail["components"] = [
            {
                "component": "c2b_implied_retail",
                "value": retail["value"],
                "weight": 1.0,
                "normalized_weight": 1.0,
                "source_family": "internal_c2b_lifecycle",
                "derived": True,
                "raw_log_value": math.log(retail["value"]),
                "clipped_log_value": math.log(retail["value"]),
                "log_clip_applied": False,
            }
        ]
        retail_from_c2b_bridge = True

    acquisition_components = [
        {
            "component": "internal_c2b_observed",
            "value": c2b_point,
            "weight": source_weight(c2b["effective_evidence_count"], c2b["latest_days"], c2b["dispersion"], 1.0),
            "source_family": "internal_c2b_lifecycle",
            "derived": False,
        },
        {
            "component": "retail_purchase_bridge",
            "value": None if retail["value"] is None else retail["value"] * purchase_ratio,
            "weight": min(math.log1p(bridges["purchase_to_sold_count"]), math.log(101.0)) / math.log(101.0) * 0.85,
            "source_family": "lifecycle_bridge",
            "derived": True,
        },
    ]
    acquisition = weighted_log_blend(acquisition_components)
    fair_retail = retail["value"]
    c2b_reference = acquisition["value"]

    total_evidence = sum(
        float(role_results[role]["effective_evidence_count"]) for role in ROLE_PREFIX
    ) + listing["count"]
    retail_half_width = (
        0.08
        if total_evidence >= 12 and retail["source_count"] >= 2 and (retail["disagreement_ratio"] or 0) <= 0.12
        else 0.12
        if total_evidence >= 6 and (retail["disagreement_ratio"] or 9) <= 0.20
        else 0.18
        if total_evidence >= 3
        else 0.25
    )
    fair_low = None if fair_retail is None else fair_retail * (1.0 - retail_half_width)
    fair_high = None if fair_retail is None else fair_retail * (1.0 + retail_half_width)
    zero_cost_ceiling = fair_low
    available = [number for number in (c2b_reference, zero_cost_ceiling) if number is not None]
    conservative = min(available) if available else None
    c2b_half_width = (
        0.10
        if total_evidence >= 12 and acquisition["source_count"] >= 2 and (acquisition["disagreement_ratio"] or 0) <= 0.15
        else 0.15
        if total_evidence >= 6
        else 0.22
        if total_evidence >= 3
        else 0.30
    )
    c2b_low = None if c2b_reference is None else c2b_reference * (1.0 - c2b_half_width)
    c2b_high = None if c2b_reference is None else c2b_reference * (1.0 + c2b_half_width)
    provisional_low = None if conservative is None else min(c2b_low or conservative, conservative)
    provisional_high = conservative

    raw_components = 0
    lifecycle_ids: set[str] = set()
    source_families: set[str] = set()
    if include_raw_observations:
        unique_observations = {record["observation_id"]: record for record in raw_observations}
        raw_observations = list(unique_observations.values())
        for record in raw_observations:
            raw_components += int(record.get("raw_price") is not None)
            raw_components += int(record.get("first_listing_price") is not None and record["price_role"] == "B2C")
            if record.get("lifecycle_id"):
                lifecycle_ids.add(record["lifecycle_id"])
            if record.get("source_family"):
                source_families.add(record["source_family"])
    else:
        for role in ROLE_PREFIX:
            exact, parent = exact_frames[role], parent_frames[role]
            combined = pd.concat([exact, parent]).drop_duplicates("observation_id")
            if combined.empty:
                continue
            raw_components += len(combined)
            raw_components += int(
                pd.to_numeric(
                    combined.loc[combined["cluster_price_type"].eq("B2C"), "first_listing_price"],
                    errors="coerce",
                ).notna().sum()
            )
            lifecycle_ids.update(combined["lifecycle_id"].dropna().astype(str))
            source_families.update(combined["source_type"].dropna().astype(str))

    exact_key = {key: value.get(key) for key in BASE_KEYS}
    output = {
        "version": "v191_1",
        "query_id": clean_text(value.get("query_id")),
        "prediction_time": _json_time(prediction_time),
        "raw_query": _raw_query(value),
        "normalized_query": _normalized_query(value),
        "matched_cluster": {
            "cluster_key": exact_key,
            "match_type": "exact_homogeneous_cluster",
            "does_not_use_candidate_medians_as_query_features": True,
        },
        "raw_observations": raw_observations,
        "bridge_pairs": (
            pair_frame[
                [
                    "lifecycle_id",
                    "observation_id_c2b",
                    "observation_id_b2c",
                    "price_c2b",
                    "price_b2c",
                    "purchase_to_sold_ratio",
                    "pair_available_at",
                ]
            ]
            .to_dict("records")
            if include_raw_observations and not pair_frame.empty
            else []
        ),
        "role_calculations": role_results,
        "listing_calculation": listing,
        "bridge_calculation": bridges,
        "retail_fusion": {**retail, "retail_from_c2b_bridge": retail_from_c2b_bridge},
        "c2b_fusion": acquisition,
        "interval_calculation": {
            "total_evidence": total_evidence,
            "retail_half_width": retail_half_width,
            "fair_retail_low": fair_low,
            "fair_retail_high": fair_high,
            "c2b_half_width": c2b_half_width,
            "c2b_reference_low": c2b_low,
            "c2b_reference_high": c2b_high,
            "provisional_purchase_low": provisional_low,
            "provisional_purchase_high": provisional_high,
        },
        "confidence_calculation": {
            "total_evidence": total_evidence,
            "retail_source_count": retail["source_count"],
            "retail_source_disagreement_ratio": retail["disagreement_ratio"],
            "confidence_bucket": (
                "high"
                if total_evidence >= 12
                and retail["source_count"] >= 2
                and (retail["disagreement_ratio"] or 0) <= 0.12
                and retail_half_width * 2 <= 0.22
                else "medium"
                if total_evidence >= 6
                and (retail["disagreement_ratio"] or 9) <= 0.20
                else "low"
                if total_evidence >= 3
                else "manual"
            ),
        },
        "price_outputs": {
            "fair_retail_transaction_price": fair_retail,
            "c2b_market_reference_price": c2b_reference,
            "conservative_reference_price": conservative,
            "recommended_c2b_low": provisional_low,
            "recommended_c2b_high": provisional_high,
        },
        "source_accounting": {
            "raw_price_component_count": int(raw_components),
            "independent_source_family_count": int(len(source_families)),
            "independent_vehicle_lifecycle_count": int(len(lifecycle_ids)),
            "derived_prices_counted_as_independent_sources": 0,
            "listing_and_sold_same_lifecycle_deduplicated": True,
        },
        "explanation_segment": {
            "segment": (
                "manual_review"
                if conservative is None
                else "major_risk"
                if value.get("condition_risk_level") == "major_risk"
                else "standard_market_quote"
            ),
            "does_not_affect_price": True,
        },
    }
    return output


def _difference(stored: float | None, recomputed: float | None) -> float | None:
    return None if stored is None or recomputed is None else float(recomputed - stored)


def replay_v191_1(ledger: dict[str, Any]) -> dict[str, Any]:
    prediction_time = pd.Timestamp(ledger["prediction_time"])
    observations = pd.DataFrame(ledger["raw_observations"])
    if observations.empty:
        observations = pd.DataFrame(
            columns=[
                "event_time",
                "knowledge_available_at",
                "price",
                "first_listing_price",
                "cluster_price_type",
                "source_type",
                "price_role",
                "match_scope",
                "lifecycle_id",
            ]
        )
    else:
        observations["event_time"] = pd.to_datetime(observations["event_time"], errors="coerce")
        observations["knowledge_available_at"] = pd.to_datetime(observations["knowledge_available_at"], errors="coerce")
        observations["price"] = pd.to_numeric(observations["raw_price"], errors="coerce")
        observations["first_listing_price"] = pd.to_numeric(observations["first_listing_price"], errors="coerce")
        observations["cluster_price_type"] = observations["price_role"]
        observations["source_type"] = observations["source_family"]
    for key, value in ledger["matched_cluster"]["cluster_key"].items():
        observations[key] = value

    role_results = {}
    exact_frames = {}
    for role in ROLE_PREFIX:
        role_frame = observations[observations["price_role"].eq(role)].copy()
        exact = role_frame[role_frame["match_scope"].eq("exact")].copy()
        parent = role_frame.copy()
        exact_frames[role] = exact
        role_results[role] = robust_role_statistics(exact, parent, prediction_time, role)
    listing = listing_statistics(exact_frames["B2C"], prediction_time)

    pair_frame = pd.DataFrame(ledger.get("bridge_pairs") or [])
    if len(pair_frame):
        pair_frame["purchase_to_sold_ratio"] = pd.to_numeric(
            pair_frame["purchase_to_sold_ratio"], errors="coerce"
        )
    bridge = bridge_statistics(pair_frame, exact_frames["B2C"])
    purchase_ratio = bridge["purchase_to_sold_ratio"]
    listing_ratio = bridge["listing_to_sold_ratio"]

    b2c, c2b, external = role_results["B2C"], role_results["C2B"], role_results["EXT_B2C_LISTING"]
    retail = weighted_log_blend(
        [
            {
                "component": "internal_b2c_sold",
                "value": b2c["point_after_trend"],
                "weight": source_weight(b2c["effective_evidence_count"], b2c["latest_days"], b2c["dispersion"], 1.0),
                "source_family": "internal_b2c_lifecycle",
                "derived": False,
            },
            {
                "component": "internal_first_listing_sold_equivalent",
                "value": None if listing["center"] is None else listing["center"] / listing_ratio,
                "weight": source_weight(listing["count"], listing["latest_days"], listing["dispersion"], 0.8),
                "source_family": "internal_b2c_lifecycle",
                "derived": True,
            },
            {
                "component": "external_listing_sold_equivalent",
                "value": None if external["point_after_trend"] is None else external["point_after_trend"] / listing_ratio,
                "weight": source_weight(
                    external["effective_evidence_count"], external["latest_days"], external["dispersion"], 0.7
                ),
                "source_family": "external_b2c_listing",
                "derived": True,
            },
        ]
    )
    if retail["value"] is None and c2b["point_after_trend"] is not None:
        retail["value"] = c2b["point_after_trend"] / purchase_ratio
    acquisition = weighted_log_blend(
        [
            {
                "component": "internal_c2b_observed",
                "value": c2b["point_after_trend"],
                "weight": source_weight(c2b["effective_evidence_count"], c2b["latest_days"], c2b["dispersion"], 1.0),
                "source_family": "internal_c2b_lifecycle",
                "derived": False,
            },
            {
                "component": "retail_purchase_bridge",
                "value": None if retail["value"] is None else retail["value"] * purchase_ratio,
                "weight": min(math.log1p(bridge["purchase_to_sold_count"]), math.log(101.0)) / math.log(101.0) * 0.85,
                "source_family": "lifecycle_bridge",
                "derived": True,
            },
        ]
    )
    total_evidence = sum(role_results[role]["effective_evidence_count"] for role in ROLE_PREFIX) + listing["count"]
    retail_half_width = (
        0.08
        if total_evidence >= 12 and retail["source_count"] >= 2 and (retail["disagreement_ratio"] or 0) <= 0.12
        else 0.12
        if total_evidence >= 6 and (retail["disagreement_ratio"] or 9) <= 0.20
        else 0.18
        if total_evidence >= 3
        else 0.25
    )
    fair_low = None if retail["value"] is None else retail["value"] * (1.0 - retail_half_width)
    available = [number for number in (acquisition["value"], fair_low) if number is not None]
    conservative = min(available) if available else None
    c2b_half_width = (
        0.10
        if total_evidence >= 12 and acquisition["source_count"] >= 2 and (acquisition["disagreement_ratio"] or 0) <= 0.15
        else 0.15
        if total_evidence >= 6
        else 0.22
        if total_evidence >= 3
        else 0.30
    )
    fair_high = None if retail["value"] is None else retail["value"] * (1.0 + retail_half_width)
    c2b_low = None if acquisition["value"] is None else acquisition["value"] * (1.0 - c2b_half_width)
    c2b_high = None if acquisition["value"] is None else acquisition["value"] * (1.0 + c2b_half_width)
    provisional_low = None if conservative is None else min(c2b_low or conservative, conservative)
    confidence = (
        "high"
        if total_evidence >= 12
        and retail["source_count"] >= 2
        and (retail["disagreement_ratio"] or 0) <= 0.12
        and retail_half_width * 2 <= 0.22
        else "medium"
        if total_evidence >= 6 and (retail["disagreement_ratio"] or 9) <= 0.20
        else "low"
        if total_evidence >= 3
        else "manual"
    )

    stages: list[dict[str, Any]] = []

    def add_stage(name: str, stored_value: Any, recomputed_value: Any) -> None:
        if isinstance(stored_value, str) or isinstance(recomputed_value, str):
            difference = None
            passed = stored_value == recomputed_value
        else:
            difference = _difference(stored_value, recomputed_value)
            passed = difference is None or abs(difference) <= 1e-6
        stages.append(
            {
                "stage": name,
                "stored_value": stored_value,
                "recomputed_value": recomputed_value,
                "difference": difference,
                "passed": bool(passed),
            }
        )

    stored_roles = ledger["role_calculations"]
    for role in ROLE_PREFIX:
        add_stage(
            f"{role}_exact_cluster_price",
            stored_roles[role]["exact_stats"].get("p50"),
            role_results[role]["exact_stats"].get("p50"),
        )
        add_stage(
            f"{role}_parent_price",
            stored_roles[role]["parent_stats"].get("p50"),
            role_results[role]["parent_stats"].get("p50"),
        )
        add_stage(
            f"{role}_parent_shrinkage",
            stored_roles[role].get("shrunk_center"),
            role_results[role].get("shrunk_center"),
        )
        add_stage(
            f"{role}_trend_adjusted_price",
            stored_roles[role].get("point_after_trend"),
            role_results[role].get("point_after_trend"),
        )
    add_stage(
        "listing_to_sold_ratio",
        ledger["bridge_calculation"].get("listing_to_sold_ratio"),
        bridge.get("listing_to_sold_ratio"),
    )
    add_stage(
        "purchase_to_sold_ratio",
        ledger["bridge_calculation"].get("purchase_to_sold_ratio"),
        bridge.get("purchase_to_sold_ratio"),
    )
    add_stage("b2c_multi_source_fusion", ledger["retail_fusion"].get("value"), retail["value"])
    add_stage(
        "b2c_to_c2b_bridge",
        next(
            (
                component.get("value")
                for component in ledger["c2b_fusion"].get("components", [])
                if component.get("component") == "retail_purchase_bridge"
            ),
            None,
        ),
        None if retail["value"] is None else retail["value"] * purchase_ratio,
    )
    add_stage("c2b_multi_source_fusion", ledger["c2b_fusion"].get("value"), acquisition["value"])
    stored = ledger["price_outputs"]
    add_stage("final_c2b_market_reference", stored.get("c2b_market_reference_price"), acquisition["value"])
    add_stage("final_conservative_reference", stored.get("conservative_reference_price"), conservative)
    stored_interval = ledger["interval_calculation"]
    add_stage("interval_fair_retail_low", stored_interval.get("fair_retail_low"), fair_low)
    add_stage("interval_fair_retail_high", stored_interval.get("fair_retail_high"), fair_high)
    add_stage("interval_c2b_low", stored_interval.get("c2b_reference_low"), c2b_low)
    add_stage("interval_c2b_high", stored_interval.get("c2b_reference_high"), c2b_high)
    add_stage("interval_provisional_low", stored_interval.get("provisional_purchase_low"), provisional_low)
    add_stage("interval_provisional_high", stored_interval.get("provisional_purchase_high"), conservative)
    add_stage(
        "confidence_bucket",
        ledger["confidence_calculation"].get("confidence_bucket"),
        confidence,
    )
    future = int(
        (
            pd.to_datetime(observations["knowledge_available_at"], errors="coerce")
            > prediction_time
        ).sum()
    )
    return {
        "query_id": ledger["query_id"],
        "stages": stages,
        "price_recalculation_passed": all(stage["passed"] for stage in stages),
        "future_data_violation_count": future,
        "duplicate_source_count": int(
            ledger["source_accounting"].get("derived_prices_counted_as_independent_sources", 0)
        ),
    }
