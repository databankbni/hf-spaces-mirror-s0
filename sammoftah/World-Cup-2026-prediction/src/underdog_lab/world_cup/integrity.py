from __future__ import annotations

from datetime import datetime, timezone

from underdog_lab.world_cup.data import TournamentRepository


class SnapshotIntegrityError(ValueError):
    """Raised when a snapshot would produce a non-pre-registered forecast."""


def validate_snapshot_integrity(
    repo: TournamentRepository,
    now: datetime | None = None,
) -> None:
    """Check that ``repo.snapshot`` can back a pre-registered forecast.

    Two things must hold for ``generated_at < information_cutoff < kickoff_at``
    (predictions/README.md, rule 4) to be satisfiable:

    1. ``information_cutoff`` must not be in the future relative to the
       generation time, otherwise the snapshot claims knowledge it cannot
       yet have.
    2. Any fixture whose date is on or before ``information_cutoff`` must
       already have a recorded result. Otherwise the snapshot is internally
       inconsistent: it claims information up to a date by which a match
       concluded, yet that match would still be forecast as "upcoming".
    """
    now = now or datetime.now(timezone.utc)
    cutoff = datetime.fromisoformat(
        repo.snapshot["information_cutoff"].replace("Z", "+00:00")
    )

    if cutoff > now:
        raise SnapshotIntegrityError(
            f"information_cutoff {cutoff.isoformat()} is in the future "
            f"relative to generation time {now.isoformat()}."
        )

    missing_results = [
        fixture.fixture_id
        for fixture in repo.fixtures
        if (
            fixture.kickoff_utc is not None
            and fixture.kickoff_utc <= cutoff
            and not fixture.played
        )
    ]
    if missing_results:
        raise SnapshotIntegrityError(
            "information_cutoff "
            f"{cutoff.isoformat()} implies results are known for "
            f"{', '.join(missing_results)}, but snapshot['results'] has no "
            "entry for them. Add the results or move information_cutoff "
            "earlier before generating a forecast."
        )
