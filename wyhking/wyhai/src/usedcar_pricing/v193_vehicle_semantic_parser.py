from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .v192_16_semantics import canonicalize_trim, normalize_energy_type
from .v193_qwen_client import QwenSemanticClient, validate_schema


SEMANTIC_PARSE_VERSION = "v193_vehicle_semantic_parser_v1"
REQUIRED_PARSE_SCHEMA = {
    "brand": str,
    "series": str,
    "model_year": (int, str),
    "normalized_trim": str,
    "canonical_trim_key": str,
    "energy_type": str,
    "confidence": (int, float),
    "reason_codes": list,
}


def _canonical_energy(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("-", "_")
    if raw in {"ICE", "BEV", "PHEV", "HEV", "EREV", "UNKNOWN"}:
        return raw
    if raw in {"GASOLINE", "DIESEL", "FUEL", "PETROL", "燃油", "汽油", "柴油"}:
        return "ICE"
    if raw in {"EV", "PURE_ELECTRIC", "ELECTRIC", "纯电"}:
        return "BEV"
    if raw in {"HYBRID", "油电混动", "混动"}:
        return "HEV"
    if raw in {"PLUG_IN_HYBRID", "PLUGIN_HYBRID", "插混"}:
        return "PHEV"
    if raw in {"RANGE_EXTENDED", "增程"}:
        return "EREV"
    return "UNKNOWN"


def _sanitize_qwen_parse(rule: dict[str, Any], qwen: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(qwen)
    sanitized["energy_type"] = _canonical_energy(sanitized.get("energy_type"))
    if sanitized["energy_type"] == "UNKNOWN" and rule.get("energy_type"):
        sanitized["energy_type"] = rule["energy_type"]
    for column in ["drivetrain", "transmission", "wheelbase_type", "trim_grade", "body_type"]:
        if column in sanitized and sanitized[column] is not None:
            sanitized[column] = str(sanitized[column]).strip().lower()
    key = str(sanitized.get("canonical_trim_key") or "")
    for bad, good in {
        "|gasoline|": "|ICE|",
        "|diesel|": "|ICE|",
        "|fuel|": "|ICE|",
        "|GASOLINE|": "|ICE|",
        "|DIESEL|": "|ICE|",
    }.items():
        key = key.replace(bad, good)
    sanitized["canonical_trim_key"] = key or rule.get("canonical_trim_key", "")
    return sanitized


def _model_year(value: Any, fallback: Any = "") -> int | None:
    for candidate in (value, fallback):
        text = str(candidate or "")
        for token in text.replace("款", " ").split():
            try:
                year = int(float(token))
                if 1990 <= year <= 2035:
                    return year
            except Exception:
                continue
        import re

        match = re.search(r"(19|20)\d{2}", text)
        if match:
            return int(match.group(0))
    return None


def rule_parse_vehicle(
    *,
    brand: Any = "",
    series: Any = "",
    model_year: Any = None,
    raw_trim: Any = "",
    raw_energy: Any = "",
    raw_description: Any = "",
) -> dict[str, Any]:
    trim_text = raw_trim or raw_description
    canonical = canonicalize_trim(trim_text, brand, series, model_year, energy_value=raw_energy)
    energy = normalize_energy_type(raw_energy, brand=brand, series=series, trim=trim_text)
    year = _model_year(model_year, trim_text)
    confidence = float(canonical.get("canonicalization_confidence") or 0.0)
    reason_codes = [canonical.get("canonicalization_reason") or "RULE_CANONICALIZATION"]
    if energy.get("energy_type") == "UNKNOWN":
        confidence = min(confidence, 0.72)
        reason_codes.append("ENERGY_UNKNOWN")
    if confidence < 0.8:
        reason_codes.append("LOW_RULE_CONFIDENCE")
    return {
        "brand": str(brand or ""),
        "series": str(series or ""),
        "model_year": year,
        "normalized_trim": canonical.get("normalized_trim", ""),
        "canonical_trim_key": canonical.get("canonical_trim_key", ""),
        "energy_type": energy.get("energy_type", "UNKNOWN"),
        "power_code": canonical.get("power_code", ""),
        "displacement": canonical.get("displacement", ""),
        "engine_code": canonical.get("engine_code", ""),
        "transmission": canonical.get("transmission", ""),
        "drivetrain": canonical.get("drivetrain", ""),
        "wheelbase_type": canonical.get("wheelbase_type") or "unknown",
        "body_type": canonical.get("body_type", ""),
        "seat_count": canonical.get("seat_count") or None,
        "facelift_stage": canonical.get("facelift_stage", ""),
        "trim_grade": canonical.get("trim_grade", ""),
        "confidence": round(confidence, 4),
        "reason_codes": [code for code in reason_codes if code],
        "parser_source": "RULE",
        "semantic_parse_version": SEMANTIC_PARSE_VERSION,
    }


@dataclass
class VehicleSemanticParser:
    client: QwenSemanticClient | None = None
    qwen_threshold: float = 0.78

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = QwenSemanticClient()

    def parse(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = rule_parse_vehicle(
            brand=payload.get("brand"),
            series=payload.get("series"),
            model_year=payload.get("model_year"),
            raw_trim=payload.get("raw_trim") or payload.get("trim") or payload.get("model"),
            raw_energy=payload.get("raw_energy") or payload.get("energy_type") or payload.get("is_new_energy"),
            raw_description=payload.get("raw_description", ""),
        )
        if rule["confidence"] >= self.qwen_threshold and "ENERGY_UNKNOWN" not in rule["reason_codes"]:
            rule["semantic_model"] = "RULE_FALLBACK"
            rule["qwen_status"] = "NOT_NEEDED_HIGH_RULE_CONFIDENCE"
            return rule
        assert self.client is not None
        qwen = self.client.complete_json(
            kind="vehicle_parse",
            system_prompt=(
                "You parse Chinese used-car trim names into strict vehicle semantics. "
                "Return JSON only, no markdown, no wrapper key. Required keys: "
                "brand, series, model_year, normalized_trim, canonical_trim_key, energy_type, "
                "power_code, displacement, engine_code, transmission, drivetrain, wheelbase_type, "
                "body_type, seat_count, facelift_stage, trim_grade, confidence, reason_codes. "
                "Do not estimate prices."
            ),
            user_payload={**payload, "rule_parse": rule},
            schema=REQUIRED_PARSE_SCHEMA,
        )
        if qwen.get("_semantic_model") == "RULE_FALLBACK":
            rule["semantic_model"] = "RULE_FALLBACK"
            rule["qwen_status"] = qwen.get("_qwen_status", "RULE_FALLBACK")
            return rule
        try:
            validate_schema(qwen, REQUIRED_PARSE_SCHEMA)
            qwen = _sanitize_qwen_parse(rule, qwen)
            merged = {**rule, **qwen}
            merged["parser_source"] = "QWEN_ASSISTED"
            merged["semantic_parse_version"] = SEMANTIC_PARSE_VERSION
            merged["semantic_model"] = qwen.get("_semantic_model", self.client.model_name)
            merged["qwen_status"] = qwen.get("_qwen_status", "OK")
            return merged
        except Exception:
            rule["semantic_model"] = "RULE_FALLBACK"
            rule["qwen_status"] = "SEMANTIC_PARSE_FAILED"
            rule["reason_codes"] = [*rule.get("reason_codes", []), "SEMANTIC_PARSE_FAILED"]
            return rule


def parse_dataframe(frame: pd.DataFrame, sample_first: int | None = None) -> pd.DataFrame:
    parser = VehicleSemanticParser()
    rows = frame.head(sample_first).copy() if sample_first else frame.copy()
    parsed: list[dict[str, Any]] = []
    for row in rows.to_dict("records"):
        parsed.append(
            parser.parse(
                {
                    "brand": row.get("brand"),
                    "series": row.get("series"),
                    "model_year": row.get("model_year"),
                    "raw_trim": row.get("trim") or row.get("raw_trim") or row.get("model"),
                    "raw_energy": row.get("is_new_energy") or row.get("energy_type"),
                    "raw_description": json.dumps(row, ensure_ascii=False, default=str)[:1200],
                }
            )
        )
    return pd.DataFrame(parsed)


def write_parse_outputs(frame: pd.DataFrame, data_path: Path, audit_path: Path, sample_first: int | None = None) -> pd.DataFrame:
    data_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    parsed = parse_dataframe(frame, sample_first=sample_first)
    parsed.to_parquet(data_path, index=False)
    audit = parsed.copy()
    audit["reason_codes"] = audit["reason_codes"].map(lambda value: "|".join(value) if isinstance(value, list) else str(value))
    audit.to_csv(audit_path, index=False, encoding="utf-8-sig")
    return parsed
