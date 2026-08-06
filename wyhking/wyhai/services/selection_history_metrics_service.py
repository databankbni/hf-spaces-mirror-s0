from __future__ import annotations

import math
import base64
import gzip
import io
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .brand_tier import matches_brand_tier, normalize_brand_tier
from .buyer_quote_conversion_service import BuyerQuoteConversionService
from .business_market_workbook_loader import normalize_text
from .vehicle_taxonomy import get_vehicle_taxonomy_service, normalize_selection_filter


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / "selection_history_cache"
TRAINING_GLOB = "训练1*90天*.csv"
DEFAULT_WINDOW_DAYS = 90
DEFAULT_CONVERSION_HORIZON_DAYS = 45
CSV_CHUNK_SIZE = 100_000
HISTORY_USECOLS = [
    "车源货品ID", "车源商品ID", "品牌名称", "车系名称", "能源类型", "车源所在城市", "首次上架时间",
    "首次展板价", "收车合同签订时间", "收车合同价", "最新订单成交价", "已售时间", "是否事故车",
    "是否泡水车", "是否火烧车", "是否调表车", "是否B2C处置", "在售状态",
]


def _latest_training_csv() -> Path | None:
    env_path = os.environ.get("SELECTION_90D_CSV_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    candidates = sorted(Path("/Users/bytedance/Downloads").glob(TRAINING_GLOB), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _file_cache_token(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{path.stem}_{stat.st_mtime_ns}_{stat.st_size}"
    except OSError:
        return f"{path.stem}_missing"


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


class SelectionHistoryMetricsService:
    """Aggregate internal 90-day B2C business outcomes for selection scoring.

    The raw 90-day CSV is large enough that request-time scans are wasteful. This
    service reads only the columns needed for selection, writes compact group
    caches, and serves city-series / national-series business metrics.
    """

    def __init__(self, csv_path: str | Path | None = None) -> None:
        self.csv_path = Path(csv_path) if csv_path else _latest_training_csv()
        self._city_series: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._series: dict[tuple[str, str], dict[str, Any]] = {}
        self._loaded = False
        self.metadata: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._city_series or self._series)

    def metrics_for(
        self,
        *,
        city: Any = "",
        brand: Any = "",
        series: Any = "",
        fallback_to_national: bool = True,
    ) -> dict[str, Any]:
        self._ensure_loaded()
        series_key = normalize_text(series)
        if not series_key:
            return {}
        brand_key = normalize_text(brand)
        city_key = normalize_text(city)
        national_key = normalize_text("全国")
        is_city_request = bool(city_key and city_key != national_key)
        row = self._city_series.get((city_key, brand_key, series_key)) if is_city_request else None
        if row:
            return {
                **dict(row),
                "history_scope": "city",
                "history_scope_display": f"{city}本地90天实证",
                "requested_city": str(city or ""),
            }
        if is_city_request and not fallback_to_national:
            return {}
        row = self._series.get((brand_key, series_key))
        if not row and not brand_key:
            candidates = [value for (candidate_brand, candidate_series), value in self._series.items() if candidate_series == series_key]
            row = candidates[0] if len(candidates) == 1 else None
        if not row:
            return {}
        scope = "national_fallback" if is_city_request else "national"
        scope_display = "全国90天同车系先验（本地样本缺失）" if is_city_request else "全国90天实证"
        return {
            **dict(row),
            "history_scope": scope,
            "history_scope_display": scope_display,
            "requested_city": str(city or "全国"),
        }

    def series_matching_energy(self, energy_type: str, *, city: str = "") -> set[str]:
        self._ensure_loaded()
        target = _normalize_energy(energy_type)
        if not target:
            return set()
        rows = self._city_series.values() if city and city != "全国" else self._series.values()
        out = {
            normalize_text(row.get("series"))
            for row in rows
            if _energy_matches(row.get("dominant_energy_type"), target)
            and (not city or city == "全国" or normalize_text(row.get("city")) == normalize_text(city))
        }
        return {item for item in out if item}

    def baseline(
        self,
        *,
        city: str = "",
        energy_type: str = "",
        selection_filter: str = "",
        brand_tier: str = "",
        price_band: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_loaded()
        rows = list(self._city_series.values() if city and city != "全国" else self._series.values())
        if city and city != "全国":
            city_key = normalize_text(city)
            rows = [row for row in rows if normalize_text(row.get("city")) == city_key]
        target = _normalize_energy(energy_type)
        if target:
            rows = [row for row in rows if _energy_matches(row.get("dominant_energy_type"), target)]
        filter_label = normalize_selection_filter(selection_filter)
        if filter_label and filter_label != "全部":
            taxonomy = get_vehicle_taxonomy_service()
            rows = [
                row for row in rows
                if taxonomy.matches_selection_filter(
                    brand=row.get("brand"),
                    series=row.get("series"),
                    selected_filter=filter_label,
                )
            ]
        tier = normalize_brand_tier(brand_tier)
        if tier:
            rows = [row for row in rows if matches_brand_tier(row.get("brand"), tier)]
        low = _safe_float((price_band or {}).get("low"))
        high = _safe_float((price_band or {}).get("high"))
        if low is not None or high is not None:
            price_rows = [row for row in rows if _price_in_band(row.get("avg_sale_price"), low, high)]
            if price_rows:
                rows = price_rows
        result = _aggregate_metric_rows(rows)
        result["baseline_price_band"] = (price_band or {}).get("label") or "不限"
        result["baseline_scope"] = "city" if city and city != "全国" else "national"
        result["baseline_city"] = city or "全国"
        result["baseline_energy_type"] = energy_type or "不限"
        result["baseline_selection_filter"] = filter_label or "全部"
        result["baseline_brand_tier"] = tier or "不限"
        return result

    def unit_events_for_evaluation(self) -> pd.DataFrame:
        """Return the compact unique-unit event frame for offline 90-day audits."""
        if not self.csv_path or not self.csv_path.is_file():
            return pd.DataFrame()
        return _load_unique_product_frame(self.csv_path, HISTORY_USECOLS)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.csv_path or not self.csv_path.is_file():
            if self._load_bundled_precomputed_cache():
                return
            self.metadata = {"available": False, "error": "selection_90d_csv_missing"}
            return
        window_days = max(30, int(os.environ.get("SELECTION_HISTORY_WINDOW_DAYS", DEFAULT_WINDOW_DAYS)))
        conversion_horizon_days = max(15, int(os.environ.get("SELECTION_CONVERSION_HORIZON_DAYS", DEFAULT_CONVERSION_HORIZON_DAYS)))
        configured_as_of = str(os.environ.get("SELECTION_HISTORY_AS_OF") or "latest").replace(":", "").replace("/", "-").replace(" ", "T")
        cache_path = CACHE_DIR / f"history_v8_true_buyer_conversion_{window_days}d_{conversion_horizon_days}d_{configured_as_of}_{_file_cache_token(self.csv_path)}.pkl"
        if cache_path.is_file() and self._load_cache_payload(cache_path):
            return
        frame = _load_unique_product_frame(self.csv_path, HISTORY_USECOLS)
        if frame.empty:
            self.metadata = {"available": False, "error": "selection_history_empty_after_dedupe"}
            return
        as_of = _resolve_as_of(frame)
        city_series_rows = _group_metrics(
            frame,
            ["city", "brand", "series"],
            as_of=as_of,
            window_days=window_days,
            conversion_horizon_days=conversion_horizon_days,
        )
        series_rows = _group_metrics(
            frame,
            ["brand", "series"],
            as_of=as_of,
            window_days=window_days,
            conversion_horizon_days=conversion_horizon_days,
        )
        conversion = BuyerQuoteConversionService(as_of=as_of, window_days=window_days)
        _apply_true_acquisition_conversion(city_series_rows, conversion, city_level=True)
        _apply_true_acquisition_conversion(series_rows, conversion, city_level=False)
        self._city_series = {
            (normalize_text(row.get("city")), normalize_text(row.get("brand")), normalize_text(row.get("series"))): row
            for row in city_series_rows
        }
        self._series = {
            (normalize_text(row.get("brand")), normalize_text(row.get("series"))): row
            for row in series_rows
        }
        self.metadata = {
            "available": True,
            "source_file": self.csv_path.name,
            "raw_row_count": int(frame["raw_row_count"].sum()),
            "unique_product_count": int(len(frame)),
            "city_series_count": len(self._city_series),
            "series_count": len(self._series),
            "metric_grain": "unique_product_id",
            "metric_grain_display": "车源商品ID优先去重；按事件时间显式截取窗口，不依赖文件名",
            "as_of": as_of.isoformat(),
            "window_start": (as_of - pd.Timedelta(days=window_days)).isoformat(),
            "history_window_days": window_days,
            "conversion_horizon_days": conversion_horizon_days,
            "normal_condition_only": True,
            "excluded_condition_flags": ["事故", "泡水", "火烧", "调表", "B2C处置"],
            "purchase_conversion_available": conversion.available,
            "purchase_conversion_note": "收车转化率按toc且2号岗定价人员为买手的唯一车源货品计算，分子为最终B2C收车成功车源，按2号岗首次合格定价时间归因。",
            "buyer_quote_conversion": conversion.metadata,
            "history_metric_version": "time_aware_v8_true_buyer_conversion",
        }
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(
                {
                    "city_series": self._city_series,
                    "series": self._series,
                    "metadata": self.metadata,
                },
                cache_path,
            )
        except Exception:
            pass

    def _load_bundled_precomputed_cache(self) -> bool:
        """Restore the reviewed 90-day aggregates in source-data-free deployments."""

        configured = str(os.environ.get("SELECTION_HISTORY_CACHE_PATH") or "").strip()
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured))
        candidates.extend(
            sorted(
                [
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*_latest_*.pkl"),
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*_latest_*.pkl.b64"),
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*_latest_*.pkl.gz.b64"),
                ],
                key=lambda path: (path.stat().st_mtime_ns, path.name),
                reverse=True,
            )
        )
        candidates.extend(
            sorted(
                [
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*.pkl"),
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*.pkl.b64"),
                    *CACHE_DIR.glob("history_v8_true_buyer_conversion_*.pkl.gz.b64"),
                ],
                key=lambda path: (path.stat().st_mtime_ns, path.name),
                reverse=True,
            )
        )
        for cache_path in dict.fromkeys(candidates):
            if cache_path.is_file() and self._load_cache_payload(cache_path):
                self.metadata = {
                    **self.metadata,
                    "deployment_source": "bundled_precomputed_v8_cache",
                    "deployment_cache_file": cache_path.name,
                }
                return True
        return False

    def _load_cache_payload(self, cache_path: Path) -> bool:
        try:
            if cache_path.name.endswith(".b64"):
                raw_payload = base64.b64decode(cache_path.read_bytes())
                if cache_path.name.endswith(".gz.b64"):
                    raw_payload = gzip.decompress(raw_payload)
                payload = pd.read_pickle(io.BytesIO(raw_payload))
            else:
                payload = pd.read_pickle(cache_path)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        city_series = payload.get("city_series") or {}
        series = payload.get("series") or {}
        if not city_series and not series:
            return False
        self._city_series = city_series
        self._series = series
        self.metadata = payload.get("metadata") or {}
        if self.metadata.get("as_of") and not self.metadata.get("window_start"):
            cached_as_of = pd.Timestamp(self.metadata["as_of"])
            cached_window_days = int(self.metadata.get("history_window_days") or DEFAULT_WINDOW_DAYS)
            self.metadata["window_start"] = (cached_as_of - pd.Timedelta(days=cached_window_days)).isoformat()
        return True


def _apply_true_acquisition_conversion(
    rows: list[dict[str, Any]],
    conversion: BuyerQuoteConversionService,
    *,
    city_level: bool,
) -> None:
    if not conversion.available:
        return
    for row in rows:
        metrics = conversion.metrics_for(
            city=row.get("city") if city_level else "",
            brand=row.get("brand"),
            series=row.get("series"),
            fallback=False,
        )
        row["candidate_acquisition_proxy_numerator"] = int(row.get("acquired_count_90d") or 0)
        row["candidate_acquisition_proxy_denominator"] = int(row.get("candidate_count_90d") or 0)
        row["candidate_acquisition_proxy"] = row.get("purchase_conversion_proxy")
        if not metrics:
            row["purchase_conversion_available"] = False
            continue
        row.update(metrics)


def _group_metrics(
    unit_frame: pd.DataFrame,
    group_cols: list[str],
    *,
    as_of: pd.Timestamp,
    window_days: int,
    conversion_horizon_days: int,
) -> list[dict[str, Any]]:
    window_start = as_of - pd.Timedelta(days=window_days)
    mature_cutoff = as_of - pd.Timedelta(days=conversion_horizon_days)
    horizon = pd.Timedelta(days=conversion_horizon_days)
    rows: list[dict[str, Any]] = []
    for key, group in unit_frame.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        payload = {column: value for column, value in zip(group_cols, key)}
        energy_mode = group["energy_type"].mode(dropna=True)
        normal = group[~group["dirty_flag"] & ~group["b2c_disposal_flag"]]
        recent_listed = normal[normal["listed_at"].between(window_start, as_of, inclusive="both")]
        recent_acquired = normal[normal["acquired_at"].between(window_start, as_of, inclusive="both") & normal["is_acquired"]]
        sold = normal[normal["sold_at"].between(window_start, as_of, inclusive="both") & normal["is_sold"]]
        active_candidate = normal[
            normal["listed_at"].between(window_start, as_of, inclusive="both")
            | normal["acquired_at"].between(window_start, as_of, inclusive="both")
            | normal["sold_at"].between(window_start, as_of, inclusive="both")
        ]
        listed_eligible = normal[
            normal["listed_at"].between(window_start, mature_cutoff, inclusive="both") & normal["is_listed"]
        ]
        acquired_eligible = normal[
            normal["acquired_at"].between(window_start, mature_cutoff, inclusive="both") & normal["is_acquired"]
        ]
        listed_sold_in_horizon = listed_eligible[
            listed_eligible["sold_at"].notna()
            & (listed_eligible["sold_at"] >= listed_eligible["listed_at"])
            & (listed_eligible["sold_at"] <= listed_eligible["listed_at"] + horizon)
        ]
        acquired_sold_in_horizon = acquired_eligible[
            acquired_eligible["sold_at"].notna()
            & (acquired_eligible["sold_at"] >= acquired_eligible["acquired_at"])
            & (acquired_eligible["sold_at"] <= acquired_eligible["acquired_at"] + horizon)
        ]
        listed_count = int(len(recent_listed))
        acquired_count = int(len(recent_acquired))
        sold_count = int(len(sold))
        candidate_count = int(len(active_candidate))
        profit_observed = sold[sold["gross_profit"].notna()]
        turnover_observed = sold[sold["turnover_days"].notna()]
        total_gross_profit = _safe_sum(sold["gross_profit"])
        all_recent_acquired = group[group["acquired_at"].between(window_start, as_of, inclusive="both") & group["is_acquired"]]
        payload.update(
            {
                "dominant_energy_type": str(energy_mode.iloc[0]) if not energy_mode.empty else "",
                "candidate_count_90d": candidate_count,
                "acquired_count_90d": acquired_count,
                "listed_count_90d": listed_count,
                "sold_count_90d": sold_count,
                "total_gross_profit": total_gross_profit,
                "purchase_conversion_proxy": _safe_ratio(acquired_count, candidate_count),
                "purchase_conversion_available": False,
                "acquisition_conversion_rate": None,
                "sale_conversion_rate": _safe_ratio(len(listed_sold_in_horizon), len(listed_eligible)),
                "sold_from_acquired_rate": _safe_ratio(len(acquired_sold_in_horizon), len(acquired_eligible)),
                "listed_conversion_numerator": int(len(listed_sold_in_horizon)),
                "listed_conversion_denominator": int(len(listed_eligible)),
                "acquired_conversion_numerator": 0,
                "acquired_conversion_denominator": 0,
                "acquired_sellthrough_numerator": int(len(acquired_sold_in_horizon)),
                "acquired_sellthrough_denominator": int(len(acquired_eligible)),
                "conversion_horizon_days": conversion_horizon_days,
                "avg_gross_profit": _safe_mean(profit_observed["gross_profit"]),
                "median_gross_profit": _safe_median(profit_observed["gross_profit"]),
                "loss_rate": _safe_ratio(float((profit_observed["gross_profit"] <= 0).sum()), len(profit_observed)),
                "profit_observed_count": int(len(profit_observed)),
                "avg_turnover_days": _safe_mean(turnover_observed["turnover_days"]),
                "median_turnover_days": _safe_median(turnover_observed["turnover_days"]),
                "turnover_efficiency_index": _turnover_efficiency(turnover_observed["turnover_days"]),
                "turnover_observed_count": int(len(turnover_observed)),
                "avg_purchase_price": _safe_mean(recent_acquired["purchase_price"]),
                "avg_sale_price": _safe_mean(sold["sale_price"]),
                "dirty_rate": _safe_ratio(float(all_recent_acquired["dirty_flag"].sum()), len(all_recent_acquired)),
                "b2c_disposal_rate": _safe_ratio(float(all_recent_acquired["b2c_disposal_flag"].sum()), len(all_recent_acquired)),
                "sample_quality": "strong" if sold_count >= 20 else "medium" if sold_count >= 5 else "weak",
                "raw_row_count": int(group["raw_row_count"].sum()),
                "unique_unit_count": int(len(group)),
                "metric_as_of": as_of.isoformat(),
                "metric_window_days": window_days,
            }
        )
        rows.append(_clean_payload(payload))
    return rows


def _load_unique_product_frame(path: Path, usecols: list[str]) -> pd.DataFrame:
    unit_cache = CACHE_DIR / f"history_unit_events_v1_{_file_cache_token(path)}.pkl"
    if unit_cache.is_file():
        try:
            cached = pd.read_pickle(unit_cache)
            if isinstance(cached, pd.DataFrame) and not cached.empty:
                return cached
        except Exception:
            pass
    units = pd.DataFrame()
    for chunk in pd.read_csv(path, usecols=lambda column: column in usecols, chunksize=CSV_CHUNK_SIZE, low_memory=False):
        prepared = _prepare_history_chunk(chunk)
        part = _collapse_history_units(prepared)
        units = part if units.empty else _merge_history_units(units, part)
    if units.empty:
        return units
    units["gross_profit"] = units["sale_price"] - units["purchase_price"]
    units.loc[~units["is_sold"] | ~units["is_acquired"], "gross_profit"] = pd.NA
    units["turnover_days"] = (units["sold_at"] - units["listed_at"]).dt.total_seconds() / 86400
    units.loc[(units["turnover_days"] < 0) | (units["turnover_days"] > 180), "turnover_days"] = pd.NA
    units = units[(units["series"] != "") & (units["city"] != "")].reset_index(drop=True)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(units, unit_cache)
    except Exception:
        pass
    return units


def _prepare_history_chunk(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "车源货品ID": "goods_id", "车源商品ID": "product_id", "品牌名称": "brand", "车系名称": "series",
        "能源类型": "energy_type", "车源所在城市": "city", "首次上架时间": "listed_at",
        "首次展板价": "first_listing_price", "收车合同签订时间": "acquired_at", "收车合同价": "purchase_price",
        "最新订单成交价": "sale_price", "已售时间": "sold_at", "是否事故车": "accident", "是否泡水车": "flood",
        "是否火烧车": "fire", "是否调表车": "odometer", "是否B2C处置": "b2c_disposal", "在售状态": "listing_status",
    }
    work = frame.rename(columns=rename).copy()
    for column in rename.values():
        if column not in work.columns:
            work[column] = None
    for column in ("brand", "series", "city", "energy_type", "product_id", "goods_id"):
        work[column] = work[column].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    work["unit_id"] = work["product_id"].where(work["product_id"] != "", work["goods_id"])
    work.loc[work["unit_id"].eq(""), "unit_id"] = "row_" + work.index.astype(str)
    for column in ("purchase_price", "sale_price", "first_listing_price"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    for column in ("listed_at", "acquired_at", "sold_at"):
        work[column] = pd.to_datetime(work[column], errors="coerce")
    work["is_acquired"] = work["purchase_price"].gt(0)
    work["is_sold"] = work["sale_price"].gt(0) & work["sold_at"].notna()
    work["is_listed"] = work["listed_at"].notna() | work["first_listing_price"].gt(0)
    work["dirty_flag"] = False
    for column in ("accident", "flood", "fire", "odometer"):
        work["dirty_flag"] = work["dirty_flag"] | work[column].fillna("").astype(str).str.strip().eq("是")
    work["b2c_disposal_flag"] = work["b2c_disposal"].fillna("").astype(str).str.strip().eq("是")
    work["raw_row_count"] = 1
    return work


def _collapse_history_units(work: pd.DataFrame) -> pd.DataFrame:
    work = work.sort_values(["sold_at", "acquired_at", "listed_at"], na_position="first")
    work["sold_sale_price"] = work["sale_price"].where(work["is_sold"])
    grouped = work.groupby("unit_id", dropna=False)
    return grouped.agg(
        brand=("brand", _last_non_empty), series=("series", _last_non_empty), city=("city", _last_non_empty),
        energy_type=("energy_type", _last_non_empty), listed_at=("listed_at", "min"), acquired_at=("acquired_at", "min"),
        sold_at=("sold_at", "max"), first_listing_price=("first_listing_price", _last_valid_number),
        purchase_price=("purchase_price", _last_valid_number), sale_price=("sold_sale_price", _last_valid_number),
        is_acquired=("is_acquired", "max"), is_listed=("is_listed", "max"), is_sold=("is_sold", "max"),
        dirty_flag=("dirty_flag", "max"), b2c_disposal_flag=("b2c_disposal_flag", "max"), raw_row_count=("raw_row_count", "sum"),
    ).reset_index()


def _merge_history_units(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([left, right], ignore_index=True)
    combined = combined.sort_values(["sold_at", "acquired_at", "listed_at"], na_position="first")
    grouped = combined.groupby("unit_id", dropna=False)
    return grouped.agg(
        brand=("brand", _last_non_empty), series=("series", _last_non_empty), city=("city", _last_non_empty),
        energy_type=("energy_type", _last_non_empty), listed_at=("listed_at", "min"), acquired_at=("acquired_at", "min"),
        sold_at=("sold_at", "max"), first_listing_price=("first_listing_price", _last_valid_number),
        purchase_price=("purchase_price", _last_valid_number), sale_price=("sale_price", _last_valid_number),
        is_acquired=("is_acquired", "max"), is_listed=("is_listed", "max"), is_sold=("is_sold", "max"),
        dirty_flag=("dirty_flag", "max"), b2c_disposal_flag=("b2c_disposal_flag", "max"), raw_row_count=("raw_row_count", "sum"),
    ).reset_index()


def _resolve_as_of(frame: pd.DataFrame) -> pd.Timestamp:
    configured = pd.to_datetime(os.environ.get("SELECTION_HISTORY_AS_OF"), errors="coerce")
    if pd.notna(configured):
        return pd.Timestamp(configured)
    values = [frame[column].max() for column in ("listed_at", "acquired_at", "sold_at") if column in frame.columns]
    valid = [pd.Timestamp(value) for value in values if pd.notna(value)]
    return max(valid) if valid else pd.Timestamp.now()


def _last_non_empty(values: pd.Series) -> str:
    for value in reversed(values.dropna().astype(str).tolist()):
        value = value.strip()
        if value:
            return value
    return ""


def _last_valid_number(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    value = float(numeric.iloc[-1])
    return value if math.isfinite(value) else None


def _aggregate_metric_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}

    def weighted(field: str, weight_field: str = "sold_count_90d") -> float | None:
        total_weight = 0
        total = 0.0
        for row in rows:
            weight = max(1, int(row.get(weight_field) or 0))
            value = _safe_float(row.get(field))
            if value is None:
                continue
            total += value * weight
            total_weight += weight
        return total / total_weight if total_weight else None

    return _clean_payload(
        {
            "row_count": len(rows),
            "candidate_count_90d": sum(int(row.get("candidate_count_90d") or 0) for row in rows),
            "acquired_count_90d": sum(int(row.get("acquired_count_90d") or 0) for row in rows),
            "listed_count_90d": sum(int(row.get("listed_count_90d") or 0) for row in rows),
            "sold_count_90d": sum(int(row.get("sold_count_90d") or 0) for row in rows),
            "total_gross_profit": sum(float(row.get("total_gross_profit") or 0) for row in rows),
            "purchase_conversion_proxy": _safe_ratio(
                sum(int(row.get("acquired_count_90d") or 0) for row in rows),
                sum(int(row.get("candidate_count_90d") or 0) for row in rows),
            ),
            "candidate_acquisition_proxy": _safe_ratio(
                sum(int(row.get("acquired_count_90d") or 0) for row in rows),
                sum(int(row.get("candidate_count_90d") or 0) for row in rows),
            ),
            "purchase_conversion_available": any(bool(row.get("purchase_conversion_available")) for row in rows),
            "acquisition_conversion_rate": _safe_ratio(
                sum(int(row.get("acquired_conversion_numerator") or 0) for row in rows),
                sum(int(row.get("acquired_conversion_denominator") or 0) for row in rows),
            ),
            "sale_conversion_rate": _safe_ratio(
                sum(int(row.get("listed_conversion_numerator") or 0) for row in rows),
                sum(int(row.get("listed_conversion_denominator") or 0) for row in rows),
            ),
            "sold_from_acquired_rate": _safe_ratio(
                sum(int(row.get("acquired_sellthrough_numerator") or 0) for row in rows),
                sum(int(row.get("acquired_sellthrough_denominator") or 0) for row in rows),
            ),
            "listed_conversion_numerator": sum(int(row.get("listed_conversion_numerator") or 0) for row in rows),
            "listed_conversion_denominator": sum(int(row.get("listed_conversion_denominator") or 0) for row in rows),
            "acquired_conversion_numerator": sum(int(row.get("acquired_conversion_numerator") or 0) for row in rows),
            "acquired_conversion_denominator": sum(int(row.get("acquired_conversion_denominator") or 0) for row in rows),
            "acquired_sellthrough_numerator": sum(int(row.get("acquired_sellthrough_numerator") or 0) for row in rows),
            "acquired_sellthrough_denominator": sum(int(row.get("acquired_sellthrough_denominator") or 0) for row in rows),
            "avg_gross_profit": weighted("avg_gross_profit", "profit_observed_count"),
            "median_gross_profit": weighted("median_gross_profit", "profit_observed_count"),
            "loss_rate": weighted("loss_rate", "profit_observed_count"),
            "profit_observed_count": sum(int(row.get("profit_observed_count") or 0) for row in rows),
            "avg_turnover_days": weighted("avg_turnover_days", "turnover_observed_count"),
            "turnover_efficiency_index": weighted("turnover_efficiency_index", "turnover_observed_count"),
            "turnover_observed_count": sum(int(row.get("turnover_observed_count") or 0) for row in rows),
            "avg_sale_price": weighted("avg_sale_price"),
            "conversion_horizon_days": rows[0].get("conversion_horizon_days"),
            "metric_as_of": rows[0].get("metric_as_of"),
            "metric_window_days": rows[0].get("metric_window_days"),
        }
    )


def _price_in_band(value: Any, low: float | None, high: float | None) -> bool:
    price = _safe_float(value)
    if price is None:
        return False
    if low is not None and price < low:
        return False
    if high is not None and price > high:
        return False
    return True


def _safe_mean(series: pd.Series) -> float | None:
    value = pd.to_numeric(series, errors="coerce").dropna().mean()
    return float(value) if pd.notna(value) and math.isfinite(float(value)) else None


def _safe_median(series: pd.Series) -> float | None:
    value = pd.to_numeric(series, errors="coerce").dropna().median()
    return float(value) if pd.notna(value) and math.isfinite(float(value)) else None


def _safe_sum(series: pd.Series) -> float:
    value = pd.to_numeric(series, errors="coerce").fillna(0).sum()
    return float(value) if pd.notna(value) and math.isfinite(float(value)) else 0.0


def _turnover_efficiency(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values >= 0]
    if values.empty:
        return None
    return float((1 / (values + 1)).mean())


def _normalize_energy(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if any(key in text for key in ("新能源", "纯电", "插混", "增程", "电车")):
        return "新能源"
    if any(key in text for key in ("燃油", "油车")):
        return "燃油车"
    return text


def _energy_matches(value: Any, target: str) -> bool:
    normalized = _normalize_energy(value)
    if target == "新能源":
        return normalized == "新能源"
    if target == "燃油车":
        return normalized == "燃油车"
    return target in normalized


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, float):
            out[key] = round(value, 6) if math.isfinite(value) else None
        elif pd.isna(value):
            out[key] = None
        else:
            out[key] = value
    return out


@lru_cache(maxsize=2)
def get_selection_history_metrics_service(csv_path: str = "") -> SelectionHistoryMetricsService:
    return SelectionHistoryMetricsService(csv_path or None)
