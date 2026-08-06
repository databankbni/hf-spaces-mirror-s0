from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from catboost import CatBoostRegressor
import numpy as np
import pandas as pd

from usedcar_pricing.v192_13_semantics import canonicalize_trim


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "v194_315" / "v194_315_c2b_from_b2c_spread.cbm"
POLICY_PATH = ROOT / "models" / "v194_315" / "v194_315_c2b_from_b2c_spread_policy.json"


class C2BFromB2CSpreadService:
    def __init__(self) -> None:
        self.model: CatBoostRegressor | None = None
        self.policy: dict[str, Any] = {}
        self.load_error = ""
        try:
            self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            model = CatBoostRegressor()
            model.load_model(MODEL_PATH)
            self.model = model
        except Exception as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _number(value: Any, default: float = -1.0) -> float:
        number = pd.to_numeric(value, errors="coerce")
        return float(number) if pd.notna(number) else default

    @staticmethod
    def _age_years(payload: dict[str, Any]) -> float:
        direct = C2BFromB2CSpreadService._number(payload.get("age_years"), np.nan)
        if np.isfinite(direct) and direct >= 0:
            return direct
        reg = pd.to_datetime(
            payload.get("reg_date") or payload.get("first_registration_date") or payload.get("firstLicenseDate"),
            errors="coerce",
        )
        quote_time = pd.to_datetime(payload.get("quote_time"), errors="coerce")
        if pd.isna(quote_time):
            quote_time = pd.Timestamp.now()
        if pd.notna(reg):
            return max(0.0, float((quote_time - reg).days / 365.25))
        return -1.0

    def predict(self, payload: dict[str, Any], *, b2c_transaction_price_yuan: float) -> dict[str, Any]:
        b2c = self._number(b2c_transaction_price_yuan, np.nan)
        if self.model is None:
            return {"enabled": False, "reason": "MODEL_NOT_LOADED", "load_error": self.load_error}
        if not np.isfinite(b2c) or b2c < 5_000:
            return {"enabled": False, "reason": "INVALID_B2C_TRANSACTION_PRICE"}
        brand = str(payload.get("brand") or payload.get("brandName") or "").strip()
        series = str(payload.get("series") or payload.get("seriesName") or "").strip()
        trim = str(
            payload.get("trim")
            or payload.get("model")
            or payload.get("modelName")
            or payload.get("standard_vehicle")
            or ""
        ).strip()
        model_year = self._number(payload.get("model_year") or payload.get("modelYear"), -1.0)
        parsed = canonicalize_trim(
            trim,
            brand,
            series,
            model_year if model_year > 0 else None,
            model_id=payload.get("model_id") or payload.get("modelId") or "",
            energy_value=payload.get("energy_type") or payload.get("energyType") or "",
        )
        bins = self.policy.get("price_bins_yuan") or [0, 30_000, 50_000, 80_000, 120_000, 200_000, 300_000, 500_000, 2_000_000]
        price_band = int(np.clip(np.digitize([b2c], bins, right=True)[0] - 1, 0, len(bins) - 2))
        frame = pd.DataFrame(
            [
                {
                    "brand": parsed.get("brand_key") or brand or "missing",
                    "series": parsed.get("series_key") or series or "missing",
                    "trim": parsed.get("canonical_trim_key") or trim or "missing",
                    "city": str(payload.get("city") or "missing"),
                    "condition": str(payload.get("condition_risk_level_strict") or payload.get("condition") or "unknown"),
                    "grade": str(payload.get("inspection_grade") or payload.get("inspection_grade_norm") or "missing").upper(),
                    "price_band": str(price_band),
                    "b2c_anchor_yuan": b2c,
                    "age_years": self._age_years(payload),
                    "mileage_wan_km": self._number(payload.get("mileage_wan_km", payload.get("mileage"))),
                    "transfer_count": self._number(payload.get("transfer_count", payload.get("transfer"))),
                    "model_year": model_year,
                }
            ]
        )
        ratio_low, ratio_high = self.policy.get("ratio_clip") or [0.55, 0.98]
        ratio = float(np.clip(np.exp(self.model.predict(frame)[0]), ratio_low, ratio_high))
        c2b = min(b2c - 1.0, b2c * ratio)
        return {
            "enabled": True,
            "version": self.policy.get("version") or "v194_315_c2b_from_b2c_spread_v1",
            "price_role_chain": "B2C_TRANSACTION_MODEL_TO_C2B_SPREAD_MODEL",
            "b2c_transaction_price_yuan": round(b2c, 2),
            "predicted_c2b_to_b2c_ratio": ratio,
            "predicted_c2b_price_yuan": round(c2b, 2),
            "gross_spread_yuan": round(b2c - c2b, 2),
            "gross_spread_ratio": 1.0 - ratio,
            "price_band": price_band,
            "training_cutoff": self.policy.get("train_end"),
            "target_actual_usage": "CURRENT_TARGET_ACTUAL_NOT_USED_AT_QUOTE_TIME",
        }


@lru_cache(maxsize=1)
def get_c2b_from_b2c_spread_service() -> C2BFromB2CSpreadService:
    return C2BFromB2CSpreadService()
