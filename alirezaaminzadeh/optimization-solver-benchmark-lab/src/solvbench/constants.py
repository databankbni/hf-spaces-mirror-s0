"""Configuration constants for SolvBench."""

from __future__ import annotations

ENGINE_VERSION = "1.0.0"
VENDOR = "Aria AI Operations Research Team"

PROBLEM_TYPES = {
    "knapsack": {
        "label": "0/1 Knapsack",
        "category": "combinatorial",
        "description": "Select items maximizing value under a weight capacity constraint.",
        "default_size": "medium",
    },
    "tsp": {
        "label": "Traveling Salesman (TSP)",
        "category": "routing",
        "description": "Find the shortest Hamiltonian cycle visiting all cities once.",
        "default_size": "medium",
    },
    "vrp": {
        "label": "Vehicle Routing (VRP)",
        "category": "routing",
        "description": "Route a fleet from a depot to customers with capacity limits.",
        "default_size": "medium",
    },
    "job_shop": {
        "label": "Job Shop Scheduling",
        "category": "scheduling",
        "description": "Assign operations to machines respecting precedence and no-overlap.",
        "default_size": "medium",
    },
    "bin_packing": {
        "label": "Bin Packing",
        "category": "packing",
        "description": "Pack items into minimum bins without exceeding capacity.",
        "default_size": "medium",
    },
    "facility_location": {
        "label": "Facility Location",
        "category": "network",
        "description": "Open facilities and assign customers minimizing fixed + transport cost.",
        "default_size": "medium",
    },
    "set_cover": {
        "label": "Set Cover",
        "category": "combinatorial",
        "description": "Cover all elements with minimum-cost subsets.",
        "default_size": "medium",
    },
    "assignment": {
        "label": "Assignment Problem",
        "category": "network",
        "description": "Assign agents to tasks minimizing total cost (bipartite matching).",
        "default_size": "medium",
    },
    "max_independent_set": {
        "label": "Maximum Independent Set",
        "category": "graph",
        "description": "Find the largest set of mutually non-adjacent vertices.",
        "default_size": "medium",
    },
}

SIZE_PRESETS = {
    "small": {"scale": 0.6, "time_limit_sec": 5},
    "medium": {"scale": 1.0, "time_limit_sec": 10},
    "large": {"scale": 1.5, "time_limit_sec": 20},
}

SOLVERS = {
    "highs": {
        "label": "HiGHS",
        "engine": "highspy",
        "available_in_space": True,
        "license": "MIT",
        "strengths": ["LP/MIP", "fast LP root", "open source"],
    },
    "cbc": {
        "label": "CBC (via PuLP)",
        "engine": "pulp",
        "available_in_space": True,
        "license": "EPL",
        "strengths": ["MIP", "general purpose", "open source"],
    },
    "cp_sat": {
        "label": "OR-Tools CP-SAT",
        "engine": "ortools",
        "available_in_space": True,
        "license": "Apache-2.0",
        "strengths": ["CP", "scheduling", "pseudo-Boolean"],
    },
    "scip": {
        "label": "SCIP",
        "engine": "scip",
        "available_in_space": False,
        "license": "Academic/Commercial",
        "strengths": ["MIP", "branch-and-cut", "research-grade"],
    },
    "gurobi": {
        "label": "Gurobi",
        "engine": "gurobi",
        "available_in_space": False,
        "license": "Commercial",
        "strengths": ["MIP", "speed", "industrial"],
    },
    "minizinc": {
        "label": "MiniZinc (Chuffed/Gecode)",
        "engine": "minizinc",
        "available_in_space": False,
        "license": "MPL",
        "strengths": ["CP", "model portability", "multi-backend"],
    },
}

METRICS = [
    "solution_quality",
    "optimality_gap",
    "time_to_first_feasible",
    "time_to_best",
    "total_solving_time",
    "memory_usage_mb",
    "branch_and_bound_nodes",
    "stability_score",
    "scalability_score",
]

FEATURE_NAMES = [
    "n_variables",
    "n_constraints",
    "density",
    "symmetry",
    "pct_integer",
    "graph_sparsity",
    "constraint_tightness",
]

SOLVER_CONFIGS = {
    "highs": {"presolve": "on", "threads": 2, "mip_rel_gap": 0.01},
    "cbc": {"presolve": "on", "cuts": "on", "heuristics": "on"},
    "cp_sat": {"num_search_workers": 4, "max_time_in_seconds": 10, "log_search_progress": False},
    "scip": {"presolving": True, "separating": True, "heuristics": True},
    "gurobi": {"Presolve": 2, "MIPFocus": 1, "Heuristics": 0.2},
    "minizinc": {"solver": "chuffed", "time_limit_ms": 10000},
}
