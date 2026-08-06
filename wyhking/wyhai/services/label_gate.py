from __future__ import annotations

from typing import Any

from .selection_score_config import get_selection_score_config


RECOMMEND_KEYS = ("avg_turnover_days", "avg_gross_profit", "sale_conversion_rate", "acquisition_conversion_rate")


def leader_metrics_pass_from_ratios(ratios: dict[str, Any] | None, *, mode: str = "recommend") -> dict[str, bool]:
    ratios = ratios or {}
    if mode == "recommend":
        checks = {
            "avg_turnover_days": _le(ratios.get("avg_turnover_days"), 0.9),
            "avg_gross_profit": _ge(ratios.get("avg_gross_profit"), 1.1),
            "sale_conversion_rate": _ge(ratios.get("sale_conversion_rate"), 1.1),
            "acquisition_conversion_rate": _ge(ratios.get("acquisition_conversion_rate"), 1.1),
        }
    elif mode == "avoid":
        checks = {
            "avg_turnover_days": _ge(ratios.get("avg_turnover_days"), 1.1),
            "avg_gross_profit": _le(ratios.get("avg_gross_profit"), 0.9),
            "sale_conversion_rate": _le(ratios.get("sale_conversion_rate"), 0.9),
            "acquisition_conversion_rate": _le(ratios.get("acquisition_conversion_rate"), 0.9),
        }
    else:
        raise ValueError(f"unknown leader metric mode: {mode}")
    checks["all_pass"] = all(checks.values())
    return checks


def apply_label_gate(
    *,
    final_opportunity_score: Any,
    business_score: Any,
    confidence_score: Any,
    sold_count: Any,
    acquired_count: Any,
    total_profit_contribution: Any,
    risk_score: Any,
    market_category: Any,
    dsi_label: Any = None,
    ratios: dict[str, Any] | None,
    sale_conversion_rate: Any = None,
    acquisition_conversion_rate: Any = None,
    sold_from_acquired_rate: Any = None,
    listed_conversion_denominator: Any = None,
    acquired_conversion_denominator: Any = None,
    loss_rate: Any = None,
    median_gross_profit: Any = None,
    sample_level: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or get_selection_score_config()
    gates = cfg.get("label_gate") or {}
    recommend_pass = leader_metrics_pass_from_ratios(ratios, mode="recommend")
    avoid_pass = leader_metrics_pass_from_ratios(ratios, mode="avoid")
    sold = _num(sold_count)
    acquired = _num(acquired_count)
    final_score = _num(final_opportunity_score)
    bscore = _num(business_score)
    conf = _num(confidence_score)
    contribution = _num(total_profit_contribution)
    risk = _num(risk_score)
    reasons: list[str] = []

    avoid_cfg = gates.get("avoid") or {}
    if avoid_pass["all_pass"] and sold >= float(avoid_cfg.get("min_sold_count", 10)):
        return _result("AVOID", "暂缓收", recommend_pass, avoid_pass, reasons + ["命中风险/规避门控"])
    if str(market_category or "") == "急跌行情":
        return _result("CAUTION", "谨慎收", recommend_pass, avoid_pass, reasons + ["行情分类为急跌行情，未命中内部严格规避门控"])
    if str(market_category or "") == "阴跌行情":
        return _result("CAUTION", "谨慎收", recommend_pass, avoid_pass, reasons + ["行情分类为阴跌行情"])

    portfolio_policy = (cfg.get("selection_policy") or {}).get("portfolio_qualification") or {}
    allowed_market = {str(value) for value in portfolio_policy.get("allowed_market_categories") or []}
    allowed_dsi = {str(value) for value in portfolio_policy.get("allowed_dsi_labels") or []}
    market_value = str(market_category or "").strip()
    dsi_value = str(dsi_label or "").strip()
    external_gate_reasons: list[str] = []
    if allowed_market and market_value and market_value not in allowed_market:
        external_gate_reasons.append(f"行情状态{market_value}不在主动推荐范围")
    if allowed_dsi and dsi_value and dsi_value not in allowed_dsi:
        external_gate_reasons.append(f"供需状态{dsi_value}不在主动推荐范围")
    if external_gate_reasons:
        return _result("WATCH", "正常跟踪", recommend_pass, avoid_pass, reasons + external_gate_reasons)

    # Evidence sufficiency is a qualification gate, not a ranking feature.
    # It must run before the strong/recommend score gates; otherwise a tiny
    # sample with attractive ratios can be promoted simply because its score
    # is high.  Those rows remain queryable in the full ranking, but cannot be
    # presented as an active acquisition recommendation.
    insufficient_cfg = gates.get("insufficient") or {}
    if sold <= float(insufficient_cfg.get("max_sold_count", 9)):
        reasons.append(f"有效经营证据不足，证据等级{sample_level or '-'}，不进入主动推荐")
        return _result("WATCH", "证据不足", recommend_pass, avoid_pass, reasons)

    strong_reasons = list(reasons)
    if _gate_pass(
        gates.get("strong_recommend") or {},
        final_score=final_score,
        business_score=bscore,
        confidence_score=conf,
        sold=sold,
        acquired=acquired,
        contribution=contribution,
        risk=risk,
        sale_conversion_rate=_num(sale_conversion_rate),
        acquisition_conversion_rate=_num(acquisition_conversion_rate),
        sold_from_acquired_rate=_num(sold_from_acquired_rate),
        listed_conversion_denominator=_num(listed_conversion_denominator),
        acquired_conversion_denominator=_num(acquired_conversion_denominator),
        loss_rate=_num(loss_rate),
        median_gross_profit=_num(median_gross_profit),
        leader_pass=recommend_pass,
        reasons=strong_reasons,
    ):
        return _result("STRONG_RECOMMEND", "重点关注", recommend_pass, avoid_pass, strong_reasons or ["通过重点关注门控"])
    recommend_reasons = list(reasons)
    if _gate_pass(
        gates.get("recommend") or {},
        final_score=final_score,
        business_score=bscore,
        confidence_score=conf,
        sold=sold,
        acquired=acquired,
        contribution=contribution,
        risk=risk,
        sale_conversion_rate=_num(sale_conversion_rate),
        acquisition_conversion_rate=_num(acquisition_conversion_rate),
        sold_from_acquired_rate=_num(sold_from_acquired_rate),
        listed_conversion_denominator=_num(listed_conversion_denominator),
        acquired_conversion_denominator=_num(acquired_conversion_denominator),
        loss_rate=_num(loss_rate),
        median_gross_profit=_num(median_gross_profit),
        leader_pass=recommend_pass,
        reasons=recommend_reasons,
    ):
        return _result("RECOMMEND", "可关注", recommend_pass, avoid_pass, recommend_reasons or ["通过推荐门控"])

    reasons = recommend_reasons or strong_reasons or reasons
    if final_score < float((gates.get("recommend") or {}).get("min_final_score", 58)):
        reasons.append("最终机会分未达到推荐门槛")
    else:
        reasons.append("四项经营指标、贡献度或风险门控未全部达标")
    if final_score < 38 or risk <= 25:
        return _result("CAUTION", "谨慎收", recommend_pass, avoid_pass, reasons)
    return _result("WATCH", "正常跟踪", recommend_pass, avoid_pass, reasons)


def _gate_pass(
    gate: dict[str, Any],
    *,
    final_score: float,
    business_score: float,
    confidence_score: float,
    sold: float,
    acquired: float,
    contribution: float,
    risk: float,
    sale_conversion_rate: float,
    acquisition_conversion_rate: float,
    sold_from_acquired_rate: float,
    listed_conversion_denominator: float,
    acquired_conversion_denominator: float,
    loss_rate: float,
    median_gross_profit: float,
    leader_pass: dict[str, bool],
    reasons: list[str],
) -> bool:
    checks = {
        "final_score": final_score >= float(gate.get("min_final_score", 0)),
        "business_score": business_score >= float(gate.get("min_business_score", 0)),
        "sold_count": sold >= float(gate.get("min_sold_count", 0)),
        "acquired_count": acquired >= float(gate.get("min_acquired_count", 0)),
        "confidence_score": confidence_score >= float(gate.get("min_confidence_score", 0)),
        "total_profit_contribution": contribution >= float(gate.get("min_total_profit_contribution", 0)),
        "sale_conversion_rate": sale_conversion_rate >= float(gate.get("min_sale_conversion_rate", 0)),
        "acquisition_conversion_rate": acquisition_conversion_rate >= float(gate.get("min_acquisition_conversion_rate", 0)),
        "sold_from_acquired_rate": sold_from_acquired_rate >= float(gate.get("min_sold_from_acquired_rate", 0)),
        "listed_conversion_support": listed_conversion_denominator >= float(gate.get("min_listed_conversion_denominator", 0)),
        "acquired_conversion_support": acquired_conversion_denominator >= float(gate.get("min_acquired_conversion_denominator", 0)),
        "loss_rate": loss_rate <= float(gate.get("max_loss_rate", 1)),
        "median_gross_profit": median_gross_profit >= float(gate.get("min_median_gross_profit", 0)),
        "risk_score": risk >= float(gate.get("min_risk_score", gate.get("min_safety_score", 0))),
        "leader_metrics": (not gate.get("require_leader_metrics", False)) or bool(leader_pass.get("all_pass")),
    }
    if all(checks.values()):
        return True
    missing = [key for key, ok in checks.items() if not ok]
    if missing:
        reasons.append("未通过门控：" + "、".join(missing[:4]))
    return False


def _result(
    level: str,
    label: str,
    recommend_pass: dict[str, bool],
    avoid_pass: dict[str, bool],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "selection_level": level,
        "recommendation_level": level,
        "recommendation_label": label,
        "business_recommend": level in {"STRONG_RECOMMEND", "RECOMMEND"},
        "business_avoid": level == "AVOID",
        "recommend_leader_metrics_pass": recommend_pass,
        "avoid_leader_metrics_pass": avoid_pass,
        "gate_reasons": list(dict.fromkeys(reasons))[:8],
    }


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _ge(value: Any, threshold: float) -> bool:
    try:
        return float(value) >= threshold
    except Exception:
        return False


def _le(value: Any, threshold: float) -> bool:
    try:
        return float(value) <= threshold
    except Exception:
        return False
