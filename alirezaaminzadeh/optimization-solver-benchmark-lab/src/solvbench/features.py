"""Instance feature extraction for meta-model input."""

from __future__ import annotations

import math
from typing import Any

from solvbench.models import InstanceFeatures, ProblemInstance


def extract_features(problem_type: str, data: dict[str, Any], size: str) -> InstanceFeatures:
    extractors = {
        "knapsack": _knapsack_features,
        "tsp": _tsp_features,
        "vrp": _vrp_features,
        "job_shop": _job_shop_features,
        "bin_packing": _bin_packing_features,
        "facility_location": _facility_location_features,
        "set_cover": _set_cover_features,
        "assignment": _assignment_features,
        "max_independent_set": _mis_features,
    }
    fn = extractors.get(problem_type, _default_features)
    return fn(data, size)


def _scale(size: str) -> float:
    return {"small": 0.6, "medium": 1.0, "large": 1.5}.get(size, 1.0)


def _knapsack_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = len(data["weights"])
    capacity = data["capacity"]
    total_w = sum(data["weights"])
    return InstanceFeatures(
        n_variables=n,
        n_constraints=1,
        density=round(n / max(capacity, 1), 4),
        symmetry=0.15,
        pct_integer=1.0,
        graph_sparsity=0.0,
        constraint_tightness=round(total_w / max(capacity * 2, 1), 4),
    )


def _tsp_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = data["n_cities"]
    return InstanceFeatures(
        n_variables=n * n,
        n_constraints=2 * n,
        density=round(1.0 / n, 4),
        symmetry=0.95,
        pct_integer=1.0,
        graph_sparsity=0.0,
        constraint_tightness=0.5,
    )


def _vrp_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = data["n_customers"]
    vehicles = data["n_vehicles"]
    return InstanceFeatures(
        n_variables=n * vehicles + n,
        n_constraints=n + vehicles,
        density=round(vehicles / max(n, 1), 4),
        symmetry=0.4,
        pct_integer=0.85,
        graph_sparsity=0.3,
        constraint_tightness=round(data.get("demand_ratio", 0.7), 4),
    )


def _job_shop_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n_jobs = data["n_jobs"]
    n_machines = data["n_machines"]
    n_ops = n_jobs * n_machines
    return InstanceFeatures(
        n_variables=n_ops * 2,
        n_constraints=n_ops + n_jobs,
        density=round(n_machines / max(n_ops, 1), 4),
        symmetry=0.25,
        pct_integer=0.9,
        graph_sparsity=0.6,
        constraint_tightness=0.65,
    )


def _bin_packing_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = len(data["item_sizes"])
    cap = data["bin_capacity"]
    return InstanceFeatures(
        n_variables=n * 2,
        n_constraints=n,
        density=round(sum(data["item_sizes"]) / (n * cap), 4),
        symmetry=0.1,
        pct_integer=1.0,
        graph_sparsity=0.0,
        constraint_tightness=round(sum(data["item_sizes"]) / (n * cap * 1.2), 4),
    )


def _facility_location_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    nf = data["n_facilities"]
    nc = data["n_customers"]
    return InstanceFeatures(
        n_variables=nf + nf * nc,
        n_constraints=nc + 1,
        density=round(nf / max(nc, 1), 4),
        symmetry=0.2,
        pct_integer=0.5,
        graph_sparsity=0.4,
        constraint_tightness=0.55,
    )


def _set_cover_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    ne = data["n_elements"]
    ns = data["n_sets"]
    avg_cov = sum(len(s) for s in data["sets"]) / max(ns, 1)
    return InstanceFeatures(
        n_variables=ns,
        n_constraints=ne,
        density=round(avg_cov / max(ne, 1), 4),
        symmetry=0.05,
        pct_integer=1.0,
        graph_sparsity=round(1 - avg_cov / ne, 4),
        constraint_tightness=round(ne / (ns * avg_cov), 4),
    )


def _assignment_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = data["n_agents"]
    return InstanceFeatures(
        n_variables=n * n,
        n_constraints=2 * n,
        density=round(1.0 / n, 4),
        symmetry=0.8,
        pct_integer=1.0,
        graph_sparsity=0.0,
        constraint_tightness=0.5,
    )


def _mis_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    n = data["n_vertices"]
    m = len(data["edges"])
    max_edges = n * (n - 1) / 2
    return InstanceFeatures(
        n_variables=n,
        n_constraints=m,
        density=round(m / max(max_edges, 1), 4),
        symmetry=0.3,
        pct_integer=1.0,
        graph_sparsity=round(1 - m / max(max_edges, 1), 4),
        constraint_tightness=round(m / max(n * 3, 1), 4),
    )


def _default_features(data: dict[str, Any], size: str) -> InstanceFeatures:
    return InstanceFeatures(
        n_variables=int(50 * _scale(size)),
        n_constraints=int(30 * _scale(size)),
        density=0.3,
        symmetry=0.3,
        pct_integer=0.8,
        graph_sparsity=0.5,
        constraint_tightness=0.5,
    )


def features_from_instance(instance: ProblemInstance) -> InstanceFeatures:
    return instance.features
