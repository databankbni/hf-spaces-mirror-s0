from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from services.v192_16_quote_service import (
    get_version_payload as get_v19216_version_payload,
    minimal_real_payload as minimal_v19216_payload,
    quote_with_v19216_service,
    v19216_readiness_check,
)
from usedcar_pricing.v193_candidate_relation_judge import CandidateRelationJudge
from usedcar_pricing.v193_evidence_card_generator import build_evidence_card
from usedcar_pricing.v193_qwen_client import FALLBACK_MODEL_2, PRIMARY_MODEL, QwenConfig, QwenSemanticClient
from usedcar_pricing.v193_semantic_ranker import semantic_rank_candidates
from usedcar_pricing.v193_vehicle_semantic_parser import VehicleSemanticParser


ROOT = Path(__file__).resolve().parents[1]
PRICING_ENGINE_VERSION = "193.0.0"
SEMANTIC_LAYER_VERSION = "v193"
MODEL_VERSION = "v193_qwen_semantic_evidence_layer"
POLICY_VERSION = "v193_semantic_trust_gate_v1"
BUILD_TIME = datetime.now(timezone.utc).isoformat()


def _candidate_to_struct(item: dict[str, Any]) -> dict[str, Any]:
    parser = VehicleSemanticParser()
    return parser.parse(
        {
            "brand": item.get("brand"),
            "series": item.get("series"),
            "model_year": item.get("model_year"),
            "raw_trim": item.get("trim") or item.get("raw_trim"),
            "raw_energy": item.get("energy_type"),
        }
    )


def _payload_to_struct(payload: dict[str, Any]) -> dict[str, Any]:
    parser = VehicleSemanticParser()
    return parser.parse(
        {
            "brand": payload.get("brand"),
            "series": payload.get("series"),
            "model_year": payload.get("model_year") or payload.get("modelYear") or payload.get("vehicle_model_year"),
            "raw_trim": payload.get("model") or payload.get("trim"),
            "raw_energy": payload.get("query_energy_type") or payload.get("energy_type") or payload.get("is_new_energy"),
            "raw_description": payload.get("raw_description", ""),
        }
    )


def _semantic_candidate_audit(result: dict[str, Any], target_struct: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    judge = CandidateRelationJudge()
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(result.get("selected_comparables") or [], start=1):
        candidate_struct = _candidate_to_struct(item)
        relation = judge.judge(
            target_struct,
            candidate_struct,
            candidate_price_role=str(item.get("price_type") or item.get("original_price_role") or ""),
            candidate_source_family=str(item.get("source_family") or item.get("source_type") or ""),
            candidate_transaction_time=item.get("transaction_time") or item.get("event_time"),
        )
        row = {
            "query_id": result.get("quote_id"),
            "candidate_rank": rank,
            "candidate_id": item.get("candidate_id"),
            "target_vehicle_key": target_struct.get("canonical_trim_key"),
            "candidate_canonical_key": candidate_struct.get("canonical_trim_key"),
            "relationship_type": relation.get("relationship_type"),
            "semantic_similarity_score": relation.get("semantic_similarity_score"),
            "source_family": item.get("source_family") or item.get("source_type"),
            "price_role": item.get("price_type") or item.get("original_price_role"),
            "raw_price": item.get("original_price"),
            "c2b_converted_price": item.get("converted_c2b_price") or item.get("original_price"),
            "conversion_ratio": item.get("conversion_ratio"),
            "candidate_weight": item.get("final_weight"),
            "used_for_baseline": item.get("used_for_statistical_baseline"),
            "used_for_interval": True,
            "used_for_manual_reference": True,
            "blocked_from_baseline_reason": "" if item.get("used_for_statistical_baseline") else "NOT_SELECTED_BY_V19216_OR_WEAK_RELATION",
            "energy_relation": "same" if target_struct.get("energy_type") == candidate_struct.get("energy_type") else "unknown_or_diff",
            "condition_relation": item.get("condition_match", ""),
            "time_distance_days": item.get("days_since_transaction"),
            "mileage_distance": item.get("mileage_difference"),
            "city_match": item.get("city_match"),
            "confidence": relation.get("max_confidence_allowed"),
            "automatic_quote": result.get("confidence") in {"HIGH", "MEDIUM"},
        }
        rows.append(row)
    if rows:
        ranked = semantic_rank_candidates(pd.DataFrame(rows))
        grouped = ranked.groupby("candidate_group_v193").size().to_dict()
    else:
        grouped = {}
    return rows, grouped


def _patch_v193_result(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    client = QwenSemanticClient()
    target_struct = _payload_to_struct(payload)
    candidate_rows, candidate_groups = _semantic_candidate_audit(result, target_struct)
    baseline_candidates = [row for row in candidate_rows if row.get("used_for_baseline")]
    interval_only = [row for row in candidate_rows if not row.get("used_for_baseline") and row.get("used_for_interval")]
    manual = [row for row in candidate_rows if row.get("used_for_manual_reference")]
    facts = {
        "target_vehicle": target_struct,
        "canonical_key": target_struct.get("canonical_trim_key"),
        "candidate_summary": candidate_groups,
        "baseline_candidates": baseline_candidates,
        "interval_only_candidates": interval_only,
        "manual_reference_candidates": manual,
        "statistical_baseline": (result.get("price_trace") or {}).get("statistical_baseline_price"),
        "residual_adjustment": {
            "policy": (result.get("price_trace") or {}).get("residual_policy"),
            "final_residual_ratio": (result.get("price_trace") or {}).get("final_residual_ratio"),
        },
        "trust_gate_result": {
            "confidence": result.get("confidence") or (result.get("price_result") or {}).get("confidence"),
            "level": "AUTO_QUOTE" if (result.get("confidence") in {"HIGH", "MEDIUM"}) else "LOW_REFERENCE_OR_MANUAL",
        },
        "risk_warnings": result.get("risk_warnings") or [],
        "web_evidence_summary": {"enabled": bool(client.config.api_key and client.config.enable_web_search), "count": 0},
    }
    semantic_card = build_evidence_card(facts)
    result["pricing_engine_used"] = "V193_QWEN_SEMANTIC"
    result["pricing_engine_version"] = PRICING_ENGINE_VERSION
    result["model_version"] = MODEL_VERSION
    result["policy_version"] = POLICY_VERSION
    result["semantic_layer_version"] = SEMANTIC_LAYER_VERSION
    result["semantic_model"] = client.model_name
    result["web_search_enabled"] = bool(client.config.api_key and client.config.enable_web_search)
    result["qwen_cache_hit_rate"] = client.cache_hit_rate
    result["underlying_pricing_engine_used"] = "V192_16"
    result["underlying_pricing_engine_version"] = get_v19216_version_payload().get("pricing_engine_version")
    result["semantic_candidate_audit"] = candidate_rows
    result["semantic_candidate_group_counts"] = candidate_groups
    result["semantic_target_parse"] = target_struct
    result["semantic_evidence_card"] = semantic_card
    card = result.get("evidence_card") or {}
    card.update(
        {
            "pricing_engine_used": "V193_QWEN_SEMANTIC",
            "pricing_engine_version": PRICING_ENGINE_VERSION,
            "semantic_layer_version": SEMANTIC_LAYER_VERSION,
            "semantic_model": client.model_name,
            "web_search_enabled": result["web_search_enabled"],
            "qwen_cache_hit_rate": result["qwen_cache_hit_rate"],
            "semantic_evidence_card": semantic_card,
            "semantic_candidate_audit": candidate_rows[:20],
        }
    )
    result["evidence_card"] = card
    result["reason"] = (
        "v193 使用 Qwen/规则语义证据层增强车型解析、候选关系、候选重排和解释；"
        "最终价格仍由 v192.16 结构化统计基线与Trust Gate决定，LLM不直接报价。"
    )
    result["modelName"] = "v193-qwen-semantic-evidence-layer"
    return result


def quote_with_v193_service(payload: dict[str, Any], legacy_pricing_callable: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    base_payload = dict(payload)
    base_payload.setdefault("_quote_state_store_path", os.environ.get("V193_QUOTE_STATE_DB") or str(ROOT / "data/runtime/v193_quote_state.sqlite"))
    result = quote_with_v19216_service(base_payload, legacy_pricing_callable)
    if result.get("pricing_engine_used") not in {"V192_16", "V193_QWEN_SEMANTIC"}:
        result["semantic_model"] = FALLBACK_MODEL_2
        result["pricing_engine_used"] = result.get("pricing_engine_used") or "LEGACY_FALLBACK"
        result["fallback_reason"] = result.get("fallback_reason") or "V19216_UNDERLYING_FAILED"
        return result
    return _patch_v193_result(result, payload)


def get_version_payload() -> dict[str, Any]:
    config = QwenConfig.from_env()
    return {
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "policy_version": POLICY_VERSION,
        "semantic_layer_version": SEMANTIC_LAYER_VERSION,
        "semantic_model": config.model if config.api_key else FALLBACK_MODEL_2,
        "primary_semantic_model": PRIMARY_MODEL,
        "web_search_enabled": bool(config.api_key and config.enable_web_search),
        "search_strategy": config.search_strategy,
        "underlying_pricing_engine_version": get_v19216_version_payload().get("pricing_engine_version"),
        "git_commit": os.environ.get("GIT_COMMIT") or "workspace-no-git-v193",
        "build_time": os.environ.get("BUILD_TIME", BUILD_TIME),
        "production_entrypoint": "app.py",
        "api_path": "/api/price",
    }


def minimal_real_payload() -> dict[str, Any]:
    return minimal_v19216_payload()


def v193_readiness_check(force: bool = False) -> dict[str, Any]:
    checks = {
        **get_version_payload(),
        "entrypoint_uses_v193": True,
        "underlying_v19216_ready": False,
        "real_prediction_succeeded": False,
        "real_prediction_pricing_engine_used": "",
        "real_prediction_selected_comparables": 0,
    }
    try:
        checks["underlying_v19216_ready"] = bool(v19216_readiness_check(force=force).get("ready"))
        os.environ.setdefault("V193_QUOTE_STATE_DB", tempfile.mktemp(prefix="v193_ready_", suffix=".sqlite"))
        result = quote_with_v193_service(minimal_real_payload(), lambda payload: {})
        checks["real_prediction_succeeded"] = result.get("pricing_engine_used") == "V193_QWEN_SEMANTIC"
        checks["real_prediction_pricing_engine_used"] = result.get("pricing_engine_used", "")
        checks["real_prediction_selected_comparables"] = len(result.get("selected_comparables") or [])
        checks["semantic_model"] = result.get("semantic_model")
        checks["web_search_enabled"] = result.get("web_search_enabled")
    except Exception as error:
        checks["engine_error"] = str(error)
    checks["ready"] = (
        checks["entrypoint_uses_v193"]
        and checks["underlying_v19216_ready"]
        and checks["real_prediction_succeeded"]
        and checks["real_prediction_pricing_engine_used"] == "V193_QWEN_SEMANTIC"
        and checks["real_prediction_selected_comparables"] > 0
    )
    return checks

