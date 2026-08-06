from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("selection_strategy_config.yaml")
GENERATED_CONFIG_PATH = ROOT / "runtime" / "selection_selected_parameter_config.json"


DEFAULT_SELECTION_SCORE_CONFIG: dict[str, Any] = {
    "selection_score_version": "selection_score_time_aware_unique_unit_v3",
    "sample_confidence": {
        "levels": [
            {"name": "very_low", "max_sold_count": 2, "confidence_cap": 0.25, "note": "有效经营证据很少，只能作为观察依据"},
            {"name": "low", "min_sold_count": 3, "max_sold_count": 4, "confidence_cap": 0.40, "note": "有效经营证据偏少，结论需保守"},
            {"name": "limited", "min_sold_count": 5, "max_sold_count": 9, "confidence_cap": 0.55, "note": "有效经营证据有限，不宜仅凭单项指标主动补库"},
            {"name": "medium", "min_sold_count": 10, "max_sold_count": 19, "confidence_cap": 0.75, "note": "经营证据覆盖中等，可结合利润和周转判断"},
            {"name": "high", "min_sold_count": 20, "max_sold_count": 29, "confidence_cap": 0.90, "note": "经营证据覆盖较高，结论稳定性较好"},
            {
                "name": "strong",
                "min_sold_count": 30,
                "min_acquired_count": 50,
                "confidence_cap": 1.00,
                "note": "经营证据覆盖充分，结论稳定性高",
            },
        ],
        "coverage_floor": 0.45,
        "acquired_support_reference": 50,
        "candidate_support_reference": 80,
    },
    "metric_smoothing": {
        "strength": 20,
        "fields": [
            "avg_gross_profit",
            "avg_turnover_days",
            "turnover_efficiency_index",
            "sale_conversion_rate",
            "acquisition_conversion_rate",
            "sold_from_acquired_rate",
            "loss_rate",
            "median_gross_profit",
        ],
    },
    "score_weights_online": {
        "demand": 0.00,
        "supply": 0.00,
        "turnover": 0.00,
        "price_stability": 0.00,
        "market_state": 0.20,
        "dsi": 0.05,
        "value": 0.55,
        "total_profit": 0.20,
    },
    "selection_policy": {
        "strategy_id": "three_layer_non_overlapping_v1_cv5",
        "strategy_mode": "three_layer",
        # Leadership's Market-state + DSI qualification pool is the product
        # selection baseline.  The smaller 21% pool is only an in-pool
        # follow-up priority and must never replace the 40.16% qualification.
        "target_selection_rate": 0.40163988626595254,
        "active_followup_target_rate": 0.21,
        "target_avoid_rate": 0.20,
        "ranking_components": {
            "acquisition": 0.10,
            "sales": 0.30,
            "turnover": 0.10,
            "profit": 0.30,
            "ranking": 0.20,
        },
        "external_full_signal_weight": 0.70,
        "acquisition_conversion_guard_weight": 0.00,
        "listed_sell_through_guard_weight": 0.30,
        "conversion_guard_smoothing_strength": 20,
        "external_components": {
            "market_state": 0.60,
            "policy_event": 0.00,
            "dsi": 0.10,
            "ranking": 0.00,
        },
        "avoid_policy": {
            "external_risk_weight": 0.80,
            "acquisition_conversion_risk_weight": 0.15,
            "listed_sell_through_risk_weight": 0.05,
        },
        "portfolio_qualification": {
            "enabled": True,
            "role": "active_followup_validation_only",
            "does_not_change_leadership_qualification_pool": True,
            "grain": "brand_series",
            "observation_min_sold_count": 1,
            "min_sold_count": 3,
            "max_loss_rate": 0.40,
            "min_profit_per_candidate": 0,
            "allowed_market_categories": ["流动行情", "结构性行情", "上涨行情", "常规行情"],
            "allowed_dsi_labels": ["供不应求", "供需平衡"],
            "require_positive_total_profit": True,
            "avoid_negative_total_profit": True,
            "city_signals_are_ordering_only": True,
        },
        "leadership_qualification_baseline": {
            "snapshot_date": "2026-07-14",
            "rule_id": "market_state_dsi_40pct_v1",
            "rule_description": "行情状态四类且DSI为供不应求或供需平衡",
            "allowed_market_categories": ["流动行情", "结构性行情", "上涨行情", "常规行情"],
            "allowed_dsi_labels": ["供不应求", "供需平衡"],
            "baseline_unique_vehicle_count": 30246,
            "qualified_unique_vehicle_count": 12148,
            "qualification_rate": 0.40163988626595254,
            "operating_metrics_are_validation_only": True,
            "active_followup_is_ordering_only": True,
        },
        "backtest_report": "results/evals/selection_three_layer_policy_champion_20260715.json",
        "stress_report": "results/evals/selection_profit_frontier_leave_one_brand_out_20260713.csv",
    },
    "label_gate": {
        "strong_recommend": {
            "min_final_score": 72,
            "min_business_score": 78,
            "min_sold_count": 10,
            "min_acquired_count": 10,
            "min_confidence_score": 0.60,
            "min_total_profit_contribution": 0.05,
            "min_sale_conversion_rate": 0.34,
            "min_acquisition_conversion_rate": 0.24,
            "min_sold_from_acquired_rate": 0.35,
            "min_listed_conversion_denominator": 20,
            "min_acquired_conversion_denominator": 20,
            "max_loss_rate": 0.15,
            "min_median_gross_profit": 2500,
            "require_leader_metrics": True,
            "min_risk_score": 55,
        },
        "recommend": {
            "min_final_score": 50,
            "min_business_score": 50,
            "min_sold_count": 3,
            "min_acquired_count": 0,
            "min_confidence_score": 0.35,
            "min_total_profit_contribution": 0,
            "min_sale_conversion_rate": 0,
            "min_acquisition_conversion_rate": 0,
            "min_sold_from_acquired_rate": 0,
            "min_listed_conversion_denominator": 0,
            "min_acquired_conversion_denominator": 0,
            "max_loss_rate": 0.40,
            "min_median_gross_profit": 0,
            "require_leader_metrics": False,
            "min_risk_score": 0,
        },
        "watch": {"min_final_score": 38},
        "insufficient": {"max_sold_count": 9, "max_label": "WATCH"},
        "avoid": {
            "min_sold_count": 10,
            "require_leader_metrics": True,
        },
    },
    "parameter_search": {
        "max_parameter_sets": 180,
        "group_grain": ["brand", "series"],
        "min_selection_rate": 0.08,
        "max_selection_rate": 0.45,
        "min_profit_retention_rate": 0.12,
        "target_selection_rate": [0.10, 0.15, 0.20, 0.25, 0.30],
        "min_recommend_sold_count": [5, 10, 15, 20],
        "min_strong_recommend_sold_count": [15, 20, 25, 30],
        "min_recommend_acquired_count": [10, 20, 30],
        "min_strong_recommend_acquired_count": [20, 30, 50],
        "smoothing_strength": [10, 20, 30, 50],
        "min_profit_contribution_for_recommend": [0.005, 0.01, 0.02, 0.03],
        "min_profit_contribution_for_strong": [0.02, 0.03, 0.05, 0.08],
        "confidence_weight_mode": ["linear", "sqrt", "log"],
        "total_profit_weight": [0.10, 0.15, 0.20, 0.25],
        "average_profit_weight": [0.15, 0.20, 0.25],
        "turnover_weight": [0.10, 0.15, 0.20],
        "acquisition_conversion_weight": [0.15, 0.20, 0.25],
        "sales_conversion_weight": [0.15, 0.20, 0.25],
    },
}


def get_selection_score_config(config_path: str | Path | None = None, *, include_generated: bool = True) -> dict[str, Any]:
    config = deepcopy(DEFAULT_SELECTION_SCORE_CONFIG)
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if path.is_file():
        config = _deep_merge(config, _read_yaml_or_json(path))
    if include_generated and GENERATED_CONFIG_PATH.is_file():
        generated = _read_yaml_or_json(GENERATED_CONFIG_PATH)
        if generated.get("metric_grain") not in {"unique_product_id"} or generated.get("history_metric_version") != "time_aware_v5":
            generated = {}
        selected_config = generated.get("selected_parameter_config") if isinstance(generated, dict) else None
        if isinstance(selected_config, dict):
            config = _deep_merge(config, _online_config_from_selected_params(selected_config))
            config["selected_parameter_config"] = selected_config
            config["parameter_set_id"] = generated.get("parameter_set_id") or selected_config.get("parameter_set_id")
            config["parameter_set_score"] = generated.get("parameter_set_score")
    return config


def _online_config_from_selected_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_smoothing": {"strength": params.get("smoothing_strength")},
        "label_gate": {
            "recommend": {
                "min_sold_count": params.get("min_recommend_sold_count"),
                "min_acquired_count": params.get("min_recommend_acquired_count"),
                "min_total_profit_contribution": params.get("min_profit_contribution_for_recommend"),
                "min_sale_conversion_rate": params.get("min_sale_conversion_rate"),
                "min_sold_from_acquired_rate": params.get("min_sold_from_acquired_rate"),
            },
            "strong_recommend": {
                "min_sold_count": params.get("min_strong_recommend_sold_count"),
                "min_acquired_count": params.get("min_strong_recommend_acquired_count"),
                "min_total_profit_contribution": params.get("min_profit_contribution_for_strong"),
            },
            "confidence_weight_mode": params.get("confidence_weight_mode"),
        },
        "score_weights_online": {
            "total_profit": params.get("total_profit_weight"),
            "value": params.get("average_profit_weight"),
            "turnover": params.get("turnover_weight"),
        },
    }


def _read_yaml_or_json(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
        else:
            import yaml  # type: ignore

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in (update or {}).items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
