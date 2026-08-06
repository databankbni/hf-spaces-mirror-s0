from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .selection_signal_strategy import (
    SIGNAL_BOUNDARIES,
    allowed_signals,
    build_signal_frame,
    score_strategy_groups,
    strategy_signal_summary,
)
from .selection_strategy_ablation_reporter import write_ablation_report
from .selection_strategy_metrics import (
    SelectionBusinessDataset,
    avoid_scale_pass,
    baseline_metrics,
    clean_metrics,
    leader_metric_pass,
    load_business_dataset,
    relative_lifts,
    scale_pass,
    subset_metrics,
    topk_group_keys,
)
from .selection_strategy_score import (
    choose_final_strategy,
    dsi_increment,
    normalized_strategy_components,
    ranking_increment,
    strategy_score,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("selection_strategy_config.yaml")
DEFAULT_OUTPUT_DIR = ROOT / "results" / "evals"
P0_STRATEGIES = ["market_daily_only", "market_daily_dsi", "market_daily_ranking", "full_signal"]
OUTCOME_INFORMED_STRATEGIES = ["outcome_guarded_full"]
OPTIONAL_STRATEGIES = ["market_only", "dsi_only", "ranking_only"]


DEFAULT_CONFIG: dict[str, Any] = {
    "version": "selection_strategy_ablation_v1",
    "paths": {
        "business_90d_csv": "/Users/bytedance/Downloads/训练1 （90天）-2026-07-09 15-02-35.csv",
        "policy_new_car_xlsx": "/Users/bytedance/Downloads/政策和新车最新表_2026-07-09_AI补充版.xlsx",
        "ranking_signals_csv": "data/external/dongchedi_rankings/current/normalized_ranking_signals.csv",
    },
    "thresholds": {
        "min_selection_rate": 0.15,
        "min_selected_count": 30,
        "min_profit_retention_rate": 0.30,
        "min_avoid_rate": 0.05,
        "min_avoid_count": 20,
    },
    "selection": {
        "group_grain": ["city", "brand", "series", "price_band", "energy_type", "vehicle_category"],
        "target_selection_rate": 0.21,
        "target_avoid_rate": 0.20,
        "min_group_sold_count": 3,
        "topk_rates": [0.10, 0.20, 0.30],
        "daily_capacity_k": 100,
    },
    "strategy_weights": {
        "market_only": {"market": 1.0},
        "dsi_only": {"dsi": 1.0},
        "ranking_only": {"ranking": 1.0},
        "market_daily_only": {"market": 0.82, "event": 0.18},
        "market_daily_dsi": {"market": 0.64, "event": 0.12, "dsi": 0.24},
        "market_daily_ranking": {"market": 0.64, "event": 0.12, "ranking": 0.24},
        "full_signal": {"market": 0.50, "event": 0.10, "dsi": 0.20, "ranking": 0.20},
        "outcome_guarded_full": {
            "market": 0.22,
            "event": 0.044,
            "dsi": 0.088,
            "ranking": 0.088,
            "acquisition_guard": 0.44,
            "sales_guard": 0.12,
        },
    },
    "avoid_strategy_weights": {
        "outcome_guarded_full": {
            "market": 0.40,
            "event": 0.08,
            "dsi": 0.16,
            "ranking": 0.16,
            "acquisition_guard": 0.15,
            "sales_guard": 0.05,
        },
    },
    "metric_smoothing": {"strength": 20},
}


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if path.is_file():
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            config = _deep_merge(config, loaded)
        except Exception:
            # Keep defaults if PyYAML is unavailable. The YAML file is for ops
            # tuning; defaults keep the script runnable in minimal environments.
            pass
    return config


def run_selection_strategy_ablation(
    *,
    config_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    include_optional: bool = True,
    write_files: bool = True,
) -> dict[str, Any]:
    config = load_config(config_path)
    dataset = load_business_dataset(
        config.get("paths", {}).get("business_90d_csv"),
        group_grain=config.get("selection", {}).get("group_grain"),
    )
    baseline = baseline_metrics(dataset)
    config["baseline_metrics"] = baseline
    signal_frame = build_signal_frame(dataset, config)
    strategies = P0_STRATEGIES + OUTCOME_INFORMED_STRATEGIES + (OPTIONAL_STRATEGIES if include_optional else [])
    baseline_candidate_count = int(baseline.get("baseline_candidate_count") or 0)

    results: list[dict[str, Any]] = [
        {
            "strategy_name": "baseline_all",
            "used_signals": [],
            "metrics": baseline,
            "lifts": {},
            "recommend_pass": {},
            "scale_pass": {},
            "strategy_score": None,
            "topk_evaluation": {},
        }
    ]
    selected_keys_by_strategy: dict[str, set[str]] = {}
    scored_by_strategy: dict[str, pd.DataFrame] = {}

    for strategy_name in strategies:
        scored = score_strategy_groups(signal_frame, strategy_name, config)
        score_col = f"{strategy_name}_recommend_score"
        avoid_col = f"{strategy_name}_avoid_score"
        eligible = _eligible_groups(scored, config)
        candidate_target = max(1, int(baseline_candidate_count * float(config["selection"]["target_selection_rate"])))
        avoid_target = max(1, int(baseline_candidate_count * float(config["selection"]["target_avoid_rate"])))
        recommend_keys = topk_group_keys(eligible, score_col, candidate_target)
        selected_group_rows = eligible[eligible["group_key"].astype(str).isin(set(recommend_keys))]
        strict_avoid = _strict_avoid_groups(eligible, baseline)
        strict_bad_keys = set(strict_avoid["group_key"].astype(str)) if not strict_avoid.empty else set()
        avoid_scored = eligible[~eligible["group_key"].astype(str).isin(set(recommend_keys))].copy()
        avoid_scored[score_col] = avoid_scored[avoid_col]
        avoid_keys = topk_group_keys(avoid_scored, score_col, avoid_target)
        metrics = subset_metrics(dataset, recommend_keys, baseline)
        avoid_metrics = subset_metrics(dataset, avoid_keys, baseline, selected_prefix="avoid")
        avoid_metrics = _augment_avoid_metrics(dataset, avoid_keys, baseline, avoid_metrics, strict_bad_keys)
        strict_bad_pool_metrics = subset_metrics(dataset, strict_bad_keys, baseline, selected_prefix="strict_bad_pool")
        lifts = relative_lifts(metrics, baseline)
        recommend_pass = leader_metric_pass(metrics, baseline, mode="recommend")
        avoid_pass = leader_metric_pass(avoid_metrics, baseline, mode="avoid")
        strategy_result = {
            **strategy_signal_summary(strategy_name),
            "metrics": metrics,
            "avoid_metrics": avoid_metrics,
            "strict_bad_pool_metrics": strict_bad_pool_metrics,
            "lifts": lifts,
            "normalized_score_components": normalized_strategy_components(metrics, baseline),
            "recommend_pass": recommend_pass,
            "scale_pass": scale_pass(metrics, config),
            "avoid_pass": avoid_pass,
            "avoid_scale_pass": avoid_scale_pass(avoid_metrics, config),
            "strategy_score": strategy_score(metrics, baseline, config),
            "topk_evaluation": _topk_evaluation(dataset, eligible, score_col, baseline, config),
            "selected_group_count": len(set(recommend_keys)),
            "selected_low_sample_group_count_lt5_sold": int(
                (pd.to_numeric(selected_group_rows["sold_count"], errors="coerce").fillna(0) < 5).sum()
            ),
            "selected_low_sample_group_count_lt10_sold": int(
                (pd.to_numeric(selected_group_rows["sold_count"], errors="coerce").fillna(0) < 10).sum()
            ),
            "selected_zero_sold_group_count": int(
                (pd.to_numeric(selected_group_rows["sold_count"], errors="coerce").fillna(0) <= 0).sum()
            ),
            "selected_low_parent_series_sample_count_lt10_sold": int(
                (pd.to_numeric(selected_group_rows.get("series_sold_count"), errors="coerce").fillna(0) < 10).sum()
            ) if "series_sold_count" in selected_group_rows else None,
            "avoid_group_count": len(set(avoid_keys)),
            "avoid_selection_mode": "strategy_avoid_score",
            "recommend_avoid_overlap_group_count": len(set(recommend_keys) & set(avoid_keys)),
            "conflict_resolution": "recommend_first_then_avoid_from_complement",
        }
        results.append(strategy_result)
        selected_keys_by_strategy[strategy_name] = set(recommend_keys)
        scored_by_strategy[strategy_name] = scored

    by_name = {item.get("strategy_name"): item for item in results}
    report = {
        "version": config.get("version"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": {
            "business_90d_csv": dataset.source_path,
            "policy_new_car_xlsx": config.get("paths", {}).get("policy_new_car_xlsx"),
            "ranking_signals_csv": str((ROOT / config.get("paths", {}).get("ranking_signals_csv", "")).resolve()),
        },
        "signal_boundaries": SIGNAL_BOUNDARIES,
        "thresholds": config.get("thresholds"),
        "selection_config": config.get("selection"),
        "strategy_weights": config.get("strategy_weights"),
        "avoid_strategy_weights": config.get("avoid_strategy_weights"),
        "dataset_metadata": dataset.metadata,
        "baseline_all": baseline,
        "strategy_results": results,
        "dsi_increment": dsi_increment(by_name.get("market_daily_only"), by_name.get("market_daily_dsi")),
        "ranking_increment": ranking_increment(by_name.get("market_daily_only"), by_name.get("market_daily_ranking")),
        "optional_best_strategy": choose_final_strategy(results),
        "final_recommendation": choose_final_strategy(
            [item for item in results if item.get("strategy_name") in {"baseline_all", *P0_STRATEGIES, *OUTCOME_INFORMED_STRATEGIES}]
        ),
        "error_analysis": _error_analysis(dataset, signal_frame, selected_keys_by_strategy, baseline),
        "notes": [
            "本轮不做 point-in-time 回测，按当前已提供的90天经营数据、行情状态、政策/新车事件、DSI、排行榜进行策略对照。",
            "无原始人工排序基线，Top-K 同容量评估按全量 baseline 均值作为参照。",
            "政策/新车事件替代日报信号，只作为弱调节和解释信号，不直接覆盖行情/经营主信号。",
            "outcome_guarded_full 明确标记为 outcome-informed：44% 行情/事件/DSI/排行榜，44% 为45天成熟收车队列售出率守门，12% 为45天成熟上架队列售出率守门。两个守门率均先做全国车系父级->本地组的EB20平滑。",
            "规避排序与推荐排序使用独立权重：80%外部风险、15%收车后售出率风险、5%上架后售出率风险；不能用推荐分简单倒序替代。",
            "推荐组成交周期方向为 <= 0.9 * baseline；避免组成交周期方向为 >= 1.1 * baseline。",
            "当前因缺少未收购候选线索，无法计算真实收车转化率；收车侧代理指标为45天成熟收车队列售出率，售车转化率为45天成熟上架队列售出率。",
            "Top-K 默认采用 group-level approximate，并输出 requested_topk 与 actual_selected_candidate_count；如单组超过 K，会提示。",
        ],
    }
    if write_files:
        report["artifacts"] = write_ablation_report(report, output_dir)
    return report


def _eligible_groups(scored: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    # Signal ablation must rank the whole candidate universe. Sample support is
    # evaluated separately by confidence/label gates; pre-filtering here can
    # make every strategy select the exact same residual pool.
    min_sold = int(config.get("selection", {}).get("ablation_min_group_sold_count", 0))
    candidate_count = pd.to_numeric(scored["candidate_count"], errors="coerce").fillna(0)
    sold_count = pd.to_numeric(scored["sold_count"], errors="coerce").fillna(0)
    eligible = scored[(candidate_count > 0) & (sold_count >= min_sold)].copy()
    return eligible if not eligible.empty else scored.copy()


def _strict_avoid_groups(scored: pd.DataFrame, baseline: dict[str, Any]) -> pd.DataFrame:
    frame = scored.copy()
    mask = (
        pd.to_numeric(frame["avg_profit"], errors="coerce").le(float(baseline.get("baseline_avg_profit") or 0) * 0.9)
        & pd.to_numeric(frame["avg_days_to_sell"], errors="coerce").ge(float(baseline.get("baseline_avg_days_to_sell") or 0) * 1.1)
        & pd.to_numeric(frame["acquisition_conversion_rate"], errors="coerce").le(
            float(baseline.get("baseline_acquisition_conversion_rate") or 0) * 0.9
        )
        & pd.to_numeric(frame["sales_conversion_rate"], errors="coerce").le(
            float(baseline.get("baseline_sales_conversion_rate") or 0) * 0.9
        )
    )
    return frame[mask].copy()


def _topk_evaluation(
    dataset: SelectionBusinessDataset,
    scored: pd.DataFrame,
    score_col: str,
    baseline: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    baseline_count = int(baseline.get("baseline_candidate_count") or 0)
    out: dict[str, Any] = {}
    for rate in config.get("selection", {}).get("topk_rates", [0.10, 0.20, 0.30]):
        target_count = max(1, int(baseline_count * float(rate)))
        keys = topk_group_keys(scored, score_col, target_count)
        metrics = subset_metrics(dataset, keys, baseline)
        out[f"top{int(float(rate) * 100)}"] = clean_metrics(
            {
                **metrics,
                **relative_lifts(metrics, baseline),
                "requested_topk_candidate_count": target_count,
                "actual_selected_group_count": len(set(keys)),
                "actual_selected_candidate_count": int(metrics.get("candidate_count") or 0),
                "topk_grain_note": "group-level approximate; a whole group is included when it crosses K",
            }
        )
    daily_k = int(config.get("selection", {}).get("daily_capacity_k") or 0)
    if daily_k > 0:
        keys = topk_group_keys(scored, score_col, daily_k)
        metrics = subset_metrics(dataset, keys, baseline)
        out[f"topK_{daily_k}"] = clean_metrics(
            {
                **metrics,
                **relative_lifts(metrics, baseline),
                "requested_topk_candidate_count": daily_k,
                "actual_selected_group_count": len(set(keys)),
                "actual_selected_candidate_count": int(metrics.get("candidate_count") or 0),
                "topk_grain_note": "group-level approximate; a whole group is included when it crosses K",
            }
        )
    return out


def _augment_avoid_metrics(
    dataset: SelectionBusinessDataset,
    group_keys: list[str],
    baseline: dict[str, Any],
    avoid_metrics: dict[str, Any],
    strict_bad_keys: set[str] | None = None,
) -> dict[str, Any]:
    selected_keys = set(group_keys)
    strict_bad_keys = set(strict_bad_keys or set())
    frame = dataset.frame[dataset.frame["group_key"].isin(selected_keys)]
    sold_profit = pd.to_numeric(frame.get("gross_profit"), errors="coerce").dropna()
    negative_profit = float((-sold_profit[sold_profit < 0]).sum()) if not sold_profit.empty else 0.0
    baseline_avg = baseline.get("baseline_avg_profit") or 0
    avoid_avg = avoid_metrics.get("avg_profit") or 0
    gap = max(0.0, float(baseline_avg) - float(avoid_avg)) * int(avoid_metrics.get("sold_count") or 0)
    captured_bad_keys = selected_keys & strict_bad_keys
    out = dict(avoid_metrics)
    out.update(
        clean_metrics(
            {
                "avoided_negative_profit": negative_profit,
                "avoid_profit_gap": gap,
                "strict_bad_group_count": len(strict_bad_keys),
                "captured_strict_bad_group_count": len(captured_bad_keys),
                "avoid_capture_rate": len(captured_bad_keys) / len(strict_bad_keys) if strict_bad_keys else None,
            }
        )
    )
    return out


def _error_analysis(
    dataset: SelectionBusinessDataset,
    signal_frame: pd.DataFrame,
    selected: dict[str, set[str]],
    baseline: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    base = selected.get("market_daily_only", set())
    dsi = selected.get("market_daily_dsi", set())
    ranking = selected.get("market_daily_ranking", set())
    full = selected.get("full_signal", set())
    return {
        "market_daily_only_missed_high_profit": _group_samples(dataset, full - base, baseline, good=True),
        "dsi_added_good": _group_samples(dataset, dsi - base, baseline, good=True),
        "ranking_added_bad": _group_samples(dataset, ranking - base, baseline, good=False),
        "full_signal_false_positive": _group_samples(dataset, full, baseline, good=False),
    }


def _group_samples(
    dataset: SelectionBusinessDataset,
    keys: set[str],
    baseline: dict[str, Any],
    *,
    good: bool,
    limit: int = 12,
) -> list[dict[str, Any]]:
    if not keys:
        return []
    frame = dataset.group_frame[dataset.group_frame["group_key"].isin(keys)].copy()
    baseline_profit = baseline.get("baseline_avg_profit") or 0
    baseline_days = baseline.get("baseline_avg_days_to_sell") or 999
    frame["avg_profit_fill"] = pd.to_numeric(frame["avg_profit"], errors="coerce").fillna(-10**9)
    frame["avg_days_fill"] = pd.to_numeric(frame["avg_days_to_sell"], errors="coerce").fillna(10**9)
    if good:
        filtered = frame[(frame["avg_profit_fill"] >= baseline_profit * 1.1) & (frame["avg_days_fill"] <= baseline_days * 0.9)]
        filtered = filtered.sort_values(["avg_profit_fill", "sold_count"], ascending=[False, False])
    else:
        filtered = frame[(frame["avg_profit_fill"] <= baseline_profit * 0.9) | (frame["avg_days_fill"] >= baseline_days * 1.1)]
        filtered = filtered.sort_values(["avg_profit_fill", "avg_days_fill"], ascending=[True, False])
    if filtered.empty:
        filtered = frame.sort_values(["avg_profit_fill"], ascending=not good)
    columns = [
        "city",
        "brand",
        "series",
        "candidate_count",
        "sold_count",
        "total_profit",
        "avg_profit",
        "avg_days_to_sell",
        "acquisition_conversion_rate",
        "sales_conversion_rate",
    ]
    rows = []
    for row in filtered.head(limit)[columns].to_dict(orient="records"):
        rows.append(clean_metrics(row))
    return rows


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


if __name__ == "__main__":
    result = run_selection_strategy_ablation(write_files=True)
    print(json.dumps(result.get("artifacts", {}), ensure_ascii=False, indent=2))
