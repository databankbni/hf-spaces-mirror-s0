from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .v192_16_semantics import canonicalize_trim, normalize_energy_type
from .v194_price_policy import weighted_quantile


RETRIEVAL_POLICY_VERSION = "v194_temporal_homogeneous_retrieval_v2_six_element_semantics"


@dataclass(frozen=True)
class RetrievalConfig:
    max_candidates: int = 100
    half_life_days: float = 120.0
    # L2 is intentionally a *near* exact-trim tier.  Older versions called
    # every same-year exact trim L2, even when it was several years or tens of
    # thousands of kilometres away.  Those rows are useful context but cannot
    # honestly be labelled a six-element comparable.
    strict_baseline_levels: tuple[str, ...] = ("L0", "L1", "L2")
    fallback_baseline_levels: tuple[str, ...] = ("L4", "L5")
    interval_levels: tuple[str, ...] = (
        "L0", "L1", "L2", "L2_WIDE_EXACT_TRIM", "L3", "L4", "L5", "B2C_BRIDGE"
    )


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def normalize_query(query: dict[str, Any]) -> dict[str, Any]:
    parsed = canonicalize_trim(
        query.get("trim") or query.get("model") or query.get("raw_trim"),
        query.get("brand"),
        query.get("series"),
        query.get("model_year"),
        model_id=query.get("model_id"),
        energy_value=query.get("is_new_energy") or query.get("energy_type"),
    )
    energy = normalize_energy_type(
        query.get("is_new_energy") or query.get("energy_type"),
        brand=query.get("brand"),
        series=query.get("series"),
        trim=query.get("trim") or query.get("model") or query.get("raw_trim"),
        is_new_energy=query.get("is_new_energy"),
    )
    model_year = pd.to_numeric(query.get("model_year") or parsed.get("model_year_key"), errors="coerce")
    return {
        **query,
        "brand_key": parsed.get("brand_key"),
        "series_key": parsed.get("series_key"),
        "model_year": int(model_year) if pd.notna(model_year) else None,
        "normalized_trim": parsed.get("normalized_trim"),
        "canonical_trim_key": parsed.get("canonical_trim_key"),
        "trim_power_code": parsed.get("trim_power_code"),
        "trim_package": parsed.get("trim_package"),
        "normalized_energy_type": energy.get("energy_type"),
        "age_years": float(pd.to_numeric(query.get("age_years"), errors="coerce"))
        if pd.notna(pd.to_numeric(query.get("age_years"), errors="coerce"))
        else np.nan,
        "mileage_wan_km": float(pd.to_numeric(query.get("mileage_wan_km"), errors="coerce"))
        if pd.notna(pd.to_numeric(query.get("mileage_wan_km"), errors="coerce"))
        else np.nan,
        "transfer_count": float(pd.to_numeric(query.get("transfer_count"), errors="coerce"))
        if pd.notna(pd.to_numeric(query.get("transfer_count"), errors="coerce"))
        else np.nan,
        "city_key_v194": _compact(query.get("city")),
        "color_key_v194": _compact(query.get("color") or query.get("color_raw")),
        "quote_time": pd.to_datetime(query.get("quote_time"), errors="coerce"),
        "query_uid": str(query.get("query_uid") or query.get("observation_id") or "query"),
    }


def _semantic_level(query: dict[str, Any], candidates: pd.DataFrame) -> pd.Series:
    same_brand = candidates["brand_key"].astype(str).eq(str(query.get("brand_key") or ""))
    same_series = candidates["series_key"].astype(str).eq(str(query.get("series_key") or ""))
    same_year = pd.to_numeric(candidates["model_year"], errors="coerce").eq(query.get("model_year"))
    adjacent_year = (pd.to_numeric(candidates["model_year"], errors="coerce") - float(query.get("model_year") or -9999)).abs().le(1)
    same_trim = candidates["canonical_trim_key"].astype(str).eq(str(query.get("canonical_trim_key") or ""))
    query_normalized_trim = str(query.get("normalized_trim") or "")
    same_configuration = (
        candidates.get("normalized_trim", pd.Series("", index=candidates.index)).astype(str).eq(query_normalized_trim)
        & bool(query_normalized_trim)
    )
    candidate_energy = candidates.get("normalized_energy_type", pd.Series("UNKNOWN", index=candidates.index)).fillna("UNKNOWN").astype(str)
    energy_from_key = candidates["canonical_trim_key"].astype(str).str.split("|").str[3].fillna("UNKNOWN")
    candidate_energy = candidate_energy.where(~candidate_energy.isin({"", "UNKNOWN", "nan"}), energy_from_key)
    query_energy = str(query.get("normalized_energy_type") or "UNKNOWN")
    same_powertrain = candidate_energy.eq(query_energy) & candidate_energy.ne("UNKNOWN") & (query_energy != "UNKNOWN")
    exact_trim_energy_compatible = same_powertrain | (same_trim & (candidate_energy.eq("UNKNOWN") | (query_energy == "UNKNOWN")))
    same_city = candidates["city_key_v194"].astype(str).eq(str(query.get("city_key_v194") or ""))
    age_gap = (pd.to_numeric(candidates["age_years"], errors="coerce") - query.get("age_years", np.nan)).abs()
    mileage_gap = (pd.to_numeric(candidates["mileage_wan_km"], errors="coerce") - query.get("mileage_wan_km", np.nan)).abs()
    transfer_gap = (pd.to_numeric(candidates["transfer_count"], errors="coerce") - query.get("transfer_count", np.nan)).abs()
    # The numerical parts of the six-element input have two explicit bands.
    # `close_six` is evidence that can be directly pooled.  `near_six` is
    # still a real exact-trim comparison, but needs an adjustment/low-trust
    # treatment.  Everything else remains visible as context, rather than
    # being silently upgraded to a strict comparable.
    close_six = age_gap.le(0.75).fillna(False) & mileage_gap.le(1.0).fillna(False) & transfer_gap.le(1).fillna(False)
    near_six = age_gap.le(1.50).fillna(False) & mileage_gap.le(3.0).fillna(False) & transfer_gap.le(2).fillna(False)
    level = pd.Series("L6_FALLBACK", index=candidates.index, dtype="object")
    level.loc[same_brand & same_series & same_year & same_trim & exact_trim_energy_compatible & same_city & close_six] = "L0"
    level.loc[same_brand & same_series & same_year & same_trim & exact_trim_energy_compatible & close_six & level.eq("L6_FALLBACK")] = "L1"
    level.loc[same_brand & same_series & same_year & same_trim & exact_trim_energy_compatible & near_six & level.eq("L6_FALLBACK")] = "L2"
    level.loc[same_brand & same_series & same_year & same_trim & exact_trim_energy_compatible & level.eq("L6_FALLBACK")] = "L2_WIDE_EXACT_TRIM"
    level.loc[same_brand & same_series & same_year & same_powertrain & level.eq("L6_FALLBACK")] = "L3"
    # A matching configuration suffix is not a timeless identity.  The same
    # package name can span several generations with materially different
    # values, so cross-year point fallback is limited to adjacent model years.
    level.loc[same_brand & same_series & adjacent_year & same_configuration & same_powertrain & level.eq("L6_FALLBACK")] = "L4"
    level.loc[same_brand & same_series & same_powertrain & level.eq("L6_FALLBACK")] = "L5"
    b2c = candidates["price_role"].astype(str).isin({"INTERNAL_B2C_SOLD_ACTUAL", "EXTERNAL_B2C_LISTING"})
    level.loc[b2c & same_brand & same_series & adjacent_year & same_trim & same_powertrain] = "B2C_BRIDGE"
    return level


def _configuration_match_flags(query: dict[str, Any], candidates: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return explicit power-code and package matches for audit and ranking.

    L3 is deliberately a broader same-series/same-energy context tier. It is
    not enough to distinguish 735Li from 740Li, or a Camry HG from GVP. These
    two flags keep that information visible even when the candidate is not a
    strict point-price comparable.
    """
    query_power = str(query.get("trim_power_code") or "").strip()
    query_package = str(query.get("trim_package") or "").strip()
    candidate_power = candidates.get("trim_power_code", pd.Series("", index=candidates.index)).fillna("").astype(str)
    candidate_package = candidates.get("trim_package", pd.Series("", index=candidates.index)).fillna("").astype(str)
    same_power = candidate_power.eq(query_power) & bool(query_power)
    same_package = candidate_package.eq(query_package) & bool(query_package)
    return same_power.astype(int), same_package.astype(int)


def _distance_score(query: dict[str, Any], candidates: pd.DataFrame) -> pd.Series:
    age_gap = (pd.to_numeric(candidates["age_years"], errors="coerce") - query.get("age_years", np.nan)).abs().fillna(5.0)
    mileage_gap = (
        pd.to_numeric(candidates["mileage_wan_km"], errors="coerce") - query.get("mileage_wan_km", np.nan)
    ).abs().fillna(10.0)
    transfer_gap = (
        pd.to_numeric(candidates["transfer_count"], errors="coerce") - query.get("transfer_count", np.nan)
    ).abs().fillna(3.0)
    city_bonus = candidates["city_key_v194"].astype(str).eq(str(query.get("city_key_v194") or "")).astype(float) * 0.08
    color_bonus = candidates["color_key_v194"].astype(str).eq(str(query.get("color_key_v194") or "")).astype(float) * 0.03
    query_condition = str(query.get("condition_risk_level_strict") or "unknown")
    candidate_condition = candidates.get(
        "condition_risk_level_strict", pd.Series("unknown", index=candidates.index)
    ).fillna("unknown").astype(str)
    # "unknown" is evidence with an unobserved inspection, not proof that the
    # vehicle is clean. It may remain a comparable, but gets less support than
    # a condition-confirmed match. This makes the resulting price trace honest
    # about why two otherwise similar cars may trade at different prices.
    condition_bonus = pd.Series(0.0, index=candidates.index)
    condition_bonus.loc[candidate_condition.eq(query_condition)] = 0.06
    condition_bonus.loc[
        candidate_condition.eq("unknown") & (query_condition == "clean")
    ] = 0.015
    condition_penalty = pd.Series(0.0, index=candidates.index)
    condition_penalty.loc[
        candidate_condition.eq("minor_defect") & (query_condition == "clean")
    ] = 0.16
    score = (
        np.exp(-(age_gap / 2.0 + mileage_gap / 4.0 + transfer_gap / 2.5 + condition_penalty))
        + city_bonus
        + color_bonus
        + condition_bonus
    )
    return pd.Series(score, index=candidates.index).clip(lower=0.001, upper=1.2)


def _time_decay(query: dict[str, Any], candidates: pd.DataFrame, half_life_days: float) -> pd.Series:
    quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce", utc=True)
    if pd.notna(quote_time):
        quote_time = quote_time.tz_convert(None)
    event_time = pd.to_datetime(candidates["event_time"], errors="coerce", utc=True).dt.tz_convert(None)
    if pd.isna(quote_time):
        days = pd.Series(365.0, index=candidates.index)
    else:
        days = ((quote_time - event_time).dt.total_seconds() / 86400.0).clip(lower=0).fillna(365.0)
    decay = np.exp(-math.log(2) * days / half_life_days)
    return pd.Series(decay, index=candidates.index).clip(lower=0.02, upper=1.0)


def _level_penalty(level: pd.Series) -> pd.Series:
    mapping = {
        "L0": 1.00,
        "L1": 0.92,
        "L2": 0.78,
        "L2_WIDE_EXACT_TRIM": 0.46,
        "L3": 0.56,
        "L4": 0.38,
        "L5": 0.22,
        "B2C_BRIDGE": 0.18,
        "L6_FALLBACK": 0.08,
    }
    return level.map(mapping).fillna(0.05)


def retrieve_candidates(
    warehouse: pd.DataFrame,
    query: dict[str, Any],
    *,
    config: RetrievalConfig | None = None,
) -> pd.DataFrame:
    config = config or RetrievalConfig()
    q = normalize_query(query)
    quote_time = pd.to_datetime(q.get("quote_time"), errors="coerce", utc=True)
    if pd.notna(quote_time):
        quote_time = quote_time.tz_convert(None)
    candidates = warehouse.copy()
    if pd.notna(quote_time):
        knowledge_available = pd.to_datetime(candidates["knowledge_available_at"], errors="coerce", utc=True).dt.tz_convert(None)
        if "pricing_available_at" in candidates.columns:
            pricing_available = pd.to_datetime(candidates["pricing_available_at"], errors="coerce", utc=True).dt.tz_convert(None)
            available_at = pricing_available.where(pricing_available.notna(), knowledge_available)
        else:
            available_at = knowledge_available
        event_time = pd.to_datetime(candidates["event_time"], errors="coerce", utc=True).dt.tz_convert(None)
        asof_mask = (available_at <= quote_time) & (event_time < quote_time)
        candidates = candidates[asof_mask]
    if "observation_id" in candidates and q.get("observation_id"):
        candidates = candidates[candidates["observation_id"].astype(str) != str(q.get("observation_id"))]

    candidates = candidates[
        candidates["allowed_for_interval"].fillna(False)
        | candidates["allowed_for_c2b_point_baseline"].fillna(False)
        | candidates["allowed_for_c2b_bridge_input"].fillna(False)
    ].copy()
    if candidates.empty:
        return candidates

    # The evidence warehouse intentionally preserves source lineage. Multiple
    # ingestions can therefore contain the same physical transaction. Collapse
    # those lifecycle duplicates before scoring so one transaction gets one vote.
    # Use the strongest identity that is actually present, rather than a
    # compound key of all identities.  A mirrored source can have a different
    # lifecycle id while still representing the same market listing; grouping
    # on both fields would incorrectly let it vote twice.
    fallback_columns = [
        column
        for column in (
            "price_role", "price_yuan", "event_time", "brand_key", "series_key",
            "model_year", "canonical_trim_key", "city_key_v194",
        )
        if column in candidates.columns
    ]
    fallback_key = candidates[fallback_columns].fillna("").astype(str).agg("|".join, axis=1).replace("", np.nan)
    # Prefer the physical transaction signature over source-provided lifecycle
    # IDs.  A newly ingested confirmed actual can duplicate a transaction that
    # already exists in the base warehouse; if we start from lifecycle IDs, that
    # one deal votes twice and the Evidence Card shows repeated candidates.
    dedup_key = fallback_key.copy()
    for column in (
        "runtime_candidate_market_listing_fingerprint",
        "runtime_candidate_transaction_fingerprint",
        "runtime_candidate_lifecycle_key",
    ):
        if column not in candidates.columns:
            continue
        value = candidates[column].fillna("").astype(str).str.strip()
        dedup_key = dedup_key.where(dedup_key.notna(), value.where(value.ne(""), np.nan))
    candidates["runtime_candidate_dedup_key"] = dedup_key.fillna(fallback_key).fillna(candidates["observation_id"].astype(str))
    candidates["candidate_duplicate_group_size"] = candidates.groupby("runtime_candidate_dedup_key", dropna=False)[
        "observation_id"
    ].transform("size")
    candidates = (
        candidates.sort_values(["knowledge_available_at", "observation_id"])
        .drop_duplicates("runtime_candidate_dedup_key", keep="first")
        .copy()
    )

    # Wide first-stage blocking keeps the candidate pool big enough while avoiding unrelated brands.
    candidates = candidates[
        candidates["brand_key"].astype(str).eq(str(q.get("brand_key") or ""))
        & candidates["series_key"].astype(str).eq(str(q.get("series_key") or ""))
    ].copy()
    if candidates.empty:
        return candidates

    level = _semantic_level(q, candidates)
    same_power_code, same_trim_package = _configuration_match_flags(q, candidates)
    distance = _distance_score(q, candidates)
    time_decay = _time_decay(q, candidates, config.half_life_days)
    source_quality = pd.Series(0.25, index=candidates.index)
    source_quality.loc[candidates["price_role"].eq("INTERNAL_C2B_PURCHASE_ACTUAL")] = 1.0
    source_quality.loc[candidates["price_role"].eq("INTERNAL_B2C_SOLD_ACTUAL")] = 0.65
    source_quality.loc[candidates["price_role"].eq("EXTERNAL_B2C_LISTING")] = 0.45
    heuristic_weight = _level_penalty(level) * distance * time_decay * source_quality
    price_prior = pd.to_numeric(q.get("direct_price_prior"), errors="coerce")
    cluster_reference = pd.to_numeric(q.get("trusted_cluster_price"), errors="coerce")
    price_values = pd.to_numeric(candidates["price_yuan"], errors="coerce").clip(lower=1)
    if pd.notna(price_prior) and float(price_prior) > 0:
        direct_alignment = np.exp(-np.abs(np.log(price_values / float(price_prior))) / 0.22)
    else:
        direct_alignment = pd.Series(0.5, index=candidates.index)
    if pd.notna(cluster_reference) and float(cluster_reference) > 0:
        cluster_alignment = np.exp(-np.abs(np.log(price_values / float(cluster_reference))) / 0.16)
    else:
        cluster_alignment = pd.Series(0.5, index=candidates.index)
    configuration_prior = 1.0 + 0.18 * same_power_code + 0.12 * (same_power_code & same_trim_package)
    if pd.notna(cluster_reference) and float(cluster_reference) > 0:
        selector_score = heuristic_weight * (0.25 + 0.45 * direct_alignment + 0.30 * cluster_alignment) * configuration_prior
    elif pd.notna(price_prior) and float(price_prior) > 0:
        # The direct prior only reorders already-retrieved comparable cars; the
        # semantic/distance/time heuristic remains multiplicative and cannot be bypassed.
        selector_score = heuristic_weight * direct_alignment * configuration_prior
    else:
        selector_score = heuristic_weight * configuration_prior

    result = candidates.copy()
    result["query_uid"] = q["query_uid"]
    result["retrieval_level"] = level
    result["age_difference"] = (pd.to_numeric(result["age_years"], errors="coerce") - q.get("age_years", np.nan)).abs()
    result["mileage_difference"] = (
        pd.to_numeric(result["mileage_wan_km"], errors="coerce") - q.get("mileage_wan_km", np.nan)
    ).abs()
    result["transfer_difference"] = (
        pd.to_numeric(result["transfer_count"], errors="coerce") - q.get("transfer_count", np.nan)
    ).abs()
    result["city_match"] = result["city_key_v194"].astype(str).eq(str(q.get("city_key_v194") or "")).astype(int)
    result["color_match"] = result["color_key_v194"].astype(str).eq(str(q.get("color_key_v194") or "")).astype(int)
    result["condition_match"] = (
        result.get("condition_risk_level_strict", pd.Series("unknown", index=result.index))
        .fillna("unknown")
        .astype(str)
        .eq(str(q.get("condition_risk_level_strict") or "unknown"))
        .astype(int)
    )
    result["same_trim"] = result["canonical_trim_key"].astype(str).eq(str(q.get("canonical_trim_key") or "")).astype(int)
    result["same_configuration_across_year"] = (
        result.get("normalized_trim", pd.Series("", index=result.index)).astype(str).eq(str(q.get("normalized_trim") or ""))
        & pd.to_numeric(result["model_year"], errors="coerce").sub(float(q.get("model_year") or -9999)).abs().le(1)
        & bool(str(q.get("normalized_trim") or ""))
    ).astype(int)
    result["same_power_code"] = same_power_code
    result["same_trim_package"] = same_trim_package
    candidate_energy_result = result.get("normalized_energy_type", pd.Series("UNKNOWN", index=result.index)).fillna("UNKNOWN").astype(str)
    energy_from_key_result = result["canonical_trim_key"].astype(str).str.split("|").str[3].fillna("UNKNOWN")
    candidate_energy_result = candidate_energy_result.where(
        ~candidate_energy_result.isin({"", "UNKNOWN", "nan"}), energy_from_key_result
    )
    query_energy_result = str(q.get("normalized_energy_type") or "UNKNOWN")
    result["same_powertrain"] = (
        candidate_energy_result.eq(query_energy_result)
        & candidate_energy_result.ne("UNKNOWN")
        & (query_energy_result != "UNKNOWN")
    ).astype(int)
    # Keep the *why* of the ranking as structured data.  The previous score
    # included city and colour bonuses, but the evidence card could not prove
    # which observable dimensions matched.  These fields are intentionally
    # independent of any target price and can be recomputed at quote time.
    result["same_model_year"] = pd.to_numeric(result["model_year"], errors="coerce").eq(q.get("model_year")).astype(int)
    result["age_close_match"] = result["age_difference"].le(0.75).fillna(False).astype(int)
    result["age_near_match"] = result["age_difference"].le(1.50).fillna(False).astype(int)
    result["mileage_close_match"] = result["mileage_difference"].le(1.0).fillna(False).astype(int)
    result["mileage_near_match"] = result["mileage_difference"].le(3.0).fillna(False).astype(int)
    result["transfer_close_match"] = result["transfer_difference"].le(1).fillna(False).astype(int)
    result["transfer_near_match"] = result["transfer_difference"].le(2).fillna(False).astype(int)
    result["close_numeric_match"] = (
        result["age_close_match"].eq(1)
        & result["mileage_close_match"].eq(1)
        & result["transfer_close_match"].eq(1)
    ).astype(int)
    result["near_numeric_match"] = (
        result["age_near_match"].eq(1)
        & result["mileage_near_match"].eq(1)
        & result["transfer_near_match"].eq(1)
    ).astype(int)
    result["observable_match_count"] = (
        result["same_trim"]
        + result["same_model_year"]
        + result["age_close_match"]
        + result["mileage_close_match"]
        + result["transfer_close_match"]
        + result["city_match"]
        + result["color_match"]
        + result["condition_match"]
    )
    # When all other characteristics are identical, same-city evidence takes
    # precedence over same-colour evidence.  City reflects a local market;
    # colour is retained as a smaller demand preference, never a reason to
    # leapfrog a closer or same-city candidate.
    result["observable_sort_priority"] = (
        result["same_trim"] * 1_000_000
        + result["same_model_year"] * 100_000
        + result["close_numeric_match"] * 10_000
        + result["near_numeric_match"] * 1_000
        + result["condition_match"] * 100
        + result["city_match"] * 10
        + result["color_match"]
    )
    result["candidate_match_profile"] = np.select(
        [
            result["retrieval_level"].eq("L0"),
            result["retrieval_level"].eq("L1"),
            result["retrieval_level"].eq("L2"),
            result["retrieval_level"].eq("L2_WIDE_EXACT_TRIM"),
        ],
        [
            "EXACT_TRIM_YEAR_CLOSE_NUMERICS_SAME_CITY",
            "EXACT_TRIM_YEAR_CLOSE_NUMERICS_NATIONAL",
            "EXACT_TRIM_YEAR_NEAR_NUMERICS",
            "EXACT_TRIM_YEAR_WIDE_NUMERICS_CONTEXT_ONLY",
        ],
        default="NON_EXACT_TRIM_CONTEXT_ONLY",
    )
    result["candidate_match_reason_codes"] = (
        "same_trim=" + result["same_trim"].astype(str)
        + "|same_year=" + result["same_model_year"].astype(str)
        + "|age_close=" + result["age_close_match"].astype(str)
        + "|mileage_close=" + result["mileage_close_match"].astype(str)
        + "|transfer_close=" + result["transfer_close_match"].astype(str)
        + "|condition_match=" + result["condition_match"].astype(str)
        + "|city_match=" + result["city_match"].astype(str)
        + "|color_match=" + result["color_match"].astype(str)
    )
    result["distance_score"] = distance
    result["time_decay"] = time_decay
    result["source_quality_score"] = source_quality
    result["heuristic_retrieval_weight"] = heuristic_weight
    result["direct_price_alignment"] = direct_alignment
    result["trusted_cluster_alignment"] = cluster_alignment
    result["final_retrieval_weight"] = selector_score
    result["selection_reason"] = np.where(
        pd.notna(cluster_reference),
        "SEMANTIC_DISTANCE_TIME_X_DIRECT_PRIOR_X_TRUSTED_CLUSTER",
        np.where(
            pd.notna(price_prior),
            "SEMANTIC_DISTANCE_TIME_X_DIRECT_PRICE_PRIOR",
            "SEMANTIC_DISTANCE_TIME_HEURISTIC",
        ),
    )
    eligible = result["allowed_for_c2b_point_baseline"].fillna(False) & result["final_retrieval_weight"].gt(0)
    l01 = eligible & result["retrieval_level"].isin({"L0", "L1"})
    exact = eligible & result["retrieval_level"].isin({"L0", "L1", "L2"})
    same_config_across_year = eligible & result["retrieval_level"].eq("L4") & result["same_configuration_across_year"].eq(1)
    if int(l01.sum()) >= 2:
        point_pool = l01
        selection_tier = "STRICT_CLOSE_EXACT_TRIM"
    elif int(exact.sum()) >= 2:
        point_pool = exact
        selection_tier = "STRICT_EXACT_TRIM"
    elif int(same_config_across_year.sum()) >= 1:
        point_pool = same_config_across_year
        selection_tier = "FALLBACK_SAME_CONFIGURATION_ACROSS_YEAR"
    else:
        # Different trims, adjacent configurations and same-series records are
        # useful market context and interval evidence, but never a C2B point
        # baseline unless a separately verified relationship table authorizes it.
        point_pool = pd.Series(False, index=result.index)
        selection_tier = "NO_STRICT_OR_SAME_CONFIGURATION_POINT_EVIDENCE"
    result["point_selection_tier"] = selection_tier
    result["strict_point_candidate"] = point_pool & result["retrieval_level"].isin(config.strict_baseline_levels)
    result["fallback_point_candidate"] = point_pool & result["retrieval_level"].isin(config.fallback_baseline_levels)
    result["used_for_point_baseline"] = result["strict_point_candidate"] | result["fallback_point_candidate"]
    result["used_for_interval"] = result["retrieval_level"].isin(config.interval_levels)
    # A market-reference candidate can still be shown to the user, but a
    # matching 740Li must never appear below a 735Li merely because the latter
    # happened to get a slightly higher generic heuristic score. Point-price
    # eligibility remains independent of this display/order preference.
    result["configuration_display_priority"] = np.select(
        [
            result["same_trim"].eq(1),
            result["same_power_code"].eq(1) & result["same_trim_package"].eq(1),
            result["same_power_code"].eq(1),
        ],
        [0, 1, 2],
        default=3,
    )
    result = result.sort_values(
        [
            "strict_point_candidate",
            "fallback_point_candidate",
            "configuration_display_priority",
            "observable_sort_priority",
            "retrieval_level",
            "final_retrieval_weight",
            "time_decay",
        ],
        ascending=[False, False, True, False, True, False, False],
    ).head(config.max_candidates)
    result["final_rank"] = np.arange(1, len(result) + 1)
    result["retrieval_policy_version"] = RETRIEVAL_POLICY_VERSION
    return result


def statistical_price_from_candidates(candidates: pd.DataFrame) -> dict[str, Any]:
    if candidates.empty or "used_for_point_baseline" not in candidates.columns:
        strict = pd.DataFrame()
    else:
        strict = candidates[candidates["used_for_point_baseline"].fillna(False)].copy()
    if strict.empty:
        return {
            "statistical_baseline_price": np.nan,
            "baseline_method": "NO_STRICT_C2B_BASELINE",
            "baseline_candidate_count": 0,
            "baseline_iqr_ratio": np.nan,
            "baseline_price_range_low": np.nan,
            "baseline_price_range_high": np.nan,
            "confidence_evidence_bucket": "manual",
        }
    values = pd.to_numeric(strict["price_yuan"], errors="coerce").to_numpy(dtype=float)
    ranker_weights = pd.to_numeric(
        strict.get("listwise_final_weight", pd.Series(np.nan, index=strict.index)), errors="coerce"
    )
    use_listwise = bool(ranker_weights.notna().all() and ranker_weights.gt(0).any())
    weights = (
        ranker_weights.fillna(0.0).to_numpy(dtype=float)
        if use_listwise
        else pd.to_numeric(strict["final_retrieval_weight"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    )
    p25 = weighted_quantile(values, weights, 0.25)
    p40 = weighted_quantile(values, weights, 0.40)
    p50 = weighted_quantile(values, weights, 0.50)
    p75 = weighted_quantile(values, weights, 0.75)
    iqr_ratio = (p75 - p25) / p50 if p50 else np.nan
    count = int(len(strict))
    strict_count = int(strict.get("strict_point_candidate", pd.Series(False, index=strict.index)).fillna(False).sum())
    fallback_count = int(strict.get("fallback_point_candidate", pd.Series(False, index=strict.index)).fillna(False).sum())
    weight_sum = float(np.nansum(weights))
    top_level = str(strict["retrieval_level"].iloc[0]) if count else "none"
    if strict_count >= 5 and iqr_ratio <= 0.12 and top_level in {"L0", "L1"}:
        bucket = "high"
    elif strict_count >= 3 and iqr_ratio <= 0.20 and top_level in {"L0", "L1", "L2"}:
        bucket = "medium"
    elif count >= 1:
        bucket = "low"
    else:
        bucket = "manual"
    return {
        "statistical_baseline_price": p25 if use_listwise else p50,
        "baseline_method": (
            "LISTWISE_RANKED_WEIGHTED_P25_INTERNAL_C2B_STRICT"
            if use_listwise and strict_count
            else "LISTWISE_RANKED_WEIGHTED_P25_INTERNAL_C2B_SAME_CONFIGURATION_FALLBACK"
            if use_listwise
            else "WEIGHTED_MEDIAN_INTERNAL_C2B_STRICT"
            if strict_count
            else "WEIGHTED_MEDIAN_INTERNAL_C2B_SAME_CONFIGURATION_FALLBACK"
        ),
        "baseline_candidate_count": count,
        "strict_baseline_candidate_count": strict_count,
        "fallback_baseline_candidate_count": fallback_count,
        "baseline_weight_sum": weight_sum,
        "listwise_ranker_used": use_listwise,
        "baseline_p25": p25,
        "baseline_p40": p40,
        "baseline_p50": p50,
        "baseline_p75": p75,
        "baseline_iqr_ratio": iqr_ratio,
        "baseline_price_range_low": p25,
        "baseline_price_range_high": p75,
        "confidence_evidence_bucket": bucket,
    }


def evidence_ledger(query: dict[str, Any], candidates: pd.DataFrame, price_summary: dict[str, Any]) -> dict[str, Any]:
    top = candidates.head(20).copy()
    fields = [
        "final_rank",
        "observation_id",
        "source_type",
        "price_role",
        "price_yuan",
        "event_time",
        "knowledge_available_at",
        "brand",
        "series",
        "model_year",
        "trim",
        "city",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "condition_risk_level_strict",
        "retrieval_level",
        "candidate_match_profile",
        "candidate_match_reason_codes",
        "observable_match_count",
        "same_model_year",
        "age_close_match",
        "mileage_close_match",
        "transfer_close_match",
        "city_match",
        "color_match",
        "condition_match",
        "distance_score",
        "time_decay",
        "source_quality_score",
        "final_retrieval_weight",
        "heuristic_retrieval_weight",
        "listwise_raw_score",
        "listwise_final_weight",
        "direct_price_alignment",
        "trusted_cluster_alignment",
        "strict_point_candidate",
        "fallback_point_candidate",
        "used_for_point_baseline",
        "used_for_interval",
        "quality_reason_codes_v194",
    ]
    available_fields = [field for field in fields if field in top.columns]
    top_records = json.loads(top[available_fields].to_json(orient="records", force_ascii=False, date_format="iso"))
    return {
        "ledger_version": "v194_evidence_ledger_v1",
        "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        "raw_query": query,
        "normalized_query": normalize_query(query),
        "candidate_count": int(len(candidates)),
        "baseline_candidate_count": int(price_summary.get("baseline_candidate_count") or 0),
        "price_summary": price_summary,
        "top_candidates": top_records,
        "explanation_facts": [
            "仅使用 quote_time 之前已知的证据。",
            "C2B 单点基线只允许内部真实收车价进入。",
            "内部/外部 B2C 只用于区间、折算输入或人工参考，不直接作为 C2B 单点。",
            "统计基线使用严格候选的加权中位数，权重包含语义层级、六要素距离、时间衰减和来源质量。",
        ],
    }
