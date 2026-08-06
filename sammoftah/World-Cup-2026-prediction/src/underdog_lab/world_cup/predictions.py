from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from underdog_lab.domain import UserForecast
from underdog_lab.forecasting.scoring import (
    brier_score,
    log_loss,
    rank_probability_score,
)
from underdog_lab.world_cup.forecasting import match_forecast
from underdog_lab.world_cup.models import TournamentFixture

SUPPORTED_SCHEMA_VERSIONS = {"live-forecast-v2"}
LEGACY_PROOF_FIXTURES = {"WC26-008"}
HORIZON_ORDER = ("final", "6h", "24h", "long_range")


def forecast_horizon(seconds: int) -> str:
    if seconds <= 2 * 3600:
        return "final"
    if seconds <= 6 * 3600:
        return "6h"
    if seconds <= 24 * 3600:
        return "24h"
    return "long_range"


def audit_forecasts(
    fixtures: list[TournamentFixture],
    predictions_dir: Path = Path("predictions"),
) -> dict:
    fixture_by_id = {fixture.fixture_id: fixture for fixture in fixtures}
    records = []
    if not predictions_dir.exists():
        return {"eligible": [], "rejected": [], "counts": {}}

    for forecast_file in sorted(predictions_dir.rglob("forecast.json")):
        try:
            data = json.loads(forecast_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            records.append(_audit_record(forecast_file, reason="invalid_json"))
            continue
        generated_at = _parse_timestamp(data.get("generated_at"))
        cutoff = _parse_timestamp(data.get("information_cutoff"))
        for prediction in data.get("fixtures", []):
            fixture_id = prediction.get("fixture_id")
            fixture = fixture_by_id.get(fixture_id)
            reason = _eligibility_reason(
                forecast_file,
                data,
                prediction,
                fixture,
                generated_at,
                cutoff,
            )
            horizon_seconds = (
                int((fixture.kickoff_utc - generated_at).total_seconds())
                if fixture is not None
                and fixture.kickoff_utc is not None
                and generated_at is not None
                else None
            )
            records.append(
                _audit_record(
                    forecast_file,
                    fixture_id=fixture_id,
                    reason=reason,
                    horizon=(
                        forecast_horizon(horizon_seconds)
                        if horizon_seconds is not None and horizon_seconds > 0
                        else None
                    ),
                    horizon_seconds=horizon_seconds,
                    payload=data,
                    prediction=prediction,
                )
            )
    eligible = [record for record in records if record["reason"] == "eligible"]
    rejected = [record for record in records if record["reason"] != "eligible"]
    return {
        "eligible": eligible,
        "rejected": rejected,
        "counts": dict(Counter(record["reason"] for record in records)),
    }


def eligible_forecasts(
    fixtures: list[TournamentFixture],
    predictions_dir: Path = Path("predictions"),
) -> dict[str, dict]:
    """Return the latest eligible forecast for each fixture."""
    selected: dict[str, dict] = {}
    for record in audit_forecasts(fixtures, predictions_dir)["eligible"]:
        current = selected.get(record["fixture_id"])
        if current is None or record["generated_at"] > current["generated_at"]:
            selected[record["fixture_id"]] = record
    return selected


def eligible_forecasts_by_horizon(
    fixtures: list[TournamentFixture],
    predictions_dir: Path = Path("predictions"),
) -> dict[str, dict[str, dict]]:
    selected: dict[str, dict[str, dict]] = {}
    for record in audit_forecasts(fixtures, predictions_dir)["eligible"]:
        horizon_rows = selected.setdefault(record["horizon"], {})
        current = horizon_rows.get(record["fixture_id"])
        if current is None or record["generated_at"] > current["generated_at"]:
            horizon_rows[record["fixture_id"]] = record
    return selected


def scored_track_records(
    fixtures: list[TournamentFixture],
    team_by_name: dict,
    predictions_dir: Path = Path("predictions"),
) -> dict[str, dict]:
    """Return prospective records by horizon plus a separate retrospective replay."""
    audit = audit_forecasts(fixtures, predictions_dir)
    archived = eligible_forecasts_by_horizon(fixtures, predictions_dir)
    prospective = {
        horizon: [] for horizon in HORIZON_ORDER
    }
    retrospective = []
    for fixture in fixtures:
        if not fixture.played:
            continue
        outcome = _outcome(fixture)
        replay = match_forecast(fixture, team_by_name)
        retrospective.append(
            _score_record(
                fixture,
                replay,
                outcome,
                source="Current-model retrospective replay",
            )
        )
        for horizon, forecasts in archived.items():
            prediction = forecasts.get(fixture.fixture_id)
            if prediction is None:
                continue
            forecast = UserForecast(
                p_home=prediction["p_home"],
                p_draw=prediction["p_draw"],
                p_away=prediction["p_away"],
            )
            prospective.setdefault(horizon, []).append(
                _score_record(
                    fixture,
                    forecast,
                    outcome,
                    source=f"Verified {horizon} artifact",
                    metadata=prediction,
                )
            )
    summaries = {
        horizon: _summarize(rows)
        for horizon, rows in prospective.items()
    }
    # Compatibility summary: one latest eligible forecast per played fixture.
    latest_rows = []
    latest = eligible_forecasts(fixtures, predictions_dir)
    for fixture in fixtures:
        prediction = latest.get(fixture.fixture_id)
        if not fixture.played or prediction is None:
            continue
        latest_rows.append(
            _score_record(
                fixture,
                UserForecast(
                    p_home=prediction["p_home"],
                    p_draw=prediction["p_draw"],
                    p_away=prediction["p_away"],
                ),
                _outcome(fixture),
                source="Latest verified pre-kickoff artifact",
                metadata=prediction,
            )
        )
    completed_fixture_ids = [
        fixture.fixture_id for fixture in fixtures if fixture.played
    ]
    scored_fixture_ids = {
        row["fixture_id"] for row in latest_rows
    }
    excluded_fixture_ids = sorted(
        set(completed_fixture_ids) - scored_fixture_ids
    )
    completed = len(completed_fixture_ids)
    return {
        "prospective": _summarize(latest_rows),
        "prospective_by_horizon": summaries,
        "retrospective": _summarize(retrospective),
        "coverage": {
            "completed": completed,
            "scored": len(scored_fixture_ids),
            "excluded": len(excluded_fixture_ids),
            "rate": len(scored_fixture_ids) / completed if completed else None,
            "excluded_fixture_ids": excluded_fixture_ids,
            "exclusion_reason": "no_verified_pre_kickoff_artifact",
        },
        "artifact_audit": {
            "eligible": len(audit["eligible"]),
            "rejected": len(audit["rejected"]),
            "counts": audit["counts"],
        },
    }


def _eligibility_reason(
    forecast_file: Path,
    data: dict,
    prediction: dict,
    fixture: TournamentFixture | None,
    generated_at: datetime | None,
    cutoff: datetime | None,
) -> str:
    if fixture is None:
        return "unknown_fixture"
    schema = data.get("schema_version")
    is_supported = schema in SUPPORTED_SCHEMA_VERSIONS
    is_legacy_proof = (
        fixture.fixture_id in LEGACY_PROOF_FIXTURES
        and "live" in forecast_file.parts
    )
    if not is_supported and not is_legacy_proof:
        return "unsupported_legacy"
    if generated_at is None or cutoff is None:
        return "invalid_timestamp"
    if cutoff > generated_at:
        return "future_cutoff"
    if fixture.kickoff_utc is None:
        return "missing_kickoff"
    if generated_at >= fixture.kickoff_utc:
        return "post_kickoff"
    if not _valid_probabilities(prediction):
        return "invalid_probabilities"

    if is_supported:
        if not _valid_manifest(forecast_file):
            return "invalid_manifest"
        if not _valid_provenance(data.get("provenance")):
            return "invalid_provenance"
        return "eligible"
    if is_legacy_proof and _valid_manifest(forecast_file):
        return "eligible"
    return "unsupported_legacy"


def _valid_manifest(forecast_file: Path) -> bool:
    manifest_path = forecast_file.with_name("manifest.json")
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        manifest.get("immutable") is True
        and manifest.get("file") == forecast_file.name
        and manifest.get("sha256")
        == hashlib.sha256(forecast_file.read_bytes()).hexdigest()
    )


def _valid_provenance(provenance: object) -> bool:
    if not isinstance(provenance, dict):
        return False
    required = (
        "model_version",
        "calibration_temperature",
        "team_ratings_sha256",
        "snapshot_sha256",
    )
    return (
        all(provenance.get(key) is not None for key in required)
        and len(str(provenance["team_ratings_sha256"])) == 64
        and len(str(provenance["snapshot_sha256"])) == 64
    )


def _valid_probabilities(prediction: dict) -> bool:
    try:
        values = [float(prediction[key]) for key in ("p_home", "p_draw", "p_away")]
    except (KeyError, TypeError, ValueError):
        return False
    return all(0.0 <= value <= 1.0 for value in values) and abs(sum(values) - 1.0) < 1e-5


def _audit_record(
    path: Path,
    *,
    fixture_id: str | None = None,
    reason: str,
    horizon: str | None = None,
    horizon_seconds: int | None = None,
    payload: dict | None = None,
    prediction: dict | None = None,
) -> dict:
    payload = payload or {}
    prediction = prediction or {}
    return {
        **prediction,
        "fixture_id": fixture_id,
        "reason": reason,
        "path": str(path),
        "horizon": horizon,
        "forecast_horizon_seconds": horizon_seconds,
        "forecast_date": payload.get("forecast_date", ""),
        "generated_at": payload.get("generated_at", ""),
        "information_cutoff": payload.get("information_cutoff", ""),
        "model": payload.get("model", "unknown"),
        "model_version": (payload.get("provenance") or {}).get(
            "model_version",
            "legacy",
        ),
    }


def _outcome(fixture: TournamentFixture) -> str:
    if fixture.home_goals > fixture.away_goals:
        return "home"
    if fixture.home_goals < fixture.away_goals:
        return "away"
    return "draw"


def _score_record(
    fixture: TournamentFixture,
    forecast,
    outcome: str,
    *,
    source: str,
    metadata: dict | None = None,
) -> dict:
    probabilities = {
        "home": forecast.p_home,
        "draw": forecast.p_draw,
        "away": forecast.p_away,
    }
    predicted_outcome = max(
        ("home", "draw", "away"),
        key=lambda name: probabilities[name],
    )
    return {
        "fixture_id": fixture.fixture_id,
        "group": getattr(fixture, "group", None) or getattr(fixture, "stage", "?"),
        "home": fixture.home,
        "away": fixture.away,
        "score": f"{fixture.home_goals}-{fixture.away_goals}",
        "outcome": outcome,
        "predicted_outcome": predicted_outcome,
        "correct": predicted_outcome == outcome,
        "p_home": forecast.p_home,
        "p_draw": forecast.p_draw,
        "p_away": forecast.p_away,
        "log_loss": log_loss(forecast, outcome),
        "brier": brier_score(forecast, outcome),
        "rps": rank_probability_score(forecast, outcome),
        "source": source,
        "metadata": metadata or {},
    }


def _summarize(rows: list[dict]) -> dict:
    uniform_log_loss = -math.log(1.0 / 3.0)
    if not rows:
        return {
            "n": 0,
            "correct": 0,
            "accuracy": None,
            "mean_log_loss": None,
            "mean_brier": None,
            "mean_rps": None,
            "uniform_log_loss": uniform_log_loss,
            "log_loss_skill_vs_uniform": None,
            "rows": [],
        }
    mean_log_loss = sum(row["log_loss"] for row in rows) / len(rows)
    correct = sum(bool(row["correct"]) for row in rows)
    return {
        "n": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "mean_log_loss": mean_log_loss,
        "mean_brier": sum(row["brier"] for row in rows) / len(rows),
        "mean_rps": sum(row["rps"] for row in rows) / len(rows),
        "uniform_log_loss": uniform_log_loss,
        "log_loss_skill_vs_uniform": 1 - mean_log_loss / uniform_log_loss,
        "rows": rows,
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
