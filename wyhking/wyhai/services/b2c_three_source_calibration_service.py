from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from catboost import CatBoostRegressor
import numpy as np
import pandas as pd

from .third_party_listing_price_service import get_third_party_listing_price_service


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models/v194_316/v194_316_three_source_b2c_residual.cbm"
POLICY_PATH = MODEL_PATH.with_suffix(".policy.json")


CAT_FEATURES = [
    "brand",
    "series",
    "city",
    "color",
    "condition",
    "model_year_cat",
    "dongchedi_match_level",
    "guazi_match_level",
    "autohome_match_level",
]
NUM_FEATURES = [
    "log_base_pred",
    "age_years",
    "mileage_wan_km",
    "transfer_count",
    "listing_to_base_ratio",
    "dongchedi_to_base_ratio",
    "guazi_to_base_ratio",
    "autohome_to_base_ratio",
    "source_count",
    "same_year_source_count",
    "total_listing_count_log",
    "cross_source_dispersion_ratio",
]


def _number(value: Any, default: float = -1.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or not math.isfinite(float(number)):
        return default
    return float(number)


def _source(quote: dict[str, Any], name: str) -> dict[str, Any]:
    return next((item for item in quote.get("sources", []) if item.get("source") == name), {})


class B2CThreeSourceCalibrationService:
    """Bounded current-listing calibration candidate for B2C transaction price.

    The service is deliberately candidate-only until the policy artifact says
    it has passed the full service validation gate. Asking prices remain a
    separate business role and are never returned as transaction labels.
    """

    def __init__(self, model_path: Path = MODEL_PATH, policy_path: Path = POLICY_PATH) -> None:
        self.model_path = model_path
        self.policy_path = policy_path
        self.model: CatBoostRegressor | None = None
        self.policy: dict[str, Any] = {}
        self.load_error = ""
        if not model_path.exists() or not policy_path.exists():
            self.load_error = "MODEL_OR_POLICY_MISSING"
            return
        try:
            self.model = CatBoostRegressor()
            self.model.load_model(model_path)
            self.policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.model = None
            self.load_error = f"{type(exc).__name__}: {exc}"

    def _feature_row(
        self,
        payload: dict[str, Any],
        quote: dict[str, Any],
        base_price_yuan: float,
    ) -> pd.DataFrame:
        sources = {name: _source(quote, name) for name in ("dongchedi", "guazi", "autohome")}
        listing_price = _number(quote.get("listing_price_yuan"))
        values: dict[str, Any] = {
            "brand": str(payload.get("brand") or ""),
            "series": str(payload.get("series") or ""),
            "city": str(payload.get("city") or ""),
            "color": str(payload.get("color") or ""),
            "condition": str(payload.get("condition") or payload.get("condition_grade") or ""),
            "model_year_cat": str(int(_number(payload.get("model_year") or payload.get("modelYear"), 0))),
            "log_base_pred": math.log(max(1.0, base_price_yuan)),
            "age_years": _number(payload.get("age_years")),
            "mileage_wan_km": _number(payload.get("mileage_wan_km") or payload.get("mileage")),
            "transfer_count": _number(payload.get("transfer_count") or payload.get("transfer")),
            "listing_to_base_ratio": listing_price / base_price_yuan if listing_price > 0 else -1.0,
            "source_count": _number(quote.get("source_count"), 0),
            "same_year_source_count": _number(quote.get("same_year_source_count"), 0),
            "total_listing_count_log": math.log1p(max(0.0, _number(quote.get("total_listing_count"), 0))),
            "cross_source_dispersion_ratio": _number(quote.get("cross_source_dispersion_ratio")),
        }
        for name, item in sources.items():
            values[f"{name}_match_level"] = str(item.get("match_level") or "")
            median = _number(item.get("price_median_yuan"))
            values[f"{name}_to_base_ratio"] = median / base_price_yuan if median > 0 else -1.0
        return pd.DataFrame([[values[name] for name in CAT_FEATURES + NUM_FEATURES]], columns=CAT_FEATURES + NUM_FEATURES)

    def predict(
        self,
        payload: dict[str, Any],
        *,
        b2c_transaction_price_yuan: float,
        listing_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = _number(b2c_transaction_price_yuan, 0)
        result: dict[str, Any] = {
            "enabled": False,
            "applied": False,
            "price_role": "B2C_TRANSACTION_CALIBRATION_CANDIDATE",
            "base_b2c_transaction_price_yuan": round(base, 2),
            "model_version": self.policy.get("version") or "v194_316_three_source_b2c_residual",
            "deployed": bool(self.policy.get("deployed", False)),
        }
        if self.model is None:
            return {**result, "reason": "MODEL_NOT_AVAILABLE", "error": self.load_error}
        if base <= 0:
            return {**result, "reason": "BASE_B2C_PRICE_MISSING"}
        quote = listing_result or get_third_party_listing_price_service().quote(payload)
        result["listing_evidence"] = quote
        if not quote.get("enabled"):
            return {**result, "reason": "THIRD_PARTY_LISTING_EVIDENCE_MISSING"}
        selected = self.policy.get("selected_model") or {}
        min_listings = int(selected.get("min_listings") or 8)
        max_dispersion = float(selected.get("max_dispersion") or 0.25)
        gate = (
            int(quote.get("source_count") or 0) >= 2
            and int(quote.get("same_year_source_count") or 0) >= 2
            and int(quote.get("total_listing_count") or 0) >= min_listings
            and _number(quote.get("cross_source_dispersion_ratio"), 999) <= max_dispersion
        )
        if not gate:
            return {
                **result,
                "reason": "STRICT_MULTI_SOURCE_CONSENSUS_GATE_FAILED",
                "required_min_listings": min_listings,
                "required_max_dispersion": max_dispersion,
            }
        frame = self._feature_row(payload, quote, base)
        residual = float(np.clip(self.model.predict(frame)[0], -0.15, 0.15))
        raw_candidate = base * math.exp(residual)
        alpha = float(self.policy.get("alpha") or 0.0)
        cap = float(self.policy.get("cap") or 0.0)
        bounded = base * float(np.clip(raw_candidate / base, 1.0 - cap, 1.0 + cap))
        candidate = base + alpha * (bounded - base)
        return {
            **result,
            "enabled": True,
            "reason": "STRICT_MULTI_SOURCE_CANDIDATE_READY",
            "predicted_log_residual": round(residual, 8),
            "raw_candidate_yuan": round(raw_candidate, 2),
            "candidate_b2c_transaction_price_yuan": round(candidate, 2),
            "candidate_b2c_transaction_price_wan": round(candidate / 10_000.0, 2),
            "blend_alpha": alpha,
            "single_adjustment_cap": cap,
            "source_count": int(quote.get("source_count") or 0),
            "total_listing_count": int(quote.get("total_listing_count") or 0),
            "cross_source_dispersion_ratio": quote.get("cross_source_dispersion_ratio"),
        }


@lru_cache(maxsize=1)
def get_b2c_three_source_calibration_service() -> B2CThreeSourceCalibrationService:
    return B2CThreeSourceCalibrationService()
