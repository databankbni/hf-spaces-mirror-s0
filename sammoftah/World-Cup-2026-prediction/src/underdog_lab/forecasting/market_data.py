"""Validation and loading for timestamped 1X2 market snapshots."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value}")
    return parsed


def load_odds_csv(
    path: Path,
    horizon: str,
) -> dict[tuple[date, str, str], dict]:
    required = {
        "date",
        "home_team",
        "away_team",
        "kickoff_utc",
        "captured_at",
        "horizon",
        "home_odds",
        "draw_odds",
        "away_odds",
    }
    rows: dict[tuple[date, str, str], dict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"odds CSV is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            if row["horizon"] != horizon:
                continue
            kickoff = _parse_timestamp(row["kickoff_utc"])
            captured = _parse_timestamp(row["captured_at"])
            if captured >= kickoff:
                raise ValueError(
                    f"line {line_number}: captured_at must be before kickoff_utc"
                )
            match_date = date.fromisoformat(row["date"])
            key = (match_date, row["home_team"], row["away_team"])
            if key in rows:
                raise ValueError(
                    f"duplicate {horizon} odds row for {key} on line {line_number}"
                )
            rows[key] = {
                "decimal_odds": (
                    float(row["home_odds"]),
                    float(row["draw_odds"]),
                    float(row["away_odds"]),
                ),
                "captured_at": captured.isoformat(),
                "kickoff_utc": kickoff.isoformat(),
            }
    return rows
