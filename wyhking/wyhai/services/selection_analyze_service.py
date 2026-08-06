from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_strategy_ablation import DEFAULT_OUTPUT_DIR, run_selection_strategy_ablation


REPORT_PATH = DEFAULT_OUTPUT_DIR / "selection_strategy_ablation_report.json"


def get_selection_strategy_lab_report(*, force: bool = False) -> dict[str, Any]:
    if not force and REPORT_PATH.is_file():
        try:
            return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return run_selection_strategy_ablation(write_files=True)


def get_selection_strategy_lab_summary(*, force: bool = False) -> dict[str, Any]:
    report = get_selection_strategy_lab_report(force=force)
    return {
        "baseline_all": report.get("baseline_all"),
        "strategy_results": [
            {
                "strategy_name": item.get("strategy_name"),
                "used_signals": item.get("used_signals"),
                "metrics": item.get("metrics"),
                "lifts": item.get("lifts"),
                "recommend_pass": item.get("recommend_pass"),
                "scale_pass": item.get("scale_pass"),
                "strategy_score": item.get("strategy_score"),
                "top20": (item.get("topk_evaluation") or {}).get("top20"),
            }
            for item in report.get("strategy_results", [])
        ],
        "dsi_increment": report.get("dsi_increment"),
        "ranking_increment": report.get("ranking_increment"),
        "final_recommendation": report.get("final_recommendation"),
        "artifacts": report.get("artifacts"),
    }
