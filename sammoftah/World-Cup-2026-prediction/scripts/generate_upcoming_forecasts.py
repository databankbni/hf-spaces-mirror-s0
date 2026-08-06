from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from underdog_lab.release.live_forecast import generate_live_forecast
from underdog_lab.world_cup.data import TournamentRepository


def output_directory(root: Path, fixture, generated_at: datetime) -> Path:
    generated = generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    return root / fixture.fixture_id / generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("predictions/live"),
    )
    parser.add_argument(
        "--within-hours",
        type=float,
        help="Only generate fixtures kicking off within this horizon.",
    )
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    repository = TournamentRepository()
    generated = 0
    skipped = 0
    for fixture in repository.fixtures:
        if fixture.played or fixture.kickoff_utc <= now:
            continue
        horizon_hours = (fixture.kickoff_utc - now).total_seconds() / 3600.0
        if args.within_hours is not None and horizon_hours > args.within_hours:
            continue
        output_dir = output_directory(args.output_root, fixture, now)
        if output_dir.exists():
            skipped += 1
            continue
        generate_live_forecast(
            fixture.fixture_id,
            output_dir,
            now=now,
        )
        generated += 1
    print(f"Generated {generated} immutable forecast(s); skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
