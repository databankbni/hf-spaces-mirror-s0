"""Meta-model for solver selection — expert-calibrated linear scoring (no ML training)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solvbench.constants import FEATURE_NAMES, SOLVER_CONFIGS, SOLVERS
from solvbench.models import InstanceFeatures, MetaModelPrediction, ProblemInstance


DEFAULT_WEIGHTS: dict[str, Any] = {
    "version": "1.0.0",
    "method": "expert_calibrated_linear_scoring",
    "feature_names": FEATURE_NAMES,
    "normalization": {
        "n_variables": 500,
        "n_constraints": 300,
    },
    "solver_weights": {
        "highs": {
            "bias": 0.55,
            "coefficients": [0.1, 0.05, -0.2, -0.1, 0.15, 0.1, -0.05],
            "problem_affinity": {
                "assignment": 0.25, "knapsack": 0.15, "facility_location": 0.1,
            },
            "config_rules": {"large_mip": {"presolve": "on", "threads": 4}},
        },
        "cbc": {
            "bias": 0.5,
            "coefficients": [0.05, 0.1, 0.1, 0.0, 0.1, 0.0, 0.05],
            "problem_affinity": {
                "set_cover": 0.2, "bin_packing": 0.15, "knapsack": 0.1,
            },
            "config_rules": {"default": {"cuts": "on", "heuristics": "on"}},
        },
        "cp_sat": {
            "bias": 0.6,
            "coefficients": [-0.05, 0.05, 0.15, 0.2, 0.25, 0.15, 0.1],
            "problem_affinity": {
                "job_shop": 0.3, "vrp": 0.2, "tsp": 0.15, "bin_packing": 0.15,
                "max_independent_set": 0.1,
            },
            "config_rules": {"scheduling": {"num_search_workers": 8}},
        },
        "scip": {
            "bias": 0.58,
            "coefficients": [0.08, 0.12, 0.05, -0.05, 0.12, 0.05, 0.08],
            "problem_affinity": {
                "facility_location": 0.2, "set_cover": 0.15, "max_independent_set": 0.1,
            },
            "config_rules": {"mip": {"presolving": True, "separating": True}},
        },
        "gurobi": {
            "bias": 0.65,
            "coefficients": [0.12, 0.08, 0.0, -0.15, 0.1, 0.0, 0.05],
            "problem_affinity": {
                "facility_location": 0.25, "assignment": 0.2, "vrp": 0.15, "tsp": 0.1,
            },
            "config_rules": {"mip_focus": {"MIPFocus": 1, "Presolve": 2}},
        },
        "minizinc": {
            "bias": 0.52,
            "coefficients": [-0.02, 0.03, 0.2, 0.25, 0.2, 0.2, 0.15],
            "problem_affinity": {
                "job_shop": 0.25, "bin_packing": 0.2, "tsp": 0.1,
            },
            "config_rules": {"cp": {"solver": "chuffed"}},
        },
    },
}


class SolverMetaModel:
    """Predicts best solver + config from instance features using calibrated weights."""

    def __init__(self, weights_path: Path | None = None) -> None:
        self.weights = DEFAULT_WEIGHTS
        if weights_path and weights_path.exists():
            self.weights = json.loads(weights_path.read_text(encoding="utf-8"))

    def predict(self, instance: ProblemInstance) -> MetaModelPrediction:
        features = instance.features
        norm = self.weights["normalization"]
        fv = self._normalized_vector(features, norm)
        rankings = []

        for solver_id, sw in self.weights["solver_weights"].items():
            coefs = sw["coefficients"]
            score = sw["bias"] + sum(c * v for c, v in zip(coefs, fv))
            affinity = sw.get("problem_affinity", {}).get(instance.problem_type, 0.0)
            score += affinity
            size_penalty = {"small": 0, "medium": -0.02, "large": -0.05}.get(instance.size, 0)
            if solver_id in ("gurobi", "scip") and instance.size == "large":
                score += 0.08
            if solver_id == "cp_sat" and instance.problem_type in ("job_shop", "vrp"):
                score += 0.1
            score += size_penalty
            rankings.append({
                "solver_id": solver_id,
                "solver_label": SOLVERS[solver_id]["label"],
                "score": round(score, 4),
            })

        rankings.sort(key=lambda r: r["score"], reverse=True)
        best = rankings[0]
        config = self._select_config(best["solver_id"], instance)
        confidence = min(0.95, 0.5 + (rankings[0]["score"] - rankings[1]["score"]) * 2)
        rationale = self._build_rationale(instance, rankings[:3])

        return MetaModelPrediction(
            recommended_solver=best["solver_id"],
            recommended_config=config,
            confidence=round(confidence, 3),
            rankings=rankings,
            rationale=rationale,
        )

    def _normalized_vector(self, features: InstanceFeatures, norm: dict[str, int]) -> list[float]:
        return [
            min(1.0, features.n_variables / norm["n_variables"]),
            min(1.0, features.n_constraints / norm["n_constraints"]),
            features.density,
            features.symmetry,
            features.pct_integer,
            features.graph_sparsity,
            features.constraint_tightness,
        ]

    def _select_config(self, solver_id: str, instance: ProblemInstance) -> dict[str, Any]:
        base = dict(SOLVER_CONFIGS.get(solver_id, {}))
        rules = self.weights["solver_weights"].get(solver_id, {}).get("config_rules", {})
        if instance.problem_type in ("job_shop", "vrp", "tsp") and "scheduling" in rules:
            base.update(rules["scheduling"])
        elif instance.problem_type in ("facility_location", "set_cover", "assignment") and "mip" in rules:
            base.update(rules["mip"])
        elif instance.problem_type in ("job_shop", "bin_packing") and "cp" in rules:
            base.update(rules["cp"])
        elif "default" in rules:
            base.update(rules["default"])
        if instance.size == "large" and solver_id == "highs":
            base["threads"] = 4
        return base

    def _build_rationale(self, instance: ProblemInstance, top3: list[dict]) -> str:
        f = instance.features
        lines = [
            f"Instance: {instance.label} ({instance.size})",
            f"Features: {f.n_variables} vars, {f.n_constraints} constraints, "
            f"density={f.density:.2f}, integer={f.pct_integer:.0%}",
            f"Top recommendation: {SOLVERS[top3[0]['solver_id']]['label']} (score={top3[0]['score']:.3f})",
        ]
        if len(top3) > 1:
            lines.append(
                f"Runner-up: {SOLVERS[top3[1]['solver_id']]['label']} "
                f"(Δ={top3[0]['score'] - top3[1]['score']:.3f})"
            )
        if f.pct_integer > 0.8 and instance.problem_type in ("job_shop", "vrp"):
            lines.append("High integer ratio + scheduling structure favors CP-SAT.")
        elif instance.problem_type in ("assignment", "knapsack"):
            lines.append("LP/MIP structure favors HiGHS or Gurobi for root relaxation speed.")
        return " | ".join(lines)

    def save_weights(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.weights, indent=2), encoding="utf-8")
