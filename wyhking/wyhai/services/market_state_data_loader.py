"""Read and filter the city-series market-state serving dataset."""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .geo_resolver import resolve_city


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_PATH = ROOT / "data" / "market_state" / "market_state_series_city.json"


def _normalized_text(value: Any) -> str:
    return re.sub(r"[\s\-_/·•（）()]+", "", str(value or "")).lower()


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MarketStateDataLoader:
    def __init__(self, json_path: Path | str | None = None) -> None:
        self.json_path = Path(json_path or DEFAULT_JSON_PATH)
        self.metadata: dict[str, Any] = {}
        self.records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.json_path.is_file():
            return
        try:
            payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.metadata = payload.get("metadata") or {}
        self.records = [
            row for row in (payload.get("records") or [])
            if isinstance(row, dict) and row.get("city") and row.get("series")
        ]

    @property
    def available(self) -> bool:
        return bool(self.records)

    @property
    def cities(self) -> list[str]:
        return sorted({str(row.get("city")) for row in self.records if row.get("city")})

    @property
    def series_names(self) -> list[str]:
        return sorted(
            {str(row.get("series")) for row in self.records if row.get("series")},
            key=len,
            reverse=True,
        )

    @property
    def brand_names(self) -> list[str]:
        return sorted(
            {str(row.get("brand")) for row in self.records if row.get("brand")},
            key=len,
            reverse=True,
        )

    def find_city_in_text(self, text: str) -> str | None:
        resolved = resolve_city(text, self.cities)
        return resolved.city if resolved else None

    def find_series_in_text(self, text: str) -> str | None:
        normalized = _normalized_text(text)
        matches = [
            series for series in self.series_names
            if _normalized_text(series) and _normalized_text(series) in normalized
        ]
        return max(matches, key=len) if matches else None

    def find_all_series_in_text(self, text: str, limit: int = 6) -> list[str]:
        normalized = _normalized_text(text)
        matches = [
            series for series in self.series_names
            if _normalized_text(series) and _normalized_text(series) in normalized
        ]
        selected: list[str] = []
        for series in matches:
            if any(_normalized_text(series) in _normalized_text(existing) for existing in selected):
                continue
            selected.append(series)
            if len(selected) >= limit:
                break
        return selected

    def find_brand_in_text(self, text: str) -> str | None:
        normalized = _normalized_text(text)
        matches = [
            brand for brand in self.brand_names
            if _normalized_text(brand) and _normalized_text(brand) in normalized
        ]
        return max(matches, key=len) if matches else None

    def filter(
        self,
        *,
        city: str | None = None,
        brand: str | None = None,
        series: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: Iterable[dict[str, Any]] = self.records
        if city and city != "全国":
            rows = (row for row in rows if str(row.get("city")) == city)
        if brand:
            target = _normalized_text(brand)
            rows = (row for row in rows if target in _normalized_text(row.get("brand")))
        if series:
            target = _normalized_text(series)
            rows = (row for row in rows if target == _normalized_text(row.get("series")))
        if keyword:
            target = _normalized_text(keyword)
            rows = (
                row for row in rows
                if target in _normalized_text(row.get("brand"))
                or target in _normalized_text(row.get("series"))
            )
        return list(rows)

    @staticmethod
    def percentile(rows: list[dict[str, Any]], field: str, quantile: float) -> float | None:
        values = sorted(
            value for value in (_finite_number(row.get(field)) for row in rows)
            if value is not None
        )
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        position = (len(values) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight


@lru_cache(maxsize=4)
def get_market_state_loader(json_path: str = "") -> MarketStateDataLoader:
    return MarketStateDataLoader(Path(json_path) if json_path else DEFAULT_JSON_PATH)
