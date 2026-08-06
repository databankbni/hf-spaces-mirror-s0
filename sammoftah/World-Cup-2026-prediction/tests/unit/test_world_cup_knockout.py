from datetime import datetime

import pytest

from underdog_lab.world_cup.data import TournamentRepository


def test_repository_exposes_group_and_knockout_fixture_sets():
    repository = TournamentRepository()

    assert len(repository.fixtures) == 72
    assert len(repository.knockout_fixtures) == 32
    assert len(repository.tournament_fixtures) == 104
    assert {fixture.match_number for fixture in repository.knockout_fixtures} == set(
        range(73, 105)
    )


def test_repository_reflects_played_semifinals_and_final():
    repository = TournamentRepository()

    semifinal_1 = next(
        fixture for fixture in repository.knockout_fixtures if fixture.match_number == 101
    )
    semifinal_2 = next(
        fixture for fixture in repository.knockout_fixtures if fixture.match_number == 102
    )
    third_place = next(
        fixture for fixture in repository.knockout_fixtures if fixture.match_number == 103
    )
    final = next(
        fixture for fixture in repository.knockout_fixtures if fixture.match_number == 104
    )

    assert semifinal_1.stage == "semifinal"
    assert {semifinal_1.home, semifinal_1.away} == {"Spain", "France"}
    assert sorted((semifinal_1.home_goals, semifinal_1.away_goals)) == [0, 2]
    assert semifinal_1.winner == "Spain"
    assert semifinal_2.stage == "semifinal"
    assert {semifinal_2.home, semifinal_2.away} == {"England", "Argentina"}
    assert sorted((semifinal_2.home_goals, semifinal_2.away_goals)) == [1, 2]
    assert semifinal_2.winner == "Argentina"
    assert third_place.stage == "third_place"
    assert third_place.home == "France"
    assert third_place.away == "England"
    assert final.stage == "final"
    assert final.home == "Spain"
    assert final.away == "Argentina"
    assert final.played
    assert (final.home_goals, final.away_goals) == (1, 0)
    assert final.winner == "Spain"
    assert final.provider_status == "STATUS_FINAL_AET"


def test_knockout_fixture_rejects_invalid_match_number():
    from underdog_lab.world_cup.models import KnockoutFixture

    with pytest.raises(ValueError):
        KnockoutFixture(
            fixture_id="WC26-072",
            match_number=72,
            stage="final",
            date="2026-07-19",
            kickoff_utc=datetime.fromisoformat("2026-07-19T19:00:00+00:00"),
            home="Spain",
            away="England",
        )
