from datetime import date

import pytest

from underdog_lab.world_cup.awards import (
    GOALKEEPER_ATTRIBUTES,
    OUTFIELD_ATTRIBUTES,
    award_predictions,
    card_attributes,
    deep_run_weight,
    expected_matches_played,
    golden_ball_rankings,
    golden_boot_rankings,
    golden_glove_rankings,
    load_players,
    young_player_rankings,
)
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.simulation import simulate_tournament


@pytest.fixture(scope="module")
def repository() -> TournamentRepository:
    return TournamentRepository()


@pytest.fixture(scope="module")
def probabilities(repository: TournamentRepository) -> dict[str, dict[str, float]]:
    return simulate_tournament(repository, iterations=200, seed=1)


def test_players_reference_real_teams(repository: TournamentRepository) -> None:
    data = load_players()
    team_names = {team.team for team in repository.teams}
    for player in data["players"]:
        assert player["team"] in team_names


def test_players_have_complete_card_attributes() -> None:
    data = load_players()
    for player in data["players"]:
        expected_keys = {key for key, _ in card_attributes(player)}
        assert set(player["attributes"]) == expected_keys
        for value in player["attributes"].values():
            assert 1 <= value <= 99
        assert 1 <= player["overall_rating"] <= 99
        assert 1 <= player["potential_rating"] <= 99
        assert player["potential_rating"] >= player["overall_rating"]


def test_card_attributes_match_position() -> None:
    outfield = {"name": "x", "position": "FW"}
    goalkeeper = {"name": "y", "position": "GK"}
    assert card_attributes(outfield) == OUTFIELD_ATTRIBUTES
    assert card_attributes(goalkeeper) == GOALKEEPER_ATTRIBUTES


def test_expected_matches_played_is_at_least_three() -> None:
    team_probabilities = {
        "advance": 0.0,
        "round_of_16": 0.0,
        "quarterfinal": 0.0,
        "semifinal": 0.0,
        "final": 0.0,
        "champion": 0.0,
    }
    assert expected_matches_played(team_probabilities) == 3.0


def test_deep_run_weight_increases_with_knockout_success() -> None:
    shallow = {"semifinal": 0.0, "final": 0.0, "champion": 0.0}
    deep = {"semifinal": 0.4, "final": 0.2, "champion": 0.1}
    assert deep_run_weight(deep) > deep_run_weight(shallow)


def test_golden_boot_excludes_goalkeepers_and_zero_goal_rate(
    probabilities: dict[str, dict[str, float]],
) -> None:
    data = load_players()
    rankings = golden_boot_rankings(data["players"], probabilities)
    assert rankings
    for row in rankings:
        assert row["position"] != "GK"
        assert row["goal_rate"] > 0


def test_golden_glove_only_includes_goalkeepers(
    probabilities: dict[str, dict[str, float]],
) -> None:
    data = load_players()
    rankings = golden_glove_rankings(data["players"], probabilities)
    assert rankings
    for row in rankings:
        assert row["position"] == "GK"


def test_golden_ball_excludes_goalkeepers(
    probabilities: dict[str, dict[str, float]],
) -> None:
    data = load_players()
    rankings = golden_ball_rankings(data["players"], probabilities)
    assert rankings
    for row in rankings:
        assert row["position"] != "GK"


def test_young_player_rankings_respect_birth_date_cutoff(
    probabilities: dict[str, dict[str, float]],
) -> None:
    data = load_players()
    cutoff = date.fromisoformat(data["young_player_cutoff"])
    rankings = young_player_rankings(data["players"], probabilities, cutoff)
    assert rankings
    for row in rankings:
        assert date.fromisoformat(row["birth_date"]) >= cutoff
        assert row["position"] != "GK"


def test_rankings_are_sorted_and_form_rating_in_range(
    probabilities: dict[str, dict[str, float]],
) -> None:
    data = load_players()
    rankings = golden_boot_rankings(data["players"], probabilities)
    indices = [row["index"] for row in rankings]
    assert indices == sorted(indices, reverse=True)
    for row in rankings:
        assert 35 <= row["form_rating"] <= 99
    assert rankings[0]["form_rating"] == 99


def test_award_predictions_returns_all_categories(
    probabilities: dict[str, dict[str, float]],
) -> None:
    predictions = award_predictions(probabilities)
    assert set(predictions) == {
        "golden_ball",
        "golden_boot",
        "golden_glove",
        "young_player",
    }
    for rankings in predictions.values():
        assert rankings
