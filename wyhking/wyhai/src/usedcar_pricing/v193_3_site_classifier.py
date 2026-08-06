from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse

CLASSIFIER_VERSION = "v193_3_site_classifier_v1"
STRICT_PAGE_TYPES = {"single_vehicle_listing", "sold_single_vehicle_listing", "certified_used_vehicle_listing"}
WHITELIST_DOMAINS = (
    "che168.com",
    "2sc.autohome.com.cn",
    "autohome.com.cn",
    "guazi.com",
    "dongchedi.com",
    "bmw-emall.cn",
    "audi.cn",
    "audi.com.cn",
    "yiche.com",
    "bj2scmm.com",
    "bj2cars.com",
    "zs-group.com.cn",
)

@dataclass
class SiteClassification:
    source_domain: str
    source_family: str
    page_type: str
    page_type_confidence: float
    is_whitelisted_source: bool
    strict_eligible_page_type: bool
    reject_reason_if_not_eligible: str
    site_classifier_version: str = CLASSIFIER_VERSION


def source_domain(url: str) -> str:
    host = urlparse(str(url or "")).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def source_family(domain: str) -> str:
    d = domain.lower()
    if "guazi" in d:
        return "guazi"
    if "che168" in d or "2sc.autohome" in d or "autohome" in d:
        return "autohome_usedcar"
    if "dongchedi" in d:
        return "dongchedi"
    if "bmw-emall" in d:
        return "bmw_certified_used"
    if "audi" in d:
        return "audi_certified_used"
    if "yiche" in d or "bitauto" in d:
        return "yiche"
    if "bj2scmm" in d or "bj2cars" in d:
        return "beijing_used_market"
    if "zs-group" in d:
        return "certified_used"
    if "sina" in d:
        return "sina_article"
    if "sohu" in d:
        return "sohu"
    return d or "unknown"


def is_whitelisted(domain: str) -> bool:
    d = domain.lower()
    return any(item in d for item in WHITELIST_DOMAINS)


def classify_page(url: str, title: str = "", snippet: str = "", page_text: str = "") -> dict[str, Any]:
    domain = source_domain(url)
    family = source_family(domain)
    text = " ".join(str(x or "") for x in [title, snippet, page_text])
    lower_url = str(url or "").lower()
    compact = re.sub(r"\s+", "", text.lower())
    page_type = "unknown"
    confidence = 0.55

    if "sina" in domain or any(x in compact for x in ["资讯", "文章", "新闻", "导购", "评测"]):
        page_type = "news_article"
        confidence = 0.88
    if any(x in compact for x in ["报价_图片_参数", "参数配置", "车型参数", "官方指导价", "新车指导价", "指导价"] ) or "/spec/" in lower_url or "car.m.yiche.com" in lower_url or "db.auto.sohu.com" in lower_url:
        page_type = "new_car_parameter_page"
        confidence = 0.92
    if any(x in lower_url for x in ["/bj/", "/china/list", "/sell/default", "/car/default", "2sc.autohome.com.cn/"]) or any(x in compact for x in ["二手车列表", "共找到", "市场报价", "多款车源", "万起"]):
        if page_type == "unknown":
            page_type = "used_car_list_page"
            confidence = 0.78
    detail_url = any(x in lower_url for x in ["car-detail", "cardetail", "sell/info", "car/info", "usedcardetail", "mcar/info", "usedcardetail"])
    single_context = any(x in compact for x in ["上牌", "行驶里程", "过户", "车主报价", "已售", "车辆编号", "首次上牌", "表显里程"])
    if detail_url or single_context:
        if "已售" in compact or "成交" in compact:
            page_type = "sold_single_vehicle_listing"
            confidence = 0.9
        elif "官方认证" in compact or "认证二手车" in compact or "bmw-emall" in domain or "audi" in domain:
            page_type = "certified_used_vehicle_listing"
            confidence = 0.88
        elif page_type not in {"new_car_parameter_page", "news_article"}:
            page_type = "single_vehicle_listing"
            confidence = 0.86

    wl = is_whitelisted(domain)
    strict = wl and page_type in STRICT_PAGE_TYPES
    reason = "" if strict else ("SOURCE_NOT_WHITELISTED_FOR_STRICT" if not wl else "PAGE_TYPE_NOT_STRICT_ELIGIBLE")
    return asdict(SiteClassification(domain, family, page_type, confidence, wl, strict, reason))
