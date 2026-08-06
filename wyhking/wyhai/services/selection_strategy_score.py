from __future__ import annotations

from typing import Any

from .selection_strategy_metrics import clean_metrics, relative_lifts, safe_divide


DEFAULT_SCORE_WEIGHTS = {
    "normalized_profit_lift": 0.25,
    "normalized_total_profit_retention": 0.20,
    "normalized_acquisition_conversion_lift": 0.20,
    "normalized_sales_conversion_lift": 0.20,
    "normalized_turnover_lift": 0.15,
}


def normalized_strategy_components(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    lifts = relative_lifts(metrics, baseline)
    components = {
        "normalized_profit_lift": _target_norm(lifts.get("avg_profit_lift"), 1.10),
        "normalized_total_profit_retention": _target_norm(lifts.get("total_profit_retention"), 0.30),
        "normalized_acquisition_conversion_lift": _target_norm(lifts.get("acquisition_conversion_lift"), 1.10),
        "normalized_sales_conversion_lift": _target_norm(lifts.get("sales_conversion_lift"), 1.10),
        "normalized_turnover_lift": _target_norm(lifts.get("days_to_sell_improvement"), 1 / 0.90),
    }
    return clean_metrics({**lifts, **components})


def strategy_score(metrics: dict[str, Any], baseline: dict[str, Any], config: dict[str, Any] | None = None) -> float:
    weights = (config or {}).get("score_weights") or DEFAULT_SCORE_WEIGHTS
    components = normalized_strategy_components(metrics, baseline)
    score = 0.0
    total_weight = 0.0
    for key, default_weight in DEFAULT_SCORE_WEIGHTS.items():
        weight = float(weights.get(key, default_weight))
        score += float(components.get(key) or 0) * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return round(score / total_weight * 100, 3)


def choose_final_strategy(strategy_results: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in strategy_results if item.get("strategy_name") != "baseline_all"]
    if not candidates:
        return {"strategy_name": "baseline_all", "reason": "no strategy results"}
    hard_scale = [
        item
        for item in candidates
        if item.get("recommend_pass", {}).get("all_pass")
        and item.get("scale_pass", {}).get("all_pass")
    ]
    pool = hard_scale or [item for item in candidates if item.get("scale_pass", {}).get("all_pass")] or candidates
    pool = sorted(
        pool,
        key=lambda item: (
            float(item.get("strategy_score") or 0),
            float(item.get("metrics", {}).get("profit_retention_rate") or 0),
            float(item.get("metrics", {}).get("selection_rate") or 0),
        ),
        reverse=True,
    )
    best = pool[0]
    warnings: list[str] = []
    if not best.get("scale_pass", {}).get("all_pass"):
        warnings.append("最佳均值策略未通过规模约束，不能直接作为 P0 唯一策略。")
    if not best.get("recommend_pass", {}).get("all_pass"):
        warnings.append("最佳综合策略未完全通过四项经营指标，需用 Top-K 与错误分析约束上线范围。")
    if (best.get("metrics", {}).get("profit_retention_rate") or 0) < 0.30:
        warnings.append("利润保留率低于 30%，存在只选少数安全车导致总利润下滑的风险。")
    return {
        "strategy_name": best.get("strategy_name"),
        "strategy_score": best.get("strategy_score"),
        "used_signals": best.get("used_signals"),
        "reason": _recommendation_reason(best),
        "warnings": warnings,
    }


def dsi_increment(market_daily_only: dict[str, Any] | None, market_daily_dsi: dict[str, Any] | None) -> dict[str, Any]:
    return _increment("DSI", market_daily_only, market_daily_dsi)


def ranking_increment(market_daily_only: dict[str, Any] | None, market_daily_ranking: dict[str, Any] | None) -> dict[str, Any]:
    return _increment("ranking", market_daily_only, market_daily_ranking)


def _increment(label: str, base: dict[str, Any] | None, challenger: dict[str, Any] | None) -> dict[str, Any]:
    if not base or not challenger:
        return {"signal": label, "available": False}
    base_metrics = base.get("metrics", {})
    challenger_metrics = challenger.get("metrics", {})
    return clean_metrics(
        {
            "signal": label,
            "available": True,
            "strategy_score_delta": (challenger.get("strategy_score") or 0) - (base.get("strategy_score") or 0),
            "avg_profit_delta": (challenger_metrics.get("avg_profit") or 0) - (base_metrics.get("avg_profit") or 0),
            "profit_retention_delta": (challenger_metrics.get("profit_retention_rate") or 0)
            - (base_metrics.get("profit_retention_rate") or 0),
            "selection_rate_delta": (challenger_metrics.get("selection_rate") or 0) - (base_metrics.get("selection_rate") or 0),
            "turnover_days_delta": (challenger_metrics.get("avg_days_to_sell") or 0)
            - (base_metrics.get("avg_days_to_sell") or 0),
            "is_positive": (challenger.get("strategy_score") or 0) > (base.get("strategy_score") or 0),
        }
    )


def _target_norm(value: Any, target: float) -> float:
    ratio = safe_divide(value, target)
    if ratio is None:
        return 0.0
    return max(0.0, min(1.5, ratio)) / 1.5


def _recommendation_reason(best: dict[str, Any]) -> str:
    metrics = best.get("metrics", {})
    return (
        f"{best.get('strategy_name')} 综合分 {best.get('strategy_score')}，"
        f"选中率 {metrics.get('selection_rate')}, "
        f"利润保留率 {metrics.get('profit_retention_rate')}, "
        f"平均利润 {metrics.get('avg_profit')}, "
        f"成交周期 {metrics.get('avg_days_to_sell')}。"
    )
