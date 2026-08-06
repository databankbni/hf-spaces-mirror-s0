from __future__ import annotations

import html
import gzip
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


EXTRACTOR_VERSION = "v193_2_web_page_extractor_v1"
MAX_PAGE_BYTES = 160_000
MAX_TEXT_CHARS = 4000


@dataclass
class PageExtract:
    url: str
    title: str
    meta_description: str
    page_text_sample: str
    detected_price_text: str
    detected_city: str
    detected_mileage: str
    detected_model_year: str
    detected_trim: str
    detected_source_family: str
    extract_status: str
    extract_error: str = ""


def detect_source_family(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "autohome" in host or "che168" in host:
        return "autohome_che168"
    if "dongchedi" in host:
        return "dongchedi"
    if "guazi" in host:
        return "guazi"
    if "renrenche" in host:
        return "renrenche"
    if "yiche" in host or "bitauto" in host:
        return "yiche"
    if host:
        return host
    return "unknown"


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def _find(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I)
    return match.group(0) if match else ""


def extract_from_text(url: str, title: str = "", snippet: str = "", page_text: str = "") -> PageExtract:
    merged = " ".join([title or "", snippet or "", page_text or ""]).strip()
    text = _strip_html(merged)[:MAX_TEXT_CHARS]
    price = _find(r"((?:\d{1,3}(?:\.\d{1,2})?)\s*万(?:元)?|(?:\d{4,7})\s*元)", text)
    mileage = _find(r"(\d{1,2}(?:\.\d{1,2})?\s*万公里|\d{3,6}\s*公里)", text)
    year = _find(r"(19|20)\d{2}\s*款", text) or _find(r"(19|20)\d{2}", text)
    city = _find(r"(北京|上海|重庆|天津|广州|深圳|杭州|成都|武汉|南京|苏州|郑州|西安|长沙|宁波|青岛|济南|合肥|佛山|东莞)", text)
    return PageExtract(
        url=url,
        title=title,
        meta_description=snippet,
        page_text_sample=text,
        detected_price_text=price,
        detected_city=city,
        detected_mileage=mileage,
        detected_model_year=year,
        detected_trim="",
        detected_source_family=detect_source_family(url),
        extract_status="OK_TEXT_ONLY" if text else "EMPTY_TEXT",
        extract_error="",
    )


def fetch_and_extract(url: str, *, title: str = "", snippet: str = "", timeout: float = 6.0) -> PageExtract:
    if not url:
        return extract_from_text(url, title, snippet)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        result = extract_from_text(url, title, snippet)
        result.extract_status = "UNSUPPORTED_URL_SCHEME"
        return result
    start = time.time()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 usedcar-pricing-v193.2",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read(MAX_PAGE_BYTES)
            encoding = str(resp.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding:
                payload = gzip.decompress(payload)
            elif "deflate" in encoding:
                import zlib

                payload = zlib.decompress(payload)
            elif "br" in encoding:
                try:
                    import brotli

                    payload = brotli.decompress(payload)
                except Exception:
                    pass
            content_type = str(resp.headers.get("Content-Type") or "")
            charset_match = re.search(r"charset=([\\w\\-]+)", content_type, re.I)
            charset = charset_match.group(1) if charset_match else "utf-8"
            try:
                raw = payload.decode(charset, errors="replace")
            except LookupError:
                raw = payload.decode("utf-8", errors="replace")
        result = extract_from_text(url, title, snippet, raw)
        result.extract_status = "OK"
        return result
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as error:
        result = extract_from_text(url, title, snippet)
        result.extract_status = "FETCH_FAILED_WITH_SNIPPET" if result.page_text_sample else "FETCH_FAILED"
        result.extract_error = f"{type(error).__name__}: {str(error)[:300]} latency_ms={int((time.time() - start) * 1000)}"
        return result
