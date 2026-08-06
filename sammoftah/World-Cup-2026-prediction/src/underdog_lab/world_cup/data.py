from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from underdog_lab.config import DATA_DIR
from underdog_lab.world_cup.models import (
    KnockoutFixture,
    TournamentFixture,
    TournamentTeam,
)


GROUP_DATES = {
    "A": ("2026-06-11", "2026-06-18", "2026-06-24"),
    "B": ("2026-06-12", "2026-06-18", "2026-06-24"),
    "C": ("2026-06-13", "2026-06-19", "2026-06-24"),
    "D": ("2026-06-12", "2026-06-19", "2026-06-25"),
    "E": ("2026-06-14", "2026-06-20", "2026-06-25"),
    "F": ("2026-06-14", "2026-06-20", "2026-06-25"),
    "G": ("2026-06-15", "2026-06-21", "2026-06-26"),
    "H": ("2026-06-15", "2026-06-21", "2026-06-26"),
    "I": ("2026-06-16", "2026-06-22", "2026-06-26"),
    "J": ("2026-06-16", "2026-06-22", "2026-06-27"),
    "K": ("2026-06-17", "2026-06-23", "2026-06-27"),
    "L": ("2026-06-17", "2026-06-23", "2026-06-27"),
}

PAIRINGS = (
    ((1, 2), (3, 4)),
    ((4, 2), (1, 3)),
    ((4, 1), (2, 3)),
)

FIXTURE_DATE_OVERRIDES = {
    ("B", 3, 4): "2026-06-13",
    ("D", 3, 4): "2026-06-13",
}

class TournamentRepository:
    def __init__(
        self,
        root: Path | None = None,
        *,
        snapshot_path: Path | None = None,
    ) -> None:
        root = root or DATA_DIR / "world_cup_2026"
        self.teams = [
            TournamentTeam.model_validate(row)
            for row in json.loads((root / "teams.json").read_text(encoding="utf-8"))
        ]
        snapshot_path = snapshot_path or root / "snapshot.json"
        self.snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.kickoff_schedule = json.loads(
            (root / "kickoffs.json").read_text(encoding="utf-8")
        )
        self.kickoff_by_fixture = self.kickoff_schedule["kickoff_utc"]
        self.team_by_name = {team.team: team for team in self.teams}
        self.fixtures = self._build_fixtures()
        knockout_path = root / "knockout.json"
        knockout_payload = json.loads(knockout_path.read_text(encoding="utf-8"))
        self.knockout_fixtures = [
            KnockoutFixture.model_validate(row)
            for row in knockout_payload["matches"]
        ]
        expected_numbers = set(range(73, 105))
        actual_numbers = {fixture.match_number for fixture in self.knockout_fixtures}
        if actual_numbers != expected_numbers:
            raise ValueError("knockout snapshot must contain matches 73 through 104")
        if len(self.knockout_fixtures) != 32:
            raise ValueError("knockout snapshot must contain exactly 32 matches")

    def _build_fixtures(self) -> list[TournamentFixture]:
        by_group: dict[str, dict[int, str]] = {}
        for team in self.teams:
            by_group.setdefault(team.group, {})[team.position] = team.team
        results = {
            (row["group"], row["home"], row["away"]): row
            for row in self.snapshot["results"]
        }
        fixtures = []
        match_number = 1
        for group in sorted(by_group):
            positions = by_group[group]
            for matchday, pairs in enumerate(PAIRINGS, start=1):
                for home_position, away_position in pairs:
                    home = positions[home_position]
                    away = positions[away_position]
                    result = results.get((group, home, away), {})
                    fixture_date = FIXTURE_DATE_OVERRIDES.get(
                        (group, home_position, away_position),
                        GROUP_DATES[group][matchday - 1],
                    )
                    fixture_id = f"WC26-{match_number:03d}"
                    kickoff = self.kickoff_by_fixture.get(fixture_id)
                    fixtures.append(
                        TournamentFixture(
                            fixture_id=fixture_id,
                            group=group,
                            matchday=matchday,
                            date=date.fromisoformat(fixture_date),
                            kickoff_utc=(
                                datetime.fromisoformat(
                                    kickoff.replace("Z", "+00:00")
                                )
                                if kickoff
                                else None
                            ),
                            home=home,
                            away=away,
                            home_goals=result.get("home_goals"),
                            away_goals=result.get("away_goals"),
                        )
                    )
                    match_number += 1
        return fixtures

    def group_teams(self, group: str) -> list[TournamentTeam]:
        return sorted(
            (team for team in self.teams if team.group == group),
            key=lambda team: team.position,
        )

    def group_fixtures(self, group: str) -> list[TournamentFixture]:
        return [fixture for fixture in self.fixtures if fixture.group == group]

    @property
    def tournament_fixtures(self) -> list[TournamentFixture | KnockoutFixture]:
        return [*self.fixtures, *self.knockout_fixtures]
