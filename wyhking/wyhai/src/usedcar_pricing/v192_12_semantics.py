from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


UNKNOWN = "UNKNOWN"
ENERGY_TYPES = {"ICE", "BEV", "PHEV", "HEV", "EREV", UNKNOWN}


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>", "null", "unknown"}:
        return ""
    return text


def compact_text(value: Any) -> str:
    text = _text(value).lower()
    text = (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
        .replace("－", "-")
        .replace("—", "-")
    )
    return re.sub(r"[\s\t\r\n_/\\|,，。:：;；()（）+·]+", "", text)


def _strip_vehicle_prefix(trim: Any, brand: Any = "", series: Any = "") -> tuple[str, list[str]]:
    raw = _text(trim)
    reasons: list[str] = []
    text = raw
    for token in (brand, series):
        token_text = _text(token)
        if token_text and token_text in text:
            text = text.replace(token_text, " ")
            reasons.append("removed_brand_or_series_prefix")
    if re.search(r"(19|20)\d{2}\s*款?", text):
        reasons.append("removed_model_year_prefix")
    text = re.sub(r"(19|20)\d{2}\s*款?", " ", text)
    if re.search(r"(二次改款|中期改款|改款)", text):
        reasons.append("removed_facelift_marker")
    text = re.sub(r"(二次改款|中期改款|改款)", " ", text)
    text = re.sub(r"\b款\b|款$", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, reasons


@dataclass(frozen=True)
class TrimSemantics:
    raw_trim: str
    normalized_trim: str
    canonical_trim_key: str
    canonicalization_reason: str
    canonicalization_confidence: float
    trim_power_code: str
    trim_wheelbase: str
    trim_package: str
    trim_drivetrain: str
    trim_generation_marker: str


def parse_trim_semantics(
    trim: Any,
    *,
    brand: Any = "",
    series: Any = "",
    model_year: Any = None,
) -> TrimSemantics:
    raw = _text(trim)
    stripped, reasons = _strip_vehicle_prefix(raw, brand, series)
    normalized = compact_text(stripped)
    normalized = normalized.replace("ｍ", "m")
    normalized = normalized.replace("ｉ", "i")
    normalized = normalized.replace("ｌ", "l")
    normalized = normalized.replace("ｘ", "x")
    normalized = normalized.replace("运动曜夜套装", "m运动曜夜套装")
    normalized = re.sub(r"(?<!m)运动套装", "m运动套装", normalized)
    normalized = normalized.replace("m运动套", "m运动套装")
    normalized = normalized.replace("曜夜版", "曜夜套装")
    if normalized != compact_text(stripped):
        reasons.append("normalized_package_alias")

    power_code = ""
    wheelbase = ""
    power_match = re.search(r"(?<!\d)(\d{3})(li|i|d|e)?(?!\d)", normalized)
    if power_match:
        power_code = power_match.group(1)
        suffix = power_match.group(2) or ""
        if suffix == "li":
            wheelbase = "long"
        elif suffix == "i":
            wheelbase = "standard"
        elif suffix:
            wheelbase = suffix
        reasons.append("parsed_power_code")
    drivetrain = "xdrive" if "xdrive" in normalized or "四驱" in normalized else ""
    package = ""
    if "曜夜" in normalized:
        package = "m_sport_shadow"
    elif "m运动" in normalized or "运动" in normalized:
        package = "m_sport"
    elif "豪华" in normalized:
        package = "luxury"
    elif "时尚" in normalized:
        package = "fashion"
    elif "领先" in normalized:
        package = "leading"
    generation = ""
    raw_compact = compact_text(raw)
    if "二次改款" in raw_compact:
        generation = "second_facelift"
    elif "改款" in raw_compact:
        generation = "facelift"

    brand_key = compact_text(brand)
    series_key = compact_text(series)
    year = ""
    try:
        if model_year is not None and not pd.isna(model_year):
            year = str(int(float(model_year)))
    except Exception:
        year = ""
    if not year:
        match = re.search(r"(19|20)\d{2}", raw)
        year = match.group(0) if match else ""

    identity_bits = []
    if power_code:
        suffix = "li" if wheelbase == "long" else "i" if wheelbase == "standard" else wheelbase
        identity_bits.append(f"{power_code}{suffix}")
    if package:
        identity_bits.append(package)
    if drivetrain:
        identity_bits.append(drivetrain)
    if not identity_bits and normalized:
        identity_bits.append(normalized)
    canonical = "|".join(bit for bit in [brand_key, series_key, year, *identity_bits] if bit)
    confidence = 0.98 if power_code and package else 0.92 if power_code else 0.75 if normalized else 0.0
    if not raw:
        reasons.append("empty_raw_trim")
    if not canonical:
        canonical = "|".join(bit for bit in [brand_key, series_key, year, normalized] if bit)
    return TrimSemantics(
        raw_trim=raw,
        normalized_trim=normalized,
        canonical_trim_key=canonical,
        canonicalization_reason="|".join(dict.fromkeys(reasons)) or "direct_normalization",
        canonicalization_confidence=float(confidence),
        trim_power_code=power_code,
        trim_wheelbase=wheelbase,
        trim_package=package,
        trim_drivetrain=drivetrain,
        trim_generation_marker=generation,
    )


def canonicalize_trim(
    trim: Any,
    brand: Any = "",
    series: Any = "",
    model_year: Any = None,
) -> dict[str, Any]:
    value = parse_trim_semantics(
        trim,
        brand=brand,
        series=series,
        model_year=model_year,
    )
    return {
        "raw_trim": value.raw_trim,
        "normalized_trim": value.normalized_trim,
        "canonical_trim_key": value.canonical_trim_key,
        "canonicalization_reason": value.canonicalization_reason,
        "canonicalization_confidence": value.canonicalization_confidence,
        "trim_power_code": value.trim_power_code,
        "trim_wheelbase": value.trim_wheelbase,
        "trim_package": value.trim_package,
        "trim_drivetrain": value.trim_drivetrain,
        "trim_generation_marker": value.trim_generation_marker,
    }


def infer_energy_from_text(*values: Any) -> str:
    text = compact_text(" ".join(_text(value) for value in values))
    if not text:
        return UNKNOWN
    if any(token in text for token in ("增程", "erev", "rangeextended")):
        return "EREV"
    if any(token in text for token in ("dmi", "dm-i", "插混", "插电混动", "phev", "e+", "hi4t", "hi4-t")):
        return "PHEV"
    if any(token in text for token in ("纯电", "bev", "ev", "磷酸铁锂", "三元锂", "kwh")):
        return "BEV"
    if any(token in text for token in ("油电混动", "油混", "hev", "双擎", "混合动力")):
        return "HEV"
    if re.search(r"\d{2,4}km", text) and any(token in text for token in ("电", "锂", "续航")):
        return "BEV"
    if re.search(r"(320|325|330|318|520|525|530)(li|i)?", text):
        return "ICE"
    if any(token in text for token in ("宝马3系", "奔驰c", "奥迪a4", "凯美瑞", "雅阁", "朗逸", "轩逸", "速腾")):
        return "ICE"
    return UNKNOWN


def normalize_energy_type(
    value: Any = None,
    *,
    brand: Any = "",
    series: Any = "",
    trim: Any = "",
    is_new_energy: Any = None,
) -> dict[str, Any]:
    raw = _text(value if value is not None else is_new_energy)
    compact = compact_text(raw)
    inferred = infer_energy_from_text(brand, series, trim)
    if compact in {"否", "燃油", "0", "false", "no", "ice", "汽油", "柴油"}:
        return {
            "energy_type": "ICE",
            "energy_normalization_source": "EXPLICIT_ICE_VALUE",
            "energy_normalization_confidence": 1.0,
        }
    if compact in {"纯电", "bev", "ev"}:
        return {
            "energy_type": "BEV",
            "energy_normalization_source": "EXPLICIT_BEV_VALUE",
            "energy_normalization_confidence": 1.0,
        }
    if compact in {"插混", "插电混动", "phev", "dmi", "dm-i"}:
        return {
            "energy_type": "PHEV",
            "energy_normalization_source": "EXPLICIT_PHEV_VALUE",
            "energy_normalization_confidence": 1.0,
        }
    if compact in {"增程", "erev"}:
        return {
            "energy_type": "EREV",
            "energy_normalization_source": "EXPLICIT_EREV_VALUE",
            "energy_normalization_confidence": 1.0,
        }
    if compact in {"油电混动", "油混", "hev", "双擎"}:
        return {
            "energy_type": "HEV",
            "energy_normalization_source": "EXPLICIT_HEV_VALUE",
            "energy_normalization_confidence": 1.0,
        }
    if compact in {"是", "新能源", "1", "true", "yes", "newenergy"}:
        if inferred != UNKNOWN and inferred != "ICE":
            return {
                "energy_type": inferred,
                "energy_normalization_source": "NEW_ENERGY_FLAG_PLUS_TEXT",
                "energy_normalization_confidence": 0.92,
            }
        return {
            "energy_type": UNKNOWN,
            "energy_normalization_source": "NEW_ENERGY_FLAG_WITHOUT_SUBTYPE",
            "energy_normalization_confidence": 0.35,
        }
    if compact in ENERGY_TYPES:
        return {
            "energy_type": compact,
            "energy_normalization_source": "CANONICAL_INPUT",
            "energy_normalization_confidence": 1.0,
        }
    if inferred != UNKNOWN:
        return {
            "energy_type": inferred,
            "energy_normalization_source": "TEXT_SEMANTICS",
            "energy_normalization_confidence": 0.86 if inferred == "ICE" else 0.90,
        }
    return {
        "energy_type": UNKNOWN,
        "energy_normalization_source": "UNRESOLVED",
        "energy_normalization_confidence": 0.0,
    }


def add_v192_12_semantic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    records = [
        canonicalize_trim(
            row.get("trim"),
            row.get("brand"),
            row.get("series"),
            row.get("model_year"),
        )
        for row in result[["trim", "brand", "series", "model_year"]]
        .fillna("")
        .to_dict("records")
    ]
    semantic = pd.DataFrame(records, index=result.index)
    for column in semantic:
        result[column] = semantic[column]
    energy_records = [
        normalize_energy_type(
            row.get("is_new_energy"),
            brand=row.get("brand"),
            series=row.get("series"),
            trim=row.get("trim"),
            is_new_energy=row.get("is_new_energy"),
        )
        for row in result[["is_new_energy", "brand", "series", "trim"]]
        .fillna("")
        .to_dict("records")
    ]
    energy = pd.DataFrame(energy_records, index=result.index)
    result["normalized_energy_type"] = energy["energy_type"]
    result["energy_normalization_source"] = energy["energy_normalization_source"]
    result["energy_normalization_confidence"] = energy[
        "energy_normalization_confidence"
    ]
    return result


def add_v192_12_candidate_similarity(
    frame: pd.DataFrame,
    query: dict[str, Any],
) -> pd.DataFrame:
    result = frame.copy()
    if "canonical_trim_key" not in result:
        result = add_v192_12_semantic_columns(result)
    query_sem = canonicalize_trim(
        query.get("trim"),
        query.get("brand"),
        query.get("series"),
        query.get("model_year"),
    )
    query_key = str(query.get("canonical_trim_key") or query_sem["canonical_trim_key"])
    result["query_canonical_trim_key"] = query_key
    result["query_normalized_trim"] = query.get("normalized_trim") or query_sem[
        "normalized_trim"
    ]
    result["same_trim"] = result["canonical_trim_key"].fillna("").astype(str).eq(query_key).astype(int)
    for field in (
        "trim_power_code",
        "trim_wheelbase",
        "trim_package",
        "trim_drivetrain",
    ):
        q = str(query.get(field) or query_sem.get(field) or "")
        candidate = result[field].fillna("").astype(str) if field in result else pd.Series("", index=result.index)
        result[f"{field}_match"] = (candidate.eq(q) & bool(q)).astype(int)
        result[f"{field}_conflict"] = (
            candidate.ne("")
            & bool(q)
            & candidate.ne(q)
        ).astype(int)
    same_power = result["trim_power_code_match"].eq(1)
    same_pkg = result["trim_package_match"].eq(1) | (
        result.get("trim_package", pd.Series("", index=result.index)).fillna("").astype(str).eq("")
    )
    result["v192_12_semantic_similarity_multiplier"] = np.select(
        [
            result["same_trim"].eq(1),
            same_power & same_pkg,
            same_power,
            result["trim_power_code_conflict"].eq(1),
        ],
        [1.35, 1.16, 1.08, 0.58],
        default=0.92,
    )
    result["v192_12_similarity_reason"] = np.select(
        [
            result["same_trim"].eq(1),
            same_power & same_pkg,
            same_power,
            result["trim_power_code_conflict"].eq(1),
        ],
        [
            "CANONICAL_EXACT_TRIM",
            "SAME_POWER_AND_PACKAGE",
            "SAME_POWER_ADJACENT",
            "POWER_CODE_CONFLICT",
        ],
        default="LOOSE_TRIM_TEXT_MATCH",
    )
    return result
