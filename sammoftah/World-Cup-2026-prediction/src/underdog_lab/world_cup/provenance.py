from __future__ import annotations

import hashlib
import json
from pathlib import Path

from underdog_lab.config import DATA_DIR
from underdog_lab.world_cup.forecasting import CALIBRATION_TEMPERATURE

MODEL_VERSION = "elo-dixon-coles-180d-temperature-v1"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forecast_provenance() -> dict:
    root = DATA_DIR / "world_cup_2026"
    return {
        "model_version": MODEL_VERSION,
        "calibration_temperature": CALIBRATION_TEMPERATURE,
        "team_ratings_sha256": file_sha256(root / "teams.json"),
        "snapshot_sha256": file_sha256(root / "snapshot.json"),
        "scoreline_probability_note": (
            "Exact-score probabilities come from the fitted Dixon-Coles score "
            "matrix; temperature scaling applies only to the displayed 1X2 "
            "probabilities."
        ),
    }


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
