"""Benchmark execution engine."""

from __future__ import annotations

from solvbench.constants import PROBLEM_TYPES, SIZE_PRESETS, SOLVERS
from solvbench.generators import generate_instance
from solvbench.models import BenchmarkRun, ProblemInstance, SolverResult
from solvbench.solvers import ALL_SOLVERS, AVAILABLE_SOLVERS, get_solver


class BenchmarkEngine:
    def __init__(self, time_limit_sec: float = 10.0) -> None:
        self.time_limit_sec = time_limit_sec

    def run_instance(
        self,
        instance: ProblemInstance,
        solvers: list[str] | None = None,
        include_reference: bool = True,
    ) -> BenchmarkRun:
        solver_ids = solvers or (ALL_SOLVERS if include_reference else AVAILABLE_SOLVERS)
        results: list[SolverResult] = []
        baseline: SolverResult | None = None

        for sid in solver_ids:
            if sid not in SOLVERS:
                continue
            solver = get_solver(sid, self.time_limit_sec, baseline=baseline)
            result = solver.solve(instance)
            results.append(result)
            if sid in AVAILABLE_SOLVERS and result.metrics.feasible:
                if baseline is None or result.metrics.solution_quality > baseline.metrics.solution_quality:
                    baseline = result

        winner = self._pick_winner(results)
        gap = self._winner_gap(results, winner)
        return BenchmarkRun(instance=instance, results=results, winner=winner, winner_gap_pct=gap)

    def run_problem_suite(
        self,
        problem_type: str,
        sizes: list[str] | None = None,
        seeds: list[int] | None = None,
        include_reference: bool = True,
    ) -> list[BenchmarkRun]:
        sizes = sizes or ["small", "medium", "large"]
        seeds = seeds or [42, 123, 456]
        runs = []
        for size in sizes:
            for seed in seeds:
                instance = generate_instance(problem_type, size, seed)
                runs.append(self.run_instance(instance, include_reference=include_reference))
        return runs

    def run_full_suite(self, include_reference: bool = True) -> list[BenchmarkRun]:
        all_runs = []
        for pt in PROBLEM_TYPES:
            all_runs.extend(self.run_problem_suite(pt, sizes=["medium"], seeds=[42], include_reference=include_reference))
        return all_runs

    @staticmethod
    def _pick_winner(results: list[SolverResult]) -> str:
        feasible = [r for r in results if r.metrics.feasible]
        if not feasible:
            return results[0].solver_id if results else "none"
        maximize = feasible[0].problem_type in ("knapsack", "max_independent_set")
        if maximize:
            best = max(feasible, key=lambda r: (r.metrics.solution_quality, -r.metrics.total_solving_time))
        else:
            best = min(
                feasible,
                key=lambda r: (r.metrics.objective_value if r.metrics.objective_value > 0 else 1e18, r.metrics.total_solving_time),
            )
        return best.solver_id

    @staticmethod
    def _winner_gap(results: list[SolverResult], winner: str) -> float:
        winner_r = next((r for r in results if r.solver_id == winner), None)
        if not winner_r or not winner_r.metrics.feasible:
            return 0.0
        others = [r for r in results if r.solver_id != winner and r.metrics.feasible]
        if not others:
            return 0.0
        gaps = []
        for r in others:
            if winner_r.metrics.objective_value > 0:
                gaps.append(abs(r.metrics.objective_value - winner_r.metrics.objective_value) / winner_r.metrics.objective_value * 100)
            else:
                gaps.append(abs(r.metrics.solution_quality - winner_r.metrics.solution_quality) * 100)
        return round(sum(gaps) / len(gaps), 2)
