from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from src.usedcar_pricing.v192_9_service import (
        EVIDENCE_CARD_VERSION,
        MODEL_VERSION,
        POLICY_VERSION,
        PRICING_ENGINE_VERSION,
        V1929PricingService,
        V1929QuoteStateStore,
    )
except ModuleNotFoundError:
    from usedcar_pricing.v192_9_service import (
        EVIDENCE_CARD_VERSION,
        MODEL_VERSION,
        POLICY_VERSION,
        PRICING_ENGINE_VERSION,
        V1929PricingService,
        V1929QuoteStateStore,
    )

from services.v192_8_quote_service import HistoricalV1928PricingEngine


ROOT = Path(__file__).resolve().parents[1]
_ENGINE: HistoricalV1928PricingEngine | None = None
BUILD_TIME = datetime.now(timezone.utc).isoformat()


def get_engine() -> HistoricalV1928PricingEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = HistoricalV1928PricingEngine(ROOT)
    return _ENGINE


def get_version_payload() -> dict[str, Any]:
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "evidence_card_version": EVIDENCE_CARD_VERSION,
        "git_commit": os.environ.get("GIT_COMMIT", ""),
        "build_time": os.environ.get("BUILD_TIME", BUILD_TIME),
        "production_entrypoint": "app.py",
        "api_path": "/api/price",
    }


def quote_with_v1929_service(
    payload: dict[str, Any],
    legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    store_path = Path(
        payload.get("_quote_state_store_path")
        or os.environ.get("V1929_QUOTE_STATE_DB", "")
        or ROOT / "data/runtime/v192_9_quote_state.sqlite"
    )
    service = V1929PricingService(
        engine=get_engine(),
        state_store=V1929QuoteStateStore(store_path),
        legacy_fallback=legacy_pricing_callable,
    )
    return service.quote(payload)


def v1929_readiness_check(load_engine: bool = False) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "entrypoint_uses_v192_9": True,
        "required_files": {},
        "sqlite_state_store": False,
        "engine_loaded": False,
    }
    required = [
        ROOT
        / "data/knowledge/v185_market_price/"
        "vehicle_source_price_observation.parquet",
        ROOT / "results/v192_2/v192_2_observation_quality.parquet",
        ROOT / "data/v192_4/v192_4_trim_relationship_quality.parquet",
        ROOT / "results/audit/v192_2_series_calibration_oof_audit.csv",
        ROOT / "models/v192_2/v192_2_base_residual_model.joblib",
    ]
    checks["required_files"] = {
        str(path.relative_to(ROOT)): path.exists()
        for path in required
    }
    try:
        store = V1929QuoteStateStore(
            ROOT / "data/runtime/v192_9_ready_check.sqlite"
        )
        with store._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["sqlite_state_store"] = True
    except Exception as error:
        checks["sqlite_error"] = str(error)
    if load_engine:
        try:
            get_engine()
            checks["engine_loaded"] = True
        except Exception as error:
            checks["engine_error"] = str(error)
    checks["ready"] = (
        all(checks["required_files"].values())
        and checks["sqlite_state_store"]
        and checks["entrypoint_uses_v192_9"]
    )
    return checks
