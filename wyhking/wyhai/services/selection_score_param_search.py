from __future__ import annotations

import itertools
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .label_gate import apply_label_gate
from .metric_smoothing import smooth_metric
from .sample_confidence_calculator import calculate_sample_confidence
from .selection_score_config import GENERATED_CONFIG_PATH, get_selection_score_config
from .selection_strategy_metrics import (
    baseline_metrics,
    clean_metrics,
    leader_metric_pass,
    load_business_dataset,
    relative_lifts,
    subset_metrics,
    topk_group_keys,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "results" / "evals"


def run_selection_score_param_search(
    *,
    config_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_parameter_sets: int | None = None,
    write_files: bool = True,
) -> dict[str, Any]:
    config = get_selection_score_config(config_path, include_generated=False)
    search_cfg = config.get("parameter_search") or {}
    dataset = load_business_dataset(
        (config.get("paths") or {}).get("business_90d_csv"),
        group_grain=search_cfg.get("group_grain") or (config.get("selection") or {}).get("group_grain"),
    )
    baseline = baseline_metrics(dataset)
    parameter_sets = _parameter_sets(search_cfg, max_parameter_sets or int(search_cfg.get("max_parameter_sets", 180)))
    scored_results = [
        _evaluate_parameter_set(index, params, dataset, baseline, config)
        for index, params in enumerate(parameter_sets, start=1)
    ]
    scored_results.sort(key=lambda item: item.get("parameter_set_score") or 0, reverse=True)
    best = scored_results[0] if scored_results else {}
    report = {
        "version": "selection_score_param_search_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": {"business_90d_csv": dataset.source_path},
        "dataset_metadata": dataset.metadata,
        "baseline_all": baseline,
        "parameter_search_config": search_cfg,
        "tested_parameter_set_count": len(scored_results),
        "best_parameter_set": best,
        "top_parameter_sets": scored_results[:20],
        "coverage": _candidate_coverage(parameter_sets, search_cfg),
        "notes": [
            "最终机会分 = business_score * confidence_score，排序不再使用原始均值或旧 opportunity_score。",
            "小样本不会被删除，但会通过置信度上限、基线平滑和标签门控降级。",
            "parameter_set_score 同时惩罚低样本误推荐和过度过滤，避免只选极少数组合。",
        ],
    }
    if write_files:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "selection_score_parameter_search_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        generated = {
            "parameter_set_id": best.get("parameter_set_id"),
            "parameter_set_score": best.get("parameter_set_score"),
            "metric_grain": dataset.metadata.get("metric_grain"),
            "history_metric_version": "time_aware_v5",
            "history_window_days": dataset.metadata.get("history_window_days"),
            "window_start": dataset.metadata.get("window_start"),
            "window_end": dataset.metadata.get("window_end"),
            "selected_parameter_config": best.get("selected_parameter_config") or {},
            "selected_at": report["generated_at"],
            "source_report": str(report_path),
        }
        GENERATED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_CONFIG_PATH.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
        report["artifacts"] = {
            "report_json": str(report_path),
            "generated_config_json": str(GENERATED_CONFIG_PATH),
        }
    return report


def _evaluate_parameter_set(
    index: int,
    params: dict[str, Any],
    dataset: Any,
    baseline: dict[str, Any],
    base_config: dict[str, Any],
) -> dict[str, Any]:
    local_config = _config_for_params(base_config, params)
    scored = _score_group_frame(dataset.group_frame, baseline, local_config, params)
    sold = pd.to_numeric(scored["sold_count"], errors="coerce").fillna(0)
    acquired = pd.to_numeric(scored["acquired_count"], errors="coerce").fillna(0)
    contribution = pd.to_numeric(scored["total_profit_contribution"], errors="coerce").fillna(0)
    confidence = pd.to_numeric(scored["confidence_score"], errors="coerce").fillna(0)
    eligible = scored[
        sold.ge(float(params["min_recommend_sold_count"]))
        & acquired.ge(float(params["min_recommend_acquired_count"]))
        & contribution.ge(float(params["min_profit_contribution_for_recommend"]))
        & confidence.ge(0.40)
    ].copy()
    target_candidates = max(1, int(float(baseline.get("baseline_candidate_count") or 0) * float(params["target_selection_rate"])))
    selected_keys = topk_group_keys(eligible, "final_opportunity_score", target_candidates)
    selected = eligible[eligible["group_key"].astype(str).isin(set(selected_keys))].copy()
    strong = selected[
        pd.to_numeric(selected["sold_count"], errors="coerce").fillna(0).ge(float(params["min_strong_recommend_sold_count"]))
        & pd.to_numeric(selected["acquired_count"], errors="coerce").fillna(0).ge(float(params["min_strong_recommend_acquired_count"]))
        & pd.to_numeric(selected["total_profit_contribution"], errors="coerce").fillna(0).ge(float(params["min_profit_contribution_for_strong"]))
    ].copy()
    metrics = subset_metrics(dataset, selected_keys, baseline)
    lifts = relative_lifts(metrics, baseline)
    recommend_pass = leader_metric_pass(metrics, baseline, mode="recommend")
    topk = _topk_metrics(dataset, scored, baseline)
    selection_rate = float(metrics.get("selection_rate") or 0)
    profit_retention = float(metrics.get("profit_retention_rate") or 0)
    low_sample_recommend = int(selected["low_sample_flag"].sum()) if not selected.empty else 0
    low_sample_strong = int(strong["low_sample_flag"].sum()) if not strong.empty else 0
    before_sample_gate = scored[
        (pd.to_numeric(scored["business_score"], errors="coerce") >= 66)
        & scored["leader_all_pass"].astype(bool)
    ]
    excluded_due_low_sample = before_sample_gate[
        pd.to_numeric(before_sample_gate["sold_count"], errors="coerce").fillna(0)
        < int(params["min_recommend_sold_count"])
    ]
    parameter_score = _parameter_set_score(
        metrics=metrics,
        lifts=lifts,
        topk=topk,
        leader_pass=recommend_pass,
        low_sample_recommend_count=low_sample_recommend,
        selected_group_count=len(selected),
        selection_rate=selection_rate,
        profit_retention=profit_retention,
        config=base_config,
    )
    return clean_metrics(
        {
            "parameter_set_id": f"sel_score_{index:04d}",
            "parameter_set_score": parameter_score,
            "selected_parameter_config": {"parameter_set_id": f"sel_score_{index:04d}", **params},
            "metrics": metrics,
            "lifts": lifts,
            "recommend_pass": recommend_pass,
            "topk_evaluation": topk,
            "selected_group_count": int(len(selected)),
            "eligible_group_count": int(len(eligible)),
            "requested_target_candidate_count": target_candidates,
            "actual_selected_candidate_count": int(metrics.get("candidate_count") or 0),
            "strong_recommend_group_count": int(len(strong)),
            "selected_count_before_sample_gate": int(len(before_sample_gate)),
            "selected_count_after_sample_gate": int(len(selected)),
            "excluded_due_to_low_sample_count": int(len(excluded_due_low_sample)),
            "low_sample_recommend_count": low_sample_recommend,
            "low_sample_strong_recommend_count": low_sample_strong,
            "selection_rate": selection_rate,
            "profit_retention_rate": profit_retention,
            "small_sample_examples": _sample_rows(scored[scored["low_sample_flag"].astype(bool)].sort_values("final_opportunity_score", ascending=False)),
            "top_selected_examples": _sample_rows(selected.sort_values("final_opportunity_score", ascending=False)),
        }
    )


def _score_group_frame(
    group_frame: pd.DataFrame,
    baseline: dict[str, Any],
    config: dict[str, Any],
    params: dict[str, Any],
) -> pd.DataFrame:
    frame = group_frame.copy()
    baseline_total_profit = float(baseline.get("baseline_total_profit") or 0)
    sold = pd.to_numeric(frame.get("sold_count"), errors="coerce").fillna(0).clip(lower=0)
    acquired = pd.to_numeric(frame.get("acquired_count"), errors="coerce").fillna(0).clip(lower=0)
    candidate = pd.to_numeric(frame.get("candidate_count"), errors="coerce").fillna(0).clip(lower=0)
    k = max(0.0, float(params["smoothing_strength"]))

    frame["smoothed_avg_profit"] = _smooth_series(frame.get("avg_profit"), baseline.get("baseline_avg_profit"), sold, k)
    frame["smoothed_avg_days_to_sell"] = _smooth_series(frame.get("avg_days_to_sell"), baseline.get("baseline_avg_days_to_sell"), sold, k)
    frame["smoothed_acquisition_conversion_rate"] = _smooth_series(
        frame.get("acquisition_conversion_rate"),
        baseline.get("baseline_acquisition_conversion_rate"),
        sold,
        k,
    )
    frame["smoothed_sales_conversion_rate"] = _smooth_series(
        frame.get("sales_conversion_rate"),
        baseline.get("baseline_sales_conversion_rate"),
        sold,
        k,
    )

    turnover_ratio = _divide_series(frame["smoothed_avg_days_to_sell"], baseline.get("baseline_avg_days_to_sell"))
    profit_ratio = _divide_series(frame["smoothed_avg_profit"], baseline.get("baseline_avg_profit"))
    acquisition_ratio = _divide_series(frame["smoothed_acquisition_conversion_rate"], baseline.get("baseline_acquisition_conversion_rate"))
    sales_ratio = _divide_series(frame["smoothed_sales_conversion_rate"], baseline.get("baseline_sales_conversion_rate"))
    total_profit = pd.to_numeric(frame.get("total_profit"), errors="coerce").fillna(0).clip(lower=0)
    contribution_base = _cohort_total_profit(frame, total_profit)
    contribution = total_profit / contribution_base.mask(contribution_base <= 0)
    if baseline_total_profit > 0:
        contribution = contribution.fillna(total_profit / baseline_total_profit)
    else:
        contribution = contribution.fillna(0.0)
    frame["total_profit_contribution"] = contribution
    frame["leader_all_pass"] = (
        turnover_ratio.le(0.9)
        & profit_ratio.ge(1.1)
        & sales_ratio.ge(1.1)
        & acquisition_ratio.ge(1.1)
    )
    frame["leader_avoid_pass"] = (
        turnover_ratio.ge(1.1)
        & profit_ratio.le(0.9)
        & sales_ratio.le(0.9)
        & acquisition_ratio.le(0.9)
    )

    components = {
        "average_profit_weight": _ratio_score_series(profit_ratio),
        "turnover_weight": _ratio_score_series(_divide_series(baseline.get("baseline_avg_days_to_sell"), frame["smoothed_avg_days_to_sell"])),
        "acquisition_conversion_weight": _ratio_score_series(acquisition_ratio),
        "sales_conversion_weight": _ratio_score_series(sales_ratio),
        "total_profit_weight": _contribution_score_series(contribution),
    }
    total_weight = sum(float(params.get(key) or 0) for key in components) or 1.0
    business = sum(float(params.get(key) or 0) * value for key, value in components.items()) / total_weight
    frame["business_score"] = business.clip(0, 100).round(4)

    cap = pd.Series(0.45, index=frame.index)
    sample_level = pd.Series("unknown", index=frame.index)
    cap = cap.mask(sold <= 2, 0.25)
    sample_level = sample_level.mask(sold <= 2, "very_low")
    cap = cap.mask((sold >= 3) & (sold <= 4), 0.40)
    sample_level = sample_level.mask((sold >= 3) & (sold <= 4), "low")
    cap = cap.mask((sold >= 5) & (sold <= 9), 0.55)
    sample_level = sample_level.mask((sold >= 5) & (sold <= 9), "limited")
    cap = cap.mask((sold >= 10) & (sold <= 19), 0.75)
    sample_level = sample_level.mask((sold >= 10) & (sold <= 19), "medium")
    cap = cap.mask((sold >= 20) & (sold <= 29), 0.90)
    sample_level = sample_level.mask((sold >= 20) & (sold <= 29), "high")
    cap = cap.mask((sold >= 30) & (acquired >= 50), 1.00)
    sample_level = sample_level.mask((sold >= 30) & (acquired >= 50), "strong")
    acquired_support = np.sqrt((acquired / 50).clip(upper=1))
    candidate_support = np.sqrt((candidate / 80).clip(upper=1))
    confidence = (cap * (0.68 + 0.22 * acquired_support + 0.10 * candidate_support)).clip(upper=cap)
    frame["sample_level"] = sample_level
    frame["confidence_score"] = _confidence_series_by_mode(confidence, params["confidence_weight_mode"]).clip(0, 1).round(4)
    frame["final_opportunity_score"] = (frame["business_score"] * frame["confidence_score"]).clip(0, 100).round(4)

    strong_gate = (config.get("label_gate") or {}).get("strong_recommend") or {}
    recommend_gate = (config.get("label_gate") or {}).get("recommend") or {}
    strong_mask = (
        frame["leader_all_pass"]
        & frame["final_opportunity_score"].ge(float(strong_gate.get("min_final_score", 72)))
        & frame["business_score"].ge(float(strong_gate.get("min_business_score", 78)))
        & sold.ge(float(strong_gate.get("min_sold_count", 20)))
        & acquired.ge(float(strong_gate.get("min_acquired_count", 30)))
        & frame["confidence_score"].ge(float(strong_gate.get("min_confidence_score", 0.75)))
        & contribution.ge(float(strong_gate.get("min_total_profit_contribution", 0.02)))
    )
    recommend_mask = (
        frame["leader_all_pass"]
        & frame["final_opportunity_score"].ge(float(recommend_gate.get("min_final_score", 58)))
        & frame["business_score"].ge(float(recommend_gate.get("min_business_score", 66)))
        & sold.ge(float(recommend_gate.get("min_sold_count", 10)))
        & acquired.ge(float(recommend_gate.get("min_acquired_count", 20)))
        & frame["confidence_score"].ge(float(recommend_gate.get("min_confidence_score", 0.55)))
        & contribution.ge(float(recommend_gate.get("min_total_profit_contribution", 0.005)))
    )
    label = pd.Series("WATCH", index=frame.index)
    label = label.mask(frame["final_opportunity_score"].lt(38), "CAUTION")
    label = label.mask(frame["leader_avoid_pass"] & sold.ge(10), "AVOID")
    label = label.mask(recommend_mask, "RECOMMEND")
    label = label.mask(strong_mask, "STRONG_RECOMMEND")
    frame["label"] = label
    frame["recommendation_label"] = label.map(
        {
            "STRONG_RECOMMEND": "重点关注",
            "RECOMMEND": "可关注",
            "WATCH": "正常跟踪",
            "CAUTION": "谨慎收",
            "AVOID": "暂缓收",
        }
    ).fillna("正常跟踪")
    frame["low_sample_flag"] = sold < int(params["min_recommend_sold_count"])
    frame["gate_reasons"] = np.where(frame["label"].isin(["STRONG_RECOMMEND", "RECOMMEND"]), "通过推荐门控", "未通过样本/四项经营指标/贡献门控")
    return frame


def _business_score_for_params(
    *,
    smooth_profit: float | None,
    smooth_days: float | None,
    smooth_acq: float | None,
    smooth_sale: float | None,
    contribution: float,
    baseline: dict[str, Any],
    params: dict[str, Any],
) -> float:
    components = {
        "average_profit_weight": _ratio_score(_ratio(smooth_profit, baseline.get("baseline_avg_profit"))),
        "turnover_weight": _ratio_score(_ratio(baseline.get("baseline_avg_days_to_sell"), smooth_days)),
        "acquisition_conversion_weight": _ratio_score(_ratio(smooth_acq, baseline.get("baseline_acquisition_conversion_rate"))),
        "sales_conversion_weight": _ratio_score(_ratio(smooth_sale, baseline.get("baseline_sales_conversion_rate"))),
        "total_profit_weight": _contribution_score(contribution),
    }
    total_weight = sum(float(params.get(key) or 0) for key in components)
    if total_weight <= 0:
        return 0.0
    score = sum(float(params.get(key) or 0) * value for key, value in components.items()) / total_weight
    return round(max(0.0, min(100.0, score)), 4)


def _smooth_series(raw: Any, baseline: Any, sample_size: pd.Series, strength: float) -> pd.Series:
    raw_series = pd.to_numeric(raw, errors="coerce") if isinstance(raw, pd.Series) else pd.Series(raw, index=sample_size.index)
    base = _maybe_num(baseline)
    if base is None:
        return pd.to_numeric(raw_series, errors="coerce")
    current = pd.to_numeric(raw_series, errors="coerce").fillna(base)
    if strength <= 0:
        return current
    n = pd.to_numeric(sample_size, errors="coerce").fillna(0).clip(lower=0)
    return (n * current + strength * base) / (n + strength)


def _cohort_total_profit(frame: pd.DataFrame, total_profit: pd.Series) -> pd.Series:
    group_grain_values = set(frame.get("group_grain", pd.Series(dtype=str)).dropna().astype(str))
    if group_grain_values and group_grain_values <= {"brand+series"}:
        return pd.Series(float(total_profit.sum()), index=frame.index)
    key_columns = [
        column
        for column in ("city_key", "price_band_key", "energy_type_key", "vehicle_category_key")
        if column in frame.columns
    ]
    if not key_columns:
        total = float(total_profit.sum())
        return pd.Series(total, index=frame.index)
    cohort_key = frame[key_columns].fillna("").astype(str).agg("|".join, axis=1)
    cohort_total = total_profit.groupby(cohort_key).transform("sum")
    sparse = cohort_total <= 0
    if sparse.any():
        cohort_total = cohort_total.mask(sparse, float(total_profit.sum()))
    return cohort_total


def _divide_series(left: Any, right: Any) -> pd.Series:
    if isinstance(left, pd.Series):
        left_series = pd.to_numeric(left, errors="coerce")
        index = left.index
    elif isinstance(right, pd.Series):
        index = right.index
        left_series = pd.Series(_maybe_num(left), index=index)
    else:
        return pd.Series(dtype=float)
    if isinstance(right, pd.Series):
        right_series = pd.to_numeric(right, errors="coerce")
    else:
        right_series = pd.Series(_maybe_num(right), index=index)
    denominator = right_series.mask(right_series.abs() < 1e-9)
    return left_series / denominator


def _ratio_score_series(ratio: pd.Series) -> pd.Series:
    return (50 + (pd.to_numeric(ratio, errors="coerce").fillna(0.96875) - 1) * 160).clip(0, 100)


def _contribution_score_series(contribution: pd.Series) -> pd.Series:
    value = pd.to_numeric(contribution, errors="coerce").fillna(0).clip(lower=0)
    return pd.Series(
        np.select(
            [
                value >= 0.08,
                value >= 0.03,
                value >= 0.01,
            ],
            [
                100.0,
                75 + (value - 0.03) / 0.05 * 25,
                55 + (value - 0.01) / 0.02 * 20,
            ],
            default=35 + (value / 0.01) * 20,
        ),
        index=contribution.index,
    ).clip(0, 100)


def _confidence_series_by_mode(confidence: pd.Series, mode: str) -> pd.Series:
    confidence = pd.to_numeric(confidence, errors="coerce").fillna(0).clip(0, 1)
    if mode == "sqrt":
        return np.sqrt(confidence)
    if mode == "log":
        return np.log1p(confidence * 1.718281828) / np.log1p(1.718281828)
    return confidence


def _parameter_set_score(
    *,
    metrics: dict[str, Any],
    lifts: dict[str, Any],
    topk: dict[str, Any],
    leader_pass: dict[str, Any],
    low_sample_recommend_count: int,
    selected_group_count: int,
    selection_rate: float,
    profit_retention: float,
    config: dict[str, Any],
) -> float:
    search_cfg = config.get("parameter_search") or {}
    leader_fraction = sum(1 for key, value in leader_pass.items() if key != "all_pass" and value) / 4
    top10 = topk.get("top10") or {}
    conversion_lift = _avg_present([lifts.get("acquisition_conversion_lift"), lifts.get("sales_conversion_lift")])
    low_sample_penalty = low_sample_recommend_count / max(1, selected_group_count)
    min_rate = float(search_cfg.get("min_selection_rate", 0.08))
    max_rate = float(search_cfg.get("max_selection_rate", 0.45))
    min_retention = float(search_cfg.get("min_profit_retention_rate", 0.12))
    over_filtering_penalty = 0.0
    if selection_rate < min_rate:
        over_filtering_penalty += (min_rate - selection_rate) / max(min_rate, 1e-6)
    if selection_rate > max_rate:
        over_filtering_penalty += (selection_rate - max_rate) / max(max_rate, 1e-6)
    if profit_retention < min_retention:
        over_filtering_penalty += (min_retention - profit_retention) / max(min_retention, 1e-6)
    score = (
        0.22 * leader_fraction
        + 0.20 * _norm(profit_retention, 0.30)
        + 0.18 * _norm(profit_retention, 0.30)
        + 0.15 * _norm(top10.get("avg_profit_lift"), 1.10)
        + 0.15 * _norm(conversion_lift, 1.10)
        + 0.10 * _norm(lifts.get("days_to_sell_improvement"), 1 / 0.90)
        - 0.15 * min(1.0, low_sample_penalty)
        - 0.10 * min(1.0, over_filtering_penalty)
    )
    return round(max(0.0, score) * 100, 4)


def _topk_metrics(dataset: Any, scored: pd.DataFrame, baseline: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    total_candidates = int(baseline.get("baseline_candidate_count") or 0)
    for rate in (0.10, 0.20, 0.30):
        target = max(1, int(total_candidates * rate))
        keys = topk_group_keys(scored, "final_opportunity_score", target)
        metrics = subset_metrics(dataset, keys, baseline)
        out[f"top{int(rate * 100)}"] = clean_metrics({**metrics, **relative_lifts(metrics, baseline)})
    return out


def _parameter_sets(search_cfg: dict[str, Any], max_sets: int) -> list[dict[str, Any]]:
    fields = [
        "min_recommend_sold_count",
        "min_strong_recommend_sold_count",
        "min_recommend_acquired_count",
        "min_strong_recommend_acquired_count",
        "smoothing_strength",
        "min_profit_contribution_for_recommend",
        "min_profit_contribution_for_strong",
        "target_selection_rate",
        "confidence_weight_mode",
        "total_profit_weight",
        "average_profit_weight",
        "turnover_weight",
        "acquisition_conversion_weight",
        "sales_conversion_weight",
    ]
    values = {field: list(search_cfg.get(field) or []) for field in fields}
    defaults = {field: vals[len(vals) // 2] for field, vals in values.items() if vals}
    sets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(params: dict[str, Any]) -> None:
        cleaned = {field: params.get(field, defaults.get(field)) for field in fields}
        token = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
        if token not in seen:
            seen.add(token)
            sets.append(cleaned)

    add(defaults)
    for field in fields:
        for value in values.get(field, []):
            params = dict(defaults)
            params[field] = value
            add(params)

    rng = random.Random(20260709)
    pools = [values[field] for field in fields]
    for combo in itertools.islice(_random_product(rng, pools), max(0, max_sets * 8)):
        add(dict(zip(fields, combo)))
        if len(sets) >= max_sets:
            break
    return sets[:max_sets]


def _random_product(rng: random.Random, pools: list[list[Any]]):
    while True:
        yield [rng.choice(pool) for pool in pools]


def _config_for_params(base_config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(json.dumps(base_config, ensure_ascii=False))
    gates = config.setdefault("label_gate", {})
    gates.setdefault("recommend", {}).update(
        {
            "min_sold_count": params["min_recommend_sold_count"],
            "min_acquired_count": params["min_recommend_acquired_count"],
            "min_total_profit_contribution": params["min_profit_contribution_for_recommend"],
        }
    )
    gates.setdefault("strong_recommend", {}).update(
        {
            "min_sold_count": params["min_strong_recommend_sold_count"],
            "min_acquired_count": params["min_strong_recommend_acquired_count"],
            "min_total_profit_contribution": params["min_profit_contribution_for_strong"],
        }
    )
    config.setdefault("metric_smoothing", {})["strength"] = params["smoothing_strength"]
    return config


def _candidate_coverage(parameter_sets: list[dict[str, Any]], search_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        field: sorted({params.get(field) for params in parameter_sets}, key=lambda value: str(value))
        for field in search_cfg
        if isinstance(search_cfg.get(field), list)
    }


def _sample_rows(frame: pd.DataFrame, limit: int = 8) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    columns = [
        "city",
        "brand",
        "series",
        "price_band",
        "candidate_count",
        "acquired_count",
        "sold_count",
        "business_score",
        "confidence_score",
        "final_opportunity_score",
        "label",
        "total_profit_contribution",
        "gate_reasons",
    ]
    return [clean_metrics(row) for row in frame.head(limit)[columns].to_dict(orient="records")]


def _ratio(left: Any, right: Any) -> float | None:
    left_number = _maybe_num(left)
    right_number = _maybe_num(right)
    if left_number is None or right_number is None or abs(right_number) < 1e-9:
        return None
    return left_number / right_number


def _ratio_score(ratio: Any) -> float:
    value = _maybe_num(ratio)
    if value is None:
        return 45.0
    return max(0.0, min(100.0, 50 + (value - 1) * 160))


def _contribution_score(value: Any) -> float:
    contribution = max(0.0, _num(value))
    if contribution >= 0.08:
        return 100.0
    if contribution >= 0.03:
        return 75 + (contribution - 0.03) / 0.05 * 25
    if contribution >= 0.01:
        return 55 + (contribution - 0.01) / 0.02 * 20
    return 35 + contribution / 0.01 * 20


def _confidence_by_mode(confidence: float, mode: str) -> float:
    confidence = max(0.0, min(1.0, confidence))
    if mode == "sqrt":
        return math.sqrt(confidence)
    if mode == "log":
        return math.log1p(confidence * 1.718281828) / math.log1p(1.718281828)
    return confidence


def _norm(value: Any, target: Any) -> float:
    ratio = _ratio(value, target)
    if ratio is None:
        return 0.0
    return max(0.0, min(1.5, ratio)) / 1.5


def _avg_present(values: list[Any]) -> float | None:
    numbers = [_maybe_num(value) for value in values]
    numbers = [value for value in numbers if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _num(value: Any) -> float:
    number = _maybe_num(value)
    return number if number is not None else 0.0


def _maybe_num(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _ge(value: Any, threshold: float) -> bool:
    number = _maybe_num(value)
    return bool(number is not None and number >= threshold)


def _le(value: Any, threshold: float) -> bool:
    number = _maybe_num(value)
    return bool(number is not None and number <= threshold)


if __name__ == "__main__":
    print(json.dumps(run_selection_score_param_search(), ensure_ascii=False, indent=2))
