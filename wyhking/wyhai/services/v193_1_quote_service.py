from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable

from services.v193_quote_service import (
    get_version_payload as get_v193_version_payload,
    minimal_real_payload,
    quote_with_v193_service,
    v193_readiness_check,
)
from usedcar_pricing.v193_qwen_client import FALLBACK_MODEL_2, PRIMARY_MODEL, QwenConfig


PRICING_ENGINE_VERSION = "193.1.0"
MODEL_VERSION = "v193_1_qwen_plus_semantic_ab"
POLICY_VERSION = "v193_1_qwen_plus_semantic_ab_policy"
BUILD_TIME = datetime.now(timezone.utc).isoformat()


def quote_with_v1931_service(payload: dict[str, Any], legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("_quote_state_store_path", os.environ.get("V193_1_QUOTE_STATE_DB") or os.environ.get("V193_QUOTE_STATE_DB"))
    if not payload.get("_quote_state_store_path"):
        payload["_quote_state_store_path"] = tempfile.mktemp(prefix="v193_1_quote_state_", suffix=".sqlite")
    result = quote_with_v193_service(payload, legacy_pricing_callable)
    config = QwenConfig.from_env()
    qwen_enabled = bool(config.api_key)
    semantic_model = config.model if qwen_enabled else FALLBACK_MODEL_2
    result.update(
        {
            "pricing_engine_used": "V193_1_QWEN_SEMANTIC",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "model_version": MODEL_VERSION,
            "policy_version": POLICY_VERSION,
            "semantic_layer_version": "v193_1",
            "semantic_model": semantic_model,
            "qwen_enabled": qwen_enabled,
            "web_search_enabled": False,
            "web_search_status": "SCHEMA_VALIDATION_FAILED_NOT_USED",
            "web_search_result_can_enter_evidence_db": False,
            "web_search_result_can_affect_price": False,
            "underlying_pricing_engine_used": result.get("underlying_pricing_engine_used") or "V192_16",
            "underlying_pricing_engine_version": result.get("underlying_pricing_engine_version") or get_v193_version_payload().get("underlying_pricing_engine_version"),
            "qwen_fallback_count": int(semantic_model == FALLBACK_MODEL_2),
        }
    )
    card = result.get("evidence_card") or {}
    card.update(
        {
            "pricing_engine_used": "V193_1_QWEN_SEMANTIC",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "semantic_layer_version": "v193_1",
            "semantic_model": semantic_model,
            "qwen_enabled": qwen_enabled,
            "web_search_status": result["web_search_status"],
        }
    )
    result["evidence_card"] = card
    return result


def get_version_payload() -> dict[str, Any]:
    config = QwenConfig.from_env()
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "semantic_layer_version": "v193_1",
        "semantic_model": config.model if config.api_key else FALLBACK_MODEL_2,
        "primary_semantic_model": PRIMARY_MODEL,
        "qwen_enabled": bool(config.api_key),
        "web_search_enabled": False,
        "web_search_status": "SCHEMA_VALIDATION_FAILED_NOT_USED",
        "underlying_pricing_engine_version": get_v193_version_payload().get("underlying_pricing_engine_version"),
        "git_commit": os.environ.get("GIT_COMMIT") or "workspace-no-git-v193_1",
        "build_time": os.environ.get("BUILD_TIME", BUILD_TIME),
        "production_entrypoint": "app.py",
        "api_path": "/api/price",
    }


def v1931_readiness_check(force: bool = False) -> dict[str, Any]:
    status = v193_readiness_check(force=force)
    version = get_version_payload()
    status.update(version)
    status["entrypoint_uses_v193_1"] = True
    status["real_prediction_pricing_engine_used"] = "V193_1_QWEN_SEMANTIC" if status.get("real_prediction_succeeded") else status.get("real_prediction_pricing_engine_used")
    status["ready"] = bool(status.get("ready"))
    return status
