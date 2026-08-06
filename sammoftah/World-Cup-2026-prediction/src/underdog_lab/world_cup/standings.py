from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from underdog_lab.world_cup.models import Standing, TournamentFixture


Result = tuple[str, str, int, int]


def _head_to_head_key(team: str, tied: set[str], results: Sequence[Result]):
    points = goals_for = goals_against = 0
    for home, away, home_goals, away_goals in results:
        if home not in tied or away not in tied:
            continue
        if team == home:
            goals_for += home_goals
            goals_against += away_goals
            points += 3 if home_goals > away_goals else 1 if home_goals == away_goals else 0
        elif team == away:
            goals_for += away_goals
            goals_against += home_goals
            points += 3 if away_goals > home_goals else 1 if away_goals == home_goals else 0
    return points, goals_for - goals_against, goals_for


def rank_standings(
    table: Mapping[str, Standing],
    results: Sequence[Result],
    fifa_ranks: Mapping[str, int] | None = None,
    fair_play_points: Mapping[str, int] | None = None,
) -> list[Standing]:
    fifa_ranks = fifa_ranks or {}
    fair_play_points = fair_play_points or {}
    by_points: dict[int, list[Standing]] = defaultdict(list)
    for row in table.values():
        by_points[row.points].append(row)

    def resolve_equal_points(rows: list[Standing]) -> list[Standing]:
        if len(rows) < 2:
            return rows
        tied = {row.team for row in rows}
        by_head_to_head: dict[tuple[int, int, int], list[Standing]] = defaultdict(list)
        for row in rows:
            by_head_to_head[_head_to_head_key(row.team, tied, results)].append(row)
        if len(by_head_to_head) > 1:
            resolved = []
            for key in sorted(by_head_to_head, reverse=True):
                resolved.extend(resolve_equal_points(by_head_to_head[key]))
            return resolved
        return sorted(
            rows,
            key=lambda row: (
                -row.goal_difference,
                -row.goals_for,
                fair_play_points.get(row.team, 0),
                fifa_ranks.get(row.team, 10_000),
                row.team,
            ),
        )

    ranked = []
    for points in sorted(by_points, reverse=True):
        ranked.extend(resolve_equal_points(by_points[points]))
    return ranked


def calculate_standings(
    teams: list[str],
    fixtures: list[TournamentFixture],
    fifa_ranks: Mapping[str, int] | None = None,
) -> list[Standing]:
    table = {team: Standing(team=team) for team in teams}
    results = []
    for fixture in fixtures:
        if not fixture.played:
            continue
        results.append(
            (
                fixture.home,
                fixture.away,
                fixture.home_goals or 0,
                fixture.away_goals or 0,
            )
        )
        home = table[fixture.home]
        away = table[fixture.away]
        home.played += 1
        away.played += 1
        home.goals_for += fixture.home_goals or 0
        home.goals_against += fixture.away_goals or 0
        away.goals_for += fixture.away_goals or 0
        away.goals_against += fixture.home_goals or 0
        if fixture.home_goals > fixture.away_goals:
            home.wins += 1
            away.losses += 1
            home.points += 3
        elif fixture.home_goals < fixture.away_goals:
            away.wins += 1
            home.losses += 1
            away.points += 3
        else:
            home.draws += 1
            away.draws += 1
            home.points += 1
            away.points += 1
    return rank_standings(table, results, fifa_ranks=fifa_ranks)
