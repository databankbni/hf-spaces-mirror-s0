from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from .v193_2_web_page_extractor import fetch_and_extract, extract_from_text


EXTRACTOR_VERSION = "v193_3_web_page_extractor_v1"


def _text_quality(text: str) -> dict[str, Any]:
    raw = str(text or "")
    total = max(len(raw), 1)
    readable_chars = sum(1 for ch in raw if ch.isprintable() and (ch.isalnum() or ch.isspace() or "\u4e00" <= ch <= "\u9fff" or ch in "，。；：、.-_/()（）[]【】"))
    chinese_chars = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
    replacement = raw.count("\ufffd")
    readable_ratio = readable_chars / total
    chinese_ratio = chinese_chars / total
    listing_signal = bool(re.search(r"(二手车|车主报价|售价|现价|价格为|成交价|具体车况|上牌|行驶里程|过户)", raw))
    binary_flag = replacement > 20 or readable_ratio < 0.45
    quality = "high"
    if binary_flag or readable_ratio < 0.55:
        quality = "low"
    elif raw and chinese_ratio < 0.02 and listing_signal:
        quality = "medium"
    elif raw and chinese_ratio < 0.02:
        quality = "low"
    elif readable_ratio < 0.72 or chinese_ratio < 0.08:
        quality = "medium"
    return {
        "html_text_length": total,
        "readable_text_length": readable_chars,
        "readable_text_ratio": round(readable_ratio, 6),
        "chinese_char_ratio": round(chinese_ratio, 6),
        "binary_garbage_flag": bool(binary_flag),
        "page_text_quality": quality,
    }


def extract_url_record(url: str, *, title: str = "", snippet: str = "", timeout: float = 2.0) -> dict[str, Any]:
    full_page_fetch_attempted = bool(url)
    result = fetch_and_extract(url, title=title, snippet=snippet, timeout=timeout)
    full_page_fetch_success = result.extract_status == "OK"
    snippet_result = extract_from_text(url, title, snippet)
    snippet_extract_success = bool(snippet_result.page_text_sample)
    if not full_page_fetch_success and snippet_extract_success:
        result = snippet_result
        result.extract_status = "STRUCTURED_FROM_SEARCH_SNIPPET_ONLY"
    row = asdict(result)
    row["extractor_version"] = EXTRACTOR_VERSION
    row["snippet_extract_success"] = snippet_extract_success
    row["full_page_fetch_attempted"] = full_page_fetch_attempted
    row["full_page_fetch_success"] = full_page_fetch_success
    row["fetch_method"] = "urllib"
    row["used_snippet_fallback"] = int(not full_page_fetch_success and snippet_extract_success)
    row["snippet_fallback_used"] = row["used_snippet_fallback"]
    row["extraction_source"] = "full_page" if full_page_fetch_success else ("snippet_fallback" if snippet_extract_success else "failed")
    row["http_status"] = "OK_OR_NOT_CAPTURED" if full_page_fetch_success else ""
    row["blocked_flag"] = int("403" in str(row.get("extract_error")) or "blocked" in str(row.get("extract_error")).lower())
    row["non_html_flag"] = 0
    row["empty_text_flag"] = int(not bool(row.get("page_text_sample")))
    row.update(_text_quality(str(row.get("page_text_sample") or "")))
    return row
