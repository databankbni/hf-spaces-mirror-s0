import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.providers import (
    normalize_espn_knockout_response,
    normalize_espn_response,
    normalize_football_data_response,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "football_data_wc2026.json"
ESPN_FIXTURE = Path(__file__).parents[1] / "fixtures" / "espn_wc2026.json"
ESPN_KNOCKOUT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "espn_knockout_wc2026.json"
FROZEN_SNAPSHOT = Path(__file__).parents[1] / "fixtures" / "world_cup" / "current_snapshot.json"


def test_provider_response_maps_to_audited_update():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/football_data.json").read_text(
            encoding="utf-8"
        )
    )

    result = normalize_football_data_response(
        payload,
        TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
        mapping["aliases"],
        fetched_at=datetime(2026, 6, 14, 20, tzinfo=timezone.utc),
    )

    assert result["results"][0]["fixture_id"] == "WC26-025"
    assert result["results"][0]["home_goals"] == 2
    assert result["raw_response_sha256"]


def test_finished_match_without_score_is_skipped_not_fatal():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["matches"].append(
        {
            "id": 900026,
            "utcDate": "2026-06-14T23:00:00Z",
            "status": "FINISHED",
            "stage": "GROUP_STAGE",
            "group": "GROUP_E",
            "lastUpdated": "2026-06-14T23:05:00Z",
            "homeTeam": {"id": 3, "name": "Ivory Coast"},
            "awayTeam": {"id": 4, "name": "Ecuador"},
            "score": {"duration": "REGULAR", "fullTime": {"home": None, "away": None}},
        }
    )
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/football_data.json").read_text(
            encoding="utf-8"
        )
    )

    result = normalize_football_data_response(
        payload,
        TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
        mapping["aliases"],
        fetched_at=datetime(2026, 6, 15, 1, tzinfo=timezone.utc),
    )

    assert result["unscored_finished"] == ["WC26-026"]
    assert result["results"][0]["fixture_id"] == "WC26-025"


def test_alias_table_covers_every_internal_team():
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/football_data.json").read_text(
            encoding="utf-8"
        )
    )
    internal = {team.team for team in TournamentRepository().teams}

    assert internal <= set(mapping["aliases"].values())


def test_provider_response_accepts_reversed_orientation_and_nested_season():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.pop("season")
    match = payload["matches"][0]
    match["season"] = {"startDate": "2026-06-11", "endDate": "2026-07-19"}
    match["homeTeam"], match["awayTeam"] = match["awayTeam"], match["homeTeam"]
    score = match["score"]["fullTime"]
    score["home"], score["away"] = score["away"], score["home"]
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/football_data.json").read_text(
            encoding="utf-8"
        )
    )

    result = normalize_football_data_response(
        payload,
        TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
        mapping["aliases"],
        fetched_at=datetime(2026, 6, 14, 20, tzinfo=timezone.utc),
    )

    assert result["results"][0]["home"] == "Germany"
    assert result["results"][0]["home_goals"] == 2
    assert (
        result["mapping_discovery"]["provider_match_ids"]["900025"]
        == "WC26-025"
    )


def test_espn_response_maps_home_away_and_scores():
    payload = json.loads(ESPN_FIXTURE.read_text(encoding="utf-8"))
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/espn.json").read_text(
            encoding="utf-8"
        )
    )

    result = normalize_espn_response(
        payload,
        TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
        mapping["aliases"],
        fetched_at=datetime(2026, 6, 14, 20, tzinfo=timezone.utc),
    )

    assert result["provider"] == "espn"
    assert len(result["results"]) == 1
    assert result["results"][0]["fixture_id"] == "WC26-025"
    assert result["results"][0]["home"] == "Germany"
    assert result["results"][0]["home_goals"] == 2
    assert result["results"][0]["away_goals"] == 0
    assert result["mapping_discovery"]["provider_match_ids"]["760422"] == "WC26-025"
    assert result["raw_response_sha256"]


def test_espn_response_rejects_wrong_competition():
    payload = json.loads(ESPN_FIXTURE.read_text(encoding="utf-8"))
    payload["leagues"][0]["slug"] = "eng.1"

    with pytest.raises(ValueError, match="not FIFA World Cup"):
        normalize_espn_response(
            payload,
            TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
            {},
            fetched_at=datetime(2026, 6, 14, 20, tzinfo=timezone.utc),
        )


def test_espn_response_rejects_empty_group_stage_feed():
    payload = json.loads(ESPN_FIXTURE.read_text(encoding="utf-8"))
    payload["events"] = []

    with pytest.raises(ValueError, match="no group-stage fixtures"):
        normalize_espn_response(
            payload,
            TournamentRepository(snapshot_path=FROZEN_SNAPSHOT),
            {},
            fetched_at=datetime(2026, 6, 14, 20, tzinfo=timezone.utc),
        )


def test_espn_knockout_response_maps_stage_match_number_and_winner():
    payload = json.loads(ESPN_KNOCKOUT_FIXTURE.read_text(encoding="utf-8"))
    mapping = json.loads(
        Path("data/world_cup_2026/provider_mappings/espn.json").read_text(
            encoding="utf-8"
        )
    )

    result = normalize_espn_knockout_response(
        payload,
        mapping["aliases"],
        fetched_at=datetime(2026, 7, 15, 8, tzinfo=timezone.utc),
    )

    semifinal = next(row for row in result["matches"] if row["match_number"] == 101)
    final = next(row for row in result["matches"] if row["match_number"] == 104)
    assert semifinal["stage"] == "semifinal"
    assert semifinal["winner"] == "Spain"
    assert (semifinal["home_goals"], semifinal["away_goals"]) == (2, 0)
    assert final["stage"] == "final"
    assert final["away"] == "Semifinal 2 Winner"
    assert final["home_goals"] is None
    assert result["provider"] == "espn"
    assert result["raw_response_sha256"]
