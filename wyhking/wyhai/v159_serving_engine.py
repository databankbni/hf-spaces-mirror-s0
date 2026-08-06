"""v159 latest trusted actual-memory serving engine.

This module is intentionally lightweight for online use:

- Load the daily v159 pricebook into memory.
- Normalize the user's six-factor vehicle input.
- Retrieve the nearest trusted historical actual-memory cluster.
- Return auto single-point quote when the match is sufficiently homogeneous;
  otherwise return interval/manual route with a reason.

Prices exposed through the API are in 万元 to match existing `/api/price`.
Internal pricebook values are yuan.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_PRICEBOOK = ROOT / "knowledge_base/v159_latest_trusted_actual_memory_pricebook.parquet"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return default
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return default
        value = match.group(0)
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    number = _safe_float(value, None)
    if number is None:
        return default
    return int(number)


def _norm(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().lower()
    if text in {"nan", "none", "<na>", "unknown"}:
        return ""
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[\s\t\r\n\u3000]+", "", text)
    return re.sub(r"[·・,，。:：;；/\\|_()（）+\-]", "", text)


def _yuan_to_wan(value: Optional[float]) -> Optional[float]:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value) / 10000.0, 2)


def _parse_date(value: Any) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        text = f"{text}-06-15"
    elif re.fullmatch(r"\d{4}[-/年]\d{1,2}月?", text):
        nums = re.findall(r"\d+", text)
        text = f"{nums[0]}-{int(nums[1]):02d}-15"
    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        return None
    return pd.Timestamp(dt)


def _age_years(reg_date: Any, quote_time: pd.Timestamp, fallback_year: Optional[int]) -> Optional[float]:
    reg = _parse_date(reg_date)
    if reg is None and fallback_year:
        reg = pd.Timestamp(f"{fallback_year}-06-15")
    if reg is None:
        return None
    return max(0.0, float((quote_time - reg).days / 365.25))


@dataclass
class V159Query:
    brand_key: str
    series_key: str
    trim_key: str
    city_key: str
    model_year_int: Optional[int]
    age_years: Optional[float]
    mileage_wan_km: Optional[float]
    transfer_count: Optional[float]
    quote_time: pd.Timestamp


@lru_cache(maxsize=1)
def load_pricebook() -> pd.DataFrame:
    path = Path(os.environ.get("V159_PRICEBOOK_PATH", DEFAULT_PRICEBOOK))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"v159 pricebook missing: {path}")
    frame = pd.read_parquet(path)
    for column in ["brand_key", "series_key", "trim_key", "city_key"]:
        frame[column] = frame[column].map(_norm)
    for column in [
        "model_year_int",
        "age_years",
        "mileage_wan_km",
        "transfer_count",
        "v159_single_point_pred",
        "v159_interval_low",
        "v159_interval_high",
        "v159_selected_level_idx",
        "v159_trusted_cluster_size",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["target_date"] = pd.to_datetime(frame["target_date"], errors="coerce")
    return frame.sort_values("target_date", ascending=False).reset_index(drop=True)


def normalize_query(payload: Dict[str, Any]) -> V159Query:
    quote_time = pd.to_datetime(payload.get("quote_time") or datetime.now(), errors="coerce")
    if pd.isna(quote_time):
        quote_time = pd.Timestamp(datetime.now())
    model_year = (
        _safe_int(payload.get("vehicle_model_year"))
        or _safe_int(payload.get("model_year"))
        or _safe_int(payload.get("modelYear"))
    )
    reg_date = payload.get("reg_date") or payload.get("regDate") or payload.get("first_registration_date")
    reg_year = _safe_int(reg_date)
    age = _safe_float(payload.get("age_years"), None)
    if age is None:
        age = _age_years(reg_date, quote_time, reg_year or model_year)
    mileage = _safe_float(payload.get("mileage_wan_km"), None)
    if mileage is None:
        mileage = _safe_float(payload.get("mileage"), None)
    transfer = _safe_float(payload.get("transfer_count"), None)
    if transfer is None:
        transfer = _safe_float(payload.get("transfer") or payload.get("transferCount"), 0.0)
    return V159Query(
        brand_key=_norm(payload.get("brand") or payload.get("brandName")),
        series_key=_norm(payload.get("series") or payload.get("seriesName")),
        trim_key=_norm(payload.get("model") or payload.get("trim") or payload.get("modelName")),
        city_key=_norm(payload.get("city") or payload.get("cityName")),
        model_year_int=model_year,
        age_years=age,
        mileage_wan_km=mileage,
        transfer_count=transfer,
        quote_time=pd.Timestamp(quote_time),
    )


def _level_codes(query: V159Query, frame: pd.DataFrame) -> pd.Series:
    same_trim = frame["trim_key"].eq(query.trim_key) if query.trim_key else pd.Series(False, index=frame.index)
    if query.trim_key:
        contains_trim = frame["trim_key"].astype(str).str.contains(query.trim_key, regex=False, na=False)
        same_trim = same_trim | contains_trim
    same_year = (
        frame["model_year_int"].eq(query.model_year_int)
        if query.model_year_int is not None
        else pd.Series(False, index=frame.index)
    )
    same_city = frame["city_key"].eq(query.city_key) if query.city_key else pd.Series(False, index=frame.index)
    age_gap = frame["age_years"].sub(query.age_years if query.age_years is not None else frame["age_years"]).abs().fillna(99)
    mileage_gap = frame["mileage_wan_km"].sub(query.mileage_wan_km if query.mileage_wan_km is not None else frame["mileage_wan_km"]).abs().fillna(99)
    close = age_gap.le(1.0) & mileage_gap.le(2.0)
    code = pd.Series(9, index=frame.index, dtype="int16")
    code.loc[same_year] = 7
    code.loc[same_year & close] = 6
    code.loc[same_trim & same_year] = 3
    code.loc[same_trim & same_year & same_city] = 2
    code.loc[same_trim & same_year & close] = 1
    code.loc[same_trim & same_year & same_city & close] = 0
    return code


def _six_factor_adjustment(query: V159Query, row: pd.Series) -> float:
    age_gap = (query.age_years - float(row.get("age_years", query.age_years or 0))) if query.age_years is not None else 0.0
    mileage_gap = (
        query.mileage_wan_km - float(row.get("mileage_wan_km", query.mileage_wan_km or 0))
        if query.mileage_wan_km is not None
        else 0.0
    )
    transfer_gap = (
        query.transfer_count - float(row.get("transfer_count", query.transfer_count or 0))
        if query.transfer_count is not None
        else 0.0
    )
    log_adjust = (
        -0.050 * np.clip(age_gap, -8, 8)
        -0.016 * np.clip(mileage_gap, -20, 20)
        -0.025 * np.clip(transfer_gap, -6, 6)
    )
    return float(np.exp(np.clip(log_adjust, math.log(0.75), math.log(1.25))))


def retrieve_memory(query: V159Query) -> pd.DataFrame:
    book = load_pricebook()
    candidates = book[
        book["brand_key"].eq(query.brand_key)
        & book["series_key"].eq(query.series_key)
        & book["target_date"].lt(query.quote_time)
    ].copy()
    if candidates.empty:
        return candidates
    candidates["serving_level_idx"] = _level_codes(query, candidates)
    candidates["age_gap"] = candidates["age_years"].sub(query.age_years if query.age_years is not None else candidates["age_years"]).abs()
    candidates["mileage_gap"] = candidates["mileage_wan_km"].sub(query.mileage_wan_km if query.mileage_wan_km is not None else candidates["mileage_wan_km"]).abs()
    candidates["transfer_gap"] = candidates["transfer_count"].sub(query.transfer_count if query.transfer_count is not None else candidates["transfer_count"]).abs()
    candidates["year_gap"] = candidates["model_year_int"].sub(query.model_year_int if query.model_year_int is not None else candidates["model_year_int"]).abs()
    candidates["same_city_flag"] = candidates["city_key"].eq(query.city_key).astype(int) if query.city_key else 0
    days_since_memory = (query.quote_time - candidates["target_date"]).dt.total_seconds() / 86400.0
    candidates["memory_days_gap"] = days_since_memory.clip(lower=0).fillna(9999)
    candidates["serving_distance"] = (
        candidates["serving_level_idx"] * 0.62
        + candidates["age_gap"].fillna(8) / 1.25
        + candidates["mileage_gap"].fillna(15) / 2.5
        + candidates["transfer_gap"].fillna(5) * 0.38
        + candidates["year_gap"].fillna(8) * 0.32
        + (1 - candidates["same_city_flag"]) * 0.30
        + np.log1p(candidates["memory_days_gap"]) / 8.0
    )
    return candidates.sort_values(["serving_distance", "memory_days_gap"], ascending=[True, True]).head(50)


def predict_v159_price(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = normalize_query(payload)
    if not query.brand_key or not query.series_key:
        return {
            "modelName": "v159_latest_trusted_cluster",
            "modelVersion": "v159",
            "route": "business_manual_confirm",
            "autoQuote": False,
            "confidence": "no_match",
            "reason": "缺少品牌或车系，无法召回价格手册。",
            "ref_cars": [],
        }
    memory = retrieve_memory(query)
    if memory.empty:
        return {
            "modelName": "v159_latest_trusted_cluster",
            "modelVersion": "v159",
            "route": "business_manual_confirm",
            "autoQuote": False,
            "confidence": "no_match",
            "reason": "价格手册没有同品牌车系可信成交记忆，转人工/补知识库。",
            "ref_cars": [],
        }
    best_distance = float(memory["serving_distance"].min())
    near = memory[memory["serving_distance"].le(best_distance + 1.25)].copy()
    if near.empty:
        near = memory.head(5).copy()
    # Latest trusted item among near-homogeneous matches, but do not let a very
    # weak broad-series row override a close exact/series-year row.
    min_level = int(near["serving_level_idx"].min())
    near_level = near[near["serving_level_idx"].le(min_level + 1)].copy()
    if near_level.empty:
        near_level = near
    selected = near_level.sort_values(["target_date", "serving_distance"], ascending=[False, True]).iloc[0]
    factor = _six_factor_adjustment(query, selected)
    point_yuan = float(selected["v159_single_point_pred"]) * factor
    low_yuan = float(selected.get("v159_interval_low", point_yuan * 0.95)) * factor
    high_yuan = float(selected.get("v159_interval_high", point_yuan * 1.05)) * factor
    if low_yuan > high_yuan:
        low_yuan, high_yuan = high_yuan, low_yuan
    low_yuan = min(low_yuan, point_yuan * 0.98)
    high_yuan = max(high_yuan, point_yuan * 1.02)
    level = int(selected.get("serving_level_idx", 9))
    distance = float(selected.get("serving_distance", 99))
    trusted_size = int(selected.get("v159_trusted_cluster_size") or 1)
    if level <= 7 and distance <= 8.5:
        route = "auto_single_point_quote"
        auto_quote = True
        confidence = "high" if level <= 3 and trusted_size >= 3 else "medium"
        reason = "命中最新可信历史成交簇，并已按车龄/里程/过户做六要素修正。"
    elif level <= 9 and distance <= 12:
        route = "interval_quote"
        auto_quote = False
        confidence = "reference"
        reason = "有同车系价格手册记忆，但同质程度不足，输出区间参考。"
    else:
        route = "business_manual_confirm"
        auto_quote = False
        confidence = "low"
        reason = "价格手册命中较弱，建议人工确认或补充近期成交。"
    ref_cars = []
    for _, row in memory.head(5).iterrows():
        ref_cars.append(
            {
                "query_uid": row.get("query_uid"),
                "brand": row.get("brand_key"),
                "series": row.get("series_key"),
                "model": row.get("trim_key"),
                "model_year": _safe_int(row.get("model_year_int")),
                "city": row.get("city_key"),
                "age_years": _safe_float(row.get("age_years")),
                "mileage_wan_km": _safe_float(row.get("mileage_wan_km")),
                "transfer_count": _safe_float(row.get("transfer_count")),
                "price": _safe_float(row.get("v159_single_point_pred")),
                "price_wan": _yuan_to_wan(_safe_float(row.get("v159_single_point_pred"))),
                "target_date": str(row.get("target_date")),
                "match_level_idx": _safe_int(row.get("serving_level_idx")),
                "distance": round(float(row.get("serving_distance", 0)), 4),
            }
        )
    c2b_wan = _yuan_to_wan(point_yuan)
    c2b_low = _yuan_to_wan(low_yuan)
    c2b_high = _yuan_to_wan(high_yuan)
    b2c_wan = round(c2b_wan * 1.08, 2) if c2b_wan is not None else None
    return {
        "modelName": "v159_latest_trusted_cluster",
        "modelVersion": "v159_latest_trusted_cluster_20260608",
        "route": route,
        "autoQuote": auto_quote,
        "confidence": confidence,
        "c2bPrice": c2b_wan,
        "b2cPrice": b2c_wan,
        "c2b_low": c2b_low,
        "c2b_high": c2b_high,
        "b2c_low": round(c2b_low * 1.08, 2) if c2b_low is not None else None,
        "b2c_high": round(c2b_high * 1.08, 2) if c2b_high is not None else None,
        "c2bPriceYuan": round(point_yuan, 0),
        "c2bLowYuan": round(low_yuan, 0),
        "c2bHighYuan": round(high_yuan, 0),
        "reason": reason,
        "sixFactorAdjustment": round(factor, 4),
        "matchedMemory": {
            "query_uid": selected.get("query_uid"),
            "memory_date": str(selected.get("target_date")),
            "trust_bucket": selected.get("v159_trust_bucket"),
            "trusted_cluster_size": trusted_size,
            "selected_level_idx": level,
            "selected_match_distance": round(distance, 4),
            "selected_option_type": selected.get("v159_selected_option_type"),
            "selected_candidate_uid": selected.get("v159_selected_candidate_uid"),
        },
        "ref_cars": ref_cars,
    }


if __name__ == "__main__":
    sample = {
        "brand": "比亚迪",
        "series": "驱逐舰05",
        "model": "荣耀版DM-i 55KM 豪华型",
        "model_year": 2024,
        "reg_date": "2024-05",
        "mileage": 3.5,
        "transfer": 1,
        "city": "南宁",
    }
    import json

    print(json.dumps(predict_v159_price(sample), ensure_ascii=False, indent=2, default=str))
