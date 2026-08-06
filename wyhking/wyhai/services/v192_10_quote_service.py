from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from src.usedcar_pricing.v192_10_service import (
        EVIDENCE_CARD_VERSION,
        MODEL_VERSION,
        POLICY_VERSION,
        PRICING_ENGINE_VERSION,
        V19210PricingService,
        V19210QuoteStateStore,
    )
except ModuleNotFoundError:
    from usedcar_pricing.v192_10_service import (
        EVIDENCE_CARD_VERSION,
        MODEL_VERSION,
        POLICY_VERSION,
        PRICING_ENGINE_VERSION,
        V19210PricingService,
        V19210QuoteStateStore,
    )

from services.v192_8_quote_service import HistoricalV1928PricingEngine


ROOT = Path(__file__).resolve().parents[1]
_ENGINE: HistoricalV1928PricingEngine | None = None
_ENGINE_LOCK = threading.Lock()
_READY_CACHE: dict[str, Any] | None = None
BUILD_TIME = datetime.now(timezone.utc).isoformat()


def minimal_real_payload() -> dict[str, Any]:
    return {
        "request_id": "v192_10_ready_probe",
        "brand": "宝马",
        "series": "宝马3系",
        "model": "2021款 320i 运动套装",
        "model_year": 2021,
        "vehicle_model_year": 2021,
        "regDate": "2021-09",
        "reg_date": "2021-09",
        "mileage": 6.34,
        "transfer": 1,
        "color": "白色",
        "city": "北京",
        "condition_risk_level": "clean",
        "query_energy_type": "ICE",
        "vehicle_id": "v19210-ready-probe",
        "lifecycle_id": "v19210-ready-probe-life",
    }


def get_engine() -> HistoricalV1928PricingEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = HistoricalV1928PricingEngine(ROOT)
    return _ENGINE


def get_version_payload() -> dict[str, Any]:
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": PRICING_ENGINE_VERSION,
        "underlying_model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
        "git_commit": os.environ.get("GIT_COMMIT", ""),
        "build_time": os.environ.get("BUILD_TIME", BUILD_TIME),
        "production_entrypoint": "app.py",
        "api_path": "/api/price",
    }


def quote_with_v19210_service(
    payload: dict[str, Any],
    legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    store_path = Path(
        payload.get("_quote_state_store_path")
        or os.environ.get("V19210_QUOTE_STATE_DB", "")
        or ROOT / "data/runtime/v192_10_quote_state.sqlite"
    )
    service = V19210PricingService(
        engine=get_engine(),
        state_store=V19210QuoteStateStore(store_path),
        legacy_fallback=legacy_pricing_callable,
    )
    return service.quote(payload)


def _required_files() -> list[Path]:
    return [
        ROOT
        / "data/knowledge/v185_market_price/"
        "vehicle_source_price_observation.parquet",
        ROOT / "results/v192_2/v192_2_observation_quality.parquet",
        ROOT / "data/v192_4/v192_4_trim_relationship_quality.parquet",
        ROOT / "results/audit/v192_2_series_calibration_oof_audit.csv",
        ROOT / "models/v192_2/v192_2_base_residual_model.joblib",
    ]


def v19210_readiness_check(force: bool = False) -> dict[str, Any]:
    global _READY_CACHE
    if _READY_CACHE is not None and not force:
        return dict(_READY_CACHE)
    checks: dict[str, Any] = {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "entrypoint_uses_v192_10": True,
        "required_files": {
            str(path.relative_to(ROOT)): path.exists()
            for path in _required_files()
        },
        "sqlite_state_store": False,
        "engine_loaded": False,
        "real_prediction_succeeded": False,
        "real_prediction_selected_comparables": 0,
    }
    try:
        store = V19210QuoteStateStore(
            ROOT / "data/runtime/v192_10_ready_check.sqlite"
        )
        with store._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["sqlite_state_store"] = True
    except Exception as error:
        checks["sqlite_error"] = str(error)
    try:
        engine = get_engine()
        checks["engine_loaded"] = True
        result = engine.quote(minimal_real_payload())
        checks["real_prediction_succeeded"] = bool(
            result.get("final_price") is not None
        )
        checks["real_prediction_final_price"] = result.get("final_price")
        checks["real_prediction_selected_comparables"] = len(
            result.get("selected_comparables") or []
        )
        checks["real_prediction_confidence"] = result.get("confidence")
    except Exception as error:
        checks["engine_error"] = str(error)
    checks["ready"] = (
        all(checks["required_files"].values())
        and checks["sqlite_state_store"]
        and checks["entrypoint_uses_v192_10"]
        and checks["engine_loaded"]
        and checks["real_prediction_succeeded"]
        and checks["real_prediction_selected_comparables"] > 0
    )
    _READY_CACHE = dict(checks)
    return checks
