from __future__ import annotations

import re
from typing import Any

from usedcar_pricing.v193_2_market_evidence_schema import parse_price_yuan

CITY_RE = re.compile(r"(北京|上海|重庆|天津|广州|深圳|杭州|成都|武汉|南京|苏州|郑州|西安|长沙|宁波|青岛|济南|合肥|佛山|东莞|酒泉|唐山)")
YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*款|((?:19|20)\d{2})")
PRICE_RE = re.compile(r"(\d{1,4}(?:\.\d{1,2})?\s*万(?:元)?|\d{4,8}\s*元)")
MILEAGE_RE = re.compile(r"(\d{1,2}(?:\.\d{1,2})?\s*万公里|\d{3,6}\s*公里)")
PRICE_CONTEXT_HINTS = (
    "车主报价",
    "报价：",
    "报价:",
    "售价",
    "现价",
    "价格为",
    "价格",
    "价格：",
    "价格:",
    "成交价",
    "已售",
    "¥",
    "￥",
)
NON_LISTING_PRICE_HINTS = (
    "万公里",
    "公里",
    "新车裸车价",
    "指导价",
    "厂商指导价",
    "平台均价",
    "均价低",
    "立省",
    "省下",
    "低首付",
    "低月供",
    "月费率",
    "全款买车",
    "贷款买车",
)

def _first(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    return next((g for g in m.groups() if g), m.group(0))

def _candidate_price_score(text: str, match: re.Match[str]) -> tuple[int, str]:
    price_text = match.group(1)
    start, end = max(0, match.start() - 45), min(len(text), match.end() + 45)
    ctx = text[start:end]
    compact_ctx = ctx.replace(" ", "")
    compact_price = price_text.replace(" ", "")
    direct_price_pattern = re.search(r"(车主报价|售价|现价|价格为|价格|成交价|已售|[¥￥])[:：]?\s*[¥￥]?\s*" + re.escape(compact_price), compact_ctx)
    if re.search(re.escape(compact_price) + r"\s*公里", compact_ctx):
        return -100, ctx
    if any(hint in compact_ctx for hint in ("万公里", "公里/")) and not any(hint in compact_ctx for hint in PRICE_CONTEXT_HINTS):
        return -80, ctx
    if "起" in text[match.end() : match.end() + 3]:
        return -70, ctx
    if any(hint in compact_ctx for hint in ("立省", "省下", "均价低", "低约", "新车指导价低", "新车裸车价")) and not direct_price_pattern:
        return -70, ctx
    if any(hint in compact_ctx for hint in NON_LISTING_PRICE_HINTS) and not direct_price_pattern:
        return -50, ctx
    score = 0
    for hint in PRICE_CONTEXT_HINTS:
        if hint in compact_ctx:
            score += 25
    if re.search(r"[¥￥]\s*" + re.escape(compact_price), compact_ctx):
        score += 30
    if direct_price_pattern:
        score += 35
    yuan = parse_price_yuan(price_text)
    if yuan and yuan >= 10_000:
        score += 8
    if yuan and yuan < 5_000:
        score -= 20
    if "新车" in compact_ctx and "车主报价" not in compact_ctx and "售价" not in compact_ctx:
        score -= 30
    return score, ctx


def _price_with_context(text: str, fallback: str = "") -> tuple[float | None, str, str]:
    candidates = list(PRICE_RE.finditer(text))
    scored: list[tuple[int, re.Match[str], str]] = []
    for m in candidates:
        score, ctx = _candidate_price_score(text, m)
        scored.append((score, m, ctx))
    for score, m, ctx in sorted(scored, key=lambda x: x[0], reverse=True):
        if score <= 0:
            continue
        price_text = m.group(1)
        yuan = parse_price_yuan(price_text)
        if yuan:
            return yuan, price_text, ctx
    yuan = parse_price_yuan(fallback)
    return yuan, fallback, fallback

def _mileage_km(text: str) -> float | None:
    raw = _first(MILEAGE_RE, text)
    if not raw:
        return None
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*万公里", raw)
    if m:
        return float(m.group(1))*10000
    m = re.search(r"(\d{3,6})", raw)
    return float(m.group(1)) if m else None

class GenericAdapter:
    adapter_name = "generic_adapter"
    def extract(self, *, target: dict[str, Any], search_row: dict[str, Any], extract_row: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(x or "") for x in [search_row.get("title"), search_row.get("snippet"), extract_row.get("page_text_sample")])
        yuan, price_text, price_ctx = _price_with_context(text, str(extract_row.get("detected_price_text") or ""))
        year_text = _first(YEAR_RE, text)
        city = str(extract_row.get("detected_city") or _first(CITY_RE, text) or "")
        reject=[]
        if not classification.get("strict_eligible_page_type"):
            reject.append(str(classification.get("reject_reason_if_not_eligible") or "PAGE_TYPE_NOT_STRICT_ELIGIBLE"))
        if not yuan:
            reject.append("PRICE_MISSING")
        if price_text and yuan and abs((parse_price_yuan(price_text) or 0)-yuan)/max(yuan,1)>0.05:
            reject.append("PRICE_TEXT_PRICE_YUAN_MISMATCH")
        if price_text and (parse_price_yuan(price_text) or 0) and parse_price_yuan(price_text) != yuan:
            reject.append("PRICE_TEXT_PRICE_YUAN_MISMATCH")
        if "万起" in text or "起二手车" in text.replace(" ", ""):
            reject.append("LIST_PAGE_WITHOUT_SINGLE_VEHICLE_PRICE")
        if "共找到0辆车" in text.replace(" ", ""):
            reject.append("LIST_PAGE_WITHOUT_SINGLE_VEHICLE_PRICE")
        return {
            "source_url": search_row.get("url"),
            "source_domain": classification.get("source_domain"),
            "source_family": classification.get("source_family"),
            "page_type": classification.get("page_type"),
            "extraction_method": "html_text_regex",
            "adapter_name": self.adapter_name,
            "title": search_row.get("title") or extract_row.get("title") or "",
            "raw_text_excerpt": text[:1200],
            "price_yuan": yuan,
            "detected_price_text": price_text,
            "price_provenance_text": price_ctx,
            "city": city,
            "model_year": int(year_text[:4]) if year_text else None,
            "evidence_model_year_source": "web_text_year" if year_text else "missing",
            "brand": target.get("brand") or "",
            "series": target.get("series") or "",
            "trim": target.get("trim") or "",
            "mileage_km": _mileage_km(text),
            "license_date": "",
            "sold_or_active": "sold" if "已售" in text or "成交" in text else "active",
            "listing_id": "",
            "extraction_confidence": 0.7 if not reject else 0.35,
            "adapter_reject_reason_codes": reject,
        }
