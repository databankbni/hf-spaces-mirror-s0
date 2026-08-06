from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QLoRAGateThresholds:
    minimum_f1_gain: float = 0.15
    maximum_attribution_regression: float = 0.0
    maximum_fallback_increase: float = 0.02
    minimum_schema_validity: float = 0.99


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluate_qlora_gate(
    base: dict[str, Any],
    tuned: dict[str, Any],
    declared: dict[str, Any],
    thresholds: QLoRAGateThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or QLoRAGateThresholds()
    deltas = {
        "factor_micro_f1": tuned["factor_micro_f1"] - base["factor_micro_f1"],
        "team_attribution_accuracy": (
            tuned["team_attribution_accuracy"] - base["team_attribution_accuracy"]
        ),
        "fallback_rate": tuned["fallback_rate"] - base["fallback_rate"],
        "median_latency_ms": (
            tuned["median_latency_ms"] - base["median_latency_ms"]
        ),
    }
    checks = {
        "minimum_f1_gain": (
            deltas["factor_micro_f1"] >= thresholds.minimum_f1_gain
        ),
        "no_attribution_regression": (
            deltas["team_attribution_accuracy"]
            >= -thresholds.maximum_attribution_regression
        ),
        "fallback_rate_controlled": (
            deltas["fallback_rate"] <= thresholds.maximum_fallback_increase
        ),
        "schema_validity": (
            tuned["schema_validity_rate"] >= thresholds.minimum_schema_validity
        ),
    }
    computed_decision = "SHIP" if all(checks.values()) else "NO-SHIP"
    declared_decision = declared.get("ship_decision")
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "status": "closed" if declared_decision == computed_decision else "invalid",
        "computed_decision": computed_decision,
        "declared_decision": declared_decision,
        "release_blocking": declared_decision != computed_decision,
        "selected_runtime": (
            "tuned_adapter" if computed_decision == "SHIP" else "base_plus_fallback"
        ),
        "thresholds": {
            "minimum_f1_gain": thresholds.minimum_f1_gain,
            "maximum_attribution_regression": (
                thresholds.maximum_attribution_regression
            ),
            "maximum_fallback_increase": thresholds.maximum_fallback_increase,
            "minimum_schema_validity": thresholds.minimum_schema_validity,
        },
        "metrics": {
            "base": {
                key: base[key]
                for key in (
                    "factor_micro_f1",
                    "team_attribution_accuracy",
                    "fallback_rate",
                    "schema_validity_rate",
                    "median_latency_ms",
                )
            },
            "tuned": {
                key: tuned[key]
                for key in (
                    "factor_micro_f1",
                    "team_attribution_accuracy",
                    "fallback_rate",
                    "schema_validity_rate",
                    "median_latency_ms",
                )
            },
            "deltas": deltas,
        },
        "checks": checks,
        "failed_checks": reasons,
        "claim": (
            "The adapter is not shipped. The base model plus deterministic "
            "fallback remains the production extraction path."
        ),
    }


def close_qlora_gate(
    root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    base_path = root / "results/base_q8.json"
    tuned_path = root / "results/tuned_q8.json"
    decision_path = root / "results/ship_decision.json"
    paths = (base_path, tuned_path, decision_path)
    report = evaluate_qlora_gate(
        _load_json(base_path),
        _load_json(tuned_path),
        _load_json(decision_path),
    )
    report["artifacts"] = {
        str(path.relative_to(root)): {"sha256": _sha256(path)}
        for path in paths
    }
    report["adapter"] = _load_json(decision_path).get("tuned_model", {})
    destination = output_path or root / "results/qlora_gate_report.json"
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
