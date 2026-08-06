"""Deterministic city market selection Agent built on business-calibrated data."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

from .market_state_data_loader import MarketStateDataLoader, get_market_state_loader


CATEGORY_PRESENTATION = {
    "上涨行情": ("价格上行", 75),
    "流动行情": ("流动性强", 85),
    "结构性行情": ("结构性机会", 90),
    "常规行情": ("常规跟踪", 60),
    "阴跌行情": ("价格偏弱", 40),
    "急跌行情": ("快速下跌", 25),
    "其他行情分类": ("需要复核", 35),
}

RECOMMENDATION_LABELS = {
    "STRONG_RECOMMEND": "重点关注",
    "RECOMMEND": "可关注",
    "WATCH": "正常跟踪",
    "CAUTION": "谨慎关注",
    "AVOID": "暂缓补库",
    "REVIEW": "人工复核",
}

RISK_KEYWORDS = ("不建议", "不要收", "风险", "下跌", "谨慎", "避开", "暂缓", "异常", "压力")
OPPORTUNITY_KEYWORDS = ("推荐", "值得收", "机会", "热门", "优先", "关注")
PRICE_RANGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*万")
UNSUPPORTED_DIMENSION_KEYWORDS = ("新能源", "纯电", "插混", "增程", "SUV", "suv", "轿车", "MPV", "mpv")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _metric_high(value: Any, threshold: float | None) -> bool:
    number = _number(value)
    return number is not None and threshold is not None and number >= threshold


def _metric_low(value: Any, threshold: float | None) -> bool:
    number = _number(value)
    return number is not None and threshold is not None and number <= threshold


def _round(value: Any, digits: int = 2) -> float | None:
    number = _number(value)
    return round(number, digits) if number is not None else None


def _recommendation_level(
    row: dict[str, Any],
    *,
    high_sell_through: bool,
    short_cycle: bool,
) -> str:
    category = row.get("market_category") or "其他行情分类"
    insufficient = (
        (_number(row.get("deal_sample_90d")) or 0) < 3
        or (_number(row.get("listing_count")) or 0) < 3
        or row.get("market_category") in (None, "")
        or (
            _number(row.get("sell_through_rate")) is None
            and _number(row.get("avg_deal_cycle")) is None
        )
    )
    if insufficient or category == "其他行情分类":
        return "REVIEW"
    if category == "结构性行情":
        return "STRONG_RECOMMEND"
    if category == "流动行情" and high_sell_through and short_cycle:
        return "STRONG_RECOMMEND"
    if category in {"流动行情", "上涨行情"}:
        return "RECOMMEND"
    if category == "常规行情":
        return "WATCH"
    if category == "阴跌行情":
        return "CAUTION"
    if category == "急跌行情":
        return "AVOID"
    return "REVIEW"


def _score_row(
    row: dict[str, Any],
    city_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    category = row.get("market_category") or "其他行情分类"
    category_label, score = CATEGORY_PRESENTATION.get(category, CATEGORY_PRESENTATION["其他行情分类"])
    thresholds = {
        "sell_through_high": MarketStateDataLoader.percentile(city_rows, "sell_through_rate", 0.75),
        "deal_cycle_short": MarketStateDataLoader.percentile(city_rows, "avg_deal_cycle", 0.25),
        "lead_rate_high": MarketStateDataLoader.percentile(city_rows, "lead_rate", 0.75),
        "inquiry_high": MarketStateDataLoader.percentile(city_rows, "inquiry_conversion_rate", 0.75),
        "search_high": MarketStateDataLoader.percentile(city_rows, "search_volume", 0.75),
        "uv_high": MarketStateDataLoader.percentile(city_rows, "detail_uv", 0.75),
        "volatility_high": MarketStateDataLoader.percentile(city_rows, "price_volatility", 0.75),
        "inventory_cycle_long": MarketStateDataLoader.percentile(city_rows, "inventory_cycle", 0.75),
        "price_cut_high": MarketStateDataLoader.percentile(city_rows, "price_cut_rate_30d", 0.75),
    }
    high_sell_through = _metric_high(row.get("sell_through_rate"), thresholds["sell_through_high"])
    short_cycle = _metric_low(row.get("avg_deal_cycle"), thresholds["deal_cycle_short"])
    high_lead = _metric_high(row.get("lead_rate"), thresholds["lead_rate_high"])
    high_inquiry = _metric_high(row.get("inquiry_conversion_rate"), thresholds["inquiry_high"])
    high_demand = (
        _metric_high(row.get("search_volume"), thresholds["search_high"])
        or _metric_high(row.get("detail_uv"), thresholds["uv_high"])
    )
    high_volatility = _metric_high(row.get("price_volatility"), thresholds["volatility_high"])
    long_inventory = _metric_high(row.get("inventory_cycle"), thresholds["inventory_cycle_long"])
    high_price_cut = (
        (_number(row.get("price_cut_rate_30d")) or 0) > 0
        and _metric_high(row.get("price_cut_rate_30d"), thresholds["price_cut_high"])
    )
    insufficient = (
        (_number(row.get("deal_sample_90d")) or 0) < 3
        or (_number(row.get("listing_count")) or 0) < 3
    )

    reasons: list[str] = []
    risks: list[str] = []
    if high_sell_through:
        score += 5
        reasons.append("上架成交率处于当前城市较高水平")
    if short_cycle:
        score += 5
        reasons.append("平均成交周期处于当前城市较短水平")
    if high_lead:
        score += 5
        reasons.append("留资率处于当前城市较高水平")
    if high_inquiry:
        score += 5
        reasons.append("询价转化率处于当前城市较高水平")
    if high_demand:
        score += 5
        reasons.append("搜索量或详情页访问处于当前城市较高水平")

    price_change_30d = _number(row.get("price_change_30d"))
    if price_change_30d is not None and price_change_30d <= -0.03:
        score -= 10
        risks.append("30天价格明显下行，收车价需要保守")
    if high_volatility:
        score -= 5
        risks.append("价格波动率偏高，需扩大安全边际")
    if long_inventory:
        score -= 5
        risks.append("库存平均周期偏长，存在周转压力")
    if high_price_cut:
        score -= 5
        risks.append("近30天降价车源占比较高")
    if insufficient:
        score -= 10
        risks.append("90天成交或上架样本不足，结论需人工复核")

    level = _recommendation_level(
        row,
        high_sell_through=high_sell_through,
        short_cycle=short_cycle,
    )
    if level == "REVIEW":
        score = min(score, 55)
    elif level == "CAUTION":
        score = min(score, 50)
    elif level == "AVOID":
        score = min(score, 35)
    if category == "上涨行情":
        risks.append("价格处于上行阶段，关注但不建议高价追涨")
    if category == "急跌行情":
        risks.insert(0, "业务分类为急跌行情，原则上暂缓补库")
    elif category == "阴跌行情":
        risks.insert(0, "业务分类为阴跌行情，建议谨慎控制收车价")
    if not reasons:
        reasons.append(f"业务校准分类为{category_label}")
    if not risks:
        risks.append("暂无业务规则命中的显著风险，仍需结合单车车况复核")

    action_by_level = {
        "STRONG_RECOMMEND": "可进入重点选品清单，结合单车车况和收车价继续评估",
        "RECOMMEND": "可关注，但上涨行情不建议高价抢收",
        "WATCH": "维持正常跟踪，等待更强成交或需求信号",
        "CAUTION": "谨慎收车，优先控制价格与库存周期",
        "AVOID": "原则上暂缓补库，已有库存优先去化",
        "REVIEW": "样本或指标不足，进入人工复核后再决定",
    }
    return {
        **row,
        "market_category_label": category_label,
        "recommendation_level": level,
        "recommendation_label": RECOMMENDATION_LABELS[level],
        "opportunity_score": max(0, min(100, int(round(score)))),
        "reasons": reasons,
        "risks": risks,
        "action": action_by_level[level],
    }


def _public_recommendation(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "brand_id": row.get("brand_id"),
        "brand": row.get("brand"),
        "series_id": row.get("series_id"),
        "series": row.get("series"),
        "city": row.get("city"),
        "market_category": row.get("market_category"),
        "market_category_label": row.get("market_category_label"),
        "category_basis": row.get("category_basis"),
        "recommendation_level": row.get("recommendation_level"),
        "recommendation_label": row.get("recommendation_label"),
        "opportunity_score": row.get("opportunity_score"),
        "price_change_7d": _round(row.get("price_change_7d"), 6),
        "price_change_14d": _round(row.get("price_change_14d"), 6),
        "price_change_30d": _round(row.get("price_change_30d"), 6),
        "deal_sample_90d": int(_number(row.get("deal_sample_90d")) or 0),
        "deal_price_low_90d": _round(row.get("deal_price_low_90d"), 0),
        "deal_price_high_90d": _round(row.get("deal_price_high_90d"), 0),
        "price_volatility": _round(row.get("price_volatility"), 4),
        "deal_count": int(_number(row.get("deal_count")) or 0),
        "listing_count": int(_number(row.get("listing_count")) or 0),
        "sell_through_rate": _round(row.get("sell_through_rate"), 2),
        "avg_deal_cycle": _round(row.get("avg_deal_cycle"), 1),
        "current_inventory": int(_number(row.get("current_inventory")) or 0),
        "inventory_cycle": _round(row.get("inventory_cycle"), 1),
        "price_cut_rate_30d": _round(row.get("price_cut_rate_30d"), 2),
        "lead_rate": _round(row.get("lead_rate"), 2),
        "inquiry_conversion_rate": _round(row.get("inquiry_conversion_rate"), 2),
        "search_volume": int(_number(row.get("search_volume")) or 0),
        "detail_uv": int(_number(row.get("detail_uv")) or 0),
        "reasons": row.get("reasons") or [],
        "risks": row.get("risks") or [],
        "action": row.get("action"),
    }


def _empty_card(city: str, query_text: str, notes: list[str]) -> dict[str, Any]:
    state_id = "ms_" + hashlib.sha1(f"{city}|{query_text}".encode("utf-8")).hexdigest()[:12]
    return {
        "card_type": "empty_market_opportunity_agent",
        "state_id": state_id,
        "city": city,
        "query_text": query_text,
        "recommendations": [],
        "empty_state": {
            "title": "暂无可用行情数据",
            "content": "当前城市暂无车系+城市维度行情数据，无法生成选品建议。",
            "actions": ["换一个城市", "查看全国行情", "返回行业日报"],
        },
        "summary_report": {
            "headline": f"{city}当前没有可用的车系+城市行情记录",
            "key_findings": [],
            "business_suggestions": [],
            "risk_notes": [],
            "data_quality_notes": notes,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_market_opportunity_response(
    query_text: str,
    selected_city: str,
    client_state: dict | None = None,
    *,
    loader: MarketStateDataLoader | None = None,
) -> dict[str, Any]:
    loader = loader or get_market_state_loader()
    query_text = str(query_text or "").strip() or "查看当前城市行情"
    client_state = client_state or {}
    prior_context = (
        client_state.get("lastMarketOpportunityContext")
        or client_state.get("last_market_opportunity_context")
        or {}
    )
    detected_city = loader.find_city_in_text(query_text) if loader.available else None
    city = detected_city or str(selected_city or "全国").strip() or "全国"
    notes: list[str] = []
    if not loader.available:
        card = _empty_card(city, query_text, ["行情状态数据文件缺失或无法读取。"])
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}

    series = loader.find_series_in_text(query_text)
    comparison_series = loader.find_all_series_in_text(query_text)
    compare_mode = len(comparison_series) >= 2 and any(keyword in query_text for keyword in ("对比", "比较", "差异", "哪个更", "谁更"))
    brand = loader.find_brand_in_text(query_text)
    contextual_follow_up = any(
        keyword in query_text
        for keyword in ("为什么推荐第一个", "第一个为什么", "这个车系风险", "为什么说它", "第一个车系")
    )
    if not series and not brand and contextual_follow_up:
        prior_top = prior_context.get("top_recommendations") or []
        if prior_top and isinstance(prior_top[0], dict):
            series = prior_top[0].get("series") or None
    price_range = PRICE_RANGE_PATTERN.search(query_text)
    if price_range:
        notes.append(
            f"已识别价格段 {price_range.group(1)}-{price_range.group(2)} 万；数据源没有价格段字段，按90天成交价区间是否重叠进行近似筛选。"
        )
    if any(keyword in query_text for keyword in UNSUPPORTED_DIMENSION_KEYWORDS):
        notes.append("当前数据源没有能源类型或车身级别字段，相关条件仅记录在查询范围中，未直接参与筛选。")

    city_rows = loader.filter(city=city)
    if not city_rows:
        card = _empty_card(city, query_text, notes or ["当前城市在业务校准数据中没有记录。"])
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}

    filtered = city_rows
    if compare_mode:
        targets = set(comparison_series)
        filtered = [row for row in city_rows if row.get("series") in targets]
    elif series:
        filtered = loader.filter(city=city, series=series)
    elif brand:
        filtered = loader.filter(city=city, brand=brand)
    if not filtered:
        card = _empty_card(city, query_text, notes + ["查询中的品牌或车系未在当前城市数据中命中。"])
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}

    if price_range:
        lower = float(price_range.group(1)) * 10000
        upper = float(price_range.group(2)) * 10000
        overlap = [
            row for row in filtered
            if (_number(row.get("deal_price_high_90d")) or 0) >= lower
            and (_number(row.get("deal_price_low_90d")) or float("inf")) <= upper
        ]
        if overlap:
            filtered = overlap
        else:
            notes.append("指定价格带与当前90天成交价范围没有交集，保留原范围并标记为需复核。")

    scored = [_score_row(row, city_rows) for row in filtered]
    risk_query = any(keyword in query_text for keyword in RISK_KEYWORDS)
    opportunity_query = any(keyword in query_text for keyword in OPPORTUNITY_KEYWORDS)
    risk_order = {"AVOID": 0, "CAUTION": 1, "REVIEW": 2, "WATCH": 3, "RECOMMEND": 4, "STRONG_RECOMMEND": 5}
    opportunity_order = {"STRONG_RECOMMEND": 0, "RECOMMEND": 1, "WATCH": 2, "CAUTION": 3, "REVIEW": 4, "AVOID": 5}
    if risk_query:
        scored.sort(key=lambda row: (risk_order[row["recommendation_level"]], row["opportunity_score"], -(row.get("deal_sample_90d") or 0)))
    else:
        scored.sort(
            key=lambda row: (
                opportunity_order[row["recommendation_level"]] if opportunity_query else 0,
                -row["opportunity_score"],
                -(row.get("deal_sample_90d") or 0),
            )
        )
    recommendations = [_public_recommendation(row, index + 1) for index, row in enumerate(scored[:20])]

    target_scope = "、".join(comparison_series) if compare_mode else series or brand or "全部车系"
    state_id = "ms_" + hashlib.sha1(f"{city}|{query_text}".encode("utf-8")).hexdigest()[:12]
    recommended = [row for row in recommendations if row["recommendation_level"] in {"STRONG_RECOMMEND", "RECOMMEND"}]
    caution = [row for row in recommendations if row["recommendation_level"] in {"CAUTION", "REVIEW"}]
    avoid = [row for row in recommendations if row["recommendation_level"] == "AVOID"]
    top = recommendations[0]
    headline = (
        f"{city}{target_scope}中，{top['brand']} {top['series']}当前排序最高，"
        f"业务分类为{top['market_category']}，建议“{top['recommendation_label']}”。"
    )
    data_note = (
        f"数据来自《{loader.metadata.get('source_file', '行情状态业务校准.xlsx')}》"
        f"的“{loader.metadata.get('source_sheet', '无需打标：车型+城市详情数据')}”sheet，"
        "推荐等级与机会分均由确定性规则计算，不由大模型判断。"
    )
    notes.append(data_note)
    card = {
        "card_type": "market_opportunity_agent",
        "state_id": state_id,
        "city": city,
        "query_text": query_text,
        "scope": {
            "series": series,
            "comparison_series": comparison_series if compare_mode else [],
            "compare_mode": compare_mode,
            "brand": brand,
            "price_range_wan": [float(price_range.group(1)), float(price_range.group(2))] if price_range else None,
            "risk_query": risk_query,
            "opportunity_query": opportunity_query,
        },
        "task_plan": {
            "goal": f"在{city}市场中筛选值得关注的二手车车系",
            "understanding": [
                f"城市：{city}",
                f"对象：{target_scope}",
                f"需求类型：{'风险排查' if risk_query else '机会筛选' if opportunity_query else '行情分析'}",
            ],
            "steps": [
                "读取车系+城市行情数据",
                "筛选符合城市和关键词的车系",
                "识别业务行情分类与风险标签",
                "计算确定性机会分",
                "生成城市选品建议",
            ],
        },
        "task_execution": [
            {"name": "匹配城市", "status": "done", "detail": f"已选择{city}"},
            {"name": "读取行情数据", "status": "done", "detail": f"当前城市共读取{len(city_rows)}条车系记录"},
            {"name": "筛选候选车系", "status": "done", "detail": f"查询范围命中{len(filtered)}条记录"},
            {"name": "计算机会分", "status": "done", "detail": "已按业务分类、流动性、需求、价格与库存风险计算"},
            {"name": "生成选品报告", "status": "done", "detail": f"已输出{len(recommendations)}个车系建议"},
        ],
        "recommendations": recommendations,
        "summary_report": {
            "headline": headline,
            "recommended_focus": [f"{row['brand']} {row['series']}" for row in recommended[:5]],
            "caution_focus": [f"{row['brand']} {row['series']}" for row in caution[:5]],
            "avoid_focus": [f"{row['brand']} {row['series']}" for row in avoid[:5]],
            "key_findings": [
                f"本次共分析{len(filtered)}个符合范围的车系记录。",
                f"重点关注/可关注车系共{len(recommended)}个。",
                f"谨慎或人工复核车系共{len(caution)}个，暂缓补库车系共{len(avoid)}个。",
            ],
            "business_suggestions": [
                "重点关注车系仍需结合具体车况和收车价确认，不建议只按机会分直接收车。",
                "上涨行情关注但不追高；阴跌与急跌行情优先控制库存和收车价格。",
                "样本不足或指标缺失的车系进入人工复核，不将缺失指标补造为零。",
            ],
            "risk_notes": list(dict.fromkeys(risk for row in recommendations[:5] for risk in row["risks"]))[:5],
            "data_quality_notes": notes,
        },
        "data_source": {
            "source_type": "uploaded_business_calibration",
            "source_file": loader.metadata.get("source_file"),
            "source_sheet": loader.metadata.get("source_sheet"),
            "row_count": loader.metadata.get("row_count"),
            "is_generated": False,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if compare_mode:
        card["comparison"] = {
            "series": comparison_series,
            "winner": f"{top['brand']} {top['series']}",
            "basis": "机会分、行情分类、90天成交样本、价格趋势、成交周期与库存风险",
            "rows": [
                {
                    "brand": item.get("brand"),
                    "series": item.get("series"),
                    "opportunity_score": item.get("opportunity_score"),
                    "recommendation_label": item.get("recommendation_label"),
                    "deal_price_range_yuan": [item.get("deal_price_low_90d"), item.get("deal_price_high_90d")],
                    "risks": item.get("risks"),
                }
                for item in recommendations
            ],
        }
    return {
        "module": "market_state",
        "selected_city": city,
        "called_price": False,
        "market_agent_card": card,
    }
