from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from underdog_lab.config import ROOT
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.integrity import (
    SnapshotIntegrityError,
    validate_snapshot_integrity,
)
from underdog_lab.world_cup.predictions import audit_forecasts

RESULT_GRACE_PERIOD = timedelta(hours=4)


def application_health(
    root: Path = ROOT,
    *,
    now: datetime | None = None,
    ignore_overdue_results: bool = False,
) -> dict:
    now = now or datetime.now(timezone.utc)
    repository = TournamentRepository(root / "data/world_cup_2026")
    checks: dict[str, bool] = {
        "teams_48": len(repository.teams) == 48,
        "fixtures_72": len(repository.fixtures) == 72,
        "all_kickoffs_present": all(
            fixture.kickoff_utc is not None for fixture in repository.fixtures
        ),
        "kickoff_ids_complete": (
            set(repository.kickoff_by_fixture)
            == {fixture.fixture_id for fixture in repository.fixtures}
        ),
    }
    errors = []
    try:
        validate_snapshot_integrity(repository, now=now)
        checks["snapshot_integrity"] = True
    except SnapshotIntegrityError as error:
        checks["snapshot_integrity"] = False
        errors.append(str(error))

    forecast_audit = audit_forecasts(
        repository.tournament_fixtures,
        root / "predictions",
    )
    invalid_artifact_reasons = {
        "invalid_json",
        "invalid_manifest",
        "invalid_provenance",
        "invalid_probabilities",
        "invalid_timestamp",
        "future_cutoff",
        "post_kickoff",
        "unknown_fixture",
    }
    artifact_failures = [
        record
        for record in forecast_audit["rejected"]
        if record["reason"] in invalid_artifact_reasons
    ]
    checks["forecast_manifests_valid"] = not artifact_failures
    errors.extend(
        f"Invalid forecast artifact ({record['reason']}): {record['path']}"
        for record in artifact_failures
    )

    overdue_results = [
        fixture.fixture_id
        for fixture in repository.fixtures
        if (
            not fixture.played
            and fixture.kickoff_utc is not None
            and fixture.kickoff_utc + RESULT_GRACE_PERIOD <= now
        )
    ]
    checks["results_current"] = not overdue_results
    if overdue_results:
        errors.append(
            "Results overdue after four-hour grace period: "
            + ", ".join(overdue_results)
        )

    cutoff = datetime.fromisoformat(
        repository.snapshot["information_cutoff"].replace("Z", "+00:00")
    )
    age_hours = (now - cutoff).total_seconds() / 3600.0
    latest_result_update = _latest_result_update(
        root / "data/world_cup_2026/result_updates"
    )
    gating_checks = checks
    if ignore_overdue_results:
        gating_checks = {
            name: value for name, value in checks.items() if name != "results_current"
        }
    return {
        "status": "healthy" if all(gating_checks.values()) else "unhealthy",
        "checked_at": now.isoformat(),
        "information_cutoff": cutoff.isoformat(),
        "snapshot_age_hours": age_hours,
        "recorded_results": sum(fixture.played for fixture in repository.fixtures),
        "eligible_prospective_forecasts": len(forecast_audit["eligible"]),
        "forecast_artifact_audit": forecast_audit["counts"],
        "overdue_result_fixtures": overdue_results,
        "latest_result_update": latest_result_update,
        "repository_revision": _repository_revision(root),
        "checks": checks,
        "errors": errors,
    }


def _latest_result_update(directory: Path) -> dict | None:
    updates = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not updates:
        return None
    path = updates[-1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "status": "unreadable"}
    return {
        "path": str(path),
        "provider": payload.get("provider"),
        "fetched_at": payload.get("fetched_at"),
        "raw_response_sha256": payload.get("raw_response_sha256"),
    }


def _repository_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()
