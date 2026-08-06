from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd


LIST_ENDPOINT = "https://www.dongchedi.com/motor/pc/sh/sh_sku_list"


@dataclass(frozen=True)
class DongchediListing:
    sku_id: str
    title: str
    series_id: int | None
    brand: str
    series: str
    model_year: int | None
    trim: str
    city: str
    price_yuan: float
    mileage_wan_km: float | None
    first_license_year: int | None
    first_license_month: str | None
    transfer_count: int | None
    color: str
    match_score: float
    match_level: str
    detail_url: str


class DongchediUsedCarMarket:
    """Small online DCD market probe for current B2C sanity checks.

    The probe uses the public used-car list API and treats listings as B2C
    asking-price evidence only.  It must not directly set C2B purchase price.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.environ.get("PROJECT_ROOT") or Path(__file__).resolve().parents[1])
        self._series_map: dict[str, int] | None = None
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self._snapshot_cache: pd.DataFrame | None = None
        self._snapshot_series_rows: dict[int, list[dict[str, Any]]] = {}

    def probe(self, payload: dict[str, Any], *, pages: int = 6, limit: int = 60) -> dict[str, Any]:
        brand = str(payload.get("brand") or "").strip()
        series = str(payload.get("series") or "").strip()
        trim = str(payload.get("trim") or payload.get("model") or payload.get("standard_vehicle") or "").strip()
        city = str(payload.get("city") or "").strip()
        year = _safe_int(payload.get("model_year") or payload.get("modelYear") or _year_from_text(trim))
        target_mileage = _safe_float(_present(payload.get("mileage_wan_km"), payload.get("mileage")))
        target_transfer = _safe_int(_present(payload.get("transfer_count"), payload.get("transfer")))
        target_first_year = _target_first_license_year(payload, fallback_model_year=year)
        target_first_month = _target_first_license_month(payload)
        target_color = _normalize_color(payload.get("color") or payload.get("color_raw"))
        if not series and trim:
            series = _series_hint_from_text(trim)
        series_id = self._series_id(brand, series)
        if _is_import_gle_request(brand=brand, series=series, trim=trim):
            series_id = 228
        if not series_id:
            return {
                "enabled": False,
                "reason": "DCD_SERIES_ID_NOT_FOUND",
                "brand": brand,
                "series": series,
                "model_year": year,
                "trim": trim,
            }
        cache_key = "|".join(
            [
                str(series_id),
                str(year or ""),
                _compact(trim),
                city,
                f"mile={target_mileage if target_mileage is not None else ''}",
                f"reg={target_first_year if target_first_year is not None else ''}",
                f"regm={target_first_month or ''}",
                f"tr={target_transfer if target_transfer is not None else ''}",
                f"color={target_color}",
            ]
        )
        if cache_key in self._memory_cache:
            return dict(self._memory_cache[cache_key])
        # Quotes must use the completed local snapshot by default.  Falling
        # through to ``_fetch_rows`` here used to start a fresh crawl whenever
        # a cold series was absent from the snapshot, even though the later
        # exact-vehicle enrichment gate was disabled.  Keep all network access
        # behind the single explicit operator switch below.
        raw_rows = self._fetch_snapshot_rows(series_id)
        listings = [
            item
            for item in (_row_to_listing(row, target_trim=trim, target_year=year) for row in raw_rows)
            if item is not None
        ]
        exact_before_year_guard = [
            row for row in listings if row.match_level in {"exact_trim", "strong_trim"}
        ]
        exact = [
            row
            for row in exact_before_year_guard
            if _model_year_compatible(target_year=year, listing_year=row.model_year)
        ]
        snapshot_same_year = [
            row
            for row in exact
            if year
            and row.model_year
            and int(row.model_year) == int(year)
        ]
        snapshot_exact_vehicle = _nearest_exact_vehicle_listing(
            snapshot_same_year,
            city=city,
            mileage_wan_km=target_mileage,
            first_license_month=target_first_month,
            transfer_count=target_transfer,
            color=target_color,
        )
        # The checked-in full snapshot is the normal production evidence
        # source.  Do not turn an ordinary quote (or an acceptance replay)
        # into another crawl merely because that exact seven-element car is
        # absent.  An operator may explicitly enable a small live enrichment
        # for incident investigation, but it is off by default.
        allow_live_enrichment = os.environ.get(
            "DONGCHEDI_ALLOW_LIVE_ENRICHMENT", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if snapshot_exact_vehicle is None and allow_live_enrichment:
            live_rows = self._fetch_live_enriched_rows(
                series_id,
                target_trim=trim,
                target_year=year,
                city=city,
                pages=max(pages, 6),
                limit=limit,
            )
            if live_rows:
                raw_rows = [*raw_rows, *live_rows]
                listings = [
                    item
                    for item in (
                        _row_to_listing(row, target_trim=trim, target_year=year)
                        for row in raw_rows
                    )
                    if item is not None
                ]
                exact_before_year_guard = [
                    row
                    for row in listings
                    if row.match_level in {"exact_trim", "strong_trim"}
                ]
                exact = [
                    row
                    for row in exact_before_year_guard
                    if _model_year_compatible(
                        target_year=year, listing_year=row.model_year
                    )
                ]
        year_gap_rejected_count = len(exact_before_year_guard) - len(exact)
        same_year_exact = [row for row in exact if year and row.model_year and int(row.model_year) == int(year)]
        exact_vehicle_match = _nearest_exact_vehicle_listing(
            same_year_exact or exact,
            city=city,
            mileage_wan_km=target_mileage,
            first_license_month=target_first_month,
            transfer_count=target_transfer,
            color=target_color,
        )
        city_same_year_exact = [row for row in same_year_exact if city and row.city == city]
        city_exact = [row for row in exact if city and row.city == city]
        if len(city_same_year_exact) >= 2:
            usable = city_same_year_exact
            usable_level = "city_same_trim_same_year"
        elif len(same_year_exact) >= 2:
            usable = same_year_exact
            usable_level = "national_same_trim_same_year"
        elif len(city_exact) >= 2:
            usable = city_exact
            usable_level = "city_same_trim_any_year"
        else:
            usable = exact
            usable_level = "national_same_trim_any_year"
        single_listing_mode = False
        if len(usable) < 2 and exact:
            # A single exact current listing is weaker than a market sample,
            # but it is still useful as a B2C sanity anchor. It must not set
            # C2B directly and uses a much larger asking-price discount below.
            usable = sorted(
                city_same_year_exact or same_year_exact or city_exact or exact,
                key=lambda row: (
                    0 if year and row.model_year and int(row.model_year) == int(year) else 1,
                    0 if city and row.city == city else 1,
                    -row.match_score,
                    row.price_yuan,
                ),
            )[:1]
            single_listing_mode = True
            usable_level = (
                "single_city_same_trim_same_year"
                if city_same_year_exact
                else "single_national_same_trim_same_year"
                if same_year_exact
                else "single_city_same_trim_any_year"
                if city_exact
                else "single_national_same_trim_any_year"
            )
        if len(usable) < 1:
            # Keep weak rows for audit, but do not let them guard prices.
            weak = sorted(listings, key=lambda row: row.match_score, reverse=True)[:8]
            result = {
                "enabled": False,
                "reason": "DCD_NO_STRONG_CURRENT_MATCH",
                "series_id": series_id,
                "brand": brand,
                "series": series,
                "model_year": year,
                "trim": trim,
                "weak_listing_count": len(weak),
                "year_gap_rejected_count": year_gap_rejected_count,
                "weak_listings": [_listing_dict(row) for row in weak],
            }
            self._memory_cache[cache_key] = result
            return dict(result)
        adjusted_rows = [
            (row, adjusted_price, adjustment)
            for row in usable
            for adjusted_price, adjustment in [_adjust_listing_price_to_target(
                row,
                target_mileage_wan_km=target_mileage,
                target_first_license_year=target_first_year,
                target_transfer_count=target_transfer,
            )]
            if adjusted_price and adjusted_price > 0
        ]
        prices = sorted(adjusted_price for _, adjusted_price, _ in adjusted_rows)
        raw_prices = sorted(row.price_yuan for row, _, _ in adjusted_rows if row.price_yuan > 0)
        if not prices:
            return {"enabled": False, "reason": "DCD_MATCH_WITHOUT_PRICE", "series_id": series_id}
        q25 = _quantile(prices, 0.25)
        q50 = _quantile(prices, 0.50)
        q75 = _quantile(prices, 0.75)
        floor_multiplier = 0.88 if single_listing_mode else 0.96
        point_multiplier = 0.92 if single_listing_mode else 0.965
        ceiling_multiplier = 1.00 if single_listing_mode else 1.02
        result = {
            "enabled": True,
            "source": "dongchedi_current_usedcar",
            "endpoint": LIST_ENDPOINT,
            "series_id": series_id,
            "brand": brand,
            "series": series,
            "model_year": year,
            "trim": trim,
            "city": city,
            "match_level": usable_level,
            "matched_count": len(usable),
            "raw_listing_count": len(raw_rows),
            "year_gap_rejected_count": year_gap_rejected_count,
            "single_listing_mode": single_listing_mode,
            "price_basis": "six_element_adjusted_listing_asking_price",
            "target_mileage_wan_km": target_mileage,
            "target_first_license_year": target_first_year,
            "target_first_license_month": target_first_month,
            "target_transfer_count": target_transfer,
            "target_color": target_color,
            "exact_vehicle_match": bool(exact_vehicle_match),
            "exact_vehicle_listing_yuan": (
                round(float(exact_vehicle_match[0].price_yuan), 2)
                if exact_vehicle_match
                else None
            ),
            "exact_vehicle_adjusted_listing_yuan": (
                round(float(exact_vehicle_match[1]), 2)
                if exact_vehicle_match
                else None
            ),
            "exact_vehicle_sku_id": (
                exact_vehicle_match[0].sku_id if exact_vehicle_match else None
            ),
            "exact_vehicle_distance": (
                round(float(exact_vehicle_match[2]), 6)
                if exact_vehicle_match
                else None
            ),
            "adjustment_available_count": sum(
                1 for _, _, adjustment in adjusted_rows if adjustment.get("has_any_six_element_signal")
            ),
            "raw_price_min_yuan": round(min(raw_prices), 2) if raw_prices else None,
            "raw_price_median_yuan": round(_quantile(raw_prices, 0.50), 2) if raw_prices else None,
            "raw_price_max_yuan": round(max(raw_prices), 2) if raw_prices else None,
            "price_min_yuan": round(min(prices), 2),
            "price_q25_yuan": round(q25, 2),
            "price_median_yuan": round(q50, 2),
            "price_q75_yuan": round(q75, 2),
            "price_max_yuan": round(max(prices), 2),
            "suggested_b2c_floor_yuan": round(q25 * floor_multiplier, 2),
            "suggested_b2c_point_yuan": round(q50 * point_multiplier, 2),
            "suggested_b2c_ceiling_yuan": round(q75 * ceiling_multiplier, 2),
            "listings": [
                _listing_dict(row, adjusted_price_yuan=adjusted_price, adjustment=adjustment)
                for row, adjusted_price, adjustment in sorted(adjusted_rows, key=lambda item: item[1])[:20]
            ],
            "fetched_at": pd.Timestamp.utcnow().isoformat(),
        }
        self._memory_cache[cache_key] = result
        return dict(result)

    def _series_id(self, brand: str, series: str) -> int | None:
        series_map = self._load_series_map()
        keys = [
            f"{_compact(brand)}|{_compact(series)}",
            f"|{_compact(series)}",
            f"{_compact(brand)}|{_strip_brand_prefix(brand, series)}",
            f"|{_strip_brand_prefix(brand, series)}",
        ]
        for key in keys:
            if key in series_map:
                return series_map[key]
        compact_series = _compact(series)
        for key, value in series_map.items():
            key_series = key.split("|", 1)[-1]
            if compact_series and (compact_series == key_series or compact_series in key_series or key_series in compact_series):
                return value
        return None

    def _load_series_map(self) -> dict[str, int]:
        if self._series_map is not None:
            return self._series_map
        mapping: dict[str, int] = {}
        path = self.root / "data/v194_40/v194_40_dongchedi_usedcar_listings.parquet"
        if path.exists():
            try:
                frame = pd.read_parquet(path, columns=["brand", "series", "series_id"])
                _add_series_mapping(mapping, frame)
            except Exception:
                pass
        current_snapshot = self._load_current_snapshot()
        if current_snapshot is not None and not current_snapshot.empty:
            try:
                cols = [col for col in ("brand", "series", "series_id") if col in current_snapshot.columns]
                if set(cols) >= {"series", "series_id"}:
                    _add_series_mapping(mapping, current_snapshot[cols])
            except Exception:
                pass
        # Stable IDs observed from the public DCD list API. These are only
        # used when the restored historical snapshot does not contain a series.
        overrides = {
            "宝马|宝马4系": 118,
            "奔驰|奔驰GLE(进口)": 228,
            "奔驰|奔驰CLS": 223,
            "本田|凌派": 287,
            "马自达|睿翼": 1006,
        }
        for key, value in overrides.items():
            brand, series = key.split("|", 1)
            mapping.setdefault(f"{_compact(brand)}|{_compact(series)}", value)
            mapping.setdefault(f"|{_compact(series)}", value)
        self._series_map = mapping
        return mapping

    def _fetch_rows(self, series_id: int, *, pages: int, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, max(1, pages) + 1):
            payload = urllib.parse.urlencode(
                {
                    "series_ids": str(series_id),
                    "sh_city_name": "全国",
                    "page": str(page),
                    "limit": str(limit),
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                LIST_ENDPOINT,
                data=payload,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.dongchedi.com/usedcar",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    body = response.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                items = (((data or {}).get("data") or {}).get("search_sh_sku_info_list") or [])
                rows.extend([item for item in items if isinstance(item, dict)])
                if not (((data or {}).get("data") or {}).get("has_more")):
                    break
            except Exception:
                break
            time.sleep(0.08)
        return rows

    def _fetch_live_enriched_rows(
        self,
        series_id: int,
        *,
        target_trim: str,
        target_year: int | None,
        city: str,
        pages: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch a few live detail rows only when the full snapshot misses."""

        live = self._fetch_rows(series_id, pages=pages, limit=limit)
        candidates: list[dict[str, Any]] = []
        for row in live:
            listing = _row_to_listing(
                row, target_trim=target_trim, target_year=target_year
            )
            if listing is None or not _model_year_compatible(
                target_year=target_year, listing_year=listing.model_year
            ):
                continue
            candidates.append(row)
        candidates.sort(
            key=lambda row: (
                0
                if city
                and _compact(
                    row.get("car_source_city_name")
                    or row.get("brand_source_city_name")
                )
                == _compact(city)
                else 1,
                _safe_float(row.get("sh_price")) or 9_999_999,
            )
        )
        if not candidates:
            return []
        try:
            from scripts.crawl_dongchedi_current_usedcar_snapshot import (
                _fetch_detail,
                _flatten_detail,
                _flatten_row,
            )
        except ImportError:
            return candidates[:8]
        enriched: list[dict[str, Any]] = []
        fetched_at = pd.Timestamp.utcnow().isoformat()
        for row in candidates[:8]:
            sku_id = str(
                row.get("sku_id")
                or row.get("group_id_str")
                or row.get("group_id")
                or ""
            )
            if not sku_id:
                continue
            flat = _flatten_row(row, series_id=series_id, fetched_at=fetched_at)
            detail = _fetch_detail(
                sku_id,
                city=str(flat.get("city") or city),
                timeout=5.0,
            )
            merged = {**flat, **_flatten_detail(detail, fallback=flat)}
            mileage_wan = _safe_float(merged.get("mileage_wan_km"))
            price_wan = (
                _safe_float(merged.get("listing_price_yuan")) or 0.0
            ) / 10_000.0
            enriched.append(
                {
                    "sku_id": sku_id,
                    "group_id_str": sku_id,
                    "series_id": series_id,
                    "brand_name": merged.get("brand"),
                    "series_name": merged.get("series"),
                    "title": merged.get("standard_vehicle") or merged.get("title"),
                    "car_name": merged.get("trim"),
                    "car_year": merged.get("model_year"),
                    "car_source_city_name": merged.get("city"),
                    "brand_source_city_name": merged.get("city"),
                    "sh_price": f"{price_wan:.2f}万" if price_wan else row.get("sh_price"),
                    "car_mileage": (
                        f"{mileage_wan:.2f}万公里"
                        if mileage_wan is not None
                        else row.get("car_mileage")
                    ),
                    "car_age": merged.get("first_registration_time") or row.get("car_age"),
                    "first_registration_time": merged.get("first_registration_time"),
                    "sub_title": row.get("sub_title"),
                    "transfer_cnt": merged.get("transfer_count", row.get("transfer_cnt")),
                    "color": merged.get("color"),
                }
            )
        return enriched or candidates[:8]

    def _fetch_snapshot_rows(self, series_id: int) -> list[dict[str, Any]]:
        if int(series_id) in self._snapshot_series_rows:
            return self._snapshot_series_rows[int(series_id)]
        frame = self._load_current_snapshot()
        if frame is None or frame.empty or "series_id" not in frame.columns:
            return []
        subset = frame[pd.to_numeric(frame["series_id"], errors="coerce") == int(series_id)]
        if subset.empty:
            return []
        rows: list[dict[str, Any]] = []
        for row in subset.to_dict("records"):
            price_wan = _safe_float(row.get("listing_price_wan"))
            mileage_wan = _safe_float(row.get("mileage_wan_km"))
            rows.append(
                {
                    "sku_id": row.get("sku_id"),
                    "group_id_str": row.get("sku_id"),
                    "series_id": row.get("series_id"),
                    "brand_name": row.get("brand"),
                    "series_name": row.get("series"),
                    "title": row.get("standard_vehicle") or row.get("title"),
                    "car_name": row.get("trim"),
                    "car_year": row.get("model_year"),
                    "car_source_city_name": row.get("city"),
                    "brand_source_city_name": row.get("city"),
                    "sh_price": (
                        f"{price_wan:.2f}万"
                        if price_wan is not None
                        else row.get("price_text")
                    ),
                    "car_mileage": (
                        f"{mileage_wan:.2f}万公里"
                        if mileage_wan is not None
                        else row.get("mileage_text")
                    ),
                    "car_age": row.get("first_registration_time") or row.get("age_text"),
                    "first_registration_time": row.get("first_registration_time"),
                    "sub_title": row.get("sub_title"),
                    "transfer_cnt": row.get("transfer_count"),
                    "color": row.get("color"),
                }
            )
        self._snapshot_series_rows[int(series_id)] = rows
        return rows

    def _load_current_snapshot(self) -> pd.DataFrame | None:
        if self._snapshot_cache is not None:
            return self._snapshot_cache
        market_store = self.root / "data/external/dongchedi_current_usedcar_market.parquet"
        if market_store.exists():
            try:
                frame = pd.read_parquet(market_store)
                self._snapshot_cache = frame
                return frame
            except Exception:
                pass
        market_store_csv = market_store.with_suffix(".csv")
        if market_store_csv.exists():
            try:
                frame = pd.read_csv(market_store_csv)
                self._snapshot_cache = frame
                return frame
            except Exception:
                pass

        candidates = _snapshot_candidates(self.root / "data/external")
        frames: list[pd.DataFrame] = []
        for path in candidates:
            if not path.exists():
                continue
            try:
                if path.suffix == ".parquet":
                    frame = pd.read_parquet(path)
                else:
                    frame = pd.read_csv(path)
                if not frame.empty:
                    frames.append(frame)
            except Exception:
                continue
        if frames:
            frame = pd.concat(frames, ignore_index=True, sort=False)
            if "sku_id" in frame.columns:
                frame = frame.drop_duplicates(subset=["sku_id"], keep="last")
            else:
                dedupe_cols = [
                    col
                    for col in ("series_id", "standard_vehicle", "listing_price_yuan", "city")
                    if col in frame.columns
                ]
                if dedupe_cols:
                    frame = frame.drop_duplicates(subset=dedupe_cols, keep="last")
            self._snapshot_cache = frame
            return frame
        self._snapshot_cache = pd.DataFrame()
        return self._snapshot_cache


def _snapshot_candidates(external_dir: Path) -> list[Path]:
    """Return raw snapshot files with parquet preferred over duplicate CSVs."""

    stems = [
        "dongchedi_current_usedcar_snapshot",
        "dongchedi_current_usedcar_priority_fast_snapshot",
        "dongchedi_current_usedcar_series_snapshot",
        "dongchedi_current_usedcar_priority_snapshot",
    ]
    candidates: list[Path] = []
    for stem in stems:
        parquet = external_dir / f"{stem}.parquet"
        csv = external_dir / f"{stem}.csv"
        candidates.append(parquet if parquet.exists() else csv)
    return candidates


def _add_series_mapping(mapping: dict[str, int], frame: pd.DataFrame) -> None:
    if frame.empty or "series_id" not in frame.columns:
        return
    valid = frame.dropna(subset=["series_id"])
    for row in valid.to_dict("records"):
        brand = str(row.get("brand") or "")
        series = str(row.get("series") or "")
        series_id = _safe_int(row.get("series_id"))
        if not series or not series_id:
            continue
        mapping[f"{_compact(brand)}|{_compact(series)}"] = series_id
        mapping[f"|{_compact(series)}"] = series_id
        mapping[f"{_compact(brand)}|{_strip_brand_prefix(brand, series)}"] = series_id
        mapping[f"|{_strip_brand_prefix(brand, series)}"] = series_id


def _row_to_listing(row: dict[str, Any], *, target_trim: str, target_year: int | None) -> DongchediListing | None:
    price = _price_yuan(row.get("sh_price"))
    if not price or price <= 0:
        return None
    title = str(row.get("title") or "")
    trim = str(row.get("car_name") or "")
    # Internal standard vehicles and the DCD snapshot share the same catalog.
    # Fuzzy matching here can only broaden into sibling configurations, so a
    # DCD listing is price-bearing only when its canonical trim is identical.
    if not trim or not _same_catalog_trim_identity(target_trim, trim):
        return None
    year = _safe_int(row.get("car_year")) or _year_from_text(" ".join([title, trim]))
    match_query = trim if _catalog_key(target_trim).endswith(_catalog_key(trim)) else target_trim
    score, level = _trim_match_score(match_query, trim)
    if score < 0.52:
        return None
    sub_title = str(row.get("sub_title") or "")
    mileage = _mileage_from_text(str(row.get("car_mileage") or "") or sub_title)
    first_license_text = str(
        row.get("first_registration_time") or row.get("car_age") or ""
    )
    first_year = _year_from_text(first_license_text or sub_title)
    first_month = _month_key(first_license_text)
    sku_id = str(row.get("sku_id") or row.get("group_id_str") or row.get("group_id") or "")
    return DongchediListing(
        sku_id=sku_id,
        title=title,
        series_id=_safe_int(row.get("series_id")),
        brand=str(row.get("brand_name") or ""),
        series=str(row.get("series_name") or ""),
        model_year=year,
        trim=trim,
        city=str(row.get("car_source_city_name") or row.get("brand_source_city_name") or ""),
        price_yuan=float(price),
        mileage_wan_km=mileage,
        first_license_year=first_year,
        first_license_month=first_month,
        transfer_count=_safe_int(row.get("transfer_cnt")),
        color=_normalize_color(row.get("color")),
        match_score=score,
        match_level=level,
        detail_url=f"https://m.dcdapp.com/motor/feoffline/usedcar_detail/detail.html?sku_id={sku_id}" if sku_id else "",
    )


def _trim_match_score(query: str, listing: str) -> tuple[float, str]:
    query_compact = _compact(query)
    listing_compact = _compact(listing)
    if not query_compact or not listing_compact:
        return 0.0, "empty"
    query_codes = _config_codes(query)
    listing_codes = _config_codes(listing)
    if query_codes and not query_codes.issubset(listing_codes):
        return 0.0, "config_code_mismatch"
    hard_conflicts = _hard_config_conflicts(query, listing)
    if hard_conflicts:
        return 0.0, f"hard_config_conflict:{','.join(sorted(hard_conflicts))}"
    query_keywords = _trim_keywords(query)
    listing_keywords = _trim_keywords(listing)
    if query_keywords:
        keyword_hit = len(query_keywords & listing_keywords) / max(1, len(query_keywords))
        if query_codes and keyword_hit >= 0.80:
            return 0.92, "exact_trim"
        if keyword_hit >= 0.82:
            return 0.82, "strong_trim"
    query_tokens = _trim_tokens(query)
    listing_tokens = _trim_tokens(listing)
    if query_tokens:
        token_hit = len(query_tokens & listing_tokens) / max(1, len(query_tokens))
    else:
        token_hit = 0.0
    contains = query_compact in listing_compact or listing_compact in query_compact
    code_bonus = 0.25 if query_codes else 0.0
    score = min(1.0, token_hit * 0.78 + code_bonus + (0.15 if contains else 0.0))
    if contains and score >= 0.82:
        return score, "exact_trim"
    if score >= 0.72:
        return score, "strong_trim"
    return score, "weak_trim"


def _trim_keywords(text: str) -> set[str]:
    compact = _compact(text)
    keywords = set(_config_codes(text))
    for keyword in (
        "quattro",
        "rdynamic",
        "m运动",
        "曜夜",
        "尊享",
        "领先",
        "设计",
        "时尚",
        "豪华",
        "舒适",
        "精英",
        "技术",
        "创行",
        "锋潮",
        "炫锋",
        "都市",
        "基本",
        "劲锐",
        "智联",
        "互联网",
        "悦享",
        "进取",
        "冠军",
        "智驾",
        "臻选",
        "动感",
        "投放",
        "90周年",
        "智享",
        "es陆尊",
        "双擎",
        "智能电混",
        "ecvt",
        "4matic",
        "两驱",
        "四驱",
        "后驱",
        "前驱",
        "手动",
        "自动",
        "cvt",
        "dct",
        "navi",
        "max",
        "pro",
        "plus",
        "ultra",
        "air",
        "lite",
        "长续航",
        "超长续航",
        "全家乐",
        "双imax",
        "imax",
        "伯牙",
        "巨幕",
        "奢享",
        "影院",
        "磷酸铁锂",
        "三元锂",
        "国v",
        "国vi",
    ):
        if _compact(keyword) in compact:
            keywords.add(_compact(keyword))
    return keywords


def _same_catalog_trim_identity(query: str, listing_trim: str) -> bool:
    """Exact identity for DCD-to-DCD standard trim names."""

    query_key = _catalog_key(query)
    listing_key = _catalog_key(listing_trim)
    return bool(
        query_key
        and listing_key
        and (
            query_key.endswith(listing_key)
            or (
                query_key == listing_key
                and not _hard_config_conflicts(query, listing_trim)
            )
        )
    )


def _catalog_key(value: str) -> str:
    text = re.sub(r"(?:19|20)\d{2}\s*款", "", str(value or "").lower())
    return _compact(text)


def _cross_source_trim_identity(query: str, listing: str) -> bool:
    """Conservative trim identity for platforms with different suffix style.

    Cross-platform titles may write 型/版/款 or Arabic/Chinese seat counts
    differently. Those presentation aliases are normalized, while generation,
    package and named-edition words remain mandatory.
    """

    def key(value: str) -> str:
        text = str(value or "").lower()
        text = re.sub(r"(?:19|20)\d{2}\s*款", "", text)
        text = text.replace("增程式", "增程")
        text = text.replace("后轮驱动", "后驱").replace("全轮驱动", "四驱")
        text = re.sub(r"\b(?:2wd|fwd)\b", "两驱", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:4wd|awd)\b", "四驱", text, flags=re.IGNORECASE)
        chinese_digits = {"二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        for chinese, number in chinese_digits.items():
            text = re.sub(rf"[大小]?{chinese}\s*座", f"{number}座", text)
        compact = _compact(text)
        return compact.translate(str.maketrans("", "", "型版款"))

    query_key = key(query)
    listing_key = key(listing)
    return bool(query_key and listing_key and query_key in listing_key)


def _trim_tokens(text: str) -> set[str]:
    compact = _compact(text)
    tokens = set(re.findall(r"[a-z]+\d*|\d+[a-z]+|\d+(?:\.\d+)?l|[\u4e00-\u9fff]{2,}", compact))
    stop = {
        "2020款", "2021款", "2022款", "2023款", "2024款", "2025款", "2026款",
        "宝马", "奔驰", "奥迪", "别克", "丰田", "本田", "捷豹", "马自达",
        "自动", "手动", "改款", "套装", "版本", "车型", "上牌",
    }
    return {token for token in tokens if token not in stop and not re.fullmatch(r"20\d{2}", token)}


def _config_codes(text: str) -> set[str]:
    compact = _compact(text)
    normalized = str(text or "").lower().replace("－", "-").replace("–", "-")
    patterns = [
        r"(?:sdrive|xdrive)\d{2}li",
        r"(?:sdrive|xdrive)\d{2}i",
        r"\d\.\d(?:gdit|tdi|tsi|td|t|l)",
        r"\d{3}li",
        r"\d{3}i",
        r"\d{3}l",
        r"(?<!\d)\d{3}(?!\d)",
        r"\d{2}tfsi",
        r"\d{3}tsi",
        r"\d{3}ps",
        r"\d{3}turbo",
        r"gle\d{3}",
        r"cls\d{3}",
        r"a8l\d{2}tfsi",
        r"\d{2,3}t",
        r"cvt",
        r"dct",
        r"ecvt",
        r"手动",
        r"自动",
        r"四驱",
        r"两驱",
        r"后驱",
        r"前驱",
        r"quattro",
        r"4matic",
    ]
    codes: set[str] = set()
    for pattern in patterns:
        codes.update(re.findall(pattern, compact))
    # Compacting joins adjacent configuration tokens (for example
    # "EQE 350 4MATIC" becomes "eqe3504matic"), so standalone numeric
    # badges must also be extracted from the separator-preserving text.
    codes.update(re.findall(r"(?<![\d.])\d{3}(?!\d)", normalized))
    codes.update(re.findall(r"(?<![\d.])\d{2,3}t(?![a-z0-9])", normalized))
    codes.update(re.findall(r"(?<!\d)\d{2}(?=\s*(?:ultra|max|pro|plus|air|lite)\b)", normalized))
    expanded: set[str] = set(codes)
    for code in codes:
        match = re.match(r"^(\d{3})(?:li|i|l)?$", code)
        if match:
            expanded.add(match.group(1))
        match = re.match(r"^(?:sdrive|xdrive)(\d{2})(?:li|i)$", code)
        if match:
            expanded.add(match.group(1) + "li")
            expanded.add(match.group(1))
    codes = expanded
    return codes


def _hard_config_conflicts(query: str, listing: str) -> set[str]:
    """Reject obvious cross-configuration matches before fuzzy scoring.

    DCD titles often share generic trim words such as "豪华" or "尊享".  Those
    words are useful once the hard configuration agrees, but they are dangerous
    when the powertrain, drivetrain or package line conflicts.
    """

    query_compact = _compact(query)
    listing_compact = _compact(listing)
    query_normalized = str(query or "").lower().replace("－", "-").replace("–", "-")
    listing_normalized = str(listing or "").lower().replace("－", "-").replace("–", "-")
    conflicts: set[str] = set()
    strict_variant_match = str(os.environ.get("V194_DCD_STRICT_CONFIG_MATCH", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

    def first(patterns: list[str], text: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return ""

    q_engine = first([r"\d\.\d(?:gdit|tdi|tsi|td|t|l)", r"\d{2,3}tfsi", r"\d{3}tsi"], query_compact)
    l_engine = first([r"\d\.\d(?:gdit|tdi|tsi|td|t|l)", r"\d{2,3}tfsi", r"\d{3}tsi"], listing_compact)
    if q_engine and l_engine and q_engine != l_engine:
        conflicts.add("engine")

    q_bmw_drive = first([r"(?:sdrive|xdrive)\d{2}(?:li|i)"], query_compact)
    l_bmw_drive = first([r"(?:sdrive|xdrive)\d{2}(?:li|i)"], listing_compact)
    if q_bmw_drive and l_bmw_drive and q_bmw_drive != l_bmw_drive:
        conflicts.add("bmw_drive_power")
    if strict_variant_match and l_bmw_drive and not q_bmw_drive:
        conflicts.add("extra_bmw_drive_power")

    q_named_awd = first([r"xdrive", r"4matic", r"quattro"], query_compact)
    l_named_awd = first([r"xdrive", r"4matic", r"quattro"], listing_compact)
    if strict_variant_match and l_named_awd and not q_named_awd:
        conflicts.add("extra_named_awd")

    q_transmission = first([r"cvt", r"dct", r"ecvt", r"手动", r"自动"], query_compact)
    l_transmission = first([r"cvt", r"dct", r"ecvt", r"手动", r"自动"], listing_compact)
    if q_transmission and l_transmission and q_transmission != l_transmission:
        conflicts.add("transmission")

    q_drive = first([r"四驱", r"全轮驱动", r"两驱", r"后驱", r"后轮驱动", r"前驱", r"quattro", r"4matic", r"xdrive", r"sdrive", r"awd", r"4wd", r"2wd"], query_compact)
    l_drive = first([r"四驱", r"全轮驱动", r"两驱", r"后驱", r"后轮驱动", r"前驱", r"quattro", r"4matic", r"xdrive", r"sdrive", r"awd", r"4wd", r"2wd"], listing_compact)
    drive_alias = {
        "全轮驱动": "四驱",
        "awd": "四驱",
        "4wd": "四驱",
        "后轮驱动": "后驱",
        "2wd": "两驱",
    }
    q_drive = drive_alias.get(q_drive, q_drive)
    l_drive = drive_alias.get(l_drive, l_drive)
    if q_drive and l_drive and q_drive != l_drive:
        conflicts.add("drivetrain")

    def values(pattern: str, text: str, *, group: int = 1) -> set[str]:
        return {match.group(group).lower() for match in re.finditer(pattern, text, flags=re.IGNORECASE)}

    def conflict_if_disjoint(name: str, q_values: set[str], l_values: set[str]) -> None:
        if q_values and l_values and q_values.isdisjoint(l_values):
            conflicts.add(name)

    # These are hard physical/configuration dimensions. They may be omitted
    # by one source, but when both sides state them they must agree.
    def seat_counts(normalized: str) -> set[str]:
        out = values(r"([2-9])\s*座", normalized)
        chinese_digits = {"二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        out.update(
            chinese_digits[match.group(1)]
            for match in re.finditer(r"[大小]?([二三四五六七八九])\s*座", normalized)
        )
        return out

    conflict_if_disjoint("seat_count", seat_counts(query_normalized), seat_counts(listing_normalized))
    conflict_if_disjoint(
        "range",
        values(r"(?<!\d)(\d{2,4})\s*(?:km|公里)(?![a-z])", query_normalized),
        values(r"(?<!\d)(\d{2,4})\s*(?:km|公里)(?![a-z])", listing_normalized),
    )

    emission_pattern = r"国\s*(iv|vi|v|iv|iii|ii|六|五|四|三|二)"
    conflict_if_disjoint(
        "emission",
        values(emission_pattern, query_normalized),
        values(emission_pattern, listing_normalized),
    )

    body_variants = ("两厢", "三厢", "旅行", "敞篷", "硬顶", "五门", "三门", "cross")
    q_body = {token for token in body_variants if token in query_compact}
    l_body = {token for token in body_variants if token in listing_compact}
    conflict_if_disjoint("body_variant", q_body, l_body)

    powertrain_groups = (
        ("phev", "插电混动", "插混"),
        ("hev", "油电混动", "双擎"),
        ("纯电", "bev"),
        ("增程",),
    )

    def powertrains(compact: str) -> set[str]:
        out: set[str] = set()
        for index, aliases in enumerate(powertrain_groups):
            if any(alias in compact for alias in aliases):
                out.add(str(index))
        return out

    conflict_if_disjoint("powertrain", powertrains(query_compact), powertrains(listing_compact))

    # A named special edition is not interchangeable with a generic trim.
    # Requiring the same signature prevents anniversary/limited editions from
    # inheriting the price of common high-volume configurations.
    special_pattern = r"(?:\d{1,3}\s*周年|纪念版|限量版|首发版|特别版|典藏版|收藏版|赛道版)"
    q_special = {re.sub(r"\s+", "", value.lower()) for value in re.findall(special_pattern, query_normalized)}
    l_special = {re.sub(r"\s+", "", value.lower()) for value in re.findall(special_pattern, listing_normalized)}
    if q_special != l_special and (q_special or l_special):
        conflicts.add("special_edition")

    # Model names with an explicit long-wheelbase/body suffix (for example
    # 揽胜极光L) must not fall back to the base generation. Only enforce the
    # query-side marker because marketplace titles include the series name
    # while some query trim fields do not.
    q_long_suffixes = {
        _compact(match.group(1)) + "l"
        for match in re.finditer(r"([\u4e00-\u9fff]{2,})\s*l(?=\s|\d|款|$)", query_normalized)
    }
    if q_long_suffixes and not any(token in listing_compact for token in q_long_suffixes):
        conflicts.add("body_suffix")

    # Named Latin grades are often the only differentiator between sibling
    # trims (FUN/GOODWOOD, DLX/PRM, HSE/PURE). Technical abbreviations are
    # handled elsewhere and excluded from this descriptor check.
    latin_stop = {
        "cvt", "dct", "ecvt", "gdi", "gdit", "td", "tdi", "tsi", "tfsi",
        "turbo", "km", "kwh", "ps", "ev", "hev", "phev", "suv", "awd",
        "fwd", "2wd", "4wd", "auto", "automatic", "manual",
    }

    def latin_descriptors(text: str) -> set[str]:
        tokens = set(re.findall(r"[a-z][a-z0-9]{1,}", text.lower()))
        return {token for token in tokens if token not in latin_stop}

    q_latin = latin_descriptors(query_normalized)
    l_latin = latin_descriptors(listing_normalized)
    if q_latin and not q_latin.issubset(l_latin):
        conflicts.add("latin_descriptor")

    package_groups = (
        [
            ("m运动", "豪华套装"),
            (
                "设计",
                "标准型",
                "标准版",
                "基本型",
                "基本版",
                "时尚型",
                "时尚版",
                "运动型",
                "运动版",
                "运动款",
                "舒适型",
                "舒适版",
                "精英型",
                "精英版",
                "领先型",
                "领先版",
                "豪华型",
                "豪华版",
                "尊享型",
                "尊享版",
                "旗舰型",
                "旗舰版",
                "至尊型",
                "至尊版",
                "智尚型",
                "智尚版",
                "智联型",
                "智联版",
                "智尊型",
                "智尊版",
                "智享版",
                "智享型",
                "智行版",
                "智行型",
                "悦享版",
                "悦享型",
                "臻享款",
                "臻享版",
                "臻享型",
                "行政型",
                "卓越型",
            ),
            ("伯牙", "双imax", "imax", "全家乐", "影院"),
            ("max", "pro", "plus", "ultra", "air", "lite"),
            ("大一版", "大二版", "大三版", "大四版"),
            ("耐力熊", "骑士", "灵动熊", "萌萌熊", "超萌熊"),
            ("艺术家", "经典派", "赛车手"),
            ("颜先锋", "智先锋"),
            ("时尚款", "夹心款", "臻享款"),
            ("pure", "seplus", "hse", "se"),
        ]
        if strict_variant_match
        else [
            ("设计", "时尚", "运动型", "领先", "尊享"),
            ("伯牙", "双imax", "imax", "全家乐", "影院"),
            ("max", "pro", "plus", "ultra", "air", "lite"),
        ]
    )
    for group in package_groups:
        q_hits = {token for token in group if token in query_compact}
        l_hits = {token for token in group if token in listing_compact}
        if q_hits and q_hits != l_hits:
            conflicts.add("package")
    return conflicts


def _model_year_compatible(*, target_year: int | None, listing_year: int | None) -> bool:
    """Keep same-trim-any-year evidence local in model-year space.

    A current query must never be anchored by a decade-old generation merely
    because both titles share an engine token. Unknown listing years remain
    auditable but cannot contribute to a same-year confidence count.
    """

    if not target_year or not listing_year:
        return True
    max_gap = max(0, int(os.environ.get("THIRD_PARTY_MAX_MODEL_YEAR_GAP", "3")))
    return abs(int(target_year) - int(listing_year)) <= max_gap


def _is_import_gle_request(*, brand: str, series: str, trim: str) -> bool:
    compact = _compact(" ".join([brand, series, trim]))
    return "奔驰" in compact and "gle" in compact and (
        "4matic" in compact or bool(re.search(r"gle(?:350|400|450|500)", compact))
    )


def _listing_dict(
    row: DongchediListing,
    *,
    adjusted_price_yuan: float | None = None,
    adjustment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = {
        "sku_id": row.sku_id,
        "title": row.title,
        "brand": row.brand,
        "series": row.series,
        "model_year": row.model_year,
        "trim": row.trim,
        "city": row.city,
        "price_yuan": round(row.price_yuan, 2),
        "price_wan": round(row.price_yuan / 10000.0, 2),
        "mileage_wan_km": row.mileage_wan_km,
        "first_license_year": row.first_license_year,
        "transfer_count": row.transfer_count,
        "match_score": round(row.match_score, 4),
        "match_level": row.match_level,
        "detail_url": row.detail_url,
    }
    if adjusted_price_yuan is not None:
        out["six_element_adjusted_price_yuan"] = round(float(adjusted_price_yuan), 2)
        out["six_element_adjusted_price_wan"] = round(float(adjusted_price_yuan) / 10000.0, 2)
    if adjustment:
        out["six_element_adjustment"] = adjustment
    return out


def _target_first_license_year(payload: dict[str, Any], *, fallback_model_year: int | None = None) -> int | None:
    for key in (
        "first_license_year",
        "firstRegistrationYear",
        "first_registration_year",
        "registration_year",
        "reg_year",
    ):
        value = _safe_int(payload.get(key))
        if value and 1990 <= value <= 2035:
            return value
    for key in (
        "regDate",
        "reg_date",
        "first_registration_date",
        "first_license_date",
        "firstLicenseDate",
        "first_registration_time",
    ):
        text = str(payload.get(key) or "")
        year = _year_from_text(text)
        if year:
            return year
        stamp = pd.to_datetime(text, errors="coerce")
        if pd.notna(stamp):
            return int(stamp.year)
    age = _safe_float(payload.get("age_years"))
    if age is not None:
        quote_time = pd.to_datetime(payload.get("quote_time") or payload.get("query_time"), errors="coerce")
        quote_year = int(quote_time.year) if pd.notna(quote_time) else int(pd.Timestamp.utcnow().year)
        return int(max(1990, round(quote_year - age)))
    return fallback_model_year


def _target_first_license_month(payload: dict[str, Any]) -> str | None:
    for key in (
        "registration_date",
        "regDate",
        "reg_date",
        "first_registration_date",
        "first_license_date",
        "firstLicenseDate",
        "first_registration_time",
    ):
        value = _month_key(payload.get(key))
        if value:
            return value
    return None


def _month_key(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"(20\d{2})\D*(0?[1-9]|1[0-2])", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    stamp = pd.to_datetime(text, errors="coerce")
    if pd.notna(stamp):
        return f"{int(stamp.year):04d}-{int(stamp.month):02d}"
    return None


def _month_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    left_year, left_month = (int(part) for part in left.split("-", 1))
    right_year, right_month = (int(part) for part in right.split("-", 1))
    return abs((left_year - right_year) * 12 + left_month - right_month)


def _normalize_color(value: Any) -> str:
    text = _compact(str(value or ""))
    for suffix in ("车身", "外观", "色"):
        text = text.replace(suffix, "")
    aliases = {
        "灰": "灰",
        "深灰": "灰",
        "浅灰": "灰",
        "银灰": "灰",
        "银": "银",
        "黑": "黑",
        "白": "白",
        "蓝": "蓝",
        "红": "红",
        "棕": "棕",
        "咖啡": "棕",
        "金": "金",
        "绿": "绿",
        "紫": "紫",
        "黄": "黄",
        "橙": "橙",
    }
    return aliases.get(text, text)


def _nearest_exact_vehicle_listing(
    listings: list[DongchediListing],
    *,
    city: str,
    mileage_wan_km: float | None,
    first_license_month: str | None,
    transfer_count: int | None,
    color: str,
) -> tuple[DongchediListing, float, float] | None:
    """Find a current listing that represents the same physical input car.

    Trim and model-year identity are enforced before this function. Missing
    listing attributes are neutral rather than treated as a match; at least
    three supplied seven-element signals must agree before a row is promoted.
    """

    ranked: list[tuple[float, int, DongchediListing]] = []
    for row in listings:
        distance = 0.0
        agreed = 0
        compared = 0
        if city and row.city:
            compared += 1
            if _compact(city) == _compact(row.city):
                agreed += 1
            else:
                distance += 3.0
        month_delta = _month_distance(first_license_month, row.first_license_month)
        if month_delta is not None:
            compared += 1
            if month_delta <= 1:
                agreed += 1
            distance += min(3.0, month_delta * 0.45)
        if mileage_wan_km is not None and row.mileage_wan_km is not None:
            compared += 1
            mileage_delta = abs(float(mileage_wan_km) - float(row.mileage_wan_km))
            if mileage_delta <= 0.35:
                agreed += 1
            distance += min(3.0, mileage_delta * 1.25)
        if transfer_count is not None and row.transfer_count is not None:
            compared += 1
            transfer_delta = abs(int(transfer_count) - int(row.transfer_count))
            if transfer_delta == 0:
                agreed += 1
            distance += min(3.0, transfer_delta * 1.4)
        if color and row.color:
            compared += 1
            if color == row.color:
                agreed += 1
            else:
                distance += 1.2
        if compared >= 3 and agreed >= 3:
            ranked.append((distance, -agreed, row))
    if not ranked:
        return None
    distance, _, row = min(ranked, key=lambda item: (item[0], item[1], -item[2].match_score))
    if distance > 1.0:
        return None
    adjusted, _ = _adjust_listing_price_to_target(
        row,
        target_mileage_wan_km=mileage_wan_km,
        target_first_license_year=(
            int(first_license_month[:4]) if first_license_month else None
        ),
        target_transfer_count=transfer_count,
    )
    return row, adjusted, distance


def _adjust_listing_price_to_target(
    row: DongchediListing,
    *,
    target_mileage_wan_km: float | None,
    target_first_license_year: int | None,
    target_transfer_count: int | None,
) -> tuple[float, dict[str, Any]]:
    """Normalize a DCD asking-price listing to the target six elements.

    DCD rows are visible B2C asking prices.  This function only adjusts the
    asking-price level for mileage/registration/transfer differences; the
    later floor/point multipliers convert the adjusted asking price into a
    sold-price proxy.
    """

    factor = 1.0
    signals: list[str] = []
    mileage_factor = 1.0
    year_factor = 1.0
    transfer_factor = 1.0
    if target_mileage_wan_km is not None and row.mileage_wan_km is not None:
        mileage_delta = float(target_mileage_wan_km) - float(row.mileage_wan_km)
        mileage_factor = math.exp(-0.030 * max(mileage_delta, 0.0)) * math.exp(0.015 * max(-mileage_delta, 0.0))
        mileage_factor = float(min(1.12, max(0.78, mileage_factor)))
        factor *= mileage_factor
        signals.append("mileage")
    else:
        mileage_delta = None
    if target_first_license_year is not None and row.first_license_year is not None:
        year_delta = int(target_first_license_year) - int(row.first_license_year)
        # Newer target cars can command a premium; older target cars need a
        # stronger discount because buyer perception and warranty age move fast.
        year_factor = (1.050 ** max(year_delta, 0)) * (0.930 ** max(-year_delta, 0))
        year_factor = float(min(1.18, max(0.70, year_factor)))
        factor *= year_factor
        signals.append("first_license_year")
    else:
        year_delta = None
    if target_transfer_count is not None and row.transfer_count is not None:
        transfer_delta = int(target_transfer_count) - int(row.transfer_count)
        transfer_factor = (0.985 ** max(transfer_delta, 0)) * (1.006 ** max(-transfer_delta, 0))
        transfer_factor = float(min(1.04, max(0.93, transfer_factor)))
        factor *= transfer_factor
        signals.append("transfer")
    else:
        transfer_delta = None
    factor = float(min(1.22, max(0.62, factor)))
    adjusted = float(row.price_yuan) * factor
    return adjusted, {
        "factor": round(factor, 6),
        "mileage_factor": round(float(mileage_factor), 6),
        "first_license_year_factor": round(float(year_factor), 6),
        "transfer_factor": round(float(transfer_factor), 6),
        "mileage_delta_wan_km": round(float(mileage_delta), 4) if mileage_delta is not None else None,
        "first_license_year_delta": int(year_delta) if year_delta is not None else None,
        "transfer_delta": int(transfer_delta) if transfer_delta is not None else None,
        "has_any_six_element_signal": bool(signals),
        "signals": signals,
    }


def _price_yuan(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if match:
        return float(match.group(1)) * 10000.0
    numeric = pd.to_numeric(text, errors="coerce")
    if pd.isna(numeric):
        return None
    number = float(numeric)
    return number * 10000.0 if number < 1000 else number


def _mileage_from_text(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*万公里", str(text or ""))
    return float(match.group(1)) if match else None


def _year_from_text(text: str) -> int | None:
    match = re.search(r"((?:19|20)\d{2})", str(text or ""))
    return int(match.group(1)) if match else None


def _safe_int(value: Any) -> int | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return int(numeric)


def _safe_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    number = float(numeric)
    if not math.isfinite(number):
        return None
    return number


def _present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _compact(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff.]+", "", str(value or "").lower())


def _strip_brand_prefix(brand: str, series: str) -> str:
    brand_key = _compact(brand)
    series_key = _compact(series)
    if brand_key and series_key.startswith(brand_key):
        return series_key[len(brand_key) :]
    return series_key


def _series_hint_from_text(text: str) -> str:
    compact = _compact(text)
    patterns = [
        "宝马5系", "宝马7系", "宝马4系", "奥迪a4l", "奥迪a8", "奔驰gle", "奔驰cls",
        "别克gl8", "亚洲龙", "捷豹xel", "凌派", "睿翼",
    ]
    for pattern in patterns:
        if _compact(pattern) in compact:
            return pattern
    return ""


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(float(v) for v in values if v and math.isfinite(float(v)))
    if not ordered:
        return float("nan")
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)
