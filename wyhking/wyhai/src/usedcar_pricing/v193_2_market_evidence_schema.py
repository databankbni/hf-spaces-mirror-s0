from __future__ import annotations

import re
from typing import Any

import pandas as pd


MARKET_EVIDENCE_SCHEMA_VERSION = "v193_2_market_evidence_schema_v1"
ALLOWED_PRICE_ROLES = {"B2C_LISTING", "B2C_SOLD", "C2B_PURCHASE", "UNKNOWN"}
ALLOWED_QUALITY = {"high", "medium", "low", "reject"}
EXTERNAL_LISTING_FAMILIES = {"autohome_che168", "dongchedi", "guazi", "renrenche", "yiche"}
USED_CAR_SOURCE_HINTS = {
    "guazi",
    "autohome_che168",
    "dongchedi",
    "renrenche",
    "yiche",
    "bj2scmm.com",
    "www.bj2scmm.com",
    "m.bj2scmm.com",
    "bj2cars.com",
    "www.bj2cars.com",
    "m.bj2cars.com",
    "zs-group.com.cn",
    "www.bmw-emall.cn",
}
PARAMETER_PAGE_HINTS = (
    "报价_图片_参数",
    "报价 - 汽车之家",
    "报价_图片_参数",
    "参数配置",
    "车型参数",
    "口碑",
    "图片",
    "资讯",
    "文章",
    "视频",
    "新车",
    "指导价",
    "裸车价",
)
POWER_CODES = ("320i", "320li", "325i", "325li", "330i", "330li", "40tfsi", "45tfsi", "40t", "45t", "25i", "28i", "30i", "2.0g", "2.5hg", "215km")
POWER_CODE_ALIASES = {"40t": "40tfsi", "45t": "45tfsi"}
CITY_NAMES = ("北京", "上海", "重庆", "天津", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "郑州", "西安", "长沙", "宁波", "青岛", "济南", "合肥", "佛山", "东莞", "酒泉", "济宁", "唐山")


def parse_price_yuan(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    text = str(value).replace(",", "").strip()
    match_wan = re.search(r"(\d{1,4}(?:\.\d{1,2})?)\s*万", text)
    if match_wan:
        return float(match_wan.group(1)) * 10000
    match_yuan = re.search(r"(\d{4,8})\s*元?", text)
    if match_yuan:
        return float(match_yuan.group(1))
    return None


def normalize_price_role(role: Any, *, source_family: str = "", text: str = "") -> str:
    raw = str(role or "").strip().upper()
    if raw in ALLOWED_PRICE_ROLES:
        normalized = raw
    elif "成交" in text or "已售" in text or "sold" in text.lower():
        normalized = "B2C_SOLD"
    elif source_family in EXTERNAL_LISTING_FAMILIES or "二手车" in text or "挂牌" in text:
        normalized = "B2C_LISTING"
    else:
        normalized = "UNKNOWN"
    if source_family in EXTERNAL_LISTING_FAMILIES and normalized == "C2B_PURCHASE":
        return "UNKNOWN"
    return normalized


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _extract_years(text: str) -> set[int]:
    years = set()
    for match in re.finditer(r"(19|20)\d{2}", text):
        try:
            years.add(int(match.group(0)))
        except Exception:
            pass
    return years


def _series_tokens(value: Any) -> set[str]:
    raw = _norm_text(value)
    tokens = {raw} if raw else set()
    aliases = {
        "宝马3系": {"宝马3系", "3系"},
        "凯美瑞": {"凯美瑞", "camry"},
        "奥迪q5l": {"奥迪q5l", "q5l"},
        "宝马x3": {"宝马x3", "x3"},
        "五菱宏光miniev": {"五菱宏光miniev", "宏光miniev", "miniev", "宏光mini"},
    }
    for key, vals in aliases.items():
        if key in raw or raw in vals:
            tokens |= vals
    return {t for t in tokens if t}


def _power_code(text: str) -> str:
    compact = _norm_text(text)
    for code in POWER_CODES:
        if code in compact:
            return POWER_CODE_ALIASES.get(code, code)
    return ""


def _price_suspected_from_mileage(text: str, price_text: Any, price_yuan: float | None) -> bool:
    raw_price_text = str(price_text or "")
    detected_yuan = parse_price_yuan(raw_price_text)
    if (
        raw_price_text
        and re.search(re.escape(raw_price_text) + r"\s*公里", text)
        and (not detected_yuan or not price_yuan or abs(detected_yuan - price_yuan) / max(price_yuan, 1.0) <= 0.05)
    ):
        return True
    if price_yuan and price_yuan < 80_000:
        wan = price_yuan / 10000
        pattern = rf"{wan:.2f}".rstrip("0").rstrip(".")
        if pattern and re.search(rf"{re.escape(pattern)}\s*万公里", text):
            return True
    return False


def _is_luxury_suv(record: dict[str, Any], text: str) -> bool:
    series_text = _norm_text(record.get("target_series") or record.get("series") or "")
    title_text = _norm_text(str(text or "")[:260])
    luxury_suv_tokens = ("奥迪q5", "q5l", "宝马x3", "x3", "宝马x1", "x1", "奔驰glc", "glc", "cayenne", "卡宴")
    if any(token in series_text for token in luxury_suv_tokens):
        return True
    return any(token in title_text for token in ("奥迪q5", "q5l", "宝马x3", "奔驰glc", "cayenne", "卡宴"))


def _dynamic_floor(record: dict[str, Any], text: str) -> float | None:
    series = _norm_text(record.get("target_series") or record.get("series") or text)
    year = pd.to_numeric(record.get("target_model_year") or record.get("model_year"), errors="coerce")
    if pd.isna(year):
        return None
    y = int(year)
    if ("宝马x3" in series or "x3" in series) and 2021 <= y <= 2022:
        return 150_000
    if ("奥迪q5l" in series or "q5l" in series) and 2021 <= y <= 2022:
        return 150_000
    if ("宝马3系" in series or "3系" in series) and y == 2021:
        return 100_000
    if "凯美瑞" in series and y == 2021:
        return 80_000
    return None


def _source_is_news_or_article(source_family: str, url: str, text: str) -> bool:
    host = str(source_family or "").lower()
    raw = str(url or "").lower()
    if "k.sina" in host or "k.sina" in raw or "/article" in raw:
        return True
    head = str(text or "")[:160]
    return ("资讯" in head or "文章" in head) and not _text_has_single_listing_context(text, url)


def _source_is_parameter_or_aggregate_page(source_family: str, url: str, text: str) -> bool:
    raw = str(url or "").lower()
    host = str(source_family or "").lower()
    if "car.m.yiche.com" in raw or "car.yiche.com" in raw or "db.auto.sohu.com" in raw or "/spec/" in raw:
        return True
    if "报价_图片_参数" in text or "参数配置" in text or "官方指导价" in text:
        return True
    if host in {"autohome_che168", "sohu", "yiche"} and ("指导价" in text or "本市最低价" in text):
        return True
    return False


def _source_is_list_page(url: str, text: str) -> bool:
    raw = str(url or "").lower()
    list_patterns = (
        "2sc.autohome.com.cn/",
        "/sell/default",
        "/bj/bmw/",
        "/jiuquan/wuling/",
        "/yanbianshi/wuling/",
        "/shanghai/wuling",
    )
    if any(pattern in raw for pattern in list_patterns):
        return True
    if "市场报价" in text or "二手车 - 汽车之家" in text or "二手车- 汽车之家" in text:
        return True
    return False


def _text_has_single_listing_context(text: str, url: str) -> bool:
    raw = str(url or "").lower()
    if any(pattern in raw for pattern in ("car-detail", "usedcardetail", "sell/info", "car/info")):
        return True
    return bool(re.search(r"(车辆编号|车辆所属|上牌年月|初次上牌|行驶里程|过户次数|车主报价|已售|官方二手车)", text))


def _evidence_city(text: str, city_value: Any) -> str:
    city = str(city_value or "").strip()
    if city:
        return city
    for candidate in CITY_NAMES:
        if candidate in text:
            return candidate
    return ""


def _price_text_variants(price_yuan: float | None) -> set[str]:
    if price_yuan is None or price_yuan <= 0:
        return set()
    wan = price_yuan / 10000
    variants = {
        f"{wan:.2f}万",
        f"{wan:.1f}万",
        f"{wan:g}万",
        f"{price_yuan:.0f}元",
        f"{int(round(price_yuan)):,}",
        f"{int(round(price_yuan))}",
    }
    return {v.replace(".00万", "万") for v in variants}


def _price_traceable_to_single_listing(record: dict[str, Any], text: str, price_yuan: float | None) -> bool:
    if price_yuan is None or price_yuan <= 0:
        return False
    variants = _price_text_variants(price_yuan)
    compact_text = str(text or "").replace(",", "")
    has_price = any(v.replace(",", "") in compact_text for v in variants)
    if not has_price:
        return False
    if "起" in compact_text and any(v.replace(",", "") + "起" in compact_text for v in variants):
        return False
    return _text_has_single_listing_context(text, str(record.get("url") or ""))


def validate_market_evidence(record: dict[str, Any]) -> dict[str, Any]:
    source_family = str(record.get("source_family") or "").strip() or "unknown"
    # Strict validation must inspect only observed web text. Do not append
    # target-filled trim/model fields here; doing so can hide real 40T/45T or
    # 320i/325i mismatches.
    text = " ".join(str(record.get(k) or "") for k in ["title", "snippet", "page_text_sample"])
    text_norm = _norm_text(text)
    price_role = normalize_price_role(record.get("price_role"), source_family=source_family, text=text)
    price_yuan = parse_price_yuan(record.get("price_yuan") if record.get("price_yuan") is not None else record.get("detected_price_text"))
    url = str(record.get("url") or "")
    relevant = bool(record.get("is_relevant_to_target", False))
    listing = bool(record.get("is_vehicle_listing", False))
    reasons: list[str] = []
    quality = str(record.get("evidence_quality") or "low").lower()
    if quality not in ALLOWED_QUALITY:
        quality = "reject"
        reasons.append("INVALID_EVIDENCE_QUALITY")
    raw_risk_flags = record.get("risk_flags", [])
    if isinstance(raw_risk_flags, list):
        risk_text = " ".join(str(x) for x in raw_risk_flags)
    else:
        risk_text = str(raw_risk_flags)
    if "qwen_quality=reject" in risk_text or quality == "reject":
        reasons.append("QWEN_MARKED_REJECT")
    if not url:
        reasons.append("MISSING_URL")
    if not listing:
        reasons.append("NOT_VEHICLE_LISTING")
    if not relevant:
        reasons.append("NOT_RELEVANT_TO_TARGET")
    if price_yuan is None or price_yuan <= 0:
        reasons.append("PRICE_MISSING")
    if price_role == "UNKNOWN":
        reasons.append("PRICE_ROLE_UNKNOWN")
    if price_role == "C2B_PURCHASE" and source_family in EXTERNAL_LISTING_FAMILIES:
        reasons.append("EXTERNAL_C2B_ROLE_BLOCKED")
        price_role = "UNKNOWN"
    if record.get("binary_garbage_flag") is True or str(record.get("binary_garbage_flag")).lower() == "true":
        reasons.append("BINARY_GARBAGE_PAGE_TEXT")
    if str(record.get("page_text_quality") or "").lower() == "low":
        reasons.append("LOW_TEXT_QUALITY")
    if record.get("is_whitelisted_source") is False or str(record.get("whitelist_status") or "").lower() in {"not_whitelisted", "false"}:
        reasons.append("SOURCE_NOT_WHITELISTED_FOR_STRICT")
    if record.get("strict_eligible_page_type") is False or str(record.get("strict_eligible_page_type")).lower() == "false":
        reasons.append("PAGE_TYPE_NOT_STRICT_ELIGIBLE")
    if _source_is_news_or_article(source_family, url, text):
        reasons.append("NEWS_OR_ARTICLE_PAGE")
        price_role = "UNKNOWN"
    if _source_is_parameter_or_aggregate_page(source_family, url, text):
        reasons.append("PARAMETER_OR_AGGREGATE_PAGE")
    if _source_is_list_page(url, text):
        reasons.append("LIST_PAGE_WITHOUT_SINGLE_VEHICLE_PRICE")
    if not _text_has_single_listing_context(text, url):
        reasons.append("NOT_SINGLE_VEHICLE_LISTING")
    target_year = pd.to_numeric(record.get("target_model_year"), errors="coerce")
    evidence_year = pd.to_numeric(record.get("model_year"), errors="coerce")
    evidence_year_source = str(record.get("evidence_model_year_source") or "").strip()
    text_years = _extract_years(text)
    if evidence_year_source == "target_fallback" or (not pd.isna(target_year) and not pd.isna(evidence_year) and int(evidence_year) == int(target_year) and int(target_year) not in text_years):
        reasons.append("EVIDENCE_YEAR_OVERWRITTEN_BY_TARGET")
    if not pd.isna(target_year) and not pd.isna(evidence_year) and int(target_year) != int(evidence_year):
        reasons.append("MODEL_YEAR_MISMATCH")
    target_city = str(record.get("target_city") or "").strip()
    city = _evidence_city(text, record.get("city"))
    if target_city and city and target_city != city:
        reasons.append("CITY_MISMATCH")
    target_series = record.get("target_series") or record.get("series")
    if target_series:
        tokens = _series_tokens(target_series)
        if tokens and not any(token in text_norm for token in tokens):
            reasons.append("SERIES_MISMATCH")
    target_trim = str(record.get("target_trim") or record.get("trim") or "")
    target_power = _power_code(target_trim)
    evidence_power = target_power if target_power and target_power in text_norm else _power_code(text)
    if target_power and evidence_power and target_power != evidence_power:
        reasons.append("TRIM_POWER_MISMATCH")
    target_trim_norm = _norm_text(target_trim)
    if target_trim_norm and len(target_trim_norm) >= 3:
        target_tokens = [t for t in re.split(r"[|/\\s,，]+", target_trim_norm) if len(t) >= 3]
        if target_tokens and not any(t in text_norm for t in target_tokens[:3]):
            reasons.append("TRIM_MISMATCH")
    if any(hint.lower() in text.lower() for hint in PARAMETER_PAGE_HINTS):
        used_price_context = any(hint in text for hint in ("二手车", "已售", "车主报价", "卖车", "个人出售", "官方二手车", "二手车买卖"))
        if not used_price_context:
            reasons.append("NEW_CAR_OR_PARAMETER_PAGE")
    if not _price_traceable_to_single_listing(record, text, price_yuan):
        reasons.append("PRICE_NOT_TRACEABLE_TO_SINGLE_LISTING")
    if _price_suspected_from_mileage(text, record.get("detected_price_text"), price_yuan):
        reasons.append("PRICE_SUSPECTED_FROM_MILEAGE")
    floor = _dynamic_floor(record, text)
    if floor is not None and price_yuan is not None and price_yuan < floor:
        reasons.append("LUXURY_SUV_BELOW_DYNAMIC_FLOOR")
    elif _is_luxury_suv(record, text) and price_yuan is not None and price_yuan < 80_000:
        reasons.append("LUXURY_SUV_BELOW_REASONABLE_FLOOR")
    adapter_reasons = record.get("adapter_reject_reason_codes")
    if isinstance(adapter_reasons, list):
        reasons.extend(str(x) for x in adapter_reasons if x)
    elif isinstance(adapter_reasons, str) and adapter_reasons.strip():
        reasons.extend(x for x in adapter_reasons.split("|") if x)
    if source_family not in USED_CAR_SOURCE_HINTS:
        explicit_used_price = bool(re.search(r"(二手车|已售|车主报价|官方二手车|个人出售|卖车|万元已售|挂牌)", text))
        if not explicit_used_price:
            reasons.append("NON_LISTING_SOURCE_WITHOUT_USED_PRICE")
    if reasons:
        quality = "reject"
    confidence = pd.to_numeric(record.get("confidence"), errors="coerce")
    if pd.isna(confidence):
        confidence = 0.0
    return {
        **record,
        "price_yuan": price_yuan,
        "price_role": price_role,
        "source_family": source_family,
        "evidence_quality": quality,
        "schema_valid": len(reasons) == 0,
        "schema_reject_reason_codes": reasons,
        "confidence": float(max(0.0, min(1.0, confidence))),
        "can_enter_baseline": False,
        "can_enter_interval": len(reasons) == 0 and price_role in {"B2C_LISTING", "B2C_SOLD"},
        "can_enter_manual_reference": len(reasons) == 0,
        "schema_version": MARKET_EVIDENCE_SCHEMA_VERSION,
    }


def dedupe_key(record: dict[str, Any]) -> str:
    price = parse_price_yuan(record.get("price_yuan")) or 0
    mileage = pd.to_numeric(record.get("mileage_km"), errors="coerce")
    mileage_bucket = "unknown" if pd.isna(mileage) else str(int(float(mileage) // 10000))
    price_bucket = str(int(price // 5000)) if price else "unknown"
    title = re.sub(r"\W+", "", str(record.get("title") or record.get("trim") or ""))[:24]
    return "|".join(
        [
            str(record.get("canonical_trim_key") or ""),
            str(record.get("city") or ""),
            mileage_bucket,
            price_bucket,
            str(record.get("source_family") or ""),
            title,
        ]
    )
