from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from .v192_13_semantics import (
    UNKNOWN,
    compact_text,
    infer_energy_from_text as _infer_energy_v13,
    normalize_condition,
    normalize_energy_type as _normalize_energy_v13,
    normalize_year,
    strip_trim_prefix,
    text,
)


CANONICALIZATION_VERSION = "v192_14"
RELATIONSHIP_TABLE_VERSION = "v192_14"


def _first(patterns: list[str], body: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, body, flags=re.I)
        if match:
            return "".join(part for part in match.groups() if part is not None).lower()
    return ""


def infer_energy_from_text(*values: Any) -> str:
    body = compact_text(" ".join(text(value) for value in values))
    if any(token in body for token in ("双擎", "油电混动", "hev", "2.5hg", "2.5hs")):
        return "HEV"
    return _infer_energy_v13(*values)


def normalize_energy_type(
    value: Any = None,
    *,
    brand: Any = "",
    series: Any = "",
    trim: Any = "",
    is_new_energy: Any = None,
) -> dict[str, Any]:
    meta = _normalize_energy_v13(
        value,
        brand=brand,
        series=series,
        trim=trim,
        is_new_energy=is_new_energy,
    )
    strong = infer_energy_from_text(brand, series, trim)
    if strong != UNKNOWN and meta["energy_type"] != strong:
        raw = meta.get("energy_type") or UNKNOWN
        return {
            **meta,
            "energy_type": strong,
            "energy_normalization_source": "V192_14_TEXT_OVERRIDES_RAW_FIELD",
            "energy_normalization_confidence": 0.64
            if raw != UNKNOWN
            else 0.92,
            "energy_field_conflict_flag": int(raw != UNKNOWN),
            "energy_field_conflict_reason": ""
            if raw == UNKNOWN
            else f"raw={raw};text={strong}",
        }
    return meta


@dataclass(frozen=True)
class CanonicalTrimV19214:
    raw_trim: str
    normalized_trim: str
    canonical_trim_key: str
    brand_key: str
    series_key: str
    model_year_key: str
    generation: str
    energy_type: str
    displacement: str
    power_code: str
    engine_code: str
    transmission: str
    drivetrain: str
    wheelbase_type: str
    body_type: str
    seat_count: str
    battery_or_range_version: str
    trim_grade: str
    facelift_stage: str
    canonicalization_confidence: float
    canonicalization_reason: str
    canonicalization_version: str = CANONICALIZATION_VERSION


def _parse_drivetrain(norm: str) -> str:
    if any(token in norm for token in ("xdrive", "quattro", "4matic", "四驱", "awd", "4wd")):
        return "awd"
    if any(token in norm for token in ("前驱", "后驱", "两驱", "rwd", "fwd")):
        return "2wd"
    # Porsche 911 "Targa 4"/"Carrera 4" style.
    if re.search(r"(targa|carrera|turbo)4s?", norm):
        return "awd"
    return ""


def _parse_body(norm: str) -> str:
    if any(token in norm for token in ("cabrio", "cabriolet", "敞篷")):
        return "cabriolet"
    if "targa" in norm:
        return "targa"
    if any(token in norm for token in ("sportturismo", "sport turismo", "猎装")):
        return "sport_turismo"
    if any(token in norm for token in ("touring", "旅行", "avant")):
        return "touring"
    if any(token in norm for token in ("sportback", "两厢")):
        return "sportback"
    if any(token in norm for token in ("limousine", "三厢")):
        return "limousine"
    if any(token in norm for token in ("coupe", "轿跑")):
        return "coupe"
    if "五门" in norm:
        return "five_door"
    if "三门" in norm:
        return "three_door"
    return ""


def _parse_grade(norm: str) -> str:
    grade_patterns = [
        ("m_sport_shadow", ("m运动曜夜", "曜夜", "黑标")),
        ("m_sport", ("m运动", "运动套装", "运动版")),
        ("sline", ("sline", "s-line")),
        ("design", ("致雅", "雅致")),
        ("dynamic", ("动感",)),
        ("luxury", ("豪华", "旗舰", "尊贵", "尊享", "至尊", "荣享", "享")),
        ("comfort", ("舒适", "舒享")),
        ("elite", ("精英", "领先")),
        ("fashion", ("时尚",)),
        ("premium", ("臻享", "智享", "智联", "星空满逸")),
        ("entry", ("进取", "低配", "入门", "都市")),
    ]
    for label, tokens in grade_patterns:
        if any(token in norm for token in tokens):
            return label
    return _first([r"(pro|max|plus|you|we|me|lite|ultra|one|cooper|carrera|targa|turbo|gt3)"], norm)


def canonicalize_trim(
    trim: Any,
    brand: Any = "",
    series: Any = "",
    model_year: Any = None,
    *,
    model_id: Any = "",
    energy_value: Any = None,
) -> dict[str, Any]:
    raw = text(trim)
    body = strip_trim_prefix(raw, brand, series)
    norm = compact_text(body)
    raw_norm = compact_text(raw)
    brand_key = compact_text(brand) or f"brand_missing_{compact_text(model_id)}"
    series_key = compact_text(series) or f"series_missing_{compact_text(model_id)}"
    year = normalize_year(model_year, raw)
    energy = normalize_energy_type(
        energy_value,
        brand=brand,
        series=series,
        trim=raw,
        is_new_energy=energy_value,
    )["energy_type"]

    facelift = ""
    if "二次改款" in raw_norm or "改款二" in raw_norm:
        facelift = "second_facelift"
    elif "中期改款" in raw_norm or "改款" in raw_norm:
        facelift = "facelift"

    displacement = _first([r"(\d\.\d)\s*[lt]", r"(\d\.\d)(?=gdit|tsi|tdi|tfsi)"], norm)
    transmission = ""
    if any(token in norm for token in ("手动", "mt")):
        transmission = "manual"
    elif "cvt" in norm:
        transmission = "cvt"
    elif any(token in norm for token in ("dsg", "双离合", "dct")):
        transmission = "dct"
    elif any(token in norm for token in ("自动", "at", "手自一体")):
        transmission = "automatic"

    power_code = _first(
        [
            r"xdrive(25|28|30|40|50)(i|e)?",
            r"(?<!\d)(25|28|30)(i|e)(?![a-z0-9])",
            r"(?<!\d)(320|325|330|318|520|525|530|535)(li|i|d|e)?(?!\d)",
            r"(?<!\d)(35|40|45|50|55)\s*(tfsi|tdi)(?![a-z0-9])",
            r"(?<!\d)(180|200|280|330|380|530)\s*(tsi|tdi)(?![a-z0-9])",
            r"(?<!\d)(2\.0g|2\.5g|2\.5hg|2\.5hs)(?![a-z0-9])",
            r"(?<!\d)(1\.5t|2\.0t|2\.4l|1\.5l|1\.6l|2\.0l|2\.5l|2\.9t|3\.0t|3\.6l|4\.0t)(?![a-z0-9])",
        ],
        norm,
    )
    if not power_code:
        if "coopers" in norm:
            power_code = "cooper_s"
        elif "cooper" in norm:
            power_code = "cooper"
        elif re.search(r"(?<![a-z])one(?![a-z])", norm):
            power_code = "one"
        elif "targa" in norm:
            power_code = "targa"
        elif "carrera" in norm:
            power_code = "carrera"
        elif "turbo" in norm:
            power_code = "turbo"
        elif "gt3" in norm:
            power_code = "gt3"

    engine_code = power_code or displacement
    drivetrain = _parse_drivetrain(norm)
    wheelbase = ""
    if re.search(r"\d{3}li", norm) or "长轴" in norm or "l版" in norm or "行政加长" in norm:
        wheelbase = "long"
    elif re.search(r"\d{3}i", norm) or "标轴" in norm:
        wheelbase = "standard"
    body_type = _parse_body(norm)
    seat_count = _first([r"(\d)座"], norm)
    battery_range = _first([r"(\d{2,4})\s*km", r"(\d{2,4})km", r"(\d+(?:\.\d+)?)kwh"], norm)
    if "磷酸铁锂" in norm:
        battery_range = f"{battery_range}_lfp" if battery_range else "lfp"
    elif "三元锂" in norm:
        battery_range = f"{battery_range}_ternary" if battery_range else "ternary"
    grade = _parse_grade(norm)
    generation = ""

    fields = [
        brand_key,
        series_key,
        year,
        generation,
        energy if energy != UNKNOWN else "",
        displacement,
        power_code,
        engine_code if engine_code != power_code else "",
        transmission,
        drivetrain,
        wheelbase,
        body_type,
        seat_count,
        battery_range,
        grade,
        facelift,
    ]
    semantic_parts = [
        energy if energy != UNKNOWN else "",
        displacement,
        power_code,
        engine_code,
        transmission,
        drivetrain,
        wheelbase,
        body_type,
        seat_count,
        battery_range,
        grade,
        facelift,
    ]
    if not any(semantic_parts) and norm:
        fields.append(norm)
    key = "|".join(str(part) for part in fields if part)
    known = sum(1 for part in semantic_parts if part)
    confidence = 0.99 if known >= 3 else 0.94 if known >= 2 else 0.84 if known == 1 else 0.70 if norm else 0.0
    reasons = []
    for label, value in [
        ("brand_series_year_preserved", brand_key and series_key and year),
        ("energy_preserved", energy != UNKNOWN),
        ("displacement_preserved", displacement),
        ("power_code_preserved", power_code),
        ("transmission_preserved", transmission),
        ("drivetrain_preserved", drivetrain),
        ("wheelbase_preserved", wheelbase),
        ("body_type_preserved", body_type),
        ("seat_count_preserved", seat_count),
        ("battery_or_range_preserved", battery_range),
        ("trim_grade_preserved", grade),
        ("facelift_preserved", facelift),
        ("fallback_normalized_trim_preserved", not any(semantic_parts) and norm),
    ]:
        if value:
            reasons.append(label)
    parsed = CanonicalTrimV19214(
        raw_trim=raw,
        normalized_trim=norm,
        canonical_trim_key=key,
        brand_key=brand_key,
        series_key=series_key,
        model_year_key=year,
        generation=generation,
        energy_type=energy,
        displacement=displacement,
        power_code=power_code,
        engine_code=engine_code,
        transmission=transmission,
        drivetrain=drivetrain,
        wheelbase_type=wheelbase,
        body_type=body_type,
        seat_count=seat_count,
        battery_or_range_version=battery_range,
        trim_grade=grade,
        facelift_stage=facelift,
        canonicalization_confidence=confidence,
        canonicalization_reason="|".join(reasons) or "insufficient_trim_semantics",
    )
    result = asdict(parsed)
    # Backward-compatible column names consumed by existing retrieval code.
    result.update(
        {
            "parsed_powertrain": power_code or engine_code or displacement,
            "parsed_transmission": transmission,
            "parsed_drivetrain": drivetrain,
            "parsed_energy": energy,
            "parsed_body": body_type,
            "parsed_generation": generation,
            "parsed_displacement": displacement,
            "parsed_engine": engine_code,
            "parsed_wheelbase": wheelbase,
            "parsed_seat_count": seat_count,
            "parsed_range_battery": battery_range,
            "parsed_config_grade": grade,
            "parsed_facelift": facelift,
            "trim_power_code": power_code or engine_code or displacement,
            "trim_wheelbase": wheelbase,
            "trim_package": grade,
            "trim_drivetrain": drivetrain,
            "trim_generation_marker": generation or facelift,
        }
    )
    return result


def add_v192_14_semantic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    required = ["trim", "brand", "series", "model_year", "model_id", "is_new_energy"]
    for column in required:
        if column not in result:
            result[column] = ""
    records = [
        canonicalize_trim(
            row.get("trim"),
            row.get("brand"),
            row.get("series"),
            row.get("model_year"),
            model_id=row.get("model_id"),
            energy_value=row.get("is_new_energy"),
        )
        for row in result[required].fillna("").to_dict("records")
    ]
    parsed = pd.DataFrame(records, index=result.index)
    for column in parsed.columns:
        result[column] = parsed[column]
    energy_records = [
        normalize_energy_type(
            row.get("is_new_energy"),
            brand=row.get("brand"),
            series=row.get("series"),
            trim=row.get("trim"),
            is_new_energy=row.get("is_new_energy"),
        )
        for row in result[["is_new_energy", "brand", "series", "trim"]].fillna("").to_dict("records")
    ]
    energy = pd.DataFrame(energy_records, index=result.index)
    result["energy_type"] = energy["energy_type"]
    result["normalized_energy_type"] = energy["energy_type"]
    result["energy_normalization_source"] = energy["energy_normalization_source"]
    result["energy_normalization_confidence"] = energy["energy_normalization_confidence"]
    result["energy_field_conflict_flag"] = energy.get("energy_field_conflict_flag", 0)
    result["energy_field_conflict_reason"] = energy.get("energy_field_conflict_reason", "")
    condition_required = [
        "condition_risk_level",
        "inspection_grade",
        "is_accident",
        "is_flood",
        "is_fire",
        "is_odometer_abnormal",
    ]
    for column in condition_required:
        if column not in result:
            result[column] = ""
    condition_records = [
        normalize_condition(
            row.get("condition_risk_level"),
            inspection_grade=row.get("inspection_grade"),
            accident=row.get("is_accident"),
            flood=row.get("is_flood"),
            fire=row.get("is_fire"),
            odometer=row.get("is_odometer_abnormal"),
        )
        for row in result[condition_required].fillna("").to_dict("records")
    ]
    condition = pd.DataFrame(condition_records, index=result.index)
    result["condition_source_v192_14"] = condition["condition_source_v192_13"]
    result["condition_risk_level_v192_14"] = condition["condition_risk_level_v192_13"]
    return result
