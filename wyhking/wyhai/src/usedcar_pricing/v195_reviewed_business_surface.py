"""Strict-match serving for the reviewed multi-source business price surface."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .v192_16_semantics import canonicalize_trim
from .v195_daily_vehicle_knowledge import exact_seven_element_fingerprint
from .v195_element_adjustments import element_log_adjustment


VERSION = "v195_386_reviewed_business_price_surface"
EFFECTIVE_FROM = pd.Timestamp("2026-07-12 11:26:00+08:00")
POST_JUL14_REVIEW_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 12:00:00+08:00")
V195_410_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 14:00:00+08:00")
V195_413_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 16:00:00+08:00")
V195_415_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 18:00:00+08:00")
V195_418_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 20:00:00+08:00")
V195_420_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 22:00:00+08:00")
V195_423_EFFECTIVE_FROM = pd.Timestamp("2026-07-15 00:00:00+08:00")
V195_426_EFFECTIVE_FROM = pd.Timestamp("2026-07-15 02:00:00+08:00")
V195_429_EFFECTIVE_FROM = pd.Timestamp("2026-07-15 04:00:00+08:00")
V195_433_EFFECTIVE_FROM = pd.Timestamp("2026-07-15 06:00:00+08:00")
V195_436_EFFECTIVE_FROM = pd.Timestamp("2026-07-15 08:00:00+08:00")
V195_439_EFFECTIVE_FROM = pd.Timestamp("2026-07-14 16:00:00+08:00")


def _compact(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _trim_alias_key(value: Any) -> str:
    text = _compact(value)
    for source, target in (
        ("标准型", "标准"),
        ("标准版", "标准"),
        ("豪华型", "豪华"),
        ("豪华版", "豪华"),
        ("旗舰型", "旗舰"),
        ("旗舰版", "旗舰"),
        ("尊贵型", "尊贵"),
        ("尊贵版", "尊贵"),
        ("舒适型", "舒适"),
        ("舒适版", "舒适"),
    ):
        text = text.replace(source, target)
    return text


def _trim_lookup_variants(trim: Any, brand: Any, series: Any) -> list[str]:
    """Return strict catalog spellings for full vehicle names and trim names."""

    raw = str(trim or "").strip()
    if not raw:
        return []
    variants = [raw]
    without_year = re.sub(r"(?:19|20)\d{2}\s*款", "", raw).strip()
    variants.append(without_year)
    prefixes = sorted(
        {
            str(brand or "").strip(),
            str(series or "").strip(),
            f"{str(brand or '').strip()}{str(series or '').strip()}",
            f"{str(brand or '').strip()} {str(series or '').strip()}",
        },
        key=len,
        reverse=True,
    )
    for value in list(variants):
        candidate = value
        for prefix in prefixes:
            if prefix and candidate.lower().startswith(prefix.lower()):
                candidate = candidate[len(prefix) :].strip()
                break
        candidate = re.sub(r"(?:19|20)\d{2}\s*款", "", candidate).strip()
        if candidate:
            variants.append(candidate)
    unique: list[str] = []
    seen: set[str] = set()
    for value in variants:
        key = _compact(value)
        if key and key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def _number(payload: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = pd.to_numeric(payload.get(key), errors="coerce")
        if pd.notna(value):
            return float(value)
    return np.nan


def _text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _timestamp(payload: dict[str, Any], *keys: str) -> pd.Timestamp:
    for key in keys:
        value = pd.to_datetime(payload.get(key), errors="coerce")
        if pd.notna(value):
            return value
    return pd.NaT


def _condition_value(value: Any) -> float:
    grade = str(value or "").strip().upper()
    return {
        "A": 0.0,
        "B": float(np.log(0.97)),
        "C": float(np.log(0.91)),
        "D": float(np.log(0.83)),
        "E": float(np.log(0.74)),
    }.get(grade, float(np.log(0.98)))


_SEMANTIC_HARD_FIELDS = (
    "parsed_energy",
    "parsed_powertrain",
    "parsed_transmission",
    "parsed_drivetrain",
    "parsed_wheelbase",
    "parsed_body",
    "parsed_seat_count",
    "parsed_range_battery",
    "parsed_facelift",
)


def _semantic_trim(trim: Any, brand: Any, series: Any, model_year: Any) -> dict[str, Any]:
    return canonicalize_trim(
        trim,
        brand=brand,
        series=series,
        model_year=model_year,
    )


def _config_grade_value(value: Any) -> float:
    text = str(value or "").lower()
    levels = (
        ("entry", -2.0),
        ("fashion", -1.0),
        ("comfort", -0.5),
        ("elite", 0.0),
        ("premium", 0.5),
        ("luxury", 1.0),
        ("design", 1.0),
        ("dynamic", 1.0),
        ("m_sport", 1.0),
        ("sline", 1.0),
        ("m_sport_shadow", 1.5),
    )
    matches = [score for token, score in levels if token in text]
    return max(matches) if matches else 0.0


def _strict_semantic_compatibility(
    query: dict[str, Any], candidate: dict[str, Any]
) -> tuple[bool, float, float]:
    """Return compatibility, distance penalty and bounded config adjustment.

    This is deliberately stricter than same-series/year retrieval.  A known
    powertrain token on the query must also be known and equal on the candidate
    so that, for example, 525 can never be priced from 530 evidence.
    """

    known = 0
    penalty = 0.0
    for field in _SEMANTIC_HARD_FIELDS:
        query_value = str(query.get(field) or "").strip().lower()
        candidate_value = str(candidate.get(field) or "").strip().lower()
        if not query_value:
            continue
        known += 1
        if not candidate_value:
            # Powertrain and range define the commercial trim and cannot be
            # treated as optional once the user supplied them.
            if field in {"parsed_powertrain", "parsed_range_battery"}:
                return False, np.inf, 0.0
            penalty += 0.35
            continue
        if query_value != candidate_value:
            return False, np.inf, 0.0

    # A semantic fallback with no usable discriminator is just
    # same_series_year in disguise and is therefore forbidden.
    if known == 0:
        return False, np.inf, 0.0

    query_grade = str(query.get("parsed_config_grade") or "")
    candidate_grade = str(candidate.get("parsed_config_grade") or "")
    grade_delta = _config_grade_value(query_grade) - _config_grade_value(candidate_grade)
    if query_grade and candidate_grade and query_grade != candidate_grade:
        penalty += min(abs(grade_delta) * 0.20, 0.60)
    # One grade step is a small equipment adjustment, not a new price anchor.
    config_log_adjustment = float(np.clip(grade_delta * 0.015, -0.045, 0.045))
    return True, penalty, config_log_adjustment


@dataclass(frozen=True)
class SurfaceMatch:
    row: dict[str, Any]
    match_level: str
    distance: float
    local_factor: float


class ReviewedBusinessPriceSurface:
    """Serve only a strict model/trim cell and bounded local interpolation."""

    def __init__(
        self,
        path: Path,
        *,
        max_distance: float = 1.20,
        stale_internal_distance_penalty: float = 0.0,
        allow_semantic_fallback: bool = False,
    ) -> None:
        self.path = path
        post_jul14_review_book = any(
            token in path.name.lower()
            for token in (
                "v195406", "v195409", "v195410", "v195413",
                "v195415", "v195418", "v195420", "v195423", "v195426",
                "v195429", "v195433", "v195436", "v195439",
            )
        )
        self.version = (
            "v195_439_full_catalog_final_appraiser_price_book"
            if "v195439" in path.name.lower()
            else "v195_436_fourth_missing_external_evidence_wave_price_book"
            if "v195436" in path.name.lower()
            else
            "v195_433_third_missing_external_evidence_wave_price_book"
            if "v195433" in path.name.lower()
            else
            "v195_429_second_missing_external_evidence_wave_price_book"
            if "v195429" in path.name.lower()
            else
            "v195_426_first_missing_external_evidence_wave_price_book"
            if "v195426" in path.name.lower()
            else
            "v195_423_second_acquisition_market_conflict_wave_price_book"
            if "v195423" in path.name.lower()
            else
            "v195_420_additional_exact_seven_element_price_book"
            if "v195420" in path.name.lower()
            else
            "v195_418_acquisition_market_conflict_wave_price_book"
            if "v195418" in path.name.lower()
            else
            "v195_415_deferred_evidence_wave_price_book"
            if "v195415" in path.name.lower()
            else
            "v195_413_market_conflict_wave_price_book"
            if "v195413" in path.name.lower()
            else
            "v195_410_exact_seven_element_appraisal_price_book"
            if "v195410" in path.name.lower()
            else
            "v195_409_first_full_catalog_signoff_wave_price_book"
            if "v195409" in path.name.lower()
            else
            "v195_406_manual_identity_full_price_book"
            if "v195406" in path.name.lower()
            else "v195_404_full_seven_element_profit_review_price_book"
            if "v195404" in path.name.lower()
            else "v195_402_catalog_identity_price_book"
            if "v195402" in path.name.lower()
            else
            "v195_401_human_appraiser_tail_review_price_book"
            if "v195401" in path.name.lower()
            else "v195_395_appraiser_adjudicated_single_answer_price_book"
            if "unified_single_answer" in path.name
            else VERSION
        )
        # v195.406 contains appraiser decisions made after the 2026-07-14
        # forward file was opened.  A historical request must never be able to
        # see those rows, otherwise a post-review replay can masquerade as a
        # forward quote.  Older books retain their original activation time.
        self.effective_from = (
            V195_439_EFFECTIVE_FROM
            if "v195439" in path.name.lower()
            else V195_436_EFFECTIVE_FROM
            if "v195436" in path.name.lower()
            else V195_433_EFFECTIVE_FROM
            if "v195433" in path.name.lower()
            else V195_429_EFFECTIVE_FROM
            if "v195429" in path.name.lower()
            else V195_426_EFFECTIVE_FROM
            if "v195426" in path.name.lower()
            else V195_423_EFFECTIVE_FROM
            if "v195423" in path.name.lower()
            else V195_420_EFFECTIVE_FROM
            if "v195420" in path.name.lower()
            else V195_418_EFFECTIVE_FROM
            if "v195418" in path.name.lower()
            else V195_415_EFFECTIVE_FROM
            if "v195415" in path.name.lower()
            else V195_413_EFFECTIVE_FROM
            if "v195413" in path.name.lower()
            else V195_410_EFFECTIVE_FROM
            if "v195410" in path.name.lower()
            else POST_JUL14_REVIEW_EFFECTIVE_FROM
            if post_jul14_review_book
            else EFFECTIVE_FROM
        )
        self.max_distance = float(max_distance)
        self.stale_internal_distance_penalty = float(stale_internal_distance_penalty)
        self.allow_semantic_fallback = bool(allow_semantic_fallback)
        self._lazy = False
        self._lazy_cache: OrderedDict[tuple[Any, ...], pd.DataFrame] = OrderedDict()
        self.row_count = pq.ParquetFile(path).metadata.num_rows if path.exists() else 0
        self._lazy = self.row_count > 100_000
        self.frame = (
            pd.DataFrame()
            if self._lazy
            else pd.read_parquet(path)
            if path.exists()
            else pd.DataFrame()
        )
        self._model_indices: dict[int, pd.Index] = {}
        self._model_year_indices: dict[tuple[int, int], pd.Index] = {}
        self._trim_indices: dict[tuple[str, str, str], pd.Index] = {}
        self._trim_year_indices: dict[tuple[str, str, str, int], pd.Index] = {}
        self._exact_indices: dict[str, pd.Index] = {}
        if self.frame.empty:
            return
        self.frame = self._prepare_frame(self.frame)
        self._build_indices()

    @staticmethod
    def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame["model_id_num"] = pd.to_numeric(frame["model_id"], errors="coerce")
        frame["model_year_num"] = pd.to_numeric(frame["model_year"], errors="coerce")
        frame["trim_key"] = frame["trim_key"].fillna("").astype(str).map(_compact)
        for column in ("brand", "series", "city", "color", "condition_grade"):
            frame[f"{column}_key"] = frame[column].fillna("").astype(str).map(_compact)
        return frame

    def _build_indices(self) -> None:
        valid_model = self.frame.loc[self.frame["model_id_num"].notna()]
        self._model_indices = {
            int(key): group.index
            for key, group in valid_model.groupby("model_id_num", sort=False)
        }
        valid_model_year = valid_model.loc[valid_model["model_year_num"].notna()]
        self._model_year_indices = {
            (int(model_id), int(model_year)): group.index
            for (model_id, model_year), group in valid_model_year.groupby(
                ["model_id_num", "model_year_num"], sort=False
            )
        }
        valid_trim_year = self.frame.loc[
            self.frame["trim_key"].ne("")
            & self.frame["series_key"].ne("")
            & self.frame["model_year_num"].notna()
        ]
        self._trim_year_indices = {
            (str(brand), str(series), str(trim), int(year)): group.index
            for (brand, series, trim, year), group in valid_trim_year.groupby(
                ["brand_key", "series_key", "trim_key", "model_year_num"], sort=False
            )
        }
        self._trim_indices = {
            (str(brand), str(series), str(trim)): group.index
            for (brand, series, trim), group in valid_trim_year.groupby(
                ["brand_key", "series_key", "trim_key"], sort=False
            )
        }
        exact = self.frame.loc[
            self.frame["knowledge_cell_id"].fillna("").astype(str).str.startswith("exact7_")
        ]
        self._exact_indices = {
            str(key): group.index
            for key, group in exact.groupby("knowledge_cell_id", sort=False)
        }

    @staticmethod
    def _query_exact_fingerprint(payload: dict[str, Any]) -> str:
        return exact_seven_element_fingerprint(
            {
                "model_id": _number(payload, "model_id", "modelId", "vehicle_model_id", "trim_id"),
                "model_year": _number(payload, "model_year", "modelYear", "vehicle_model_year"),
                "trim": _text(
                    payload,
                    "trim",
                    "model",
                    "modelName",
                    "standard_vehicle",
                    "standardModelName",
                    "model_name",
                ),
                "registration_date": _text(
                    payload,
                    "first_registration_date",
                    "registration_date",
                    "registration_time",
                    "license_date",
                    "reg_date",
                    "regDate",
                    "firstLicenseDate",
                ),
                "mileage_wan_km": _number(payload, "mileage_wan_km", "mileage", "mileageWanKm"),
                "city": _text(payload, "city", "city_name"),
                "transfer_count": _number(payload, "transfer_count", "transferCount", "transfers", "transfer"),
                "color": _text(payload, "color", "color_raw", "exterior_color"),
                "condition_grade": _text(
                    payload, "condition_grade", "inspection_grade", "condition"
                ),
            }
        )

    def _exact_reviewed_match(self, payload: dict[str, Any]) -> SurfaceMatch | None:
        fingerprint = self._query_exact_fingerprint(payload)
        if self._lazy:
            candidates = self._lazy_read(
                ("exact_manual", fingerprint),
                [("knowledge_cell_id", "==", fingerprint)],
            )
        else:
            indices = self._exact_indices.get(fingerprint)
            candidates = self.frame.loc[indices] if indices is not None else pd.DataFrame()
        if candidates.empty:
            return None
        reviewed = candidates.loc[
            candidates.get("review_method", pd.Series("", index=candidates.index))
            .fillna("")
            .astype(str)
            .eq("HUMAN_APPRAISER_EXPLICIT_SEVEN_ELEMENT_TAIL_REVIEW")
        ]
        if reviewed.empty:
            return None
        return SurfaceMatch(
            row=reviewed.iloc[-1].to_dict(),
            match_level="exact_human_appraiser_review",
            distance=0.0,
            local_factor=1.0,
        )

    def _lazy_read(self, key: tuple[Any, ...], filters: list[tuple[str, str, Any]]) -> pd.DataFrame:
        cached = self._lazy_cache.get(key)
        if cached is not None:
            self._lazy_cache.move_to_end(key)
            return cached
        try:
            frame = pd.read_parquet(self.path, filters=filters)
        except Exception:
            frame = pd.DataFrame()
        if not frame.empty:
            frame = self._prepare_frame(frame).reset_index(drop=True)
        self._lazy_cache[key] = frame
        self._lazy_cache.move_to_end(key)
        while len(self._lazy_cache) > 16:
            self._lazy_cache.popitem(last=False)
        return frame

    def _lazy_candidates(
        self,
        *,
        model_id: float,
        model_year: float,
        brand: str,
        series: str,
        trim: str,
    ) -> pd.DataFrame:
        frames = []
        if pd.notna(model_id) and model_id > 0:
            filters = [("model_id", "==", int(model_id))]
            key: tuple[Any, ...] = ("model", int(model_id))
            frames.append(self._lazy_read(key, filters))
        if brand and series and trim:
            for trim_variant in _trim_lookup_variants(trim, brand, series):
                text_key = ("text", brand, series, trim_variant)
                text_filters = [
                    ("brand", "==", brand),
                    ("series", "==", series),
                    ("trim", "==", trim_variant),
                ]
                frames.append(self._lazy_read(text_key, text_filters))
        usable = [frame for frame in frames if not frame.empty]
        if not usable:
            return pd.DataFrame()
        return pd.concat(usable, ignore_index=True, sort=False).drop_duplicates(
            "knowledge_cell_id", keep="last"
        ).reset_index(drop=True)

    def _lazy_series_year_candidates(
        self, *, brand: str, series: str, model_year: float
    ) -> pd.DataFrame:
        if not brand or not series or pd.isna(model_year):
            return pd.DataFrame()
        year = int(model_year)
        return self._lazy_read(
            ("series_year_semantic", brand, series, year),
            [("brand", "==", brand), ("series", "==", series), ("model_year", "==", year)],
        )

    @property
    def enabled(self) -> bool:
        return self.path.exists() and (self._lazy or not self.frame.empty)

    def _quote_time_is_eligible(self, payload: dict[str, Any]) -> bool:
        quote_time = _timestamp(payload, "quote_time", "prediction_time", "target_date")
        if pd.isna(quote_time):
            return True
        if quote_time.tzinfo is None:
            quote_time = quote_time.tz_localize("Asia/Shanghai")
        else:
            quote_time = quote_time.tz_convert("Asia/Shanghai")
        return quote_time >= self.effective_from

    def match(self, payload: dict[str, Any], side: str) -> SurfaceMatch | None:
        if not self.enabled or not self._quote_time_is_eligible(payload):
            return None
        exact_reviewed = self._exact_reviewed_match(payload)
        if exact_reviewed is not None:
            return exact_reviewed
        # Every row is one complete price ladder.  B2C and C2B must resolve to
        # the same seven-element cell; the evidence's original business side
        # is metadata and never participates in serving lookup.
        model_id = _number(payload, "model_id", "modelId", "vehicle_model_id", "trim_id")
        model_year = _number(payload, "model_year", "modelYear", "vehicle_model_year")
        trim_key = _compact(
            _text(
                payload,
                "trim",
                "model",
                "modelName",
                "standard_vehicle",
                "standardModelName",
                "model_name",
            )
        )
        trim_alias_key = _trim_alias_key(trim_key)
        brand_key = _compact(_text(payload, "brand", "brand_name"))
        series_key = _compact(_text(payload, "series", "series_name"))
        brand_text = _text(payload, "brand", "brand_name")
        series_text = _text(payload, "series", "series_name")
        trim_text = _text(
            payload,
            "trim",
            "model",
            "modelName",
            "standard_vehicle",
            "standardModelName",
            "model_name",
        )
        trim_variants = _trim_lookup_variants(trim_text, brand_text, series_text)
        trim_variant_keys = {_compact(value) for value in trim_variants}
        subset = pd.DataFrame()
        model_indices = pd.Index([])
        text_indices = pd.Index([])
        semantic_fallback = False
        alias_fallback = False
        if self._lazy:
            subset = self._lazy_candidates(
                model_id=model_id,
                model_year=model_year,
                brand=brand_text,
                series=series_text,
                trim=trim_text,
            )
            if not subset.empty:
                model_indices = subset.index[
                    pd.to_numeric(subset["model_id_num"], errors="coerce").eq(model_id)
                ]
                text_indices = subset.index[
                    subset["brand_key"].eq(brand_key)
                    & subset["series_key"].eq(series_key)
                    & subset["trim_key"].isin(trim_variant_keys)
                    & pd.to_numeric(subset["model_year_num"], errors="coerce").eq(model_year)
                ]
                if not text_indices.empty:
                    # Exact trim/year text is the identity authority when an
                    # internal model id and a DCD synthetic id disagree.
                    subset = subset.loc[text_indices].copy()
                    model_indices = pd.Index([])
            else:
                alias_subset = self._lazy_series_year_candidates(
                    brand=brand_text,
                    series=series_text,
                    model_year=model_year,
                )
                if not alias_subset.empty and trim_alias_key:
                    alias_match = alias_subset["trim"].map(_trim_alias_key).eq(trim_alias_key)
                    subset = alias_subset.loc[alias_match].copy()
                    alias_fallback = not subset.empty
                if subset.empty and self.allow_semantic_fallback:
                    subset = alias_subset
                    semantic_fallback = not subset.empty
        else:
            if pd.notna(model_id) and model_id > 0:
                indices = self._model_indices.get(int(model_id))
                if indices is not None:
                    model_indices = indices
            if trim_variant_keys and series_key and pd.notna(model_year):
                for variant_key in trim_variant_keys:
                    indices = self._trim_indices.get(
                        (brand_key, series_key, variant_key)
                    )
                    if indices is not None:
                        text_indices = text_indices.union(indices, sort=False)
            candidate_indices = model_indices.union(text_indices, sort=False)
            if not candidate_indices.empty:
                subset = self.frame.loc[candidate_indices]
                exact_text = subset.index.intersection(text_indices, sort=False)
                if not exact_text.empty:
                    subset = subset.loc[exact_text].copy()
                    model_indices = pd.Index([])
            elif brand_key and series_key and pd.notna(model_year):
                alias_subset = self.frame.loc[
                    self.frame["brand_key"].eq(brand_key)
                    & self.frame["series_key"].eq(series_key)
                    & pd.to_numeric(self.frame["model_year_num"], errors="coerce").eq(model_year)
                ]
                if not alias_subset.empty and trim_alias_key:
                    alias_match = alias_subset["trim"].map(_trim_alias_key).eq(trim_alias_key)
                    subset = alias_subset.loc[alias_match].copy()
                    alias_fallback = not subset.empty
                if subset.empty and self.allow_semantic_fallback:
                    subset = alias_subset
                    semantic_fallback = not subset.empty
        if subset.empty:
            return None

        semantic_penalty = pd.Series(0.0, index=subset.index)
        config_adjustment = pd.Series(0.0, index=subset.index)
        if semantic_fallback:
            query_semantic = _semantic_trim(
                trim_text, brand_text, series_text, model_year
            )
            compatibility: list[bool] = []
            penalties: list[float] = []
            adjustments: list[float] = []
            for candidate in subset.itertuples(index=False):
                parsed = _semantic_trim(
                    getattr(candidate, "trim", ""),
                    getattr(candidate, "brand", ""),
                    getattr(candidate, "series", ""),
                    getattr(candidate, "model_year", model_year),
                )
                compatible, penalty, adjustment = _strict_semantic_compatibility(
                    query_semantic, parsed
                )
                compatibility.append(compatible)
                penalties.append(penalty)
                adjustments.append(adjustment)
            keep = pd.Series(compatibility, index=subset.index)
            subset = subset.loc[keep].copy()
            if subset.empty:
                return None
            semantic_penalty = pd.Series(penalties, index=keep.index).loc[keep]
            config_adjustment = pd.Series(adjustments, index=keep.index).loc[keep]

        quote_time = _timestamp(payload, "quote_time", "prediction_time", "target_date")
        if pd.isna(quote_time):
            quote_time = pd.Timestamp.now()
        registration = _timestamp(
            payload,
            "first_registration_date",
            "registration_date",
            "registration_time",
            "license_date",
            "reg_date",
            "regDate",
            "firstLicenseDate",
        )
        age = _number(payload, "age_years", "vehicle_age_years")
        if pd.isna(age) and pd.notna(registration):
            age = (quote_time.tz_localize(None) - registration.tz_localize(None)).days / 365.25
        mileage = _number(payload, "mileage_wan_km", "mileage", "mileageWanKm")
        transfer = _number(payload, "transfer_count", "transferCount", "transfers")
        score = _number(payload, "inspection_score", "condition_score")
        city = _compact(_text(payload, "city", "city_name"))
        color = _compact(_text(payload, "color", "exterior_color"))
        condition = _text(payload, "condition_grade", "inspection_grade", "condition")

        distance = pd.Series(0.0, index=subset.index)
        distance += semantic_penalty
        if pd.notna(model_year):
            distance += (
                pd.to_numeric(subset["model_year_num"], errors="coerce") - model_year
            ).abs().fillna(5.0) * 0.75
        if pd.notna(age):
            distance += (pd.to_numeric(subset["age_years"], errors="coerce") - age).abs().fillna(1.0)
        if pd.notna(mileage):
            distance += (
                pd.to_numeric(subset["mileage_wan_km"], errors="coerce") - mileage
            ).abs().fillna(2.0) / 2.0
        if pd.notna(transfer):
            distance += (
                pd.to_numeric(subset["transfer_count"], errors="coerce") - transfer
            ).abs().fillna(1.0) * 0.35
        if pd.notna(score):
            distance += (
                pd.to_numeric(subset["inspection_score"], errors="coerce") - score
            ).abs().fillna(5.0) / 15.0
        if city:
            distance += subset["city_key"].ne(city).astype(float) * 0.25
        if color:
            distance += subset["color_key"].ne(color).astype(float) * 0.08
        if condition:
            distance += subset["condition_grade_key"].ne(_compact(condition)).astype(float) * 0.20
        if self.stale_internal_distance_penalty > 0 and side.upper() == "B2C":
            origin = subset.get(
                "evidence_origin_side", pd.Series("", index=subset.index)
            ).fillna("").astype(str)
            current_dcd = origin.eq("DCD_ONLY_CURRENT_MARKET")
            distance += (~current_dcd).astype(float) * self.stale_internal_distance_penalty
        best_index = distance.idxmin()
        best_distance = float(distance.loc[best_index])
        if best_distance > self.max_distance:
            return None
        row = subset.loc[best_index]
        match_level = (
            "strict_adjacent_config"
            if semantic_fallback
            else "exact_trim_alias"
            if alias_fallback
            else "same_model_id"
            if best_index in model_indices
            else "exact_trim_text"
            if pd.isna(model_id) or model_id <= 0
            else "model_id_miss_exact_trim_text"
        )
        anchor_year = pd.to_numeric(row.get("model_year_num"), errors="coerce")
        if pd.notna(model_year) and pd.notna(anchor_year) and int(anchor_year) != int(model_year):
            match_level = f"{match_level}_any_year"

        log_adjustment = 0.0
        if semantic_fallback:
            log_adjustment += float(config_adjustment.loc[best_index])
        anchor_age = pd.to_numeric(row.get("age_years"), errors="coerce")
        anchor_mileage = pd.to_numeric(row.get("mileage_wan_km"), errors="coerce")
        anchor_transfer = pd.to_numeric(row.get("transfer_count"), errors="coerce")
        if pd.notna(age) and pd.notna(anchor_age):
            log_adjustment -= 0.035 * (age - float(anchor_age))
        if pd.notna(mileage) and pd.notna(anchor_mileage):
            log_adjustment -= 0.015 * (mileage - float(anchor_mileage))
        if pd.notna(transfer) and pd.notna(anchor_transfer):
            log_adjustment -= 0.010 * (transfer - float(anchor_transfer))
        if condition:
            log_adjustment += _condition_value(condition) - _condition_value(row.get("condition_grade"))
        market_adjustment, market_adjustment_trace = element_log_adjustment(
            brand=brand_text or row.get("brand"),
            series=series_text or row.get("series"),
            trim=trim_text or row.get("trim"),
            model_year=model_year if pd.notna(model_year) else row.get("model_year"),
            query_city=city,
            anchor_city=row.get("city"),
            query_color=color,
            anchor_color=row.get("color"),
        )
        log_adjustment += market_adjustment
        lower_bound = -0.30 if str(condition).strip().upper() in {"D", "E"} else -0.12
        local_factor = float(np.exp(np.clip(log_adjustment, lower_bound, 0.08)))
        matched_row = row.to_dict()
        matched_row["element_adjustment_trace"] = market_adjustment_trace
        return SurfaceMatch(
            row=matched_row,
            match_level=match_level if best_distance < 1e-9 else f"{match_level}_local",
            distance=best_distance,
            local_factor=local_factor,
        )

    def quote(self, payload: dict[str, Any], side: str) -> dict[str, Any] | None:
        match = self.match(payload, side)
        if match is None:
            return None
        row = match.row
        factor = match.local_factor
        matched_exact_fingerprint = exact_seven_element_fingerprint(
            {
                "model_id": row.get("model_id") or row.get("model_id_numeric"),
                "model_year": row.get("model_year") or row.get("model_year_numeric"),
                "trim": row.get("trim") or row.get("trim_normalized_display"),
                "registration_date": row.get("registration_date")
                or row.get("registration_date_normalized"),
                "mileage_wan_km": row.get("mileage_wan_km"),
                "city": row.get("city"),
                "transfer_count": row.get("transfer_count"),
                "color": row.get("color"),
                "condition_grade": row.get("condition_grade")
                or row.get("inspection_grade"),
            }
        )
        def adjusted(column: str) -> float:
            value = pd.to_numeric(row.get(column), errors="coerce")
            return round(float(value) * factor, 2) if pd.notna(value) else np.nan

        b2c = adjusted("b2c_transaction_yuan")
        listing = max(adjusted("recommended_listing_yuan"), b2c)
        listing_low = max(b2c, round(listing * 0.97, 2))
        listing_high = round(listing * 1.03, 2)
        c2b = min(adjusted("expected_c2b_yuan"), b2c)
        first_offer = min(adjusted("first_c2b_offer_yuan"), c2b)
        point = b2c if side.upper() == "B2C" else c2b
        low = adjusted("b2c_low_yuan" if side.upper() == "B2C" else "c2b_low_yuan")
        high = adjusted("b2c_high_yuan" if side.upper() == "B2C" else "c2b_high_yuan")
        c2b_high = adjusted("c2b_high_yuan")
        max_c2b = min(max(adjusted("max_c2b_yuan"), c2b, c2b_high), b2c)
        price_wan = round(point / 10_000.0, 2)
        range_wan = [round(low / 10_000.0, 2), round(high / 10_000.0, 2)]
        internal_support = pd.to_numeric(row.get("internal_knn_support"), errors="coerce")
        source_count = pd.to_numeric(row.get("source_count"), errors="coerce")
        same_year_count = pd.to_numeric(row.get("same_year_source_count"), errors="coerce")
        evidence_rows = []
        for source, column, role in (
            ("懂车帝当前挂牌", "dongchedi_listing_yuan", "EXTERNAL_B2C_LISTING"),
            ("三方挂牌共识", "third_party_listing_yuan", "EXTERNAL_B2C_LISTING_CONSENSUS"),
            ("内部严格同款可比", "internal_knn_yuan", f"INTERNAL_{side.upper()}_COMPARABLE"),
            ("原线上模型", "online_model_yuan", "MODEL_CHALLENGER"),
        ):
            value = pd.to_numeric(row.get(column), errors="coerce")
            if pd.notna(value) and float(value) > 0:
                evidence_rows.append(
                    {
                        "source": source,
                        "price_role": role,
                        "price_yuan": round(float(value), 2),
                        "used_as_direct_answer": False,
                    }
                )
        why_this_price = [
            {
                "label": "严格车型匹配",
                "display_value": f"{match.match_level}，距离 {match.distance:.3f}",
                "amount_yuan": None,
            },
            {
                "label": "多源市场共识",
                "display_value": f"{float(row.get('market_consensus_yuan')) / 10_000.0:.2f}万",
                "amount_yuan": None,
            },
            {
                "label": "连续七要素修正",
                "display_value": f"局部系数 {factor:.4f}",
                "amount_yuan": None,
            },
            {
                "label": "市场收车价复核",
                "display_value": "收车价与最高收车价均按当前市场成交口径给出",
                "amount_yuan": None,
            },
        ]
        is_manual_review = str(row.get("review_method") or "").startswith(
            "HUMAN_APPRAISER_"
        )
        manual_reason = str(
            row.get("full_appraiser_review_reason")
            or row.get("conflict_review_reason")
            or "已按同款真实交易、当前行情和本车七要素完成复核"
        )
        if is_manual_review:
            why_this_price.insert(
                1,
                {
                    "label": "人工逐车复核",
                    "display_value": manual_reason,
                    "amount_yuan": None,
                },
            )
        business_explanation = {
            "conclusion": {
                "reference_price_wan": round(point / 10_000.0, 2),
                "recommended_listing_wan": round(listing / 10_000.0, 2),
                "expected_b2c_wan": round(b2c / 10_000.0, 2),
                "expected_c2b_wan": round(c2b / 10_000.0, 2),
                "deal_decision": row.get("deal_decision"),
                "evidence_origin_side": row.get("evidence_origin_side"),
                "internal_b2c_recency_days": row.get("internal_b2c_recency_days"),
                "internal_c2b_recency_days": row.get("internal_c2b_recency_days"),
            },
            "why_this_price": why_this_price,
            "calculation_logic": {
                "baseline_formula": (
                    "同一七要素成交/合同硬证据 + 同款挂牌议价校验，由定价师逐车审核。"
                    if is_manual_review
                    else "内部严格同款可比 + DCD优先三方挂牌折扣 + 原线上模型 -> 市场共识；已确认交易只做最小日更校准。"
                ),
                "raw_transaction_returned_directly": False,
                "same_series_year_primary_anchor": False,
            },
        }
        evidence_card = {
            "version": self.version,
            "knowledge_cell_id": row.get("knowledge_cell_id"),
            "price_summary": {
                "baseline_method": self.version,
                "recommended_listing_yuan": listing,
                "b2c_transaction_yuan": b2c,
                "expected_c2b_yuan": c2b,
                "first_c2b_offer_yuan": first_offer,
                "max_c2b_yuan": max_c2b,
            },
            "evidence": evidence_rows,
            "business_explanation": business_explanation,
        }
        frontline_answer = (
            f"建议挂牌{listing / 10000:.2f}万，预计{b2c / 10000:.2f}万左右成交，"
            f"正常成交区间{adjusted('b2c_low_yuan') / 10000:.2f}-{adjusted('b2c_high_yuan') / 10000:.2f}万。"
            f"预计实际收车{c2b / 10000:.2f}万，市场最高收车价{max_c2b / 10000:.2f}万。"
            if side.upper() == "B2C"
            else f"建议先报{first_offer / 10000:.2f}万，预计{c2b / 10000:.2f}万左右收下，"
            f"市场最高收车价{max_c2b / 10000:.2f}万。预计可卖{b2c / 10000:.2f}万，"
            f"建议挂牌{listing / 10000:.2f}万。"
        )
        catalog_resolution_warning = str(
            payload.get("catalog_resolution_warning") or ""
        ).strip()
        risk_warnings: list[str] = []
        if catalog_resolution_warning:
            risk_warnings.append(catalog_resolution_warning)
        return {
            "success": True,
            "quote_id": payload.get("request_id"),
            "knowledge_cell_id": row.get("knowledge_cell_id"),
            "pricing_engine_used": "V195_REVIEWED_BUSINESS_SURFACE",
            "pricing_engine_version": self.version,
            "model_version": self.version,
            "policy_version": self.version,
            "target_price_role": f"{side.upper()}_REVIEWED_BUSINESS_PRICE",
            "final_price": point,
            "display_price_wan": price_wan,
            "b2cPrice": round(b2c / 10_000.0, 2),
            "b2c_price": round(b2c / 10_000.0, 2),
            "targetB2C": round(b2c / 10_000.0, 2),
            "b2cRange": [round(adjusted("b2c_low_yuan") / 10_000.0, 2), round(adjusted("b2c_high_yuan") / 10_000.0, 2)],
            "c2bPrice": round(c2b / 10_000.0, 2),
            "c2b_price": round(c2b / 10_000.0, 2),
            "targetC2B": round(c2b / 10_000.0, 2),
            "c2bRange": [round(adjusted("c2b_low_yuan") / 10_000.0, 2), round(adjusted("c2b_high_yuan") / 10_000.0, 2)],
            "recommended_listing_price_yuan": listing,
            "recommended_listing_range_yuan": [listing_low, listing_high],
            "first_c2b_offer_yuan": first_offer,
            "max_c2b_price_yuan": max_c2b,
            "price_ladder": {
                "recommended_listing_yuan": listing,
                "recommended_listing_range_yuan": [listing_low, listing_high],
                "expected_b2c_transaction_yuan": b2c,
                "b2c_transaction_range_yuan": [
                    adjusted("b2c_low_yuan"),
                    adjusted("b2c_high_yuan"),
                ],
                "expected_c2b_yuan": c2b,
                "c2b_range_yuan": [
                    adjusted("c2b_low_yuan"),
                    adjusted("c2b_high_yuan"),
                ],
                "first_c2b_offer_yuan": first_offer,
                "max_c2b_yuan": max_c2b,
            },
            "deal_decision": row.get("deal_decision"),
            "price_result": {
                "final_price": point,
                "price_low": low,
                "price_high": high,
                "confidence": "HIGH",
                "reasonableness_level": "MULTI_SOURCE_REVIEWED",
                "display_type": "REVIEWED_BUSINESS_PRICE",
            },
            "interval": {"low": low, "high": high, "type": f"{side.upper()}_REVIEWED_INTERVAL"},
            "confidence": "HIGH",
            "confidence_reasons": [
                "STRICT_MODEL_OR_EXACT_TRIM_MATCH",
                "MULTI_SOURCE_MARKET_CONSENSUS",
                "MINIMUM_CONFIRMED_TRANSACTION_CALIBRATION",
            ],
            "quote_decision": "AUTO_SINGLE_POINT",
            "catalog_resolution_warning": catalog_resolution_warning or None,
            "frontline_answer": frontline_answer,
            "selected_comparables": evidence_rows,
            "external_market_evidence": [
                item for item in evidence_rows if item["price_role"].startswith("EXTERNAL_")
            ],
            "price_trace": {
                "knowledge_cell_id": row.get("knowledge_cell_id"),
                "matched_model_id": row.get("model_id") or row.get("model_id_numeric"),
                "matched_model_year": row.get("model_year") or row.get("model_year_numeric"),
                "matched_trim": row.get("trim") or row.get("trim_normalized_display"),
                "statistical_baseline_price": point,
                "baseline_method": self.version,
                "source_policy": self.version,
                "evidence_origin_side": row.get("evidence_origin_side"),
                "internal_b2c_recency_days": row.get("internal_b2c_recency_days"),
                "internal_c2b_recency_days": row.get("internal_c2b_recency_days"),
                "match_level": match.match_level,
                "match_distance": match.distance,
                "exact_seven_element_fingerprint": matched_exact_fingerprint,
                "local_adjustment_factor": factor,
                "element_adjustment_trace": row.get("element_adjustment_trace") or {},
                "market_consensus_yuan": row.get("market_consensus_yuan"),
                "online_model_yuan": row.get("online_model_yuan"),
                "third_party_listing_yuan": row.get("third_party_listing_yuan"),
                "dongchedi_listing_yuan": row.get("dongchedi_listing_yuan"),
                "internal_knn_yuan": row.get("internal_knn_yuan"),
                "internal_knn_support": row.get("internal_knn_support"),
                "calibration_weight": row.get("calibration_weight"),
                "recommended_listing_yuan": listing,
                "b2c_transaction_yuan": b2c,
                "expected_c2b_yuan": c2b,
                "first_c2b_offer_yuan": first_offer,
                "max_c2b_yuan": max_c2b,
                "deal_decision": row.get("deal_decision"),
                "review_method": row.get("review_method"),
                "manual_review_reason": manual_reason,
            },
            "evidence_summary": {
                "internal_knn_support": int(internal_support) if pd.notna(internal_support) else 0,
                "third_party_source_count": int(source_count) if pd.notna(source_count) else 0,
                "same_year_source_count": int(same_year_count) if pd.notna(same_year_count) else 0,
                "raw_transaction_target_returned_directly": False,
            },
            "risk_warnings": risk_warnings,
            "evidence_card": evidence_card,
            "business_explanation": business_explanation,
            "normalized_query": payload,
            "reason": (
                "已结合这款车的真实交易、当前行情，以及上牌时间、公里数、过户、车况、城市和颜色逐项复核。"
                if is_manual_review
                else "已结合严格同款交易、当前行情和本车七要素给出价格。"
            ),
        }


_CACHE: dict[tuple[Any, ...], tuple[float, ReviewedBusinessPriceSurface]] = {}


def get_reviewed_business_surface(
    path: Path,
    *,
    max_distance: float = 1.20,
    stale_internal_distance_penalty: float = 0.0,
    allow_semantic_fallback: bool = False,
) -> ReviewedBusinessPriceSurface:
    modified = path.stat().st_mtime if path.exists() else -1.0
    key = (
        str(path),
        float(max_distance),
        float(stale_internal_distance_penalty),
        bool(allow_semantic_fallback),
    )
    cached = _CACHE.get(key)
    if cached is None or cached[0] != modified:
        _CACHE[key] = (
            modified,
            ReviewedBusinessPriceSurface(
                path,
                max_distance=max_distance,
                stale_internal_distance_penalty=stale_internal_distance_penalty,
                allow_semantic_fallback=allow_semantic_fallback,
            ),
        )
    return _CACHE[key][1]
