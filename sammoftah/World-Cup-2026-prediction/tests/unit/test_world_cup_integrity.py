from datetime import datetime, timezone
from pathlib import Path

import pytest

from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.integrity import (
    SnapshotIntegrityError,
    validate_snapshot_integrity,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "world_cup"


def test_current_snapshot_is_internally_consistent():
    repo = TournamentRepository()
    validate_snapshot_integrity(repo)


def test_frozen_current_snapshot_is_internally_consistent():
    repo = TournamentRepository(
        snapshot_path=FIXTURES / "current_snapshot.json"
    )
    validate_snapshot_integrity(
        repo,
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
    )


def test_future_dated_cutoff_is_rejected():
    repo = TournamentRepository()
    repo.snapshot = dict(repo.snapshot)
    repo.snapshot["information_cutoff"] = "2099-01-01T00:00:00Z"

    with pytest.raises(SnapshotIntegrityError, match="future"):
        validate_snapshot_integrity(repo)


def test_missing_result_for_decided_fixture_is_rejected():
    repo = TournamentRepository(snapshot_path=FIXTURES / "current_snapshot.json")
    repo.snapshot = dict(repo.snapshot)
    repo.snapshot["information_cutoff"] = "2026-06-14T18:00:00Z"

    now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    with pytest.raises(SnapshotIntegrityError, match="WC26-025"):
        validate_snapshot_integrity(repo, now=now)
