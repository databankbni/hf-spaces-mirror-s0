from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import pandas as pd


class ExperimentTracker:
    def __init__(self, result_path: str | Path):
        self.result_path = Path(result_path)
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        if self.result_path.exists():
            self.results = pd.read_csv(self.result_path)
        else:
            self.results = pd.DataFrame()

    def is_done(self, task: str, model_name: str, feature_set: str, phase: str) -> bool:
        if self.results.empty:
            return False
        mask = (
            (self.results["task"] == task)
            & (self.results["model_name"] == model_name)
            & (self.results["feature_set"] == feature_set)
            & (self.results["phase"] == phase)
            & (self.results["status"] == "completed")
        )
        return bool(mask.any())

    def append(self, record: dict) -> None:
        row = pd.DataFrame([record])
        self.results = pd.concat([self.results, row], ignore_index=True)
        self.results.to_csv(self.result_path, index=False, encoding="utf-8-sig")


class Timer:
    def __enter__(self):
        self.start = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.end = perf_counter()
        self.duration_seconds = self.end - self.start


def write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

