from __future__ import annotations

from typing import Any

import pandas as pd


DIRTY_CLASSIFIER_VERSION = "v193_dirty_data_classifier_v1"
TOKEN_VALUES = {1, 2, 4, 10, 50, 100, 101, 111, 123, 999, 1000, 1111, 1234, 2000, 2222, 3000, 3333, 9999}


def _body(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).lower()


def classify_price_record(record: dict[str, Any]) -> dict[str, Any]:
    price = pd.to_numeric(record.get("price"), errors="coerce")
    source_type = str(record.get("source_type") or "")
    price_type = str(record.get("price_type") or "")
    body = _body(record.get("description"), record.get("trim"), source_type, price_type, record.get("sale_status_raw"))
    reasons: list[str] = []
    if pd.isna(price) or float(price) <= 0:
        reasons.append("PRICE_MISSING_OR_NONPOSITIVE")
    elif int(round(float(price))) in TOKEN_VALUES:
        reasons.append("TOKEN_OR_PLACEHOLDER_PRICE")
    elif float(price) < 1000 or float(price) > 2_000_000:
        reasons.append("PRICE_OUT_OF_BUSINESS_RANGE")
    if any(token in body for token in ("订金", "定金", "首付", "尾款", "服务费", "佣金")):
        reasons.append("NON_VEHICLE_TOTAL_PRICE_ROLE")
    if any(token in body for token in ("事故残值", "泡水", "火烧", "调表", "报废", "手续")):
        reasons.append("SPECIAL_RISK_OR_RESIDUAL_PRICE")
    if "c2b" in body or "purchase" in body or "收车" in body:
        role = "C2B_PURCHASE"
    elif "listing" in body or "挂牌" in body:
        role = "B2C_LISTING"
    elif "sold" in body or "成交" in body:
        role = "B2C_SOLD"
    else:
        role = "UNKNOWN"
    valid = len(reasons) == 0
    return {
        "valid_for_training": valid and role in {"C2B_PURCHASE", "B2C_SOLD"},
        "valid_for_retrieval": valid,
        "valid_for_evaluation_label": valid and role == "C2B_PURCHASE",
        "price_role": role,
        "dirty_reason_codes": reasons,
        "confidence": 0.95 if reasons else 0.82,
        "dirty_classifier_version": DIRTY_CLASSIFIER_VERSION,
    }


def classify_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for record in frame.to_dict("records"):
        rows.append({**{k: record.get(k) for k in ["observation_id", "price", "source_type", "price_type", "brand", "series", "model_year", "trim"]}, **classify_price_record(record)})
    result = pd.DataFrame(rows)
    if "dirty_reason_codes" in result:
        result["dirty_reason_codes"] = result["dirty_reason_codes"].map(lambda value: "|".join(value) if isinstance(value, list) else str(value))
    return result
