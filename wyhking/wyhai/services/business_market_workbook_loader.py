"""Business market workbook loader for market report and selection modules.

This loader intentionally reads only the two online-safe sheets from
``行情状态业务校准.xlsx``.  The two "业务需打标" sheets are human calibration
work queues and must not be used as serving data.
"""

from __future__ import annotations

import math
import base64
import gzip
import io
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .geo_resolver import resolve_city


ROOT = Path(__file__).resolve().parents[1]


def _default_pack_source_dir() -> Path:
    candidates = [
        Path("/Users/bytedance/Downloads/ai_dongchejia_codex_pack/source_files"),
        Path("/Users/bytedance/Desktop/ai_dongchejia_codex_pack/source_files"),
        Path("/Users/bytedance/Desktop/ai_dongchejia_final_premium_pack/source_files"),
    ]
    for candidate in candidates:
        if (candidate / "行情状态业务校准.xlsx").is_file():
            return candidate
    return candidates[0]


PACK_SOURCE_DIR = _default_pack_source_dir()
DEFAULT_WORKBOOK = PACK_SOURCE_DIR / "行情状态业务校准.xlsx"
DEFAULT_DSI_CANDIDATES = [
    Path("/Users/bytedance/Downloads/未保存的查询-2026-07-09 15-35-13.xlsx"),
    PACK_SOURCE_DIR / "DSI供需指数_车款ID.xlsx",
]
DEFAULT_DSI_FILE = next((path for path in DEFAULT_DSI_CANDIDATES if path.is_file()), DEFAULT_DSI_CANDIDATES[-1])
DEFAULT_MODEL_ID_MAP_FILE = PACK_SOURCE_DIR / "车型ID映射_品牌车系车款.xlsx"
SAFE_MODEL_YEAR_SHEET = "无需打标：车型+年款详情数据"
SAFE_CITY_SERIES_SHEET = "无需打标：车系+城市详情数据"
CACHE_DIR = ROOT / "runtime" / "business_market_cache"


CITY_SERIES_COLUMNS = {
    "品牌ID": "brand_id",
    "品牌名称": "brand",
    "车系ID": "series_id",
    "车系名称": "series",
    "城市": "city",
    "7天价格变化率": "price_change_7d",
    "14天价格变化率": "price_change_14d",
    "30天价格变化率": "price_change_30d",
    "45天价格变化率": "price_change_45d",
    "60天价格变化率": "price_change_60d",
    "90天成交样本数": "deal_sample_90d",
    "90天最高成交价": "deal_price_high_90d",
    "90天最低成交价": "deal_price_low_90d",
    "价格波动率": "price_volatility",
    "新车官方指导价": "official_guide_price",
    "上架车源数": "listing_count",
    "成交车源数": "deal_count",
    "平均成交周期": "avg_deal_cycle",
    "上架成交率": "sell_through_rate",
    "当前库存总量": "current_inventory",
    "过去7日销量": "sales_7d",
    "过去15日销量": "sales_15d",
    "过去30日销量": "sales_30d",
    "30天平均清库天数": "avg_clear_days_30d",
    "同车系平台存量": "platform_inventory",
    "同城车源数": "city_listing_count",
    "近7天降价车源数": "price_cut_count_7d",
    "近15天降价车源数": "price_cut_count_15d",
    "近30天降价车源数": "price_cut_count_30d",
    "近30天降价车源占比": "price_cut_rate_30d",
    "库存平均周期": "inventory_cycle",
    "在售平均周期": "active_listing_cycle",
    "平均调价次数": "avg_price_adjustments",
    "留资率": "lead_rate",
    "询价转化率": "inquiry_conversion_rate",
    "收藏数": "favorite_count",
    "当前搜索量": "search_volume",
    "详情页UV": "detail_uv",
    "行情分类": "market_category",
    "分类依据": "category_basis",
    "是否准确": "business_accuracy",
}

MODEL_YEAR_COLUMNS = {
    "品牌ID": "brand_id",
    "品牌名称": "brand",
    "车系ID": "series_id",
    "车系名称": "series",
    "车型": "model",
    "年款": "model_year",
    "聚合名称": "aggregation_name",
    "平均价差": "avg_price_spread",
    "7天价格变化率": "price_change_7d",
    "14天价格变化率": "price_change_14d",
    "30天价格变化率": "price_change_30d",
    "45天价格变化率": "price_change_45d",
    "60天价格变化率": "price_change_60d",
    "90天成交样本数": "deal_sample_90d",
    "90天最高成交价": "deal_price_high_90d",
    "90天最低成交价": "deal_price_low_90d",
    "价格波动率": "price_volatility",
    "新车官方指导价": "official_guide_price",
    "上架车源数": "listing_count",
    "成交车源数": "deal_count",
    "平均成交周期": "avg_deal_cycle",
    "上架成交率": "sell_through_rate",
    "当前库存总量": "current_inventory",
    "过去7日销量": "sales_7d",
    "同车型平台存量": "platform_inventory",
    "近7天降价车源数": "price_cut_count_7d",
    "降价车源占比": "price_cut_rate_7d",
    "库存平均周期": "inventory_cycle",
    "在售平均周期": "active_listing_cycle",
    "平均调价次数": "avg_price_adjustments",
    "留资率": "lead_rate",
    "询价转化率": "inquiry_conversion_rate",
    "收藏数": "favorite_count",
    "当前搜索量": "search_volume",
    "行情分类": "market_category",
    "分类依据": "category_basis",
}


def normalize_text(value: Any) -> str:
    return re.sub(r"[\s\-_/·•（）()，,。.;；:：]+", "", str(value or "")).lower()


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return round(value, 10)
    return value


def _file_cache_token(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{path.stem}_{stat.st_mtime_ns}_{stat.st_size}"
    except OSError:
        return f"{path.stem}_missing"


def percentile(rows: list[dict[str, Any]], field: str, quantile: float) -> float | None:
    values = sorted(
        value for value in (finite_number(row.get(field)) for row in rows)
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


def rank_percentile(rows: list[dict[str, Any]], field: str, value: Any, *, reverse: bool = False) -> float:
    current = finite_number(value)
    values = sorted(
        number for number in (finite_number(row.get(field)) for row in rows)
        if number is not None
    )
    if current is None or not values:
        return 0.5
    less_or_equal = sum(1 for item in values if item <= current)
    pct = less_or_equal / len(values)
    return 1 - pct if reverse else pct


class BusinessMarketWorkbookLoader:
    def __init__(
        self,
        workbook_path: Path | str | None = None,
        dsi_file: Path | str | None = None,
        model_id_map_file: Path | str | None = None,
    ) -> None:
        env_workbook = os.environ.get("MARKET_STATE_XLSX_PATH")
        self.workbook_path = Path(workbook_path or env_workbook or DEFAULT_WORKBOOK)
        self.dsi_file = Path(dsi_file or os.environ.get("DSI_XLSX_PATH") or DEFAULT_DSI_FILE)
        self.model_id_map_file = Path(
            model_id_map_file or os.environ.get("MODEL_ID_MAP_XLSX_PATH") or DEFAULT_MODEL_ID_MAP_FILE
        )
        self.city_series_records: list[dict[str, Any]] = []
        self.model_year_records: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self._dsi_by_model_id: dict[str, str] = {}
        self._model_to_id_rows: list[dict[str, Any]] = []
        self._dsi_by_series: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def available(self) -> bool:
        return bool(self.city_series_records or self.model_year_records)

    @property
    def cities(self) -> list[str]:
        return sorted({str(row.get("city")) for row in self.city_series_records if row.get("city")})

    @property
    def series_names(self) -> list[str]:
        values = {str(row.get("series")) for row in self.city_series_records + self.model_year_records if row.get("series")}
        return sorted(values, key=lambda value: (-len(normalize_text(value)), normalize_text(value), value))

    @property
    def brand_names(self) -> list[str]:
        values = {str(row.get("brand")) for row in self.city_series_records + self.model_year_records if row.get("brand")}
        return sorted(values, key=lambda value: (-len(normalize_text(value)), normalize_text(value), value))

    def _load(self) -> None:
        if not self.workbook_path.is_file():
            self._load_bundled_safe_cache()
            return
        self.city_series_records = self._read_sheet(SAFE_CITY_SERIES_SHEET, CITY_SERIES_COLUMNS)
        self.model_year_records = self._read_sheet(SAFE_MODEL_YEAR_SHEET, MODEL_YEAR_COLUMNS)
        self._load_dsi()
        self.metadata = {
            "source_file": self.workbook_path.name,
            "safe_sheets": [SAFE_MODEL_YEAR_SHEET, SAFE_CITY_SERIES_SHEET],
            "city_series_row_count": len(self.city_series_records),
            "model_year_row_count": len(self.model_year_records),
            "city_count": len(self.cities),
            "series_count": len({row.get("series_id") for row in self.city_series_records if row.get("series_id") is not None}),
            "online_safe": True,
            "forbidden_sheets": ["业务需打标：车型+年款", "业务需打标：车系+城市"],
        }

    @staticmethod
    def _latest_cache_file(prefix: str) -> Path | None:
        """Return the newest prebuilt safe cache shipped with a deployment.

        Cloud runtimes intentionally do not receive the operators' source
        workbooks.  The cache contains the same normalized records produced by
        ``_read_sheet`` and lets the online selection/report path retain its
        evidence without copying workstation-only absolute paths into the
        image.
        """
        try:
            candidates = [
                path
                for pattern in (f"{prefix}*.pkl", f"{prefix}*.pkl.b64", f"{prefix}*.pkl.gz.b64")
                for path in CACHE_DIR.glob(pattern)
                if path.is_file()
            ]
            return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name)) if candidates else None
        except OSError:
            return None

    @staticmethod
    def _read_bundled_pickle(cache_path: Path) -> Any:
        if cache_path.name.endswith(".b64"):
            payload = base64.b64decode(cache_path.read_bytes())
            if cache_path.name.endswith(".gz.b64"):
                payload = gzip.decompress(payload)
            return pd.read_pickle(io.BytesIO(payload))
        return pd.read_pickle(cache_path)

    def _load_bundled_safe_cache(self) -> None:
        cache_specs = (
            (normalize_text(SAFE_CITY_SERIES_SHEET), "city_series_records"),
            (normalize_text(SAFE_MODEL_YEAR_SHEET), "model_year_records"),
        )
        loaded_cache_files: list[str] = []
        for prefix, attribute in cache_specs:
            cache_path = self._latest_cache_file(prefix)
            if cache_path is None:
                continue
            try:
                cached = self._read_bundled_pickle(cache_path)
            except Exception:
                continue
            if isinstance(cached, list):
                setattr(self, attribute, cached)
                loaded_cache_files.append(cache_path.name)

        dsi_cache_path = self._latest_cache_file("dsi_")
        if dsi_cache_path is not None:
            try:
                cached_dsi = self._read_bundled_pickle(dsi_cache_path)
            except Exception:
                cached_dsi = None
            if isinstance(cached_dsi, dict):
                self._dsi_by_model_id = cached_dsi.get("dsi_by_model_id") or {}
                self._model_to_id_rows = cached_dsi.get("model_to_id_rows") or []
                self._dsi_by_series = cached_dsi.get("dsi_by_series") or {}
                loaded_cache_files.append(dsi_cache_path.name)

        if not self.available:
            return
        self.metadata = {
            "source_file": "bundled_online_safe_market_cache",
            "source_workbook_available": False,
            "safe_sheets": [SAFE_MODEL_YEAR_SHEET, SAFE_CITY_SERIES_SHEET],
            "cache_files": loaded_cache_files,
            "city_series_row_count": len(self.city_series_records),
            "model_year_row_count": len(self.model_year_records),
            "city_count": len(self.cities),
            "series_count": len(
                {row.get("series_id") for row in self.city_series_records if row.get("series_id") is not None}
            ),
            "online_safe": True,
            "forbidden_sheets": ["业务需打标：车型+年款", "业务需打标：车系+城市"],
        }

    def _read_sheet(self, sheet_name: str, column_map: dict[str, str]) -> list[dict[str, Any]]:
        cache_path = CACHE_DIR / f"{normalize_text(sheet_name)}_{_file_cache_token(self.workbook_path)}.pkl"
        if cache_path.is_file():
            try:
                cached = pd.read_pickle(cache_path)
                if isinstance(cached, list):
                    return cached
            except Exception:
                pass
        try:
            frame = pd.read_excel(self.workbook_path, sheet_name=sheet_name)
        except Exception:
            return []
        existing_columns = [column for column in column_map if column in frame.columns]
        if not existing_columns:
            return []
        selected = frame[existing_columns].rename(columns={column: column_map[column] for column in existing_columns})
        required = ["brand", "series"]
        if "city" in selected.columns:
            required.append("city")
        selected = selected.dropna(subset=[column for column in required if column in selected.columns]).copy()
        for column in ("brand", "series", "city", "model", "market_category", "category_basis", "business_accuracy"):
            if column in selected.columns:
                selected[column] = selected[column].map(lambda value: str(value).strip() if pd.notna(value) else None)
        records = [
            {column: clean_scalar(value) for column, value in row.items()}
            for row in selected.to_dict(orient="records")
        ]
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(records, cache_path)
        except Exception:
            pass
        return records

    def _load_dsi(self) -> None:
        dsi_cache_path = (
            CACHE_DIR
            / f"dsi_{_file_cache_token(self.dsi_file)}_{_file_cache_token(self.model_id_map_file)}.pkl"
        )
        if dsi_cache_path.is_file():
            try:
                cached = pd.read_pickle(dsi_cache_path)
                if isinstance(cached, dict):
                    self._dsi_by_model_id = cached.get("dsi_by_model_id") or {}
                    self._model_to_id_rows = cached.get("model_to_id_rows") or []
                    self._dsi_by_series = cached.get("dsi_by_series") or {}
                    return
            except Exception:
                pass
        if self.dsi_file.is_file():
            try:
                dsi_frame = pd.read_excel(self.dsi_file)
                self._dsi_by_model_id = {
                    str(int(row["车款id"])): str(row["DSI水平—车型"]).strip()
                    for _, row in dsi_frame.iterrows()
                    if pd.notna(row.get("车款id")) and pd.notna(row.get("DSI水平—车型"))
                }
            except Exception:
                self._dsi_by_model_id = {}
        if self.model_id_map_file.is_file():
            try:
                mapping = pd.read_excel(self.model_id_map_file)
                self._model_to_id_rows = [
                    {
                        "brand": str(row.get("品牌") or "").strip(),
                        "series": str(row.get("车系") or "").strip(),
                        "model": str(row.get("车款") or "").strip(),
                        "model_id": str(int(row.get("车款ID"))),
                    }
                    for _, row in mapping.iterrows()
                    if pd.notna(row.get("车款ID"))
                ]
            except Exception:
                self._model_to_id_rows = []
        series_labels: dict[str, list[str]] = {}
        for row in self._model_to_id_rows:
            model_id = row.get("model_id")
            series_key = normalize_text(row.get("series"))
            if not series_key or model_id not in self._dsi_by_model_id:
                continue
            series_labels.setdefault(series_key, []).append(self._dsi_by_model_id[model_id])
        self._dsi_by_series = {}
        for series_key, labels in series_labels.items():
            label, count = Counter(labels).most_common(1)[0]
            score = {"供不应求": 100, "供需平衡": 70, "供过于求": 30}.get(label, 50)
            self._dsi_by_series[series_key] = {
                "label": label,
                "score": score,
                "sample_count": len(labels),
                "top_count": count,
            }
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(
                {
                    "dsi_by_model_id": self._dsi_by_model_id,
                    "model_to_id_rows": self._model_to_id_rows,
                    "dsi_by_series": self._dsi_by_series,
                },
                dsi_cache_path,
            )
        except Exception:
            pass

    def find_city_in_text(self, text: str) -> str | None:
        resolved = resolve_city(text, self.cities)
        return resolved.city if resolved else None

    def find_series_in_text(self, text: str) -> str | None:
        normalized = normalize_text(text)
        matches = [
            series for series in self.series_names
            if normalize_text(series) and normalize_text(series) in normalized
        ]
        return max(matches, key=len) if matches else None

    def find_brand_in_text(self, text: str) -> str | None:
        normalized = normalize_text(text)
        matches = [
            brand for brand in self.brand_names
            if normalize_text(brand) and normalize_text(brand) in normalized
        ]
        return max(matches, key=len) if matches else None

    def filter_city_series(
        self,
        *,
        city: str | None = None,
        brand: str | None = None,
        series: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: Iterable[dict[str, Any]] = self.city_series_records
        if city and city != "全国":
            rows = (row for row in rows if str(row.get("city")) == city)
        if brand:
            brand_target = normalize_text(brand)
            rows = (row for row in rows if brand_target in normalize_text(row.get("brand")))
        if series:
            series_target = normalize_text(series)
            rows = (row for row in rows if series_target == normalize_text(row.get("series")))
        if keyword:
            keyword_target = normalize_text(keyword)
            rows = (
                row for row in rows
                if keyword_target in normalize_text(row.get("brand"))
                or keyword_target in normalize_text(row.get("series"))
            )
        return list(rows)

    def filter_model_year(
        self,
        *,
        brand: str | None = None,
        series: str | None = None,
        model_year: int | str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: Iterable[dict[str, Any]] = self.model_year_records
        if brand:
            brand_target = normalize_text(brand)
            rows = (row for row in rows if brand_target in normalize_text(row.get("brand")))
        if series:
            series_target = normalize_text(series)
            rows = (row for row in rows if series_target == normalize_text(row.get("series")))
        if model_year not in (None, ""):
            year = str(model_year)
            rows = (row for row in rows if str(row.get("model_year") or "") == year)
        if keyword:
            keyword_target = normalize_text(keyword)
            rows = (
                row for row in rows
                if keyword_target in normalize_text(row.get("brand"))
                or keyword_target in normalize_text(row.get("series"))
                or keyword_target in normalize_text(row.get("model"))
                or keyword_target in normalize_text(row.get("aggregation_name"))
            )
        return list(rows)

    def dsi_for_series(self, series: str | None) -> dict[str, Any]:
        if not series:
            return {"label": "未知", "score": 50, "sample_count": 0}
        target = normalize_text(series)
        result = dict(self._dsi_by_series.get(target) or {"label": "未知", "score": 50, "sample_count": 0})
        result["score"] = {
            "供不应求": 80,
            "供需平衡": 55,
            "供过于求": 50,
        }.get(str(result.get("label") or "未知"), 50)
        return result


@lru_cache(maxsize=4)
def get_business_market_loader(workbook_path: str = "") -> BusinessMarketWorkbookLoader:
    return BusinessMarketWorkbookLoader(Path(workbook_path) if workbook_path else None)
