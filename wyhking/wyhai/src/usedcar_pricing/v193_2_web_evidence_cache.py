from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd


CACHE_VERSION = "v193_2_web_evidence_cache_v1"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def date_bucket(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def search_cache_key(provider: str, query_text: str, bucket: str | None = None) -> str:
    return stable_hash({"provider": provider, "query_text": query_text, "date_bucket": bucket or date_bucket()})


def default_data_dir() -> Path:
    return project_root() / "data/v193_2"


def read_parquet_or_empty(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def load_search_cache(data_dir: Path | None = None) -> pd.DataFrame:
    return read_parquet_or_empty((data_dir or default_data_dir()) / "search_cache/search_results.parquet")


def append_search_cache(rows: list[dict[str, Any]], data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or default_data_dir()) / "search_cache/search_results.parquet"
    existing = read_parquet_or_empty(path)
    incoming = pd.DataFrame(rows)
    if incoming.empty:
        return existing
    combined = pd.concat([existing, incoming], ignore_index=True) if not existing.empty else incoming
    if "cache_key" in combined.columns and "result_rank" in combined.columns:
        combined = combined.drop_duplicates(["cache_key", "result_rank"], keep="last")
    write_parquet(combined, path)
    return combined


def find_cached_results(provider: str, query_text: str, ttl_days: int, data_dir: Path | None = None) -> pd.DataFrame:
    cache = load_search_cache(data_dir)
    if cache.empty:
        return cache
    threshold = pd.Timestamp.utcnow() - pd.Timedelta(days=ttl_days)
    cache_time = pd.to_datetime(cache.get("search_time"), errors="coerce", utc=True)
    mask = (
        cache.get("provider", pd.Series(dtype=str)).astype(str).eq(provider)
        & cache.get("query_text", pd.Series(dtype=str)).astype(str).eq(query_text)
        & cache_time.ge(threshold)
    )
    return cache[mask].copy()

