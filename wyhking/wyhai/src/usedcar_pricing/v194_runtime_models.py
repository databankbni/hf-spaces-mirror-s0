from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


MODEL_FEATURES = [
    "brand_key",
    "series_key",
    "canonical_trim_key",
    "city_key_v194",
    "color_key_v194",
    "condition_risk_level_strict",
    "model_year",
    "age_years",
    "mileage_wan_km",
    "transfer_count",
    "event_ordinal",
]
CATEGORICAL_FEATURES = [
    "brand_key",
    "series_key",
    "canonical_trim_key",
    "city_key_v194",
    "color_key_v194",
    "condition_risk_level_strict",
]


def query_feature_frame(query: dict[str, Any]) -> pd.DataFrame:
    quote_time = pd.to_datetime(query.get("quote_time"), errors="coerce")
    event_ordinal = (quote_time - pd.Timestamp("2020-01-01")).days if pd.notna(quote_time) else 0
    row = {
        "brand_key": str(query.get("brand_key") or ""),
        "series_key": str(query.get("series_key") or ""),
        "canonical_trim_key": str(query.get("canonical_trim_key") or ""),
        "city_key_v194": str(query.get("city_key_v194") or ""),
        "color_key_v194": str(query.get("color_key_v194") or ""),
        "condition_risk_level_strict": str(query.get("condition_risk_level_strict") or "unknown"),
        "model_year": pd.to_numeric(query.get("model_year"), errors="coerce"),
        "age_years": pd.to_numeric(query.get("age_years"), errors="coerce"),
        "mileage_wan_km": pd.to_numeric(query.get("mileage_wan_km"), errors="coerce"),
        "transfer_count": pd.to_numeric(query.get("transfer_count"), errors="coerce"),
        "event_ordinal": event_ordinal,
    }
    frame = pd.DataFrame([row], columns=MODEL_FEATURES)
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].fillna("").astype(str)
    for column in set(MODEL_FEATURES) - set(CATEGORICAL_FEATURES):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(-1.0)
    return frame


class V194DirectPricePrior:
    def __init__(self, bundle_path: Path) -> None:
        bundle = joblib.load(bundle_path)
        self.model = bundle["model"]
        self.validation_metrics = bundle.get("validation_metrics", {})
        self.model_version = str(bundle.get("model_version") or "v194_1_direct_price_prior")

    def predict(self, query: dict[str, Any]) -> float | None:
        try:
            value = float(np.exp(self.model.predict(query_feature_frame(query))[0]))
        except Exception:
            return None
        return value if np.isfinite(value) and value > 0 else None

