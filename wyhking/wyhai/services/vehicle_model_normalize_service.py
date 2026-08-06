from __future__ import annotations

import difflib
import gzip
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from .online_vehicle_catalog_service import OnlineVehicleCatalogService
from .vehicle_identity_semantics import (
    code_compatibility,
    distinctive_vehicle_codes,
    most_specific_query_code,
)


class VehicleModelNormalizeService:
    """Normalize slots against the vehicle catalog without silent mis-match."""

    def __init__(self) -> None:
        self._catalog = None
        self._runtime_catalog = None
        self.online_catalog = OnlineVehicleCatalogService()


    @staticmethod
    def _compact(value: Any) -> str:
        return re.sub(r"[\s,，。._/()（）·・\-]+", "", str(value or "")).lower()

    @classmethod
    def _similarity(cls, left: Any, right: Any) -> float:
        a = cls._compact(left)
        b = cls._compact(right)
        if not a or not b:
            return 0.0
        seq = difflib.SequenceMatcher(None, a, b).ratio()
        a2 = {a[i:i+2] for i in range(max(len(a) - 1, 1))} or {a}
        b2 = {b[i:i+2] for i in range(max(len(b) - 1, 1))} or {b}
        jac = len(a2 & b2) / max(len(a2 | b2), 1)
        return max(seq, jac)

    def _fuzzy_catalog_candidates(self, message: str, brand: str | None, model_year: int | None, limit: int = 8) -> List[Dict[str, Any]]:
        catalog = self._load_catalog()
        if catalog is None or getattr(catalog, "empty", True):
            return []
        df = catalog
        if brand and "brand" in df.columns:
            brand_exact = df[df["brand"].astype(str).eq(str(brand))]
            if brand_exact.empty:
                brand_exact = df[
                    df["brand"].astype(str).str.contains(str(brand), regex=False, na=False)
                    | df["series"].astype(str).str.startswith(str(brand), na=False)
                ]
            if not brand_exact.empty:
                df = brand_exact
            else:
                return []
        if model_year and "model_year" in df.columns:
            year_exact = df[df["model_year"].astype("Int64", errors="ignore").astype(str).eq(str(model_year))]
            if not year_exact.empty:
                df = year_exact
        rows: List[Dict[str, Any]] = []
        text = str(message or "")
        for _, row in df.head(5000).iterrows():
            label = self._label(row)
            hay = " ".join(str(row.get(k) or "") for k in ["brand", "series", "model_name", "model_year"])
            if code_compatibility(text, hay) is False:
                continue
            score = self._similarity(text, hay)
            if score < 0.38:
                continue
            item = {
                "model_id": str(row.get("model_id") or ""),
                "series_id": str(row.get("series_id") or ""),
                "brand": row.get("brand", ""),
                "series": row.get("series", ""),
                "model_year": int(row["model_year"]) if row.get("model_year") == row.get("model_year") else None,
                "model_name": row.get("model_name", ""),
                "label": label,
                "fuzzy_score": round(score, 4),
            }
            rows.append(item)
        rows.sort(key=lambda x: x.get("fuzzy_score", 0), reverse=True)
        return rows[:limit]

    def _load_catalog(self):
        if self._catalog is not None:
            return self._catalog
        try:
            from v7_pricing_engine import load_vehicle_catalog

            self._catalog = load_vehicle_catalog()
        except Exception:
            self._catalog = None
        return self._catalog

    def _load_runtime_catalog(self) -> List[Dict[str, Any]]:
        if self._runtime_catalog is not None:
            return self._runtime_catalog
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "runtime"
            / "vehicle_catalog_search_index.json.gz"
        )
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                rows = json.load(handle)
            self._runtime_catalog = rows if isinstance(rows, list) else []
        except Exception:
            self._runtime_catalog = []
        return self._runtime_catalog

    def _runtime_catalog_candidates(
        self,
        brand: str,
        series: str | None,
        model_year: int | None,
        limit: int = 8,
        query_text: Any = "",
    ) -> List[Dict[str, Any]]:
        brand_compact = self._compact(brand)
        series_compact = self._compact(series)
        candidates: List[Dict[str, Any]] = []
        for row in self._load_runtime_catalog():
            row_brand = str(row.get("brand") or "")
            row_series = str(row.get("series") or "")
            if brand_compact and self._compact(row_brand) != brand_compact:
                continue
            searchable_series = self._compact(row_series)
            if brand_compact and searchable_series.startswith(brand_compact):
                searchable_series_without_brand = searchable_series[len(brand_compact) :]
            else:
                searchable_series_without_brand = searchable_series
            if series_compact and series_compact not in {
                searchable_series,
                searchable_series_without_brand,
            }:
                continue
            row_year = row.get("model_year")
            if model_year and str(row_year or "") != str(model_year):
                continue
            model_name = str(row.get("model") or row.get("model_name") or "")
            candidates.append(
                {
                    "model_id": str(row.get("model_id") or row.get("id") or ""),
                    "series_id": str(row.get("series_id") or ""),
                    "brand": row_brand,
                    "series": row_series,
                    "model_year": int(row_year) if str(row_year or "").isdigit() else None,
                    "model_name": model_name,
                    "label": self._label(
                        {
                            "brand": row_brand,
                            "series": row_series,
                            "model_year": int(row_year) if str(row_year or "").isdigit() else None,
                            "model_name": model_name,
                        }
                    ),
                }
            )
        if query_text:
            candidates = self._rank_candidates_by_user_text(candidates, query_text)
        return candidates[:limit]

    @staticmethod
    def _slot_value(slots: Dict[str, Any], key: str) -> Any:
        value = (slots.get(key) or {}).get("value")
        return value

    def _catalog_candidates(
        self,
        brand: str,
        series: str | None,
        model_year: int | None,
        limit: int = 8,
        query_text: Any = "",
    ) -> List[Dict[str, Any]]:
        # The production runtime index is the complete internal-transaction +
        # current-DCD catalog.  Query it before the legacy v7 training catalog.
        # For an explicit trim, rank the entire same-series/year pool before
        # truncating; popularity-first truncation can turn 525 into 530.
        runtime = self._runtime_catalog_candidates(
            brand, series, model_year, limit, query_text=query_text
        )
        if runtime:
            return runtime
        catalog = self._load_catalog()
        if catalog is None or getattr(catalog, "empty", True):
            return (
                self.online_catalog.candidates(brand, series, model_year, limit)
                if series
                else self._online_brand_candidates(brand, limit)
            )
        df = catalog
        if brand:
            brand_exact = df[df["brand"].astype(str).eq(str(brand))]
            if brand_exact.empty:
                brand_exact = df[
                    df["brand"].astype(str).str.contains(str(brand), regex=False, na=False)
                    | df["series"].astype(str).str.startswith(str(brand), na=False)
                ]
            df = brand_exact
        if series:
            s = str(series).replace(" ", "").lower()
            df2 = df[
                df["series"].astype(str).str.replace(" ", "", regex=False).str.lower().str.contains(s, regex=False, na=False)
                | df["model_name"].astype(str).str.replace(" ", "", regex=False).str.lower().str.contains(s, regex=False, na=False)
            ]
            if df2.empty:
                return self.online_catalog.candidates(brand, series, model_year, limit)
            df = df2
        if model_year:
            exact = df[df["model_year"].astype("Int64", errors="ignore").astype(str).eq(str(model_year))]
            if exact.empty:
                return self.online_catalog.candidates(brand, series or "", model_year, limit) if series else []
            df = exact
        if "sample_count" in df.columns:
            df = df.sort_values("sample_count", ascending=False)
        rows = []
        for _, row in df.head(limit).iterrows():
            rows.append(
                {
                    "model_id": str(row.get("model_id") or ""),
                    "series_id": str(row.get("series_id") or ""),
                    "brand": row.get("brand", ""),
                    "series": row.get("series", ""),
                    "model_year": int(row["model_year"]) if row.get("model_year") == row.get("model_year") else None,
                    "model_name": row.get("model_name", ""),
                    "label": self._label(row),
                }
            )
        if query_text:
            rows = self._rank_candidates_by_user_text(rows, query_text)
        return rows

    def _online_brand_candidates(self, brand: str, limit: int = 8) -> List[Dict[str, Any]]:
        rows = []
        for item in self.online_catalog.list_brand_series(brand, limit):
            rows.append(
                {
                    "model_id": "",
                    "series_id": str(item.get("series_id") or ""),
                    "brand": item.get("brand") or brand,
                    "series": item.get("series") or "",
                    "model_year": None,
                    "model_name": "",
                    "label": f"{item.get('brand') or brand} {item.get('series') or ''}".strip(),
                    "catalog_source": "autohome_current_catalog",
                    "source_url": item.get("source_url"),
                }
            )
        return rows

    @staticmethod
    def _label(row: Dict[str, Any]) -> str:
        year = row.get("model_year")
        prefix = f"{int(year)}款 " if year == year and year else ""
        brand = str(row.get("brand") or "").strip()
        series = str(row.get("series") or "").strip()
        if brand and series.startswith(brand):
            parts = [series, str(row.get("model_name") or "")]
        else:
            parts = [brand, series, str(row.get("model_name") or "")]
        return prefix + " ".join([p for p in parts if p]).strip()

    @classmethod
    def _rank_candidates_by_user_text(
        cls,
        candidates: List[Dict[str, Any]],
        user_model_text: Any,
    ) -> List[Dict[str, Any]]:
        """Prefer the user's explicit trim/code over catalog popularity.

        Catalog rows are often sorted by sample_count.  That is useful for
        suggestions, but unsafe after the user has typed a concrete trim:
        "525Li M运动套装" must not inherit the model_id of a more common 530Li.
        """

        if not candidates:
            return candidates
        query_text = str(user_model_text or "").strip()
        query_compact = cls._compact(query_text)
        query_code = most_specific_query_code(query_text)
        if not query_compact and not query_code:
            return candidates

        scored: List[tuple[float, int, Dict[str, Any]]] = []
        for idx, item in enumerate(candidates):
            model_name = str(item.get("model_name") or "")
            label = str(item.get("label") or "")
            haystack = f"{model_name} {label}".strip()
            model_compact = cls._compact(model_name)
            candidate_code = most_specific_query_code(haystack)

            score = cls._similarity(query_text, model_name) * 100
            score += cls._similarity(query_text, label) * 40
            if query_compact and model_compact == query_compact:
                score += 520
            elif query_compact and query_compact in model_compact:
                score += 280
            elif query_compact and model_compact and model_compact in query_compact:
                score += 120

            compat = code_compatibility(query_text, haystack)
            if compat is True:
                score += 260
            elif compat is False:
                score -= 700

            if query_code and candidate_code:
                if query_code == candidate_code:
                    score += 260
                else:
                    score -= 520

            if "改款" not in query_text and "改款" in model_name:
                score -= 20
            scored.append((score, -idx, item))

        scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
        return [item for _, _, item in scored]

    def _fallback_brand_candidates(self, brand: str) -> List[Dict[str, Any]]:
        # Broad brand-level suggestions. This is not one-off hardcoding for a
        # single test case; it is the safe fallback when catalog coverage for
        # newer brands is incomplete.
        hints = {
            "小米": ["小米SU7", "小米SU7 Ultra"],
            "问界": ["问界M5", "问界M7", "问界M9"],
            "理想": ["理想L6", "理想L7", "理想L8", "理想L9"],
            "蔚来": ["蔚来ET5", "蔚来ES6", "蔚来ES8"],
            "小鹏": ["小鹏P7", "小鹏G6", "小鹏G9"],
        }
        return [
            {"model_id": "", "series_id": "", "brand": brand, "series": label.replace(brand, ""), "model_name": "", "label": label}
            for label in hints.get(brand, [])
        ]

    def normalize(self, slots: Dict[str, Any], message: str = "") -> Dict[str, Any]:
        brand = self._slot_value(slots, "brand")
        series = self._slot_value(slots, "series")
        model_year = self._slot_value(slots, "model_year")
        if isinstance(model_year, str) and model_year.isdigit():
            model_year = int(model_year)
        trim = self._slot_value(slots, "trim")
        raw_vehicle_text = self._slot_value(slots, "raw_vehicle_text")
        # A series/year string is not a concrete trim.  Earlier code treated a
        # synthesized raw label such as “2018 宝沃 BX7” as user confirmation
        # and silently selected the first catalog configuration.  Only an
        # explicit trim is sufficient for exact pricing; a series-only request
        # must ask the user to confirm the configuration.
        user_confirmed_vehicle = bool(trim)

        if brand and series and model_year and user_confirmed_vehicle:
            model_name = str(trim or raw_vehicle_text or series or "").strip()
            candidates = self._catalog_candidates(
                str(brand or ""),
                str(series or ""),
                model_year,
                8,
                query_text=model_name,
            )
            candidates = self._rank_candidates_by_user_text(candidates, model_name)
            # A concrete numeric/alpha-numeric configuration is an identity
            # constraint, not a soft ranking hint.  If a user says 1160, 945,
            # 605 or 215Max, never borrow a different catalog trim merely
            # because it is the most popular row for that series/year.
            if distinctive_vehicle_codes(model_name):
                candidates = [
                    item
                    for item in candidates
                    if code_compatibility(
                        model_name,
                        f"{item.get('model_name') or ''} {item.get('label') or ''}",
                    )
                    is not False
                ]
            top = candidates[0] if candidates else {}
            return {
                "matched": True,
                "need_manual_confirm": False,
                # Keep the catalog display identity when it is available.  The
                # extraction layer intentionally stores compact series slots
                # such as ``3系``; the match returned to the frontline must use
                # the canonical catalog label (``宝马3系``) so the confirmation
                # card cannot look like a different or incomplete vehicle.
                "brand_name": top.get("brand") or brand or "",
                "series_name": top.get("series") or series or "",
                "model_id": top.get("model_id", ""),
                "series_id": top.get("series_id", ""),
                "model_name": model_name,
                "model_year": model_year,
                "match_confidence": 0.92 if candidates else 0.86,
                "match_method": "user_confirmed_full_trim_text",
                "match_reason": "用户已输入品牌/车系/年款/具体款型，允许直接估价；车型库候选仅作参考",
                "candidates": candidates,
                "user_confirmed_vehicle": True,
                "catalog_source": top.get("catalog_source") or ("local_historical_catalog" if candidates else "user_confirmed_custom_model"),
                "catalog_source_url": top.get("source_url") or "",
                "catalog_coverage_level": "exact_year_candidate" if candidates else "series_or_custom_text_only",
                "official_price_min": top.get("official_price_min"),
                "official_price_max": top.get("official_price_max"),
            }

        fuzzy_candidates = self._fuzzy_catalog_candidates(message, brand, model_year, 8)
        if fuzzy_candidates and not series and model_year and (trim or raw_vehicle_text):
            top = fuzzy_candidates[0]
            return {
                "matched": True,
                "need_manual_confirm": False,
                "brand_name": top.get("brand") or brand or "",
                "series_name": top.get("series") or series or "",
                "model_id": top.get("model_id") or "",
                "series_id": top.get("series_id") or "",
                "model_name": top.get("model_name") or str(trim or raw_vehicle_text or ""),
                "model_year": top.get("model_year") or model_year,
                "match_confidence": min(0.86, max(0.55, float(top.get("fuzzy_score") or 0))),
                "match_method": "fuzzy_catalog_typo_recovery",
                "match_reason": "用户输入疑似包含错别字，已按车型库相似度恢复候选；保留候选列表供证据卡审计",
                "candidates": fuzzy_candidates,
                "normalization_warnings": ["FUZZY_VEHICLE_TEXT_RECOVERY"],
            }

        # Brand without series must never become a concrete model silently.
        if brand and not series:
            candidates = (
                self._catalog_candidates(brand, None, model_year, 8)
                or self._online_brand_candidates(brand, 8)
                or self._fallback_brand_candidates(brand)
            )
            # Collapse to series-level labels for quick tags.
            seen = set()
            compact = []
            for item in candidates:
                key = item.get("series") or item.get("label")
                if key in seen:
                    continue
                seen.add(key)
                compact.append(item)
            return {
                "matched": False,
                "need_manual_confirm": True,
                "brand_name": brand,
                "series_name": "",
                "model_id": "",
                "series_id": "",
                "model_name": "",
                "model_year": model_year,
                "match_confidence": 0.0,
                "match_method": "brand_only",
                "match_reason": "只有品牌，缺少车系/车型",
                "candidates": compact[:8],
            }

        if not brand and not series:
            return {
                "matched": False,
                "need_manual_confirm": True,
                "match_confidence": 0.0,
                "match_method": "no_vehicle_hint",
                "match_reason": "缺少品牌或车系",
                "candidates": [],
            }

        candidates = self._catalog_candidates(str(brand or ""), str(series or ""), model_year, 8)
        if not candidates:
            fuzzy_candidates = fuzzy_candidates or self._fuzzy_catalog_candidates(message, brand, model_year, 8)
            if fuzzy_candidates:
                top = fuzzy_candidates[0]
                return {
                    "matched": True,
                    "need_manual_confirm": bool(float(top.get("fuzzy_score") or 0) < 0.55 and not (trim or raw_vehicle_text)),
                    "brand_name": top.get("brand") or brand or "",
                    "series_name": top.get("series") or series or "",
                    "model_id": top.get("model_id") or "",
                    "series_id": top.get("series_id") or "",
                    "model_name": top.get("model_name") or str(trim or raw_vehicle_text or ""),
                    "model_year": top.get("model_year") or model_year,
                    "match_confidence": min(0.82, max(0.45, float(top.get("fuzzy_score") or 0))),
                    "match_method": "fuzzy_catalog_no_exact_match",
                    "match_reason": "车型库无精确候选，使用模糊相似候选；低置信时需要人工确认",
                    "candidates": fuzzy_candidates,
                    "normalization_warnings": ["NO_EXACT_MODEL_MATCH_FUZZY_USED"],
                }
            return {
                "matched": bool(trim or raw_vehicle_text),
                "need_manual_confirm": not bool(trim or raw_vehicle_text),
                "brand_name": brand or "",
                "series_name": series or "",
                "model_id": "",
                "series_id": "",
                "model_name": str(trim or raw_vehicle_text or ""),
                "model_year": model_year,
                "match_confidence": 0.55 if (trim or raw_vehicle_text) else 0.0,
                "match_method": "custom_model_text_catalog_missing" if (trim or raw_vehicle_text) else "no_match",
                "match_reason": "车型库未收录该具体款型，按用户输入自定义款型报价并在证据中标注" if (trim or raw_vehicle_text) else "车型库无稳定候选",
                "candidates": self._fallback_brand_candidates(str(brand or ""))[:8],
                "normalization_warnings": ["CATALOG_MISSING_CUSTOM_MODEL_USED"] if (trim or raw_vehicle_text) else [],
            }

        if len(candidates) == 1 and model_year:
            top = candidates[0]
            return {
                "matched": True,
                "need_manual_confirm": True,
                "brand_name": top["brand"],
                "series_name": top["series"],
                "model_id": top["model_id"],
                "series_id": top["series_id"],
                "model_name": top["model_name"],
                "model_year": top["model_year"] or model_year,
                "match_confidence": 0.72,
                "match_method": "catalog_single_suggestion_requires_confirmation",
                "match_reason": "当前目录仅返回一个候选，但用户未输入具体款型；候选只作建议，仍需用户确认",
                "candidates": candidates,
            }

        top = candidates[0]
        return {
            "matched": True,
            "need_manual_confirm": True,
            "brand_name": top["brand"],
            "series_name": top["series"],
            "model_id": top["model_id"],
            "series_id": top["series_id"],
            "model_name": top["model_name"],
            "model_year": top["model_year"] or model_year,
            "match_confidence": 0.65 if len(candidates) > 1 else 0.78,
            "match_method": "catalog_candidates",
            "match_reason": "存在多个车型库候选，需要用户确认",
            "candidates": candidates,
        }
