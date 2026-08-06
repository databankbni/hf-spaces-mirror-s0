"""Market report module service backed by online-safe workbook data."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .business_market_workbook_loader import finite_number, get_business_market_loader


PRICE_RANGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*万")
RANKING_ROOT = Path(__file__).resolve().parents[1] / "data/external/dongchedi_rankings/current"


def _num(value: Any, default: float = 0) -> float:
    number = finite_number(value)
    return number if number is not None else default


def _round(value: Any, digits: int = 2) -> float | None:
    number = finite_number(value)
    return round(number, digits) if number is not None else None


def _wan(value: Any) -> str:
    number = finite_number(value)
    if number is None:
        return "-"
    return f"{number / 10000:.2f}万"


def _state_label(row: dict[str, Any]) -> str:
    category = str(row.get("market_category") or "其他行情分类")
    if category == "结构性行情":
        return "结构性机会"
    if category == "流动行情":
        return "流通较好"
    if category == "上涨行情":
        return "价格上行"
    if category == "阴跌行情":
        return "价格偏弱"
    if category == "急跌行情":
        return "快速下跌"
    return category


def _row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "brand": row.get("brand"),
        "series": row.get("series"),
        "model": row.get("model"),
        "model_year": row.get("model_year"),
        "city": row.get("city"),
        "market_category": row.get("market_category"),
        "market_category_label": _state_label(row),
        "price_change_7d": _round(row.get("price_change_7d"), 6),
        "price_change_14d": _round(row.get("price_change_14d"), 6),
        "price_change_30d": _round(row.get("price_change_30d"), 6),
        "deal_sample_90d": int(_num(row.get("deal_sample_90d"))),
        "deal_price_low_90d": _round(row.get("deal_price_low_90d"), 0),
        "deal_price_high_90d": _round(row.get("deal_price_high_90d"), 0),
        "listing_count": int(_num(row.get("listing_count"))),
        "deal_count": int(_num(row.get("deal_count"))),
        "avg_deal_cycle": _round(row.get("avg_deal_cycle"), 1),
        "sell_through_rate": _round(row.get("sell_through_rate"), 2),
        "current_inventory": int(_num(row.get("current_inventory"))),
        "inventory_cycle": _round(row.get("inventory_cycle"), 1),
        "price_volatility": _round(row.get("price_volatility"), 4),
        "lead_rate": _round(row.get("lead_rate"), 2),
        "inquiry_conversion_rate": _round(row.get("inquiry_conversion_rate"), 2),
        "category_basis": row.get("category_basis"),
    }


def _business_read(row: dict[str, Any], *, scope_label: str) -> dict[str, Any]:
    category = str(row.get("market_category") or "")
    price_change_30d = _num(row.get("price_change_30d"), 0)
    cycle = _num(row.get("avg_deal_cycle") or row.get("inventory_cycle"), 0)
    volatility = _num(row.get("price_volatility"), 0)
    findings: list[str] = []
    risks: list[str] = []
    actions: list[str] = []
    if _num(row.get("deal_sample_90d")) >= 20:
        findings.append("近90天成交样本较充足")
    elif _num(row.get("deal_sample_90d")) > 0:
        findings.append("有成交样本，但数量有限")
    else:
        findings.append("成交样本不足，结论仅作观察")
    if category in {"结构性行情", "流动行情", "上涨行情"}:
        findings.append(f"{scope_label}呈现{_state_label(row)}")
        actions.append("可进入关注池，但单车仍要按同款现价定价")
    elif category in {"阴跌行情", "急跌行情"}:
        risks.append(f"{scope_label}{_state_label(row)}，报价要保守")
        actions.append("已有库存优先去化，新收车必须留足安全边际")
    else:
        actions.append("维持观察，等待更明确成交或需求信号")
    if price_change_30d <= -0.03:
        risks.append("30天价格下行，不能按高价样本追")
    elif price_change_30d >= 0.03:
        findings.append("30天价格有上行信号")
    if cycle >= 45:
        risks.append("成交/库存周期偏长，存在周转压力")
    if volatility >= 0.8:
        risks.append("价格波动较大，报价边界要收紧")
    if not risks:
        risks.append("暂无强风险标签，仍需结合车况和整备成本")
    return {
        "findings": findings[:4],
        "risks": risks[:4],
        "actions": actions[:4],
    }


def _item_from_row(row: dict[str, Any], rank: int, scope: str) -> dict[str, Any]:
    metrics = _row_metrics(row)
    read = _business_read(row, scope_label=scope)
    ranking_evidence = _ranking_evidence(row.get("city"), row.get("brand"), row.get("series"))
    return {
        "rank": rank,
        **metrics,
        "title": " ".join(str(part) for part in (row.get("brand"), row.get("series"), row.get("model"), row.get("model_year")) if part),
        "state_label": metrics["market_category_label"],
        "reason": "；".join(read["findings"][:2]),
        "risks": read["risks"],
        "action": read["actions"][0] if read["actions"] else "结合单车复核",
        "official_photo": _official_photo(row.get("brand"), row.get("series")),
        "ranking_evidence": ranking_evidence,
    }


def _official_photo(brand: Any, series: Any) -> dict[str, Any] | None:
    try:
        from .dongchedi_official_photo_service import get_dongchedi_official_photo_service

        return get_dongchedi_official_photo_service().find_series_photo(brand=brand, series=series)
    except Exception:
        return None


def _ranking_evidence(city: Any, brand: Any, series: Any) -> dict[str, list[dict[str, Any]]]:
    try:
        from .ranking_signal_service import get_ranking_signal_service

        service = get_ranking_signal_service()
        kwargs = {
            "city": str(city or "") if city and str(city) != "全国" else None,
            "brand": str(brand or "") or None,
            "series": str(series or "") or None,
            "limit": 3,
        }
        return {
            "sales": service.get_sales_liquidity_evidence(**kwargs),
            "popular": service.get_popularity_evidence(**kwargs),
            "discount": service.get_discount_risk_evidence(**kwargs),
            "city": service.get_city_preference_evidence(**kwargs),
        }
    except Exception:
        return {}


def _ranking_inventory() -> dict[str, Any]:
    path = RANKING_ROOT / "filter_inventory.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _ranking_snapshot_at() -> str:
    path = RANKING_ROOT / "crawl_manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("updated_at") or payload.get("run_started_at") or "")
    except Exception:
        return ""


def _discount_filters(text: str, inventory: dict[str, Any]) -> dict[str, str]:
    filters = inventory.get("filters") if isinstance(inventory.get("filters"), dict) else {}
    selected: dict[str, str] = {"city": "全国"}
    for key in ("city", "energy_type", "vehicle_category", "price_band", "manufacturer_attribute"):
        options = filters.get(key) if isinstance(filters, dict) else []
        values = [
            str(item.get("value") or item.get("label") or "")
            for item in options or []
            if isinstance(item, dict) and str(item.get("value") or item.get("label") or "") not in {"", "全部", "新能源" if key == "vehicle_category" else ""}
        ]
        matches = [value for value in values if value and value.lower() in text.lower()]
        if matches:
            selected[key] = max(matches, key=len)
    # “新能源”是能源类型，不把同名车身筛选重复计算。
    if "新能源" in text and "energy_type" not in selected:
        selected["energy_type"] = "新能源"
    return selected


def _discount_filter_options(inventory: dict[str, Any]) -> dict[str, list[str]]:
    filters = inventory.get("filters") if isinstance(inventory.get("filters"), dict) else {}
    result: dict[str, list[str]] = {}
    for key in ("energy_type", "vehicle_category", "price_band", "manufacturer_attribute"):
        values = [
            str(item.get("value") or item.get("label") or "")
            for item in (filters.get(key) or [])
            if isinstance(item, dict)
        ]
        if key == "vehicle_category":
            values = [value for value in values if value != "新能源"]
        result[key] = [value for value in values if value][:80]
    return result


def _discount_brand_lookup(text: str, inventory: dict[str, Any]) -> str | None:
    filters = inventory.get("filters") if isinstance(inventory.get("filters"), dict) else {}
    options = filters.get("brand") if isinstance(filters, dict) else []
    candidates = [
        str(item.get("value") or item.get("label") or "").strip()
        for item in options or []
        if isinstance(item, dict)
    ]
    compact = re.sub(r"\s+", "", str(text or "")).lower()
    matches = [brand for brand in candidates if brand and re.sub(r"\s+", "", brand).lower() in compact]
    if matches:
        return max(matches, key=len)
    raw = re.sub(r"^\s*(?:全国|国内|新车)[，,\s]*", "", str(text or "").strip())
    fallback_patterns = (
        r"^([A-Za-z0-9\u4e00-\u9fff·・\- ]{2,18}?)(?:在不在|是否在|有没有)(?:当前|全国)?(?:新车)?降价(?:榜|排行)",
        r"^([A-Za-z0-9\u4e00-\u9fff·・\- ]{2,18}?)(?:在)?(?:当前|全国)?(?:新车)?降价(?:榜|排行).{0,8}(?:排第几|排名|第几)",
    )
    for pattern in fallback_patterns:
        match = re.search(pattern, raw, flags=re.I)
        if match:
            return re.sub(r"\s+", "", match.group(1)).strip("，,。？? ")
    return None


def _build_discount_ranking_response(text: str) -> dict[str, Any]:
    from .ranking_signal_service import get_ranking_signal_service
    from .vehicle_taxonomy import get_vehicle_taxonomy_service

    inventory = _ranking_inventory()
    filters = _discount_filters(text, inventory)
    requested_brand = _discount_brand_lookup(text, inventory)
    board = get_ranking_signal_service().ranking_board(
        rank_type="降价榜",
        filters=filters,
        limit=700,
    )
    taxonomy = get_vehicle_taxonomy_service()
    verified_board: list[dict[str, Any]] = []
    for row in board:
        kwargs = {"brand": row.get("brand_name"), "series": row.get("series_name")}
        applied_slices = set(row.get("applied_filter_slices") or [])
        energy = filters.get("energy_type")
        category = filters.get("vehicle_category")
        manufacturer = filters.get("manufacturer_attribute")
        # The published single-dimension ranking slice is the primary evidence
        # for a selected filter.  Local taxonomy is only a fallback when that
        # slice was unavailable; otherwise newer brands without a local
        # manufacturer tag would be incorrectly removed after already passing
        # the official ranking filter.
        if (
            energy
            and f"energy_type={energy}" not in applied_slices
            and not taxonomy.matches_energy_subtype(**kwargs, energy_subtype=energy)
        ):
            continue
        if (
            category
            and f"vehicle_category={category}" not in applied_slices
            and not taxonomy.matches_vehicle_category(**kwargs, vehicle_category=category)
        ):
            continue
        if (
            manufacturer
            and f"manufacturer_attribute={manufacturer}" not in applied_slices
            and not taxonomy.matches_manufacturer_attribute(**kwargs, manufacturer_attribute=manufacturer)
        ):
            continue
        verified_board.append(row)
        if len(verified_board) >= 30:
            break
    board = verified_board
    items: list[dict[str, Any]] = []
    for display_rank, item in enumerate(board, start=1):
        metric = _num(item.get("metric_value"), 0)
        series = str(item.get("series_name") or "未知车系")
        brand = str(item.get("brand_name") or "")
        items.append(
            {
                "rank": display_rank,
                "published_rank": item.get("published_rank"),
                "brand": brand,
                "series": series,
                "title": f"{brand} {series}".strip(),
                "discount_wan": round(metric, 2),
                "metric_name": "新车经销商参考降价幅度",
                "reason": f"公开降价榜参考降幅 {metric:.2f} 万元",
                "risk": "新车降价可能压低同车系二手车残值，收车和库存报价需留安全边际。",
                "evidence_text": item.get("evidence_text"),
                "official_photo": _official_photo(brand, series),
            }
        )
    brand_matches = [
        item for item in items
        if requested_brand and requested_brand.lower() in str(item.get("brand") or "").lower()
    ]
    if requested_brand:
        if brand_matches:
            first = brand_matches[0]
            headline = (
                f"{requested_brand}在当前全国新车降价榜中，最高位车系为"
                f"{first.get('series')}，榜单第{first.get('rank')}名，参考降幅"
                f"{_num(first.get('discount_wan')):.2f}万元。"
            )
            items = brand_matches
        else:
            headline = f"{requested_brand}当前不在本次全国新车降价榜样本中。"
            items = []
    else:
        headline = (
            f"当前筛选命中 {len(items)} 个降价车系，榜首为{items[0]['series']}，参考降幅 {items[0]['discount_wan']:.2f} 万元。"
            if items
            else "当前筛选组合未命中降价榜车系，请减少一个筛选条件后重试。"
        )
    active = [f"{key}={value}" for key, value in filters.items() if value not in {"", "全国"}]
    snapshot_at = _ranking_snapshot_at()
    card = {
        "card_type": "market_report_agent",
        "report_kind": "discount_ranking",
        "title": "全国新车降价榜",
        "state_id": "discount_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
        "city": filters.get("city", "全国"),
        "query_text": text,
        "metrics": {
            "report_kind": "discount_ranking",
            "snapshot_at": snapshot_at,
            "source_url": inventory.get("source_url"),
            "active_filters": filters,
            "filter_options": _discount_filter_options(inventory),
            "brand_lookup": requested_brand,
        },
        "recommendations": items,
        "task_plan": {
            "goal": "查看全国新车降价榜",
            "understanding": ["只读取公开榜单证据", f"当前筛选：{'、'.join(active) if active else '全部'}"],
            "steps": ["识别榜单筛选条件", "读取对应公开榜单切片", "校验同一榜单排序", "输出残值风险提示"],
        },
        "task_execution": [
            {"step_id": "ranking_filter_tool", "name": "识别榜单筛选条件", "status": "done", "detail": f"已识别：{'、'.join(active) if active else '全国全部车系'}。"},
            {"step_id": "ranking_board_tool", "name": "读取懂车帝公开降价榜", "status": "done", "detail": f"已按同一筛选口径命中 {len(items)} 个车系。"},
            {"step_id": "ranking_risk_tool", "name": "解释二手车残值影响", "status": "done", "detail": "降价榜只作为新车价格冲击证据，不直接改写二手车估值。"},
        ],
        "summary_report": {
            "headline": headline,
            "key_findings": [f"榜单快照：{snapshot_at or '以本地已归档快照为准'}", f"当前筛选：{'、'.join(active) if active else '全部'}"],
            "business_suggestions": ["降幅靠前车系的新收车报价应更保守，并关注在库车去化。"],
            "risk_notes": ["公开榜单为新车经销商参考降价，不等于二手车实际成交跌幅。"],
            "data_quality_notes": ["各组合通过独立榜单切片交集筛选，避免混合多个互不相干的第一名。"],
        },
        "data_source": {"source": inventory.get("source"), "source_url": inventory.get("source_url"), "snapshot_at": snapshot_at},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"module": "market_state", "selected_city": filters.get("city", "全国"), "called_price": False, "market_agent_card": card}


def _build_national_market_response(text: str) -> dict[str, Any]:
    reports = sorted(
        (Path(__file__).resolve().parents[1] / "uploaded_reports").glob("national_market_*.json"),
        key=lambda path: path.name,
        reverse=True,
    )
    if not reports:
        card = {
            "card_type": "market_report_agent",
            "report_kind": "national_market",
            "title": "全国二手车行情研判",
            "metrics": {"report_kind": "national_market"},
            "recommendations": [],
            "summary_report": {"headline": "全国行情离线报告尚未生成", "key_findings": [], "business_suggestions": ["请先运行每日全国行情离线任务。"], "risk_notes": [], "data_quality_notes": []},
        }
        return {"module": "market_state", "selected_city": "全国", "called_price": False, "market_agent_card": card}
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    snapshot = payload.get("internal_snapshot") or {}
    headline = str(payload.get("headline") or "全国行情已生成")
    card = {
        "card_type": "market_report_agent",
        "report_kind": "national_market",
        "state_id": "national_" + hashlib.sha1(f"{payload.get('report_date')}|{text}".encode("utf-8")).hexdigest()[:12],
        "title": f"全国二手车行情研判｜{payload.get('report_date')}",
        "city": "全国",
        "query_text": text,
        "metrics": {
            "report_kind": "national_market",
            "report_date": payload.get("report_date"),
            "filename": payload.get("filename"),
            "file_url": payload.get("file_url"),
            "dashboard_cards": payload.get("dashboard_cards") or [],
            "dsi_snapshot": payload.get("dsi_snapshot") or {},
            "daily_digest": payload.get("daily_digest") or {},
            "discount_ranking": payload.get("discount_ranking") or [],
            "sections": payload.get("sections") or [],
        },
        "recommendations": [],
        "task_plan": {
            "goal": "读取今天已审核的全国二手车行情研判",
            "understanding": ["范围：全国", "口径：内部安全样本 + 权威外部验证", "执行方式：读取离线版本，避免每次搜索结果漂移"],
            "steps": ["读取内部结构化行情", "校验最新脱敏日报", "对齐全国权威数据与政策", "输出业务建议和数据边界"],
        },
        "task_execution": [
            {"step_id": "internal_market_snapshot", "name": "读取内部结构化行情", "status": "done", "detail": f"已读取 {snapshot.get('model_year_count', 0)} 个全国车型+年款组合和近90天经营结果。"},
            {"step_id": "dsi_weekly_migration", "name": "核对DSI周度迁移", "status": "done", "detail": f"共同车款 {int((payload.get('dsi_snapshot') or {}).get('common_vehicle_count') or 0):,} 个；改善 {int((payload.get('dsi_snapshot') or {}).get('improved_vehicle_count') or 0):,} 个。"},
            {"step_id": "daily_report_digest", "name": "提取最新脱敏日报精华", "status": "done", "detail": f"已读取 {str((payload.get('daily_digest') or {}).get('report_date') or payload.get('report_date'))} 脱敏日报，只保留影响二手车经营的事件。"},
            {"step_id": "external_market_validation", "name": "校验全国权威数据与政策", "status": "done", "detail": f"已核验 {len(payload.get('external_sources') or [])} 个权威外部来源。"},
            {"step_id": "national_market_report", "name": "生成全国行情研判", "status": "done", "detail": headline},
        ],
        "summary_report": {
            "headline": f"{headline}。{payload.get('summary') or ''}",
            "key_findings": [str(section.get("summary")) for section in payload.get("sections") or [] if isinstance(section, dict)][:3],
            "business_suggestions": ["打开 PDF 查看完整内部信号、全国外部验证、结构性行情和经营动作。"],
            "risk_notes": ["内部数据是懂车帝业务样本，不直接等同于全国市场。"],
            "data_quality_notes": ["每天离线生成并保存版本，用户查询时不临时自由搜索。"],
        },
        "data_source": {"metadata_file": reports[0].name, "external_source_count": len(payload.get("external_sources") or [])},
        "created_at": payload.get("created_at"),
    }
    return {"module": "market_state", "selected_city": "全国", "called_price": False, "market_agent_card": card}


def _select_rows(loader: Any, text: str, city: str) -> tuple[str, list[dict[str, Any]], str, list[str]]:
    notes: list[str] = []
    series = loader.find_series_in_text(text)
    brand = loader.find_brand_in_text(text)
    price_range = PRICE_RANGE_PATTERN.search(text)
    if city and city != "全国":
        rows = loader.filter_city_series(city=city, series=series, brand=brand)
        scope = "城市车系口径"
        if not rows and series:
            notes.append("当前城市未命中该车系，降级查看全国车型+年款口径。")
            rows = loader.filter_model_year(series=series)
            scope = "全国车型+年款口径"
    else:
        rows = loader.filter_model_year(series=series, brand=brand)
        scope = "全国车型+年款口径"
        if not rows:
            rows = loader.model_year_records
    if price_range:
        lower = float(price_range.group(1)) * 10000
        upper = float(price_range.group(2)) * 10000
        overlap = [
            row for row in rows
            if _num(row.get("deal_price_high_90d")) >= lower
            and (_num(row.get("deal_price_low_90d")) or math.inf) <= upper
        ]
        rows = overlap or rows
        notes.append(f"已识别{price_range.group(1)}-{price_range.group(2)}万价格带，按90天成交价范围近似匹配。")
    return scope, rows, series or brand or "市场整体", notes


def build_market_report_response(
    query_text: str,
    selected_city: str,
    client_state: dict | None = None,
) -> dict[str, Any]:
    loader = get_business_market_loader()
    text = str(query_text or "").strip() or "查看行情"
    if re.search(r"降价最多|降价(?:榜|排行)|降幅.*榜|新车降价", text):
        return _build_discount_ranking_response(text)
    if re.search(r"全国.*行情|行情.*全国|全国二手车|行情研判", text):
        return _build_national_market_response(text)
    detected_city = loader.find_city_in_text(text)
    wants_national = "全国" in text or "整体" in text
    city = "全国" if wants_national else (detected_city or str(selected_city or "全国").strip() or "全国")
    if not loader.available:
        card = {
            "card_type": "market_report_agent",
            "state_id": "mr_" + hashlib.sha1(f"{city}|{text}".encode("utf-8")).hexdigest()[:12],
            "city": city,
            "query_text": text,
            "recommendations": [],
            "metrics": {},
            "summary_report": {
                "headline": "行情数据不可用",
                "key_findings": ["未找到线上安全行情 workbook。"],
                "business_suggestions": ["请检查行情状态业务校准.xlsx 是否存在。"],
                "risk_notes": [],
                "data_quality_notes": [],
            },
        }
        return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}
    scope, rows, target, notes = _select_rows(loader, text, city)
    rows = rows[:200]
    rows.sort(
        key=lambda row: (
            -_num(row.get("deal_sample_90d")),
            _num(row.get("avg_deal_cycle"), 9999),
            -_num(row.get("listing_count")),
        )
    )
    if not rows:
        headline = f"{city}{target}暂无可用行情数据"
        recommendations: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        findings = ["当前查询在安全行情数据中未命中。"]
        risks = ["不要补造行情结论，改为换城市、换车系或转人工复核。"]
        actions = ["换一个城市或车系重新查询。"]
    else:
        top = rows[0]
        recommendations = [_item_from_row(row, index + 1, scope) for index, row in enumerate(rows[:12])]
        metrics = _row_metrics(top)
        read = _business_read(top, scope_label=target)
        price_range = f"{_wan(top.get('deal_price_low_90d'))}-{_wan(top.get('deal_price_high_90d'))}"
        headline = (
            f"{target}按{scope}看是{_state_label(top)}，"
            f"90天成交{int(_num(top.get('deal_sample_90d')))}辆，成交价约{price_range}。"
        )
        findings = read["findings"]
        risks = read["risks"]
        actions = read["actions"]
    card = {
        "card_type": "market_report_agent",
        "state_id": "mr_" + hashlib.sha1(f"{city}|{text}".encode("utf-8")).hexdigest()[:12],
        "city": city,
        "query_text": text,
        "scope": {"data_scope": scope, "target": target},
        "metrics": metrics,
        "recommendations": recommendations,
        "task_plan": {
            "goal": f"生成{target}行情报告",
            "understanding": [f"城市：{city}", f"对象：{target}", f"数据口径：{scope}"],
            "steps": [
                "识别查询范围",
                "读取行情与日报证据",
                "判断价格、成交、库存和周转",
                "整理行情结论和经营动作",
            ],
        },
        "task_execution": [
            {
                "step_id": "market_scope_tool",
                "name": "识别查询范围",
                "status": "done",
                "detail": f"已确认{city} · {target}，按{scope}查询。",
                "business_explanation": {
                    "conclusion": f"本轮分析对象是{city} · {target}。",
                    "evidence": [f"城市：{city}", f"对象：{target}", f"数据口径：{scope}"],
                    "impact": "先锁定同一查询范围，避免把全国和城市、车系和价格带混在一起。",
                    "action": "继续读取该范围内的行情与日报证据。",
                    "risk": "范围不一致会让成交、库存和价格趋势失真。",
                },
            },
            {
                "step_id": "market_evidence_tool",
                "name": "读取行情与日报证据",
                "status": "done",
                "detail": f"已命中{len(rows)}条当前查询范围内的安全行情记录。",
                "business_explanation": {
                    "conclusion": f"已读取 {len(rows)} 条可用于本轮判断的行情记录。",
                    "evidence": findings[:3] or ["当前范围可用样本较少"],
                    "impact": "这些证据用于判断真实市场表现，不用单一在售价代替行情。",
                    "action": "继续判断价格、成交、库存和周转状态。",
                    "risk": "样本不足时结论会更保守，并明确提示证据边界。",
                },
            },
            {
                "step_id": "market_state_tool",
                "name": "判断价格、成交、库存和周转",
                "status": "done",
                "detail": "已完成价格趋势、成交活跃、库存压力和周转速度判断。",
                "business_explanation": {
                    "conclusion": headline,
                    "evidence": findings[:4] or ["已完成当前范围行情指标计算"],
                    "impact": "把零散指标整理成市场强弱和风险边界，便于一线决定经营动作。",
                    "action": actions[0] if actions else "按当前行情边界控制报价和库存。",
                    "risk": "；".join(risks[:3]) if risks else "暂无额外强风险提示。",
                },
            },
            {
                "step_id": "market_response_composer",
                "name": "整理行情结论和经营动作",
                "status": "done",
                "detail": headline,
                "business_explanation": {
                    "conclusion": headline,
                    "evidence": findings[:3] or ["已整合价格、成交、库存和周转结果"],
                    "impact": "一线可直接看到结论、风险和下一步，不需要理解内部指标名称。",
                    "action": actions[0] if actions else "继续关注近7天价格和成交变化。",
                    "risk": "；".join(risks[:2]) if risks else "行情会变化，使用时关注数据日期。",
                },
            },
        ],
        "summary_report": {
            "headline": headline,
            "key_findings": findings,
            "business_suggestions": actions,
            "risk_notes": risks,
            "data_quality_notes": notes + [
                f"数据来自{loader.metadata.get('source_file')}的{scope}安全口径。",
                "线上不使用业务需打标sheet。",
            ],
        },
        "data_source": {
            "source_file": loader.metadata.get("source_file"),
            "source_sheet": "无需打标：车系+城市详情数据" if scope == "城市车系口径" else "无需打标：车型+年款详情数据",
            "data_scope": scope,
            "online_safe": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"module": "market_state", "selected_city": city, "called_price": False, "market_agent_card": card}
