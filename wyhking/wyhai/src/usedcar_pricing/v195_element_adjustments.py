"""Evidence-backed city and colour residual adjustments for the v195 price book."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data/v195/v195_403_market_element_adjustments.json"
)


def _compact(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _strict_key(brand: Any, series: Any, trim: Any, model_year: Any) -> str:
    try:
        year = str(int(float(model_year)))
    except (TypeError, ValueError):
        year = ""
    return "|".join((_compact(brand), _compact(series), _compact(trim), year))


@lru_cache(maxsize=4)
def load_adjustments(path: str = str(DEFAULT_PATH)) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def element_log_adjustment(
    *,
    brand: Any,
    series: Any,
    trim: Any,
    model_year: Any,
    query_city: Any,
    anchor_city: Any,
    query_color: Any,
    anchor_color: Any,
    path: str = str(DEFAULT_PATH),
) -> tuple[float, dict[str, Any]]:
    """Return bounded query-vs-anchor market residuals with evidence trace."""

    data = load_adjustments(path)
    if not data:
        return 0.0, {"city_level": "unavailable", "color_level": "unavailable"}
    strict = _strict_key(brand, series, trim, model_year)

    def factor(kind: str, value: Any) -> tuple[float, str, int]:
        category = _compact(value)
        if not category:
            return 0.0, "missing", 0
        exact = (data.get(f"strict_{kind}") or {}).get(f"{strict}|{category}")
        if isinstance(exact, dict):
            return float(exact.get("log_factor") or 0.0), "strict_trim_year", int(exact.get("support") or 0)
        global_row = (data.get(f"global_{kind}") or {}).get(category)
        if isinstance(global_row, dict):
            return float(global_row.get("log_factor") or 0.0), "global_residual", int(global_row.get("support") or 0)
        return 0.0, "neutral", 0

    query_city_factor, city_level, city_support = factor("city", query_city)
    anchor_city_factor, _, _ = factor("city", anchor_city)
    query_color_factor, color_level, color_support = factor("color", query_color)
    anchor_color_factor, _, _ = factor("color", anchor_color)
    city_delta = float(np.clip(query_city_factor - anchor_city_factor, -0.035, 0.035))
    color_delta = float(np.clip(query_color_factor - anchor_color_factor, -0.020, 0.020))
    return city_delta + color_delta, {
        "city_log_adjustment": city_delta,
        "city_level": city_level,
        "city_support": city_support,
        "color_log_adjustment": color_delta,
        "color_level": color_level,
        "color_support": color_support,
    }

