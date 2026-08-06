"""Data models for solver benchmarking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class InstanceFeatures:
    n_variables: int = 0
    n_constraints: int = 0
    density: float = 0.0
    symmetry: float = 0.0
    pct_integer: float = 0.0
    graph_sparsity: float = 0.0
    constraint_tightness: float = 0.0

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)

    def vector(self) -> list[float]:
        return [
            float(self.n_variables),
            float(self.n_constraints),
            self.density,
            self.symmetry,
            self.pct_integer,
            self.graph_sparsity,
            self.constraint_tightness,
        ]


@dataclass
class ProblemInstance:
    problem_type: str
    instance_id: str
    label: str
    size: str
    seed: int
    data: dict[str, Any]
    features: InstanceFeatures
    known_optimum: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_type": self.problem_type,
            "instance_id": self.instance_id,
            "label": self.label,
            "size": self.size,
            "seed": self.seed,
            "data": self.data,
            "features": self.features.to_dict(),
            "known_optimum": self.known_optimum,
        }


@dataclass
class SolverMetrics:
    solution_quality: float = 0.0
    optimality_gap: float = 0.0
    time_to_first_feasible: float = 0.0
    time_to_best: float = 0.0
    total_solving_time: float = 0.0
    memory_usage_mb: float = 0.0
    branch_and_bound_nodes: int = 0
    stability_score: float = 1.0
    scalability_score: float = 1.0
    status: str = "unknown"
    objective_value: float = 0.0
    feasible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SolverResult:
    solver_id: str
    solver_config: dict[str, Any]
    instance_id: str
    problem_type: str
    metrics: SolverMetrics
    solution: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "solver_id": self.solver_id,
            "solver_config": self.solver_config,
            "instance_id": self.instance_id,
            "problem_type": self.problem_type,
            "metrics": self.metrics.to_dict(),
            "solution": self.solution,
        }


@dataclass
class MetaModelPrediction:
    recommended_solver: str
    recommended_config: dict[str, Any]
    confidence: float
    rankings: list[dict[str, Any]]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkRun:
    instance: ProblemInstance
    results: list[SolverResult]
    winner: str
    winner_gap_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "winner": self.winner,
            "winner_gap_pct": self.winner_gap_pct,
        }
