from __future__ import annotations

from functools import lru_cache
import math
import os
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from .dongchedi_usedcar_market import (
    DongchediListing,
    DongchediUsedCarMarket,
    _adjust_listing_price_to_target,
    _compact,
    _safe_float,
    _safe_int,
    _target_first_license_year,
    _cross_source_trim_identity,
    _trim_match_score,
    _model_year_compatible,
    _year_from_text,
)


ROOT = Path(__file__).resolve().parents[1]


def _fresh_snapshot_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "snapshot_date" not in frame.columns:
        return frame
    max_age_days = max(1.0, float(os.environ.get("THIRD_PARTY_LISTING_MAX_AGE_DAYS", "14")))
    snapshot_time = pd.to_datetime(frame["snapshot_date"], errors="coerce", utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
    return frame.loc[snapshot_time.ge(cutoff)].copy()


def _quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q))


def _weighted_median(values: list[float], weights: list[float]) -> float:
    order = np.argsort(values)
    sorted_values = np.asarray(values, dtype=float)[order]
    sorted_weights = np.asarray(weights, dtype=float)[order]
    return float(sorted_values[np.searchsorted(np.cumsum(sorted_weights), sorted_weights.sum() / 2.0)])


def _sibling_series_variant_conflict(series: str, target_trim: str, listing_title: str) -> bool:
    """Reject sibling body variants that a source labels under one series.

    Some marketplace titles put variants such as 致炫X under the base 致炫
    series.  A substring series filter therefore is not sufficient even when
    the trim words overlap.
    """

    target = _compact(" ".join([series, target_trim]))
    listing = _compact(listing_title)
    explicit_variants = (
        "致炫x",
        "致享x",
        "两厢版",
        "三厢版",
        "旅行版",
        "cross版",
    )
    return any(token in listing and token not in target for token in explicit_variants)


class ThirdPartyListingPriceService:
    """Offline three-source asking-price retrieval.

    This service returns a listing-price role only. It never converts these
    values into the B2C transaction target or the C2B purchase target.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.dongchedi = DongchediUsedCarMarket(self.root)
        self._guazi: pd.DataFrame | None = None
        self._autohome: pd.DataFrame | None = None
        self._local_pool_index_cache: dict[tuple[str, str, str], np.ndarray] = {}

    def _load_guazi(self) -> pd.DataFrame:
        if self._guazi is not None:
            return self._guazi
        path = self.root / "data" / "knowledge" / "current_guazi_used_market_listing_snapshot.csv"
        frame = pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
        frame = _fresh_snapshot_rows(frame)
        if not frame.empty:
            frame["_brand_key"] = frame.get("canonical_brand", "").fillna("").astype(str).map(_compact)
            frame["_series_key"] = frame.get("canonical_series", "").fillna("").astype(str).map(_compact)
        self._guazi = frame
        return frame

    def _load_autohome(self) -> pd.DataFrame:
        if self._autohome is not None:
            return self._autohome
        full_snapshot = self.root / "data" / "external" / "autohome_current_usedcar_market.parquet"
        full_summary = self.root / "data" / "external" / "autohome_current_usedcar_market_summary.json"
        full_snapshot_complete = False
        if full_snapshot.exists() and full_summary.exists():
            try:
                import json

                summary = json.loads(full_summary.read_text(encoding="utf-8"))
                full_snapshot_complete = bool(summary.get("complete")) and int(summary.get("unique_listing_rows") or 0) >= 1_000
            except Exception:
                full_snapshot_complete = False
        candidates = [
            *([full_snapshot] if full_snapshot_complete else []),
            self.root / "data" / "knowledge" / "current_che168_series_listing_snapshot_20260703.csv",
        ]
        path = next((item for item in candidates if item.exists()), None)
        if path is None:
            frame = pd.DataFrame()
        elif path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path, low_memory=False)
        frame = _fresh_snapshot_rows(frame)
        if not frame.empty:
            title = frame.get("carname", frame.get("display_name", pd.Series("", index=frame.index)))
            frame["_title_key"] = title.fillna("").astype(str).map(_compact)
            extracted_series = title.fillna("").astype(str).str.replace(r"\s*20\d{2}款.*$", "", regex=True)
            frame["_series_key"] = extracted_series.map(_compact)
        self._autohome = frame
        return frame

    @staticmethod
    def _local_listing(
        row: pd.Series,
        *,
        source: str,
        target_trim: str,
        brand: str,
        series: str,
    ) -> DongchediListing | None:
        if source == "guazi":
            title = str(row.get("display_name") or row.get("trim_name") or "")
            listing_trim = str(row.get("trim_name") or title)
            price = _safe_float(row.get("listing_price_yuan"))
            city = str(row.get("city") or "")
            mileage = _safe_float(row.get("mileage_wan_km"))
            register = str(row.get("register_month") or row.get("vehicle_model_date_raw") or "")
            transfer = _safe_int(row.get("transfer_count"))
            model_year = _safe_int(row.get("model_year")) or _year_from_text(listing_trim)
            listing_id = str(row.get("listing_id") or "")
            url = str(row.get("source_url") or "")
        else:
            title = str(row.get("carname") or row.get("display_name") or "")
            listing_trim = title
            price = _safe_float(row.get("price_yuan"))
            if not price:
                price_wan = _safe_float(row.get("price_wan"))
                price = price_wan * 10_000 if price_wan else None
            city = str(row.get("city_name") or "")
            mileage = _safe_float(row.get("mileage_wan_km"))
            register = str(row.get("first_register_date") or row.get("register_date") or "")
            transfer = _safe_int(row.get("transfer_count"))
            model_year = _safe_int(row.get("model_year")) or _year_from_text(listing_trim)
            listing_id = str(row.get("listing_id") or "")
            url = str(row.get("source_url") or "")
        if not price or price <= 0 or not title:
            return None
        if _sibling_series_variant_conflict(series, target_trim, title):
            return None
        if not _cross_source_trim_identity(target_trim, listing_trim):
            return None
        score, level = _trim_match_score(target_trim, listing_trim)
        if level not in {"exact_trim", "strong_trim"}:
            return None
        return DongchediListing(
            sku_id=listing_id,
            title=title,
            series_id=None,
            brand=brand,
            series=series,
            model_year=model_year,
            trim=listing_trim,
            city=city,
            price_yuan=float(price),
            mileage_wan_km=mileage,
            first_license_year=_year_from_text(register),
            first_license_month=None,
            transfer_count=transfer,
            color="",
            match_score=float(score),
            match_level=level,
            detail_url=url,
        )

    def _local_probe(self, source: str, payload: dict[str, Any]) -> dict[str, Any]:
        brand = str(payload.get("brand") or "").strip()
        series = str(payload.get("series") or "").strip()
        trim = str(payload.get("trim") or payload.get("model") or payload.get("modelName") or "").strip()
        city = str(payload.get("city") or "").strip()
        year = _safe_int(payload.get("model_year") or payload.get("modelYear") or _year_from_text(trim))
        brand_key, series_key = _compact(brand), _compact(series)
        if not series_key:
            return {"enabled": False, "source": source, "reason": "SERIES_MISSING"}
        frame = self._load_guazi() if source == "guazi" else self._load_autohome()
        if frame.empty:
            return {"enabled": False, "source": source, "reason": "SNAPSHOT_EMPTY_OR_SERIES_MISSING"}
        pool_key = (source, brand_key, series_key)
        indices = self._local_pool_index_cache.get(pool_key)
        if indices is None:
            if source == "guazi":
                mask = frame["_series_key"].eq(series_key)
                if brand_key:
                    mask &= frame["_brand_key"].eq(brand_key)
            else:
                title = frame["_title_key"]
                mask = frame["_series_key"].eq(series_key)
                if not mask.any():
                    # Some imported series names carry a suffix in one source
                    # but not another. This fallback remains title-scoped and
                    # the later trim matcher still rejects configuration drift.
                    mask = title.str.contains(re.escape(series_key), regex=True)
                if brand_key:
                    brand_mask = mask & title.str.contains(re.escape(brand_key), regex=True)
                    if brand_mask.any():
                        mask = brand_mask
            indices = frame.index[mask].to_numpy()
            self._local_pool_index_cache[pool_key] = indices
        pool = frame.loc[indices]
        listings = [
            listing
            for listing in (
                self._local_listing(row, source=source, target_trim=trim, brand=brand, series=series)
                for _, row in pool.iterrows()
            )
            if listing is not None
        ]
        year_compatible = [
            item
            for item in listings
            if _model_year_compatible(target_year=year, listing_year=item.model_year)
        ]
        year_gap_rejected_count = len(listings) - len(year_compatible)
        same_year = [item for item in year_compatible if year and item.model_year == year]
        year_pool = same_year if same_year else year_compatible
        city_pool = [item for item in year_pool if city and item.city == city]
        usable = city_pool if len(city_pool) >= 2 else year_pool
        if not usable:
            return {
                "enabled": False,
                "source": source,
                "reason": "NO_STRICT_TRIM_MATCH",
                "pool_rows": len(pool),
                "year_gap_rejected_count": year_gap_rejected_count,
            }
        target_mileage = _safe_float(payload.get("mileage_wan_km", payload.get("mileage")))
        target_transfer = _safe_int(payload.get("transfer_count", payload.get("transfer")))
        target_first_year = _target_first_license_year(payload, fallback_model_year=year)
        adjusted = [
            (item, *_adjust_listing_price_to_target(
                item,
                target_mileage_wan_km=target_mileage,
                target_first_license_year=target_first_year,
                target_transfer_count=target_transfer,
            ))
            for item in usable
        ]
        adjusted = [record for record in adjusted if record[1] and record[1] > 0]
        prices = [float(record[1]) for record in adjusted]
        return {
            "enabled": bool(prices),
            "source": source,
            "match_level": (
                "city_same_trim_same_year"
                if len(city_pool) >= 2 and same_year
                else "city_same_trim_any_year"
                if len(city_pool) >= 2
                else "national_same_trim_same_year"
                if same_year
                else "national_same_trim_any_year"
            ),
            "matched_count": len(prices),
            "year_gap_rejected_count": year_gap_rejected_count,
            "price_q25_yuan": _quantile(prices, 0.25) if prices else None,
            "price_median_yuan": _quantile(prices, 0.50) if prices else None,
            "price_q75_yuan": _quantile(prices, 0.75) if prices else None,
            "listings": [
                {
                    "listing_id": item.sku_id,
                    "title": item.title,
                    "city": item.city,
                    "raw_listing_price_yuan": item.price_yuan,
                    "adjusted_listing_price_yuan": adjusted_price,
                    "source_url": item.detail_url,
                }
                for item, adjusted_price, _ in adjusted[:20]
            ],
        }

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        dcd = self.dongchedi.probe(payload)
        sources = [
            {
                "enabled": bool(dcd.get("enabled")),
                "source": "dongchedi",
                "match_level": dcd.get("match_level"),
                "matched_count": int(dcd.get("matched_count") or 0),
                "price_q25_yuan": dcd.get("price_q25_yuan"),
                "price_median_yuan": dcd.get("price_median_yuan"),
                "price_q75_yuan": dcd.get("price_q75_yuan"),
                "listings": dcd.get("listings") or [],
                "exact_vehicle_match": bool(dcd.get("exact_vehicle_match")),
                "exact_vehicle_listing_yuan": dcd.get("exact_vehicle_listing_yuan"),
                "exact_vehicle_adjusted_listing_yuan": dcd.get(
                    "exact_vehicle_adjusted_listing_yuan"
                ),
                "exact_vehicle_sku_id": dcd.get("exact_vehicle_sku_id"),
                "exact_vehicle_distance": dcd.get("exact_vehicle_distance"),
            },
            self._local_probe("guazi", payload),
            self._local_probe("autohome", payload),
        ]
        usable = [item for item in sources if item.get("enabled") and _safe_float(item.get("price_median_yuan"))]
        if not usable:
            return {
                "enabled": False,
                "price_role": "THIRD_PARTY_B2C_LISTING_PRICE",
                "reason": "NO_STRICT_THIRD_PARTY_LISTING_MATCH",
                "sources": sources,
            }
        medians = [float(item["price_median_yuan"]) for item in usable]
        weights = [min(3.0, math.sqrt(max(1, int(item.get("matched_count") or 1)))) for item in usable]
        # Inventory counts are not independent observations across platforms:
        # the same dealer vehicle is often syndicated. Use one vote per source
        # as the primary market point and retain the count-weighted value only
        # for audit.
        market_consensus = float(np.median(np.asarray(medians, dtype=float)))
        exact_dcd = _safe_float(dcd.get("exact_vehicle_adjusted_listing_yuan"))
        if exact_dcd:
            # The same physical vehicle is the strongest asking-price anchor,
            # but a seller can still be optimistic or undercut the market.
            # Retain a market-consensus vote and cap the strategy adjustment.
            blended = 0.72 * exact_dcd + 0.28 * market_consensus
            listing_point = float(np.clip(blended, exact_dcd * 0.96, exact_dcd * 1.04))
        else:
            listing_point = market_consensus
        exact_market_gap = (
            abs(exact_dcd - market_consensus) / market_consensus
            if exact_dcd and market_consensus > 0
            else None
        )
        weighted_listing_point = _weighted_median(medians, weights)
        lows = [float(item.get("price_q25_yuan") or item["price_median_yuan"]) for item in usable]
        highs = [float(item.get("price_q75_yuan") or item["price_median_yuan"]) for item in usable]
        total_listing_count = sum(int(item.get("matched_count") or 0) for item in usable)
        dispersion_ratio = (max(medians) - min(medians)) / listing_point if listing_point > 0 else float("inf")
        same_year_source_count = sum("same_year" in str(item.get("match_level") or "") for item in usable)
        safe_for_transaction_calibration = bool(
            len(usable) >= 2
            and total_listing_count >= 5
            and same_year_source_count >= 2
            and dispersion_ratio <= 0.18
        )
        confidence = (
            "HIGH"
            if safe_for_transaction_calibration
            else "MEDIUM"
            if (exact_dcd is not None or total_listing_count >= 2) and dispersion_ratio <= 0.30
            else "LOW"
        )
        return {
            "enabled": True,
            "version": "third_party_listing_price_v3_exact_vehicle_consensus",
            "price_role": "THIRD_PARTY_B2C_LISTING_PRICE",
            "listing_price_yuan": round(listing_point, 2),
            "listing_price_wan": round(listing_point / 10_000.0, 2),
            "source_weighted_listing_price_yuan": round(weighted_listing_point, 2),
            "market_consensus_listing_price_yuan": round(market_consensus, 2),
            "exact_dcd_vehicle_match": bool(exact_dcd),
            "exact_dcd_vehicle_listing_yuan": round(exact_dcd, 2) if exact_dcd else None,
            "exact_dcd_vehicle_sku_id": dcd.get("exact_vehicle_sku_id"),
            "exact_dcd_vehicle_distance": dcd.get("exact_vehicle_distance"),
            "exact_dcd_to_market_gap_ratio": (
                round(float(exact_market_gap), 6)
                if exact_market_gap is not None
                else None
            ),
            "listing_range_yuan": [round(min(lows), 2), round(max(highs), 2)],
            "source_count": len(usable),
            "same_year_source_count": same_year_source_count,
            "total_listing_count": total_listing_count,
            "cross_source_dispersion_ratio": round(float(dispersion_ratio), 6),
            "safe_for_transaction_calibration": safe_for_transaction_calibration,
            "confidence": confidence,
            "asking_price_is_not_transaction_price": True,
            "sources": sources,
        }


@lru_cache(maxsize=1)
def get_third_party_listing_price_service() -> ThirdPartyListingPriceService:
    return ThirdPartyListingPriceService()
