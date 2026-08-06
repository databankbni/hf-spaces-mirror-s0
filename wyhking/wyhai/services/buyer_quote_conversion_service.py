from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .business_market_workbook_loader import normalize_text


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / "buyer_quote_conversion_cache"
DEFAULT_SOURCE = Path("/Users/bytedance/Downloads/未保存的查询-2026-07-13 20-12-50.csv")
WINDOW_DAYS = 90
CSV_CHUNK_SIZE = 100_000
USECOLS = [
    "车源货品ID",
    "车源商品ID",
    "品牌ID",
    "品牌",
    "车系ID",
    "车系",
    "车型ID",
    "车型",
    "2号岗定价时间",
    "是否收车成功",
    "收车门店城市",
    "电商品类划分",
    "车源零售类型",
    "2号岗定价人员是否买手",
    "收车成功方式",
    "收车成功时间",
    "能源类型",
]


def _source_path() -> Path | None:
    configured = os.environ.get("SELECTION_BUYER_QUOTE_CSV_PATH")
    if configured and Path(configured).is_file():
        return Path(configured)
    if DEFAULT_SOURCE.is_file():
        return DEFAULT_SOURCE
    candidates = sorted(
        Path("/Users/bytedance/Downloads").glob("未保存的查询-*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _file_token(path: Path) -> str:
    stat = path.stat()
    return f"{path.stem}_{stat.st_mtime_ns}_{stat.st_size}"


def _clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        left = float(numerator)
        right = float(denominator)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(left) or not math.isfinite(right) or right <= 0:
        return None
    return left / right


class BuyerQuoteConversionService:
    """Serve the true buyer-post B2C acquisition conversion funnel.

    Denominator: unique goods priced by a buyer at post 2 for a ``toc`` lead.
    Numerator: denominator goods that later reached B2C acquisition success.
    Attribution: the first qualifying post-2 pricing timestamp in the window.
    """

    def __init__(
        self,
        source_path: str | Path | None = None,
        *,
        as_of: Any = None,
        window_days: int = WINDOW_DAYS,
    ) -> None:
        self.source_path = Path(source_path) if source_path else _source_path()
        configured_as_of = as_of if as_of is not None else os.environ.get("SELECTION_HISTORY_AS_OF")
        self.as_of = pd.to_datetime(configured_as_of, errors="coerce")
        self.window_days = max(30, int(window_days))
        self._loaded = False
        self._unit_frame = pd.DataFrame()
        self._city_series: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._series: dict[tuple[str, str], dict[str, Any]] = {}
        self._city_category: dict[tuple[str, str], dict[str, Any]] = {}
        self._category: dict[str, dict[str, Any]] = {}
        self._city: dict[str, dict[str, Any]] = {}
        self.metadata: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return not self._unit_frame.empty

    def unit_frame(self) -> pd.DataFrame:
        self._ensure_loaded()
        return self._unit_frame.copy()

    def global_metrics(self) -> dict[str, Any]:
        self._ensure_loaded()
        return _aggregate_frame(self._unit_frame, scope="global")

    def metrics_for(
        self,
        *,
        city: Any = "",
        brand: Any = "",
        series: Any = "",
        category: Any = "",
        fallback: bool = True,
    ) -> dict[str, Any]:
        self._ensure_loaded()
        city_key = normalize_text(city)
        brand_key = normalize_text(brand)
        series_key = normalize_text(series)
        category_key = normalize_text(category)
        is_city = bool(city_key and city_key != normalize_text("全国"))
        if is_city and series_key:
            exact = self._city_series.get((city_key, brand_key, series_key))
            if exact:
                return dict(exact)
        if series_key and (not is_city or fallback):
            national = self._series.get((brand_key, series_key))
            if not national and not brand_key:
                candidates = [row for (key_brand, key_series), row in self._series.items() if key_series == series_key]
                national = candidates[0] if len(candidates) == 1 else None
            if national:
                payload = dict(national)
                if is_city:
                    payload["conversion_scope"] = "national_series_fallback"
                return payload
        if is_city and category_key and fallback:
            row = self._city_category.get((city_key, category_key))
            if row:
                return dict(row)
        if category_key and fallback:
            row = self._category.get(category_key)
            if row:
                return dict(row)
        if is_city and fallback:
            row = self._city.get(city_key)
            if row:
                return dict(row)
        return self.global_metrics() if fallback else {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.source_path or not self.source_path.is_file():
            self.metadata = {"available": False, "error": "buyer_quote_conversion_source_missing"}
            return
        as_of_token = str(self.as_of if pd.notna(self.as_of) else "source_max").replace(":", "").replace(" ", "T")
        cache_path = CACHE_DIR / f"buyer_post2_b2c_v1_{self.window_days}d_{as_of_token}_{_file_token(self.source_path)}.pkl"
        if cache_path.is_file():
            try:
                payload = pd.read_pickle(cache_path)
                if isinstance(payload, dict) and isinstance(payload.get("unit_frame"), pd.DataFrame):
                    self._load_payload(payload)
                    return
            except Exception:
                pass
        payload = self._build_payload()
        self._load_payload(payload)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(payload, cache_path)
        except Exception:
            pass

    def _load_payload(self, payload: dict[str, Any]) -> None:
        self._unit_frame = payload.get("unit_frame") if isinstance(payload.get("unit_frame"), pd.DataFrame) else pd.DataFrame()
        self.metadata = payload.get("metadata") or {}
        self._city_series = _index_rows(payload.get("city_series") or [], ("city", "brand", "series"))
        self._series = _index_rows(payload.get("series") or [], ("brand", "series"))
        self._city_category = _index_rows(payload.get("city_category") or [], ("city", "category"))
        self._category = _index_rows(payload.get("category") or [], ("category",))
        self._city = _index_rows(payload.get("city") or [], ("city",))

    def _build_payload(self) -> dict[str, Any]:
        parts: list[pd.DataFrame] = []
        raw_rows = 0
        eligible_rows = 0
        source_min: pd.Timestamp | None = None
        source_max: pd.Timestamp | None = None
        for chunk in pd.read_csv(
            self.source_path,
            usecols=lambda column: column in USECOLS,
            chunksize=CSV_CHUNK_SIZE,
            low_memory=False,
            encoding="utf-8-sig",
        ):
            raw_rows += len(chunk)
            pricing_at = pd.to_datetime(chunk.get("2号岗定价时间"), errors="coerce")
            if pricing_at.notna().any():
                current_min = pd.Timestamp(pricing_at.min())
                current_max = pd.Timestamp(pricing_at.max())
                source_min = current_min if source_min is None else min(source_min, current_min)
                source_max = current_max if source_max is None else max(source_max, current_max)
            goods_id = pd.to_numeric(chunk.get("车源货品ID"), errors="coerce")
            eligible = (
                _clean_text(chunk.get("车源零售类型", pd.Series(index=chunk.index, dtype=object))).str.lower().eq("toc")
                & _clean_text(chunk.get("2号岗定价人员是否买手", pd.Series(index=chunk.index, dtype=object))).eq("是")
                & pricing_at.notna()
                & goods_id.gt(0)
            )
            if not eligible.any():
                continue
            work = chunk.loc[eligible].copy()
            work["goods_id"] = goods_id.loc[eligible].astype("int64")
            work["pricing_at"] = pricing_at.loc[eligible]
            work["success_at"] = pd.to_datetime(work.get("收车成功时间"), errors="coerce")
            success = _clean_text(work.get("是否收车成功", pd.Series(index=work.index, dtype=object))).eq("是")
            b2c = _clean_text(work.get("收车成功方式", pd.Series(index=work.index, dtype=object))).str.upper().eq("B2C")
            work["b2c_success"] = success & b2c
            work = work.rename(
                columns={
                    "品牌": "brand",
                    "车系": "series",
                    "车型": "model",
                    "收车门店城市": "city",
                    "电商品类划分": "category",
                    "能源类型": "energy_type",
                }
            )
            keep = [
                "goods_id",
                "pricing_at",
                "success_at",
                "b2c_success",
                "brand",
                "series",
                "model",
                "city",
                "category",
                "energy_type",
            ]
            for column in keep:
                if column not in work:
                    work[column] = None
            for column in ("brand", "series", "model", "city", "category", "energy_type"):
                work[column] = _clean_text(work[column])
            parts.append(work[keep])
            eligible_rows += len(work)
        if not parts:
            return {"unit_frame": pd.DataFrame(), "metadata": {"available": False, "error": "no_eligible_rows"}}
        work = pd.concat(parts, ignore_index=True)
        resolved_as_of = pd.Timestamp(self.as_of) if pd.notna(self.as_of) else pd.Timestamp(work["pricing_at"].max())
        window_start = resolved_as_of - pd.Timedelta(days=self.window_days)
        work = work[work["pricing_at"].between(window_start, resolved_as_of, inclusive="both")].copy()
        work = work.sort_values(["goods_id", "pricing_at"], kind="mergesort")
        first = work.drop_duplicates("goods_id", keep="first").copy()
        outcomes = work.groupby("goods_id", as_index=False).agg(
            b2c_success=("b2c_success", "max"),
            success_at=("success_at", "min"),
            raw_row_count=("goods_id", "size"),
        )
        units = first.drop(columns=["b2c_success", "success_at"]).merge(outcomes, on="goods_id", how="left")
        success_before_price = units["b2c_success"] & units["success_at"].notna() & (units["success_at"] < units["pricing_at"])
        units.loc[success_before_price, "b2c_success"] = False
        units["pricing_week"] = units["pricing_at"].dt.to_period("W-MON").astype(str)
        units = units.reset_index(drop=True)
        metadata = {
            "available": True,
            "source_file": self.source_path.name,
            "source_raw_rows": raw_rows,
            "source_eligible_rows_all_dates": eligible_rows,
            "source_pricing_min": source_min.isoformat() if source_min is not None else None,
            "source_pricing_max": source_max.isoformat() if source_max is not None else None,
            "window_start": window_start.isoformat(),
            "window_end": resolved_as_of.isoformat(),
            "window_days": self.window_days,
            "unique_buyer_priced_toc_goods": int(len(units)),
            "b2c_success_goods": int(units["b2c_success"].sum()),
            "b2c_acquisition_conversion_rate": _safe_ratio(units["b2c_success"].sum(), len(units)),
            "duplicate_rows_removed_in_window": int(len(work) - len(units)),
            "success_before_first_buyer_price_excluded": int(success_before_price.sum()),
            "metric_grain": "unique_goods_id",
            "attribution_time": "first_qualifying_post2_buyer_pricing_time",
            "denominator": "toc且2号岗定价人员是买手的唯一车源货品数",
            "numerator": "分母中最终B2C收车成功的唯一车源货品数",
        }
        return {
            "unit_frame": units,
            "metadata": metadata,
            "city_series": _group_rows(units, ("city", "brand", "series"), "city_series"),
            "series": _group_rows(units, ("brand", "series"), "national_series"),
            "city_category": _group_rows(units, ("city", "category"), "city_category"),
            "category": _group_rows(units, ("category",), "national_category"),
            "city": _group_rows(units, ("city",), "city"),
        }


def _aggregate_frame(frame: pd.DataFrame, *, scope: str) -> dict[str, Any]:
    if frame.empty:
        return {}
    denominator = int(len(frame))
    numerator = int(frame["b2c_success"].sum())
    return {
        "acquired_conversion_numerator": numerator,
        "acquired_conversion_denominator": denominator,
        "acquisition_conversion_rate": _safe_ratio(numerator, denominator),
        "purchase_conversion_available": denominator > 0,
        "acquisition_conversion_metric_name": "buyer_post2_toc_b2c_success_90d",
        "conversion_scope": scope,
    }


def _group_rows(frame: pd.DataFrame, columns: Iterable[str], scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    group_columns = list(columns)
    for key, group in frame.groupby(group_columns, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        payload = {column: value for column, value in zip(group_columns, key)}
        payload.update(_aggregate_frame(group, scope=scope))
        rows.append(payload)
    return rows


def _index_rows(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> dict[Any, dict[str, Any]]:
    output: dict[Any, dict[str, Any]] = {}
    for row in rows:
        key_parts = tuple(normalize_text(row.get(column)) for column in columns)
        key: Any = key_parts[0] if len(key_parts) == 1 else key_parts
        output[key] = row
    return output


@lru_cache(maxsize=4)
def get_buyer_quote_conversion_service(as_of: str = "") -> BuyerQuoteConversionService:
    return BuyerQuoteConversionService(as_of=as_of or None)
