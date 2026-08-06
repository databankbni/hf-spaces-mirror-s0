from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .v193_qwen_client import QwenSemanticClient


RELATION_VERSION = "v193_candidate_relation_judge_v1"
ALLOWED_RELATION_TYPES = {
    "T1_EXACT_TRIM",
    "T2_EXACT_UNKNOWN_FIELD",
    "T3A_VERIFIED_ADJACENT",
    "T3B_HEURISTIC_ADJACENT",
    "T4_LOOSE_FALLBACK",
    "NOT_COMPARABLE",
}
RELATION_ALIASES = {
    "T1_EXACT_MATCH": "T1_EXACT_TRIM",
    "T2_EXACT_TRIM_ENERGY_UNKNOWN": "T2_EXACT_UNKNOWN_FIELD",
    "T2_EXACT_UNKNOWN": "T2_EXACT_UNKNOWN_FIELD",
    "T3_ADJACENT": "T3B_HEURISTIC_ADJACENT",
}


def _same(a: Any, b: Any) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower() and str(a or "").strip() != ""


def _unknown(value: Any) -> bool:
    return str(value or "").strip().upper() in {"", "UNKNOWN", "UNKNOWN_FIELD", "NAN", "NONE"}


def _field_relation(target: dict[str, Any], candidate: dict[str, Any], field: str) -> tuple[int, int, int]:
    left = target.get(field)
    right = candidate.get(field)
    if _unknown(left) or _unknown(right):
        return 0, 1, 0
    if _same(left, right):
        return 1, 0, 0
    return 0, 0, 1


def judge_relation_rule(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "energy_type",
        "power_code",
        "engine_code",
        "transmission",
        "drivetrain",
        "wheelbase_type",
        "body_type",
        "seat_count",
        "trim_grade",
    ]
    known = unknown = conflict = 0
    for field in fields:
        k, u, c = _field_relation(target, candidate, field)
        known += k
        unknown += u
        conflict += c
    same_brand = _same(target.get("brand"), candidate.get("brand"))
    same_series = _same(target.get("series"), candidate.get("series"))
    same_year = str(target.get("model_year") or "") == str(candidate.get("model_year") or "")
    same_key = _same(target.get("canonical_trim_key"), candidate.get("canonical_trim_key"))
    energy_conflict = conflict > 0 and not _unknown(target.get("energy_type")) and not _unknown(candidate.get("energy_type")) and target.get("energy_type") != candidate.get("energy_type")
    if not same_brand or not same_series:
        rel = "NOT_COMPARABLE"
    elif same_key and conflict == 0 and unknown <= 2:
        rel = "T1_EXACT_TRIM"
    elif same_key and conflict == 0:
        rel = "T2_EXACT_UNKNOWN_FIELD"
    elif same_year and conflict == 0 and known >= 5 and unknown <= 3 and not energy_conflict:
        rel = "T3A_VERIFIED_ADJACENT"
    elif same_year and conflict <= 1:
        rel = "T3B_HEURISTIC_ADJACENT"
    elif same_series:
        rel = "T4_LOOSE_FALLBACK"
    else:
        rel = "NOT_COMPARABLE"
    if rel in {"T1_EXACT_TRIM", "T2_EXACT_UNKNOWN_FIELD", "T3A_VERIFIED_ADJACENT"}:
        baseline = True
        max_conf = "MEDIUM" if rel != "T1_EXACT_TRIM" else "HIGH"
    elif rel == "T3B_HEURISTIC_ADJACENT":
        baseline = False
        max_conf = "LOW"
    elif rel == "T4_LOOSE_FALLBACK":
        baseline = False
        max_conf = "MANUAL"
    else:
        baseline = False
        max_conf = "NO_QUOTE"
    reason_codes = []
    if energy_conflict:
        reason_codes.append("ENERGY_CONFLICT")
    if unknown > 3:
        reason_codes.append("MANY_UNKNOWN_FIELDS")
    if conflict:
        reason_codes.append("SPEC_CONFLICT")
    return {
        "relationship_type": rel,
        "can_enter_baseline": baseline,
        "can_enter_interval": rel != "NOT_COMPARABLE",
        "can_enter_manual_reference": rel != "NOT_COMPARABLE",
        "max_confidence_allowed": max_conf,
        "reason_codes": reason_codes,
        "semantic_similarity_score": round(max(0.0, (known - conflict) / max(1, len(fields))), 4),
        "risk_flags": reason_codes,
        "known_field_count": known,
        "unknown_field_count": unknown,
        "conflict_field_count": conflict,
        "relation_judge_version": RELATION_VERSION,
        "judge_source": "RULE",
    }


@dataclass
class CandidateRelationJudge:
    client: QwenSemanticClient | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = QwenSemanticClient()

    def judge(self, target: dict[str, Any], candidate: dict[str, Any], *, candidate_price_role: str = "", candidate_source_family: str = "", candidate_transaction_time: Any = "") -> dict[str, Any]:
        rule = judge_relation_rule(target, candidate)
        uncertain = rule["relationship_type"] in {"T2_EXACT_UNKNOWN_FIELD", "T3B_HEURISTIC_ADJACENT", "T4_LOOSE_FALLBACK"} or rule["unknown_field_count"] > 4
        if not uncertain:
            rule["semantic_model"] = "RULE_FALLBACK"
            rule["qwen_status"] = "NOT_NEEDED_STRONG_RULE"
            return rule
        assert self.client is not None
        qwen = self.client.complete_json(
            kind="candidate_relation",
            system_prompt=(
                "Judge whether target and candidate used-car trims are comparable. "
                "Never upgrade obvious energy, power, wheelbase or body conflicts. "
                "Return JSON only, no markdown, no wrapper key. Required keys: "
                "relationship_type, can_enter_baseline, can_enter_interval, can_enter_manual_reference, "
                "max_confidence_allowed, reason_codes, semantic_similarity_score, risk_flags."
            ),
            user_payload={
                "target_vehicle_struct": target,
                "candidate_vehicle_struct": candidate,
                "candidate_price_role": candidate_price_role,
                "candidate_source_family": candidate_source_family,
                "candidate_transaction_time": str(candidate_transaction_time or ""),
                "rule_judgment": rule,
            },
            schema={"relationship_type": str, "can_enter_baseline": bool, "reason_codes": list},
        )
        if qwen.get("_semantic_model") == "RULE_FALLBACK":
            rule["semantic_model"] = "RULE_FALLBACK"
            rule["qwen_status"] = qwen.get("_qwen_status", "RULE_FALLBACK")
            return rule
        # Qwen can only downgrade or refine uncertain cases; hard conflicts stay blocked.
        if rule["conflict_field_count"] > 0 and qwen.get("relationship_type") in {"T1_EXACT_TRIM", "T3A_VERIFIED_ADJACENT"}:
            qwen["relationship_type"] = rule["relationship_type"]
            qwen["can_enter_baseline"] = rule["can_enter_baseline"]
            qwen["reason_codes"] = [*qwen.get("reason_codes", []), "QWEN_UPGRADE_BLOCKED_BY_STRONG_RULE"]
        rel = str(qwen.get("relationship_type") or "")
        rel = RELATION_ALIASES.get(rel, rel)
        if rel not in ALLOWED_RELATION_TYPES:
            rel = rule["relationship_type"]
            qwen["reason_codes"] = [*qwen.get("reason_codes", []), "QWEN_RELATION_ENUM_NORMALIZED_TO_RULE"]
        qwen["relationship_type"] = rel
        merged = {**rule, **qwen}
        merged["judge_source"] = "QWEN_ASSISTED"
        merged["semantic_model"] = qwen.get("_semantic_model", self.client.model_name)
        merged["qwen_status"] = qwen.get("_qwen_status", "OK")
        merged["relation_judge_version"] = RELATION_VERSION
        return merged


def relation_audit_from_pairs(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> pd.DataFrame:
    judge = CandidateRelationJudge()
    return pd.DataFrame([judge.judge(target, candidate) for target, candidate in pairs])
