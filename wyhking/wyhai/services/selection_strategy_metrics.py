from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .business_market_workbook_loader import normalize_text
from .buyer_quote_conversion_service import BuyerQuoteConversionService
from .selection_history_metrics_service import SelectionHistoryMetricsService
from .vehicle_taxonomy import get_vehicle_taxonomy_service, normalize_energy


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / "selection_strategy_ablation_cache"
DEFAULT_90D_CSV = Path("/Users/bytedance/Downloads/训练1 （90天）-2026-07-09 15-02-35.csv")


BUSINESS_USECOLS = [
    "车源货品ID",
    "能源类型",
    "品牌名称",
    "车系名称",
    "车型ID",
    "车型",
    "车源所在城市",
    "首次上架时间",
    "首次展板价",
    "收车合同签订时间",
    "收车合同价",
    "最新订单成交价",
    "已售时间",
    "是否B2C处置",
    "在售状态",
]


@dataclass(frozen=True)
class SelectionBusinessDataset:
    frame: pd.DataFrame
    group_frame: pd.DataFrame
    source_path: str
    group_grain: tuple[str, ...]
    metadata: dict[str, Any]


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def safe_divide(numerator: Any, denominator: Any) -> float | None:
    left = safe_float(numerator)
    right = safe_float(denominator)
    if left is None or right is None or right == 0:
        return None
    return left / right


def clean_number(value: Any, digits: int = 6) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return round(number, digits)


DEFAULT_GROUP_GRAIN = ("city", "brand", "series", "price_band", "energy_type", "vehicle_category")


def load_business_dataset(
    csv_path: str | Path | None = None,
    *,
    group_grain: Iterable[str] | None = None,
) -> SelectionBusinessDataset:
    path = Path(csv_path or os.environ.get("SELECTION_90D_CSV_PATH") or DEFAULT_90D_CSV)
    if not path.is_file():
        raise FileNotFoundError(f"selection 90d csv not found: {path}")
    grain = tuple(group_grain or DEFAULT_GROUP_GRAIN)
    grain_token = "_".join(grain)
    cache_path = CACHE_DIR / f"time_aware_unique_v5_true_buyer_conversion_{path.stem}_{path.stat().st_mtime_ns}_{path.stat().st_size}_{grain_token}.pkl"
    if cache_path.is_file():
        cached = pd.read_pickle(cache_path)
        if isinstance(cached, dict) and "frame" in cached and "group_frame" in cached:
            return SelectionBusinessDataset(
                cached["frame"],
                cached["group_frame"],
                str(path),
                tuple(cached.get("group_grain") or grain),
                cached.get("metadata") or {},
            )

    history = SelectionHistoryMetricsService(path)
    history._ensure_loaded()
    if int(history.metadata.get("history_window_days") or 0) != 90:
        raise RuntimeError("selection strategy evaluation requires the latest 90-day window")
    frame = history.unit_events_for_evaluation().copy()
    if frame.empty:
        raise RuntimeError("selection strategy unit-level dataset is empty")
    as_of = pd.Timestamp(history.metadata["as_of"])
    window_start = as_of - pd.Timedelta(days=90)
    conversion_horizon_days = int(history.metadata.get("conversion_horizon_days") or 45)
    mature_cutoff = as_of - pd.Timedelta(days=conversion_horizon_days)
    horizon = pd.Timedelta(days=conversion_horizon_days)
    frame = frame[
        ~frame["dirty_flag"]
        & ~frame["b2c_disposal_flag"]
        & frame["series"].ne("")
        & frame["city"].ne("")
    ].copy()
    frame["recent_listed"] = frame["listed_at"].between(window_start, as_of, inclusive="both") & frame["is_listed"]
    frame["recent_acquired"] = frame["acquired_at"].between(window_start, as_of, inclusive="both") & frame["is_acquired"]
    frame["recent_sold"] = frame["sold_at"].between(window_start, as_of, inclusive="both") & frame["is_sold"]
    frame["listed_conversion_eligible"] = frame["listed_at"].between(window_start, mature_cutoff, inclusive="both") & frame["is_listed"]
    frame["acquired_conversion_eligible"] = frame["acquired_at"].between(window_start, mature_cutoff, inclusive="both") & frame["is_acquired"]
    frame["listed_sold_in_horizon"] = (
        frame["listed_conversion_eligible"]
        & frame["sold_at"].notna()
        & (frame["sold_at"] >= frame["listed_at"])
        & (frame["sold_at"] <= frame["listed_at"] + horizon)
    )
    frame["acquired_sold_in_horizon"] = (
        frame["acquired_conversion_eligible"]
        & frame["sold_at"].notna()
        & (frame["sold_at"] >= frame["acquired_at"])
        & (frame["sold_at"] <= frame["acquired_at"] + horizon)
    )
    active = frame["recent_listed"] | frame["recent_acquired"] | frame["recent_sold"]
    frame = frame[active].copy()
    frame["is_acquired"] = frame["recent_acquired"]
    frame["is_listed"] = frame["recent_listed"]
    frame["is_sold"] = frame["recent_sold"]
    frame["gross_profit"] = (frame["sale_price"] - frame["purchase_price"]).where(frame["recent_sold"])
    frame["days_to_sell"] = ((frame["sold_at"] - frame["listed_at"]).dt.total_seconds() / 86400).where(frame["recent_sold"])
    frame.loc[(frame["days_to_sell"] < 0) | (frame["days_to_sell"] > 180), "days_to_sell"] = pd.NA
    frame["price_for_band"] = frame["purchase_price"].combine_first(frame["first_listing_price"]).combine_first(frame["sale_price"])
    frame["price_band"] = frame["price_for_band"].map(price_band_from_yuan)
    taxonomy = get_vehicle_taxonomy_service()
    taxonomy_rows = []
    for brand, series in frame[["brand", "series"]].drop_duplicates().itertuples(index=False, name=None):
        classified = taxonomy.classify_series(brand=brand, series=series)
        taxonomy_rows.append(
            {
                "brand": brand,
                "series": series,
                "taxonomy_body_type": classified.get("body_type") or "其他",
                "taxonomy_energy_type": classified.get("energy_type") or "",
            }
        )
    taxonomy_frame = pd.DataFrame(taxonomy_rows)
    frame = frame.merge(taxonomy_frame, on=["brand", "series"], how="left")
    frame["vehicle_category"] = frame["taxonomy_body_type"].fillna("其他")
    frame["energy_type"] = frame["energy_type"].map(normalize_energy)
    frame["energy_type"] = frame["energy_type"].where(frame["energy_type"].ne(""), frame["taxonomy_energy_type"].fillna(""))
    for column in ("brand", "series", "city", "energy_type", "price_band", "vehicle_category"):
        frame[f"{column}_key"] = frame[column].map(normalize_text)
    missing_grain = [column for column in grain if column not in frame.columns]
    effective_grain = tuple(column for column in grain if column in frame.columns)
    if not effective_grain:
        effective_grain = ("city", "brand", "series")
    key_columns = [f"{column}_key" if f"{column}_key" in frame.columns else column for column in effective_grain]
    frame["group_key"] = frame[key_columns].astype(str).agg("|".join, axis=1)
    group_frame = _build_group_frame(frame, effective_grain)
    conversion = BuyerQuoteConversionService(as_of=as_of, window_days=90)
    _apply_group_conversion(group_frame, conversion, city_level="city" in effective_grain)
    conversion_columns = [
        "group_key",
        "acquired_conversion_numerator",
        "acquired_conversion_denominator",
        "acquisition_conversion_rate",
        "purchase_conversion_available",
        "acquisition_conversion_metric_name",
        "conversion_scope",
    ]
    frame = frame.merge(group_frame[conversion_columns], on="group_key", how="left")
    frame["conversion_group_weight"] = (~frame.duplicated("group_key", keep="first")).astype(int)
    vehicle_category_coverage = float((frame["vehicle_category"] != "其他").mean()) if len(frame) else 0.0
    metadata = {
        "source_file": path.name,
        "raw_snapshot_row_count": int(history.metadata.get("raw_row_count") or 0),
        "unique_product_count_in_source": int(history.metadata.get("unique_product_count") or 0),
        "active_unique_product_count_90d": int(len(frame)),
        "metric_grain": "unique_product_id",
        "window_start": window_start.isoformat(),
        "window_end": as_of.isoformat(),
        "history_window_days": 90,
        "conversion_horizon_days": conversion_horizon_days,
        "historical_transactions_before_window_used": False,
        "normal_condition_only": True,
        "requested_group_grain": list(grain),
        "effective_group_grain": list(effective_grain),
        "missing_group_grain": missing_grain,
        "price_band_coverage": float(frame["price_band"].ne("").mean()) if len(frame) else 0.0,
        "vehicle_category_coverage": round(vehicle_category_coverage, 6),
        "vehicle_category_method": "vehicle_taxonomy_service",
        "data_quality_notes": [
            "原始快照按车源商品ID优先去重后再计算，避免同一车辆重复计数。",
            "所有计数、利润和已售事件显式限制在最新90天；更早的上架时间仅用于当前已售车辆周转天数。",
            "收车转化率按toc且2号岗定价人员为买手的唯一车源货品计算；分子为最终B2C收车成功车源，按2号岗首次合格定价时间归因。",
            "收进售出率另按45天成熟收车队列计算，只作为库存变现补充指标。",
            "售车转化率使用45天成熟上架队列售出率，避免窗口尾部车辆尚未成熟造成低估。",
        ]
        + ([f"group_grain 字段缺失已降级：{', '.join(missing_grain)}"] if missing_grain else []),
        "buyer_quote_conversion": conversion.metadata,
    }
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        pd.to_pickle({"frame": frame, "group_frame": group_frame, "group_grain": effective_grain, "metadata": metadata}, cache_path)
    except Exception:
        pass
    return SelectionBusinessDataset(frame=frame, group_frame=group_frame, source_path=str(path), group_grain=effective_grain, metadata=metadata)


def _build_group_frame(frame: pd.DataFrame, group_grain: Iterable[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_key, group in frame.groupby("group_key", dropna=False):
        sold = group[group["recent_sold"]]
        listed_count = int(group["recent_listed"].sum())
        acquired_count = int(group["recent_acquired"].sum())
        candidate_count = int(len(group))
        sold_count = int(group["recent_sold"].sum())
        observed_profit = pd.to_numeric(sold["gross_profit"], errors="coerce").dropna()
        total_profit = float(observed_profit.sum()) if not observed_profit.empty else 0.0
        positive_profit_pool = float(observed_profit.clip(lower=0).sum()) if not observed_profit.empty else 0.0
        gross_loss_pool = float(observed_profit.clip(upper=0).sum()) if not observed_profit.empty else 0.0
        listed_conversion_numerator = int(group["listed_sold_in_horizon"].sum())
        listed_conversion_denominator = int(group["listed_conversion_eligible"].sum())
        acquired_sellthrough_numerator = int(group["acquired_sold_in_horizon"].sum())
        acquired_sellthrough_denominator = int(group["acquired_conversion_eligible"].sum())
        row = {
            "group_key": group_key,
            "city": first_non_empty(group["city"]),
            "brand": first_non_empty(group["brand"]),
            "series": first_non_empty(group["series"]),
            "price_band": first_non_empty(group["price_band"]),
            "energy_type": first_non_empty(group["energy_type"]),
            "vehicle_category": first_non_empty(group["vehicle_category"]),
            "city_key": first_non_empty(group["city_key"]),
            "brand_key": first_non_empty(group["brand_key"]),
            "series_key": first_non_empty(group["series_key"]),
            "price_band_key": first_non_empty(group["price_band_key"]),
            "energy_type_key": first_non_empty(group["energy_type_key"]),
            "vehicle_category_key": first_non_empty(group["vehicle_category_key"]),
            "group_grain": "+".join(group_grain),
            "candidate_count": candidate_count,
            "acquired_count": acquired_count,
            "listed_count": listed_count,
            "sold_count": sold_count,
            "total_profit": total_profit,
            "positive_profit_pool": positive_profit_pool,
            "gross_loss_pool": gross_loss_pool,
            "profit_observed_count": int(len(observed_profit)),
            "avg_profit": _series_mean(sold["gross_profit"]),
            "median_profit": _series_median(sold["gross_profit"]),
            "loss_rate": safe_divide(int((observed_profit <= 0).sum()), len(observed_profit)),
            "avg_days_to_sell": _series_mean(sold["days_to_sell"]),
            "listed_conversion_numerator": listed_conversion_numerator,
            "listed_conversion_denominator": listed_conversion_denominator,
            "candidate_acquisition_proxy_numerator": acquired_count,
            "candidate_acquisition_proxy_denominator": candidate_count,
            "candidate_acquisition_proxy": safe_divide(acquired_count, candidate_count),
            "purchase_conversion_proxy": safe_divide(acquired_count, candidate_count),
            "acquired_conversion_numerator": 0,
            "acquired_conversion_denominator": 0,
            "acquisition_conversion_rate": None,
            "purchase_conversion_available": False,
            "acquisition_conversion_metric_name": "buyer_post2_toc_b2c_success_90d",
            "conversion_scope": "unavailable",
            "acquired_sellthrough_numerator": acquired_sellthrough_numerator,
            "acquired_sellthrough_denominator": acquired_sellthrough_denominator,
            "sold_from_acquired_rate": safe_divide(acquired_sellthrough_numerator, acquired_sellthrough_denominator),
            "sales_conversion_rate": safe_divide(listed_conversion_numerator, listed_conversion_denominator),
        }
        row.update(_profit_unit_metrics(row))
        rows.append(row)
    return pd.DataFrame(rows)


def _apply_group_conversion(
    groups: pd.DataFrame,
    conversion: BuyerQuoteConversionService,
    *,
    city_level: bool,
) -> None:
    if groups.empty or not conversion.available:
        return
    for index, row in groups.iterrows():
        metrics = conversion.metrics_for(
            city=row.get("city") if city_level else "",
            brand=row.get("brand"),
            series=row.get("series"),
            fallback=False,
        )
        if not metrics:
            continue
        for field in (
            "acquired_conversion_numerator",
            "acquired_conversion_denominator",
            "acquisition_conversion_rate",
            "purchase_conversion_available",
            "acquisition_conversion_metric_name",
            "conversion_scope",
        ):
            groups.at[index, field] = metrics.get(field)
        groups.at[index, "acquisition_conversion_proxy"] = metrics.get("acquisition_conversion_rate")


def first_non_empty(series: pd.Series) -> str:
    values = series.dropna().astype(str)
    for value in values:
        value = value.strip()
        if value:
            return value
    return ""


def _series_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    number = float(values.mean())
    return number if math.isfinite(number) else None


def _series_median(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    number = float(values.median())
    return number if math.isfinite(number) else None


def _profit_unit_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    total_profit = metrics.get("total_profit") or 0
    return {
        "profit_per_candidate": safe_divide(total_profit, metrics.get("candidate_count")),
        "profit_per_acquired": safe_divide(total_profit, metrics.get("acquired_count")),
        "profit_per_sold": safe_divide(total_profit, metrics.get("sold_count")),
    }


def price_band_from_yuan(value: Any) -> str:
    price = safe_float(value)
    if price is None or price <= 0:
        return ""
    wan = price / 10000
    if wan < 5:
        return "0-5万"
    if wan < 10:
        return "5-10万"
    if wan < 15:
        return "10-15万"
    if wan < 20:
        return "15-20万"
    if wan < 30:
        return "20-30万"
    if wan < 50:
        return "30-50万"
    return "50万以上"


def infer_vehicle_category(series: Any, model_name: Any = "") -> str:
    text = f"{series or ''} {model_name or ''}".lower()
    if any(key in text for key in ("suv", "越野", "揽胜", "卫士", "牧马人")):
        return "SUV"
    if any(key in text for key in ("mpv", "gl8", "奥德赛", "艾力绅", "塞纳", "赛那", "威然", "传祺m8", "极氪009")):
        return "MPV"
    if any(key in text for key in ("跑车", "roadster", "cayman", "boxster", "911", "718", "amg gt")):
        return "跑车"
    if any(key in text for key in ("皮卡", "炮", "ranger", "坦途", "f-150")):
        return "皮卡"
    if any(key in text for key in ("轿车", "三厢", "两厢", "掀背", "sportback", "gt")):
        return "轿车"
    return "其他"


def calculate_metrics_from_frame(
    frame: pd.DataFrame,
    *,
    baseline: dict[str, Any] | None = None,
    selected_prefix: str = "selected",
) -> dict[str, Any]:
    candidate_count = int(len(frame))
    acquired_flag = "recent_acquired" if "recent_acquired" in frame else "is_acquired"
    listed_flag = "recent_listed" if "recent_listed" in frame else "is_listed"
    sold_flag = "recent_sold" if "recent_sold" in frame else "is_sold"
    acquired_count = int(frame[acquired_flag].sum()) if acquired_flag in frame else 0
    listed_count = int(frame[listed_flag].sum()) if listed_flag in frame else 0
    sold_count = int(frame[sold_flag].sum()) if sold_flag in frame else 0
    sold = frame[frame[sold_flag]] if sold_flag in frame else frame.iloc[0:0]
    observed_profit = pd.to_numeric(sold.get("gross_profit"), errors="coerce").dropna() if sold_count else pd.Series(dtype=float)
    total_profit = float(observed_profit.sum()) if not observed_profit.empty else 0.0
    positive_profit_pool = float(observed_profit.clip(lower=0).sum()) if not observed_profit.empty else 0.0
    gross_loss_pool = float(observed_profit.clip(upper=0).sum()) if not observed_profit.empty else 0.0
    listed_conversion_numerator = int(frame["listed_sold_in_horizon"].sum()) if "listed_sold_in_horizon" in frame else sold_count
    listed_conversion_denominator = int(frame["listed_conversion_eligible"].sum()) if "listed_conversion_eligible" in frame else listed_count
    acquired_sellthrough_numerator = int(frame["acquired_sold_in_horizon"].sum()) if "acquired_sold_in_horizon" in frame else sold_count
    acquired_sellthrough_denominator = int(frame["acquired_conversion_eligible"].sum()) if "acquired_conversion_eligible" in frame else acquired_count
    if "group_key" in frame and "acquired_conversion_denominator" in frame:
        conversion_groups = frame.drop_duplicates("group_key", keep="first")
        acquired_conversion_numerator = int(
            pd.to_numeric(conversion_groups["acquired_conversion_numerator"], errors="coerce").fillna(0).sum()
        )
        acquired_conversion_denominator = int(
            pd.to_numeric(conversion_groups["acquired_conversion_denominator"], errors="coerce").fillna(0).sum()
        )
    else:
        acquired_conversion_numerator = acquired_count
        acquired_conversion_denominator = candidate_count
    metrics = {
        "candidate_count": candidate_count,
        "acquired_count": acquired_count,
        "listed_count": listed_count,
        "sold_count": sold_count,
        "total_profit": total_profit,
        "positive_profit_pool": positive_profit_pool,
        "gross_loss_pool": gross_loss_pool,
        "profit_observed_count": int(len(observed_profit)),
        "avg_profit": _series_mean(sold["gross_profit"]) if sold_count and "gross_profit" in sold else None,
        "median_profit": _series_median(sold["gross_profit"]) if sold_count and "gross_profit" in sold else None,
        "loss_rate": safe_divide(int((observed_profit <= 0).sum()), len(observed_profit)),
        "avg_days_to_sell": _series_mean(sold["days_to_sell"]) if sold_count and "days_to_sell" in sold else None,
        "listed_conversion_numerator": listed_conversion_numerator,
        "listed_conversion_denominator": listed_conversion_denominator,
        "candidate_acquisition_proxy_numerator": acquired_count,
        "candidate_acquisition_proxy_denominator": candidate_count,
        "candidate_acquisition_proxy": safe_divide(acquired_count, candidate_count),
        "purchase_conversion_proxy": safe_divide(acquired_count, candidate_count),
        "acquired_conversion_numerator": acquired_conversion_numerator,
        "acquired_conversion_denominator": acquired_conversion_denominator,
        "acquisition_conversion_rate": safe_divide(acquired_conversion_numerator, acquired_conversion_denominator),
        "acquisition_conversion_proxy": safe_divide(acquired_conversion_numerator, acquired_conversion_denominator),
        "acquisition_conversion_metric_name": "buyer_post2_toc_b2c_success_90d",
        "acquired_sellthrough_numerator": acquired_sellthrough_numerator,
        "acquired_sellthrough_denominator": acquired_sellthrough_denominator,
        "sold_from_acquired_rate": safe_divide(acquired_sellthrough_numerator, acquired_sellthrough_denominator),
        "sales_conversion_rate": safe_divide(listed_conversion_numerator, listed_conversion_denominator),
    }
    metrics.update(_profit_unit_metrics(metrics))
    return add_selection_context(metrics, baseline=baseline, selected_prefix=selected_prefix)


def baseline_metrics(dataset: SelectionBusinessDataset) -> dict[str, Any]:
    raw = calculate_metrics_from_frame(dataset.frame, selected_prefix="baseline")
    out = dict(raw)
    mapping = {
        "candidate_count": "baseline_candidate_count",
        "acquired_count": "baseline_acquired_count",
        "sold_count": "baseline_sold_count",
        "total_profit": "baseline_total_profit",
        "positive_profit_pool": "baseline_positive_profit_pool",
        "gross_loss_pool": "baseline_gross_loss_pool",
        "profit_observed_count": "baseline_profit_observed_count",
        "avg_profit": "baseline_avg_profit",
        "median_profit": "baseline_median_profit",
        "loss_rate": "baseline_loss_rate",
        "avg_days_to_sell": "baseline_avg_days_to_sell",
        "acquisition_conversion_rate": "baseline_acquisition_conversion_rate",
        "acquisition_conversion_proxy": "baseline_acquisition_conversion_proxy",
        "acquired_conversion_numerator": "baseline_acquired_conversion_numerator",
        "acquired_conversion_denominator": "baseline_acquired_conversion_denominator",
        "candidate_acquisition_proxy": "baseline_candidate_acquisition_proxy",
        "sales_conversion_rate": "baseline_sales_conversion_rate",
    }
    for source, target in mapping.items():
        out[target] = raw.get(source)
    return clean_metrics(out)


def subset_metrics(
    dataset: SelectionBusinessDataset,
    group_keys: Iterable[str],
    baseline: dict[str, Any],
    *,
    selected_prefix: str = "selected",
) -> dict[str, Any]:
    keys = set(group_keys)
    if not keys:
        empty = dataset.frame.iloc[0:0].copy()
        return calculate_metrics_from_frame(empty, baseline=baseline, selected_prefix=selected_prefix)
    frame = dataset.frame[dataset.frame["group_key"].isin(keys)]
    return calculate_metrics_from_frame(frame, baseline=baseline, selected_prefix=selected_prefix)


def add_selection_context(
    metrics: dict[str, Any],
    *,
    baseline: dict[str, Any] | None,
    selected_prefix: str,
) -> dict[str, Any]:
    out = dict(metrics)
    if baseline:
        baseline_total_profit = baseline.get("baseline_total_profit", baseline.get("total_profit"))
        baseline_positive_profit = baseline.get("baseline_positive_profit_pool", baseline.get("positive_profit_pool"))
        baseline_candidate_count = baseline.get("baseline_candidate_count", baseline.get("candidate_count"))
        out["profit_retention_rate"] = safe_divide(out.get("total_profit"), baseline_total_profit)
        out["positive_profit_capture_rate"] = safe_divide(out.get("positive_profit_pool"), baseline_positive_profit)
        out["selection_rate"] = safe_divide(out.get("candidate_count"), baseline_candidate_count)
    aliases = {
        f"{selected_prefix}_candidate_count": out.get("candidate_count"),
        f"{selected_prefix}_acquired_count": out.get("acquired_count"),
        f"{selected_prefix}_sold_count": out.get("sold_count"),
        f"{selected_prefix}_total_profit": out.get("total_profit"),
    }
    if selected_prefix == "selected":
        aliases["selected_listed_count"] = out.get("listed_count")
    if selected_prefix == "avoid":
        aliases["avoid_candidate_count"] = out.get("candidate_count")
        aliases["avoid_rate"] = out.get("selection_rate")
    out.update(aliases)
    return clean_metrics(out)


def relative_lifts(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    selected_days = metrics.get("avg_days_to_sell")
    baseline_days = baseline.get("baseline_avg_days_to_sell", baseline.get("avg_days_to_sell"))
    return clean_metrics(
        {
            "avg_profit_lift": safe_divide(metrics.get("avg_profit"), baseline.get("baseline_avg_profit", baseline.get("avg_profit"))),
            "total_profit_retention": metrics.get("profit_retention_rate"),
            "days_to_sell_improvement": safe_divide(baseline_days, selected_days),
            "acquisition_conversion_lift": safe_divide(
                metrics.get("acquisition_conversion_rate"),
                baseline.get("baseline_acquisition_conversion_rate", baseline.get("acquisition_conversion_rate")),
            ),
            "sales_conversion_lift": safe_divide(
                metrics.get("sales_conversion_rate"),
                baseline.get("baseline_sales_conversion_rate", baseline.get("sales_conversion_rate")),
            ),
        }
    )


def leader_metric_pass(metrics: dict[str, Any], baseline: dict[str, Any], *, mode: str) -> dict[str, Any]:
    base_days = baseline.get("baseline_avg_days_to_sell")
    base_profit = baseline.get("baseline_avg_profit")
    base_acq = baseline.get("baseline_acquisition_conversion_rate")
    base_sale = baseline.get("baseline_sales_conversion_rate")
    current_days = metrics.get("avg_days_to_sell")
    current_profit = metrics.get("avg_profit")
    current_acq = metrics.get("acquisition_conversion_rate")
    current_sale = metrics.get("sales_conversion_rate")
    if mode == "recommend":
        checks = {
            "avg_days_to_sell": _lte(current_days, _mul(base_days, 0.9)),
            "avg_profit": _gte(current_profit, _mul(base_profit, 1.1)),
            "acquisition_conversion_rate": _gte(current_acq, _mul(base_acq, 1.1)),
            "sales_conversion_rate": _gte(current_sale, _mul(base_sale, 1.1)),
        }
    elif mode == "avoid":
        checks = {
            "avg_days_to_sell": _gte(current_days, _mul(base_days, 1.1)),
            "avg_profit": _lte(current_profit, _mul(base_profit, 0.9)),
            "acquisition_conversion_rate": _lte(current_acq, _mul(base_acq, 0.9)),
            "sales_conversion_rate": _lte(current_sale, _mul(base_sale, 0.9)),
        }
    else:
        raise ValueError(f"unknown leader metric mode: {mode}")
    checks["all_pass"] = all(checks.values())
    return checks


def scale_pass(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    thresholds = config.get("thresholds", {})
    checks = {
        "selection_rate": (metrics.get("selection_rate") or 0) >= float(thresholds.get("min_selection_rate", 0.15)),
        "selected_candidate_count": int(metrics.get("selected_candidate_count") or metrics.get("candidate_count") or 0)
        >= int(thresholds.get("min_selected_count", 30)),
        "profit_retention_rate": (metrics.get("profit_retention_rate") or 0) >= float(thresholds.get("min_profit_retention_rate", 0.30)),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def avoid_scale_pass(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    thresholds = config.get("thresholds", {})
    checks = {
        "avoid_rate": (metrics.get("avoid_rate") or metrics.get("selection_rate") or 0) >= float(thresholds.get("min_avoid_rate", 0.05)),
        "avoid_candidate_count": int(metrics.get("avoid_candidate_count") or metrics.get("candidate_count") or 0)
        >= int(thresholds.get("min_avoid_count", 20)),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def topk_group_keys(group_frame: pd.DataFrame, score_col: str, candidate_count: int) -> list[str]:
    if group_frame.empty or candidate_count <= 0:
        return []
    columns = ["group_key", "candidate_count", score_col]
    ranked = group_frame[columns].copy()
    ranked[score_col] = pd.to_numeric(ranked[score_col], errors="coerce").fillna(0)
    ranked["candidate_count"] = pd.to_numeric(ranked["candidate_count"], errors="coerce").fillna(0)
    ranked = ranked.sort_values(
        [score_col, "candidate_count", "group_key"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    ranked["cum_count"] = ranked["candidate_count"].cumsum()
    selected = ranked[ranked["cum_count"] <= candidate_count]
    if selected.empty:
        selected = ranked.head(1)
    elif int(selected["candidate_count"].sum()) < candidate_count and len(selected) < len(ranked):
        selected = pd.concat([selected, ranked.iloc[[len(selected)]]], ignore_index=True)
    return selected["group_key"].astype(str).tolist()


def clean_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in metrics.items():
        if isinstance(value, bool) or value is None:
            out[key] = value
        elif isinstance(value, int):
            out[key] = value
        elif isinstance(value, float):
            out[key] = round(value, 6) if math.isfinite(value) else None
        elif hasattr(value, "item"):
            out[key] = clean_metrics({key: value.item()})[key]
        else:
            out[key] = value
    return out


def _mul(value: Any, factor: float) -> float | None:
    number = safe_float(value)
    return number * factor if number is not None else None


def _gte(value: Any, threshold: Any) -> bool:
    left = safe_float(value)
    right = safe_float(threshold)
    return bool(left is not None and right is not None and left >= right)


def _lte(value: Any, threshold: Any) -> bool:
    left = safe_float(value)
    right = safe_float(threshold)
    return bool(left is not None and right is not None and left <= right)
