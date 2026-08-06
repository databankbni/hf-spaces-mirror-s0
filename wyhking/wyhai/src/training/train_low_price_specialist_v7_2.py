#!/usr/bin/env python3
"""Thin entrypoint for the v7.2 low-price specialist experiment.

The implementation lives in `run_v7_2_experiments.py` so the feature handling,
metrics and output schema stay identical to the main model run.
"""
from run_v7_2_experiments import main

if __name__ == "__main__":
    main()
