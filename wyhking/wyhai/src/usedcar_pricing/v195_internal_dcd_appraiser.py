"""Strict same-trim appraiser anchors for the complete production catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import json
import os
from pathlib import Path
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd

from services.vehicle_identity_semantics import code_compatibility
from .v195_element_adjustments import element_log_adjustment
from .v195_price_ladder_solver import business_cost_inputs, load_ladder_config


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _compact(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).lower()
    return re.sub(r"[\s,，。._/()（）·・\-]+", "", text)


_BRAND_KEY_ALIASES = {
    "aito": "问界",
    "问界汽车": "问界",
    "深蓝汽车": "深蓝",
    "哪吒汽车": "哪吒",
    "创维汽车": "创维",
    "睿蓝汽车": "睿蓝",
    "威马汽车": "威马",
    "吉利几何": "几何",
}

_SERIES_KEY_ALIASES = {
    # Common frontline/marketing names versus the canonical catalog family.
    "k5凯酷": "k5",
    "d9dmi": "d9dm",
}


def _brand_key(value: Any) -> str:
    key = _compact(value)
    key = _BRAND_KEY_ALIASES.get(key, key)
    for suffix in ("汽车集团", "汽车", "集团"):
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
            break
    return _BRAND_KEY_ALIASES.get(key, key)


def _brand_equivalent(left: Any, right: Any) -> bool:
    return bool(_brand_key(left) and _brand_key(left) == _brand_key(right))


def _series_key(value: Any, brand: Any = "") -> str:
    key = _compact(value)
    brand_variants = {
        _compact(brand),
        _brand_key(brand),
        f"{_brand_key(brand)}汽车" if _brand_key(brand) else "",
    }
    for prefix in sorted((item for item in brand_variants if item), key=len, reverse=True):
        if key.startswith(prefix) and len(key) > len(prefix):
            key = key[len(prefix) :]
            break
    return _SERIES_KEY_ALIASES.get(key, key)


def _series_equivalent(
    left: Any,
    right: Any,
    *,
    left_brand: Any = "",
    right_brand: Any = "",
) -> bool:
    left_key = _series_key(left, left_brand)
    right_key = _series_key(right, right_brand)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    # Brand-prefixed series such as 深蓝S07 / S07 and 奔驰C级 / C级 are
    # equivalent.  Require at least two characters so a bare one-letter hint
    # cannot silently select a different catalog family.
    return min(len(left_key), len(right_key)) >= 2 and (
        left_key.endswith(right_key) or right_key.endswith(left_key)
    )


def _trim_similarity(left: Any, right: Any) -> float:
    left_key = _compact(left)
    right_key = _compact(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    containment = min(len(left_key), len(right_key)) / max(
        len(left_key), len(right_key)
    ) if left_key in right_key or right_key in left_key else 0.0
    return max(
        containment,
        difflib.SequenceMatcher(None, left_key, right_key).ratio(),
    )


def _catalog_trim_similarity(query: Any, row: dict[str, Any]) -> float:
    """Compare a frontline trim name with one canonical catalog identity."""

    query_key = _compact(query)
    series_key = _compact(row.get("series"))
    if "hi4t" in series_key and "插混" in query_key:
        query_key = query_key.replace("插混版", "hi4t").replace("插混", "hi4t")
    if "hti" in series_key and "115km" in query_key and "尊贵" in query_key:
        query_key = query_key.replace("115km", "").replace("尊贵", "尊耀")
    return _trim_similarity(query_key, row.get("trim"))


def _catalog_code_compatibility(query: Any, row: dict[str, Any]) -> bool | None:
    compatibility = code_compatibility(query, row.get("trim"))
    if compatibility is not False:
        return compatibility
    # Public catalog pages use 2023 "115KM 尊贵" colloquially for the
    # adjacent 115KM 尊耀 configuration.  The internal catalog row omits the
    # range token, so preserve this one reviewed alias explicitly.
    query_key = _compact(query)
    series_key = _compact(row.get("series"))
    candidate_key = _compact(row.get("trim"))
    if (
        "hti" in series_key
        and "115km" in query_key
        and "尊贵" in query_key
        and "尊耀" in candidate_key
    ):
        return True
    return False


def _unique_ranked_identity(
    rows: list[dict[str, Any]],
    trim: str,
    *,
    target_year: int,
) -> str | None:
    """Select one code-compatible identity, deduplicating catalog aliases."""

    by_model: dict[str, tuple[int, float, dict[str, Any]]] = {}
    query_facelift = "改款" in _compact(trim)
    for row in rows:
        compatibility = _catalog_code_compatibility(trim, row)
        if compatibility is False:
            continue
        candidate_facelift = "改款" in _compact(row.get("trim"))
        year = int(_number(row.get("model_year")) or target_year)
        score = _catalog_trim_similarity(trim, row)
        if query_facelift != candidate_facelift:
            score -= 0.12
        score -= abs(year - target_year) * 0.04
        model_id = _number(row.get("canonical_model_id"))
        alias_key = (
            f"model:{int(model_id)}"
            if model_id is not None
            else f"identity:{row.get('identity_key')}"
        )
        candidate = (1 if compatibility is True else 0, score, row)
        existing = by_model.get(alias_key)
        if existing is None or candidate[:2] > existing[:2]:
            by_model[alias_key] = candidate
    scored = sorted(by_model.values(), key=lambda item: item[:2], reverse=True)
    if not scored:
        return None
    best_code, best_score, best_row = scored[0]
    runner_up = (
        scored[1][1]
        if len(scored) > 1 and scored[1][0] == best_code
        else 0.0
    )
    min_score = 0.45 if best_code else 0.72
    required_margin = 0.05 if best_code else 0.08
    if best_score >= min_score and best_score - runner_up >= required_margin:
        return str(best_row["identity_key"])
    return None


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed) or not np.isfinite(float(parsed)):
        return None
    return float(parsed)


def _condition_factor(value: Any) -> float:
    return {
        "A": 1.00,
        "B": 0.97,
        "C": 0.91,
        "D": 0.83,
        "E": 0.74,
        "CLEAN": 1.00,
        "MINOR_DEFECT": 0.96,
        "MAJOR_DEFECT": 0.86,
        "UNKNOWN": 0.98,
    }.get(_text(value).upper() or "UNKNOWN", 0.98)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    usable = np.isfinite(values) & np.isfinite(weights) & (values > 0) & (weights > 0)
    if not usable.any():
        return None
    values = values[usable]
    weights = weights[usable]
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    index = int(np.searchsorted(np.cumsum(weights), weights.sum() / 2.0, side="left"))
    return float(values[min(index, len(values) - 1)])


@dataclass(frozen=True)
class AppraiserAnchor:
    identity_key: str
    b2c_yuan: float | None
    c2b_yuan: float | None
    b2c_support: int
    c2b_support: int
    b2c_recency_days: float | None
    c2b_recency_days: float | None
    route: str
    identity: dict[str, Any] = field(default_factory=dict)
    b2c_evidence: dict[str, Any] = field(default_factory=dict)
    c2b_evidence: dict[str, Any] = field(default_factory=dict)
    derivation: dict[str, Any] = field(default_factory=dict)


class InternalDcdCatalogAppraiser:
    """Price a payload only from its exact catalog trim/model-year evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        catalog_path = root / "data/v195/internal_dcd_vehicle_catalog.parquet"
        evidence_path = root / "data/v195/internal_dcd_appraiser_vehicle_evidence.parquet"
        self.catalog = pd.read_parquet(catalog_path)
        self.evidence = pd.read_parquet(evidence_path)
        panel_path = (
            root / "data/v195/full_catalog_appraiser_identity_panels_v195404.parquet"
        )
        use_reviewed_panels = str(
            os.environ.get("V195_USE_FULL_CATALOG_APPRAISER_PANEL", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.reviewed_panels = (
            pd.read_parquet(panel_path)
            if use_reviewed_panels and panel_path.exists()
            else pd.DataFrame()
        )
        manual_panel_path = Path(
            os.environ.get(
                "V195_MANUAL_IDENTITY_PANEL_PATH",
                str(root / "data/manual_price_book/manual_identity_price_panels_v195405.parquet"),
            )
        )
        use_manual_panels = str(
            os.environ.get("V195_USE_MANUAL_IDENTITY_PANELS", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
        manual_panels = (
            pd.read_parquet(manual_panel_path)
            if use_manual_panels and manual_panel_path.exists()
            else pd.DataFrame()
        )
        self._reviewed_panel_rows = (
            {
                str(row["identity_key"]): row
                for row in self.reviewed_panels.to_dict("records")
            }
            if not self.reviewed_panels.empty
            else {}
        )
        if not manual_panels.empty:
            self._reviewed_panel_rows.update(
                {
                    str(row["identity_key"]): row
                    for row in manual_panels.to_dict("records")
                }
            )
        self._manual_identity_lookup = {
            "|".join(
                [
                    _compact(row.get("brand")),
                    _compact(row.get("series")),
                    _compact(row.get("trim")),
                    str(int(_number(row.get("model_year")) or 0)),
                ]
            ): str(row["identity_key"])
            for row in manual_panels.to_dict("records")
        }
        self.ladder_config = load_ladder_config(root / "config/v195_price_ladder.json")
        self.ladder_config = json.loads(json.dumps(self.ladder_config))
        self.ladder_config["refurbishment_cost_by_condition"].update(
            {"D": 9_000.0, "E": 13_000.0}
        )
        self._excluded_counts: dict[str, int] = {}
        exclusion_path = root / "data/v195/appraiser_live_anchor_exclusions.parquet"
        if exclusion_path.exists():
            exclusions = pd.read_parquet(
                exclusion_path, columns=["identity_key", "vehicle_key"]
            ).drop_duplicates()
            exclusion_keys = set(
                zip(
                    exclusions["identity_key"].astype(str),
                    exclusions["vehicle_key"].astype(str),
                )
            )
            rejected = pd.Series(
                [
                    (str(identity), str(vehicle)) in exclusion_keys
                    for identity, vehicle in zip(
                        self.evidence["identity_key"], self.evidence["vehicle_key"]
                    )
                ],
                index=self.evidence.index,
            )
            self._excluded_counts = (
                self.evidence.loc[rejected, "identity_key"]
                .astype(str)
                .value_counts()
                .astype(int)
                .to_dict()
            )
            self.evidence = self.evidence.loc[~rejected].copy()
        self.catalog["model_year"] = pd.to_numeric(self.catalog["model_year"], errors="coerce")
        self.catalog["canonical_model_id"] = pd.to_numeric(
            self.catalog["canonical_model_id"], errors="coerce"
        )
        self._identity_keys = set(self.catalog["identity_key"].astype(str))
        self._model_year_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self._series_year_rows: dict[int, list[dict[str, Any]]] = {}
        for row in self.catalog.to_dict("records"):
            year = _number(row.get("model_year"))
            aliases = row.get("model_id_aliases") or "[]"
            try:
                model_ids = [int(value) for value in json.loads(str(aliases))]
            except (TypeError, ValueError, json.JSONDecodeError):
                model_ids = []
            canonical = _number(row.get("canonical_model_id"))
            if canonical is not None:
                model_ids.append(int(canonical))
            if year is None:
                continue
            self._series_year_rows.setdefault(int(year), []).append(row)
            for model_id in set(model_ids):
                self._model_year_rows.setdefault((model_id, int(year)), []).append(row)
        self._evidence_indices = {
            str(key): group.index.to_numpy()
            for key, group in self.evidence.groupby("identity_key", sort=False)
        }
        manifest_path = root / "models/v195_390/v195_390_unified_single_answer_price_book.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            manifest = {}
        self.spreads = {str(key): float(value) for key, value in (manifest.get("spread_by_price_band") or {}).items()}
        self.default_spread = float(manifest.get("default_spread") or 0.093)

    @staticmethod
    def _price_band(price: float) -> str:
        return str(int(np.digitize([price], [30_000, 50_000, 80_000, 120_000, 200_000, 300_000])[0]))

    def _spread(self, b2c: float) -> float:
        return float(np.clip(self.spreads.get(self._price_band(b2c), self.default_spread), 0.05, 0.22))

    def _quote_reviewed_panel(
        self,
        identity_key: str,
        payload: dict[str, Any],
        cutoff_time: pd.Timestamp,
    ) -> AppraiserAnchor | None:
        """Apply a dated appraiser card with only the reviewed element rules."""

        row = self._reviewed_panel_rows.get(identity_key)
        if row is None:
            return None
        eligible_b2c = row.get("quote_eligible_b2c")
        if eligible_b2c is None:
            eligible_b2c = _number(row.get("reviewed_b2c_yuan")) is not None
        if not bool(eligible_b2c):
            return None
        effective = pd.to_datetime(row.get("effective_from"), errors="coerce")
        data_cutoff = pd.to_datetime(row.get("data_cutoff"), errors="coerce")
        if pd.notna(effective) and effective.tzinfo is not None:
            effective = effective.tz_convert("Asia/Shanghai").tz_localize(None)
        if pd.notna(data_cutoff) and data_cutoff.tzinfo is not None:
            data_cutoff = data_cutoff.tz_convert("Asia/Shanghai").tz_localize(None)
        if pd.notna(effective) and cutoff_time < effective:
            return None
        if pd.notna(data_cutoff) and cutoff_time < data_cutoff:
            return None

        registration, mileage, transfer, city, condition = self._target_features(payload)
        reference_registration = pd.to_datetime(
            row.get("reference_registration_date"), errors="coerce"
        )
        reference_mileage = _number(row.get("reference_mileage_wan_km"))
        reference_transfer = _number(row.get("reference_transfer_count"))
        reference_condition = _text(
            row.get("reference_condition_grade") or "UNKNOWN"
        ).upper()
        registration_year_delta = 0.0
        if pd.notna(registration) and pd.notna(reference_registration):
            registration_year_delta = (
                (registration.year - reference_registration.year) * 12
                + registration.month
                - reference_registration.month
            ) / 12.0
        mileage_delta = (
            float(mileage) - float(reference_mileage)
            if mileage is not None and reference_mileage is not None
            else 0.0
        )
        transfer_delta = (
            float(transfer) - float(reference_transfer)
            if reference_transfer is not None
            else 0.0
        )
        market_adjustment, market_trace = element_log_adjustment(
            brand=row.get("brand"),
            series=row.get("series"),
            trim=row.get("trim"),
            model_year=row.get("model_year"),
            query_city=city,
            anchor_city=row.get("reference_city"),
            query_color=payload.get("color") or payload.get("exterior_color"),
            anchor_color=row.get("reference_color"),
        )
        log_adjustment = (
            0.035 * registration_year_delta
            - 0.015 * mileage_delta
            - 0.010 * transfer_delta
            + np.log(_condition_factor(condition))
            - np.log(_condition_factor(reference_condition))
            + market_adjustment
        )
        lower_bound = -0.30 if condition in {"D", "E", "MAJOR_DEFECT"} else -0.12
        factor = float(np.exp(np.clip(log_adjustment, lower_bound, 0.08)))
        base_b2c = _number(row.get("reviewed_b2c_yuan"))
        if base_b2c is None:
            return None
        b2c = max(base_b2c * factor, 3_500.0)

        base_c2b = _number(row.get("reviewed_c2b_yuan"))
        confidence = (
            "HIGH"
            if int(_number(row.get("b2c_support")) or 0) >= 3
            else "MEDIUM"
            if _number(row.get("listing_anchor_yuan")) is not None
            else "LOW"
        )
        costs = business_cost_inputs(
            b2c,
            condition_grade=condition,
            confidence=confidence,
            config=self.ladder_config,
        )
        profitable_ceiling = b2c - costs.total
        base_max_c2b_market = _number(row.get("max_c2b_market_yuan"))
        max_c2b_market = (
            max(base_max_c2b_market * factor, (base_c2b or 0.0) * factor)
            if base_max_c2b_market is not None
            else (base_c2b * factor * 1.025 if base_c2b is not None else None)
        )
        pricing_only_panel = (
            _text(row.get("version")) == "v195.408"
            or _text(row.get("deal_decision")).startswith("PRICING_QUOTE")
        )
        c2b = None
        profitability_clamp_used = False
        if base_c2b is not None and pricing_only_panel:
            requested_c2b = base_c2b * factor
            c2b = min(requested_c2b, b2c * 0.985)
            if c2b <= 0:
                c2b = None
        elif base_c2b is not None and profitable_ceiling > 1_000:
            requested_c2b = base_c2b * factor
            c2b = min(requested_c2b, profitable_ceiling * 0.985)
            profitability_clamp_used = c2b < requested_c2b - 1e-6
            if c2b <= 0:
                c2b = None

        b2c_support = int(_number(row.get("b2c_support")) or 0)
        c2b_support = int(_number(row.get("c2b_support")) or 0)
        b2c_recency = _number(row.get("b2c_recency_days"))
        c2b_recency = _number(row.get("c2b_recency_days"))
        panel_version = _text(row.get("version"))
        if pricing_only_panel and panel_version:
            panel_route = (
                "MANUAL_IDENTITY_APPRAISER_PANEL_"
                + panel_version.replace(".", "").upper()
            )
        elif panel_version == "v195.405":
            panel_route = "MANUAL_IDENTITY_APPRAISER_PANEL_V195405"
        else:
            panel_route = "FULL_CATALOG_HUMAN_APPRAISER_PANEL_V195404"
        return AppraiserAnchor(
            identity_key=identity_key,
            b2c_yuan=float(b2c),
            c2b_yuan=float(c2b) if c2b is not None else None,
            b2c_support=b2c_support,
            c2b_support=c2b_support,
            b2c_recency_days=b2c_recency,
            c2b_recency_days=c2b_recency,
            route=panel_route,
            identity={
                "identity_key": identity_key,
                "brand": _text(row.get("brand")),
                "series": _text(row.get("series")),
                "trim": _text(row.get("trim")),
                "model_year": int(_number(row.get("model_year")) or 0),
                "canonical_model_id": int(
                    _number(row.get("canonical_model_id"))
                    or _number(row.get("model_id"))
                    or 0
                ),
                "panel_version": panel_version,
            },
            b2c_evidence={
                "status": "REVIEWED_STRICT_IDENTITY_BASE_CARD",
                "support": b2c_support,
                "nearest_recency_days": b2c_recency,
                "direct_anchor_yuan": _number(row.get("direct_b2c_anchor_yuan")),
                "listing_anchor_yuan": _number(row.get("listing_anchor_yuan")),
                "appraisal_method": _text(row.get("b2c_appraisal_method")),
            },
            c2b_evidence={
                "status": "REVIEWED_STRICT_IDENTITY_ACQUISITION_CARD",
                "support": c2b_support,
                "nearest_recency_days": c2b_recency,
                "direct_anchor_yuan": _number(row.get("direct_c2b_anchor_yuan")),
                "appraisal_method": _text(row.get("c2b_appraisal_method")),
            },
            derivation={
                "panel_base_b2c_yuan": base_b2c,
                "panel_base_c2b_yuan": base_c2b,
                "registration_year_delta": registration_year_delta,
                "mileage_wan_delta": mileage_delta,
                "transfer_delta": transfer_delta,
                "condition_from": reference_condition,
                "condition_to": condition,
                "city_color_adjustment": market_trace,
                "seven_element_factor": factor,
                "profitable_c2b_ceiling_yuan": profitable_ceiling,
                "profitability_clamp_used": profitability_clamp_used,
                "selection_profit_gap_yuan": profitable_ceiling - c2b
                if c2b is not None
                else None,
                "max_c2b_market_yuan": max_c2b_market,
                "pricing_is_independent_from_selection": pricing_only_panel,
                "deal_decision": _text(row.get("deal_decision")),
                "review_reason": _text(row.get("review_reason")),
                "data_cutoff": _text(row.get("data_cutoff")),
                "same_series_year_primary_anchor": False,
                "official_guide_price_used": False,
            },
        )

    def _payload_identity_key(self, payload: dict[str, Any]) -> str | None:
        brand = _text(payload.get("brand") or payload.get("brand_name"))
        series = _text(payload.get("series") or payload.get("series_name"))
        trim = _text(
            payload.get("trim")
            or payload.get("model")
            or payload.get("model_name")
            or payload.get("standard_vehicle")
        )
        year = _number(payload.get("model_year") or payload.get("modelYear"))
        if not brand or not series or not trim or year is None:
            return None
        direct = f"{_compact(brand)}|{_compact(series)}|{_compact(trim)}|{int(year)}"
        manual_identity = self._manual_identity_lookup.get(direct)
        if manual_identity:
            return manual_identity
        if direct in self._identity_keys:
            return direct
        trim_without_header = _compact(trim)
        for prefix in (
            f"{int(year)}款",
            f"{int(year)}",
            _compact(brand),
            _compact(series),
            _compact(f"{brand}{series}"),
        ):
            trim_without_header = trim_without_header.replace(prefix, "", 1)
        stripped = f"{_compact(brand)}|{_compact(series)}|{trim_without_header}|{int(year)}"
        if stripped in self._identity_keys:
            return stripped

        model_id = _number(
            payload.get("model_id")
            or payload.get("modelId")
            or payload.get("vehicle_model_id")
        )
        candidates = (
            self._model_year_rows.get((int(model_id), int(year)), [])
            if model_id is not None
            else []
        )
        compatible = [
            row
            for row in candidates
            if _brand_equivalent(row.get("brand"), brand)
            and _series_equivalent(
                row.get("series"),
                series,
                left_brand=row.get("brand"),
                right_brand=brand,
            )
            and _catalog_code_compatibility(trim, row) is not False
        ]
        exact = [row for row in compatible if _compact(row.get("trim")) == _compact(trim)]
        selected = exact or compatible
        if len(selected) == 1:
            return str(selected[0]["identity_key"])

        # Some complete-catalog inputs arrive without a stable model id.  Use
        # the same brand/series/model-year pool, but only accept a unique trim
        # winner.  Explicit codes remain a hard guard (215 never becomes 285).
        series_year = [
            row
            for row in self._series_year_rows.get(int(year), [])
            if _brand_equivalent(row.get("brand"), brand)
            and _series_equivalent(
                row.get("series"),
                series,
                left_brand=row.get("brand"),
                right_brand=brand,
            )
            and _catalog_code_compatibility(trim, row) is not False
        ]
        exact = [
            row for row in series_year if _compact(row.get("trim")) == _compact(trim)
        ]
        if len(exact) == 1:
            return str(exact[0]["identity_key"])
        selected_identity = _unique_ranked_identity(
            series_year,
            trim,
            target_year=int(year),
        )
        if selected_identity:
            return selected_identity

        # Frontline names frequently retain the launch-year trim while the
        # catalog stores it under the adjacent model year.  Search at most two
        # years away, keep explicit power/range codes as a hard guard, and
        # require one unique winner after canonical-model alias deduplication.
        # This resolves, for example, 270T/945/1160/605 naming drift without
        # ever crossing 215 to 285 or another materially different trim.
        adjacent: list[dict[str, Any]] = []
        for gap in (1, 2):
            for adjacent_year in (int(year) - gap, int(year) + gap):
                adjacent.extend(
                    row
                    for row in self._series_year_rows.get(adjacent_year, [])
                    if _brand_equivalent(row.get("brand"), brand)
                    and _series_equivalent(
                        row.get("series"),
                        series,
                        left_brand=row.get("brand"),
                        right_brand=brand,
                    )
                    and _catalog_code_compatibility(trim, row) is not False
                )
            selected_identity = _unique_ranked_identity(
                adjacent,
                trim,
                target_year=int(year),
            )
            if selected_identity:
                return selected_identity
        return None

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve a safe canonical identity without requiring price evidence."""

        identity_key = self._payload_identity_key(payload)
        if not identity_key:
            return None
        rows = self.catalog.loc[
            self.catalog["identity_key"].astype(str).eq(identity_key)
        ]
        if rows.empty:
            return None
        row = rows.iloc[-1]
        return {
            "identity_key": identity_key,
            "brand": _text(row.get("brand")),
            "series": _text(row.get("series")),
            "trim": _text(row.get("trim")),
            "model_year": int(_number(row.get("model_year")) or 0),
            "model_id": int(_number(row.get("canonical_model_id")) or 0),
        }

    @staticmethod
    def _target_features(payload: dict[str, Any]) -> tuple[pd.Timestamp, float | None, float, str, str]:
        registration = pd.to_datetime(
            payload.get("registration_date")
            or payload.get("first_registration_date")
            or payload.get("regDate"),
            errors="coerce",
        )
        mileage = _number(payload.get("mileage_wan_km") or payload.get("mileage"))
        if mileage is None:
            mileage_km = _number(payload.get("mileage_km"))
            mileage = mileage_km / 10_000.0 if mileage_km is not None else None
        transfer = _number(payload.get("transfer_count") or payload.get("transfer")) or 0.0
        city = _compact(payload.get("city") or payload.get("city_name"))
        condition = _text(
            payload.get("condition_grade")
            or payload.get("inspection_grade")
            or payload.get("condition")
            or "A"
        ).upper()
        return registration, mileage, transfer, city, condition

    def _side_anchor(
        self,
        rows: pd.DataFrame,
        *,
        side: str,
        cutoff: pd.Timestamp,
        registration: pd.Timestamp,
        mileage: float | None,
        transfer: float,
        city: str,
        condition: str,
    ) -> tuple[float | None, int, float | None, dict[str, Any]]:
        price_column = "b2c_sold_price_yuan" if side == "B2C" else "c2b_purchase_price_yuan"
        event_column = "b2c_event_time" if side == "B2C" else "c2b_event_time"
        price = pd.to_numeric(rows[price_column], errors="coerce")
        usable = rows.loc[price.between(3_000, 5_000_000)].copy()
        if usable.empty:
            return None, 0, None, {"status": "NO_LEGAL_DIRECT_EVIDENCE"}
        usable["_price"] = pd.to_numeric(usable[price_column], errors="coerce")
        candidate_registration = pd.to_datetime(usable["first_registration_date"], errors="coerce")
        candidate_mileage = pd.to_numeric(usable["mileage_wan_km"], errors="coerce")
        candidate_transfer = pd.to_numeric(usable["transfer_count"], errors="coerce").fillna(0.0)
        event_time = pd.to_datetime(usable[event_column], errors="coerce")
        available_time = pd.to_datetime(
            usable.get("pricing_available_at", usable[event_column]), errors="coerce"
        )
        # Undated history never competes with dated evidence.  It is retained
        # only as a last-resort legacy clue for catalog cars that would
        # otherwise be unquotable, with maximum time decay and zero live
        # support reported to the confidence gate.
        available_asof = available_time.notna() & available_time.lt(
            cutoff.tz_localize(None)
        )
        dated_asof = (
            event_time.notna()
            & event_time.lt(cutoff.tz_localize(None))
            & available_asof
        )
        legacy_undated = not bool(dated_asof.any())
        legacy_snapshot_evidence = (
            available_time.isna()
            & usable["source"].astype(str).eq("INTERNAL_FULL_HISTORY")
        )
        asof_mask = (
            event_time.isna() & (available_asof | legacy_snapshot_evidence)
            if legacy_undated
            else dated_asof
        )
        usable = usable.loc[asof_mask].copy()
        event_time = event_time.loc[asof_mask]
        if usable.empty:
            return None, 0, None, {"status": "NO_ASOF_DIRECT_EVIDENCE"}
        before_event_dedup = len(usable)
        event_dedup_columns = [
            price_column,
            event_column,
            "first_registration_date",
            "mileage_wan_km",
            "city",
            "transfer_count",
            "inspection_grade",
        ]
        usable = usable.drop_duplicates(event_dedup_columns, keep="last")
        event_time = event_time.loc[usable.index]
        duplicate_evidence_rows_removed = before_event_dedup - len(usable)
        recency_days = (
            pd.Series(9_999.0, index=event_time.index)
            if legacy_undated
            else (cutoff.tz_localize(None) - event_time).dt.days.clip(lower=0)
        )

        distance = pd.Series(0.0, index=usable.index)
        if pd.notna(registration):
            month_delta = (
                (registration.year - candidate_registration.dt.year) * 12
                + registration.month
                - candidate_registration.dt.month
            )
            distance += month_delta.abs().fillna(12.0) / 12.0
        else:
            month_delta = pd.Series(0.0, index=usable.index)
        if mileage is not None:
            mileage_delta = mileage - candidate_mileage
            distance += mileage_delta.abs().fillna(3.0) / 2.0
        else:
            mileage_delta = pd.Series(0.0, index=usable.index)
        transfer_delta = transfer - candidate_transfer
        distance += transfer_delta.abs() * 0.35
        if city:
            distance += usable["city"].fillna("").astype(str).map(_compact).ne(city).astype(float) * 0.25
        candidate_condition = usable["inspection_grade"].fillna("UNKNOWN").astype(str)
        distance += candidate_condition.str.upper().ne(condition).astype(float) * 0.20
        nearest = distance.nsmallest(min(20, len(distance))).index
        usable = usable.loc[nearest]
        distance = distance.loc[nearest]
        month_delta = month_delta.loc[nearest].fillna(0.0)
        mileage_delta = mileage_delta.loc[nearest].fillna(0.0)
        transfer_delta = transfer_delta.loc[nearest].fillna(0.0)
        recency_days = recency_days.loc[nearest].fillna(9_999.0)
        candidate_condition = candidate_condition.loc[nearest]

        local_factor = (
            np.power(1.005, month_delta.clip(lower=0))
            * np.power(0.994, (-month_delta).clip(lower=0))
            * np.exp(-0.030 * mileage_delta.clip(lower=0))
            * np.exp(0.015 * (-mileage_delta).clip(lower=0))
            * np.power(0.985, transfer_delta.clip(lower=0))
            * np.power(1.006, (-transfer_delta).clip(lower=0))
            * (
                _condition_factor(condition)
                / candidate_condition.map(_condition_factor).astype(float)
            )
        ).clip(0.68, 1.28)
        annual_decay = 0.20 if side == "B2C" else 0.16
        time_factor = np.exp(-annual_decay * recency_days / 365.25).clip(0.55, 1.0)
        adjusted = usable["_price"].to_numpy(dtype=float) * local_factor.to_numpy(dtype=float) * time_factor.to_numpy(dtype=float)
        weights = np.exp(-distance.to_numpy(dtype=float)) * np.maximum(
            np.exp(-recency_days.to_numpy(dtype=float) / 180.0), 0.05
        )
        anchor = _weighted_median(adjusted, weights)
        raw_anchor = _weighted_median(usable["_price"].to_numpy(dtype=float), weights)
        recency = (
            None
            if legacy_undated
            else float(recency_days.min())
            if len(recency_days)
            else None
        )
        audit = usable[
            [
                "first_registration_date",
                "mileage_wan_km",
                "city",
                "transfer_count",
                "inspection_grade",
                price_column,
                event_column,
                "pricing_available_at",
                "source",
            ]
        ].copy()
        audit["distance"] = distance
        audit["local_factor"] = local_factor
        audit["time_factor"] = time_factor
        audit["adjusted_price_yuan"] = adjusted
        audit["weight"] = weights
        audit = audit.sort_values("weight", ascending=False, kind="stable").head(8)
        top_comparables: list[dict[str, Any]] = []
        for item in audit.to_dict("records"):
            top_comparables.append(
                {
                    "price_yuan": round(float(item[price_column]), 2),
                    "adjusted_price_yuan": round(float(item["adjusted_price_yuan"]), 2),
                    "event_time": (
                        pd.Timestamp(item[event_column]).isoformat()
                        if pd.notna(item[event_column])
                        else None
                    ),
                    "pricing_available_at": (
                        pd.Timestamp(item["pricing_available_at"]).isoformat()
                        if pd.notna(item["pricing_available_at"])
                        else None
                    ),
                    "registration_date": (
                        pd.Timestamp(item["first_registration_date"]).date().isoformat()
                        if pd.notna(item["first_registration_date"])
                        else None
                    ),
                    "mileage_wan_km": _number(item["mileage_wan_km"]),
                    "city": _text(item["city"]),
                    "transfer_count": _number(item["transfer_count"]),
                    "condition_grade": _text(item["inspection_grade"]) or "UNKNOWN",
                    "local_factor": round(float(item["local_factor"]), 6),
                    "time_factor": round(float(item["time_factor"]), 6),
                    "distance": round(float(item["distance"]), 6),
                    "weight": round(float(item["weight"]), 6),
                    "source": _text(item["source"]),
                }
            )
        details = {
            "status": (
                "LEGACY_UNDATED_SAME_TRIM_SAME_MODEL_YEAR_CLUE"
                if legacy_undated
                else "DIRECT_SAME_TRIM_SAME_MODEL_YEAR_EVIDENCE"
            ),
            "side": side,
            "support": 0 if legacy_undated else int(len(usable)),
            "legacy_undated_rows": int(len(usable)) if legacy_undated else 0,
            "duplicate_evidence_rows_removed": int(
                duplicate_evidence_rows_removed
            ),
            "nearest_recency_days": recency,
            "raw_weighted_median_yuan": round(float(raw_anchor), 2)
            if raw_anchor is not None
            else None,
            "adjusted_weighted_median_yuan": round(float(anchor), 2)
            if anchor is not None
            else None,
            "raw_price_p10_yuan": round(float(usable["_price"].quantile(0.10)), 2),
            "raw_price_p90_yuan": round(float(usable["_price"].quantile(0.90)), 2),
            "median_local_factor": round(float(np.median(local_factor)), 6),
            "median_time_factor": round(float(np.median(time_factor)), 6),
            "adjustment_policy": {
                "registration": "按目标与样本上牌月份差逐月折旧/回调",
                "mileage": "高于样本每万公里下修约3%，低于样本每万公里上修约1.5%",
                "transfer": "每多一次过户下修约1.5%，更少过户小幅回调",
                "city": "同城证据优先；跨城只降低权重，不伪造固定城市金额",
                "condition": "按A/B/C/D/E或检测等级比例修正",
                "recency": f"{side}历史价格按年化{int(annual_decay * 100)}%向当前时点衰减",
            },
            "top_comparables": top_comparables,
        }
        return anchor, 0 if legacy_undated else int(len(usable)), recency, details

    def quote(self, payload: dict[str, Any], *, cutoff: Any = None) -> AppraiserAnchor | None:
        identity_key = self._payload_identity_key(payload)
        if not identity_key:
            return None
        cutoff_time = pd.Timestamp(cutoff or payload.get("quote_time") or pd.Timestamp.now())
        if cutoff_time.tzinfo is not None:
            cutoff_time = cutoff_time.tz_convert("Asia/Shanghai").tz_localize(None)
        reviewed = self._quote_reviewed_panel(identity_key, payload, cutoff_time)
        if reviewed is not None:
            return reviewed
        indices = self._evidence_indices.get(identity_key)
        if indices is None or len(indices) == 0:
            return None
        rows = self.evidence.loc[indices]
        registration, mileage, transfer, city, condition = self._target_features(payload)
        b2c, b2c_support, b2c_recency, b2c_evidence = self._side_anchor(
            rows,
            side="B2C",
            cutoff=cutoff_time,
            registration=registration,
            mileage=mileage,
            transfer=transfer,
            city=city,
            condition=condition,
        )
        c2b, c2b_support, c2b_recency, c2b_evidence = self._side_anchor(
            rows,
            side="C2B",
            cutoff=cutoff_time,
            registration=registration,
            mileage=mileage,
            transfer=transfer,
            city=city,
            condition=condition,
        )
        initial_b2c = b2c
        initial_c2b = c2b
        b2c_derivation = "DIRECT_INTERNAL_B2C"
        c2b_derivation = "DIRECT_INTERNAL_C2B"
        if b2c is None and c2b is not None:
            estimated_b2c = c2b / max(1.0 - self.default_spread, 0.75)
            b2c = c2b / max(1.0 - self._spread(estimated_b2c), 0.75)
            b2c_derivation = "DERIVED_FROM_DIRECT_C2B_AND_CONFIRMED_SPREAD"
        if b2c is not None and c2b is None:
            c2b = b2c * (1.0 - self._spread(b2c))
            c2b_derivation = "DERIVED_FROM_B2C_AND_CONFIRMED_SPREAD"
        listing_anchor = None
        if b2c is None or c2b is None:
            listing = pd.to_numeric(rows["first_listing_price_yuan"], errors="coerce")
            listing = listing.loc[listing.between(3_000, 5_000_000)]
            if not listing.empty:
                listing_anchor = float(listing.median()) * 0.96
                if b2c is None:
                    b2c = listing_anchor
                    b2c_derivation = "INTERNAL_LISTING_MEDIAN_WITH_4PCT_NEGOTIATION"
                if c2b is None:
                    c2b = listing_anchor * (1.0 - self._spread(listing_anchor))
                    c2b_derivation = "LISTING_TO_B2C_TO_C2B_SPREAD"
        if b2c is None or c2b is None:
            return None
        b2c = max(float(b2c), 3_500.0)
        derived_c2b = float(b2c) * (1.0 - self._spread(float(b2c)))
        direct_c2b = float(c2b)
        direct_c2b = float(
            np.clip(direct_c2b, derived_c2b * 0.90, derived_c2b * 1.10)
        )
        direct_weight = (
            1.0
            if c2b_support >= 3
            and c2b_recency is not None
            and c2b_recency <= 90
            else 0.75
            if c2b_support >= 3
            and c2b_recency is not None
            and c2b_recency <= 120
            else 0.50
            if c2b_support >= 8
            else 0.25
        )
        c2b = (1.0 - direct_weight) * derived_c2b + direct_weight * direct_c2b
        c2b = max(float(c2b), 3_000.0)
        c2b = min(float(c2b), float(b2c) * 0.985)
        catalog_row = self.catalog.loc[self.catalog["identity_key"].eq(identity_key)].iloc[0]
        return AppraiserAnchor(
            identity_key=identity_key,
            b2c_yuan=float(b2c),
            c2b_yuan=float(c2b),
            b2c_support=b2c_support,
            c2b_support=c2b_support,
            b2c_recency_days=b2c_recency,
            c2b_recency_days=c2b_recency,
            route="STRICT_INTERNAL_SAME_TRIM_SAME_MODEL_YEAR_APPRAISER",
            identity={
                "identity_key": identity_key,
                "brand": _text(catalog_row.get("brand")),
                "series": _text(catalog_row.get("series")),
                "trim": _text(catalog_row.get("trim")),
                "model_year": int(catalog_row.get("model_year")),
                "canonical_model_id": int(catalog_row.get("canonical_model_id")),
                "price_evidence_source": _text(catalog_row.get("price_evidence_source")),
                "dcd_listing_count": int(_number(catalog_row.get("dcd_listing_count")) or 0),
                "dcd_listing_median_yuan": _number(catalog_row.get("dcd_listing_median_yuan")),
            },
            b2c_evidence=b2c_evidence,
            c2b_evidence=c2b_evidence,
            derivation={
                "initial_direct_b2c_yuan": _number(initial_b2c),
                "initial_direct_c2b_yuan": _number(initial_c2b),
                "internal_listing_transaction_proxy_yuan": listing_anchor,
                "b2c_derivation": b2c_derivation,
                "c2b_derivation": c2b_derivation,
                "confirmed_spread_ratio": round(float(self._spread(float(b2c))), 6),
                "c2b_from_b2c_yuan": round(float(derived_c2b), 2),
                "direct_c2b_weight": direct_weight,
                "final_appraiser_b2c_yuan": round(float(b2c), 2),
                "final_appraiser_c2b_yuan": round(float(c2b), 2),
                "same_series_year_primary_anchor": False,
                "official_guide_price_used": False,
                "source_rows_rejected_by_audit": int(
                    self._excluded_counts.get(identity_key, 0)
                ),
            },
        )
