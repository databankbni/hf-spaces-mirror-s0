from __future__ import annotations

import math
from bisect import bisect_right
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .business_market_workbook_loader import get_business_market_loader, normalize_text
from .selection_strategy_metrics import SelectionBusinessDataset, clean_metrics, safe_divide


DEFAULT_EVENT_XLSX = Path("/Users/bytedance/Downloads/政策和新车最新表_2026-07-09_AI补充版.xlsx")
DEFAULT_RANKING_CSV = Path("data/external/dongchedi_rankings/current/normalized_ranking_signals.csv")


SIGNAL_BOUNDARIES = {
    "baseline_all": [],
    "market_only": ["market"],
    "dsi_only": ["dsi"],
    "ranking_only": ["ranking"],
    "market_daily_only": ["market", "event"],
    "market_daily_dsi": ["market", "event", "dsi"],
    "market_daily_ranking": ["market", "event", "ranking"],
    "full_signal": ["market", "event", "dsi", "ranking"],
    "outcome_guarded_full": ["market", "event", "dsi", "ranking", "acquisition_guard", "sales_guard"],
}


def allowed_signals(strategy_name: str) -> list[str]:
    if strategy_name not in SIGNAL_BOUNDARIES:
        raise ValueError(f"unknown selection strategy: {strategy_name}")
    return list(SIGNAL_BOUNDARIES[strategy_name])


def build_signal_frame(dataset: SelectionBusinessDataset, config: dict[str, Any] | None = None) -> pd.DataFrame:
    config = config or {}
    group_frame = dataset.group_frame.copy()
    baseline = config.get("baseline_metrics") or {}
    market = _market_signal_frame(group_frame, baseline)
    event = _event_signal_frame(
        group_frame,
        Path(config.get("paths", {}).get("policy_new_car_xlsx") or DEFAULT_EVENT_XLSX),
    )
    dsi = _dsi_signal_frame(group_frame)
    ranking = _ranking_signal_frame(
        group_frame,
        Path(config.get("paths", {}).get("ranking_signals_csv") or DEFAULT_RANKING_CSV),
    )
    acquisition_guard = _conversion_guard_signal_frame(
        group_frame,
        baseline,
        prefix="acquisition_guard",
        numerator_column="acquired_conversion_numerator",
        denominator_column="acquired_conversion_denominator",
        baseline_key="baseline_acquisition_conversion_rate",
        metric_name="buyer_post2_toc_b2c_success_90d",
        config=config,
    )
    sales_guard = _conversion_guard_signal_frame(
        group_frame,
        baseline,
        prefix="sales_guard",
        numerator_column="listed_conversion_numerator",
        denominator_column="listed_conversion_denominator",
        baseline_key="baseline_sales_conversion_rate",
        metric_name="listed_to_sold_rate_45d",
        config=config,
    )
    out = group_frame.merge(market, on="group_key", how="left")
    out = out.merge(event, on="group_key", how="left")
    out = out.merge(dsi, on="group_key", how="left")
    out = out.merge(ranking, on="group_key", how="left")
    out = out.merge(acquisition_guard, on="group_key", how="left")
    out = out.merge(sales_guard, on="group_key", how="left")
    defaults = {
        "market_score": 50.0,
        "market_avoid_score": 50.0,
        "market_signal_score": 50.0,
        "business_outcome_score": 50.0,
        "event_score": 50.0,
        "event_avoid_score": 50.0,
        "event_risk_score": 0.0,
        "event_opportunity_score": 0.0,
        "dsi_score": 50.0,
        "dsi_avoid_score": 50.0,
        "ranking_score": 50.0,
        "ranking_avoid_score": 50.0,
        "ranking_demand_signal": 0.0,
        "ranking_liquidity_signal": 0.0,
        "ranking_positive_score": 0.0,
        "ranking_discount_risk_score": 0.0,
        "ranking_noise_penalty": 0.0,
        "acquisition_guard_score": 50.0,
        "acquisition_guard_avoid_score": 50.0,
        "sales_guard_score": 50.0,
        "sales_guard_avoid_score": 50.0,
    }
    for column, default in defaults.items():
        if column not in out.columns:
            out[column] = default
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(default)
    for column in ("event_evidence", "ranking_evidence", "dsi_label", "dsi_match_level", "ranking_match_level"):
        if column not in out.columns:
            out[column] = "" if column != "dsi_label" else "未知"
        out[column] = out[column].fillna("")
    return _attach_hierarchical_sample_confidence(out)


def score_strategy_groups(signal_frame: pd.DataFrame, strategy_name: str, config: dict[str, Any] | None = None) -> pd.DataFrame:
    config = config or {}
    weights = (config.get("strategy_weights") or {}).get(strategy_name)
    if weights is None:
        signals = allowed_signals(strategy_name)
        weights = {signal: 1 / len(signals) for signal in signals} if signals else {}
    forbidden = set(weights) - set(allowed_signals(strategy_name))
    if forbidden:
        raise ValueError(f"{strategy_name} uses forbidden signals: {sorted(forbidden)}")
    scored = signal_frame.copy()
    score = pd.Series(0.0, index=scored.index)
    total_weight = 0.0
    for signal_name, weight in weights.items():
        column = f"{signal_name}_score"
        if column not in scored.columns:
            raise ValueError(f"missing signal column: {column}")
        score += pd.to_numeric(scored[column], errors="coerce").fillna(50) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        raw_score = pd.Series(50.0, index=scored.index)
    else:
        raw_score = (score / total_weight).clip(0, 100)
    avoid_weights = (config.get("avoid_strategy_weights") or {}).get(strategy_name) or weights
    forbidden_avoid = set(avoid_weights) - set(allowed_signals(strategy_name))
    if forbidden_avoid:
        raise ValueError(f"{strategy_name} avoid score uses forbidden signals: {sorted(forbidden_avoid)}")
    avoid_score = pd.Series(0.0, index=scored.index)
    avoid_weight = 0.0
    for signal_name, weight in avoid_weights.items():
        avoid_column = f"{signal_name}_avoid_score"
        if avoid_column in scored.columns:
            source = pd.to_numeric(scored[avoid_column], errors="coerce").fillna(50)
        else:
            source = 100 - pd.to_numeric(scored[f"{signal_name}_score"], errors="coerce").fillna(50)
        avoid_score += source * float(weight)
        avoid_weight += float(weight)
    scored[f"{strategy_name}_avoid_score"] = (avoid_score / avoid_weight if avoid_weight else 50).clip(0, 100).round(4)
    confidence_source = scored["sample_confidence_score"] if "sample_confidence_score" in scored else pd.Series(1.0, index=scored.index)
    confidence = pd.to_numeric(confidence_source, errors="coerce").fillna(0.25).clip(0, 1)
    scored[f"{strategy_name}_business_score"] = raw_score.round(4)
    scored[f"{strategy_name}_recommend_score"] = (raw_score * confidence).clip(0, 100).round(4)
    return scored


def _attach_hierarchical_sample_confidence(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    parent = work.groupby(["brand_key", "series_key"], dropna=False).agg(
        series_candidate_count=("candidate_count", "sum"),
        series_acquired_count=("acquired_count", "sum"),
        series_sold_count=("sold_count", "sum"),
    ).reset_index()
    work = work.merge(parent, on=["brand_key", "series_key"], how="left")
    sold = pd.to_numeric(work["series_sold_count"], errors="coerce").fillna(0).clip(lower=0)
    acquired = pd.to_numeric(work["series_acquired_count"], errors="coerce").fillna(0).clip(lower=0)
    candidate = pd.to_numeric(work["series_candidate_count"], errors="coerce").fillna(0).clip(lower=0)
    cap = pd.Series(0.25, index=work.index, dtype=float)
    level = pd.Series("very_low", index=work.index, dtype=object)
    cap = cap.mask((sold >= 3) & (sold <= 4), 0.40)
    level = level.mask((sold >= 3) & (sold <= 4), "low")
    cap = cap.mask((sold >= 5) & (sold <= 9), 0.55)
    level = level.mask((sold >= 5) & (sold <= 9), "limited")
    cap = cap.mask((sold >= 10) & (sold <= 19), 0.75)
    level = level.mask((sold >= 10) & (sold <= 19), "medium")
    cap = cap.mask((sold >= 20) & (sold <= 29), 0.90)
    level = level.mask((sold >= 20) & (sold <= 29), "high")
    cap = cap.mask((sold >= 30) & (acquired >= 50), 1.00)
    level = level.mask((sold >= 30) & (acquired >= 50), "strong")
    support = 0.68 + 0.22 * np.sqrt((acquired / 50).clip(upper=1)) + 0.10 * np.sqrt((candidate / 80).clip(upper=1))
    work["sample_confidence_score"] = (cap * support).clip(upper=cap).round(4)
    work["sample_level"] = level
    work["local_group_sold_count"] = pd.to_numeric(work["sold_count"], errors="coerce").fillna(0).astype(int)
    work["sample_scope"] = "national_series_parent_with_local_group_evidence"
    return work


def _market_signal_frame(group_frame: pd.DataFrame, baseline: dict[str, Any]) -> pd.DataFrame:
    loader = get_business_market_loader()
    market_rows = pd.DataFrame(loader.city_series_records)
    state_by_key: dict[str, float] = {}
    risk_by_key: dict[str, float] = {}
    state_by_series: dict[str, float] = {}
    risk_by_series: dict[str, float] = {}
    if not market_rows.empty:
        market_rows["market_match_key"] = (
            market_rows.get("city", "").map(normalize_text)
            + "|"
            + market_rows.get("brand", "").map(normalize_text)
            + "|"
            + market_rows.get("series", "").map(normalize_text)
        )
        for column in (
            "deal_sample_90d",
            "detail_uv",
            "favorite_count",
            "sell_through_rate",
            "listing_count",
            "inventory_cycle",
            "avg_deal_cycle",
            "price_volatility",
            "price_change_30d",
        ):
            if column not in market_rows:
                market_rows[column] = None
            market_rows[column] = pd.to_numeric(market_rows[column], errors="coerce")
        market_rows["state_score"] = market_rows.apply(_state_score, axis=1)
        market_rows["risk_score"] = market_rows.apply(_state_risk_score, axis=1)
        state_by_key = dict(zip(market_rows["market_match_key"], market_rows["state_score"]))
        risk_by_key = dict(zip(market_rows["market_match_key"], market_rows["risk_score"]))
        by_series = market_rows.groupby(market_rows["series"].map(normalize_text))["state_score"].mean()
        state_by_series = by_series.to_dict()
        risk_by_series = market_rows.groupby(market_rows["series"].map(normalize_text))["risk_score"].mean().to_dict()

    rows: list[dict[str, Any]] = []
    for row in group_frame.to_dict(orient="records"):
        coarse_key = _market_match_key(row)
        state_score = state_by_key.get(coarse_key) or state_by_series.get(row.get("series_key")) or 50
        risk_score = risk_by_key.get(coarse_key) or risk_by_series.get(row.get("series_key")) or max(0, 100 - state_score)
        business_score = _business_outcome_score(row, baseline)
        business_avoid_score = _business_outcome_avoid_score(row, baseline)
        rows.append(
            {
                "group_key": row.get("group_key"),
                "market_score": round(max(0, min(100, state_score)), 3),
                "market_signal_score": round(max(0, min(100, state_score)), 3),
                "market_avoid_score": round(max(0, min(100, risk_score)), 3),
                "market_state_score": round(state_score, 3),
                "market_signal_source": "market_fields_only",
                "business_outcome_score": round(business_score, 3),
                "business_outcome_avoid_score": round(business_avoid_score, 3),
                "business_outcome_source": "reference_only_not_used_by_p0",
            }
        )
    return pd.DataFrame(rows)


def _market_match_key(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(key) or "") for key in ("city_key", "brand_key", "series_key"))


def _state_score(row: pd.Series) -> float:
    demand = max(
        _percentile_from_row(row, "deal_sample_90d"),
        _percentile_from_row(row, "detail_uv"),
        _percentile_from_row(row, "favorite_count"),
    )
    liquidity = 0.45 * _percentile_from_row(row, "sell_through_rate") + 0.25 * _percentile_from_row(row, "listing_count")
    cycle = 1 - _percentile_from_row(row, "avg_deal_cycle")
    inventory = 1 - _percentile_from_row(row, "inventory_cycle")
    volatility = 1 - _percentile_from_row(row, "price_volatility")
    price_change = _safe(row.get("price_change_30d")) or 0
    price_score = 1.0 if -0.03 <= price_change <= 0.06 else 0.55 if price_change > 0.06 else 0.35
    category_bonus = {
        "结构性行情": 8,
        "流动行情": 6,
        "上涨行情": 4,
        "常规行情": 0,
        "阴跌行情": -12,
        "急跌行情": -25,
    }.get(str(row.get("market_category") or ""), -4)
    score = 100 * (0.22 * demand + 0.22 * liquidity + 0.18 * cycle + 0.18 * inventory + 0.12 * volatility + 0.08 * price_score)
    return max(0, min(100, score + category_bonus))


def _state_risk_score(row: pd.Series) -> float:
    inventory_risk = _percentile_from_row(row, "inventory_cycle")
    slow_cycle = _percentile_from_row(row, "avg_deal_cycle")
    volatility = _percentile_from_row(row, "price_volatility")
    low_sell_through = 1 - _percentile_from_row(row, "sell_through_rate")
    weak_demand = 1 - max(
        _percentile_from_row(row, "deal_sample_90d"),
        _percentile_from_row(row, "detail_uv"),
        _percentile_from_row(row, "favorite_count"),
    )
    price_change = _safe(row.get("price_change_30d")) or 0
    price_drop_risk = 1.0 if price_change < -0.05 else 0.70 if price_change < -0.02 else 0.30
    category_bonus = {
        "急跌行情": 24,
        "阴跌行情": 14,
        "常规行情": 0,
        "上涨行情": -4,
        "流动行情": -8,
        "结构性行情": -8,
    }.get(str(row.get("market_category") or ""), 4)
    score = 100 * (
        0.22 * inventory_risk
        + 0.22 * slow_cycle
        + 0.18 * volatility
        + 0.16 * low_sell_through
        + 0.14 * weak_demand
        + 0.08 * price_drop_risk
    )
    return max(0, min(100, score + category_bonus))


def _percentile_from_row(row: pd.Series, column: str) -> float:
    value = _safe(row.get(column))
    if value is None:
        return 0.5
    # The safe workbook table is already pre-filtered.  A log-style transform is
    # enough for an ordinal state score without keeping global distributions here.
    if column in {"avg_deal_cycle", "inventory_cycle", "price_volatility"}:
        return max(0.0, min(1.0, value / (value + 30)))
    return max(0.0, min(1.0, math.log1p(max(value, 0)) / 10))


def _business_outcome_score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    profit_ratio = safe_divide(row.get("avg_profit"), baseline.get("baseline_avg_profit"))
    turnover_ratio = safe_divide(baseline.get("baseline_avg_days_to_sell"), row.get("avg_days_to_sell"))
    acquisition_ratio = safe_divide(row.get("acquisition_conversion_rate"), baseline.get("baseline_acquisition_conversion_rate"))
    sales_ratio = safe_divide(row.get("sales_conversion_rate"), baseline.get("baseline_sales_conversion_rate"))
    sold_count = _safe(row.get("sold_count")) or 0
    sample_penalty = 0.78 if sold_count < 3 else 0.90 if sold_count < 8 else 1.0
    score = (
        0.32 * _ratio_score(profit_ratio)
        + 0.24 * _ratio_score(turnover_ratio)
        + 0.22 * _ratio_score(acquisition_ratio)
        + 0.22 * _ratio_score(sales_ratio)
    )
    return max(0, min(100, score * sample_penalty))


def _business_outcome_avoid_score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    profit_bad = safe_divide(baseline.get("baseline_avg_profit"), row.get("avg_profit"))
    turnover_bad = safe_divide(row.get("avg_days_to_sell"), baseline.get("baseline_avg_days_to_sell"))
    acquisition_bad = safe_divide(baseline.get("baseline_acquisition_conversion_rate"), row.get("acquisition_conversion_rate"))
    sales_bad = safe_divide(baseline.get("baseline_sales_conversion_rate"), row.get("sales_conversion_rate"))
    sold_count = _safe(row.get("sold_count")) or 0
    sample_penalty = 0.80 if sold_count < 3 else 0.92 if sold_count < 8 else 1.0
    score = (
        0.30 * _ratio_score(profit_bad)
        + 0.24 * _ratio_score(turnover_bad)
        + 0.23 * _ratio_score(acquisition_bad)
        + 0.23 * _ratio_score(sales_bad)
    )
    return max(0, min(100, score * sample_penalty))


def _event_signal_frame(group_frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    base = group_frame[["group_key", "city", "city_key", "brand", "brand_key", "series", "series_key", "energy_type"]].copy()
    base["event_opportunity_score"] = 0.0
    base["event_risk_score"] = 0.0
    base["event_evidence"] = ""
    if not path.is_file():
        base["event_score"] = 50.0
        return base[["group_key", "event_score", "event_opportunity_score", "event_risk_score", "event_evidence"]]

    try:
        policies = pd.read_excel(path, sheet_name="policy_impact_events")
    except Exception:
        policies = pd.DataFrame()
    try:
        new_cars = pd.read_excel(path, sheet_name="daily_new_car_events_latest")
    except Exception:
        new_cars = pd.DataFrame()

    for _, policy in policies.iterrows():
        level = str(policy.get("impact_level") or "").strip().lower()
        confidence = str(policy.get("confidence") or "").strip().lower()
        amount = {"high": 18, "medium": 12, "low": 6}.get(level, 8) * {"high": 1.0, "medium": 0.8, "low": 0.55}.get(confidence, 0.7)
        direction = str(policy.get("impact_direction") or "").strip().lower()
        opportunity = amount if direction == "positive" else amount * 0.45 if direction == "mixed" else 0
        risk = amount if direction in {"negative", "risk"} else amount * 0.55 if direction == "mixed" else amount * 0.20
        mask = _policy_mask(base, policy)
        if not mask.any():
            continue
        evidence = _compact_evidence(policy.get("policy_name"), policy.get("selection_impact") or policy.get("evidence_text"))
        base.loc[mask, "event_opportunity_score"] += opportunity
        base.loc[mask, "event_risk_score"] += risk
        base.loc[mask, "event_evidence"] = base.loc[mask, "event_evidence"].map(lambda text: _append_evidence(text, evidence))

    known_series = sorted(
        set(base["series"].dropna().astype(str)),
        key=lambda value: (-len(normalize_text(value)), normalize_text(value), value),
    )
    for _, item in new_cars.iterrows():
        name = str(item.get("品牌车型") or "")
        advice = str(item.get("收车建议") or "")
        judgement = str(item.get("属性判定") or "")
        matched = _match_series(name, known_series)
        if not matched:
            continue
        risk = 14 if any(key in advice + judgement for key in ("压价", "谨慎", "旧款", "改款", "新增", "限定")) else 6
        opportunity = 6 if any(key in advice + judgement for key in ("重点", "关注", "热销")) else 2
        mask = base["series"].isin(matched)
        evidence = _compact_evidence(name, f"{judgement}；{advice}")
        base.loc[mask, "event_opportunity_score"] += opportunity
        base.loc[mask, "event_risk_score"] += risk
        base.loc[mask, "event_evidence"] = base.loc[mask, "event_evidence"].map(lambda text: _append_evidence(text, evidence))

    base["event_score"] = (50 + base["event_opportunity_score"] - base["event_risk_score"]).clip(0, 100)
    base["event_avoid_score"] = (50 + base["event_risk_score"] - base["event_opportunity_score"]).clip(0, 100)
    return base[["group_key", "event_score", "event_avoid_score", "event_opportunity_score", "event_risk_score", "event_evidence"]]


def _policy_mask(base: pd.DataFrame, policy: pd.Series) -> pd.Series:
    mask = pd.Series(True, index=base.index)
    scoped = False
    city = normalize_text(policy.get("city"))
    if city:
        mask &= base["city_key"].eq(city)
        scoped = True
    brand = normalize_text(policy.get("affected_brand"))
    if brand:
        mask &= base["brand_key"].str.contains(brand, regex=False)
        scoped = True
    series = normalize_text(policy.get("affected_series"))
    if series:
        mask &= base["series_key"].str.contains(series, regex=False)
        scoped = True
    energy = str(policy.get("affected_energy_type") or "")
    if energy and energy not in {"不限", "nan"}:
        if "新能源" in energy:
            mask &= base["energy_type"].astype(str).str.contains("新能源|纯电|插混|增程", regex=True)
            scoped = True
        elif "燃油" in energy:
            mask &= base["energy_type"].astype(str).str.contains("燃油", regex=False)
            scoped = True
    category = str(policy.get("affected_vehicle_category") or "")
    if not scoped and any(key in category for key in ("乘用车", "二手")):
        return pd.Series(True, index=base.index)
    return mask if scoped else pd.Series(False, index=base.index)


def _dsi_signal_frame(group_frame: pd.DataFrame) -> pd.DataFrame:
    loader = get_business_market_loader()
    rows: list[dict[str, Any]] = []
    for row in group_frame[["group_key", "series", "price_band", "energy_type"]].to_dict(orient="records"):
        dsi = loader.dsi_for_series(row.get("series"))
        sample_count = int(dsi.get("sample_count") or 0)
        missing = sample_count <= 0 or str(dsi.get("label") or "未知") == "未知"
        match_level = "missing" if missing else "series_fallback"
        confidence = 0.0 if missing else min(0.55, 0.25 + sample_count / 200)
        rows.append(
            {
                "group_key": row.get("group_key"),
                "dsi_score": float(dsi.get("score") or 50),
                "dsi_avoid_score": float(100 - float(dsi.get("score") or 50)),
                "dsi_label": dsi.get("label") or "未知",
                "dsi_match_level": match_level,
                "dsi_match_confidence": round(confidence, 3),
                "dsi_sample_count": sample_count,
                "dsi_missing_flag": missing,
            }
        )
    return pd.DataFrame(rows)


def _ranking_signal_frame(group_frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    base = group_frame[["group_key", "series_key", "city_key", "price_band_key", "energy_type_key", "vehicle_category_key"]].copy()
    if not path.is_file():
        base["ranking_score"] = 50.0
        base["ranking_avoid_score"] = 50.0
        base["ranking_demand_signal"] = 0.0
        base["ranking_liquidity_signal"] = 0.0
        base["ranking_positive_score"] = 0.0
        base["ranking_discount_risk_score"] = 0.0
        base["ranking_noise_penalty"] = 0.0
        base["ranking_match_level"] = "missing"
        base["ranking_evidence"] = ""
        return base.drop(columns=["series_key", "city_key", "price_band_key", "energy_type_key", "vehicle_category_key"])
    wanted = set(base["series_key"].astype(str))
    aggregates: dict[str, dict[str, Any]] = {}
    usecols = ["rank_type", "city", "series_name", "vehicle_category", "energy_type", "price_band", "rank", "signal_strength", "evidence_text"]
    for chunk in pd.read_csv(path, usecols=lambda column: column in usecols, chunksize=120000, low_memory=False):
        chunk["series_key"] = chunk["series_name"].map(normalize_text)
        chunk = chunk[chunk["series_key"].isin(wanted)]
        if chunk.empty:
            continue
        for record in chunk.to_dict(orient="records"):
            series_key = record.get("series_key")
            if not series_key:
                continue
            keys = _ranking_record_keys(record)
            rank_points = _ranking_points(record.get("rank"), record.get("signal_strength"))
            rank_type = str(record.get("rank_type") or "")
            for level, key in keys:
                agg = aggregates.setdefault(key, {"demand": 0.0, "liquidity": 0.0, "risk": 0.0, "level": level, "evidence": []})
                if rank_type in {"热门榜", "城市榜"}:
                    agg["demand"] += rank_points
                elif rank_type in {"销量榜", "新能源榜", "懂车分榜"}:
                    agg["liquidity"] += rank_points
                elif rank_type == "降价榜":
                    agg["risk"] += rank_points
                if len(agg["evidence"]) < 3 and record.get("evidence_text"):
                    agg["evidence"].append(str(record.get("evidence_text")))

    if not aggregates:
        base["ranking_score"] = 50.0
        base["ranking_avoid_score"] = 50.0
        base["ranking_demand_signal"] = 0.0
        base["ranking_liquidity_signal"] = 0.0
        base["ranking_positive_score"] = 0.0
        base["ranking_discount_risk_score"] = 0.0
        base["ranking_noise_penalty"] = 0.0
        base["ranking_match_level"] = "missing"
        base["ranking_evidence"] = ""
        return base.drop(columns=["series_key", "city_key", "price_band_key", "energy_type_key", "vehicle_category_key"])

    demand_values = sorted(item["demand"] for item in aggregates.values())
    liquidity_values = sorted(item["liquidity"] for item in aggregates.values())
    risk_values = sorted(item["risk"] for item in aggregates.values())
    rows: list[dict[str, Any]] = []
    for record in base.to_dict(orient="records"):
        key, level = _best_ranking_key(record, aggregates)
        agg = aggregates.get(key) if key else None
        if not agg:
            rows.append(
                {
                    "group_key": record.get("group_key"),
                    "ranking_score": 50.0,
                    "ranking_avoid_score": 50.0,
                    "ranking_demand_signal": 0.0,
                    "ranking_liquidity_signal": 0.0,
                    "ranking_positive_score": 0.0,
                    "ranking_discount_risk_score": 0.0,
                    "ranking_noise_penalty": 0.0,
                    "ranking_match_level": "missing",
                    "ranking_evidence": "",
                }
            )
            continue
        demand_score = _rank_in_values(demand_values, agg["demand"]) * 100
        liquidity_score = _rank_in_values(liquidity_values, agg["liquidity"]) * 100
        risk_score = _rank_in_values(risk_values, agg["risk"]) * 100
        positive_score = max(demand_score * 0.45, liquidity_score * 0.75)
        noise_penalty = max(0, demand_score - liquidity_score) * 0.18 + risk_score * 0.12
        ranking_score = max(0, min(100, 50 + demand_score * 0.10 + liquidity_score * 0.28 - risk_score * 0.24 - noise_penalty))
        ranking_avoid_score = max(0, min(100, 50 + risk_score * 0.34 + noise_penalty * 0.25 - liquidity_score * 0.18))
        rows.append(
            {
                "group_key": record.get("group_key"),
                "ranking_score": round(ranking_score, 3),
                "ranking_avoid_score": round(ranking_avoid_score, 3),
                "ranking_demand_signal": round(demand_score, 3),
                "ranking_liquidity_signal": round(liquidity_score, 3),
                "ranking_positive_score": round(positive_score, 3),
                "ranking_discount_risk_score": round(risk_score, 3),
                "ranking_noise_penalty": round(noise_penalty, 3),
                "ranking_match_level": level,
                "ranking_evidence": "；".join(agg["evidence"][:3]),
            }
        )
    out = pd.DataFrame(rows)
    out["ranking_score"] = pd.to_numeric(out["ranking_score"], errors="coerce").fillna(50.0)
    out["ranking_avoid_score"] = pd.to_numeric(out["ranking_avoid_score"], errors="coerce").fillna(50.0)
    out["ranking_demand_signal"] = pd.to_numeric(out["ranking_demand_signal"], errors="coerce").fillna(0.0)
    out["ranking_liquidity_signal"] = pd.to_numeric(out["ranking_liquidity_signal"], errors="coerce").fillna(0.0)
    out["ranking_positive_score"] = pd.to_numeric(out["ranking_positive_score"], errors="coerce").fillna(0.0)
    out["ranking_discount_risk_score"] = pd.to_numeric(out["ranking_discount_risk_score"], errors="coerce").fillna(0.0)
    out["ranking_noise_penalty"] = pd.to_numeric(out["ranking_noise_penalty"], errors="coerce").fillna(0.0)
    out["ranking_match_level"] = out["ranking_match_level"].fillna("missing")
    out["ranking_evidence"] = out["ranking_evidence"].fillna("")
    return out


def strategy_signal_summary(strategy_name: str) -> dict[str, Any]:
    signals = allowed_signals(strategy_name)
    return {
        "strategy_name": strategy_name,
        "used_signals": signals,
        "uses_market": "market" in signals,
        "uses_event": "event" in signals,
        "uses_dsi": "dsi" in signals,
        "uses_ranking": "ranking" in signals,
        "outcome_informed": bool({"acquisition_guard", "sales_guard", "business_outcome"} & set(signals)),
    }


def _conversion_guard_signal_frame(
    group_frame: pd.DataFrame,
    baseline: dict[str, Any],
    *,
    prefix: str,
    numerator_column: str,
    denominator_column: str,
    baseline_key: str,
    metric_name: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Build a two-level empirical-Bayes conversion guard.

    Fine city/price/energy/body groups are intentionally not trusted at face
    value. The national brand-series rate is first shrunk to baseline_all, then
    each fine group is shrunk to that parent. This prevents 1/1 or 2/2 groups
    from dominating either recommendation or avoidance rankings.
    """
    strength = max(1.0, float((config.get("metric_smoothing") or {}).get("strength") or 20))
    base = float(baseline.get(baseline_key) or 0)
    work = group_frame[
        ["group_key", "brand_key", "series_key", numerator_column, denominator_column]
    ].copy()
    work["_row_order"] = np.arange(len(work))
    work[numerator_column] = pd.to_numeric(work[numerator_column], errors="coerce").fillna(0).clip(lower=0)
    work[denominator_column] = pd.to_numeric(work[denominator_column], errors="coerce").fillna(0).clip(lower=0)
    parent = (
        work.groupby(["brand_key", "series_key"], dropna=False)[[numerator_column, denominator_column]]
        .sum()
        .reset_index()
    )
    if base > 0:
        parent["_parent_rate"] = (
            parent[numerator_column] + strength * base
        ) / (parent[denominator_column] + strength)
    else:
        parent["_parent_rate"] = np.where(
            parent[denominator_column] > 0,
            parent[numerator_column] / parent[denominator_column].replace(0, np.nan),
            0.0,
        )
    work = work.merge(parent[["brand_key", "series_key", "_parent_rate"]], on=["brand_key", "series_key"], how="left")
    work = work.sort_values("_row_order")
    local_rate = (
        work[numerator_column] + strength * work["_parent_rate"].fillna(base)
    ) / (work[denominator_column] + strength)
    if base > 0:
        score = (50 + (local_rate / base - 1) * 160).clip(0, 100)
        avoid_score = (50 + (base / local_rate.clip(lower=0.01) - 1) * 160).clip(0, 100)
    else:
        score = pd.Series(50.0, index=work.index)
        avoid_score = pd.Series(50.0, index=work.index)
    return pd.DataFrame(
        {
            "group_key": work["group_key"].to_numpy(),
            f"{prefix}_score": score.to_numpy().round(4),
            f"{prefix}_avoid_score": avoid_score.to_numpy().round(4),
            f"{prefix}_smoothed_rate": local_rate.to_numpy().round(6),
            f"{prefix}_parent_rate": work["_parent_rate"].fillna(base).to_numpy().round(6),
            f"{prefix}_local_denominator": work[denominator_column].to_numpy(dtype=float),
            f"{prefix}_metric_name": metric_name,
            f"{prefix}_smoothing_strength": strength,
        }
    )


def _ranking_record_keys(record: dict[str, Any]) -> list[tuple[str, str]]:
    series = normalize_text(record.get("series_name"))
    if not series:
        return []
    city = normalize_text(record.get("city"))
    price_band = normalize_text(record.get("price_band"))
    energy = normalize_text(record.get("energy_type"))
    category = normalize_text(record.get("vehicle_category"))
    keys: list[tuple[str, str]] = []
    if city and price_band and energy and category:
        keys.append(("city_price_energy_category_series", "|".join([series, city, price_band, energy, category])))
    if city and price_band and energy:
        keys.append(("city_price_energy_series", "|".join([series, city, price_band, energy])))
    if price_band and energy:
        keys.append(("price_energy_series", "|".join([series, price_band, energy])))
    keys.append(("series_fallback", series))
    return keys


def _best_ranking_key(group: dict[str, Any], aggregates: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
    series = str(group.get("series_key") or "")
    city = str(group.get("city_key") or "")
    price_band = str(group.get("price_band_key") or "")
    energy = str(group.get("energy_type_key") or "")
    category = str(group.get("vehicle_category_key") or "")
    candidates = [
        ("city_price_energy_category_series", "|".join([series, city, price_band, energy, category])),
        ("city_price_energy_series", "|".join([series, city, price_band, energy])),
        ("price_energy_series", "|".join([series, price_band, energy])),
        ("series_fallback", series),
    ]
    for level, key in candidates:
        if key in aggregates:
            return key, level
    return None, "missing"


def _ratio_score(ratio: Any) -> float:
    number = _safe(ratio)
    if number is None:
        return 42.0
    return max(0.0, min(100.0, 50.0 + (number - 1.0) * 52.0))


def _safe(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _compact_evidence(title: Any, text: Any) -> str:
    title_text = str(title or "").strip()
    body = str(text or "").strip()
    return (title_text + "：" + body)[:160] if body else title_text[:160]


def _append_evidence(current: str, evidence: str) -> str:
    if not evidence:
        return current
    items = [item for item in str(current or "").split("；") if item]
    if evidence not in items:
        items.append(evidence)
    return "；".join(items[:3])


def _match_series(text: str, known_series: list[str]) -> list[str]:
    normalized = normalize_text(text)
    out: list[str] = []
    for series in known_series:
        key = normalize_text(series)
        if key and (key in normalized or normalized in key):
            out.append(series)
            if len(out) >= 3:
                break
    return out


def _ranking_points(rank: Any, strength: Any) -> float:
    try:
        rank_number = max(1, int(float(rank)))
    except Exception:
        rank_number = 50
    rank_score = max(0.05, 1 - (rank_number - 1) / 60)
    strength_score = {"high": 1.0, "medium": 0.72, "low": 0.45}.get(str(strength or "").lower(), 0.6)
    return rank_score * strength_score


def _rank_in_values(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    return bisect_right(values, value) / len(values)
