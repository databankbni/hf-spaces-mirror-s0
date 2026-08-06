from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd


HEALTHCHECK_VERSION = "v193_3_search_healthcheck_v1"
SAMPLE_QUERY = "宝马3系 2021款 320i 运动套装 二手车 价格"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_searxng_healthcheck(base_url: str | None = None, *, sample_query: str = SAMPLE_QUERY, timeout: float = 15.0) -> dict[str, Any]:
    base_url = (base_url or os.environ.get("SEARXNG_BASE_URL") or "http://localhost:8080").rstrip("/")
    started = time.time()
    row: dict[str, Any] = {
        "healthcheck_version": HEALTHCHECK_VERSION,
        "searxng_base_url": base_url,
        "sample_query": sample_query,
        "sample_curl_url": f"{base_url}/search?q={urllib.parse.quote(sample_query)}&format=json",
        "searxng_available": False,
        "json_enabled": False,
        "sample_query_result_count": 0,
        "latency_ms": 0,
        "error_code": "",
        "error_message": "",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with urllib.request.urlopen(row["sample_curl_url"], timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        results = data.get("results") or []
        row.update(
            {
                "searxng_available": True,
                "json_enabled": isinstance(data, dict),
                "sample_query_result_count": len(results),
                "first_result_url": (results[0].get("url") if results else ""),
                "first_result_title": (results[0].get("title") if results else ""),
            }
        )
        if not results:
            row["error_code"] = "SEARCH_EMPTY_RESULT"
    except json.JSONDecodeError as error:
        row["error_code"] = "SEARCH_NON_JSON_RESPONSE"
        row["error_message"] = str(error)[:500]
    except Exception as error:
        row["error_code"] = "SEARCH_PROVIDER_UNAVAILABLE"
        row["error_message"] = f"{type(error).__name__}: {str(error)[:500]}"
    row["latency_ms"] = int((time.time() - started) * 1000)
    return row


def write_healthcheck(path: Path | None = None, *, base_url: str | None = None) -> pd.DataFrame:
    path = path or project_root() / "results/audit/v193_3_searxng_healthcheck.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([run_searxng_healthcheck(base_url=base_url)])
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return frame

