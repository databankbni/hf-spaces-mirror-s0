"""Plotly visualizations for benchmark results."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from solvbench.constants import SOLVERS
from solvbench.models import BenchmarkRun, SolverResult


def build_solver_comparison_chart(results: list[SolverResult], metric: str = "total_solving_time") -> go.Figure:
    labels = [SOLVERS.get(r.solver_id, {}).get("label", r.solver_id) for r in results]
    values = [getattr(r.metrics, metric, 0) for r in results]
    colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors[: len(labels)],
        text=[f"{v:.3f}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Solver Comparison — {metric.replace('_', ' ').title()}",
        yaxis_title=metric.replace("_", " ").title(),
        template="plotly_white",
        height=400,
    )
    return fig


def build_radar_chart(results: list[SolverResult]) -> go.Figure:
    categories = ["Quality", "Speed", "Gap", "Stability", "Scalability"]
    fig = go.Figure()
    colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
    for i, r in enumerate(results):
        if not r.metrics.feasible:
            continue
        speed = max(0, 1 - r.metrics.total_solving_time / 30)
        gap_score = max(0, 1 - r.metrics.optimality_gap / 20)
        values = [
            r.metrics.solution_quality,
            speed,
            gap_score,
            r.metrics.stability_score,
            r.metrics.scalability_score,
        ]
        label = SOLVERS.get(r.solver_id, {}).get("label", r.solver_id)
        fig.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=label,
            line_color=colors[i % len(colors)],
            opacity=0.7,
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title="Multi-Metric Solver Radar",
        template="plotly_white",
        height=450,
    )
    return fig


def build_benchmark_heatmap(rows: list[dict[str, Any]]) -> go.Figure:
    if not rows:
        return go.Figure()
    problems = sorted({r["problem_type"] for r in rows})
    solvers = sorted({r["solver_id"] for r in rows})
    z = []
    for p in problems:
        row = []
        for s in solvers:
            match = [r for r in rows if r["problem_type"] == p and r["solver_id"] == s]
            row.append(match[0]["solve_time_sec"] if match else 0)
        z.append(row)
    fig = go.Figure(go.Heatmap(
        z=z, x=[SOLVERS.get(s, {}).get("label", s) for s in solvers],
        y=problems, colorscale="Viridis",
    ))
    fig.update_layout(title="Solve Time Heatmap (sec)", template="plotly_white", height=500)
    return fig


def build_scalability_chart(rows: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    colors = {"small": "#10b981", "medium": "#6366f1", "large": "#ef4444"}
    for solver_id in sorted({r["solver_id"] for r in rows}):
        for size in ("small", "medium", "large"):
            subset = [r for r in rows if r["solver_id"] == solver_id and r.get("size") == size]
            if not subset:
                continue
            avg_time = sum(r["solve_time_sec"] for r in subset) / len(subset)
            label = SOLVERS.get(solver_id, {}).get("label", solver_id)
            fig.add_trace(go.Bar(
                name=f"{label} ({size})",
                x=[size], y=[avg_time],
                marker_color=colors.get(size, "#888"),
            ))
    fig.update_layout(
        title="Scalability by Instance Size",
        xaxis_title="Size", yaxis_title="Avg Solve Time (sec)",
        barmode="group", template="plotly_white", height=400,
    )
    return fig


def build_metamodel_chart(rankings: list[dict[str, Any]]) -> go.Figure:
    labels = [r["solver_label"] for r in rankings]
    scores = [r["score"] for r in rankings]
    fig = go.Figure(go.Bar(
        x=labels, y=scores,
        marker_color=["#6366f1" if i == 0 else "#94a3b8" for i in range(len(labels))],
        text=[f"{s:.3f}" for s in scores],
        textposition="outside",
    ))
    fig.update_layout(title="Meta-Model Solver Rankings", template="plotly_white", height=380)
    return fig


def build_gap_timeline(results: list[SolverResult]) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    labels = [SOLVERS.get(r.solver_id, {}).get("label", r.solver_id) for r in results]
    fig.add_trace(go.Bar(
        x=labels,
        y=[r.metrics.time_to_first_feasible for r in results],
        name="Time to First Feasible",
        marker_color="#10b981",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=labels,
        y=[r.metrics.time_to_best for r in results],
        name="Time to Best",
        mode="lines+markers",
        line=dict(color="#6366f1", width=3),
    ), secondary_y=True)
    fig.update_layout(title="Solution Progress Timeline", template="plotly_white", height=400)
    fig.update_yaxes(title_text="First Feasible (sec)", secondary_y=False)
    fig.update_yaxes(title_text="Best Solution (sec)", secondary_y=True)
    return fig
