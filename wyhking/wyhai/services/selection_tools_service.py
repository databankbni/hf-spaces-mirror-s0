from __future__ import annotations

import hashlib
import math
import re
from bisect import bisect_right
from datetime import datetime, timezone
from typing import Any

from .brand_tier import classify_brand_tier, extract_brand_tier_from_text, matches_brand_tier, normalize_brand_tier
from .business_market_workbook_loader import finite_number, get_business_market_loader, normalize_text
from .label_gate import apply_label_gate
from .metric_smoothing import smooth_business_metrics, smooth_business_metrics_hierarchical
from .sample_confidence_calculator import calculate_sample_confidence
from .selection_query_semantics import classify_selection_query_family
from .selection_category_ontology import describe_category_scope, extract_selection_category_constraints
from .selection_score_config import get_selection_score_config
from .selection_history_metrics_service import get_selection_history_metrics_service
from .vehicle_slot_extractor_v2 import VehicleSlotExtractorV2
from .vehicle_taxonomy import (
    get_vehicle_taxonomy_service,
    normalize_energy,
    normalize_energy_subtype,
    normalize_manufacturer_attribute,
    normalize_selection_filter,
    normalize_vehicle_category,
)


PRICE_RANGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*万")
PRICE_UNDER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*万(?:以内|以下|内)")
PRICE_ABOVE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*万(?:以上|起)")
PRICE_BUDGET_OPPORTUNITY_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*万(?:预算)?(?:有什么|有啥|有哪些|哪些|什么|有)?(?:机会|推荐|值得收|能做)"
)
TIME_WINDOW_PATTERN = re.compile(r"(7|14|15|30|45|60|90)\s*天")
RISK_KEYWORDS = ("避免", "别碰", "不要", "不建议", "避坑", "风险", "亏", "慢", "库存压力", "库存高", "库存多", "去库存", "下跌", "阴跌", "急跌", "暂缓")
COMPARE_KEYWORDS = ("对比", "比较", "哪个", "哪款", "谁更", "差异")
PRICE_BAND_KEYWORDS = ("价格带", "预算", "价位", "多少万")
PRICING_HANDOFF_KEYWORDS = ("定价", "收车价", "报价", "价格区间", "建议价")
FUEL_KEYWORDS = {
    "新能源": ("新能源", "电车", "纯电", "插混", "增程"),
    "燃油车": ("燃油", "油车"),
}
VEHICLE_TYPE_KEYWORDS = ("SUV", "suv", "轿车", "MPV", "mpv", "皮卡", "轻客", "微面")
GENERIC_SCOPE_SERIES = {"新能源", "燃油", "油车", "电车", "纯电", "插混", "混动", "二手车", "车", "SUV", "MPV", "轿车", "豪华", "综合新能源"}
GENERIC_SCOPE_SERIES_NORMALIZED = {normalize_text(value) for value in GENERIC_SCOPE_SERIES}
BRAND_GROUP_ALIASES = {
    "BBA": ("宝马", "奔驰", "奥迪"),
    "两田一产": ("丰田", "本田", "日产"),
}

SELECTION_TASK_TARGETS = {
    "recommend_models": "recommend_series",
    "recommend_price_band": "price_band_opportunity",
    "recommend_city_opportunity": "recommend_series",
    "identify_risky_models": "risk_series",
    "compare_series": "compare_series",
    "low_price_opportunity": "price_band_opportunity",
    "series_judgement": "series_judgement",
    "lookup_selection_rank": "rank_lookup",
    "selection_to_pricing": "selection_to_pricing",
    "explain_selection_reason": "selection_reason",
    "explain_selection_score": "score_explanation",
    "show_selection_evidence": "evidence_answer",
    "run_signal_ablation": "signal_ablation",
    "show_backtest_metrics": "backtest_metrics",
    "explain_baseline": "baseline_answer",
    "explain_total_profit_scale": "total_profit_answer",
    "explain_data_quality": "data_quality_answer",
    "explain_signal_rule": "method_explanation",
    "explain_policy_newcar_effect": "policy_answer",
    "explain_module_boundary": "module_boundary_answer",
}


def _normalize_energy_filter(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"全部", "不限", "总计"}:
        return ""
    normalized = normalize_energy(text)
    if normalized == "燃油车":
        return "燃油车"
    if normalized == "新能源":
        return "新能源"
    return ""


def _num(value: Any, default: float = 0) -> float:
    number = finite_number(value)
    return number if number is not None else default


def _round(value: Any, digits: int = 2) -> float | None:
    number = finite_number(value)
    return round(number, digits) if number is not None else None


def _rank(values: list[float], value: Any, *, reverse: bool = False) -> float:
    current = finite_number(value)
    if current is None or not values:
        return 0.5
    pct = bisect_right(values, current) / len(values)
    return 1 - pct if reverse else pct


def _quantile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _stats(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field in fields:
        values = sorted(
            number for number in (_num(row.get(field), math.nan) for row in rows)
            if math.isfinite(number)
        )
        out[field] = {"values": values, "q25": _quantile(values, 0.25), "q75": _quantile(values, 0.75)}
    return out


class SelectionToolsService:
    """Deterministic productized toolchain for the selection module."""

    def __init__(self) -> None:
        self.loader = get_business_market_loader()
        self.history = get_selection_history_metrics_service()
        self.score_config = get_selection_score_config()
        self.taxonomy = get_vehicle_taxonomy_service()
        self.vehicle_slot_extractor = VehicleSlotExtractorV2()

    def run(self, query_text: str, selected_city: str = "全国", client_state: dict | None = None) -> dict[str, Any]:
        text = str(query_text or "").strip() or "推荐值得收的车系"
        slots = self.extract_slots(text, selected_city, client_state or {})
        needs_daily_report = slots.get("selection_target") == "policy_answer" or bool(
            re.search(r"日报|政策|新车|上市|降价事件|品牌事件", text)
        )
        daily_report = (
            self.daily_report_tool(text, slots)
            if needs_daily_report
            else {"available": False, "tool": "daily_report_tool", "events": [], "not_required": True}
        )
        indicators = self.market_indicator_tool(slots)
        market_state = self.market_state_tool(indicators, slots)
        strategy = self.selection_strategy_tool(market_state, slots)
        return self.response_composer(text, slots, daily_report, indicators, market_state, strategy)

    def extract_slots(self, text: str, selected_city: str, client_state: dict[str, Any]) -> dict[str, Any]:
        city = self.loader.find_city_in_text(text) or str(selected_city or "").strip() or client_state.get("selected_city") or "全国"
        if "全国" in text:
            city = "全国"
        selection_task_intent = str(client_state.get("selection_task_intent") or "").strip()
        selection_detail_intent = str(client_state.get("selection_detail_intent") or "").strip()
        loader_brand = self.loader.find_brand_in_text(text)
        loader_series = self.loader.find_series_in_text(text)
        series_alias = self._series_alias_from_text(text)
        if series_alias:
            loader_series = series_alias
        obvious_scope_request = self._is_cohort_selection_request(
            text,
            selection_task_intent=selection_task_intent,
            selection_detail_intent=selection_detail_intent,
        ) or bool(
            not loader_brand
            and not loader_series
            and re.search(
                r"新能源|燃油|纯电|插混|增程|轿车|SUV|MPV|豪华|自主|合资|进口|"
                r"供不应求|供需平衡|机会|榜单|值得收|避免收|不建议收",
                str(text or ""),
                flags=re.I,
            )
        )
        intent_slots = client_state.get("intent_v2_slots") or client_state.get("_intent_v2_slots") or {}
        if not isinstance(intent_slots, dict):
            intent_slots = {}
        # Cohort selection does not need the single-vehicle catalogue matcher.
        # Skipping its full catalogue scan keeps first response latency stable
        # while concrete series questions still use the canonical matcher.
        if not intent_slots and not obvious_scope_request:
            intent_slots = (self.vehicle_slot_extractor.extract(text, client_state) or {}).get("slots") or {}
        series_mentions = self._find_all_series(text, limit=6)
        brand_group = self._brand_group_from_text(text)
        if self._is_generic_scope_series(loader_series):
            loader_series = None
        cohort_request = self._is_cohort_selection_request(
            text,
            selection_task_intent=selection_task_intent,
            selection_detail_intent=selection_detail_intent,
        )
        inherit_entity = not cohort_request or bool(series_mentions) or bool(loader_series) or bool(loader_brand)
        intent_series_is_scope = self._is_generic_scope_series(intent_slots.get("series"))
        brand = loader_brand or (
            intent_slots.get("brand") if inherit_entity and not intent_series_is_scope else None
        )
        extracted_series = self._canonical_series(
            brand,
            intent_slots.get("series") if inherit_entity else None,
        )
        if self._is_generic_scope_series(extracted_series):
            extracted_series = None
        series = series_mentions[0] if series_mentions else loader_series or extracted_series
        if series and not series_mentions:
            series_mentions = [series]
        series_brand = self._brand_for_series(series)
        if series_brand:
            # A trim token such as "Lite" can also be a niche brand name. Once
            # the series is matched exactly, its catalogue brand is the safer
            # identity and must win over incidental trim text.
            brand = series_brand
        price_band = self._extract_price_band(text)
        if not price_band and isinstance(intent_slots.get("price_band"), dict):
            price_band = dict(intent_slots.get("price_band") or {})
        category_constraints = extract_selection_category_constraints(text)
        fuel_type = (
            category_constraints.get("fuel_type")
            or _normalize_energy_filter(intent_slots.get("fuel_type") or intent_slots.get("energy_filter"))
            or self._extract_fuel_type(text, client_state)
        )
        selection_filter = self._extract_selection_filter(text, client_state)
        if category_constraints.get("selection_filter"):
            selection_filter = str(category_constraints.get("selection_filter"))
        brand_tier = (
            category_constraints.get("brand_tier")
            or normalize_brand_tier(intent_slots.get("brand_tier"))
            or self._extract_brand_tier(text, client_state)
        )
        energy_subtype = normalize_energy_subtype(
            category_constraints.get("energy_subtype") or intent_slots.get("energy_subtype")
        )
        body_category = normalize_vehicle_category(
            category_constraints.get("body_category") or intent_slots.get("body_category")
        )
        manufacturer_attribute = normalize_manufacturer_attribute(
            category_constraints.get("manufacturer_attribute") or intent_slots.get("manufacturer_attribute")
        )
        vehicle_type = next((item.upper() if item.lower() == "suv" else item for item in VEHICLE_TYPE_KEYWORDS if item in text), "")
        if selection_filter in {"轿车", "SUV", "MPV"}:
            vehicle_type = selection_filter
        time_window = self._extract_time_window(text)
        selection_target = self._selection_target(
            text,
            series_mentions,
            price_band,
            selection_task_intent=selection_task_intent,
        )
        requested_rank = _extract_ordinal(text) if selection_target == "rank_lookup" else None
        market_context = client_state.get("lastMarketOpportunityContext") or client_state.get("last_market_opportunity_context") or {}
        context_scope = market_context.get("scope") if isinstance(market_context, dict) else {}
        is_scope_followup = selection_task_intent in {
            "refine_selection_scope",
            "sort_filter_selection_result",
            "lookup_selection_rank",
            "explain_selection_score",
            "explain_selection_reason",
            "series_judgement",
        } or selection_detail_intent in {
            "selection.followup_refine",
            "selection.sort_filter",
            "selection.rank_lookup",
            "selection.explain_rank_score",
            "selection.explain_exclusion",
            "selection.series_judgement",
        }
        if is_scope_followup and isinstance(context_scope, dict):
            if not brand_group:
                brand_group = [str(item) for item in (context_scope.get("brand_group") or []) if str(item).strip()]
            if not price_band and isinstance(context_scope.get("price_band"), dict):
                price_band = dict(context_scope.get("price_band") or {})
            if not fuel_type or fuel_type == "全部":
                fuel_type = _normalize_energy_filter(
                    context_scope.get("fuel_type") or context_scope.get("energy_filter")
                )
            if selection_filter == "全部":
                inherited_body = normalize_selection_filter(
                    context_scope.get("selection_filter") or context_scope.get("body_filter")
                )
                if inherited_body in {"轿车", "SUV", "MPV"}:
                    selection_filter = inherited_body
                    vehicle_type = inherited_body
            if not brand_tier:
                brand_tier = normalize_brand_tier(context_scope.get("brand_tier"))
            if not energy_subtype:
                energy_subtype = normalize_energy_subtype(context_scope.get("energy_subtype"))
            if not body_category:
                body_category = normalize_vehicle_category(context_scope.get("body_category"))
            if not manufacturer_attribute:
                manufacturer_attribute = normalize_manufacturer_attribute(context_scope.get("manufacturer_attribute"))
            price_band = price_band or {}
        contextual_items = (
            market_context.get("all_ranked_candidates")
            or market_context.get("top_recommendations")
            or []
        ) if isinstance(market_context, dict) else []
        contextual_rank_item: dict[str, Any] | None = None
        contextual_series_items: list[dict[str, Any]] = []
        if series and isinstance(contextual_items, list):
            normalized_series = normalize_text(series)
            normalized_brand = normalize_text(brand)
            contextual_series_items = [
                dict(item)
                for item in contextual_items
                if isinstance(item, dict)
                and (
                    normalize_text(item.get("series")) == normalized_series
                    or (
                        normalized_brand
                        and normalize_text(item.get("brand")) == normalized_brand
                        and (
                            normalized_series in normalize_text(item.get("series"))
                            or normalize_text(item.get("series")) in normalized_series
                        )
                    )
                )
            ][:20]
        if (
            not series
            # “第37名是什么车”字面含“什么车”，但本质是读取上一张完整榜单，
            # 不能因此被当成重新生成候选集的群组请求。
            and (not cohort_request or selection_target == "rank_lookup")
            and isinstance(contextual_items, list)
            and contextual_items
            and self._has_vehicle_context_reference(text)
        ):
            ordinal = _extract_ordinal(text)
            referenced = None
            if ordinal:
                referenced = contextual_items[ordinal - 1] if ordinal <= len(contextual_items) else None
            else:
                previous_lookup = market_context.get("subject_lookup") if isinstance(market_context, dict) else {}
                previous_matches = previous_lookup.get("matches") if isinstance(previous_lookup, dict) else []
                if isinstance(previous_matches, list) and previous_matches:
                    previous_subject = previous_matches[0]
                    if isinstance(previous_subject, dict):
                        previous_series = normalize_text(previous_subject.get("series"))
                        previous_brand = normalize_text(previous_subject.get("brand"))
                        referenced = next(
                            (
                                item for item in contextual_items
                                if isinstance(item, dict)
                                and normalize_text(item.get("series")) == previous_series
                                and (not previous_brand or normalize_text(item.get("brand")) == previous_brand)
                            ),
                            previous_subject,
                        )
                if referenced is None:
                    referenced = contextual_items[0]
            if isinstance(referenced, dict):
                contextual_rank_item = dict(referenced)
                # Preserve the exact row the user is referring to.  Without
                # this, the next step may recompute the same series in a new
                # scope and silently fall back to the current top-1 vehicle.
                contextual_series_items = [dict(referenced)]
                brand = referenced.get("brand") or brand
                series = referenced.get("series") or series
                if series:
                    series_mentions = [str(series)]
        return {
            "city": city,
            "selection_filter": selection_filter,
            "price_band": price_band,
            "price_low_yuan": price_band.get("low"),
            "price_high_yuan": price_band.get("high"),
            "brand": brand,
            "series": series,
            "series_mentions": series_mentions,
            "brand_tier": brand_tier,
            "manufacturer_attribute": manufacturer_attribute,
            "brand_group": brand_group,
            "fuel_type": fuel_type,
            "energy_subtype": energy_subtype,
            "body_category": body_category,
            "vehicle_type": vehicle_type,
            "time_window": time_window,
            "selection_target": selection_target,
            "selection_task_intent": selection_task_intent,
            "selection_detail_intent": selection_detail_intent,
            "requested_rank": requested_rank,
            "contextual_rank_item": contextual_rank_item,
            "contextual_series_items": contextual_series_items,
            "requested_answer_mode": client_state.get("answer_mode"),
            "raw_text": text,
        }

    def _series_alias_from_text(self, text: str) -> str | None:
        aliases = (
            (r"宝马\s*5(?!\s*系)", "宝马5系"),
            (r"奔驰\s*E\s*(?:200|260|300|350|400|450)(?:L|eL)?", "奔驰E级"),
            (r"奔驰\s*E\s*级", "奔驰E级"),
            (r"毛豆\s*[Yy]", "Model Y"),
            (r"问届\s*M?7", "问界M7"),
        )
        for pattern, canonical in aliases:
            if re.search(pattern, str(text or ""), flags=re.I):
                return canonical
        return None

    def _brand_for_series(self, series: Any) -> str | None:
        series_key = normalize_text(series)
        if not series_key:
            return None
        brands = {
            str(row.get("brand") or "").strip()
            for row in self.loader.city_series_records + self.loader.model_year_records
            if normalize_text(row.get("series")) == series_key and str(row.get("brand") or "").strip()
        }
        return next(iter(brands)) if len(brands) == 1 else None

    @staticmethod
    def _brand_group_from_text(text: str) -> list[str]:
        value = str(text or "")
        for alias, brands in BRAND_GROUP_ALIASES.items():
            if re.search(re.escape(alias), value, flags=re.I):
                return list(brands)
        return []

    def _canonical_series(self, brand: Any, series: Any) -> str | None:
        brand_text = str(brand or "").strip()
        series_text = str(series or "").strip()
        if not series_text:
            return None
        target = normalize_text(f"{brand_text}{series_text}") if brand_text else normalize_text(series_text)
        exact = [name for name in self.loader.series_names if normalize_text(name) == target]
        if exact:
            return exact[0]
        standalone = [name for name in self.loader.series_names if normalize_text(name) == normalize_text(series_text)]
        if standalone:
            return standalone[0]
        if brand_text:
            candidates = [
                name
                for name in self.loader.series_names
                if normalize_text(name).startswith(normalize_text(brand_text))
                and normalize_text(series_text) in normalize_text(name)
            ]
            if candidates:
                return sorted(candidates, key=lambda name: ("进口" in str(name), len(str(name)), str(name)))[0]
        return series_text

    def daily_report_tool(self, text: str, slots: dict[str, Any]) -> dict[str, Any]:
        try:
            from .daily_report_content_service import DailyReportContentService

            report_date = _latest_report_date()
            if not report_date:
                return {"available": False, "tool": "daily_report_tool", "events": [], "degraded_reason": "no_uploaded_report"}
            service = DailyReportContentService()
            query = " ".join(
                str(item)
                for item in (slots.get("brand"), slots.get("series"), slots.get("fuel_type"), slots.get("city"), text)
                if item
            )
            events = service.retrieve(report_date, query=query, limit=4)
            return {
                "available": bool(events),
                "tool": "daily_report_tool",
                "report_date": report_date,
                "events": events,
                "degraded_reason": "" if events else "no_matched_daily_report_event",
            }
        except Exception as exc:
            return {"available": False, "tool": "daily_report_tool", "events": [], "degraded_reason": str(exc)}

    def market_indicator_tool(self, slots: dict[str, Any]) -> dict[str, Any]:
        city = str(slots.get("city") or "全国")
        brand = slots.get("brand")
        series = slots.get("series")
        brand_group = [str(item) for item in (slots.get("brand_group") or []) if str(item).strip()]
        allowed_brands = {normalize_text(item) for item in brand_group}
        series_mentions = [item for item in (slots.get("series_mentions") or []) if item]
        target = str(slots.get("selection_target") or "")
        has_snapshot_subject = bool(
            slots.get("contextual_rank_item")
            or slots.get("contextual_series_items")
        )
        explain_against_full_scope = target in {"selection_reason", "rank_lookup"} or (
            target in {"score_explanation", "series_judgement", "evidence_answer"}
            and has_snapshot_subject
        )
        filter_brand = None if explain_against_full_scope else brand
        filter_series = None if explain_against_full_scope else series
        use_national = city in {"", "全国", "全网"}
        notes: list[str] = []
        model_year_universe = self.loader.model_year_records
        if allowed_brands:
            model_year_universe = [
                row for row in model_year_universe
                if normalize_text(row.get("brand")) in allowed_brands
            ]
        national_cohort = (
            _with_market_evidence_scope(model_year_universe, "national", "全国")
            if use_national
            else _aggregate_market_rows_by_series(
                model_year_universe,
                scope="national_prior",
                requested_city=city,
            )
        )
        if target == "compare_series" and series_mentions:
            rows = []
            if use_national:
                cohort_rows = national_cohort
                data_scope = "全国多车系对比口径"
                source_sheet = "无需打标：车型+年款详情数据"
            else:
                city_cohort = _with_market_evidence_scope(self.loader.filter_city_series(city=city), "city", city)
                cohort_rows = _merge_market_series_rows(city_cohort, national_cohort)
                data_scope = "城市实证+全国车系先验多车系对比口径"
                source_sheet = "无需打标：车系+城市详情数据"
            for mentioned_series in series_mentions:
                national_source = self.loader.filter_model_year(series=mentioned_series)
                national_matched = (
                    _with_market_evidence_scope(national_source, "national", "全国")
                    if use_national
                    else _aggregate_market_rows_by_series(
                        national_source,
                        scope="national_prior",
                        requested_city=city,
                    )
                )
                local_matched = [] if use_national else _with_market_evidence_scope(
                    self.loader.filter_city_series(city=city, series=mentioned_series), "city", city
                )
                matched = national_matched if use_national else _merge_market_series_rows(local_matched, national_matched)
                if not local_matched and national_matched and not use_national:
                    notes.append(f"{mentioned_series}在{city}城市行情未命中，已用全国车系聚合行情作先验补足。")
                rows.extend(matched)
            rows = _merge_market_series_rows([], rows)
            notes.append(f"已按{len(series_mentions)}个车系分别召回，避免用第一个品牌过滤其它车系。")
        elif use_national:
            national_source = self.loader.filter_model_year(brand=filter_brand, series=filter_series)
            if allowed_brands:
                national_source = [
                    row for row in national_source
                    if normalize_text(row.get("brand")) in allowed_brands
                ]
            rows = _with_market_evidence_scope(national_source, "national", "全国")
            cohort_rows = national_cohort
            data_scope = "全国车型+年款口径"
            source_sheet = "无需打标：车型+年款详情数据"
        else:
            city_rows = _with_market_evidence_scope(
                self.loader.filter_city_series(city=city, brand=filter_brand, series=filter_series), "city", city
            )
            national_rows = _aggregate_market_rows_by_series(
                self.loader.filter_model_year(brand=filter_brand, series=filter_series),
                scope="national_prior",
                requested_city=city,
            )
            rows = _merge_market_series_rows(city_rows, national_rows)
            city_cohort = _with_market_evidence_scope(self.loader.filter_city_series(city=city), "city", city)
            cohort_rows = _merge_market_series_rows(city_cohort, national_cohort)
            data_scope = "城市实证+全国车系先验候选口径"
            source_sheet = "无需打标：车系+城市详情数据"
            prior_count = sum(row.get("market_evidence_scope") == "national_prior" for row in rows)
            if prior_count:
                notes.append(f"城市行情覆盖不足，补入{prior_count}个全国车系聚合候选；全国行情只作先验，不冒充{city}本地证据。")
        if not rows and not (brand or series):
            rows = cohort_rows
        if brand_group:
            before = len(rows)
            rows = [row for row in rows if normalize_text(row.get("brand")) in allowed_brands]
            cohort_rows = [row for row in cohort_rows if normalize_text(row.get("brand")) in allowed_brands]
            notes.append(f"已按品牌组{'/'.join(brand_group)}筛选，{before}条 -> {len(rows)}条。")
        low = slots.get("price_low_yuan")
        high = slots.get("price_high_yuan")
        if low is not None or high is not None:
            before = len(rows)
            label = slots.get("price_band", {}).get("label") or "价格带"
            scoped_source = self.loader.filter_model_year(brand=filter_brand, series=filter_series)
            if allowed_brands:
                scoped_source = [
                    row for row in scoped_source
                    if normalize_text(row.get("brand")) in allowed_brands
                ]
            price_scope_builder = _price_scoped_national_model_year_rows if use_national else _price_scoped_market_rows
            scoped_rows = price_scope_builder(
                scoped_source,
                low=low,
                high=high,
                scope="national" if use_national else "national_prior",
                requested_city=city,
            )
            scoped_cohort = price_scope_builder(
                model_year_universe,
                low=low,
                high=high,
                scope="national" if use_national else "national_prior",
                requested_city=city,
            )
            if scoped_rows:
                rows = scoped_rows if use_national else _apply_price_scope_to_city_rows(rows, scoped_rows)
                cohort_rows = scoped_cohort if use_national else _apply_price_scope_to_city_rows(cohort_rows, scoped_cohort)
                data_scope = "全国车型+年款价格带实证" if use_national else "城市经营实证+全国车型年款价格带先验"
                source_sheet = "无需打标：车型+年款详情数据"
                notes.append(
                    f"已先在车型+年款层按{label}筛选，再聚合到车系，{before}条 -> {len(rows)}条；"
                    "只把实际命中该价格带的年款纳入价格证据。"
                )
            else:
                rows = []
                cohort_rows = []
                notes.append(f"{city}{label}未命中有90天成交价格证据的车型年款，返回空榜单，不回退到其它价格带。")
        # Energy/body/brand-class controls are presentation filters over one
        # deterministic city ranking. They must not rebuild the comparison
        # baseline, otherwise the same vehicle receives a different score
        # merely because the user switches a filter and a top-ranked Tesla can
        # disappear from the new-energy view. Keep the pre-filter cohort for
        # percentile scoring and business baselines, then project the ranked
        # universe to the requested category.
        scoring_cohort_rows = list(cohort_rows)
        fuel_type = str(slots.get("fuel_type") or "")
        if fuel_type:
            before = len(rows)
            filtered_rows = self._filter_rows_by_energy(rows, fuel_type, city=city)
            filtered_cohort = self._filter_rows_by_energy(cohort_rows, fuel_type, city=city)
            if filtered_rows:
                rows = filtered_rows
                if filtered_cohort:
                    cohort_rows = filtered_cohort
                notes.append(f"已用DCD taxonomy + 90天内部能源字段按{fuel_type}过滤，{before}条 -> {len(rows)}条。")
            else:
                rows = []
                cohort_rows = filtered_cohort
                notes.append(f"{city}{fuel_type}口径暂无可安全推荐候选，已返回空榜单而不是回退全量。")
        energy_subtype = normalize_energy_subtype(slots.get("energy_subtype"))
        if energy_subtype and energy_subtype not in {"新能源", "燃油"}:
            before = len(rows)
            rows = self._filter_rows_by_energy_subtype(rows, energy_subtype)
            cohort_rows = self._filter_rows_by_energy_subtype(cohort_rows, energy_subtype)
            notes.append(f"已按懂车帝能源细分证据筛选{energy_subtype}，{before}条 -> {len(rows)}条；未命中时不回退粗分类。")
        selection_filter = normalize_selection_filter(slots.get("selection_filter"))
        if selection_filter and selection_filter not in {"全部", "新能源"}:
            before = len(rows)
            filtered_rows = self._filter_rows_by_selection_filter(rows, selection_filter)
            filtered_cohort = self._filter_rows_by_selection_filter(cohort_rows, selection_filter)
            if filtered_rows:
                rows = filtered_rows
                if filtered_cohort:
                    cohort_rows = filtered_cohort
                notes.append(f"已按{selection_filter}榜单口径重算候选和cohort，{before}条 -> {len(rows)}条。")
            else:
                rows = []
                cohort_rows = filtered_cohort
                notes.append(f"{city}{selection_filter}榜单口径暂无可安全推荐候选，已返回空榜单而不是回退全量。")
        body_category = normalize_vehicle_category(slots.get("body_category"))
        # ``轿车 / SUV / MPV`` are the canonical body filters.  The previous
        # condition accidentally skipped exactly those three values and only
        # tried to filter unknown values, so an “新能源 SUV” result could mix
        # Model 3 and other sedans into the list.  “全部” is the only
        # presentation value that must leave the cohort untouched.
        if body_category and body_category not in {"全部", "总计"}:
            before = len(rows)
            rows = self._filter_rows_by_body_category(rows, body_category)
            cohort_rows = self._filter_rows_by_body_category(cohort_rows, body_category)
            notes.append(f"已按车型分类证据筛选{body_category}，{before}条 -> {len(rows)}条；未命中时不回退乘用车榜单。")
        brand_tier = normalize_brand_tier(slots.get("brand_tier"))
        if brand_tier:
            before = len(rows)
            rows = [row for row in rows if matches_brand_tier(row.get("brand"), brand_tier)]
            cohort_rows = [row for row in cohort_rows if matches_brand_tier(row.get("brand"), brand_tier)]
            notes.append(f"已按{brand_tier}品牌层级重算候选和cohort，{before}条 -> {len(rows)}条。")
        manufacturer_attribute = normalize_manufacturer_attribute(slots.get("manufacturer_attribute"))
        if manufacturer_attribute:
            before = len(rows)
            rows = self._filter_rows_by_manufacturer_attribute(rows, manufacturer_attribute)
            cohort_rows = self._filter_rows_by_manufacturer_attribute(cohort_rows, manufacturer_attribute)
            notes.append(f"已按懂车帝产销属性筛选{manufacturer_attribute}，{before}条 -> {len(rows)}条。")
        history_baseline = self.history.baseline(
            city=city,
            energy_type="",
            selection_filter="全部",
            brand_tier="",
            price_band=slots.get("price_band"),
        )
        national_history_baseline = history_baseline if city == "全国" else self.history.baseline(
            city="全国",
            energy_type="",
            selection_filter="全部",
            brand_tier="",
            price_band=slots.get("price_band"),
        )
        return {
            "tool": "market_indicator_tool",
            "city": city,
            "rows": rows,
            "cohort_rows": cohort_rows,
            "scoring_cohort_rows": scoring_cohort_rows,
            "data_scope": data_scope,
            "source_sheet": source_sheet,
            "notes": notes,
            "history_baseline": history_baseline,
            "national_history_baseline": national_history_baseline,
            "selection_filter": selection_filter,
            "brand_tier": brand_tier,
            "manufacturer_attribute": manufacturer_attribute,
            "energy_subtype": energy_subtype,
            "body_category": body_category,
        }

    def market_state_tool(self, indicators: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
        rows = list(indicators.get("rows") or [])
        cohort_rows = list(indicators.get("cohort_rows") or rows)
        scoring_cohort_rows = list(indicators.get("scoring_cohort_rows") or cohort_rows)
        stats = _stats(
            scoring_cohort_rows,
            (
                "deal_sample_90d",
                "detail_uv",
                "favorite_count",
                "inventory_cycle",
                "sell_through_rate",
                "avg_deal_cycle",
                "price_volatility",
                "price_change_30d",
                "listing_count",
            ),
        )
        ranking_requests: list[dict[str, Any]] = []
        for row in rows:
            taxonomy = self.taxonomy.classify_series(
                brand=row.get("brand"), series=row.get("series"), model=row.get("model")
            )
            ranking_requests.append(
                {
                    "city": None if str(slots.get("city") or "") in {"", "全国", "全网"} else slots.get("city"),
                    "brand": row.get("brand"),
                    "series": row.get("series"),
                    "vehicle_category": taxonomy.get("body_type"),
                    "energy_type": taxonomy.get("energy_type"),
                    "price_band": (slots.get("price_band") or {}).get("label"),
                }
            )
        try:
            from .ranking_signal_service import get_ranking_signal_service

            ranking_signals = get_ranking_signal_service().selection_signal_scores_bulk(ranking_requests)
        except Exception:
            ranking_signals = [{} for _ in rows]
        enriched = []
        for index, row in enumerate(rows):
            payload = dict(row)
            payload["_ranking_selection_signal"] = ranking_signals[index] if index < len(ranking_signals) else {}
            enriched.append(self._score_row(payload, stats, slots, indicators))
        return {
            "tool": "market_state_tool",
            "rows": enriched,
            "stats": stats,
            "cohort_size": len(cohort_rows),
            "scoring_cohort_size": len(scoring_cohort_rows),
        }

    def selection_strategy_tool(self, market_state: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
        rows = list(market_state.get("rows") or [])
        target = slots.get("selection_target")
        if target in {"risk_series", "risk"}:
            rows.sort(
                key=lambda row: (
                    row.get("selection_level") not in {"AVOID", "CAUTION"},
                    not row.get("profit_frontier_avoid"),
                    -(row.get("avoid_policy_score") or 0),
                    row.get("risk_score") or 100,
                    -(row.get("final_opportunity_score") or 0),
                )
            )
        elif target == "compare_series":
            mentions = {normalize_text(item) for item in (slots.get("series_mentions") or [])}
            rows = [row for row in rows if normalize_text(row.get("series")) in mentions] or rows
            rows.sort(key=_recommend_sort_key)
        elif target == "price_band_opportunity":
            rows.sort(
                key=lambda row: (
                    not row.get("business_recommend"),
                    row.get("selection_level") in {"AVOID"},
                    -(row.get("price_band_fit_score") or 0),
                    -(row.get("value_score") or 0),
                    -(row.get("final_opportunity_score") or 0),
                )
            )
        else:
            rows.sort(key=_recommend_sort_key)
        recommendation_rows = _dedupe_strategy_rows(rows)
        visible_recommend_keys = {
            _strategy_row_key(item) for item in recommendation_rows[:30]
        } if target not in {"risk_series", "risk"} else set()
        risk_source_rows = [
            item for item in rows
            if not item.get("business_recommend")
            and _strategy_row_key(item) not in visible_recommend_keys
        ]
        risk_rows = _dedupe_strategy_rows(
            sorted(
                risk_source_rows,
                key=lambda item: (
                    not item.get("business_avoid"),
                    not item.get("profit_frontier_avoid"),
                    -(item.get("avoid_policy_score") or 0),
                    item.get("risk_score") or 100,
                    -(item.get("final_opportunity_score") or 0),
                ),
            )
        )
        subject_lookup = _build_subject_lookup(slots, recommendation_rows, risk_rows)
        # Keep the complete deterministic ranking for conversational follow-ups.
        # The UI still renders compact slices, while session state can answer
        # any concrete-series/rank question without recomputing another list.
        full_recommendations = [
            self._public_item(row, rank=index + 1, city=slots.get("city"))
            for index, row in enumerate(recommendation_rows)
        ]
        # Leadership's product-selection baseline is the deterministic
        # Market-state + DSI pool (12,148 / 30,246 vehicles, 40.16%).  The
        # operating score below only orders follow-up work inside this pool;
        # it must not remove rows from the downloadable qualification pool.
        selection_policy = self.score_config.get("selection_policy") or {}
        qualification_policy = selection_policy.get("leadership_qualification_baseline") or {}
        allowed_market_categories = set(
            qualification_policy.get("allowed_market_categories")
            or ["流动行情", "结构性行情", "上涨行情", "常规行情"]
        )
        allowed_dsi_labels = set(
            qualification_policy.get("allowed_dsi_labels")
            or ["供不应求", "供需平衡"]
        )
        full_qualification_items: list[dict[str, Any]] = []
        for row, public_item in zip(recommendation_rows, full_recommendations):
            market_category = str(row.get("market_category") or "").strip()
            dsi_label = str((row.get("dsi_signal") or {}).get("label") or "").strip()
            if market_category not in allowed_market_categories or dsi_label not in allowed_dsi_labels:
                continue
            # This list is transported to the Excel endpoint, so keep only
            # the public fields the projection sheet actually consumes.  A
            # full public item is ~6KB; multiplying that by every nationwide
            # model-year row makes the interactive response unnecessarily
            # heavy without adding any report evidence.
            item = {
                "rank": len(full_qualification_items) + 1,
                "city": public_item.get("city"),
                "brand": public_item.get("brand"),
                "series": public_item.get("series"),
                "model_year": public_item.get("model_year"),
                "energy_type": public_item.get("energy_type"),
                "body_type": public_item.get("body_type"),
                "market_category": market_category,
                "market_category_label": market_category,
                "dsi_signal": {"label": dsi_label},
                "final_opportunity_score": public_item.get("final_opportunity_score"),
                "qualification_pool": "leadership_market_dsi_40pct_20260714",
                "qualification_status": "入选40%底池",
                "qualification_reason": f"行情{market_category} + DSI{dsi_label}",
                "active_followup_recommend": bool(public_item.get("business_recommend")),
            }
            full_qualification_items.append(item)
        full_risk_items = [
            self._public_item(row, rank=index + 1, city=slots.get("city"))
            for index, row in enumerate(risk_rows)
        ]
        full_strict_recommendations = [item for item in full_recommendations if item.get("business_recommend")]
        full_strict_avoid_items = [item for item in full_risk_items if item.get("business_avoid")]
        recommendations = full_recommendations[:30]
        risk_items = full_risk_items[:15]
        recommend_gate = (self.score_config.get("label_gate") or {}).get("recommend") or {}
        recommend_business_threshold = float(recommend_gate.get("min_business_score", 66))
        insufficient_gate = (self.score_config.get("label_gate") or {}).get("insufficient") or {}
        sample_min_sold = max(
            int(recommend_gate.get("min_sold_count", 10)),
            int(insufficient_gate.get("max_sold_count", -1)) + 1,
        )
        after_sample_gate = [row for row in recommendation_rows if row.get("business_recommend")]
        excluded_low_sample = [
            row for row in recommendation_rows
            if not row.get("business_recommend")
            if (row.get("business_score") or 0) >= recommend_business_threshold
            and row.get("profit_frontier_eligible") is True
            and any("有效经营证据不足" in str(reason) for reason in (row.get("gate_reasons") or []))
        ]
        return {
            "tool": "selection_strategy_tool",
            "recommendations": recommendations,
            "risk_items": risk_items,
            # The visible business lists are sliced from the complete strict
            # pools.  Otherwise a qualified row outside the generic preview
            # window can incorrectly make a narrow filter look empty.
            "strict_recommendations": full_strict_recommendations[:30],
            "strict_avoid_items": full_strict_avoid_items[:15],
            "session_ranking_snapshot": {
                "all_ranked_candidates": full_recommendations,
                "all_qualification_items": full_qualification_items,
                "all_avoid_items": full_risk_items,
                "candidate_count": len(full_recommendations),
                "qualification_count": len(full_qualification_items),
                "avoid_count": len(full_risk_items),
            },
            "comparison": _build_comparison(recommendations) if slots.get("selection_target") == "compare_series" else [],
            "price_band_summary": _price_band_summary(recommendations, slots),
            "subject_lookup": subject_lookup,
            "selection_audit": {
                "ranking_grain": "全国车系×年款" if str(slots.get("city") or "全国") in {"全国", "全网", ""} else f"{slots.get('city')}×车系",
                "ranking_grain_rule": "全国榜同车系同年款只保留经营得分最高的代表配置；城市榜同城市同车系只保留一条。",
                "qualification_pool_snapshot": qualification_policy.get("snapshot_date") or "2026-07-14",
                "qualification_pool_rule": qualification_policy.get("rule_description") or "行情状态四类且DSI为供不应求或供需平衡",
                "baseline_unique_vehicle_count": int(qualification_policy.get("baseline_unique_vehicle_count") or 30246),
                "qualified_unique_vehicle_count": int(qualification_policy.get("qualified_unique_vehicle_count") or 12148),
                "qualification_rate": float(qualification_policy.get("qualification_rate") or (12148 / 30246)),
                "qualification_rate_display": "40.16%",
                "qualification_projection_count": len(full_qualification_items),
                "operating_metrics_role": "90天经营结果只用于验证和池内跟进排序，不反向筛除40%准入底池。",
                "active_followup_target_rate": float(selection_policy.get("active_followup_target_rate") or 0.21),
                "active_followup_is_ordering_only": True,
                "candidate_group_count": len(rows),
                "selected_count_before_sample_gate": len(after_sample_gate) + len(excluded_low_sample),
                "selected_count_after_sample_gate": len(after_sample_gate),
                "excluded_due_to_low_sample_count": len(excluded_low_sample),
                "low_sample_candidate_count": len([row for row in recommendation_rows if int(_num(row.get("sold_count_90d"))) < sample_min_sold]),
                "sample_min_sold_count": sample_min_sold,
            },
            "score_policy": {
                "version": self.score_config.get("selection_score_version"),
                "parameter_set_id": self.score_config.get("parameter_set_id"),
                "parameter_set_score": self.score_config.get("parameter_set_score"),
                "selection_policy": self.score_config.get("selection_policy") or {},
                "conflict_resolution": "recommend_first_then_risk_from_complement",
            },
        }

    def response_composer(
        self,
        text: str,
        slots: dict[str, Any],
        daily_report: dict[str, Any],
        indicators: dict[str, Any],
        market_state: dict[str, Any],
        strategy: dict[str, Any],
    ) -> dict[str, Any]:
        city = slots.get("city") or "全国"
        recommendations = strategy.get("recommendations") or []
        risk_items = strategy.get("risk_items") or []
        strict_recommendations = strategy.get("strict_recommendations") or []
        strict_avoid_items = strategy.get("strict_avoid_items") or []
        subject_lookup = strategy.get("subject_lookup") or {}
        top = recommendations[0] if recommendations else {}
        selection_explanation = _selection_explanation(
            slots,
            recommendations,
            strict_recommendations,
            risk_items,
            subject_lookup=subject_lookup,
        )
        state_id = "sel_" + hashlib.sha1(f"{city}|{text}".encode("utf-8")).hexdigest()[:12]
        target_label = _target_label(slots.get("selection_target"))
        headline = _headline(
            city,
            target_label,
            slots.get("selection_target"),
            top,
            strict_recommendations,
            strict_avoid_items,
            subject_lookup=subject_lookup,
        )
        if slots.get("selection_target") == "selection_reason" and selection_explanation.get("headline"):
            headline = str(selection_explanation.get("headline"))
        answer_mode = _selection_answer_mode(slots)
        direct_answer = _selection_direct_answer(
            answer_mode=answer_mode,
            headline=headline,
            slots=slots,
            selection_explanation=selection_explanation,
            recommendations=recommendations,
            risk_items=risk_items,
            strategy=strategy,
            indicators=indicators,
            daily_report=daily_report,
        )
        if direct_answer.get("title"):
            headline = str(direct_answer.get("title"))
        report_date = daily_report.get("report_date")
        matched_count = len(indicators.get("rows") or [])
        comparable_count = len(indicators.get("cohort_rows") or [])
        task_execution = _build_selection_task_execution(
            answer_mode=answer_mode,
            city=city,
            headline=headline,
            direct_answer=direct_answer,
            selection_explanation=selection_explanation,
            recommendations=recommendations,
            risk_items=risk_items,
            indicators=indicators,
            daily_report=daily_report,
            matched_count=matched_count,
            comparable_count=comparable_count,
            report_date=report_date,
        )
        card = {
            "card_type": "selection_strategy_agent",
            "state_id": state_id,
            "city": city,
            "query_text": text,
            "answer_mode": answer_mode,
            "direct_answer": direct_answer,
            "scope": {
                "city": city,
                "price_band": slots.get("price_band"),
                "brand": slots.get("brand"),
                "series": slots.get("series"),
                "brand_tier": slots.get("brand_tier") or "全部",
                "manufacturer_attribute": slots.get("manufacturer_attribute") or "全部",
                "brand_group": slots.get("brand_group") or [],
                "energy_filter": slots.get("fuel_type") or "全部",
                "energy_subtype": slots.get("energy_subtype") or "全部",
                "body_filter": slots.get("selection_filter") or "全部",
                "body_category": slots.get("body_category") or slots.get("selection_filter") or "全部",
                "selection_filter": slots.get("selection_filter"),
                "fuel_type": slots.get("fuel_type"),
                "vehicle_type": slots.get("vehicle_type"),
                "time_window": slots.get("time_window"),
                "selection_target": slots.get("selection_target"),
                "data_scope": indicators.get("data_scope"),
            },
            "task_card": {
                "task_goal": "在指定城市、价格带、品牌或能源范围内，筛选值得收、谨慎收、不建议收的车系",
                "input_slots": {
                    "city": city,
                    "price_band": slots.get("price_band"),
                    "brand": slots.get("brand"),
                    "series": slots.get("series"),
                    "brand_tier": slots.get("brand_tier") or "全部",
                    "manufacturer_attribute": slots.get("manufacturer_attribute") or "全部",
                    "brand_group": slots.get("brand_group") or [],
                    "energy_filter": slots.get("fuel_type") or "全部",
                    "energy_subtype": slots.get("energy_subtype") or "全部",
                    "body_filter": slots.get("selection_filter") or "全部",
                    "body_category": slots.get("body_category") or slots.get("selection_filter") or "全部",
                    "selection_filter": slots.get("selection_filter"),
                    "fuel_type": slots.get("fuel_type"),
                    "time_window": slots.get("time_window"),
                    "selection_target": slots.get("selection_target"),
                },
                "execution_tools": [
                    "daily_report_tool",
                    "market_indicator_tool",
                    "market_state_tool",
                    "selection_strategy_tool",
                    "response_composer",
                ],
                "confirm_actions": [
                    {"action": "start_single_vehicle_pricing", "label": "进入单车定价任务"},
                    {"action": "export_selection_report", "label": "导出选品报告"},
                ],
            },
            "task_plan": {
                "goal": f"{city}{target_label}",
                "understanding": _understanding(slots),
                "steps": [item["name"] for item in task_execution],
            },
            "task_execution": task_execution,
            "recommendations": recommendations[:30],
            "risk_items": risk_items[:15],
            "strict_recommendations": strict_recommendations[:30],
            "strict_avoid_items": strict_avoid_items[:15],
            # The screen deliberately stays compact, but Excel exports need
            # the complete, strictly classified business pools.  These are
            # public decision rows (not the private conversational snapshot),
            # and never mix WATCH rows into either business action.
            "export_recommendations": [
                item
                for item in (strategy.get("session_ranking_snapshot") or {}).get("all_ranked_candidates", [])
                if item.get("business_recommend")
            ],
            "export_qualification_items": list(
                (strategy.get("session_ranking_snapshot") or {}).get("all_qualification_items", [])
            ),
            "export_avoid_items": [
                item
                for item in (strategy.get("session_ranking_snapshot") or {}).get("all_avoid_items", [])
                if item.get("business_avoid")
            ],
            "selection_explanation": selection_explanation,
            "subject_lookup": subject_lookup,
            "comparison": strategy.get("comparison") or [],
            "price_band_summary": strategy.get("price_band_summary") or {},
            "selection_audit": strategy.get("selection_audit") or {},
            "score_policy": strategy.get("score_policy") or {},
            # Private transport field.  InteractionService moves it into
            # server-side session context and removes it from the UI payload.
            "_session_ranking_snapshot": strategy.get("session_ranking_snapshot") or {},
            "summary_report": {
                "headline": headline,
                "key_findings": _key_findings(
                    top,
                    recommendations,
                    risk_items,
                    slots=slots,
                    strict_recommendations=strict_recommendations,
                    selection_explanation=selection_explanation,
                ),
                "business_suggestions": _business_suggestions(top, slots),
                "risk_notes": list(dict.fromkeys(risk for item in recommendations[:5] for risk in item.get("risks", [])))[:6],
                "data_quality_notes": (indicators.get("notes") or []) + [
                    "40%准入底池只由行情四状态与DSI供需标签确定；近90天内部业务表现和排行榜证据仅用于回测验证与池内跟进排序。",
                    "建议收车价区间是车系级经营参考，不替代单车七要素定价。",
                ],
            },
            "tool_outputs": {
                "daily_report_tool": {k: v for k, v in daily_report.items() if k != "events"} | {"event_count": len(daily_report.get("events") or [])},
                "market_indicator_tool": {
                    "data_scope": indicators.get("data_scope"),
                    "source_sheet": indicators.get("source_sheet"),
                    "matched_rows": len(indicators.get("rows") or []),
                    "cohort_rows": len(indicators.get("cohort_rows") or []),
                    "history_baseline": indicators.get("history_baseline"),
                },
                "market_state_tool": {"cohort_size": market_state.get("cohort_size")},
                "selection_strategy_tool": {
                    "recommendation_count": len(recommendations),
                    "risk_count": len(risk_items),
                    "strict_recommendation_count": len(strict_recommendations),
                    "strict_avoid_count": len(strict_avoid_items),
                    "selection_audit": strategy.get("selection_audit") or {},
                    "score_policy": strategy.get("score_policy") or {},
                },
            },
            "data_source": {
                "source_file": self.loader.metadata.get("source_file"),
                "source_sheet": indicators.get("source_sheet"),
                "data_scope": indicators.get("data_scope"),
                "history_source": self.history.metadata,
                "dsi_source": "DSI供需指数_车款ID.xlsx",
                "online_safe": True,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}

    def _find_all_series(self, text: str, limit: int = 6) -> list[str]:
        normalized = normalize_text(text)
        matches = [
            series for series in self.loader.series_names
            if normalize_text(series) and normalize_text(series) in normalized
            and str(series).strip() not in GENERIC_SCOPE_SERIES
        ]
        selected: list[str] = []
        for series in matches:
            if any(normalize_text(series) in normalize_text(existing) for existing in selected):
                continue
            selected.append(series)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _is_generic_scope_series(value: Any) -> bool:
        return normalize_text(value) in GENERIC_SCOPE_SERIES_NORMALIZED

    @staticmethod
    def _is_cohort_selection_request(
        text: str,
        *,
        selection_task_intent: str = "",
        selection_detail_intent: str = "",
    ) -> bool:
        if selection_task_intent in {
            "recommend_models",
            "recommend_price_band",
            "recommend_city_opportunity",
            "identify_risky_models",
            "low_price_opportunity",
            "sort_filter_selection_result",
            "refine_selection_scope",
        }:
            return True
        if selection_detail_intent in {
            "selection.recommend_scope",
            "selection.risk_scope",
            "selection.sort_filter",
            "selection.followup_refine",
        }:
            return True
        if (
            (PRICE_RANGE_PATTERN.search(str(text or "")) or PRICE_UNDER_PATTERN.search(str(text or "")) or PRICE_ABOVE_PATTERN.search(str(text or "")))
            and re.search(r"机会|值得|推荐|适合|可收|哪些|什么", str(text or ""))
        ):
            return True
        return bool(
            re.search(
                r"哪些(?:车|车型|车系)|什么(?:车|车型|车系)|"
                r"(?:推荐|风险|避坑|暂缓|不要收).{0,6}(?:榜|榜单|清单|车系|车型)|"
                r"(?:车系|车型).{0,6}(?:推荐|风险|不要收|别碰)|top\s*\d+",
                str(text or ""),
                flags=re.I,
            )
        )

    @staticmethod
    def _has_vehicle_context_reference(text: str) -> bool:
        return bool(
            re.search(
                r"这车|这款车|这(?:台|辆)车|这个车|该车|它|"
                r"这个(?:机会分|评分|分数|排名|推荐结果)|该(?:机会分|评分|分数|排名)|"
                r"第\s*(?:\d+|[一二三四五六七八九十]+)(?:个|名|位)?|"
                r"上面(?:那个|那台|第\s*(?:\d+|[一二三四五六七八九十]+)个)|"
                r"刚才(?:那台|那个车|第\s*(?:\d+|[一二三四五六七八九十]+)个)",
                str(text or ""),
            )
        )

    def _extract_price_band(self, text: str) -> dict[str, Any]:
        match = PRICE_RANGE_PATTERN.search(text)
        if match:
            low = float(match.group(1)) * 10000
            high = float(match.group(2)) * 10000
            if low > high:
                low, high = high, low
            return {"label": f"{match.group(1)}-{match.group(2)}万", "low": low, "high": high}
        match = PRICE_UNDER_PATTERN.search(text)
        if match:
            high = float(match.group(1)) * 10000
            return {"label": f"{match.group(1)}万以内", "low": None, "high": high}
        match = PRICE_ABOVE_PATTERN.search(text)
        if match:
            low = float(match.group(1)) * 10000
            return {"label": f"{match.group(1)}万以上", "low": low, "high": None}
        # In selection language, “20万有什么机会” is a budget
        # constraint, not an unconstrained full-market query and not a request
        # to price one concrete vehicle.
        match = PRICE_BUDGET_OPPORTUNITY_PATTERN.search(text)
        if match and not re.search(r"这台|这辆|估价|报价|收车价|卖车价|挂牌价", text):
            high = float(match.group(1)) * 10000
            return {"label": f"{match.group(1)}万预算内", "low": None, "high": high}
        return {}

    def _extract_fuel_type(self, text: str, client_state: dict[str, Any] | None = None) -> str:
        client_state = client_state or {}
        for key in ("selectedEnergyType", "selected_energy_type", "energy_filter", "selectedFuelType", "selected_fuel_type"):
            value = _normalize_energy_filter(client_state.get(key))
            if value:
                return value
        legacy_category = str(
            client_state.get("selectedVehicleCategory")
            or client_state.get("selected_vehicle_category")
            or ""
        ).strip()
        legacy_energy = _normalize_energy_filter(legacy_category)
        if legacy_energy:
            return legacy_energy
        for label, keywords in FUEL_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return label
        return ""

    def _extract_selection_filter(self, text: str, client_state: dict[str, Any]) -> str:
        for key in ("selectedBodyType", "selected_body_type", "body_filter", "selectedSelectionFilter", "selection_filter", "selectedVehicleCategory", "selected_vehicle_category"):
            value = client_state.get(key)
            if value:
                normalized = normalize_selection_filter(value)
                if normalized in {"轿车", "SUV", "MPV"}:
                    return normalized
                if str(value).strip() in {"全部", "总计"}:
                    return "全部"
        for candidate in ("轿车", "SUV", "suv", "MPV", "mpv", "总计", "全部"):
            if candidate in text:
                return normalize_selection_filter(candidate)
        return "全部"

    def _extract_brand_tier(self, text: str, client_state: dict[str, Any]) -> str:
        for key in ("selectedBrandTier", "selected_brand_tier", "brand_tier", "selectedVehicleCategory", "selected_vehicle_category"):
            value = normalize_brand_tier(client_state.get(key))
            if value:
                return value
        return extract_brand_tier_from_text(text)

    def _filter_rows_by_energy(self, rows: list[dict[str, Any]], fuel_type: str, *, city: str) -> list[dict[str, Any]]:
        allowed = self.history.series_matching_energy(fuel_type, city=city)
        return [
            row for row in rows
            if normalize_text(row.get("series")) in allowed
            or self.taxonomy.matches_energy(
                brand=row.get("brand"),
                series=row.get("series"),
                model=row.get("model"),
                energy_type=fuel_type,
            )
        ]

    def _filter_rows_by_selection_filter(self, rows: list[dict[str, Any]], selection_filter: str) -> list[dict[str, Any]]:
        return [
            row for row in rows
            if self.taxonomy.matches_selection_filter(
                brand=row.get("brand"),
                series=row.get("series"),
                model=row.get("model"),
                selected_filter=selection_filter,
            )
        ]

    def _filter_rows_by_energy_subtype(self, rows: list[dict[str, Any]], energy_subtype: str) -> list[dict[str, Any]]:
        return [
            row for row in rows
            if self.taxonomy.matches_energy_subtype(
                brand=row.get("brand"),
                series=row.get("series"),
                model=row.get("model"),
                energy_subtype=energy_subtype,
            )
        ]

    def _filter_rows_by_body_category(self, rows: list[dict[str, Any]], body_category: str) -> list[dict[str, Any]]:
        return [
            row for row in rows
            if self.taxonomy.matches_vehicle_category(
                brand=row.get("brand"),
                series=row.get("series"),
                model=row.get("model"),
                vehicle_category=body_category,
            )
        ]

    def _filter_rows_by_manufacturer_attribute(self, rows: list[dict[str, Any]], manufacturer_attribute: str) -> list[dict[str, Any]]:
        return [
            row for row in rows
            if self.taxonomy.matches_manufacturer_attribute(
                brand=row.get("brand"),
                series=row.get("series"),
                model=row.get("model"),
                manufacturer_attribute=manufacturer_attribute,
            )
        ]

    def _extract_time_window(self, text: str) -> str:
        match = TIME_WINDOW_PATTERN.search(text)
        return f"{match.group(1)}天" if match else "90天"

    def _selection_target(
        self,
        text: str,
        series_mentions: list[str],
        price_band: dict[str, Any],
        *,
        selection_task_intent: str = "",
    ) -> str:
        if any(keyword in text for keyword in COMPARE_KEYWORDS) and len(series_mentions) >= 2:
            return "compare_series"
        if selection_task_intent == "explain_selection_score":
            return "score_explanation"
        if selection_task_intent == "explain_signal_rule" or (
            not selection_task_intent
            and (
                re.search(
                    r"(?:风险|避免|推荐|排名|排序).{0,32}(?:怎么算|如何计算|计算逻辑|公式|权重|占比)",
                    text,
                )
                or (
                    re.search(r"权重|占比|怎么参与|如何参与|为什么这么定|为何这么定|有什么区别|口径", text)
                    and re.search(r"收车转化|售车转化|成熟(?:库存|上架)|利润质量|排行榜|排序|选品", text)
                )
            )
        ):
            return "method_explanation"
        # “避免收/别碰/暂缓” is a list-direction instruction, not a generic
        # recommendation request.  Resolve it before the broad semantic
        # family classifier so a risk query can never be routed to the
        # recommendation list merely because it also contains “收车”。
        if any(keyword in text for keyword in RISK_KEYWORDS):
            return "risk_series"
        semantic_family = classify_selection_query_family(text, has_vehicle_entity=bool(series_mentions) or bool(self.loader.find_brand_in_text(text)))
        if semantic_family == "rank_lookup":
            return "rank_lookup"
        if semantic_family == "explain_exclusion":
            return "selection_reason"
        if semantic_family == "series_judgement":
            return "series_judgement"
        if semantic_family == "score_explanation":
            return "score_explanation"
        if semantic_family == "method_explanation":
            return "method_explanation"
        if semantic_family == "evidence_request":
            return "evidence_answer"
        if semantic_family == "compare":
            return "compare_series"
        if semantic_family == "recommend_scope":
            return "price_band_opportunity" if price_band else "recommend_series"
        if semantic_family == "city_opportunity":
            return "price_band_opportunity" if price_band else "recommend_series"
        if any(keyword in text for keyword in PRICING_HANDOFF_KEYWORDS):
            return "selection_to_pricing"
        if price_band and (
            any(keyword in text for keyword in PRICE_BAND_KEYWORDS)
            or re.search(r"机会|值得|推荐|适合|可收|哪些|什么", text)
            or selection_task_intent in {"recommend_price_band", "low_price_opportunity"}
        ):
            return "price_band_opportunity"
        inferred = "series_judgement" if series_mentions else "recommend_series"
        task_target = SELECTION_TASK_TARGETS.get(selection_task_intent)
        return task_target or inferred

    def _score_row(
        self,
        row: dict[str, Any],
        stats: dict[str, dict[str, Any]],
        slots: dict[str, Any],
        indicators: dict[str, Any],
    ) -> dict[str, Any]:
        config = self.score_config
        policy = config.get("selection_policy") or {}
        three_layer_policy = policy.get("strategy_mode") == "three_layer"
        dsi = self.loader.dsi_for_series(row.get("series"))
        history = self.history.metrics_for(city=slots.get("city"), brand=row.get("brand"), series=row.get("series"))
        national_series_history = self.history.metrics_for(
            city="全国",
            brand=row.get("brand"),
            series=row.get("series"),
        )
        history_scope = str(history.get("history_scope") or "missing")
        uses_national_fallback = history_scope == "national_fallback"
        baseline = (
            indicators.get("national_history_baseline")
            if uses_national_fallback
            else indicators.get("history_baseline")
        ) or {}
        evidence_sold_count = _num(history.get("sold_count_90d"), 0)
        evidence_acquired_count = _num(history.get("acquired_count_90d"), 0)
        evidence_listed_count = _num(history.get("listed_count_90d"), 0)
        # National series data is a useful prior for a sparse city, but it is
        # never allowed to masquerade as local support for a hard recommendation.
        sold_count = evidence_sold_count if three_layer_policy else 0.0 if uses_national_fallback else evidence_sold_count
        acquired_count = evidence_acquired_count if three_layer_policy else 0.0 if uses_national_fallback else evidence_acquired_count
        listed_count = evidence_listed_count if three_layer_policy else 0.0 if uses_national_fallback else evidence_listed_count
        candidate_count = max(acquired_count, listed_count, _num(row.get("listing_count"), 0), _num(row.get("deal_sample_90d"), 0))
        national_baseline = indicators.get("national_history_baseline") or baseline
        if history_scope == "city" and national_series_history:
            smoothed_history = smooth_business_metrics_hierarchical(
                history,
                national_series_history,
                national_baseline,
                config=config,
            )
        else:
            smoothed_history = smooth_business_metrics(history, baseline, config=config)
        metric_ratios = _history_metric_ratios(smoothed_history, baseline)
        leader_recommend_raw = sold_count >= 1 and _business_recommend_flag(metric_ratios)
        leader_avoid_raw = sold_count >= 1 and _business_avoid_flag(metric_ratios)
        leader_pass_count = _leader_metric_pass_count(metric_ratios, mode="recommend")
        sample_confidence = calculate_sample_confidence(
            candidate_count=candidate_count,
            acquired_count=acquired_count,
            sold_count=sold_count,
            data_coverage=_data_coverage(row, history),
            config=config,
        )
        demand_score = max(
            _rank(stats["deal_sample_90d"]["values"], row.get("deal_sample_90d")),
            _rank(stats["detail_uv"]["values"], row.get("detail_uv")),
            _rank(stats["favorite_count"]["values"], row.get("favorite_count")),
        ) * 100
        supply_score = (
            0.45 * _rank(stats["inventory_cycle"]["values"], row.get("inventory_cycle"), reverse=True)
            + 0.35 * _rank(stats["sell_through_rate"]["values"], row.get("sell_through_rate"))
            + 0.20 * _rank(stats["listing_count"]["values"], row.get("listing_count"))
        ) * 100
        turnover_score = _rank(stats["avg_deal_cycle"]["values"], row.get("avg_deal_cycle"), reverse=True) * 100
        price_change = _num(row.get("price_change_30d"), 0)
        price_stability = (
            0.7 * _rank(stats["price_volatility"]["values"], row.get("price_volatility"), reverse=True)
            + 0.3 * (1.0 if -0.03 <= price_change <= 0.06 else 0.55 if price_change > 0.06 else 0.35)
        ) * 100
        metric_scores = _history_metric_scores(smoothed_history, baseline)
        value_score = _history_value_score(smoothed_history, baseline, metric_scores=metric_scores)
        risk_score = _history_risk_score(smoothed_history, baseline, row, metric_scores=metric_scores)
        market_evidence_scope = str(row.get("market_evidence_scope") or ("national" if slots.get("city") == "全国" else "city"))
        market_state_score = {
            "结构性行情": 80,
            "流动行情": 70,
            "上涨行情": 80,
            "常规行情": 45,
            "阴跌行情": 10,
            "急跌行情": 0,
        }.get(str(row.get("market_category") or ""), 45)
        if market_evidence_scope == "national_prior":
            market_state_score = 50 + (market_state_score - 50) * 0.5
        price_band_fit = _price_band_fit_score(row, slots)
        # Positive-only profit is retained for score contribution.  The
        # signed value is the auditable business fact exposed to users.
        total_profit = _history_total_profit(history)
        signed_total_profit = _history_signed_total_profit(history)
        baseline_total_profit = _history_total_profit(baseline)
        total_profit_contribution = total_profit / baseline_total_profit if baseline_total_profit > 0 else 0.0
        total_profit_score = _total_profit_score(total_profit_contribution)
        expected_profit_per_10_candidates = (
            10.0
            * _num(smoothed_history.get("acquisition_conversion_rate"), 0.0)
            * _num(smoothed_history.get("sold_from_acquired_rate"), 0.0)
            * _num(smoothed_history.get("median_gross_profit"), 0.0)
        )
        taxonomy = self.taxonomy.classify_series(brand=row.get("brand"), series=row.get("series"), model=row.get("model"))
        ranking_signal = row.get("_ranking_selection_signal") or _ranking_selection_signal(
            city=slots.get("city"),
            brand=row.get("brand"),
            series=row.get("series"),
            vehicle_category=taxonomy.get("body_type"),
            energy_type=taxonomy.get("energy_type"),
            price_band=(slots.get("price_band") or {}).get("label"),
        )
        selection_dsi_score = {
            "供不应求": 80.0,
            "供需平衡": 55.0,
            "供过于求": 50.0,
        }.get(str(dsi.get("label") or "未知"), 50.0)
        portfolio_policy = policy.get("portfolio_qualification") or {}
        national_series_sold_count = int(_num(national_series_history.get("sold_count_90d")))
        national_series_total_profit = _history_signed_total_profit(national_series_history)
        national_series_candidate_count = int(_num(national_series_history.get("candidate_count_90d")))
        national_series_loss_rate = finite_number(national_series_history.get("loss_rate"))
        national_series_profit_per_candidate = (
            national_series_total_profit / national_series_candidate_count
            if national_series_candidate_count > 0
            else 0.0
        )
        portfolio_min_sold_count = int(portfolio_policy.get("min_sold_count", 3))
        portfolio_observation_min_sold_count = int(portfolio_policy.get("observation_min_sold_count", 1))
        portfolio_max_loss_rate = float(portfolio_policy.get("max_loss_rate", 1.0))
        portfolio_min_profit_per_candidate = float(portfolio_policy.get("min_profit_per_candidate", 0.0))
        portfolio_supported = national_series_sold_count >= portfolio_min_sold_count
        portfolio_observation_supported = national_series_sold_count >= portfolio_observation_min_sold_count
        profit_frontier_observation = bool(
            portfolio_observation_supported
            and national_series_total_profit > 0
            and national_series_profit_per_candidate >= portfolio_min_profit_per_candidate
            and national_series_loss_rate is not None
            and national_series_loss_rate <= portfolio_max_loss_rate
        )
        profit_frontier_eligible = bool(
            portfolio_supported
            and national_series_total_profit > 0
            and national_series_profit_per_candidate >= portfolio_min_profit_per_candidate
            and national_series_loss_rate is not None
            and national_series_loss_rate <= portfolio_max_loss_rate
        )
        profit_frontier_avoid = bool(
            portfolio_supported
            and national_series_total_profit < 0
        )
        if profit_frontier_eligible:
            profit_frontier_status = "recommend_eligible"
        elif profit_frontier_observation:
            profit_frontier_status = "observation_only"
        elif profit_frontier_avoid:
            profit_frontier_status = "avoid_eligible"
        elif portfolio_supported:
            profit_frontier_status = "outside_profit_frontier"
        else:
            profit_frontier_status = "insufficient_series_evidence"
        acquisition_component_score = _relative_metric_score(
            smoothed_history.get("acquisition_conversion_rate"),
            baseline.get("acquisition_conversion_rate"),
            floor_abs=0.08,
        )
        sales_component_score = _relative_metric_score(
            smoothed_history.get("sale_conversion_rate"),
            baseline.get("sale_conversion_rate"),
            floor_abs=0.08,
        )
        # Nationwide ranking is model-year grain.  Series-level history is
        # still used for profitability and conversion qualification, but the
        # turnover component must use the current model-year (or current city
        # series row) rather than copying one series value onto every year.
        # This gives different years a real, visible ordering signal.
        turnover_component_score = turnover_score
        current_profit_per_candidate = (
            _history_signed_total_profit(history) / candidate_count if candidate_count > 0 else 0.0
        )
        baseline_candidate_count = max(1.0, _num(baseline.get("candidate_count_90d"), 0.0))
        baseline_profit_per_candidate = _history_signed_total_profit(baseline) / baseline_candidate_count
        average_profit_component_score = _relative_metric_score(
            smoothed_history.get("avg_gross_profit"),
            baseline.get("avg_gross_profit"),
            floor_abs=1000.0,
        )
        profit_per_candidate_component_score = _relative_metric_score(
            current_profit_per_candidate,
            baseline_profit_per_candidate,
            floor_abs=250.0,
        )
        profit_component_score = (average_profit_component_score + profit_per_candidate_component_score) / 2.0
        ranking_component_score = float(ranking_signal.get("score") or 50)
        if three_layer_policy:
            component_weights = policy.get("ranking_components") or {}
            component_values = {
                "acquisition": acquisition_component_score,
                "sales": sales_component_score,
                "turnover": turnover_component_score,
                "profit": profit_component_score,
                "ranking": ranking_component_score,
            }
            component_total = sum(max(0.0, _num(component_weights.get(key))) for key in component_values) or 1.0
            core_score = sum(
                value * max(0.0, _num(component_weights.get(key)))
                for key, value in component_values.items()
            ) / component_total
            # Market state and DSI are qualification gates in this policy.  We
            # expose their values for explanation, but never add them to the
            # ranking score a second time.
            external_full_signal_score = (
                market_state_score + selection_dsi_score
            ) / 2.0
            acquired_sell_through_guard_score = acquisition_component_score
            listed_sell_through_guard_score = sales_component_score
        elif policy.get("strategy_mode") == "outcome_guarded":
            component_weights = policy.get("external_components") or {}
            component_total = sum(max(0.0, _num(value)) for value in component_weights.values()) or 1.0
            external_full_signal_score = (
                market_state_score * max(0.0, _num(component_weights.get("market_state")))
                + 50.0 * max(0.0, _num(component_weights.get("policy_event")))
                + selection_dsi_score * max(0.0, _num(component_weights.get("dsi")))
                + float(ranking_signal.get("score") or 50) * max(0.0, _num(component_weights.get("ranking")))
            ) / component_total
            acquired_sell_through_guard_score = _relative_metric_score(
                smoothed_history.get("acquisition_conversion_rate"),
                baseline.get("acquisition_conversion_rate"),
                floor_abs=0.08,
            )
            listed_sell_through_guard_score = _relative_metric_score(
                smoothed_history.get("sale_conversion_rate"),
                baseline.get("sale_conversion_rate"),
                floor_abs=0.08,
            )
            external_weight = max(0.0, _num(policy.get("external_full_signal_weight"), 0.44))
            acquired_guard_weight = max(0.0, _num(policy.get("acquisition_conversion_guard_weight", policy.get("acquired_sell_through_guard_weight")), 0.44))
            listed_guard_weight = max(0.0, _num(policy.get("listed_sell_through_guard_weight"), 0.12))
            policy_weight_total = external_weight + acquired_guard_weight + listed_guard_weight or 1.0
            core_score = (
                external_full_signal_score * external_weight
                + acquired_sell_through_guard_score * acquired_guard_weight
                + listed_sell_through_guard_score * listed_guard_weight
            ) / policy_weight_total
        else:
            weights = _normalized_score_weights(config.get("score_weights_online") or {})
            core_score = (
                demand_score * weights.get("demand", 0)
                + supply_score * weights.get("supply", 0)
                + turnover_score * weights.get("turnover", 0)
                + price_stability * weights.get("price_stability", 0)
                + market_state_score * weights.get("market_state", 0)
                + float(dsi.get("score") or 50) * weights.get("dsi", 0)
                + value_score * weights.get("value", 0)
                + total_profit_score * weights.get("total_profit", 0)
            )
            external_full_signal_score = core_score
            acquired_sell_through_guard_score = _relative_metric_score(
                smoothed_history.get("acquisition_conversion_rate"),
                baseline.get("acquisition_conversion_rate"),
                floor_abs=0.08,
            )
            listed_sell_through_guard_score = _relative_metric_score(
                smoothed_history.get("sale_conversion_rate"),
                baseline.get("sale_conversion_rate"),
                floor_abs=0.08,
            )
        avoid_policy = policy.get("avoid_policy") or {}
        avoid_external_weight = max(0.0, _num(avoid_policy.get("external_risk_weight"), 0.80))
        avoid_acquired_weight = max(0.0, _num(avoid_policy.get("acquisition_conversion_risk_weight", avoid_policy.get("acquired_sell_through_risk_weight")), 0.15))
        avoid_listed_weight = max(0.0, _num(avoid_policy.get("listed_sell_through_risk_weight"), 0.05))
        avoid_weight_total = avoid_external_weight + avoid_acquired_weight + avoid_listed_weight or 1.0
        avoid_policy_score = (
            (100 - external_full_signal_score) * avoid_external_weight
            + (100 - acquired_sell_through_guard_score) * avoid_acquired_weight
            + (100 - listed_sell_through_guard_score) * avoid_listed_weight
        ) / avoid_weight_total
        if slots.get("price_band"):
            core_score = core_score * 0.88 + price_band_fit * 0.12
        # `market_category` is the single numerical representation of the
        # existing state machine. Its source indicators remain visible for
        # evidence, but are not counted a second time in the online score.
        business_score = core_score
        if not three_layer_policy:
            if leader_recommend_raw:
                business_score = max(business_score, 68)
            if leader_avoid_raw:
                business_score = min(business_score, 42)
            if sold_count < 1:
                business_score = min(business_score, 55)
            if not leader_recommend_raw:
                business_score = min(business_score, 64 + min(leader_pass_count, 3))
        business_score = max(0, min(100, round(business_score, 1)))
        confidence_score = float(sample_confidence.get("confidence_score") or 0)
        final_opportunity_score = (
            business_score
            if three_layer_policy
            else max(0, min(100, round(business_score * confidence_score, 1)))
        )
        if not three_layer_policy and not leader_recommend_raw:
            observation_cap = 42 + leader_pass_count * 4
            if sold_count >= 20 and acquired_count >= 30:
                observation_cap += 4
            final_opportunity_score = min(final_opportunity_score, observation_cap)
        gate_sold_count = sold_count
        gate_acquired_count = acquired_count
        gate_confidence_score = confidence_score
        if three_layer_policy and str(slots.get("city") or "全国") not in {"全国", "全网", ""}:
            # City ranking remains city+series.  When the local outcome sample
            # is sparse, national same-series outcomes may satisfy the basic
            # qualification layer, while the result is capped below "重点关注"
            # and explicitly labelled as a national prior in the evidence.
            gate_sold_count = max(gate_sold_count, float(national_series_sold_count))
            gate_acquired_count = max(gate_acquired_count, float(_num(national_series_history.get("acquired_count_90d"))))
            if national_series_sold_count >= portfolio_min_sold_count:
                gate_confidence_score = max(gate_confidence_score, 0.35)
        gate = apply_label_gate(
            final_opportunity_score=final_opportunity_score,
            business_score=business_score,
            confidence_score=gate_confidence_score,
            sold_count=gate_sold_count,
            acquired_count=gate_acquired_count,
            total_profit_contribution=total_profit_contribution,
            risk_score=risk_score,
            market_category=row.get("market_category"),
            dsi_label=dsi.get("label"),
            ratios=metric_ratios,
            sale_conversion_rate=smoothed_history.get("sale_conversion_rate"),
            acquisition_conversion_rate=smoothed_history.get("acquisition_conversion_rate"),
            sold_from_acquired_rate=smoothed_history.get("sold_from_acquired_rate"),
            listed_conversion_denominator=history.get("listed_conversion_denominator"),
            acquired_conversion_denominator=history.get("acquired_conversion_denominator"),
            loss_rate=smoothed_history.get("loss_rate"),
            median_gross_profit=smoothed_history.get("median_gross_profit"),
            sample_level=str(sample_confidence.get("sample_level") or ""),
            config=config,
        )
        if portfolio_policy.get("enabled", False):
            gate_reasons = list(gate.get("gate_reasons") or [])
            if profit_frontier_avoid and gate.get("selection_level") not in {"CAUTION", "AVOID"}:
                gate.update(
                    {
                        "selection_level": "AVOID",
                        "recommendation_level": "AVOID",
                        "recommendation_label": "暂缓收",
                        "business_recommend": False,
                        "business_avoid": True,
                    }
                )
                gate_reasons.insert(0, f"全国同车系90天净利润{national_series_total_profit:.0f}元，进入规避资格池")
            elif not profit_frontier_eligible and gate.get("selection_level") in {"STRONG_RECOMMEND", "RECOMMEND"}:
                gate.update(
                    {
                        "selection_level": "WATCH",
                        "recommendation_level": "WATCH",
                        "recommendation_label": "正常跟踪",
                        "business_recommend": False,
                        "business_avoid": False,
                    }
                )
                if portfolio_supported:
                    gate_reasons.insert(0, "全国同车系90天净利润未进入正利润前沿，不做主动推荐")
                else:
                    gate_reasons.insert(0, "全国同车系有效经营证据不足，不做主动推荐")
            gate["gate_reasons"] = list(dict.fromkeys(gate_reasons))[:8]
        if three_layer_policy and str(slots.get("city") or "全国") not in {"全国", "全网", ""}:
            if gate.get("selection_level") == "STRONG_RECOMMEND" and evidence_sold_count < 10:
                gate.update(
                    {
                        "selection_level": "RECOMMEND",
                        "recommendation_level": "RECOMMEND",
                        "recommendation_label": "可关注",
                        "business_recommend": True,
                        "business_avoid": False,
                    }
                )
                gate["gate_reasons"] = list(dict.fromkeys([
                    "城市本地样本不足以支持重点关注，按全国同车系经营资格降为可关注",
                    *(gate.get("gate_reasons") or []),
                ]))[:8]
        level = str(gate.get("selection_level") or "WATCH")
        label = str(gate.get("recommendation_label") or "正常跟踪")
        reasons, risks = _reason_risk(row, smoothed_history, dsi, stats)
        if total_profit_contribution > 0:
            reasons.append(f"90天总毛利贡献约{total_profit_contribution * 100:.1f}%")
        if sold_count < float((config.get("label_gate") or {}).get("recommend", {}).get("min_sold_count", 10)):
            risks.insert(0, str(sample_confidence.get("data_quality_note") or "有效经营证据不足，先观察不主动推荐"))
        if uses_national_fallback:
            risks.insert(0, "当前城市缺少同车系内部90天样本；全国数据仅作先验，不能据此给出城市强推荐")
        if market_evidence_scope == "national_prior":
            risks.append("当前城市行情表未覆盖该车系，行情状态来自全国90天车系聚合先验，已降权")
        purchase_range = _purchase_price_range(row, history, level)
        return {
            **row,
            "dsi_signal": dsi,
            "selection_dsi_score": round(selection_dsi_score, 1),
            "history_metrics": history,
            "smoothed_history_metrics": smoothed_history,
            "sample_confidence": sample_confidence,
            "demand_score": round(demand_score, 1),
            "supply_score": round(supply_score, 1),
            "turnover_score": round(turnover_score, 1),
            "market_state_score": round(market_state_score, 1),
            "market_evidence_scope": market_evidence_scope,
            "market_evidence_scope_display": row.get("market_evidence_scope_display") or "90天行情实证",
            "market_category_distribution": row.get("market_category_distribution") or {},
            "price_stability_score": round(price_stability, 1),
            "external_full_signal_score": round(external_full_signal_score, 1),
            "selection_layer_scores": {
                "qualification": {
                    "market_state": str(row.get("market_category") or "未知"),
                    "dsi": str(dsi.get("label") or "未知"),
                    "positive_total_profit": national_series_total_profit > 0,
                    "sold_support": national_series_sold_count,
                },
                "ranking": {
                    "acquisition": round(acquisition_component_score, 1),
                    "sales": round(sales_component_score, 1),
                    "turnover": round(turnover_component_score, 1),
                    "profit": round(profit_component_score, 1),
                    "ranking": round(ranking_component_score, 1),
                },
                "risk": {
                    "loss_rate": _round(national_series_loss_rate, 4),
                    "max_loss_rate": portfolio_max_loss_rate,
                },
            },
            "acquired_sell_through_guard_score": round(acquired_sell_through_guard_score, 1),
            "listed_sell_through_guard_score": round(listed_sell_through_guard_score, 1),
            "avoid_policy_score": round(avoid_policy_score, 1),
            "ranking_signal": ranking_signal,
            "selection_policy_id": policy.get("strategy_id"),
            "profit_frontier_status": profit_frontier_status,
            "profit_frontier_eligible": profit_frontier_eligible,
            "profit_frontier_observation": profit_frontier_observation,
            "profit_frontier_avoid": profit_frontier_avoid,
            "national_series_total_profit_90d": round(national_series_total_profit, 2),
            "national_series_sold_count_90d": national_series_sold_count,
            "national_series_candidate_count_90d": national_series_candidate_count,
            "national_series_profit_per_candidate_90d": round(national_series_profit_per_candidate, 2),
            "national_series_loss_rate_90d": _round(national_series_loss_rate, 4),
            "value_score": round(value_score, 1),
            "risk_score": round(risk_score, 1),
            "business_recommend": bool(gate.get("business_recommend")),
            "business_avoid": bool(gate.get("business_avoid")),
            "business_metric_ratios": metric_ratios,
            "comparison_baseline": _compact_history_metrics(baseline),
            "comparison_scope": _comparison_scope_label(slots, uses_national_fallback=uses_national_fallback),
            "leader_metric_pass_count": leader_pass_count,
            "recommend_leader_metrics_pass": gate.get("recommend_leader_metrics_pass") or {},
            "avoid_leader_metrics_pass": gate.get("avoid_leader_metrics_pass") or {},
            "price_band_fit_score": round(price_band_fit, 1),
            "raw_business_score": round(core_score, 1),
            "business_score": business_score,
            "confidence_score": round(confidence_score, 4),
            "final_opportunity_score": final_opportunity_score,
            "selection_score": final_opportunity_score,
            "selection_level": level,
            "recommendation_level": level,
            "recommendation_label": label,
            "sample_level": sample_confidence.get("sample_level"),
            "sample_note": sample_confidence.get("data_quality_note"),
            "candidate_count_90d": int(candidate_count),
            "acquired_count_90d": int(acquired_count),
            "sold_count_90d": int(sold_count),
            "history_evidence_scope": history_scope,
            "history_evidence_scope_display": history.get("history_scope_display") or "暂无内部90天实证",
            "national_prior_acquired_count_90d": int(evidence_acquired_count) if uses_national_fallback else 0,
            "national_prior_sold_count_90d": int(evidence_sold_count) if uses_national_fallback else 0,
            "sale_conversion_rate": _round(smoothed_history.get("sale_conversion_rate"), 4),
            "acquisition_conversion_rate": _round(smoothed_history.get("acquisition_conversion_rate"), 4),
            "sold_from_acquired_rate": _round(smoothed_history.get("sold_from_acquired_rate"), 4),
            "avg_turnover_days": _round(smoothed_history.get("avg_turnover_days"), 2),
            "avg_gross_profit": _round(smoothed_history.get("avg_gross_profit"), 2),
            "observed_avg_gross_profit": _round(history.get("avg_gross_profit"), 2),
            "listed_conversion_denominator": int(_num(history.get("listed_conversion_denominator"))),
            "acquired_conversion_denominator": int(_num(history.get("acquired_conversion_denominator"))),
            "loss_rate": _round(smoothed_history.get("loss_rate"), 4),
            "median_gross_profit": _round(smoothed_history.get("median_gross_profit"), 2),
            "observed_loss_rate": _round(history.get("loss_rate"), 4),
            "observed_median_gross_profit": _round(history.get("median_gross_profit"), 2),
            "profit_observed_count": int(_num(history.get("profit_observed_count"))),
            "total_gross_profit": round(signed_total_profit, 2),
            "total_profit_contribution": round(total_profit_contribution, 6),
            "expected_profit_per_10_candidates": round(expected_profit_per_10_candidates, 2),
            "gate_reasons": gate.get("gate_reasons") or [],
            "reasons": reasons,
            "risks": risks,
            "suggested_purchase_price_range": purchase_range,
            "action": _action(level),
        }

    def _public_item(self, row: dict[str, Any], rank: int, city: Any) -> dict[str, Any]:
        ranking_evidence = _compact_ranking_evidence(_ranking_evidence(city, row.get("brand"), row.get("series"), limit=2)) if rank <= 8 else {}
        official_photo = _compact_photo(_official_photo(row.get("brand"), row.get("series")))
        taxonomy = self.taxonomy.classify_series(brand=row.get("brand"), series=row.get("series"), model=row.get("model"))
        body_type = taxonomy.get("body_type")
        energy_type = taxonomy.get("energy_type")
        detailed_categories = list(taxonomy.get("vehicle_categories") or [])
        energy_subtypes = list(taxonomy.get("energy_subtypes") or [])
        manufacturer_attributes = list(taxonomy.get("manufacturer_attributes") or [])
        vehicle_tags = list(dict.fromkeys(tag for tag in (body_type, energy_type, *detailed_categories, *energy_subtypes, *manufacturer_attributes) if tag))
        brand_tier = classify_brand_tier(row.get("brand"))
        national_scope = str(city or "全国") in {"", "全国", "全网"}
        business_recommend = bool(row.get("business_recommend"))
        business_avoid = bool(row.get("business_avoid"))
        public_label = "推荐收" if business_recommend else "避免收" if business_avoid else "未进入推荐或避免池"
        public_action = (
            "推荐主动收；找到具体车后进入单车定价"
            if business_recommend
            else "不主动收；已有库存优先去化"
            if business_avoid
            else "不进入业务清单，仅保留在完整排名供查询"
        )
        business_metric_scope = "series_reference" if national_scope else "city_series"
        return {
            "rank": rank,
            "brand": row.get("brand"),
            "series": row.get("series"),
            # National lists expose model-year rows. City lists are strictly
            # city+series and must not leak the internal aggregate helper.
            "model": None,
            "vehicle_category": body_type or energy_type,
            "vehicle_tags": vehicle_tags,
            "body_type": body_type,
            "energy_type": energy_type,
            "energy_subtypes": energy_subtypes,
            "energy_subtype": energy_subtypes[0] if len(energy_subtypes) == 1 else " / ".join(energy_subtypes),
            "vehicle_categories": detailed_categories,
            "manufacturer_attributes": manufacturer_attributes,
            "manufacturer_attribute": manufacturer_attributes[0] if len(manufacturer_attributes) == 1 else " / ".join(manufacturer_attributes),
            "brand_tier": brand_tier,
            "taxonomy": taxonomy,
            "model_year": row.get("model_year") if national_scope else None,
            "business_metric_scope": business_metric_scope,
            "business_metric_scope_display": (
                "车系90天经营参考（同车系各年款共享）"
                if national_scope
                else f"{row.get('city') or city}车系90天经营实证"
            ),
            "year_market_metric_scope_display": (
                "当前年款90天行情实证" if national_scope else ""
            ),
            "price_scope_model_years": row.get("price_scope_model_years") or [],
            "price_scope_models": row.get("price_scope_models") or [],
            "price_scope_match_count": row.get("price_scope_match_count"),
            "price_scope_total_count": row.get("price_scope_total_count"),
            "price_scope_coverage_ratio": row.get("price_scope_coverage_ratio"),
            "city": row.get("city") or city,
            "market_category": row.get("market_category"),
            "market_category_label": row.get("market_category"),
            "market_evidence_scope": row.get("market_evidence_scope"),
            "market_evidence_scope_display": row.get("market_evidence_scope_display"),
            "market_category_distribution": row.get("market_category_distribution") or {},
            "recommendation_level": row.get("recommendation_level"),
            "recommendation_label": public_label,
            "business_action_label": public_label,
            "opportunity_score": row.get("selection_score"),
            "business_score": row.get("business_score"),
            "confidence_score": row.get("confidence_score"),
            "final_opportunity_score": row.get("final_opportunity_score"),
            "raw_business_score": row.get("raw_business_score"),
            "sample_level": row.get("sample_level"),
            "sample_note": row.get("sample_note"),
            "candidate_count_90d": row.get("candidate_count_90d"),
            "acquired_count_90d": row.get("acquired_count_90d"),
            "sold_count_90d": row.get("sold_count_90d"),
            "history_evidence_scope": row.get("history_evidence_scope"),
            "history_evidence_scope_display": row.get("history_evidence_scope_display"),
            "national_prior_acquired_count_90d": row.get("national_prior_acquired_count_90d"),
            "national_prior_sold_count_90d": row.get("national_prior_sold_count_90d"),
            "acquisition_conversion_rate": row.get("acquisition_conversion_rate"),
            "sold_from_acquired_rate": row.get("sold_from_acquired_rate"),
            "sale_conversion_rate": row.get("sale_conversion_rate"),
            "listed_conversion_denominator": row.get("listed_conversion_denominator"),
            "acquired_conversion_denominator": row.get("acquired_conversion_denominator"),
            # Public profit facts are observed and signed.  Smoothed values
            # remain separately labelled as ranking inputs so a positive
            # prior cannot be mistaken for an achieved result.
            "loss_rate": row.get("observed_loss_rate"),
            "median_gross_profit": row.get("observed_median_gross_profit"),
            "ranking_loss_rate": row.get("loss_rate"),
            "ranking_median_gross_profit": row.get("median_gross_profit"),
            "ranking_avg_gross_profit": row.get("avg_gross_profit"),
            "profit_observed_count": row.get("profit_observed_count"),
            "total_gross_profit": row.get("total_gross_profit"),
            "total_profit_contribution": row.get("total_profit_contribution"),
            "expected_profit_per_10_candidates": row.get("expected_profit_per_10_candidates"),
            "gate_reasons": row.get("gate_reasons") or [],
            "demand_score": row.get("demand_score"),
            "supply_score": row.get("supply_score"),
            "value_score": row.get("value_score"),
            "risk_score": row.get("risk_score"),
            "external_full_signal_score": row.get("external_full_signal_score"),
            "selection_layer_scores": row.get("selection_layer_scores") or {},
            "selection_dsi_score": row.get("selection_dsi_score"),
            "acquired_sell_through_guard_score": row.get("acquired_sell_through_guard_score"),
            "listed_sell_through_guard_score": row.get("listed_sell_through_guard_score"),
            "avoid_policy_score": row.get("avoid_policy_score"),
            "ranking_signal": row.get("ranking_signal") or {},
            "selection_policy_id": row.get("selection_policy_id"),
            "profit_frontier_status": row.get("profit_frontier_status"),
            "profit_frontier_eligible": row.get("profit_frontier_eligible"),
            "profit_frontier_observation": row.get("profit_frontier_observation"),
            "profit_frontier_avoid": row.get("profit_frontier_avoid"),
            "national_series_total_profit_90d": row.get("national_series_total_profit_90d"),
            "national_series_sold_count_90d": row.get("national_series_sold_count_90d"),
            "national_series_candidate_count_90d": row.get("national_series_candidate_count_90d"),
            "national_series_profit_per_candidate_90d": row.get("national_series_profit_per_candidate_90d"),
            "national_series_loss_rate_90d": row.get("national_series_loss_rate_90d"),
            "business_recommend": business_recommend,
            "business_avoid": business_avoid,
            "business_metric_ratios": row.get("business_metric_ratios") or {},
            "comparison_baseline": row.get("comparison_baseline") or {},
            "comparison_scope": row.get("comparison_scope") or "当前同条件候选",
            "leader_metric_pass_count": row.get("leader_metric_pass_count"),
            "recommend_leader_metrics_pass": row.get("recommend_leader_metrics_pass") or {},
            "avoid_leader_metrics_pass": row.get("avoid_leader_metrics_pass") or {},
            "price_band_fit_score": row.get("price_band_fit_score"),
            "turnover_score": row.get("turnover_score"),
            "market_state_score": row.get("market_state_score"),
            "deal_sample_90d": int(_num(row.get("deal_sample_90d"))),
            "listing_count": int(_num(row.get("listing_count"))),
            "avg_deal_cycle": _round(row.get("avg_deal_cycle"), 1),
            "avg_turnover_days": _round(row.get("avg_turnover_days"), 1),
            "avg_gross_profit": _round(row.get("observed_avg_gross_profit"), 2),
            "inventory_cycle": _round(row.get("inventory_cycle"), 1),
            "sell_through_rate": _round(row.get("sell_through_rate"), 2),
            "price_change_30d": _round(row.get("price_change_30d"), 6),
            "deal_price_low_90d": _round(row.get("deal_price_low_90d"), 0),
            "deal_price_high_90d": _round(row.get("deal_price_high_90d"), 0),
            "price_scope_model_years": row.get("price_scope_model_years") or [],
            "price_scope_models": row.get("price_scope_models") or [],
            "price_scope_match_count": int(_num(row.get("price_scope_match_count"))),
            "price_scope_total_count": int(_num(row.get("price_scope_total_count"))),
            "price_scope_coverage_ratio": row.get("price_scope_coverage_ratio"),
            "suggested_purchase_price_range": row.get("suggested_purchase_price_range"),
            "dsi_signal": row.get("dsi_signal") or {},
            "history_metrics": _compact_history_metrics(row.get("history_metrics") or {}),
            "sample_confidence": _compact_sample_confidence(row.get("sample_confidence") or {}),
            "reasons": row.get("reasons") or [],
            "risks": row.get("risks") or [],
            "action": public_action,
            "official_photo": official_photo,
            "ranking_evidence": ranking_evidence,
        }


def _price_overlap(row: dict[str, Any], low: Any, high: Any) -> bool:
    row_low = finite_number(row.get("deal_price_low_90d"))
    row_high = finite_number(row.get("deal_price_high_90d"))
    if row_low is None and row_high is None:
        return False
    row_low = row_low if row_low is not None else row_high
    row_high = row_high if row_high is not None else row_low
    if low is not None and row_high < float(low):
        return False
    if high is not None and row_low > float(high):
        return False
    return True


def _price_fully_within_band(row: dict[str, Any], low: Any, high: Any) -> bool:
    row_low = finite_number(row.get("deal_price_low_90d"))
    row_high = finite_number(row.get("deal_price_high_90d"))
    if row_low is None and row_high is None:
        return False
    row_low = row_low if row_low is not None else row_high
    row_high = row_high if row_high is not None else row_low
    if low is not None and row_low < float(low):
        return False
    if high is not None and row_high > float(high):
        return False
    return True


def _with_market_evidence_scope(rows: list[dict[str, Any]], scope: str, requested_city: str) -> list[dict[str, Any]]:
    display = {
        "city": "城市90天车系行情实证",
        "national": "全国90天车型+年款行情实证",
        "national_prior": "全国90天车系行情先验",
    }.get(scope, "行情数据")
    return [
        {
            **row,
            "market_evidence_scope": scope,
            "market_evidence_scope_display": display,
            "market_requested_city": requested_city,
        }
        for row in rows
    ]


def _aggregate_market_rows_by_series(
    rows: list[dict[str, Any]],
    *,
    scope: str,
    requested_city: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (normalize_text(row.get("brand")), normalize_text(row.get("series")))
        if not key[1]:
            continue
        grouped.setdefault(key, []).append(row)

    sum_fields = (
        "deal_sample_90d", "listing_count", "deal_count", "current_inventory", "sales_7d", "sales_15d",
        "sales_30d", "platform_inventory", "city_listing_count", "price_cut_count_7d", "price_cut_count_15d",
        "price_cut_count_30d", "favorite_count", "search_volume", "detail_uv",
    )
    weighted_fields = (
        "avg_price_spread", "price_change_7d", "price_change_14d", "price_change_30d", "price_change_45d",
        "price_change_60d", "price_volatility", "official_guide_price", "avg_deal_cycle", "sell_through_rate",
        "avg_clear_days_30d", "inventory_cycle", "active_listing_cycle", "avg_price_adjustments", "lead_rate",
        "inquiry_conversion_rate", "price_cut_rate_7d", "price_cut_rate_30d",
    )
    out: list[dict[str, Any]] = []
    for members in grouped.values():
        base = max(
            members,
            key=lambda item: (
                _num(item.get("deal_sample_90d")),
                _num(item.get("deal_count")),
                _num(item.get("listing_count")),
            ),
        )
        payload = dict(base)
        weights = [max(1.0, _num(item.get("deal_sample_90d")) or _num(item.get("deal_count")) or _num(item.get("listing_count"))) for item in members]
        for field in sum_fields:
            values = [finite_number(item.get(field)) for item in members]
            present = [value for value in values if value is not None]
            payload[field] = sum(present) if present else None
        for field in weighted_fields:
            numerator = 0.0
            denominator = 0.0
            for item, weight in zip(members, weights):
                value = finite_number(item.get(field))
                if value is None:
                    continue
                numerator += value * weight
                denominator += weight
            payload[field] = numerator / denominator if denominator else None
        lows = [value for value in (finite_number(item.get("deal_price_low_90d")) for item in members) if value is not None and value > 0]
        highs = [value for value in (finite_number(item.get("deal_price_high_90d")) for item in members) if value is not None and value > 0]
        payload["deal_price_low_90d"] = min(lows) if lows else None
        payload["deal_price_high_90d"] = max(highs) if highs else None
        category_weights: dict[str, float] = {}
        for item, weight in zip(members, weights):
            category = str(item.get("market_category") or "未知")
            category_weights[category] = category_weights.get(category, 0.0) + weight
        payload["market_category"] = max(category_weights, key=category_weights.get) if category_weights else "未知"
        payload["market_category_distribution"] = {
            key: round(value / sum(category_weights.values()), 4)
            for key, value in sorted(category_weights.items(), key=lambda item: item[1], reverse=True)
        } if category_weights else {}
        payload["model"] = ""
        payload["model_year"] = "多年份聚合"
        payload["aggregation_member_count"] = len(members)
        payload["city"] = "全国" if scope == "national" else requested_city
        payload["market_evidence_scope"] = scope
        payload["market_evidence_scope_display"] = "全国90天车系行情实证" if scope == "national" else "全国90天车系行情先验"
        payload["market_requested_city"] = requested_city
        out.append(payload)
    return out


def _price_scoped_market_rows(
    rows: list[dict[str, Any]],
    *,
    low: Any,
    high: Any,
    scope: str,
    requested_city: str,
) -> list[dict[str, Any]]:
    priced_by_series: dict[tuple[str, str], list[dict[str, Any]]] = {}
    matched_by_series: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (normalize_text(row.get("brand")), normalize_text(row.get("series")))
        if not key[1]:
            continue
        if finite_number(row.get("deal_price_low_90d")) is not None or finite_number(row.get("deal_price_high_90d")) is not None:
            priced_by_series.setdefault(key, []).append(row)
        if _price_fully_within_band(row, low, high):
            matched_by_series.setdefault(key, []).append(row)

    aggregated = _aggregate_market_rows_by_series(
        [row for members in matched_by_series.values() for row in members],
        scope=scope,
        requested_city=requested_city,
    )
    for row in aggregated:
        key = (normalize_text(row.get("brand")), normalize_text(row.get("series")))
        matched = matched_by_series.get(key) or []
        priced = priced_by_series.get(key) or matched
        years = sorted({str(item.get("model_year")) for item in matched if str(item.get("model_year") or "").strip()})
        models = [str(item.get("model") or "").strip() for item in matched if str(item.get("model") or "").strip()]
        row["price_scope_model_years"] = years
        row["price_scope_models"] = list(dict.fromkeys(models))[:8]
        row["price_scope_match_count"] = len(matched)
        row["price_scope_total_count"] = len(priced)
        row["price_scope_coverage_ratio"] = len(matched) / len(priced) if priced else None
    return aggregated


def _price_scoped_national_model_year_rows(
    rows: list[dict[str, Any]],
    *,
    low: Any,
    high: Any,
    scope: str,
    requested_city: str,
) -> list[dict[str, Any]]:
    """Keep the national ranking at concrete model+year grain after price filtering."""
    matched = [row for row in rows if _price_fully_within_band(row, low, high)]
    scoped = _with_market_evidence_scope(matched, "national", "全国")
    out: list[dict[str, Any]] = []
    for row in scoped:
        payload = dict(row)
        year = str(row.get("model_year") or "").strip()
        model = str(row.get("model") or "").strip()
        payload["price_scope_model_years"] = [year] if year else []
        payload["price_scope_models"] = [model] if model else []
        payload["price_scope_match_count"] = 1
        payload["price_scope_total_count"] = 1
        payload["price_scope_coverage_ratio"] = 1.0
        out.append(payload)
    return out


def _apply_price_scope_to_city_rows(
    city_rows: list[dict[str, Any]],
    scoped_national_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scoped = {
        (normalize_text(row.get("brand")), normalize_text(row.get("series"))): row
        for row in scoped_national_rows
    }
    city = {
        (normalize_text(row.get("brand")), normalize_text(row.get("series"))): row
        for row in city_rows
    }
    price_fields = (
        "deal_price_low_90d",
        "deal_price_high_90d",
        "price_scope_model_years",
        "price_scope_models",
        "price_scope_match_count",
        "price_scope_total_count",
        "price_scope_coverage_ratio",
    )
    out: list[dict[str, Any]] = []
    for key, price_row in scoped.items():
        local = city.get(key)
        if local is None:
            out.append(price_row)
            continue
        payload = {**price_row, **local}
        for field in price_fields:
            payload[field] = price_row.get(field)
        out.append(payload)
    return out


def _merge_market_series_rows(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in [*primary, *secondary]:
        key = (normalize_text(row.get("brand")), normalize_text(row.get("series")))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (
            normalize_text(row.get("city")),
            normalize_text(row.get("brand")),
            normalize_text(row.get("series")),
            normalize_text(row.get("model")),
            str(row.get("model_year") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_strategy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = _strategy_row_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _strategy_row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    city = normalize_text(row.get("city"))
    brand = normalize_text(row.get("brand"))
    series = normalize_text(row.get("series"))
    if city in {"", "全国", "全网"}:
        # Product grain: national = series/model-year.  Multiple trims in the
        # same year are evidence rows for the same selection object, not
        # separate ranking positions.
        return ("全国", brand, series, str(row.get("model_year") or ""), "")
    # Product grain: city = city/series.  Model-year and trim stay available
    # as supporting evidence but must not occupy duplicate city positions.
    return (city, brand, series, "", "")


def _build_subject_lookup(
    slots: dict[str, Any],
    ranked_rows: list[dict[str, Any]],
    risk_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    target = str(slots.get("selection_target") or "")
    if target not in {"rank_lookup", "selection_reason", "score_explanation", "series_judgement", "evidence_answer"}:
        return {}
    subject_series = normalize_text(slots.get("series"))
    subject_brand = normalize_text(slots.get("brand"))

    strict_rows = [row for row in ranked_rows if row.get("business_recommend")]
    strict_rank = {_strategy_row_key(row): index + 1 for index, row in enumerate(strict_rows)}
    risk_rank = {_strategy_row_key(row): index + 1 for index, row in enumerate(risk_rows)}

    requested_rank = int(slots.get("requested_rank") or 0)
    if target == "rank_lookup" and requested_rank > 0:
        contextual = slots.get("contextual_rank_item") if isinstance(slots.get("contextual_rank_item"), dict) else None
        displayed_rows = strict_rows or ranked_rows
        row = contextual or (displayed_rows[requested_rank - 1] if requested_rank <= len(displayed_rows) else None)
        if isinstance(row, dict):
            key = _strategy_row_key(row)
            matched = {
                "brand": row.get("brand"),
                "series": row.get("series"),
                "candidate_rank": requested_rank,
                "strict_rank": row.get("strict_rank") or strict_rank.get(key),
                "risk_rank": row.get("risk_rank") or risk_rank.get(key),
                "in_displayed_top30": requested_rank <= 30,
                "business_recommend": bool(row.get("business_recommend")),
                "business_avoid": bool(row.get("business_avoid")),
                "recommendation_label": row.get("recommendation_label"),
                "opportunity_score": row.get("selection_score") or row.get("opportunity_score"),
                "business_score": row.get("business_score"),
                "confidence_score": row.get("confidence_score"),
                "sample_level": row.get("sample_level"),
                "sold_count_90d": row.get("sold_count_90d"),
                "acquired_count_90d": row.get("acquired_count_90d"),
                "acquisition_conversion_rate": row.get("acquisition_conversion_rate"),
                "sale_conversion_rate": row.get("sale_conversion_rate"),
                "sold_from_acquired_rate": row.get("sold_from_acquired_rate"),
                "total_profit_contribution": row.get("total_profit_contribution"),
                "avg_deal_cycle": row.get("avg_deal_cycle"),
                "avg_turnover_days": row.get("avg_turnover_days"),
                "avg_gross_profit": row.get("avg_gross_profit"),
                "median_gross_profit": row.get("median_gross_profit"),
                "loss_rate": row.get("loss_rate"),
                "total_gross_profit": row.get("total_gross_profit"),
                "market_category": row.get("market_category"),
                "dsi_signal": row.get("dsi_signal") or {},
                "business_metric_ratios": row.get("business_metric_ratios") or {},
                "comparison_baseline": row.get("comparison_baseline") or {},
                "comparison_scope": row.get("comparison_scope") or "当前同条件候选基线",
                "suggested_purchase_price_range": row.get("suggested_purchase_price_range") or {},
                "gate_reasons": list(row.get("gate_reasons") or [])[:4],
                "risks": list(row.get("risks") or [])[:4],
                "entity_match": "requested_ordinal",
            }
            return {
                "subject": f"第{requested_rank}名",
                "subject_type": "rank",
                "candidate_universe_size": len(displayed_rows),
                "strict_pool_size": len(strict_rows),
                "display_limit": 30,
                "matched_count": 1,
                "best_candidate_rank": requested_rank,
                "best_strict_rank": matched.get("strict_rank"),
                "in_candidate_pool": True,
                "in_displayed_top30": requested_rank <= 30,
                "in_strict_recommend_pool": bool(matched.get("business_recommend")),
                "ranking_source": "previous_result_snapshot" if contextual else "same_scope_recomputed_display_ranking",
                "matches": [matched],
            }
        return {
            "subject": f"第{requested_rank}名",
            "subject_type": "rank",
            "candidate_universe_size": len(displayed_rows),
            "strict_pool_size": len(strict_rows),
            "display_limit": 30,
            "matched_count": 0,
            "in_candidate_pool": False,
            "in_displayed_top30": False,
            "in_strict_recommend_pool": False,
            "matches": [],
        }

    if not subject_series and not subject_brand:
        return {}

    def matches(row: dict[str, Any]) -> bool:
        row_series = normalize_text(row.get("series"))
        row_brand = normalize_text(row.get("brand"))
        if subject_series:
            return row_series == subject_series or (
                bool(subject_brand)
                and row_brand == subject_brand
                and (subject_series in row_series or row_series in subject_series)
            )
        return row_brand == subject_brand

    contextual_series_items = (
        slots.get("contextual_series_items")
        if isinstance(slots.get("contextual_series_items"), list)
        else []
    )
    source_pairs = (
        [
            (int(_num(row.get("rank"))) or index, row)
            for index, row in enumerate(contextual_series_items, start=1)
            if isinstance(row, dict)
        ]
        if contextual_series_items
        else list(enumerate(ranked_rows, start=1))
    )
    found: list[dict[str, Any]] = []
    for index, row in source_pairs:
        if not matches(row):
            continue
        key = _strategy_row_key(row)
        found.append(
            {
                "brand": row.get("brand"),
                "series": row.get("series"),
                "candidate_rank": index,
                "strict_rank": row.get("strict_rank") or strict_rank.get(key),
                "risk_rank": row.get("risk_rank") or risk_rank.get(key),
                "in_displayed_top30": index <= 30,
                "business_recommend": bool(row.get("business_recommend")),
                "business_avoid": bool(row.get("business_avoid")),
                "recommendation_label": row.get("recommendation_label"),
                "opportunity_score": row.get("selection_score") or row.get("opportunity_score"),
                "business_score": row.get("business_score"),
                "confidence_score": row.get("confidence_score"),
                "sample_level": row.get("sample_level"),
                "sold_count_90d": row.get("sold_count_90d"),
                "acquired_count_90d": row.get("acquired_count_90d"),
                "acquisition_conversion_rate": row.get("acquisition_conversion_rate"),
                "sale_conversion_rate": row.get("sale_conversion_rate"),
                "sold_from_acquired_rate": row.get("sold_from_acquired_rate"),
                "total_profit_contribution": row.get("total_profit_contribution"),
                "avg_deal_cycle": row.get("avg_deal_cycle"),
                "avg_turnover_days": row.get("avg_turnover_days"),
                "avg_gross_profit": row.get("avg_gross_profit"),
                "median_gross_profit": row.get("median_gross_profit"),
                "loss_rate": row.get("loss_rate"),
                "total_gross_profit": row.get("total_gross_profit"),
                "market_category": row.get("market_category"),
                "dsi_signal": row.get("dsi_signal") or {},
                "business_metric_ratios": row.get("business_metric_ratios") or {},
                "comparison_baseline": row.get("comparison_baseline") or {},
                "comparison_scope": row.get("comparison_scope") or "当前同条件候选基线",
                "suggested_purchase_price_range": row.get("suggested_purchase_price_range") or {},
                "gate_reasons": list(row.get("gate_reasons") or [])[:4],
                "risks": list(row.get("risks") or [])[:4],
                "entity_match": "exact_series" if subject_series and normalize_text(row.get("series")) == subject_series else "brand_or_alias",
            }
        )
    found.sort(
        key=lambda item: (
            0 if item.get("entity_match") == "exact_series" else 1,
            item.get("candidate_rank") or 10**9,
            str(item.get("series") or ""),
        )
    )
    return {
        "subject": str(slots.get("series") or slots.get("brand") or ""),
        "subject_type": "series" if subject_series else "brand",
        "candidate_universe_size": len(ranked_rows),
        "strict_pool_size": len(strict_rows),
        "display_limit": 30,
        "matched_count": len(found),
        "best_candidate_rank": found[0].get("candidate_rank") if found else None,
        "best_strict_rank": next((item.get("strict_rank") for item in found if item.get("strict_rank")), None),
        "in_candidate_pool": bool(found),
        "in_displayed_top30": any(item.get("in_displayed_top30") for item in found),
        "in_strict_recommend_pool": any(item.get("business_recommend") for item in found),
        "ranking_source": "previous_full_ranking_snapshot" if contextual_series_items else "same_scope_recomputed_ranking",
        "matches": found[:20],
    }


def _recommend_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        not row.get("business_recommend"),
        not row.get("profit_frontier_eligible"),
        not row.get("profit_frontier_observation"),
        row.get("selection_level") in {"AVOID", "CAUTION"},
        -(row.get("final_opportunity_score") or 0),
        -_sample_level_rank(row.get("sample_level")),
        -int(_num(row.get("sold_count_90d") or row.get("deal_sample_90d"))),
        -int(_num(row.get("acquired_count_90d"))),
        -(row.get("total_profit_contribution") or 0),
        row.get("avg_deal_cycle") or 9999,
        -_num((row.get("business_metric_ratios") or {}).get("sale_conversion_rate") if isinstance(row.get("business_metric_ratios"), dict) else 0),
        normalize_text(row.get("brand")),
        normalize_text(row.get("series")),
    )


def _sample_level_rank(value: Any) -> int:
    return {
        "very_low": 0,
        "low": 1,
        "limited": 2,
        "medium": 3,
        "high": 4,
        "strong": 5,
    }.get(str(value or ""), -1)


def _data_coverage(row: dict[str, Any], history: dict[str, Any]) -> float:
    fields = (
        row.get("deal_sample_90d"),
        row.get("detail_uv"),
        row.get("favorite_count"),
        row.get("inventory_cycle"),
        row.get("sell_through_rate"),
        row.get("avg_deal_cycle"),
        history.get("avg_gross_profit"),
        history.get("avg_turnover_days"),
        history.get("sale_conversion_rate"),
        history.get("acquisition_conversion_rate"),
        history.get("sold_from_acquired_rate"),
    )
    available = sum(1 for value in fields if finite_number(value) is not None)
    return available / len(fields)


def _history_total_profit(history: dict[str, Any]) -> float:
    explicit = finite_number(history.get("total_gross_profit") if isinstance(history, dict) else None)
    if explicit is not None:
        return max(0.0, explicit)
    avg_profit = finite_number(history.get("avg_gross_profit") if isinstance(history, dict) else None)
    sold_count = finite_number(history.get("sold_count_90d") if isinstance(history, dict) else history.get("sold_count") if isinstance(history, dict) else None)
    if avg_profit is None or sold_count is None:
        return 0.0
    return max(0.0, avg_profit * sold_count)


def _history_signed_total_profit(history: dict[str, Any]) -> float:
    explicit = finite_number(history.get("total_gross_profit") if isinstance(history, dict) else None)
    if explicit is not None:
        return float(explicit)
    avg_profit = finite_number(history.get("avg_gross_profit") if isinstance(history, dict) else None)
    sold_count = finite_number(
        history.get("sold_count_90d")
        if isinstance(history, dict)
        else history.get("sold_count") if isinstance(history, dict) else None
    )
    if avg_profit is None or sold_count is None:
        return 0.0
    return float(avg_profit * sold_count)


def _total_profit_score(contribution: float) -> float:
    if contribution <= 0:
        return 35.0
    if contribution >= 0.08:
        return 100.0
    if contribution >= 0.03:
        return 78.0 + min(1.0, (contribution - 0.03) / 0.05) * 22.0
    if contribution >= 0.01:
        return 56.0 + min(1.0, (contribution - 0.01) / 0.02) * 22.0
    return 38.0 + min(1.0, contribution / 0.01) * 18.0


def _normalized_score_weights(weights: dict[str, Any]) -> dict[str, float]:
    defaults = {
        "demand": 0.00,
        "supply": 0.00,
        "turnover": 0.00,
        "price_stability": 0.00,
        "market_state": 0.20,
        "dsi": 0.05,
        "value": 0.55,
        "total_profit": 0.20,
    }
    out: dict[str, float] = {}
    for key, default in defaults.items():
        out[key] = max(0.0, float(finite_number((weights or {}).get(key)) if finite_number((weights or {}).get(key)) is not None else default))
    total = sum(out.values())
    if total <= 0:
        return defaults
    return {key: value / total for key, value in out.items()}


def _price_band_fit_score(row: dict[str, Any], slots: dict[str, Any]) -> float:
    band = slots.get("price_band") or {}
    low = finite_number(band.get("low"))
    high = finite_number(band.get("high"))
    if low is None and high is None:
        return 100.0
    row_low = finite_number(row.get("deal_price_low_90d"))
    row_high = finite_number(row.get("deal_price_high_90d"))
    guide_price = finite_number(row.get("official_guide_price"))
    if row_low is None and row_high is None and guide_price is not None:
        row_low = guide_price * 0.58
        row_high = guide_price * 0.92
    if row_low is None and row_high is None:
        return 55.0
    row_low = row_low if row_low is not None else row_high
    row_high = row_high if row_high is not None else row_low
    if high is not None and low is None and float(row_high) <= high:
        # A budget ceiling should prefer the part of the market that actually
        # uses the budget, otherwise 20万 and 30万 queries collapse to the
        # same cheap-car ranking even after candidate filtering.
        row_mid = (float(row_low) + float(row_high)) / 2
        ideal = float(high) * 0.78
        distance = abs(row_mid - ideal)
        return max(55.0, min(100.0, 100.0 - distance / max(float(high) * 0.45, 50_000.0) * 45.0))
    if low is not None and high is None and float(row_low) >= low:
        row_mid = (float(row_low) + float(row_high)) / 2
        ideal = float(low) * 1.18
        distance = abs(row_mid - ideal)
        return max(55.0, min(100.0, 100.0 - distance / max(float(low) * 0.55, 50_000.0) * 45.0))
    if low is not None and high is not None and _price_overlap(row, low, high):
        row_mid = (float(row_low) + float(row_high)) / 2
        ideal = (float(low) + float(high)) / 2
        distance = abs(row_mid - ideal)
        return max(60.0, min(100.0, 100.0 - distance / max((float(high) - float(low)) / 2, 50_000.0) * 35.0))
    if low is not None and high is not None:
        band_mid = (low + high) / 2
        band_width = max(1.0, high - low)
    elif high is not None:
        band_mid = high * 0.72
        band_width = max(50000.0, high * 0.42)
    else:
        band_mid = low * 1.18 if low is not None else 150000.0
        band_width = max(50000.0, (low or 100000.0) * 0.5)
    row_mid = (float(row_low) + float(row_high)) / 2
    distance = abs(row_mid - band_mid)
    score = 100 - distance / max(50000.0, band_width) * 70
    return max(0.0, min(100.0, score))


def _history_metric_scores(history: dict[str, Any], baseline: dict[str, Any]) -> list[float]:
    return [
        _relative_metric_score(history.get("avg_gross_profit"), baseline.get("avg_gross_profit"), floor_abs=2500),
        _relative_metric_score(history.get("sale_conversion_rate"), baseline.get("sale_conversion_rate"), floor_abs=0.08),
        _relative_metric_score(history.get("acquisition_conversion_rate"), baseline.get("acquisition_conversion_rate"), floor_abs=0.08),
        _relative_metric_score(history.get("turnover_efficiency_index"), baseline.get("turnover_efficiency_index"), floor_abs=0.015),
    ]


def _history_metric_ratios(history: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float | None]:
    return {
        "avg_turnover_days": _safe_metric_ratio(history.get("avg_turnover_days"), baseline.get("avg_turnover_days")),
        "avg_gross_profit": _safe_metric_ratio(history.get("avg_gross_profit"), baseline.get("avg_gross_profit")),
        "sale_conversion_rate": _safe_metric_ratio(history.get("sale_conversion_rate"), baseline.get("sale_conversion_rate")),
        "acquisition_conversion_rate": _safe_metric_ratio(history.get("acquisition_conversion_rate"), baseline.get("acquisition_conversion_rate")),
        "sold_from_acquired_rate": _safe_metric_ratio(history.get("sold_from_acquired_rate"), baseline.get("sold_from_acquired_rate")),
        "purchase_conversion_proxy": _safe_metric_ratio(history.get("purchase_conversion_proxy"), baseline.get("purchase_conversion_proxy")),
        "turnover_efficiency_index": _safe_metric_ratio(history.get("turnover_efficiency_index"), baseline.get("turnover_efficiency_index")),
    }


def _safe_metric_ratio(value: Any, baseline: Any) -> float | None:
    current = finite_number(value)
    base = finite_number(baseline)
    if current is None or base is None or abs(base) < 1e-9:
        return None
    return round(current / base, 6)


def _business_recommend_flag(ratios: dict[str, float | None]) -> bool:
    required = (
        ratios.get("avg_turnover_days"),
        ratios.get("avg_gross_profit"),
        ratios.get("sale_conversion_rate"),
        ratios.get("acquisition_conversion_rate"),
    )
    if any(value is None for value in required):
        return False
    return (
        float(ratios["avg_turnover_days"]) <= 0.9
        and float(ratios["avg_gross_profit"]) >= 1.1
        and float(ratios["sale_conversion_rate"]) >= 1.1
        and float(ratios["acquisition_conversion_rate"]) >= 1.1
    )


def _business_avoid_flag(ratios: dict[str, float | None]) -> bool:
    required = (
        ratios.get("avg_turnover_days"),
        ratios.get("avg_gross_profit"),
        ratios.get("sale_conversion_rate"),
        ratios.get("acquisition_conversion_rate"),
    )
    if any(value is None for value in required):
        return False
    return (
        float(ratios["avg_turnover_days"]) >= 1.1
        and float(ratios["avg_gross_profit"]) <= 0.9
        and float(ratios["sale_conversion_rate"]) <= 0.9
        and float(ratios["acquisition_conversion_rate"]) <= 0.9
    )


def _leader_metric_pass_count(ratios: dict[str, float | None], *, mode: str) -> int:
    if mode == "avoid":
        checks = (
            ratios.get("avg_turnover_days") is not None and float(ratios["avg_turnover_days"]) >= 1.1,
            ratios.get("avg_gross_profit") is not None and float(ratios["avg_gross_profit"]) <= 0.9,
            ratios.get("sale_conversion_rate") is not None and float(ratios["sale_conversion_rate"]) <= 0.9,
            ratios.get("acquisition_conversion_rate") is not None and float(ratios["acquisition_conversion_rate"]) <= 0.9,
        )
    else:
        checks = (
            ratios.get("avg_turnover_days") is not None and float(ratios["avg_turnover_days"]) <= 0.9,
            ratios.get("avg_gross_profit") is not None and float(ratios["avg_gross_profit"]) >= 1.1,
            ratios.get("sale_conversion_rate") is not None and float(ratios["sale_conversion_rate"]) >= 1.1,
            ratios.get("acquisition_conversion_rate") is not None and float(ratios["acquisition_conversion_rate"]) >= 1.1,
        )
    return sum(bool(item) for item in checks)


def _history_value_score(history: dict[str, Any], baseline: dict[str, Any], *, metric_scores: list[float] | None = None) -> float:
    if not history:
        return 55
    sold_count = _num(history.get("sold_count_90d"), 0)
    reliability = max(0.35, min(1.0, sold_count / 20))
    scores = metric_scores or _history_metric_scores(history, baseline)
    short_board_score = min(scores)
    balanced_score = sum(scores) / len(scores)
    raw_score = short_board_score * 0.52 + balanced_score * 0.48
    return raw_score * reliability + 48 * (1 - reliability)


def _history_risk_score(
    history: dict[str, Any],
    baseline: dict[str, Any],
    row: dict[str, Any],
    *,
    metric_scores: list[float] | None = None,
) -> float:
    scores = metric_scores or _history_metric_scores(history, baseline)
    broad_weakness = max(scores) * 0.58 + (sum(scores) / len(scores)) * 0.42
    if not history:
        broad_weakness = min(broad_weakness, 42)
    if str(row.get("market_category") or "") == "急跌行情":
        broad_weakness -= 16
    elif str(row.get("market_category") or "") == "阴跌行情":
        broad_weakness -= 9
    if _num(row.get("price_change_30d"), 0) <= -0.03:
        broad_weakness -= 6
    loss_rate = finite_number(history.get("loss_rate"))
    if loss_rate is not None and loss_rate > 0.25:
        broad_weakness -= min(24, (loss_rate - 0.25) * 60)
    return max(0.0, min(100.0, broad_weakness))


def _relative_metric_score(value: Any, baseline: Any, *, floor_abs: float) -> float:
    current = finite_number(value)
    base = finite_number(baseline)
    if current is None:
        return 45.0
    if base is None or abs(base) < 1e-9:
        base = floor_abs
    if base <= 0:
        delta = current - base
        score = 55 + delta / max(floor_abs, abs(base), 1.0) * 40
    else:
        ratio = current / max(base, floor_abs)
        score = 50 + (ratio - 1) * 170
    return max(0.0, min(100.0, score))


def _reason_risk(row: dict[str, Any], history: dict[str, Any], dsi: dict[str, Any], stats: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    risks: list[str] = []
    if _num(row.get("deal_sample_90d")) >= (stats.get("deal_sample_90d", {}).get("q75") or math.inf):
        reasons.append("90天成交样本处于同城较高水平")
    if _num(row.get("sell_through_rate")) >= (stats.get("sell_through_rate", {}).get("q75") or math.inf):
        reasons.append("上架成交率处于同城较高水平")
    if _num(row.get("avg_deal_cycle")) <= (stats.get("avg_deal_cycle", {}).get("q25") or -1):
        reasons.append("平均成交周期较短")
    if dsi.get("label") == "供不应求":
        reasons.append("供需状态为供不应求")
    if history.get("avg_gross_profit") is not None and _num(history.get("avg_gross_profit")) > 3000:
        reasons.append(f"90天内部平均毛利约{_num(history.get('avg_gross_profit'))/10000:.2f}万")
    if _num(row.get("price_change_30d"), 0) <= -0.03:
        risks.append("30天价格下行，收车价要保守")
    if _num(row.get("inventory_cycle")) >= (stats.get("inventory_cycle", {}).get("q75") or math.inf):
        risks.append("库存周期偏长，存在周转压力")
    if _num(row.get("price_volatility")) >= (stats.get("price_volatility", {}).get("q75") or math.inf):
        risks.append("价格波动偏高，不能追高")
    if history.get("avg_gross_profit") is not None and _num(history.get("avg_gross_profit")) <= 0:
        risks.append("90天内部平均毛利偏低或为负")
    if history.get("sale_conversion_rate") is not None and _num(history.get("sale_conversion_rate")) < 0.08:
        risks.append("90天内部售车转化偏低")
    if str(row.get("market_category") or "") == "急跌行情":
        risks.insert(0, "近期价格快速下跌，收车需明显压价")
    elif str(row.get("market_category") or "") == "阴跌行情":
        risks.insert(0, "近期价格持续下行，收车价要保守")
    if not reasons:
        category_reason = {
            "上涨行情": "近期成交价格稳中有升",
            "流动行情": "成交活跃且价格相对稳定",
            "结构性行情": "供给与需求存在分化，需挑具体车源",
            "常规行情": "近期成交与价格表现相对稳定",
            "阴跌行情": "近期成交价格持续下行",
            "急跌行情": "近期成交价格快速下跌",
        }.get(str(row.get("market_category") or ""), "近期有可核验的成交与价格数据")
        reasons.append(category_reason)
    if not risks:
        risks.append("暂无强风险标签，仍需结合单车车况和目标利润")
    return reasons[:5], risks[:5]


def _level(score: float, category: str, history: dict[str, Any], *, value_score: float | None = None) -> tuple[str, str]:
    if category == "急跌行情" or score < 35:
        return "AVOID", "暂缓收"
    if category == "阴跌行情" or score < 50 or (value_score is not None and value_score < 42):
        return "CAUTION", "谨慎收"
    if history.get("avg_gross_profit") is not None and _num(history.get("avg_gross_profit")) < -1000:
        return "CAUTION", "谨慎收"
    if score >= 80 and (value_score is None or value_score >= 65):
        return "STRONG_RECOMMEND", "重点关注"
    if score >= 65 and (value_score is None or value_score >= 56):
        return "RECOMMEND", "可关注"
    return "WATCH", "正常跟踪"


def _purchase_price_range(row: dict[str, Any], history: dict[str, Any], level: str) -> dict[str, Any]:
    low = finite_number(row.get("deal_price_low_90d"))
    high = finite_number(row.get("deal_price_high_90d"))
    avg_sale = finite_number(history.get("avg_sale_price"))
    if avg_sale and (low is None or high is None):
        low = avg_sale * 0.92
        high = avg_sale * 1.04
    if low is None and high is None:
        return {"low": None, "high": None, "label": "需进入单车定价"}
    low = low if low is not None else high
    high = high if high is not None else low
    discount = {
        "STRONG_RECOMMEND": (0.82, 0.90),
        "RECOMMEND": (0.80, 0.88),
        "WATCH": (0.77, 0.85),
        "CAUTION": (0.72, 0.80),
        "AVOID": (0.66, 0.74),
    }.get(level, (0.76, 0.84))
    purchase_low = max(0, low * discount[0])
    purchase_high = max(purchase_low, high * discount[1])
    return {
        "low": round(purchase_low, 0),
        "high": round(purchase_high, 0),
        "label": f"{purchase_low / 10000:.2f}-{purchase_high / 10000:.2f}万",
        "basis": "按90天成交价区间倒推利润、整备和周转风险；最终以单车七要素定价为准",
    }


def _action(level: str) -> str:
    return {
        "STRONG_RECOMMEND": "进入重点关注池；找到具体车后进入单车定价",
        "RECOMMEND": "可作为候选车系；只在报价安全边界内推进",
        "WATCH": "先观察，不作为主动高价收车对象",
        "CAUTION": "谨慎收；优先选择低里程、好车况、低整备成本车源",
        "AVOID": "暂缓补库；已有库存优先去化",
    }.get(level, "人工复核后再推进")


def _ranking_evidence(city: Any, brand: Any, series: Any, limit: int = 2) -> dict[str, list[dict[str, Any]]]:
    try:
        from .ranking_signal_service import get_ranking_signal_service

        service = get_ranking_signal_service()
        city_text = str(city or "")
        is_national = not city_text or city_text == "全国"
        kwargs = {
            "city": None if is_national else city_text,
            "brand": str(brand or "") or None,
            "series": str(series or "") or None,
            "limit": max(limit, 40) if is_national else limit,
        }
        evidence = {
            "sales": service.get_sales_liquidity_evidence(**kwargs),
            "popular": service.get_popularity_evidence(**kwargs),
            "discount": service.get_discount_risk_evidence(**kwargs),
            "city": [] if is_national else service.get_city_preference_evidence(**kwargs),
        }
        if is_national:
            return {
                bucket: _national_ranking_summary(rows, bucket=bucket)
                for bucket, rows in evidence.items()
            }
        return evidence
    except Exception:
        return {}


def _ranking_selection_signal(
    *,
    city: Any,
    brand: Any,
    series: Any,
    vehicle_category: Any,
    energy_type: Any,
    price_band: Any,
) -> dict[str, Any]:
    try:
        from .ranking_signal_service import get_ranking_signal_service

        return get_ranking_signal_service().selection_signal_score(
            city=None if str(city or "") in {"", "全国", "全网"} else str(city),
            brand=str(brand or "") or None,
            series=str(series or "") or None,
            vehicle_category=str(vehicle_category or "") or None,
            energy_type=str(energy_type or "") or None,
            price_band=str(price_band or "") or None,
        )
    except Exception:
        return {
            "score": 50.0,
            "liquidity_score": 0.0,
            "demand_score": 0.0,
            "discount_risk_score": 0.0,
            "noise_penalty": 0.0,
            "match_level": "missing",
        }


def _national_ranking_summary(rows: list[dict[str, Any]], *, bucket: str) -> list[dict[str, Any]]:
    valid = [row for row in rows if row.get("evidence_text") != "暂无匹配榜单证据"]
    if not valid:
        return [{"evidence_text": "暂无匹配榜单证据", "business_interpretation": "暂无匹配榜单证据"}]
    national_rows = [row for row in valid if str(row.get("city") or "").strip() in {"", "全国"}]
    if national_rows:
        return national_rows[:1]
    ranks = [int(float(row.get("rank"))) for row in valid if finite_number(row.get("rank")) is not None]
    cities = {str(row.get("city") or "").strip() for row in valid if str(row.get("city") or "").strip()}
    rank_type = str(valid[0].get("rank_type") or {"sales": "销量榜", "popular": "热门榜", "discount": "降价榜"}.get(bucket, "排行榜"))
    top10 = sum(1 for rank in ranks if rank <= 10)
    interpretation = {
        "sales": "跨城市销量覆盖仅作外部流动性佐证，不能替代内部售出率、毛利和周转。",
        "popular": "跨城市关注热度不等于利润，热度越高也可能抬高车主报价预期。",
        "discount": "跨城市降价命中代表新车价格冲击，收车价和周转预期需要保守。",
    }.get(bucket, "全国查询不使用单一城市榜单冒充全国结论。")
    return [{
        "rank_type": rank_type,
        "rank": min(ranks) if ranks else None,
        "metric_name": "跨城市榜单覆盖",
        "metric_value": len(cities),
        "rank_date_text": valid[0].get("rank_date_text"),
        "evidence_text": f"{rank_type}跨城市命中{len(valid)}个筛选榜，覆盖{len(cities)}城，Top10命中{top10}次；未用单一城市结果冒充全国。",
        "business_interpretation": interpretation,
    }]


def _official_photo(brand: Any, series: Any) -> dict[str, Any] | None:
    try:
        from .dongchedi_official_photo_service import get_dongchedi_official_photo_service

        return get_dongchedi_official_photo_service().find_series_photo(brand=brand, series=series)
    except Exception:
        return None


def _compact_history_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_count_90d",
        "acquired_count_90d",
        "listed_count_90d",
        "sold_count_90d",
        "avg_gross_profit",
        "avg_turnover_days",
        "acquisition_conversion_rate",
        "sale_conversion_rate",
        "sold_from_acquired_rate",
        "listed_conversion_denominator",
        "acquired_conversion_denominator",
        "conversion_horizon_days",
        "loss_rate",
        "median_gross_profit",
        "total_gross_profit",
        "sample_quality",
        "metric_as_of",
        "metric_window_days",
        "history_scope",
        "history_scope_display",
        "requested_city",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _comparison_scope_label(slots: dict[str, Any], *, uses_national_fallback: bool = False) -> str:
    parts = ["全国" if uses_national_fallback else str(slots.get("city") or "全国")]
    price_band = slots.get("price_band") or {}
    if isinstance(price_band, dict) and price_band.get("label"):
        parts.append(str(price_band.get("label")))
    for value in (slots.get("fuel_type"), slots.get("selection_filter"), slots.get("brand_tier")):
        label = str(value or "").strip()
        if label and label not in {"全部", "全国"} and label not in parts:
            parts.append(label)
    return "、".join(parts) + "同条件候选基线"


def _compact_sample_confidence(payload: dict[str, Any]) -> dict[str, Any]:
    keys = ("confidence_score", "confidence_cap", "sample_level", "data_quality_note", "acquired_count", "sold_count")
    return {key: payload.get(key) for key in keys if key in payload}


def _compact_photo(photo: dict[str, Any] | None) -> dict[str, Any] | None:
    if not photo:
        return None
    keys = ("brand_name", "series_name", "image_url", "proxied_image_url", "validated_image_count", "source", "updated_at")
    return {key: photo.get(key) for key in keys if photo.get(key) not in (None, "")}


def _compact_ranking_evidence(evidence: dict[str, list[dict[str, Any]]] | None) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for bucket, rows in (evidence or {}).items():
        compact_rows = []
        for row in (rows or [])[:1]:
            compact_rows.append(
                {
                    key: row.get(key)
                    for key in (
                        "rank_type",
                        "rank",
                        "metric_name",
                        "metric_value",
                        "rank_date_text",
                        "evidence_text",
                        "business_interpretation",
                    )
                    if row.get(key) not in (None, "")
                }
            )
        if compact_rows:
            out[bucket] = compact_rows
    return out


def _latest_report_date() -> str:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    candidates: list[str] = []
    for directory in (root / "uploaded_reports", root / "outputs"):
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
            if match:
                candidates.append(match.group(1))
    return sorted(candidates)[-1] if candidates else ""


def _build_comparison(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "series": item.get("series"),
            "score": item.get("opportunity_score"),
            "action": item.get("action"),
            "advantages": item.get("reasons", [])[:3],
            "risks": item.get("risks", [])[:3],
            "suggested_purchase_price_range": item.get("suggested_purchase_price_range"),
        }
        for item in items[:6]
    ]


def _price_band_summary(items: list[dict[str, Any]], slots: dict[str, Any]) -> dict[str, Any]:
    if not slots.get("price_band"):
        return {}
    return {
        "price_band": slots.get("price_band"),
        "opportunity_series": [item.get("series") for item in items[:5]],
        "avoid_direction": list(dict.fromkeys(risk for item in items[-5:] for risk in item.get("risks", [])))[:5],
    }


def _target_label(target: Any) -> str:
    return {
        "recommend_series": "值得收车系",
        "risk_series": "风险车系识别",
        "compare_series": "车系对比",
        "price_band_opportunity": "价格带机会",
        "selection_to_pricing": "选品后定价",
        "series_judgement": "单车系是否值得收",
        "selection_reason": "选品推荐解释",
        "rank_lookup": "选品榜单排名查询",
        "score_explanation": "选品评分解释",
        "evidence_answer": "选品证据说明",
        "signal_ablation": "选品策略对照",
        "backtest_metrics": "选品回测指标",
        "baseline_answer": "选品基线口径",
        "total_profit_answer": "选品规模与利润",
        "data_quality_answer": "选品数据质量",
        "method_explanation": "选品计算逻辑",
        "policy_answer": "政策与新车影响",
        "module_boundary_answer": "选品能力边界",
    }.get(str(target or ""), "选品")


def _vehicle_label(brand: Any, series: Any, model_year: Any = None) -> str:
    brand_text = str(brand or "").strip()
    series_text = str(series or "").strip()
    if not series_text:
        return brand_text
    if brand_text and normalize_text(series_text).startswith(normalize_text(brand_text)):
        label = series_text
    else:
        label = f"{brand_text} {series_text}".strip()
    try:
        year_text = f" · {int(float(model_year))}款" if model_year not in (None, "") else ""
    except (TypeError, ValueError):
        year_text = ""
    return f"{label}{year_text}"


def _extract_ordinal(text: Any) -> int | None:
    match = re.search(r"第\s*(\d+|[一二三四五六七八九十两]+)", str(text or ""))
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return max(1, int(token))
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if token == "十":
        return 10
    if "十" in token:
        left, right = token.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return max(1, tens * 10 + ones)
    return max(1, digits.get(token, 1))


def _selection_answer_mode(slots: dict[str, Any]) -> str:
    requested = str(slots.get("requested_answer_mode") or "").strip()
    allowed = {
        "rank_answer",
        "exclusion_answer",
        "series_judgement",
        "score_explanation",
        "method_explanation",
        "evidence_answer",
        "backtest_answer",
        "baseline_answer",
        "data_quality_answer",
        "policy_answer",
        "module_boundary_answer",
        "task_card",
    }
    if requested in allowed:
        return requested
    return {
        "rank_lookup": "rank_answer",
        "selection_reason": "exclusion_answer",
        "series_judgement": "series_judgement",
        "score_explanation": "score_explanation",
        "method_explanation": "method_explanation",
        "evidence_answer": "evidence_answer",
        "signal_ablation": "method_explanation",
        "backtest_metrics": "backtest_answer",
        "baseline_answer": "baseline_answer",
        "total_profit_answer": "backtest_answer",
        "data_quality_answer": "data_quality_answer",
        "policy_answer": "policy_answer",
        "module_boundary_answer": "module_boundary_answer",
    }.get(str(slots.get("selection_target") or ""), "task_card")


def _selection_direct_answer(
    *,
    answer_mode: str,
    headline: str,
    slots: dict[str, Any],
    selection_explanation: dict[str, Any],
    recommendations: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    strategy: dict[str, Any],
    indicators: dict[str, Any],
    daily_report: dict[str, Any],
) -> dict[str, Any]:
    if answer_mode == "task_card":
        target = str(slots.get("selection_target") or "")
        if target in {"risk_series", "risk"}:
            avoid = [item for item in risk_items if item.get("business_avoid")]
            scope_parts = [str(slots.get("city") or "全国")]
            price_label = (slots.get("price_band") or {}).get("label") if isinstance(slots.get("price_band"), dict) else ""
            for value in (price_label, slots.get("fuel_type"), slots.get("selection_filter")):
                label = str(value or "").strip()
                if label and label not in {"全部", "全国"} and label not in scope_parts:
                    scope_parts.append(label)
            scope_text = "".join(scope_parts)
            if avoid:
                names = "、".join(_vehicle_label(item.get("brand"), item.get("series"), item.get("model_year")) for item in avoid[:3])
                conclusion = f"{scope_text}明确建议避免主动收的车系优先看{names}。这些车系通过了风险资格，不是把普通观察项强行列为避免收。"
                evidence_items = avoid[:3]
            else:
                conclusion = f"{scope_text}当前没有车系达到明确规避阈值；系统不会为了凑榜单把普通观察项标成避免收。"
                evidence_items = []
            evidence = []
            for item in evidence_items:
                subject = _vehicle_label(item.get("brand"), item.get("series"), item.get("model_year")) or "该车系"
                lines = _business_evidence_lines(item)
                evidence.append(f"{subject}：{lines[0] if lines else _business_decision_sentence(item, subject=subject)}")
            caveats = list(dict.fromkeys(
                str(reason) for item in evidence_items for reason in (item.get("risks") or [])
                if reason and not _is_internal_selection_reason(str(reason))
            ))[:3]
            return {
                "title": str(headline or conclusion),
                "conclusion": conclusion,
                "evidence": evidence,
                "caveats": caveats,
                "next_action": "避免主动补库；若遇到明显低价的具体车源，仍需进入单车定价核对安全收车边界。",
                "text": conclusion + ((" " + "；".join(evidence[:2])) if evidence else ""),
                "grounded": True,
                "llm_used": False,
            }
        active = [
            item for item in recommendations
            if item.get("business_recommend") or str(item.get("recommendation_label") or "") in {"重点关注", "可关注"}
        ]
        scope_parts = [str(slots.get("city") or "全国")]
        price_label = (slots.get("price_band") or {}).get("label") if isinstance(slots.get("price_band"), dict) else ""
        for value in (price_label, slots.get("fuel_type"), slots.get("selection_filter")):
            label = str(value or "").strip()
            if label and label not in {"全部", "全国"} and label not in scope_parts:
                scope_parts.append(label)
        scope_text = "".join(scope_parts)
        if active:
            names = "、".join(_vehicle_label(item.get("brand"), item.get("series"), item.get("model_year")) for item in active[:3])
            conclusion = f"{scope_text}当前推荐收{names}。其他车系没有进入推荐清单；只有达到明确风险阈值的车系才会进入避免收清单。"
            evidence_items = active[:3]
        else:
            conclusion = f"{scope_text}当前没有车系达到主动补库条件；系统没有用观察项补位，也不会把全部未推荐车系一概标为避免收。"
            evidence_items = recommendations[:3]
        evidence = []
        for item in evidence_items:
            subject = _vehicle_label(item.get("brand"), item.get("series"), item.get("model_year")) or "该车系"
            lines = _business_evidence_lines(item)
            evidence.append(f"{subject}：{lines[0] if lines else _business_decision_sentence(item, subject=subject)}")
        caveats = list(dict.fromkeys(
            str(reason) for item in evidence_items for reason in (item.get("risks") or [])
            if reason and not _is_internal_selection_reason(str(reason))
        ))[:4]
        next_action = "先按建议动作挑车系；找到具体车辆后，再补齐七要素进入单车定价。"
        answer_text = conclusion
        if evidence:
            answer_text += " " + "；".join(evidence[:2])
        return {
            "title": str(headline or conclusion),
            "conclusion": conclusion,
            "evidence": evidence,
            "caveats": caveats,
            "next_action": next_action,
            "text": answer_text,
            "grounded": True,
            "llm_used": False,
        }
    evidence: list[str] = []
    caveats: list[str] = []
    conclusion = str(selection_explanation.get("conclusion") or headline)
    title = str(selection_explanation.get("headline") or conclusion)
    next_action = str(selection_explanation.get("next_action") or "找到具体车辆后进入单车定价")

    if answer_mode in {"rank_answer", "exclusion_answer", "series_judgement"}:
        evidence = [str(item) for item in (selection_explanation.get("main_reasons") or []) if item]
        caveats = [str(item) for item in (selection_explanation.get("risk_reasons") or []) if item]
    elif answer_mode == "score_explanation":
        matched_items = selection_explanation.get("matched_series") or []
        item = matched_items[0] if isinstance(matched_items, list) and matched_items else (recommendations[0] if recommendations else {})
        subject = str(selection_explanation.get("subject") or item.get("series") or "该车系")
        title = f"为什么给出{subject}这个收车建议"
        if item:
            conclusion = str(selection_explanation.get("conclusion") or _business_decision_sentence(item, subject=subject))
            evidence = [str(reason) for reason in (selection_explanation.get("main_reasons") or _business_evidence_lines(item)) if reason]
            caveats = [str(reason) for reason in (selection_explanation.get("risk_reasons") or item.get("risks") or [])[:4]]
        else:
            conclusion = "当前筛选条件未命中可计算车系；选品分不会在无样本时强行生成。"
    elif answer_mode == "method_explanation":
        policy = (strategy.get("score_policy") or {}).get("selection_policy") or {}
        components = policy.get("ranking_components") or {}
        title = "选品排序与收车建议如何产生"
        conclusion = (
            "领导准入底池只由行情四类状态和DSI供需决定；"
            "底池内再用真实经营结果和懂车帝公开榜单证据排序；最后用正毛利、亏损率、样本不足和降价风险决定是否主动跟进或降级。"
            "资格、排序和风险各管一层，同一个信号不会重复加分。"
        )
        evidence = [
            "领导准入底池：行情须属于流动、结构性、上涨或常规行情，DSI供需须为供不应求或供需平衡；全国资格率依此口径计算。",
            (
                "排序层：真实收车转化"
                f"{float(components.get('acquisition') or 0):.0%}、"
                f"45天成熟上架车源售出率{float(components.get('sales') or 0):.0%}、"
                f"周转速度{float(components.get('turnover') or 0):.0%}、"
                f"利润质量{float(components.get('profit') or 0):.0%}、"
                f"公开排行榜证据{float(components.get('ranking') or 0):.0%}。"
            ),
            "真实收车转化是“买手首次合格出价的唯一车源，最终被B2C成功收下”的比例；它受车源供给和买手执行影响较大，因此只占10%。",
            "45天成熟上架车源售出率只看已经获得完整观察期的上架车源，直接反映库存能否转成成交，故权重高于收车转化。",
            "利润质量同时比较单车平均毛利和每个候选车源贡献的总毛利，避免只靠一两台高毛利个案冲榜。",
            "排行榜证据由懂车帝销量榜、热门榜/城市榜和新车降价榜共同形成：销量与热度提供流动性证据，降价榜作为残值风险扣分；它是外部辅助证据，不替代内部经营结果。",
            "主动跟进与风险层：有效售出样本少于10台只能观察；亏损率、负总毛利或降价风险会把结果降为暂缓或避免收，但不反向改写领导40%准入底池口径。",
        ]
        caveats = [
            "日报和政策事件只作当日风险说明，不进入排序分，避免同一市场信息重复计分。",
            "单车是否能收仍需补齐车型、上牌、里程、城市、过户、颜色和车况后定价。",
        ]
        next_action = "可继续问某个车系的分项得分、排名或未上榜原因"
    elif answer_mode == "evidence_answer":
        title = "这次选品使用了哪些证据"
        conclusion = (
            "证据分成资格、排序、主动跟进与风险三层：领导口径的行情状态和DSI供需只决定全国准入底池；"
            "底池内由内部90天经营结果与懂车帝公开榜单决定先后；正毛利、样本量、亏损率和新车降价风险决定是否主动跟进或降级，不修改40%底池口径。"
        )
        evidence = [
            f"行情数据：{indicators.get('data_scope') or '-'}，命中{len(indicators.get('rows') or [])}条。",
            "经营证据：最新90天按唯一车源去重后的真实收车转化、45天成熟上架车源售出率、周转、单车毛利、总毛利和亏损率。",
            "公开榜单证据：懂车帝销量榜、热门榜/城市榜和新车降价榜；销量与热度校验流动性，降价榜只做风险扣分。",
            f"日报事件：{'已命中，只作风险说明' if daily_report.get('available') else '本轮未命中，不强行补造事件证据'}。",
        ]
        caveats = ["挂牌、热度和排名不能代替内部成交与利润。", "外部信号缺失时会降级，不会编造命中。"]
        next_action = "可指定车系查看其证据明细"
    elif answer_mode in {"backtest_answer", "baseline_answer"}:
        report = _selection_backtest_snapshot()
        baseline = report.get("baseline") or {}
        selected = report.get("recommend") or {}
        title = "选品策略90天回测" if answer_mode == "backtest_answer" else "选品回测基线口径"
        if report:
            conclusion = (
                f"窗口{report.get('window_start')}至{report.get('window_end')}，推荐组覆盖{selected.get('candidate_count') or 0}个唯一车源；"
                f"平均毛利为全量{_ratio(selected.get('avg_profit'), baseline.get('avg_profit'))}，"
                f"成交周期为全量{_ratio(selected.get('avg_days_to_sell'), baseline.get('avg_days_to_sell'))}。"
            )
            evidence = [
                f"全量：平均毛利{_money(baseline.get('avg_profit'))}，成交周期{_days(baseline.get('avg_days_to_sell'))}。",
                f"推荐组：平均毛利{_money(selected.get('avg_profit'))}，成交周期{_days(selected.get('avg_days_to_sell'))}，售车转化{_pct(selected.get('sales_conversion_rate'))}。",
                f"选择率{_pct(selected.get('selection_rate'))}，总毛利保留率{_pct(selected.get('profit_retention_rate'))}。",
            ]
        else:
            conclusion = "当前没有加载到可审计的90天回测快照，不能口头声称达标。"
        caveats = ["真实收车转化按买手首个合格出价车源归因，并以最终B2C收车成功作为分子。", "回测是历史关联验证，不等同于随机实验因果结论。"]
        next_action = "可查看完整策略对照与样本明细"
    elif answer_mode == "data_quality_answer":
        audit = strategy.get("selection_audit") or {}
        title = "选品数据质量与样本要求"
        conclusion = "同一车源按唯一商品ID去重，经营证据限制在最新90天；证据覆盖不足的车系可以展示，但不会建议主动补库。"
        evidence = [
            f"本轮分析{audit.get('candidate_group_count') or 0}个车系，其中{audit.get('selected_count_after_sample_gate') or 0}个达到主动跟进条件。",
            f"本轮有{audit.get('excluded_due_to_low_sample_count') or 0}个车系因有效经营证据不足降为观察，不会用少量个案强行推荐。",
            *[str(note) for note in (indicators.get("notes") or [])[:3]],
        ]
        caveats = ["缺失字段会降低置信度或缩小可用范围，不会自动填成有利值。"]
    elif answer_mode == "policy_answer":
        title = "政策与新车事件如何影响选品"
        conclusion = "政策和新车事件只用于提示残值、降价与周转风险，不单独把车系推成推荐或规避。"
        evidence = [str(event.get("title") or event.get("summary") or event) for event in (daily_report.get("events") or [])[:4]]
        if not evidence:
            evidence = ["本轮没有命中与目标车系直接相关的事件，因此事件信号保持中性。"]
        caveats = ["最终标签仍以最新90天行情状态和内部经营结果为主。"]
    elif answer_mode == "module_boundary_answer":
        title = "选品与单车定价的边界"
        conclusion = "榜单只负责帮你找到值得看的车系；锁定具体车后，再进入单车定价，按七要素生成安全收车价和最高收车边界。"
        evidence = [
            "先确认标准车型、上牌时间、里程、城市、过户次数、颜色和车况，缺一项就先补齐，不拿车系均价硬估。",
            "定价模型会核对相近成交/在售样本和市场基线，再逐项计算七要素带来的上调或下调。",
            "最终同时给出建议挂牌价、预计实际售车价、建议收车价、最高收车价及各自区间，并保持价格梯度一致。",
        ]
        caveats = ["车系排名说明是否值得优先看，不直接决定某台车应该多少钱收。"]
        next_action = "找到具体车后，把七要素一次发来即可进入单车定价"

    evidence = list(dict.fromkeys(item for item in evidence if item))[:8]
    caveats = list(dict.fromkeys(item for item in caveats if item))[:6]
    text = conclusion
    if evidence:
        text += " " + "；".join(evidence[:2])
    return {
        "title": title,
        "conclusion": conclusion,
        "evidence": evidence,
        "caveats": caveats,
        "next_action": next_action,
        "text": text,
        "grounded": True,
        "llm_used": False,
    }


def _build_selection_task_execution(
    *,
    answer_mode: str,
    city: str,
    headline: str,
    direct_answer: dict[str, Any],
    selection_explanation: dict[str, Any],
    recommendations: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    indicators: dict[str, Any],
    daily_report: dict[str, Any],
    matched_count: int,
    comparable_count: int,
    report_date: Any,
) -> list[dict[str, Any]]:
    """Return only the real steps required by this specific question.

    The task plan and the completed execution card use the same names.  This
    prevents a short rank lookup from being presented as a fresh full-market
    selection run and prevents completion from replacing the live process.
    """

    answer_evidence = [str(item) for item in (direct_answer.get("evidence") or []) if item]
    answer_risks = [str(item) for item in (direct_answer.get("caveats") or []) if item]
    comparison_grain = "车型×年款" if city in {"", "全国", "全网"} else f"{city}×车系"

    def step(
        step_id: str,
        name: str,
        conclusion: str,
        evidence: list[str],
        impact: str,
        action: str,
        risk: str,
    ) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "name": name,
            "status": "done",
            "running_detail": f"正在{name}。",
            "detail": conclusion,
            "business_explanation": {
                "conclusion": conclusion,
                "evidence": evidence,
                "impact": impact,
                "action": action,
                "risk": risk,
            },
        }

    if answer_mode == "rank_answer":
        return [
            step(
                "selection_context_lookup",
                "定位榜单和查询名次",
                "已找到本次会话中最近一次同口径选品榜单。",
                [f"榜单范围：{city}", f"完整候选数：{len(recommendations)}"],
                "使用原榜单回答，不重跑一张可能变化的全量榜。",
                "继续核对指定名次。",
                "如会话中没有原榜单，应请用户先生成榜单。",
            ),
            step(
                "selection_rank_answer",
                "核对该名次并直接回答",
                str(direct_answer.get("conclusion") or headline),
                answer_evidence[:4] or [str(selection_explanation.get("headline") or headline)],
                "只回答用户问的名次，不用整张榜单淹没结论。",
                str(direct_answer.get("next_action") or "可继续查询该车系为什么位于这个名次。"),
                "；".join(answer_risks[:3]) or "榜单是车系级结果，不等于具体单车收车价。",
            ),
        ]

    if answer_mode in {"exclusion_answer", "series_judgement", "score_explanation"}:
        return [
            step(
                "selection_subject_lookup",
                "定位目标车系与原榜单",
                str(selection_explanation.get("headline") or "已定位目标车系和原榜单。"),
                [f"分析范围：{city}", f"候选车系：{len(recommendations)} 个"],
                "先确认车系和榜单口径，避免答成另一个同名或相近车系。",
                "继续核对经营证据。",
                "若车系未命中，不编造名次。",
            ),
            step(
                "selection_subject_evidence",
                "核对该车系的经营证据",
                "已核对成交、利润、周转、亏损和供需信号。",
                answer_evidence[:5] or [f"本轮命中 {matched_count} 条可用记录"],
                "这些数据决定该车系是主动跟进、观察还是暂缓。",
                "用同一口径解释排名。",
                "；".join(answer_risks[:3]) or "小样本和高亏损率会降低结论强度。",
            ),
            step(
                "selection_subject_answer",
                "解释排名或未推荐原因",
                str(direct_answer.get("conclusion") or headline),
                answer_evidence[:4] or [headline],
                "一线可直接看懂为什么给出当前标签。",
                str(direct_answer.get("next_action") or "找到具体车源后再进入单车定价。"),
                "；".join(answer_risks[:3]) or "车系级结论不能直接代替单车价格。",
            ),
        ]

    if answer_mode in {"method_explanation", "evidence_answer", "backtest_answer", "baseline_answer", "data_quality_answer", "module_boundary_answer"}:
        return [
            step(
                "selection_question_scope",
                "确认要查的策略问题",
                "已确认本轮查询的是策略逻辑、证据或口径，不重跑选品推荐。",
                [f"回答类型：{answer_mode}", f"分析范围：{city}"],
                "避免用一张新榜单回避用户问的方法问题。",
                "读取对应的可审计口径。",
                "本步不生成新排名。",
            ),
            step(
                "selection_audit_lookup",
                "读取对应的可审计口径",
                "已找到与当前问题相关的规则、指标和样本说明。",
                answer_evidence[:5] or [f"数据范围：{indicators.get('data_scope') or '当前安全数据'}"],
                "所有结论都能回到具体口径，不靠模板话术。",
                "把口径翻译成一线可理解的结论。",
                "口径说明不等于回测已证明因果。",
            ),
            step(
                "selection_audit_answer",
                "直接解释结论与边界",
                str(direct_answer.get("conclusion") or headline),
                answer_evidence[:5] or [headline],
                "一线可据此判断这个指标或证据到底有什么用。",
                str(direct_answer.get("next_action") or "可继续查看指定车系的证据明细。"),
                "；".join(answer_risks[:3]) or "不能把辅助信号当成唯一决策依据。",
            ),
        ]

    if answer_mode == "policy_answer":
        return [
            step(
                "selection_event_lookup",
                "检索相关日报与政策事件",
                f"{'已读取 ' + str(report_date) if report_date else '本轮没有命中直接相关事件'}。",
                [str(item.get("title") or item.get("summary") or item) for item in (daily_report.get("events") or [])[:4]] or ["未强行生成事件证据"],
                "只将相关事件作为风险背景。",
                "对照近90天经营证据。",
                "日报有时滞，不能代替当前成交。",
            ),
            step(
                "selection_event_business_check",
                "对照近90天经营证据",
                "已检查事件是否已体现在成交、价格、库存或周转中。",
                [f"命中记录：{matched_count} 条", f"可比较组合：{comparable_count} 个"],
                "事件与经营数据相互印证后才提高风险等级。",
                "说明对选品的实际影响。",
                "没有经营证据时不改写榜单。",
            ),
            step(
                "selection_event_answer",
                "说明事件影响与业务动作",
                str(direct_answer.get("conclusion") or headline),
                answer_evidence[:5] or [headline],
                "明确事件是强证据、弱证据还是仅作背景。",
                str(direct_answer.get("next_action") or "按最新90天经营表现继续观察。"),
                "；".join(answer_risks[:3]) or "不能因为一条新闻就直接推荐收车。",
            ),
        ]

    return [
        step(
            "selection_business_history",
            "读取近90天经营数据",
            "已读取去重车源、库存、周转、利润和亏损基础。",
            [f"数据范围：{indicators.get('data_scope') or '全国车系与年款'}", f"本轮命中 {matched_count} 条记录"],
            "真实经营数据是本轮选品的基础。",
            "继续核对可比较车系样本。",
            "本轮未要求日报时，不会额外调用日报影响排名。",
        ),
        step(
            "selection_comparable_scope",
            "核对可比较的车系样本",
            f"已找到 {matched_count} 条符合条件的记录，可与 {comparable_count} 个同口径组合比较。",
            [f"筛选范围：{city}", f"可比较{comparison_grain}组合：{comparable_count} 个"],
            f"只在同一预算、能源和车身口径内比较{comparison_grain}。",
            "继续计算供需、周转和价格风险。",
            "样本少的车系会降低推荐强度。",
        ),
        step(
            "selection_business_risk",
            "判断供需、周转和价格风险",
            "已将成交、库存、周转、价格趋势和供需状态放到同一口径判断。",
            ["最新90天去重经营证据", "库存与平均周转", "价格趋势、利润与亏损车占比"],
            "区分真正容易成交的机会和只有热度的风险车系。",
            "继续排出机会和风险车系。",
            "供需指数只是辅助证据，不替代经营实证。",
        ),
        step(
            "selection_rank_and_answer",
            "排出并解释机会车系与风险车系",
            str(direct_answer.get("conclusion") or headline),
            answer_evidence[:4] or [f"机会车系：{len(recommendations)} 个", f"风险候选：{len(risk_items)} 个"],
            "一线可直接知道先看哪些车系、为什么以及不能忽略哪些风险。",
            str(direct_answer.get("next_action") or "找到具体车源后，带七要素进入单车定价。"),
            "；".join(answer_risks[:3]) or "车系级推荐不能直接当成具体单车收车价。",
        ),
    ]


def _selection_backtest_snapshot() -> dict[str, Any]:
    try:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "results" / "evals" / "selection_profit_frontier_champion_20260713.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = payload.get("source") or {}
        return {
            "window_start": metadata.get("window_start"),
            "window_end": metadata.get("window_end"),
            "baseline": payload.get("baseline") or {},
            "recommend": payload.get("recommend_metrics") or {},
        }
    except Exception:
        return {}


def _ratio(value: Any, baseline: Any) -> str:
    current = finite_number(value)
    base = finite_number(baseline)
    return "-" if current is None or base in (None, 0) else f"{current / base:.3f}倍"


def _headline(
    city: Any,
    target_label: str,
    target: Any,
    top: dict[str, Any],
    strict_recommendations: list[dict[str, Any]],
    strict_avoid_items: list[dict[str, Any]],
    *,
    subject_lookup: dict[str, Any] | None = None,
) -> str:
    lookup = subject_lookup or {}
    if str(target) == "rank_lookup":
        matches = lookup.get("matches") or []
        if not matches:
            return f"{city}当前展示榜单没有{lookup.get('subject') or '这个名次'}。"
        best = matches[0]
        list_name = "推荐榜" if best.get("business_recommend") else "候选观察榜"
        return f"{city}{list_name}第{best.get('candidate_rank')}名是{_vehicle_label(best.get('brand'), best.get('series'), best.get('model_year'))}。"
    if str(target) == "selection_reason":
        matches = lookup.get("matches") or []
        subject = lookup.get("subject") or "该车系"
        if lookup.get("in_strict_recommend_pool"):
            strict_names = [item.get("series") for item in matches if item.get("business_recommend")][:3]
            return f"{subject}并非不在榜单：{'、'.join(str(name) for name in strict_names if name)}已列入主动跟进清单。"
        if matches:
            return f"{subject}已命中完整候选榜，但当前不建议主动跟进；最高候选位次第{matches[0].get('candidate_rank')}名。"
        return f"{city}{target_label}未命中可用车系"
    if str(target) in {"risk_series", "risk"}:
        if strict_avoid_items:
            item = strict_avoid_items[0]
            return f"{city}{target_label}优先暂缓：{_vehicle_label(item.get('brand'), item.get('series'), item.get('model_year'))}。"
        if top:
            return f"{city}{target_label}暂无四项均弱的硬规避车系，先关注单项风险：{_vehicle_label(top.get('brand'), top.get('series'))}。"
        return f"{city}{target_label}未命中可用车系"
    if str(target) in {"recommend_series", "price_band_opportunity", "selection_to_pricing"}:
        if strict_recommendations:
            item = strict_recommendations[0]
            return f"{city}{target_label}优先看：{_vehicle_label(item.get('brand'), item.get('series'), item.get('model_year'))}，建议：{item.get('recommendation_label', '')}。"
        if top:
            return f"{city}{target_label}暂无达到主动补库条件的车系，先观察：{_vehicle_label(top.get('brand'), top.get('series'))}。"
        return f"{city}{target_label}未命中可用车系"
    if str(target) == "series_judgement" and top:
        subject = _vehicle_label(top.get("brand"), top.get("series"))
        if top.get("business_recommend"):
            return f"{city}{subject}建议纳入可收候选，仍需按单车价格与车况复核。"
        if top.get("business_avoid"):
            return f"{city}{subject}当前建议暂缓主动收车。"
        return f"{city}{subject}当前不作主动推荐，建议观察或仅在安全报价内推进。"
    if top:
        return f"{city}{target_label}优先看{_vehicle_label(top.get('brand'), top.get('series'))}，建议：{top.get('recommendation_label', '')}。"
    return f"{city}{target_label}未命中可用车系"


def _understanding(slots: dict[str, Any]) -> list[str]:
    labels = []
    for key, label in (
        ("city", "城市"),
        ("price_band", "价格带"),
        ("brand", "品牌"),
        ("series", "车系"),
        ("time_window", "时间窗"),
        ("selection_target", "任务"),
    ):
        value = slots.get(key)
        if isinstance(value, dict):
            value = value.get("label")
        if value:
            labels.append(f"{label}：{value}")
    labels.extend(describe_category_scope(slots))
    brand_group = [str(item) for item in (slots.get("brand_group") or []) if str(item).strip()]
    if brand_group:
        labels.append(f"品牌组：{'/'.join(brand_group)}")
    return labels or ["未指定筛选条件，默认查看全国机会车系"]


def _key_findings(
    top: dict[str, Any],
    recommendations: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    *,
    slots: dict[str, Any] | None = None,
    strict_recommendations: list[dict[str, Any]] | None = None,
    selection_explanation: dict[str, Any] | None = None,
) -> list[str]:
    if (slots or {}).get("selection_target") in {"selection_reason", "rank_lookup"}:
        explanation = selection_explanation or _selection_explanation(slots or {}, recommendations, strict_recommendations or [], risk_items)
        findings = [explanation.get("conclusion") or "已按选品策略解释当前车系是否进入推荐池。"]
        findings.extend(explanation.get("main_reasons") or [])
        return findings[:5]
    if not top:
        return ["当前筛选条件未命中可用车系。"]
    active_count = len([
        item for item in recommendations
        if item.get("business_recommend") or str(item.get("recommendation_label") or "") in {"重点关注", "可关注"}
    ])
    return [
        f"本次输出{len(recommendations)}个候选车系，其中{active_count}个达到主动跟进条件。",
        f"首个候选：{_vehicle_label(top.get('brand'), top.get('series'))}，建议动作{top.get('recommendation_label') or '观察'}。",
        f"经营表现：单车典型毛利{_money(top.get('median_gross_profit'))}，亏损车占比{_pct(top.get('loss_rate'))}，平均周转{_days(top.get('avg_deal_cycle'))}。",
        f"本轮识别{len(risk_items)}个需要暂缓补库或谨慎报价的车系。",
    ]


def _business_suggestions(top: dict[str, Any], slots: dict[str, Any]) -> list[str]:
    if not top:
        return ["换城市、放宽价格带/能源条件，或转为单车定价。"]
    return [
        "机会车系只代表值得关注；最终能不能收取决于同款现价、车况和目标利润。",
        f"建议收车价区间：{(top.get('suggested_purchase_price_range') or {}).get('label') or '需进入单车定价'}。",
        "进入定价前必须补齐具体单车七要素，不按车系机会分直接给单车价。",
    ]


def _selection_explanation(
    slots: dict[str, Any],
    recommendations: list[dict[str, Any]],
    strict_recommendations: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    *,
    subject_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if slots.get("selection_target") in {
        "selection_reason",
        "rank_lookup",
        "score_explanation",
        "series_judgement",
        "evidence_answer",
    } and subject_lookup:
        return _subject_lookup_explanation(slots, subject_lookup)
    series = normalize_text(slots.get("series"))
    brand = normalize_text(slots.get("brand"))
    if brand and not series:
        brand_items = [
            item for item in recommendations
            if normalize_text(item.get("brand")) == brand
        ]
        brand_strict = [
            item for item in strict_recommendations
            if normalize_text(item.get("brand")) == brand
        ]
        brand_risks = [
            item for item in risk_items
            if normalize_text(item.get("brand")) == brand
        ]
        subject = slots.get("brand") or (brand_items[0].get("brand") if brand_items else "")
        if not brand_items:
            return {
                "subject": subject,
                "subject_type": "brand",
                "in_candidate_pool": False,
                "in_strict_recommend_pool": False,
                "headline": f"{subject}当前没有可直接执行的收车建议。",
                "conclusion": f"{subject}在当前筛选条件下没有足够的90天经营证据，暂不建议主动补库。",
                "main_reasons": ["可能是城市/价格带/能源筛选后无安全样本，或品牌名未映射到可用车系。"],
                "risk_reasons": [],
                "next_action": "放宽城市/价格带后重新选品，或指定具体车系查看原因",
                "matched_series": [],
            }
        blocked = [
            item for item in brand_items
            if not item.get("business_recommend")
        ]
        top_names = [str(item.get("series") or "").strip() for item in brand_items[:5] if item.get("series")]
        strict_names = [str(item.get("series") or "").strip() for item in brand_strict[:5] if item.get("series")]
        main_reasons: list[str] = []
        if brand_strict:
            main_reasons.append("建议主动跟进：" + "、".join(strict_names))
        else:
            main_reasons.append("该品牌下暂时没有车系同时满足样本、毛利、周转、收车和售车表现要求。")
        for item in blocked[:4]:
            label = str(item.get("series") or item.get("brand") or "")
            main_reasons.append(f"{label}：{_business_item_summary(item)}")
        conclusion = (
            f"{subject}当前建议重点跟进{'、'.join(strict_names)}；其他车系先观察，不建议按同样力度补库。"
            if brand_strict
            else f"{subject}当前没有建议主动补库的车系；可先观察{'、'.join(top_names[:3])}，找到具体车后再核价。"
        )
        return {
            "subject": str(subject),
            "subject_type": "brand",
            "in_candidate_pool": True,
            "in_strict_recommend_pool": bool(brand_strict),
            "headline": conclusion,
            "conclusion": conclusion,
            "main_reasons": main_reasons[:6],
            "risk_reasons": list(dict.fromkeys(risk for item in brand_risks[:5] for risk in (item.get("risks") or [])))[:5],
            "next_action": "指定具体车系后可进入单车系判断或单车定价",
            "matched_series": [
                {
                    "brand": item.get("brand"),
                    "series": item.get("series"),
                    "rank": item.get("rank"),
                    "opportunity_score": item.get("opportunity_score"),
                    "business_score": item.get("business_score"),
                    "confidence_score": item.get("confidence_score"),
                    "sample_level": item.get("sample_level"),
                    "sold_count_90d": item.get("sold_count_90d"),
                    "acquired_count_90d": item.get("acquired_count_90d"),
                    "recommendation_label": item.get("recommendation_label"),
                    "gate_reasons": item.get("gate_reasons") or [],
                }
                for item in brand_items[:12]
            ],
            "strict_series": [
                {"brand": item.get("brand"), "series": item.get("series"), "rank": item.get("rank")}
                for item in brand_strict[:12]
            ],
        }
    target = next(
        (
            item for item in recommendations
            if (series and normalize_text(item.get("series")) == series)
            or (not series and brand and normalize_text(item.get("brand")) == brand)
        ),
        recommendations[0] if recommendations else {},
    )
    if not target:
        return {
            "subject": slots.get("series") or slots.get("brand") or "",
            "in_candidate_pool": False,
            "in_strict_recommend_pool": False,
            "conclusion": "当前筛选条件没有命中可核验的同车系经营数据，暂时不能给出收车建议。",
            "main_reasons": ["请先核对车系识别；若车系正确，再放宽城市或价格带查看全国90天数据。"],
            "risk_reasons": [],
            "next_action": "放宽条件后重新选品",
        }
    target_series = normalize_text(target.get("series"))
    in_strict = any(normalize_text(item.get("series")) == target_series for item in strict_recommendations)
    ratios = target.get("business_metric_ratios") or {}
    evidence = _business_evidence_lines(target)
    target_label = _vehicle_label(target.get("brand"), target.get("series"))
    conclusion = _business_decision_sentence(target, subject=target_label)
    return {
        "subject": target_label,
        "in_candidate_pool": True,
        "in_strict_recommend_pool": in_strict,
        "opportunity_score": target.get("opportunity_score"),
        "business_score": target.get("business_score"),
        "confidence_score": target.get("confidence_score"),
        "sample_level": target.get("sample_level"),
        "sold_count_90d": target.get("sold_count_90d"),
        "acquired_count_90d": target.get("acquired_count_90d"),
        "total_profit_contribution": target.get("total_profit_contribution"),
        "recommendation_label": target.get("recommendation_label"),
        "metric_ratios": ratios,
        "conclusion": conclusion,
        "main_reasons": evidence[:5],
        "risk_reasons": [str(item) for item in (target.get("risks") or [])[:3] if item not in evidence],
        "suggested_purchase_price_range": target.get("suggested_purchase_price_range"),
        "next_action": target.get("action") or "找到具体车后进入单车定价",
        "nearby_risk_items": [
            {"brand": item.get("brand"), "series": item.get("series"), "risk_score": item.get("risk_score")}
            for item in risk_items[:5]
        ],
    }


def _subject_lookup_explanation(slots: dict[str, Any], lookup: dict[str, Any]) -> dict[str, Any]:
    subject = str(lookup.get("subject") or slots.get("series") or slots.get("brand") or "目标车系")
    matches = list(lookup.get("matches") or [])
    target = str(slots.get("selection_target") or "")
    if not matches:
        if target == "rank_lookup":
            return {
                "subject": subject,
                "subject_type": lookup.get("subject_type"),
                "in_candidate_pool": False,
                "in_strict_recommend_pool": False,
                "headline": f"当前展示榜单没有{subject}。",
                "conclusion": f"当前展示榜单不足{subject.replace('第', '').replace('名', '')}项，不能把其它名次的车代替回答。",
                "main_reasons": ["排名按当前页面同一筛选条件、同一排序快照从1开始读取。"],
                "risk_reasons": [],
                "next_action": "返回完整榜单或调整筛选条件后再查询",
                "matched_series": [],
            }
        return {
            "subject": subject,
            "subject_type": lookup.get("subject_type"),
            "in_candidate_pool": False,
            "in_strict_recommend_pool": False,
            "headline": f"{subject}未命中当前完整候选榜。",
            "conclusion": f"{subject}在当前地域、能源、车身和价格带口径下未命中可比车系，不能编造排名。",
            "main_reasons": ["先核对车系映射；若映射正确，则说明当前筛选口径没有足够的90天安全数据。"],
            "risk_reasons": [],
            "next_action": "核对车系名称或放宽筛选条件后重试",
            "matched_series": [],
        }
    best = matches[0]
    in_strict = bool(lookup.get("in_strict_recommend_pool"))
    in_top30 = bool(lookup.get("in_displayed_top30"))
    strict_matches = [item for item in matches if item.get("business_recommend")]
    if target == "rank_lookup":
        list_name = "推荐榜" if best.get("business_recommend") else "候选观察榜"
        headline = f"{list_name}第{best.get('candidate_rank')}名是{_vehicle_label(best.get('brand'), best.get('series'))}。"
        conclusion = headline
    elif in_strict:
        names = list(dict.fromkeys(
            str(item.get("series") or "") for item in strict_matches[:5] if item.get("series")
        ))
        if target == "series_judgement":
            headline = f"{subject}当前建议主动跟进。"
            conclusion = f"{subject}已通过主动收车资格，并进入当前口径的推荐池。"
        else:
            headline = f"{subject}并非不在榜单：{'、'.join(names)}已列入主动跟进清单。"
            conclusion = headline
    elif in_top30:
        headline = f"{subject}在前30候选榜中，但当前经营数据不支持主动补库。"
        conclusion = f"{subject}最高候选位次第{best.get('candidate_rank')}名；候选不等于建议主动收车。"
    else:
        headline = (
            f"{subject}当前不建议主动补库；已命中完整候选榜，但最高第"
            f"{best.get('candidate_rank')}名，未进入前30展示。"
        )
        conclusion = headline
    reasons: list[str] = []
    for item in matches[:3]:
        label = str(item.get("series") or item.get("brand") or "该车系")
        item_lines = _business_evidence_lines(item)
        for index, line in enumerate(item_lines[:8]):
            reasons.append(f"{label}：{line}" if index == 0 else line)
    if not reasons:
        reasons.append(
            f"完整候选池共{lookup.get('candidate_universe_size') or '-'}个车系，展示前{lookup.get('display_limit') or 30}个。"
        )
    return {
        "subject": subject,
        "subject_type": lookup.get("subject_type"),
        "in_candidate_pool": True,
        "in_displayed_top30": in_top30,
        "in_strict_recommend_pool": in_strict,
        "candidate_rank": best.get("candidate_rank"),
        "strict_rank": best.get("strict_rank"),
        "headline": headline,
        "conclusion": conclusion,
        "main_reasons": reasons[:8],
        "risk_reasons": list(dict.fromkeys(risk for item in matches[:5] for risk in (item.get("risks") or [])))[:5],
        "next_action": "查看具体车系分项，或找到具体车辆后进入单车定价",
        "matched_series": matches,
    }


def _business_decision_sentence(item: dict[str, Any], *, subject: str = "该车系") -> str:
    if item.get("business_recommend"):
        action = "建议重点跟进" if item.get("selection_level") == "STRONG_RECOMMEND" else "可以关注"
        return f"{subject}{action}，找到具体车辆后再按车况和目标利润核定最高收车价。"
    if item.get("business_avoid"):
        return f"{subject}当前建议暂缓主动收车，已有库存优先去化。"
    if str(item.get("recommendation_label") or "") in {"谨慎收", "暂缓收"}:
        return f"{subject}不建议高价主动收车，只在明显低于市场且单车利润可锁定时考虑。"
    return f"{subject}暂不建议主动补库，可继续观察或只在安全报价内看具体车辆。"


def _business_item_summary(item: dict[str, Any]) -> str:
    turnover = _days(item.get("avg_turnover_days") if item.get("avg_turnover_days") is not None else item.get("avg_deal_cycle"))
    margin = _money(item.get("avg_gross_profit") if item.get("avg_gross_profit") is not None else item.get("median_gross_profit"))
    loss_rate = _pct(item.get("loss_rate"))
    acquisition_rate = _pct(item.get("acquisition_conversion_rate"))
    sale_rate = _pct(item.get("sale_conversion_rate"))
    return (
        f"真实收车转化{acquisition_rate}、售车转化{sale_rate}，"
        f"平均周转{turnover}，单车平均毛利{margin}，亏损车占比{loss_rate}"
    )


def _business_baseline_comparison_lines(item: dict[str, Any]) -> list[str]:
    baseline = item.get("comparison_baseline") or {}
    if not isinstance(baseline, dict) or not baseline:
        return ["当前没有可核验的同条件基线，不能只凭绝对数判断排名高低。"]
    scope = str(item.get("comparison_scope") or "当前同条件候选基线")

    turnover = finite_number(item.get("avg_turnover_days") if item.get("avg_turnover_days") is not None else item.get("avg_deal_cycle"))
    base_turnover = finite_number(baseline.get("avg_turnover_days"))
    avg_profit = finite_number(item.get("avg_gross_profit") if item.get("avg_gross_profit") is not None else item.get("median_gross_profit"))
    base_profit = finite_number(baseline.get("avg_gross_profit"))
    acquisition = finite_number(item.get("acquisition_conversion_rate"))
    base_acquisition = finite_number(baseline.get("acquisition_conversion_rate"))
    sale = finite_number(item.get("sale_conversion_rate"))
    base_sale = finite_number(baseline.get("sale_conversion_rate"))
    loss = finite_number(item.get("loss_rate"))
    base_loss = finite_number(baseline.get("loss_rate"))

    lines: list[str] = []
    if acquisition is not None and base_acquisition is not None:
        lines.append(
            f"真实收车转化{_pct(acquisition)}，对比{scope}{_pct(base_acquisition)}，"
            f"{'高' if acquisition >= base_acquisition else '低'}{abs(acquisition - base_acquisition) * 100:.1f}个百分点。"
        )
    if sale is not None and base_sale is not None:
        lines.append(
            f"售车转化{_pct(sale)}，对比基线{_pct(base_sale)}，"
            f"{'高' if sale >= base_sale else '低'}{abs(sale - base_sale) * 100:.1f}个百分点。"
        )
    performance_parts: list[str] = []
    if turnover is not None and base_turnover is not None:
        performance_parts.append(
            f"周转{_days(turnover)}，比基线{_days(base_turnover)}{'快' if turnover <= base_turnover else '慢'}{abs(turnover - base_turnover):.1f}天"
        )
    if avg_profit is not None and base_profit is not None:
        performance_parts.append(
            f"单车平均毛利{_money(avg_profit)}，比基线{_money(base_profit)}{'高' if avg_profit >= base_profit else '低'}{_money(abs(avg_profit - base_profit))}"
        )
    if performance_parts:
        lines.append("；".join(performance_parts) + "。")
    if loss is not None and base_loss is not None:
        lines.append(
            f"亏损车占比{_pct(loss)}，对比基线{_pct(base_loss)}，"
            f"{'低' if loss <= base_loss else '高'}{abs(loss - base_loss) * 100:.1f}个百分点。"
        )

    ratios = item.get("business_metric_ratios") or {}
    positive: list[str] = []
    negative: list[str] = []
    metric_rules = (
        ("真实收车转化", ratios.get("acquisition_conversion_rate"), "high"),
        ("售车转化", ratios.get("sale_conversion_rate"), "high"),
        ("周转速度", ratios.get("avg_turnover_days"), "low"),
        ("单车毛利", ratios.get("avg_gross_profit"), "high"),
    )
    for label, raw_ratio, direction in metric_rules:
        ratio = finite_number(raw_ratio)
        if ratio is None:
            continue
        passed = ratio >= 1.1 if direction == "high" else ratio <= 0.9
        (positive if passed else negative).append(f"{label}{ratio:.2f}倍基线")
    if loss is not None and base_loss is not None:
        (positive if loss <= base_loss else negative).append(
            f"亏损率{'低于' if loss <= base_loss else '高于'}基线{abs(loss - base_loss) * 100:.1f}个百分点"
        )
    if positive or negative:
        lines.append(
            f"排名拉高项：{'、'.join(positive) if positive else '暂无明显优势'}；"
            f"排名拉低项：{'、'.join(negative) if negative else '暂无明显短板'}。"
        )
    return list(dict.fromkeys(lines))[:5]


def _business_evidence_lines(item: dict[str, Any]) -> list[str]:
    lines = [_business_item_summary(item) + "。"]
    lines.extend(_business_baseline_comparison_lines(item))
    purchase_label = str((item.get("suggested_purchase_price_range") or {}).get("label") or "").strip()
    if purchase_label and purchase_label != "需进入单车定价":
        lines.append(f"若继续看车，只在车况、里程和整备成本可控且车源报价落在{purchase_label}参考带内推进；最终仍以单车七要素定价的最高收车价为准。")
    dsi = item.get("dsi_signal") or {}
    dsi_label = str(dsi.get("label") or item.get("dsi_label") or "").strip() if isinstance(dsi, dict) else ""
    market_category = str(item.get("market_category") or "").strip()
    if market_category or (dsi_label and dsi_label != "未知"):
        lines.append(f"基础准入信号：行情为{market_category or '暂无明确状态'}，供需为{dsi_label or '暂无标签'}；它们只决定是否具备候选资格，最终名次仍由本车经营数据与同条件基线共同决定。")
    signed_profit = finite_number(item.get("national_series_total_profit_90d"))
    if signed_profit is not None:
        if signed_profit > 0:
            lines.append(f"近90天车系累计毛利{_money(signed_profit)}。")
        else:
            lines.append(f"近90天车系累计毛利{_money(signed_profit)}，整体没有形成正毛利。")
    for risk in item.get("risks") or []:
        text = str(risk or "").strip()
        if text and not _is_internal_selection_reason(text) and text not in lines:
            lines.append(text)
    return list(dict.fromkeys(lines))[:8]


def _is_internal_selection_reason(text: str) -> bool:
    return bool(
        re.search(
            r"门控|final_score|business_score|total_profit_contribution|leader_metrics|confidence_score|"
            r"sample_level|sold_count|acquired_count|loss_rate|median_gross_profit|risk_score",
            str(text or ""),
            flags=re.I,
        )
    )


def _money(value: Any) -> str:
    number = finite_number(value)
    return "-" if number is None else f"{number / 10000:.2f}万"


def _pct(value: Any) -> str:
    number = finite_number(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _days(value: Any) -> str:
    number = finite_number(value)
    return "-" if number is None else f"{number:.1f}天"


def build_selection_tools_response(query_text: str, selected_city: str = "全国", client_state: dict | None = None) -> dict[str, Any]:
    return SelectionToolsService().run(query_text, selected_city=selected_city, client_state=client_state or {})
