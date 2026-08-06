"""Selection module service backed by online-safe market workbook data."""

from __future__ import annotations

from bisect import bisect_right
import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

from .business_market_workbook_loader import (
    finite_number,
    get_business_market_loader,
)


RISK_KEYWORDS = ("别碰", "不要", "风险", "亏", "慢", "库存", "下跌", "阴跌", "急跌")
PRICE_RANGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*万")


def _num(value: Any, default: float = 0) -> float:
    number = finite_number(value)
    return number if number is not None else default


def _round(value: Any, digits: int = 2) -> float | None:
    number = finite_number(value)
    return round(number, digits) if number is not None else None


def _category_bonus(category: str) -> float:
    return {
        "结构性行情": 8,
        "流动行情": 7,
        "上涨行情": 4,
        "常规行情": 0,
        "阴跌行情": -10,
        "急跌行情": -20,
        "其他行情分类": -6,
    }.get(category, -4)


SCORE_FIELDS = (
    "deal_sample_90d",
    "detail_uv",
    "favorite_count",
    "inventory_cycle",
    "sell_through_rate",
    "avg_deal_cycle",
    "price_volatility",
)


def _quantile_from_values(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _build_score_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for field in SCORE_FIELDS:
        values = sorted(
            number for number in (_num(row.get(field), math.nan) for row in rows)
            if math.isfinite(number)
        )
        stats[field] = {
            "values": values,
            "q25": _quantile_from_values(values, 0.25),
            "q75": _quantile_from_values(values, 0.75),
        }
    return stats


def _rank_from_stats(stats: dict[str, dict[str, Any]], field: str, value: Any, *, reverse: bool = False) -> float:
    current = finite_number(value)
    values = stats.get(field, {}).get("values") or []
    if current is None or not values:
        return 0.5
    pct = bisect_right(values, current) / len(values)
    return 1 - pct if reverse else pct


def _quantile_from_stats(stats: dict[str, dict[str, Any]], field: str, key: str) -> float | None:
    value = stats.get(field, {}).get(key)
    return value if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def _recommendation(score: float, category: str) -> tuple[str, str]:
    if category == "急跌行情" or score < 35:
        return "AVOID", "暂缓收"
    if category == "阴跌行情" or score < 50:
        return "CAUTION", "谨慎收"
    if score >= 78:
        return "STRONG_RECOMMEND", "重点关注"
    if score >= 64:
        return "RECOMMEND", "可关注"
    return "WATCH", "正常跟踪"


def _score(row: dict[str, Any], score_stats: dict[str, dict[str, Any]], dsi: dict[str, Any], *, cohort_label: str) -> dict[str, Any]:
    active = max(
        _rank_from_stats(score_stats, "deal_sample_90d", row.get("deal_sample_90d")),
        _rank_from_stats(score_stats, "detail_uv", row.get("detail_uv")),
        _rank_from_stats(score_stats, "favorite_count", row.get("favorite_count")),
    ) * 100
    inventory_health = (
        0.55 * _rank_from_stats(score_stats, "inventory_cycle", row.get("inventory_cycle"), reverse=True)
        + 0.45 * _rank_from_stats(score_stats, "sell_through_rate", row.get("sell_through_rate"))
    ) * 100
    turnover = _rank_from_stats(score_stats, "avg_deal_cycle", row.get("avg_deal_cycle"), reverse=True) * 100
    volatility_pct = _rank_from_stats(score_stats, "price_volatility", row.get("price_volatility"), reverse=True) * 100
    price_change = _num(row.get("price_change_30d"), 0)
    trend_bonus = 100 if -0.03 <= price_change <= 0.06 else 55 if price_change > 0.06 else 35
    price_stability = 0.7 * volatility_pct + 0.3 * trend_bonus
    daily_neutral = 60
    score = (
        active * 0.25
        + inventory_health * 0.20
        + turnover * 0.20
        + price_stability * 0.15
        + float(dsi.get("score") or 50) * 0.10
        + daily_neutral * 0.10
        + _category_bonus(str(row.get("market_category") or ""))
    )
    risks: list[str] = []
    reasons: list[str] = []
    if _num(row.get("deal_sample_90d")) >= (_quantile_from_stats(score_stats, "deal_sample_90d", "q75") or 999999):
        reasons.append(f"成交样本高于{cohort_label}多数对象")
    if _num(row.get("sell_through_rate")) >= (_quantile_from_stats(score_stats, "sell_through_rate", "q75") or 999999):
        reasons.append(f"成交转化处于{cohort_label}较高水平")
    if _num(row.get("avg_deal_cycle")) <= (_quantile_from_stats(score_stats, "avg_deal_cycle", "q25") or -1):
        reasons.append("平均成交周期较短")
    if dsi.get("label") == "供不应求":
        reasons.append("DSI显示供不应求")
    if price_change <= -0.03:
        risks.append("30天价格下行，收车价要保守")
        score -= 6
    if _num(row.get("inventory_cycle")) >= (_quantile_from_stats(score_stats, "inventory_cycle", "q75") or math.inf):
        risks.append("库存周期偏长，存在周转压力")
        score -= 5
    if _num(row.get("price_volatility")) >= (_quantile_from_stats(score_stats, "price_volatility", "q75") or math.inf):
        risks.append("价格波动偏高，不能追高")
        score -= 4
    if str(row.get("market_category") or "") == "急跌行情":
        risks.insert(0, "业务分类为急跌行情")
    if not reasons:
        reasons.append(f"行情分类为{row.get('market_category') or '常规行情'}")
    if not risks:
        risks.append("暂无强风险标签，仍需结合单车车况和目标利润")
    level, label = _recommendation(score, str(row.get("market_category") or ""))
    return {
        "score": max(0, min(100, round(score, 1))),
        "level": level,
        "label": label,
        "reasons": reasons[:4],
        "risks": risks[:4],
    }


def _public_item(
    row: dict[str, Any],
    score_stats: dict[str, dict[str, Any]],
    rank: int,
    dsi: dict[str, Any],
    *,
    city: str,
    cohort_label: str,
    include_ranking: bool = True,
) -> dict[str, Any]:
    scored = _score(row, score_stats, dsi, cohort_label=cohort_label)
    official_photo = _official_photo(row.get("brand"), row.get("series"))
    ranking_evidence = (
        _ranking_evidence(
            city=city,
            brand=row.get("brand"),
            series=row.get("series"),
        )
        if include_ranking
        else {}
    )
    return {
        "rank": rank,
        "brand": row.get("brand"),
        "series": row.get("series"),
        "model": row.get("model"),
        "model_year": row.get("model_year"),
        "city": row.get("city") or city,
        "market_category": row.get("market_category"),
        "market_category_label": row.get("market_category"),
        "recommendation_level": scored["level"],
        "recommendation_label": scored["label"],
        "opportunity_score": scored["score"],
        "deal_sample_90d": int(_num(row.get("deal_sample_90d"))),
        "listing_count": int(_num(row.get("listing_count"))),
        "avg_deal_cycle": _round(row.get("avg_deal_cycle"), 1),
        "inventory_cycle": _round(row.get("inventory_cycle"), 1),
        "sell_through_rate": _round(row.get("sell_through_rate"), 2),
        "price_change_30d": _round(row.get("price_change_30d"), 6),
        "deal_price_low_90d": _round(row.get("deal_price_low_90d"), 0),
        "deal_price_high_90d": _round(row.get("deal_price_high_90d"), 0),
        "dsi_signal": dsi,
        "reasons": scored["reasons"],
        "risks": scored["risks"],
        "action": _action_for(scored["level"]),
        "official_photo": official_photo,
        "ranking_evidence": ranking_evidence,
    }


def _action_for(level: str) -> str:
    return {
        "STRONG_RECOMMEND": "进入重点关注池；单车定价时优先查同款现价和利润空间",
        "RECOMMEND": "可作为候选车系；只在报价安全边界内推进",
        "WATCH": "先观察，不作为主动高价收车对象",
        "CAUTION": "谨慎收；优先选择低里程、好车况、低整备成本车源",
        "AVOID": "暂缓收；已有库存优先去化",
    }.get(level, "人工复核后再推进")


def _official_photo(brand: Any, series: Any) -> dict[str, Any] | None:
    try:
        from .dongchedi_official_photo_service import get_dongchedi_official_photo_service

        return get_dongchedi_official_photo_service().find_series_photo(brand=brand, series=series)
    except Exception:
        return None


def _ranking_evidence(city: str, brand: Any, series: Any) -> dict[str, list[dict[str, Any]]]:
    try:
        from .ranking_signal_service import get_ranking_signal_service

        service = get_ranking_signal_service()
        kwargs = {
            "city": city if city and city != "全国" else None,
            "brand": str(brand or "") or None,
            "series": str(series or "") or None,
            "limit": 2,
        }
        return {
            "sales": service.get_sales_liquidity_evidence(**kwargs),
            "popular": service.get_popularity_evidence(**kwargs),
            "discount": service.get_discount_risk_evidence(**kwargs),
            "city": service.get_city_preference_evidence(**kwargs),
        }
    except Exception:
        return {}


def build_selection_strategy_response(
    query_text: str,
    selected_city: str,
    client_state: dict | None = None,
) -> dict[str, Any]:
    from .selection_tools_service import build_selection_tools_response

    return build_selection_tools_response(query_text=query_text, selected_city=selected_city, client_state=client_state or {})

    loader = get_business_market_loader()
    text = str(query_text or "").strip() or "推荐值得收的车系"
    city = loader.find_city_in_text(text) or str(selected_city or "全国").strip() or "全国"
    if "全国" in text:
        city = "全国"
    brand = loader.find_brand_in_text(text)
    series = loader.find_series_in_text(text)
    use_national_scope = city in {"", "全国", "全网"}
    if use_national_scope:
        data_scope = "全国车型+年款口径"
        source_sheet = "无需打标：车型+年款详情数据"
        cohort_rows = loader.model_year_records
        rows = loader.filter_model_year(brand=brand, series=series)
        if not rows and not (brand or series):
            rows = cohort_rows
        cohort_label = "全国车型+年款"
    else:
        data_scope = "城市车系口径"
        source_sheet = "无需打标：车系+城市详情数据"
        cohort_rows = loader.filter_city_series(city=city)
        rows = cohort_rows
        cohort_label = f"{city}车系"
    notes: list[str] = []
    if not use_national_scope and brand:
        rows = [row for row in rows if brand in str(row.get("brand") or "")]
    if not use_national_scope and series:
        rows = [row for row in rows if row.get("series") == series]
    price_range = PRICE_RANGE_PATTERN.search(text)
    if price_range:
        lower = float(price_range.group(1)) * 10000
        upper = float(price_range.group(2)) * 10000
        overlap = [
            row for row in rows
            if _num(row.get("deal_price_high_90d")) >= lower
            and (_num(row.get("deal_price_low_90d")) or math.inf) <= upper
        ]
        rows = overlap or rows
        notes.append(f"已按{price_range.group(1)}-{price_range.group(2)}万成交价范围做近似筛选。")
    risk_mode = any(keyword in text for keyword in RISK_KEYWORDS)
    if not rows:
        card = {
            "card_type": "selection_strategy_agent",
            "state_id": "sel_" + hashlib.sha1(f"{city}|{text}".encode("utf-8")).hexdigest()[:12],
            "city": city,
            "query_text": text,
            "recommendations": [],
            "summary_report": {
                "headline": f"{city}没有命中可用选品数据",
                "key_findings": ["当前筛选条件在安全行情数据中未命中。"],
                "business_suggestions": ["换城市、放宽品牌/车系条件，或转为单车定价。"],
                "risk_notes": [],
                "data_quality_notes": [f"仅使用无需打标的线上安全 sheet；本次口径：{data_scope}。"],
            },
            "data_source": {
                "source_file": loader.metadata.get("source_file"),
                "source_sheet": source_sheet,
                "data_scope": data_scope,
                "online_safe": True,
            },
        }
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}
    items = []
    score_stats = _build_score_stats(cohort_rows)
    for row in rows:
        items.append(
            (
                row,
                _public_item(
                    row,
                    score_stats,
                    0,
                    loader.dsi_for_series(row.get("series")),
                    city=city,
                    cohort_label=cohort_label,
                    include_ranking=False,
                ),
            )
        )
    if risk_mode:
        items.sort(key=lambda pair: (pair[1]["recommendation_level"] not in {"AVOID", "CAUTION"}, pair[1]["opportunity_score"]))
    else:
        items.sort(key=lambda pair: -pair[1]["opportunity_score"])
    recommendations = []
    for index, (_, item) in enumerate(items[:20], start=1):
        item["rank"] = index
        if index <= 12:
            item["ranking_evidence"] = _ranking_evidence(
                city=city,
                brand=item.get("brand"),
                series=item.get("series"),
            )
        recommendations.append(item)
    top = recommendations[0]
    risk_count = sum(1 for item in recommendations if item["recommendation_level"] in {"CAUTION", "AVOID"})
    card = {
        "card_type": "selection_strategy_agent",
        "state_id": "sel_" + hashlib.sha1(f"{city}|{text}".encode("utf-8")).hexdigest()[:12],
        "city": city,
        "query_text": text,
        "scope": {"brand": brand, "series": series, "risk_mode": risk_mode, "data_scope": data_scope},
        "task_plan": {
            "goal": f"在{city}筛选值得收或需要避开的车系",
            "understanding": [f"城市：{city}", f"对象：{series or brand or '全部车系'}", f"任务：{'风险识别' if risk_mode else '机会推荐'}"],
            "steps": [
                f"读取{data_scope}行情指标",
                "计算成交活跃、库存健康、周转、价格稳定和DSI",
                "扣减价格下行、库存周期和波动风险",
                "输出可收车系、风险车系和下一步动作",
            ],
        },
        "task_execution": [
            {"name": "读取行情指标", "status": "done", "detail": f"{city}共读取{len(cohort_rows)}条{data_scope}记录"},
            {"name": "筛选候选车系", "status": "done", "detail": f"本轮命中{len(rows)}条候选记录"},
            {"name": "计算机会分", "status": "done", "detail": "按活跃度、库存健康、周转、价格稳定、DSI和风险扣分计算"},
            {"name": "生成选品建议", "status": "done", "detail": f"输出{len(recommendations)}个候选车系"},
        ],
        "recommendations": recommendations,
        "summary_report": {
            "headline": f"{city}优先看{top['brand']} {top['series']}，建议：{top['recommendation_label']}。",
            "key_findings": [
                f"本次命中{len(rows)}条候选，Top1机会分{top['opportunity_score']}。",
                f"前20个候选中，谨慎/暂缓车系{risk_count}个。",
                f"Top1：90天成交{top['deal_sample_90d']}辆，成交周期{top.get('avg_deal_cycle') or '-'}天。",
            ],
            "business_suggestions": [
                "进入定价前必须补齐具体单车七要素，不能直接按车系机会分收车。",
                "机会车系只代表值得关注；最终能不能收取决于同款现价、车况和目标利润。",
                "风险车系优先压低收车价或暂缓补库。",
            ],
            "risk_notes": list(dict.fromkeys(risk for item in recommendations[:5] for risk in item["risks"]))[:5],
            "data_quality_notes": notes + ["数据来自线上安全 sheet；机会分含DSI辅助信号，为确定性规则计算，不由LLM排序。"],
        },
        "data_source": {
            "source_file": loader.metadata.get("source_file"),
            "source_sheet": source_sheet,
            "data_scope": data_scope,
            "dsi_source": "DSI供需指数_车款ID.xlsx",
            "online_safe": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}
