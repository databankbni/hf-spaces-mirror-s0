"""Shared schemas and strict identity helpers for v195 pricing."""

from __future__ import annotations

from enum import Enum
import hashlib
import math
import re
from typing import Any, Iterable

import pandas as pd


class EvaluationMode(str, Enum):
    CLEAN_ROLLING_EVAL = "CLEAN_ROLLING_EVAL"
    PRODUCTION_DAILY_KNOWLEDGE = "PRODUCTION_DAILY_KNOWLEDGE"
    POST_HOC_ORACLE = "POST_HOC_ORACLE"


class PriceType(str, Enum):
    INTERNAL_C2B_TRANSACTION = "INTERNAL_C2B_TRANSACTION"
    INTERNAL_B2C_TRANSACTION = "INTERNAL_B2C_TRANSACTION"
    INTERNAL_LISTING = "INTERNAL_LISTING"
    DONGCHEDI_LISTING = "DONGCHEDI_LISTING"
    AUTOHOME_LISTING = "AUTOHOME_LISTING"
    GUAZI_LISTING = "GUAZI_LISTING"


class QuoteDecision(str, Enum):
    AUTO_QUOTE = "AUTO_QUOTE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_QUOTE = "NO_QUOTE"


TRUTH_COLUMNS = [
    "source",
    "source_record_id",
    "source_vehicle_id",
    "vehicle_signature",
    "fuzzy_vehicle_signature",
    "strict_identity_key",
    "model_id",
    "source_model_id",
    "series_id",
    "brand",
    "series",
    "trim",
    "trim_normalized",
    "model_year",
    "registration_date",
    "mileage_km",
    "city",
    "transfer_count",
    "color",
    "condition_grade",
    "price",
    "price_type",
    "observed_at",
    "transaction_at",
    "source_confidence",
    "data_quality_flags",
    "eligible_for_transaction_target",
    "eligible_for_clean_eval",
    "eligible_for_online_quote",
    "cross_source_cluster_id",
    "dedup_weight",
]


UNKNOWN_VALUES = {
    "",
    "0",
    "nan",
    "none",
    "null",
    "other",
    "unknown",
    "其它",
    "其他",
    "未知",
    "未识别",
}


def text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def compact(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text(value).lower())


def is_unknown(value: Any) -> bool:
    return compact(value) in UNKNOWN_VALUES


def normalize_trim(value: Any, *, brand: Any = "", series: Any = "") -> str:
    """Normalize a trim while preserving configuration-defining digits.

    The function intentionally does not fuzzy-collapse numeric tokens.  Thus
    525 and 530, or 1.5T and 2.0T, always produce different strict keys.
    """

    raw = text(value).lower()
    match = re.search(r"20\d{2}\s*款", raw)
    if match:
        raw = raw[match.end() :]
    normalized = compact(raw)
    for prefix in (compact(brand), compact(series)):
        if prefix and normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized


def normalize_color(value: Any) -> str:
    normalized = compact(value)
    groups = {
        "白": "WHITE",
        "黑": "BLACK",
        "灰": "GRAY",
        "银": "SILVER",
        "红": "RED",
        "蓝": "BLUE",
        "绿": "GREEN",
        "黄": "YELLOW",
        "橙": "ORANGE",
        "棕": "BROWN",
        "咖啡": "BROWN",
        "紫": "PURPLE",
        "金": "GOLD",
    }
    for token, group in groups.items():
        if token in normalized:
            return group
    return "UNKNOWN"


def mileage_bucket_km(value: Any, bucket_km: int = 5_000) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or float(number) < 0:
        return "UNKNOWN"
    lower = int(math.floor(float(number) / bucket_km) * bucket_km)
    return f"{lower}_{lower + bucket_km}"


def registration_quarter(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "UNKNOWN"
    quarter = ((parsed.month - 1) // 3) + 1
    return f"{parsed.year:04d}Q{quarter}"


def transfer_bucket(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or float(number) < 0:
        return "UNKNOWN"
    count = int(number)
    return str(count) if count <= 2 else "3_PLUS"


def condition_bucket(value: Any) -> str:
    normalized = compact(value).upper()
    if normalized.startswith("A"):
        return "A"
    if normalized.startswith("B"):
        return "B"
    if normalized.startswith("C"):
        return "C"
    return "UNKNOWN"


def price_bucket(value: Any, ratio_step: float = 0.025) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or float(number) <= 0:
        return "UNKNOWN"
    index = int(round(math.log(float(number)) / math.log(1.0 + ratio_step)))
    return str(index)


def registration_month(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "UNKNOWN"
    return f"{parsed.year:04d}-{parsed.month:02d}"


def registration_year(value: Any) -> str:
    raw = text(value)
    match = re.search(r"(19|20)\d{2}", raw)
    if match:
        return match.group(0)
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "UNKNOWN"
    return f"{parsed.year:04d}"


def stable_hash(parts: Iterable[Any], prefix: str) -> str:
    payload = "|".join(text(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def strict_identity_key(
    *,
    model_id: Any,
    brand: Any,
    series: Any,
    trim: Any,
    model_year: Any,
) -> str:
    model_number = pd.to_numeric(model_id, errors="coerce")
    if pd.notna(model_number) and int(model_number) > 0:
        identity = f"MODEL_ID:{int(model_number)}"
    else:
        trim_key = normalize_trim(trim, brand=brand, series=series)
        if not trim_key:
            return ""
        identity = f"TEXT:{compact(brand)}:{compact(series)}:{trim_key}"
    year = pd.to_numeric(model_year, errors="coerce")
    year_key = str(int(year)) if pd.notna(year) and int(year) > 1900 else "UNKNOWN_YEAR"
    return stable_hash([identity, year_key], "identity")


def vehicle_signature(
    *,
    identity_key: Any,
    registration_date: Any,
    mileage_km_value: Any,
    city: Any,
    transfer_count: Any,
    color: Any,
) -> str:
    if not text(identity_key):
        return ""
    transfer = pd.to_numeric(transfer_count, errors="coerce")
    transfer_key = str(int(transfer)) if pd.notna(transfer) and float(transfer) >= 0 else "UNKNOWN"
    return stable_hash(
        [
            identity_key,
            registration_month(registration_date),
            mileage_bucket_km(mileage_km_value),
            compact(city) or "UNKNOWN",
            transfer_key,
            normalize_color(color),
        ],
        "vehicle",
    )


def fuzzy_listing_signature(
    *,
    brand: Any,
    series: Any,
    trim: Any,
    model_year: Any,
    registration_date: Any,
    mileage_km_value: Any,
    city: Any,
    color: Any,
    price: Any,
) -> str:
    """Return a conservative cross-platform duplicate signature.

    It is emitted only when all high-value identity fields are present.  This
    intentionally favors missed duplicates over merging different trims.
    """

    series_key = compact(series)
    trim_key = normalize_trim(trim, brand=brand, series=series)
    year = pd.to_numeric(model_year, errors="coerce")
    registration = registration_year(registration_date)
    mileage = mileage_bucket_km(mileage_km_value)
    city_key = compact(city)
    price_key = price_bucket(price)
    if (
        not series_key
        or not trim_key
        or pd.isna(year)
        or int(year) <= 1900
        or registration == "UNKNOWN"
        or mileage == "UNKNOWN"
        or not city_key
        or price_key == "UNKNOWN"
    ):
        return ""
    return stable_hash(
        [
            series_key,
            trim_key,
            int(year),
            registration,
            mileage,
            city_key,
            price_key,
        ],
        "fuzzy",
    )
