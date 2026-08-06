#!/usr/bin/env python3
"""Versioned schema and validation for the price explanation ledger."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = "price_explanation_ledger_v1"
TEMPLATE_VERSION = "business_explanation_template_v1"


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


@dataclass
class PriceExplanationLedger:
    quote_id: str
    model_version: str
    policy_version: str
    explanation_schema_version: str = SCHEMA_VERSION
    explanation_template_version: str = TEMPLATE_VERSION
    as_of_time: str = ""
    prediction_time: str = ""
    target_vehicle: dict[str, Any] = field(default_factory=dict)
    scenario_route: dict[str, Any] = field(default_factory=dict)
    retrieval_summary: dict[str, Any] = field(default_factory=dict)
    retrieved_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_comparables: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    statistical_price: dict[str, Any] = field(default_factory=dict)
    model_adjustment: dict[str, Any] = field(default_factory=dict)
    final_price: dict[str, Any] = field(default_factory=dict)
    interval: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    business_explanation: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    audit_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PriceExplanationLedger":
        return cls(**value)

    def validate(self, tolerance: float = 1.0) -> list[str]:
        errors: list[str] = []
        required = {
            "scenario_route": self.scenario_route,
            "statistical_price": self.statistical_price,
            "final_price": self.final_price,
            "interval": self.interval,
            "confidence": self.confidence,
            "business_explanation": self.business_explanation,
        }
        if self.final_price.get("final_point_price") is not None:
            required["selected_comparables"] = self.selected_comparables
        for name, value in required.items():
            if value in ({}, [], None, ""):
                errors.append(f"missing_{name}")

        selected_weight = sum(float(row.get("normalized_final_weight") or 0) for row in self.selected_comparables)
        if self.selected_comparables and abs(selected_weight - 1.0) > 1e-6:
            errors.append("selected_comparable_weights_do_not_sum_to_one")
        if any(abs(float(row.get("normalized_final_weight") or 0)) > 1e-12 for row in self.rejected_candidates):
            errors.append("rejected_candidate_has_nonzero_weight")

        prediction = self.prediction_time
        if prediction:
            try:
                cutoff = datetime.fromisoformat(str(prediction).replace("Z", "+00:00"))
                for candidate in self.retrieved_candidates:
                    available = candidate.get("knowledge_available_at")
                    if not available:
                        continue
                    available_at = datetime.fromisoformat(str(available).replace("Z", "+00:00"))
                    if available_at > cutoff:
                        errors.append("future_candidate_in_ledger")
                        break
            except (TypeError, ValueError):
                errors.append("invalid_temporal_field")

        difference = self.reconciliation.get("difference_from_serving_price")
        if difference is not None and abs(float(difference)) > tolerance:
            errors.append("final_price_reconciliation_failed")
        return errors

