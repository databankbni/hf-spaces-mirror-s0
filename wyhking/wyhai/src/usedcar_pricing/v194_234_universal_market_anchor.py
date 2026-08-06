"""Universal market-anchor guard for v194 online pricing.

This layer is deliberately not a new point-price model.  It is a broad,
time-adjusted safety net built from legal internal actuals plus low-weight
external listing proxies.  The service uses it only after the main quote path
has produced a price, to keep online C2B/B2C values inside a defensible market
range when exact evidence is sparse or a router drifts.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .v194_121_product_memory import _trim_match_key
from .v194_retrieval import normalize_query


UNIVERSAL_MARKET_ANCHOR_POLICY_VERSION = "v194_234_universal_market_anchor_guard_v1"


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _safe_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(float(numeric)):
        return None
    return float(numeric)


def _key_value(value: Any) -> str:
    if value is None:
        return ""
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric) and np.isfinite(float(numeric)):
        number = float(numeric)
        return str(int(number)) if number.is_integer() else f"{number:.6g}"
    return _compact(value)


def _price_band(price: Any) -> str:
    value = _safe_float(price)
    if not value or value <= 0:
        return ""
    wan = value / 10000.0
    for edge, label in [
        (3, "00_03w"),
        (5, "03_05w"),
        (8, "05_08w"),
        (12, "08_12w"),
        (18, "12_18w"),
        (25, "18_25w"),
        (35, "25_35w"),
        (50, "35_50w"),
        (80, "50_80w"),
        (120, "80_120w"),
    ]:
        if wan < edge:
            return label
    return "120w_plus"


def _energy_from_key(canonical_trim_key: Any) -> str:
    parts = str(canonical_trim_key or "").split("|")
    if len(parts) > 3:
        value = _compact(parts[3])
        if value:
            return value
    return "unknown"


def _trim_family_key(value: Any) -> str:
    text = str(value or "").strip()
    parts = text.split("|")
    if len(parts) >= 3 and re.fullmatch(r"(?:19|20)\d{2}", parts[2] or ""):
        parts[2] = "*"
    specific_tokens = [
        token
        for token in parts[3:]
        if token and token.lower() not in {"ice", "bev", "phev", "hev", "erev", "unknown"}
    ]
    if not specific_tokens:
        return ""
    trim_tokens = [token for token in specific_tokens if token.startswith("trim=")]
    if trim_tokens:
        trim_body = trim_tokens[-1].split("=", 1)[-1]
        series = parts[1] if len(parts) > 1 else ""
        if _compact(trim_body) in {_compact(series), ""}:
            return ""
    return "|".join(parts)


class V194234UniversalMarketAnchor:
    level_specs: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("same_trim_year", ("brand_key", "series_key", "canonical_trim_match_key", "model_year")),
        ("same_trim_any_year", ("brand_key", "series_key", "canonical_trim_family_key")),
        ("same_series_year", ("brand_key", "series_key", "model_year")),
        ("same_series_energy", ("brand_key", "series_key", "energy_key")),
        ("same_series_any_year", ("brand_key", "series_key")),
        ("brand_energy_price_band", ("brand_key", "energy_key", "price_band")),
        ("brand_price_band", ("brand_key", "price_band")),
        ("market_energy_price_band", ("energy_key", "price_band")),
        ("global_price_band", ("price_band",)),
    )

    def __init__(self, root: Path) -> None:
        self.root = root
        path = root / "data/v194/universal_market_anchor/v194_234_universal_market_anchor.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        self.table = pd.read_parquet(path)
        self.indexes: dict[tuple[str, str], dict[tuple[str, ...], dict[str, Any]]] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        table = self.table.copy()
        for _, columns in self.level_specs:
            for column in columns:
                if column in table.columns:
                    table[column] = table[column].map(_key_value)
        for column in ("anchor_role", "match_level"):
            table[column] = table[column].fillna("").astype(str)
        for role, role_frame in table.groupby("anchor_role", sort=False):
            for level, columns in self.level_specs:
                subset = role_frame[role_frame["match_level"].eq(level)]
                if subset.empty:
                    self.indexes[(role, level)] = {}
                    continue
                current: dict[tuple[str, ...], dict[str, Any]] = {}
                for record in subset.to_dict("records"):
                    key = tuple(_key_value(record.get(column)) for column in columns)
                    current[key] = record
                self.indexes[(role, level)] = current

    def _normalize_for_lookup(self, query: dict[str, Any], *, price_hint_yuan: float | None) -> dict[str, str]:
        normalized = normalize_query(query)
        canonical = str(normalized.get("canonical_trim_key") or "")
        trim_match = _trim_match_key(canonical)
        energy = _compact(normalized.get("normalized_energy_type") or "")
        if not energy or energy == "unknown":
            energy = _energy_from_key(canonical)
        return {
            "brand_key": _key_value(normalized.get("brand_key")),
            "series_key": _key_value(normalized.get("series_key")),
            "canonical_trim_match_key": _key_value(trim_match),
            "canonical_trim_family_key": _key_value(_trim_family_key(trim_match)),
            "model_year": _key_value(normalized.get("model_year")),
            "energy_key": _key_value(energy or "UNKNOWN"),
            "price_band": _price_band(price_hint_yuan),
            "_age_years": str(normalized.get("age_years") or ""),
        }

    @staticmethod
    def _lookup_variants(lookup: dict[str, str]) -> list[dict[str, str]]:
        variants: list[dict[str, str]] = []
        brand = lookup.get("brand_key", "")
        series = lookup.get("series_key", "")
        series_candidates = [series]
        if brand and series and not series.startswith(brand):
            series_candidates.append(f"{brand}{series}")
        if brand and series.startswith(brand):
            stripped = series[len(brand):]
            if stripped:
                series_candidates.append(stripped)
        seen: set[str] = set()
        for candidate in series_candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            current = dict(lookup)
            current["series_key"] = candidate
            variants.append(current)
        return variants

    @staticmethod
    def _age_adjustment(row: dict[str, Any], query_age: float | None) -> float:
        if query_age is None:
            return 1.0
        anchor_age = _safe_float(row.get("median_age_years_asof"))
        rate = _safe_float(row.get("annual_depreciation_rate")) or 0.09
        if anchor_age is None or not np.isfinite(anchor_age):
            return 1.0
        gap = max(-1.0, min(8.0, query_age - anchor_age))
        return float(np.clip(math.exp(-rate * gap), 0.55, 1.35))

    @staticmethod
    def _guard_margins(row: dict[str, Any]) -> tuple[float, float]:
        confidence = str(row.get("confidence_bucket") or "LOW").upper()
        external_share = _safe_float(row.get("external_weight_share")) or 0.0
        if confidence == "HIGH":
            low_mult, high_mult = 0.88, 1.12
        elif confidence == "MEDIUM":
            low_mult, high_mult = 0.80, 1.22
        else:
            low_mult, high_mult = 0.68, 1.38
        if external_share >= 0.75:
            low_mult = min(low_mult, 0.60)
            high_mult = max(high_mult, 1.45)
        return low_mult, high_mult

    def lookup(self, query: dict[str, Any], *, role: str, price_hint_yuan: float | None = None) -> dict[str, Any] | None:
        anchor_role = "b2c" if str(role).lower().startswith("b2c") else "c2b"
        lookup = self._normalize_for_lookup(query, price_hint_yuan=price_hint_yuan)
        query_age = _safe_float(lookup.get("_age_years"))
        for level, columns in self.level_specs:
            row = None
            key: tuple[str, ...] = ()
            for variant in self._lookup_variants(lookup):
                key = tuple(variant.get(column, "") for column in columns)
                if any(part == "" for part in key):
                    continue
                row = self.indexes.get((anchor_role, level), {}).get(key)
                if row:
                    break
            if not row:
                continue
            age_factor = self._age_adjustment(row, query_age)
            point_source = "q50_yuan" if anchor_role == "b2c" else "q30_yuan"
            point = (_safe_float(row.get(point_source)) or _safe_float(row.get("q50_yuan")) or 0.0) * age_factor
            low = (_safe_float(row.get("q10_yuan")) or point) * age_factor
            high = (_safe_float(row.get("q90_yuan")) or point) * age_factor
            low_mult, high_mult = self._guard_margins(row)
            guard_low = max(1000.0, low * low_mult)
            guard_high = max(guard_low * 1.08, high * high_mult)
            return {
                "enabled": True,
                "policy_version": UNIVERSAL_MARKET_ANCHOR_POLICY_VERSION,
                "anchor_role": anchor_role,
                "match_level": level,
                "point_yuan": round(point, 2),
                "guard_low_yuan": round(guard_low, 2),
                "guard_high_yuan": round(guard_high, 2),
                "q10_yuan": round(low, 2),
                "q30_yuan": round((_safe_float(row.get("q30_yuan")) or point) * age_factor, 2),
                "q50_yuan": round((_safe_float(row.get("q50_yuan")) or point) * age_factor, 2),
                "q90_yuan": round(high, 2),
                "row_count": int(_safe_float(row.get("row_count")) or 0),
                "effective_weight": round(_safe_float(row.get("effective_weight")) or 0.0, 4),
                "freshest_days": round(_safe_float(row.get("freshest_days")) or 0.0, 2),
                "confidence_bucket": str(row.get("confidence_bucket") or "LOW"),
                "external_weight_share": round(_safe_float(row.get("external_weight_share")) or 0.0, 4),
                "source_kinds": str(row.get("source_kinds") or ""),
                "age_adjustment_factor": round(age_factor, 6),
                "lookup_key": "|".join(key),
            }
        return None

    def guard_price(
        self,
        query: dict[str, Any],
        *,
        role: str,
        price_yuan: float,
        interval_low_yuan: float | None = None,
        interval_high_yuan: float | None = None,
        price_hint_yuan: float | None = None,
    ) -> dict[str, Any]:
        price = _safe_float(price_yuan)
        if not price or price <= 0:
            return {"enabled": False, "reason": "NO_PRICE"}
        anchor = self.lookup(query, role=role, price_hint_yuan=price_hint_yuan or price)
        if not anchor:
            return {"enabled": False, "reason": "NO_ANCHOR"}
        low_bound = _safe_float(anchor.get("guard_low_yuan")) or 0.0
        high_bound = _safe_float(anchor.get("guard_high_yuan")) or 0.0
        guarded = price
        action = "within_anchor_range"
        if high_bound and price > high_bound:
            guarded = high_bound
            action = "clamped_down_to_anchor_high"
        elif low_bound and price < low_bound:
            guarded = low_bound
            action = "clamped_up_to_anchor_low"
        interval_low = _safe_float(interval_low_yuan)
        interval_high = _safe_float(interval_high_yuan)
        if interval_low is None or interval_low <= 0:
            interval_low = min(guarded, _safe_float(anchor.get("q10_yuan")) or guarded) * 0.96
        if interval_high is None or interval_high <= 0:
            interval_high = max(guarded, _safe_float(anchor.get("q90_yuan")) or guarded) * 1.04
        if action != "within_anchor_range":
            width_low = max(0.04, min(0.18, (guarded - min(interval_low, guarded)) / max(guarded, 1.0)))
            width_high = max(0.04, min(0.20, (max(interval_high, guarded) - guarded) / max(guarded, 1.0)))
            interval_low = max(1000.0, guarded * (1.0 - width_low))
            interval_high = max(interval_low * 1.05, guarded * (1.0 + width_high))
        return {
            **anchor,
            "applied": action != "within_anchor_range",
            "action": action,
            "pre_guard_price_yuan": round(price, 2),
            "guarded_price_yuan": round(guarded, 2),
            "adjustment_yuan": round(guarded - price, 2),
            "interval_low_yuan": round(interval_low, 2),
            "interval_high_yuan": round(interval_high, 2),
        }
