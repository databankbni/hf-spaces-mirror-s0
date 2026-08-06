"""Problem instance generators."""

from __future__ import annotations

import math
import random
from typing import Any

from solvbench.features import extract_features
from solvbench.models import ProblemInstance


def generate_instance(problem_type: str, size: str = "medium", seed: int = 42) -> ProblemInstance:
    generators = {
        "knapsack": _gen_knapsack,
        "tsp": _gen_tsp,
        "vrp": _gen_vrp,
        "job_shop": _gen_job_shop,
        "bin_packing": _gen_bin_packing,
        "facility_location": _gen_facility_location,
        "set_cover": _gen_set_cover,
        "assignment": _gen_assignment,
        "max_independent_set": _gen_mis,
    }
    if problem_type not in generators:
        raise ValueError(f"Unknown problem type: {problem_type}")
    rng = random.Random(seed)
    data, label = generators[problem_type](rng, size)
    features = extract_features(problem_type, data, size)
    instance_id = f"{problem_type}_{size}_s{seed}"
    return ProblemInstance(
        problem_type=problem_type,
        instance_id=instance_id,
        label=label,
        size=size,
        seed=seed,
        data=data,
        features=features,
        known_optimum=data.get("known_optimum"),
    )


def _scale_n(base: int, size: str) -> int:
    factor = {"small": 0.6, "medium": 1.0, "large": 1.5}.get(size, 1.0)
    return max(3, int(base * factor))


def _gen_knapsack(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(80, size)
    weights = [rng.randint(1, 50) for _ in range(n)]
    values = [rng.randint(10, 200) for _ in range(n)]
    capacity = int(sum(weights) * rng.uniform(0.35, 0.55))
    return {
        "n_items": n,
        "weights": weights,
        "values": values,
        "capacity": capacity,
    }, f"Knapsack ({n} items, capacity {capacity})"


def _gen_tsp(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(15, size)
    coords = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
    dist = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(0.0)
            else:
                dx = coords[i][0] - coords[j][0]
                dy = coords[i][1] - coords[j][1]
                row.append(round(math.hypot(dx, dy), 2))
        dist.append(row)
    return {
        "n_cities": n,
        "coordinates": coords,
        "distance_matrix": dist,
    }, f"TSP ({n} cities)"


def _gen_vrp(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(20, size)
    vehicles = max(2, n // 8)
    depot = (50.0, 50.0)
    customers = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
    demands = [rng.randint(1, 15) for _ in range(n)]
    capacity = max(demands) * 3
    total_demand = sum(demands)
    coords = [depot] + customers
    dist = []
    for i in range(len(coords)):
        row = []
        for j in range(len(coords)):
            if i == j:
                row.append(0.0)
            else:
                dx = coords[i][0] - coords[j][0]
                dy = coords[i][1] - coords[j][1]
                row.append(round(math.hypot(dx, dy), 2))
        dist.append(row)
    return {
        "n_customers": n,
        "n_vehicles": vehicles,
        "depot_index": 0,
        "coordinates": coords,
        "demands": [0] + demands,
        "vehicle_capacity": capacity,
        "distance_matrix": dist,
        "demand_ratio": round(total_demand / (vehicles * capacity), 4),
    }, f"VRP ({n} customers, {vehicles} vehicles)"


def _gen_job_shop(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n_jobs = _scale_n(5, size)
    n_machines = max(3, n_jobs)
    processing_times = []
    machine_order = []
    for _ in range(n_jobs):
        machines = list(range(n_machines))
        rng.shuffle(machines)
        machine_order.append(machines)
        processing_times.append([rng.randint(1, 20) for _ in range(n_machines)])
    return {
        "n_jobs": n_jobs,
        "n_machines": n_machines,
        "machine_order": machine_order,
        "processing_times": processing_times,
    }, f"Job Shop ({n_jobs} jobs × {n_machines} machines)"


def _gen_bin_packing(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(60, size)
    capacity = 100
    sizes = [rng.randint(10, 90) for _ in range(n)]
    return {
        "n_items": n,
        "item_sizes": sizes,
        "bin_capacity": capacity,
    }, f"Bin Packing ({n} items, bin cap {capacity})"


def _gen_facility_location(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    nf = _scale_n(8, size)
    nc = _scale_n(25, size)
    facilities = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(nf)]
    customers = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(nc)]
    fixed_costs = [rng.randint(500, 2000) for _ in range(nf)]
    transport = []
    for c in customers:
        row = []
        for f in facilities:
            row.append(round(math.hypot(c[0] - f[0], c[1] - f[1]) * rng.uniform(1.0, 3.0), 2))
        transport.append(row)
    return {
        "n_facilities": nf,
        "n_customers": nc,
        "facility_coords": facilities,
        "customer_coords": customers,
        "fixed_costs": fixed_costs,
        "transport_costs": transport,
    }, f"Facility Location ({nf} sites, {nc} customers)"


def _gen_set_cover(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    ne = _scale_n(40, size)
    ns = _scale_n(25, size)
    sets = []
    for _ in range(ns):
        size_set = rng.randint(max(1, ne // 10), max(2, ne // 3))
        members = sorted(rng.sample(range(ne), min(size_set, ne)))
        sets.append(members)
    costs = [rng.randint(1, 50) for _ in range(ns)]
    return {
        "n_elements": ne,
        "n_sets": ns,
        "sets": sets,
        "costs": costs,
    }, f"Set Cover ({ne} elements, {ns} sets)"


def _gen_assignment(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(15, size)
    costs = [[rng.randint(1, 100) for _ in range(n)] for _ in range(n)]
    return {
        "n_agents": n,
        "cost_matrix": costs,
    }, f"Assignment ({n}×{n})"


def _gen_mis(rng: random.Random, size: str) -> tuple[dict[str, Any], str]:
    n = _scale_n(25, size)
    p_edge = 0.25
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p_edge:
                edges.append([i, j])
    return {
        "n_vertices": n,
        "edges": edges,
    }, f"Max Independent Set ({n} vertices, {len(edges)} edges)"
