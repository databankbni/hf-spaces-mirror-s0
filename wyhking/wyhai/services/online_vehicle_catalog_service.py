from __future__ import annotations

import gzip
import html
import json
import re
import threading
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
SERIES_CATALOG_PATH = ROOT / "data/runtime/autohome_vehicle_series_catalog.json.gz"
SPEC_CATALOG_PATH = ROOT / "data/runtime/autohome_vehicle_spec_catalog.json.gz"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UsedCarPricingCatalogLookup/1.0)",
    "Referer": "https://m.autohome.com.cn/cars/",
}


def compact(value: Any) -> str:
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", str(value or "")).lower()


def brand_keys(value: Any) -> set[str]:
    key = compact(value)
    keys = {key} if key else set()
    for suffix in ("汽车", "集团", "股份"):
        if key.endswith(suffix) and len(key) > len(suffix):
            keys.add(key[: -len(suffix)])
    return keys


class OnlineVehicleCatalogService:
    """Current-market catalog supplement.

    The bundled series catalog is deterministic and fast. Exact trim pages are
    fetched only when the local historical catalog has no suitable candidate.
    Fetched web content identifies a vehicle; it never directly sets a price.
    """

    _series_rows: list[dict[str, Any]] | None = None
    _spec_cache: dict[int, list[dict[str, Any]]] = {}
    _spec_rows: list[dict[str, Any]] | None = None
    _lock = threading.Lock()

    def load_series(self) -> list[dict[str, Any]]:
        if self.__class__._series_rows is not None:
            return self.__class__._series_rows
        rows: list[dict[str, Any]] = []
        try:
            with gzip.open(SERIES_CATALOG_PATH, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                rows = [row for row in payload if row.get("series_id")]
        except Exception:
            rows = []
        self.__class__._series_rows = rows
        return rows

    def find_series(self, brand: str, series: str) -> dict[str, Any] | None:
        query_brand_keys = brand_keys(brand)
        series_key = compact(series)
        matches = []
        for row in self.load_series():
            row_brand_keys = brand_keys(row.get("brand"))
            row_series = compact(row.get("series"))
            series_aliases = {row_series}
            for row_brand in row_brand_keys | query_brand_keys:
                if row_brand and row_series.startswith(row_brand):
                    series_aliases.add(row_series[len(row_brand) :])
            if query_brand_keys and not (query_brand_keys & row_brand_keys):
                continue
            if series_key in series_aliases:
                matches.append(row)
        if not matches:
            return None
        matches.sort(
            key=lambda row: (
                0 if row.get("series_state") in {20, 30} else 1,
                int(row.get("series_id") or 0),
            )
        )
        return matches[0]

    def load_specs(self) -> list[dict[str, Any]]:
        if self.__class__._spec_rows is not None:
            return self.__class__._spec_rows
        rows: list[dict[str, Any]] = []
        try:
            with gzip.open(SPEC_CATALOG_PATH, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                rows = [row for row in payload if row.get("model_id")]
        except Exception:
            rows = []
        self.__class__._spec_rows = rows
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(int(row["series_id"]), []).append(
                {
                    "model_id": str(row["model_id"]),
                    "model_year": row.get("model_year"),
                    "model_name": row.get("model_name") or "",
                    "raw_spec_name": row.get("raw_spec_name") or "",
                    "source_url": row.get("source_url"),
                }
            )
        self.__class__._spec_cache.update(grouped)
        return rows

    def list_brand_series(self, brand: str, limit: int = 8) -> list[dict[str, Any]]:
        query_brand_keys = brand_keys(brand)
        rows = [
            row
            for row in self.load_series()
            if query_brand_keys & brand_keys(row.get("brand"))
        ]
        rows.sort(
            key=lambda row: (
                0 if row.get("series_state") in {20, 30} else 1,
                str(row.get("series") or ""),
            )
        )
        return rows[:limit]

    def fetch_specs(self, series_id: int) -> list[dict[str, Any]]:
        series_id = int(series_id)
        self.load_specs()
        with self._lock:
            if series_id in self._spec_cache:
                return self._spec_cache[series_id]
        specs: list[dict[str, Any]] = []
        try:
            response = requests.get(
                f"https://www.autohome.com.cn/{series_id}/",
                headers=HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                response.text,
                flags=re.S,
            )
            payload = json.loads(html.unescape(match.group(1))) if match else {}
            page = ((payload.get("props") or {}).get("pageProps") or {})
            raw_specs = page.get("vrData") or []
            seen = set()
            for item in raw_specs:
                spec_id = item.get("specid")
                spec_name = str(item.get("specname") or "").strip()
                year_match = re.search(r"((?:19|20)\d{2})款", spec_name)
                if not spec_id or not spec_name or spec_id in seen:
                    continue
                seen.add(spec_id)
                specs.append(
                    {
                        "model_id": str(spec_id),
                        "model_year": int(year_match.group(1)) if year_match else None,
                        "model_name": re.sub(r"^(?:19|20)\d{2}款\s*", "", spec_name),
                        "raw_spec_name": spec_name,
                        "source_url": f"https://www.autohome.com.cn/{series_id}/",
                    }
                )
        except Exception:
            specs = []
        config_specs = self._fetch_config_specs(series_id)
        by_id = {str(item["model_id"]): item for item in specs}
        for item in config_specs:
            by_id.setdefault(str(item["model_id"]), item)
        specs = list(by_id.values())
        with self._lock:
            self._spec_cache[series_id] = specs
        return specs

    @staticmethod
    def _fetch_config_specs(series_id: int) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                f"https://car.autohome.com.cn/config/series/{int(series_id)}.html",
                headers=HEADERS,
                timeout=16,
            )
            response.raise_for_status()
            match = re.search(
                r"var config = (\{.*?\});\s*var option\s*=",
                response.text,
                flags=re.S,
            )
            if not match:
                return []
            payload = json.loads(match.group(1))
            groups = ((payload.get("result") or {}).get("paramtypeitems") or [])
            if not groups:
                return []
            params = groups[0].get("paramitems") or []
            if not params:
                return []
            items = params[0].get("valueitems") or []
            specs = []
            for item in items:
                spec_id = item.get("specid")
                raw = html.unescape(re.sub(r"<[^>]+>", "", str(item.get("value") or ""))).strip()
                year_match = re.search(r"((?:19|20)\d{2})款", raw)
                if not spec_id or not year_match:
                    continue
                model_name = raw[year_match.end() :].strip()
                specs.append(
                    {
                        "model_id": str(spec_id),
                        "model_year": int(year_match.group(1)),
                        "model_name": model_name,
                        "raw_spec_name": f"{year_match.group(1)}款 {model_name}".strip(),
                        "source_url": f"https://car.autohome.com.cn/config/series/{int(series_id)}.html",
                    }
                )
            return specs
        except Exception:
            return []

    def candidates(
        self,
        brand: str,
        series: str,
        model_year: int | None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        series_row = self.find_series(brand, series)
        if not series_row:
            return []
        specs = self.fetch_specs(int(series_row["series_id"]))
        if model_year:
            specs = [item for item in specs if item.get("model_year") == int(model_year)]
        rows = []
        for item in specs[:limit]:
            brand_name = str(series_row["brand"] or "").strip()
            series_name = str(series_row["series"] or "").strip()
            compact_series_name = compact(series_name)
            has_brand_prefix = any(
                key and compact_series_name.startswith(key)
                for key in brand_keys(brand_name)
            )
            vehicle_name = series_name if has_brand_prefix else f"{brand_name} {series_name}".strip()
            year_text = f"{item.get('model_year')}款"
            raw_name = str(item["raw_spec_name"] or "").strip()
            trim_name = raw_name[len(year_text) :].strip() if raw_name.startswith(year_text) else raw_name
            rows.append(
                {
                    "model_id": item["model_id"],
                    "series_id": str(series_row["series_id"]),
                    "brand": series_row["brand"],
                    "series": series_row["series"],
                    "model_year": item.get("model_year"),
                    "model_name": item["model_name"],
                    "label": f"{year_text} {vehicle_name} {trim_name}".strip(),
                    "catalog_source": "autohome_current_catalog",
                    "source_url": item["source_url"],
                    "official_price_min": series_row.get("official_price_min"),
                    "official_price_max": series_row.get("official_price_max"),
                }
            )
        return rows
