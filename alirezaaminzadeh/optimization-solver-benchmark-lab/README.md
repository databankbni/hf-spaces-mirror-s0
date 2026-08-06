---
title: Optimization Solver Benchmark Lab
emoji: ⚖️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.50.0
app_file: app.py
short_description: Benchmark OR solvers with meta-model advisor
python_version: "3.12"
pinned: false
license: mit
---

# Optimization Solver Benchmark Lab

**Aria AI Operations Research Team** — Compare optimization solvers across 9 benchmark problem families with a meta-model that recommends the best solver and configuration for each instance.

## Features

- **9 Benchmark Problems:** Knapsack, TSP, VRP, Job Shop, Bin Packing, Facility Location, Set Cover, Assignment, Maximum Independent Set
- **6 Solvers:** HiGHS, CBC, OR-Tools CP-SAT, SCIP, Gurobi, MiniZinc
- **9 Metrics:** Solution quality, optimality gap, time to first feasible, time to best, total time, memory, B&B nodes, stability, scalability
- **Meta-Model Advisor:** Predicts best solver + config from instance features

## Live Solvers

HiGHS, CBC, and CP-SAT run directly in this Space. Reference solvers (Gurobi, SCIP, MiniZinc) use calibrated benchmark profiles.

## Links

- [Aria AI](https://aria-ai.ir)
- [Dataset](https://huggingface.co/datasets/alirezaaminzadeh/solvbench-benchmark-data)
- [Meta-Model](https://huggingface.co/alirezaaminzadeh/solvbench-metamodel)
