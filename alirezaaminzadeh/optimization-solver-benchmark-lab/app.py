"""
Optimization Solver Benchmark Lab — Interactive Benchmark Console
Aria AI Operations Research Team.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import gradio as gr
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from solvbench.constants import METRICS, PROBLEM_TYPES, SOLVERS  # noqa: E402
from solvbench.pipeline import SolvBenchPipeline  # noqa: E402
from solvbench.visualization import (  # noqa: E402
    build_benchmark_heatmap,
    build_gap_timeline,
    build_metamodel_chart,
    build_radar_chart,
    build_scalability_chart,
    build_solver_comparison_chart,
)

pipeline = SolvBenchPipeline(ROOT / "assets")
pipeline.load()

SUMMARY = pipeline.summary
BENCHMARKS = pipeline.benchmarks
PROBLEM_CHOICES = pipeline.problem_choices()
SIZE_CHOICES = [("Small", "small"), ("Medium", "medium"), ("Large", "large")]
METRIC_CHOICES = [
    ("Total Solving Time", "total_solving_time"),
    ("Solution Quality", "solution_quality"),
    ("Optimality Gap (%)", "optimality_gap"),
    ("Time to First Feasible", "time_to_first_feasible"),
    ("Memory Usage (MB)", "memory_usage_mb"),
    ("B&B Nodes", "branch_and_bound_nodes"),
]

CUSTOM_CSS = """
.gradio-container { max-width: 1520px !important; }
.markdown h1 { color: #4f46e5; }
.tab-nav button { font-weight: 600; }
"""

_state: dict = {"last_run": None, "last_prediction": None}


def _kpi_md() -> str:
    return f"""
### Optimization Solver Benchmark Lab — Executive Summary

| Metric | Value |
|--------|-------|
| Engine version | **v{pipeline.version}** |
| Benchmark problems | **{SUMMARY.get('problem_types', 9)}** (Knapsack, TSP, VRP, Job Shop, …) |
| Solvers profiled | **{SUMMARY.get('solvers', 6)}** (HiGHS, CBC, CP-SAT, SCIP, Gurobi, MiniZinc) |
| Evaluation metrics | **{SUMMARY.get('metrics', 9)}** |
| Meta-model | **Expert-calibrated** solver selector |
| Benchmark runs | **{SUMMARY.get('total_benchmark_runs', 54)}** pre-computed |

*Algorithm Engineering · Operations Research · Machine Learning · Experimental Design*
"""


def _benchmark_df() -> pd.DataFrame:
    rows = pipeline.benchmark_table_rows()
    if not rows:
        return pd.DataFrame()
    cols = [
        "problem_label", "size", "solver_label", "objective_value",
        "optimality_gap", "solve_time_sec", "time_to_first_feasible",
        "memory_mb", "bb_nodes", "status", "winner",
    ]
    return pd.DataFrame(rows)[[c for c in cols if c in rows[0]]]


def _run_benchmark(problem_type: str, size: str, seed: int, include_ref: bool):
    run = pipeline.run_benchmark(problem_type, size, int(seed), include_reference=include_ref)
    _state["last_run"] = run
    rows = []
    for r in run.results:
        rows.append({
            "Solver": SOLVERS[r.solver_id]["label"],
            "Objective": r.metrics.objective_value,
            "Gap (%)": r.metrics.optimality_gap,
            "Solve Time (s)": r.metrics.total_solving_time,
            "First Feasible (s)": r.metrics.time_to_first_feasible,
            "Memory (MB)": r.metrics.memory_usage_mb,
            "B&B Nodes": r.metrics.branch_and_bound_nodes,
            "Quality": r.metrics.solution_quality,
            "Status": r.metrics.status,
        })
    df = pd.DataFrame(rows)
    time_chart = build_solver_comparison_chart(run.results, "total_solving_time")
    radar = build_radar_chart(run.results)
    gap_chart = build_gap_timeline(run.results)
    inst = run.instance
    features_md = f"""
**Instance:** {inst.label}  
**Features:** {inst.features.n_variables} variables · {inst.features.n_constraints} constraints ·  
density={inst.features.density:.3f} · symmetry={inst.features.symmetry:.3f} ·  
integer={inst.features.pct_integer:.0%} · sparsity={inst.features.graph_sparsity:.3f} ·  
tightness={inst.features.constraint_tightness:.3f}  
**Winner:** {SOLVERS.get(run.winner, {}).get('label', run.winner)} (avg gap vs others: {run.winner_gap_pct:.1f}%)
"""
    return df, time_chart, radar, gap_chart, features_md


def _predict_solver(problem_type: str, size: str, seed: int):
    pred = pipeline.predict_solver(problem_type, size, int(seed))
    _state["last_prediction"] = pred
    df = pd.DataFrame(pred.rankings)
    chart = build_metamodel_chart(pred.rankings)
    config_json = json.dumps(pred.recommended_config, indent=2)
    md = f"""
**Recommended:** {SOLVERS[pred.recommended_solver]['label']}  
**Confidence:** {pred.confidence:.1%}  
**Rationale:** {pred.rationale}
"""
    return md, df, chart, config_json


def _problem_info(problem_type: str) -> str:
    meta = PROBLEM_TYPES.get(problem_type, {})
    return f"**{meta.get('label', problem_type)}** — {meta.get('description', '')}"


with gr.Blocks(title="Optimization Solver Benchmark Lab", css=CUSTOM_CSS, theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Optimization Solver Benchmark Lab")
    gr.Markdown("*Aria AI Operations Research · Algorithm Engineering & Experimental Design*")

    with gr.Tabs():
        with gr.Tab("Executive Overview"):
            gr.Markdown(_kpi_md())
            gr.Markdown("### Pre-Computed Benchmark Results")
            bench_table = gr.Dataframe(value=_benchmark_df, interactive=False)
            heatmap = gr.Plot(value=build_benchmark_heatmap(pipeline.benchmark_table_rows()))
            with gr.Row():
                for pid, meta in list(PROBLEM_TYPES.items())[:5]:
                    gr.Markdown(f"- **{meta['label']}**: {meta['description'][:80]}…")
            with gr.Row():
                for pid, meta in list(PROBLEM_TYPES.items())[5:]:
                    gr.Markdown(f"- **{meta['label']}**: {meta['description'][:80]}…")

        with gr.Tab("Run Benchmark"):
            gr.Markdown("### Live Solver Benchmark")
            with gr.Row():
                problem_dd = gr.Dropdown(choices=PROBLEM_CHOICES, value="knapsack", label="Problem Type")
                size_dd = gr.Dropdown(choices=SIZE_CHOICES, value="medium", label="Instance Size")
                seed_num = gr.Number(value=42, label="Random Seed", precision=0)
                ref_cb = gr.Checkbox(value=True, label="Include reference solvers (Gurobi, SCIP, MiniZinc)")
            problem_info = gr.Markdown(_problem_info("knapsack"))
            run_btn = gr.Button("Run Benchmark", variant="primary")
            features_out = gr.Markdown()
            results_df = gr.Dataframe(interactive=False)
            with gr.Row():
                time_plot = gr.Plot()
                radar_plot = gr.Plot()
            gap_plot = gr.Plot()

            problem_dd.change(_problem_info, problem_dd, problem_info)
            run_btn.click(
                _run_benchmark,
                [problem_dd, size_dd, seed_num, ref_cb],
                [results_df, time_plot, radar_plot, gap_plot, features_out],
            )

        with gr.Tab("Meta-Model Advisor"):
            gr.Markdown("""
### Solver Selection Meta-Model
Predicts the best solver and configuration based on instance features:
`n_variables`, `n_constraints`, `density`, `symmetry`, `pct_integer`, `graph_sparsity`, `constraint_tightness`
            """)
            with gr.Row():
                mm_problem = gr.Dropdown(choices=PROBLEM_CHOICES, value="job_shop", label="Problem Type")
                mm_size = gr.Dropdown(choices=SIZE_CHOICES, value="medium", label="Size")
                mm_seed = gr.Number(value=42, label="Seed", precision=0)
            predict_btn = gr.Button("Predict Best Solver", variant="primary")
            pred_md = gr.Markdown()
            pred_df = gr.Dataframe(interactive=False)
            pred_chart = gr.Plot()
            config_out = gr.Code(language="json", label="Recommended Configuration")

            predict_btn.click(
                _predict_solver,
                [mm_problem, mm_size, mm_seed],
                [pred_md, pred_df, pred_chart, config_out],
            )

        with gr.Tab("Scalability Analysis"):
            gr.Markdown("### Solver Scalability Across Instance Sizes")
            scale_plot = gr.Plot(value=build_scalability_chart(pipeline.benchmark_table_rows()))
            gr.Markdown("""
| Metric | Description |
|--------|-------------|
| Solution quality | Normalized objective vs known bound |
| Optimality gap | Relative gap to best proven bound |
| Time to first feasible | Seconds until first valid solution |
| Time to best | Seconds until best solution found |
| Total solving time | Wall-clock solver runtime |
| Memory usage | Peak RAM during solve |
| B&B nodes | Branch-and-bound tree nodes explored |
| Stability | Consistency across random seeds |
| Scalability | Performance degradation with size |
            """)

        with gr.Tab("Solver Profiles"):
            solver_rows = []
            for sid, meta in SOLVERS.items():
                solver_rows.append({
                    "Solver": meta["label"],
                    "Engine": meta["engine"],
                    "License": meta["license"],
                    "Cloud Available": "Yes" if meta["available_in_space"] else "Reference",
                    "Strengths": ", ".join(meta["strengths"]),
                })
            gr.Dataframe(value=pd.DataFrame(solver_rows), interactive=False)
            gr.Markdown("""
**Note:** HiGHS, CBC, and OR-Tools CP-SAT run live in this Space.  
Gurobi, SCIP, and MiniZinc results are calibrated from reference benchmarks
(expert profiles based on published solver characteristics).
            """)

if __name__ == "__main__":
    demo.launch()
