from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd


UNKNOWN = "UNKNOWN"
ENERGY_TYPES = {"ICE", "BEV", "PHEV", "HEV", "EREV", UNKNOWN}
CANONICALIZATION_VERSION = "v192_13_canonical_key_v1"
RELATIONSHIP_TABLE_VERSION = "v192_13_relationship_table_v1"


def text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    raw = str(value).strip()
    if raw.lower() in {"nan", "none", "null", "<na>", "unknown"}:
        return ""
    return raw


def compact_text(value: Any) -> str:
    raw = text(value).lower()
    raw = (
        raw.replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
        .replace("－", "-")
        .replace("—", "-")
        .replace("＋", "+")
        .replace("ｍ", "m")
        .replace("ｉ", "i")
        .replace("ｌ", "l")
        .replace("ｘ", "x")
    )
    return re.sub(r"[\s\t\r\n_/\\|,，。:：;；()（）+·]+", "", raw)


def normalize_year(value: Any, fallback_text: Any = "") -> str:
    for candidate in (value, fallback_text):
        raw = text(candidate)
        if not raw:
            continue
        try:
            numeric = int(float(raw))
            if 1990 <= numeric <= 2035:
                return str(numeric)
        except Exception:
            pass
        match = re.search(r"(19|20)\d{2}", raw)
        if match:
            return match.group(0)
    return ""


def infer_energy_from_text(*values: Any) -> str:
    body = compact_text(" ".join(text(value) for value in values))
    if not body:
        return UNKNOWN
    if any(token in body for token in ("增程", "erev", "rangeextended")):
        return "EREV"
    if any(token in body for token in ("dmi", "dm-i", "dm", "插混", "插电混动", "phev", "e+", "hi4t", "hi4-t", "hi4")):
        return "PHEV"
    if any(token in body for token in ("纯电", "bev", "ev", "磷酸铁锂", "三元锂", "kwh", "电池")):
        return "BEV"
    if any(token in body for token in ("油电混动", "油混", "hev", "双擎", "混合动力", "混动")):
        return "HEV"
    if re.search(r"\d{2,4}km", body) and any(token in body for token in ("电", "锂", "续航", "海鸥", "miniev", "lumin", "熊猫", "乖帅虎")):
        return "BEV"
    if any(token in body for token in ("汽油", "柴油", "燃油")):
        return "ICE"
    # Common ICE families with ambiguous source flags.
    if any(token in body for token in ("宝马3系", "奔驰c", "奥迪a4", "凯美瑞", "雅阁", "朗逸", "轩逸", "速腾", "英朗", "君威")):
        return "ICE"
    if re.search(r"(?<!\d)(318|320|325|330|520|525|530|35|40|45)(li|i|tfsi)?(?!\d)", body):
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
    raw = text(value if value is not None else is_new_energy)
    raw_compact = compact_text(raw)
    inferred = infer_energy_from_text(brand, series, trim)
    explicit: str | None = None
    source = "UNRESOLVED"
    confidence = 0.0
    if raw_compact in {"否", "燃油", "燃油车", "0", "false", "no", "ice", "汽油", "柴油"}:
        explicit, source, confidence = "ICE", "EXPLICIT_ICE_VALUE", 1.0
    elif raw_compact in {"纯电", "bev", "ev"}:
        explicit, source, confidence = "BEV", "EXPLICIT_BEV_VALUE", 1.0
    elif raw_compact in {"插混", "插电混动", "phev", "dmi", "dm-i", "dm"}:
        explicit, source, confidence = "PHEV", "EXPLICIT_PHEV_VALUE", 1.0
    elif raw_compact in {"增程", "erev"}:
        explicit, source, confidence = "EREV", "EXPLICIT_EREV_VALUE", 1.0
    elif raw_compact in {"油电混动", "油混", "hev", "双擎", "混动"}:
        explicit, source, confidence = "HEV", "EXPLICIT_HEV_VALUE", 1.0
    elif raw_compact in {"是", "新能源", "1", "true", "yes", "newenergy"}:
        if inferred in {"BEV", "PHEV", "HEV", "EREV"}:
            explicit, source, confidence = inferred, "NEW_ENERGY_FLAG_PLUS_TEXT", 0.92
        else:
            explicit, source, confidence = UNKNOWN, "NEW_ENERGY_FLAG_WITHOUT_SUBTYPE", 0.35
    elif raw_compact.upper() in ENERGY_TYPES:
        explicit, source, confidence = raw_compact.upper(), "CANONICAL_INPUT", 1.0
    elif inferred != UNKNOWN:
        explicit, source, confidence = inferred, "TEXT_SEMANTICS", 0.88 if inferred == "ICE" else 0.92
    else:
        explicit = UNKNOWN

    conflict = (
        explicit not in {None, UNKNOWN}
        and inferred not in {UNKNOWN, explicit}
    )
    if conflict:
        return {
            "energy_type": inferred,
            "energy_normalization_source": "TEXT_OVERRIDES_CONFLICTING_RAW_FIELD",
            "energy_normalization_confidence": 0.62,
            "energy_field_conflict_flag": 1,
            "energy_field_conflict_reason": f"raw={explicit};text={inferred}",
            "raw_energy_value": raw,
        }
    return {
        "energy_type": explicit or UNKNOWN,
        "energy_normalization_source": source,
        "energy_normalization_confidence": confidence,
        "energy_field_conflict_flag": 0,
        "energy_field_conflict_reason": "",
        "raw_energy_value": raw,
    }


def normalize_condition(value: Any, *, inspection_grade: Any = "", accident: Any = "", flood: Any = "", fire: Any = "", odometer: Any = "") -> dict[str, Any]:
    risk_text = compact_text(" ".join(text(v) for v in (value, inspection_grade, accident, flood, fire, odometer)))
    grade = text(inspection_grade).upper()
    yes_values = {"是", "1", "true", "yes", "有"}
    major = (
        text(accident) in yes_values
        or text(flood) in yes_values
        or text(fire) in yes_values
        or text(odometer) in yes_values
        or grade in {"D", "E"}
        or any(token in risk_text for token in ("事故", "泡水", "火烧", "调表", "重大"))
    )
    if major:
        return {"condition_risk_level_v192_13": "MAJOR_RISK", "condition_source_v192_13": "INSPECTION_CONFIRMED" if grade else "RISK_FLAG_CONFIRMED"}
    if grade in {"A", "B"}:
        return {"condition_risk_level_v192_13": "clean", "condition_source_v192_13": "INSPECTION_CONFIRMED"}
    if grade == "C":
        return {"condition_risk_level_v192_13": "minor_defect", "condition_source_v192_13": "INSPECTION_CONFIRMED"}
    raw = compact_text(value)
    if raw in {"用户确认良好", "用户确认精品", "userconfirmedgood"}:
        return {"condition_risk_level_v192_13": "clean", "condition_source_v192_13": "USER_CONFIRMED_GOOD_CONDITION"}
    if raw in {"clean", "良好", "精品", "good", "systemdefaultgood"}:
        return {"condition_risk_level_v192_13": "clean", "condition_source_v192_13": "SYSTEM_DEFAULT_GOOD_CONDITION"}
    if raw in {"unknown", "missing", "不详", "未知", ""}:
        return {"condition_risk_level_v192_13": "unknown", "condition_source_v192_13": "UNKNOWN"}
    return {"condition_risk_level_v192_13": text(value) or "unknown", "condition_source_v192_13": "SYSTEM_DEFAULT_GOOD_CONDITION" if raw == "clean" else "UNKNOWN"}


def strip_trim_prefix(trim: Any, brand: Any = "", series: Any = "") -> str:
    raw = text(trim)
    body = raw
    for token in sorted((text(brand), text(series)), key=len, reverse=True):
        token_text = text(token)
        if token_text:
            body = body.replace(token_text, " ")
    body = re.sub(r"(19|20)\d{2}\s*款?", " ", body)
    body = re.sub(r"\b款\b|款$", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def _first_match(patterns: list[str], body: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, body, flags=re.I)
        if match:
            return "".join(group for group in match.groups() if group is not None).lower()
    return ""


@dataclass(frozen=True)
class CanonicalTrim:
    raw_trim: str
    normalized_trim: str
    canonical_trim_key: str
    parsed_powertrain: str
    parsed_transmission: str
    parsed_drivetrain: str
    parsed_energy: str
    parsed_body: str
    parsed_generation: str
    parsed_displacement: str
    parsed_engine: str
    parsed_wheelbase: str
    parsed_seat_count: str
    parsed_range_battery: str
    parsed_config_grade: str
    parsed_facelift: str
    canonicalization_confidence: float
    canonicalization_reason: str
    canonicalization_version: str = CANONICALIZATION_VERSION


def canonicalize_trim(trim: Any, brand: Any = "", series: Any = "", model_year: Any = None, *, model_id: Any = "", energy_value: Any = None) -> dict[str, Any]:
    raw = text(trim)
    body = strip_trim_prefix(raw, brand, series)
    norm = compact_text(body)
    raw_norm = compact_text(raw)
    year = normalize_year(model_year, raw)
    brand_key = compact_text(brand) or f"brand_missing_{compact_text(model_id)}"
    series_key = compact_text(series) or f"series_missing_{compact_text(model_id)}"

    generation = ""
    facelift = ""
    if "二次改款" in raw_norm:
        facelift = "second_facelift"
    elif "中期改款" in raw_norm or "改款" in raw_norm:
        facelift = "facelift"

    displacement = _first_match([r"(\d\.\d)\s*[lt]", r"(\d\.\d)(?=gdit|tsi|tdi)"], norm)
    turbo = "t" if re.search(r"\d\.\d\s*t|tsi|tfsi|gdit|涡轮", norm, flags=re.I) else ""
    engine = _first_match(
        [
            r"(?<!\d)(\d{3})(li|i|d|e)?(?!\d)",
            r"(?<!\d)(35|40|45|50|55)\s*(tfsi|tdi)(?![a-z0-9])",
            r"(?<!\d)(180|200|280|330|380|530)\s*(tsi|tdi)(?![a-z0-9])",
            r"(?<!\d)(1\.5t|2\.0t|1\.5l|1\.6l|2\.0l|2\.5l)(?![a-z0-9])",
            r"(?<!\d)(2\.0g|2\.5g|2\.5hg|2\.5hs)(?![a-z0-9])",
        ],
        norm,
    )
    if displacement and turbo and not engine:
        engine = f"{displacement}{turbo}"
    powertrain = engine or displacement

    transmission = ""
    if any(token in norm for token in ("手动", "mt")):
        transmission = "manual"
    elif any(token in norm for token in ("自动", "at", "cvt", "dsg", "双离合", "手自一体")):
        if "cvt" in norm:
            transmission = "cvt"
        elif "dsg" in norm or "双离合" in norm:
            transmission = "dct"
        else:
            transmission = "automatic"

    drivetrain = ""
    if any(token in norm for token in ("四驱", "awd", "4wd", "xdrive", "quattro")):
        drivetrain = "awd"
    elif any(token in norm for token in ("两驱", "前驱", "后驱", "rwd", "fwd")):
        drivetrain = "2wd"

    wheelbase = ""
    if re.search(r"\d{3}li", norm) or "长轴" in norm or "l版" in norm:
        wheelbase = "long"
    elif re.search(r"\d{3}i", norm) or "标轴" in norm:
        wheelbase = "standard"

    body = ""
    if any(token in norm for token in ("两厢", "hatchback")):
        body = "hatchback"
    elif any(token in norm for token in ("旅行", "touring", "avant")):
        body = "wagon"
    elif any(token in norm for token in ("轿跑", "coupe")):
        body = "coupe"

    seat = _first_match([r"(\d)座"], norm)
    range_battery = _first_match([r"(\d{2,4})\s*km", r"(\d{2,4})km", r"(\d+(?:\.\d+)?)kwh"], norm)
    if "磷酸铁锂" in norm:
        range_battery = f"{range_battery}_lfp" if range_battery else "lfp"
    elif "三元锂" in norm:
        range_battery = f"{range_battery}_ternary" if range_battery else "ternary"

    config = ""
    config_patterns = [
        ("m_sport_shadow", ("m运动曜夜", "曜夜", "黑标")),
        ("m_sport", ("m运动", "运动套装", "运动版")),
        ("luxury", ("豪华", "旗舰", "尊贵", "尊享", "至尊")),
        ("comfort", ("舒适", "舒享")),
        ("elite", ("精英", "领先")),
        ("fashion", ("时尚",)),
        ("premium", ("臻享", "智享", "智联", "星空满逸")),
        ("entry", ("进取", "低配", "入门")),
    ]
    for label, tokens in config_patterns:
        if any(token in norm for token in tokens):
            config = label
            break
    if not config:
        config = _first_match([r"(pro|max|plus|you|we|me|lite|ultra)"], norm)

    energy = normalize_energy_type(energy_value, brand=brand, series=series, trim=raw, is_new_energy=energy_value)["energy_type"]

    bits = [
        brand_key,
        series_key,
        year,
        generation,
        energy if energy != UNKNOWN else "",
        powertrain,
        transmission,
        drivetrain,
        wheelbase,
        body,
        seat,
        range_battery,
        config,
        facelift,
    ]
    # If parser could not extract any meaningful spec, keep normalized trim
    # instead of collapsing unrelated trims into a package-level key.
    spec_bits = [powertrain, transmission, drivetrain, wheelbase, body, seat, range_battery, config, facelift]
    if not any(spec_bits) and norm:
        bits.append(norm)
    canonical_key = "|".join(str(bit) for bit in bits if bit)
    parsed = CanonicalTrim(
        raw_trim=raw,
        normalized_trim=norm,
        canonical_trim_key=canonical_key,
        parsed_powertrain=powertrain,
        parsed_transmission=transmission,
        parsed_drivetrain=drivetrain,
        parsed_energy=energy,
        parsed_body=body,
        parsed_generation=generation,
        parsed_displacement=displacement,
        parsed_engine=engine,
        parsed_wheelbase=wheelbase,
        parsed_seat_count=seat,
        parsed_range_battery=range_battery,
        parsed_config_grade=config,
        parsed_facelift=facelift,
        canonicalization_confidence=0.98 if powertrain and (config or transmission or wheelbase) else 0.90 if powertrain or range_battery else 0.72 if norm else 0.0,
        canonicalization_reason="|".join(
            reason
            for reason, ok in [
                ("brand_series_year_preserved", bool(brand_key and series_key and year)),
                ("powertrain_preserved", bool(powertrain)),
                ("transmission_preserved", bool(transmission)),
                ("drivetrain_preserved", bool(drivetrain)),
                ("wheelbase_preserved", bool(wheelbase)),
                ("energy_preserved", energy != UNKNOWN),
                ("range_battery_preserved", bool(range_battery)),
                ("config_preserved", bool(config)),
                ("fallback_normalized_trim_preserved", not any(spec_bits) and bool(norm)),
            ]
            if ok
        )
        or "insufficient_trim_semantics",
    )
    return asdict(parsed)


def add_v192_13_semantic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    records = [
        canonicalize_trim(
            row.get("trim"),
            row.get("brand"),
            row.get("series"),
            row.get("model_year"),
            model_id=row.get("model_id"),
            energy_value=row.get("is_new_energy"),
        )
        for row in result[["trim", "brand", "series", "model_year", "model_id", "is_new_energy"]].fillna("").to_dict("records")
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
    for column in energy.columns:
        result[column] = energy[column]
    condition_records = [
        normalize_condition(
            row.get("condition_risk_level"),
            inspection_grade=row.get("inspection_grade"),
            accident=row.get("is_accident"),
            flood=row.get("is_flood"),
            fire=row.get("is_fire"),
            odometer=row.get("is_odometer_abnormal"),
        )
        for row in result[["condition_risk_level", "inspection_grade", "is_accident", "is_flood", "is_fire", "is_odometer_abnormal"]].fillna("").to_dict("records")
    ]
    condition = pd.DataFrame(condition_records, index=result.index)
    for column in condition.columns:
        result[column] = condition[column]
    return result
