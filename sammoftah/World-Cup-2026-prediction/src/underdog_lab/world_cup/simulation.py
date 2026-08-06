from __future__ import annotations

import random
from collections import Counter, defaultdict
from underdog_lab.world_cup.bracket import KNOCKOUT_PATH, build_round_of_32
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.forecasting import (
    calibrated_scoreline_matrix,
    knockout_advance_probability,
    match_forecast,
)
from underdog_lab.world_cup.models import Standing
from underdog_lab.world_cup.standings import rank_standings


def _scoreline_sampler(forecast) -> list[tuple[float, int, int]]:
    """Cumulative distribution over (home_goals, away_goals) scorelines.

    Sampling the joint Dixon-Coles matrix (rather than two independent
    Poisson draws) keeps the simulated draw rate consistent with the fitted
    low-score correlation and the calibrated 1X2 probabilities.
    """
    cumulative = 0.0
    table = []
    for i, row in enumerate(calibrated_scoreline_matrix(forecast)):
        for j, probability in enumerate(row):
            cumulative += probability
            table.append((cumulative, i, j))
    return table


def _sample_scoreline(
    table: list[tuple[float, int, int]],
    rng: random.Random,
) -> tuple[int, int]:
    threshold = rng.random() * table[-1][0]
    for cumulative, home_goals, away_goals in table:
        if threshold <= cumulative:
            return home_goals, away_goals
    return table[-1][1], table[-1][2]


def _apply_result(table, home, away, home_goals, away_goals):
    h, a = table[home], table[away]
    h.played += 1
    a.played += 1
    h.goals_for += home_goals
    h.goals_against += away_goals
    a.goals_for += away_goals
    a.goals_against += home_goals
    if home_goals > away_goals:
        h.wins += 1
        a.losses += 1
        h.points += 3
    elif home_goals < away_goals:
        a.wins += 1
        h.losses += 1
        a.points += 3
    else:
        h.draws += 1
        a.draws += 1
        h.points += 1
        a.points += 1


def _knockout_win_probability(
    first: str,
    second: str,
    repository: TournamentRepository,
) -> float:
    return knockout_advance_probability(first, second, repository.team_by_name)


def _recorded_knockout_winner(
    match: int,
    first: str,
    second: str,
    repository: TournamentRepository,
) -> str | None:
    """Return a recorded winner only when the live bracket agrees with the simulation slot."""
    fixture = next(
        (item for item in repository.knockout_fixtures if item.match_number == match),
        None,
    )
    if fixture is None or not fixture.played or fixture.winner is None:
        return None
    return fixture.winner


def simulate_tournament(
    repository: TournamentRepository,
    iterations: int = 3000,
    seed: int = 20260612,
) -> dict[str, dict[str, float]]:
    rng = random.Random(seed)
    counts = defaultdict(Counter)
    groups = sorted({team.group for team in repository.teams})
    samplers: dict[str, list[tuple[float, int, int]]] = {}
    for group in groups:
        for fixture in repository.group_fixtures(group):
            if not fixture.played:
                samplers[fixture.fixture_id] = _scoreline_sampler(
                    match_forecast(fixture, repository.team_by_name)
                )
    group_by_team = {team.team: team.group for team in repository.teams}
    fifa_ranks = {team.team: team.rank for team in repository.teams}

    for _ in range(iterations):
        ranked_groups = {}
        thirds = []
        for group in groups:
            teams = [team.team for team in repository.group_teams(group)]
            table = {team: Standing(team=team) for team in teams}
            results = []
            for fixture in repository.group_fixtures(group):
                if fixture.played:
                    home_goals = fixture.home_goals or 0
                    away_goals = fixture.away_goals or 0
                else:
                    home_goals, away_goals = _sample_scoreline(
                        samplers[fixture.fixture_id], rng
                    )
                _apply_result(
                    table,
                    fixture.home,
                    fixture.away,
                    home_goals,
                    away_goals,
                )
                results.append(
                    (fixture.home, fixture.away, home_goals, away_goals)
                )
            ranked = rank_standings(table, results, fifa_ranks=fifa_ranks)
            ranked_groups[group] = ranked
            counts[ranked[0].team]["group_winner"] += 1
            counts[ranked[0].team]["advance"] += 1
            counts[ranked[1].team]["advance"] += 1
            thirds.append(ranked[2])

        best_thirds = sorted(
            thirds,
            key=lambda row: (
                -row.points,
                -row.goal_difference,
                -row.goals_for,
                fifa_ranks.get(row.team, 10_000),
                row.team,
            ),
        )[:8]
        for row in best_thirds:
            counts[row.team]["advance"] += 1

        winners_by_match = {}
        for match, first, second in build_round_of_32(
            ranked_groups,
            best_thirds,
            group_by_team,
        ):
            winner = _recorded_knockout_winner(match, first, second, repository)
            if winner is None:
                probability_first = _knockout_win_probability(first, second, repository)
                winner = first if rng.random() < probability_first else second
            winners_by_match[match] = winner
            counts[winner]["round_of_16"] += 1

        for round_name, matches in KNOCKOUT_PATH.items():
            for match, first_match, second_match in matches:
                first = winners_by_match[first_match]
                second = winners_by_match[second_match]
                winner = _recorded_knockout_winner(match, first, second, repository)
                if winner is None:
                    probability_first = _knockout_win_probability(first, second, repository)
                    winner = first if rng.random() < probability_first else second
                winners_by_match[match] = winner
                advancement = {
                    "round_of_16": "quarterfinal",
                    "quarterfinal": "semifinal",
                    "semifinal": "final",
                    "champion": "champion",
                }[round_name]
                counts[winner][advancement] += 1

    return {
        team.team: {
            metric: counts[team.team][metric] / iterations
            for metric in (
                "group_winner",
                "advance",
                "round_of_16",
                "quarterfinal",
                "semifinal",
                "final",
                "champion",
            )
        }
        for team in repository.teams
    }
