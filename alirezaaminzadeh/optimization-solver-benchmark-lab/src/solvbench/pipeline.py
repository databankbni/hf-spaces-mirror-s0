"""Pipeline for loading pre-computed assets and running live benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solvbench.constants import ENGINE_VERSION, PROBLEM_TYPES, SOLVERS
from solvbench.engine import BenchmarkEngine
from solvbench.generators import generate_instance
from solvbench.metamodel import SolverMetaModel
from solvbench.models import BenchmarkRun, MetaModelPrediction, ProblemInstance


class SolvBenchPipeline:
    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = Path(assets_dir)
        self.version = ENGINE_VERSION
        self.engine = BenchmarkEngine()
        self.metamodel = SolverMetaModel()
        self.summary: dict[str, Any] = {}
        self.benchmarks: dict[str, Any] = {}
        self.comparisons: dict[str, Any] = {}
        self.scalability: dict[str, Any] = {}

    def load(self) -> None:
        demo = self.assets_dir / "demo"
        if (demo / "summary.json").exists():
            self.summary = json.loads((demo / "summary.json").read_text(encoding="utf-8"))
        if (demo / "benchmarks.json").exists():
            self.benchmarks = json.loads((demo / "benchmarks.json").read_text(encoding="utf-8"))
        if (demo / "comparisons.json").exists():
            self.comparisons = json.loads((demo / "comparisons.json").read_text(encoding="utf-8"))
        if (demo / "scalability.json").exists():
            self.scalability = json.loads((demo / "scalability.json").read_text(encoding="utf-8"))
        model_weights = self.assets_dir.parent.parent / "model" / "metamodel_weights.json"
        if not model_weights.exists():
            model_weights = self.assets_dir / "model" / "metamodel_weights.json"
        if model_weights.exists():
            self.metamodel = SolverMetaModel(model_weights)

    def get_instance(self, problem_type: str, size: str = "medium", seed: int = 42) -> ProblemInstance:
        return generate_instance(problem_type, size, seed)

    def run_benchmark(
        self,
        problem_type: str,
        size: str = "medium",
        seed: int = 42,
        include_reference: bool = True,
    ) -> BenchmarkRun:
        instance = self.get_instance(problem_type, size, seed)
        return self.engine.run_instance(instance, include_reference=include_reference)

    def predict_solver(self, problem_type: str, size: str = "medium", seed: int = 42) -> MetaModelPrediction:
        instance = self.get_instance(problem_type, size, seed)
        return self.metamodel.predict(instance)

    def benchmark_table_rows(self) -> list[dict[str, Any]]:
        return self.benchmarks.get("rows", [])

    def problem_choices(self) -> list[tuple[str, str]]:
        return [(meta["label"], pid) for pid, meta in PROBLEM_TYPES.items()]

    def solver_choices(self) -> list[tuple[str, str]]:
        return [(meta["label"], sid) for sid, meta in SOLVERS.items()]
