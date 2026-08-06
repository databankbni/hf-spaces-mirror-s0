from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from underdog_lab.world_cup.data import TournamentRepository

GROUP_STAGE = "GROUP_STAGE"
FINISHED = "FINISHED"
ESPN_GROUP_STAGE = "group-stage"
ESPN_KNOCKOUT_STAGES = {
    "round-of-32": ("round_of_32", 73),
    "round-of-16": ("round_of_16", 89),
    "quarterfinals": ("quarterfinal", 97),
    "semifinals": ("semifinal", 101),
    "3rd-place-match": ("third_place", 103),
    "final": ("final", 104),
}


def normalize_football_data_response(
    payload: dict,
    repository: TournamentRepository,
    aliases: dict[str, str],
    *,
    fetched_at: datetime | None = None,
    kickoff_tolerance_minutes: int = 180,
) -> dict:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    competition = payload.get("competition") or {}
    matches = payload.get("matches") or []
    season = payload.get("season") or next(
        (match.get("season") for match in matches if match.get("season")),
        {},
    )
    if competition.get("code") != "WC":
        raise ValueError("football-data response is not competition WC")
    if not str(season.get("startDate", "")).startswith("2026-"):
        raise ValueError("football-data response is not the 2026 World Cup season")

    fixture_by_pair = {
        (fixture.home, fixture.away): (fixture, False)
        for fixture in repository.fixtures
    }
    fixture_by_pair.update(
        {
            (fixture.away, fixture.home): (fixture, True)
            for fixture in repository.fixtures
        }
    )
    existing = {
        (row["group"], row["home"], row["away"]): row
        for row in repository.snapshot["results"]
    }
    additions = []
    corrections = []
    provider_matches = []
    unscored_finished = []
    seen_fixture_ids = set()
    discovered_team_ids = {}
    discovered_match_ids = {}
    for match in matches:
        if match.get("stage") != GROUP_STAGE:
            continue
        home_team = match.get("homeTeam") or {}
        away_team = match.get("awayTeam") or {}
        home = _team_name(home_team, aliases)
        away = _team_name(away_team, aliases)
        fixture_match = fixture_by_pair.get((home, away))
        if fixture_match is None:
            raise ValueError(f"unmapped World Cup fixture: {home} vs {away}")
        fixture, reversed_orientation = fixture_match
        if fixture.fixture_id in seen_fixture_ids:
            raise ValueError(f"duplicate provider match for {fixture.fixture_id}")
        seen_fixture_ids.add(fixture.fixture_id)
        _record_team_id(discovered_team_ids, home_team, home)
        _record_team_id(discovered_team_ids, away_team, away)
        if match.get("id") is not None:
            discovered_match_ids[str(match["id"])] = fixture.fixture_id
        provider_kickoff = _timestamp(match.get("utcDate"))
        if provider_kickoff is None:
            raise ValueError(f"missing provider kickoff for {fixture.fixture_id}")
        delta = abs((provider_kickoff - fixture.kickoff_utc).total_seconds()) / 60
        if delta > kickoff_tolerance_minutes:
            raise ValueError(
                f"kickoff mismatch for {fixture.fixture_id}: {delta:.0f} minutes"
            )
        provider_matches.append(
            {
                "provider_match_id": match.get("id"),
                "fixture_id": fixture.fixture_id,
                "status": match.get("status"),
                "last_updated": match.get("lastUpdated"),
                "provider_kickoff_utc": provider_kickoff.isoformat(),
            }
        )
        if match.get("status") != FINISHED:
            continue
        score = match.get("score") or {}
        full_time = score.get("regularTime") or score.get("fullTime") or {}
        home_goals = full_time.get("home")
        away_goals = full_time.get("away")
        if home_goals is None or away_goals is None:
            # football-data.org sometimes reports a match FINISHED before the
            # score fields are populated. Skip just this match so other
            # results in the same poll are not lost; it will be picked up on
            # a later poll once the provider backfills the score.
            unscored_finished.append(fixture.fixture_id)
            continue
        if reversed_orientation:
            home_goals, away_goals = away_goals, home_goals
        row = {
            "provider": "football-data.org",
            "provider_match_id": match.get("id"),
            "provider_last_updated": match.get("lastUpdated"),
            "fixture_id": fixture.fixture_id,
            "group": fixture.group,
            "home": fixture.home,
            "away": fixture.away,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
        }
        old = existing.get((fixture.group, fixture.home, fixture.away))
        if old is None:
            additions.append(row)
        elif (
            old["home_goals"] != row["home_goals"]
            or old["away_goals"] != row["away_goals"]
        ):
            corrections.append(
                {
                    **row,
                    "previous_home_goals": old["home_goals"],
                    "previous_away_goals": old["away_goals"],
                }
            )

    cutoff = safe_information_cutoff(
        repository,
        additions,
        corrections,
        fetched_at=fetched_at,
    )
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "provider": "football-data.org",
        "fetched_at": fetched_at.isoformat(),
        "competition": {
            "id": competition.get("id"),
            "code": competition.get("code"),
            "name": competition.get("name"),
        },
        "season": {
            "id": season.get("id"),
            "startDate": season.get("startDate"),
            "endDate": season.get("endDate"),
        },
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "sources": ["https://api.football-data.org/v4/competitions/WC/matches"],
        "results": additions,
        "corrections": corrections,
        "unscored_finished": unscored_finished,
        "provider_matches": provider_matches,
        "mapping_discovery": {
            "provider_team_ids": discovered_team_ids,
            "provider_match_ids": discovered_match_ids,
        },
    }


def normalize_espn_response(
    payload: dict,
    repository: TournamentRepository,
    aliases: dict[str, str],
    *,
    fetched_at: datetime | None = None,
    kickoff_tolerance_minutes: int = 180,
) -> dict:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    leagues = payload.get("leagues") or []
    league = leagues[0] if leagues else {}
    season = league.get("season") or {}
    if league.get("slug") != "fifa.world":
        raise ValueError("ESPN response is not FIFA World Cup")
    if int(season.get("year", 0)) != 2026:
        raise ValueError("ESPN response is not the 2026 World Cup season")

    fixture_by_pair = {
        (fixture.home, fixture.away): (fixture, False)
        for fixture in repository.fixtures
    }
    fixture_by_pair.update(
        {
            (fixture.away, fixture.home): (fixture, True)
            for fixture in repository.fixtures
        }
    )
    existing = {
        (row["group"], row["home"], row["away"]): row
        for row in repository.snapshot["results"]
    }
    additions = []
    corrections = []
    provider_matches = []
    seen_fixture_ids = set()
    discovered_team_ids = {}
    discovered_match_ids = {}

    for event in payload.get("events") or []:
        event_season = event.get("season") or {}
        if event_season.get("slug") != ESPN_GROUP_STAGE:
            continue
        competitions = event.get("competitions") or []
        competition = competitions[0] if competitions else {}
        competitors = competition.get("competitors") or []
        home_team = next(
            (row for row in competitors if row.get("homeAway") == "home"),
            None,
        )
        away_team = next(
            (row for row in competitors if row.get("homeAway") == "away"),
            None,
        )
        if home_team is None or away_team is None:
            raise ValueError(f"missing ESPN competitors for event {event.get('id')}")
        home = _espn_team_name(home_team, aliases)
        away = _espn_team_name(away_team, aliases)
        fixture_match = fixture_by_pair.get((home, away))
        if fixture_match is None:
            raise ValueError(f"unmapped World Cup fixture: {home} vs {away}")
        fixture, reversed_orientation = fixture_match
        if fixture.fixture_id in seen_fixture_ids:
            raise ValueError(f"duplicate provider match for {fixture.fixture_id}")
        seen_fixture_ids.add(fixture.fixture_id)
        _record_espn_team_id(discovered_team_ids, home_team, home)
        _record_espn_team_id(discovered_team_ids, away_team, away)
        if event.get("id") is not None:
            discovered_match_ids[str(event["id"])] = fixture.fixture_id

        provider_kickoff = _timestamp(event.get("date"))
        if provider_kickoff is None:
            raise ValueError(f"missing provider kickoff for {fixture.fixture_id}")
        delta = abs((provider_kickoff - fixture.kickoff_utc).total_seconds()) / 60
        if delta > kickoff_tolerance_minutes:
            raise ValueError(
                f"kickoff mismatch for {fixture.fixture_id}: {delta:.0f} minutes"
            )
        status = event.get("status") or {}
        status_type = status.get("type") or {}
        provider_matches.append(
            {
                "provider_match_id": event.get("id"),
                "fixture_id": fixture.fixture_id,
                "status": status_type.get("name"),
                "provider_kickoff_utc": provider_kickoff.isoformat(),
            }
        )
        if status_type.get("completed") is not True:
            continue
        home_goals = home_team.get("score")
        away_goals = away_team.get("score")
        if home_goals is None or away_goals is None:
            raise ValueError(f"completed ESPN event has no score: {fixture.fixture_id}")
        if reversed_orientation:
            home_goals, away_goals = away_goals, home_goals
        row = {
            "provider": "espn",
            "provider_match_id": event.get("id"),
            "fixture_id": fixture.fixture_id,
            "group": fixture.group,
            "home": fixture.home,
            "away": fixture.away,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
        }
        old = existing.get((fixture.group, fixture.home, fixture.away))
        if old is None:
            additions.append(row)
        elif (
            old["home_goals"] != row["home_goals"]
            or old["away_goals"] != row["away_goals"]
        ):
            corrections.append(
                {
                    **row,
                    "previous_home_goals": old["home_goals"],
                    "previous_away_goals": old["away_goals"],
                }
            )

    if not seen_fixture_ids:
        raise ValueError("ESPN response contains no group-stage fixtures")

    cutoff = safe_information_cutoff(
        repository,
        additions,
        corrections,
        fetched_at=fetched_at,
    )
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "provider": "espn",
        "fetched_at": fetched_at.isoformat(),
        "competition": {
            "id": league.get("id"),
            "slug": league.get("slug"),
            "name": league.get("name"),
        },
        "season": {
            "year": season.get("year"),
            "displayName": season.get("displayName"),
        },
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "sources": [
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard"
        ],
        "results": additions,
        "corrections": corrections,
        "provider_matches": provider_matches,
        "mapping_discovery": {
            "provider_team_ids": discovered_team_ids,
            "provider_match_ids": discovered_match_ids,
        },
    }


def normalize_espn_knockout_response(
    payload: dict,
    aliases: dict[str, str],
    *,
    fetched_at: datetime | None = None,
) -> dict:
    """Normalize ESPN's knockout events into the checked-in bracket schema."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    leagues = payload.get("leagues") or []
    league = leagues[0] if leagues else {}
    season = league.get("season") or {}
    if league.get("slug") != "fifa.world":
        raise ValueError("ESPN response is not FIFA World Cup")
    if int(season.get("year", 0)) != 2026:
        raise ValueError("ESPN response is not the 2026 World Cup season")

    grouped: dict[str, list[dict]] = {slug: [] for slug in ESPN_KNOCKOUT_STAGES}
    for event in payload.get("events") or []:
        slug = (event.get("season") or {}).get("slug")
        if slug in grouped:
            grouped[slug].append(event)
    if not any(grouped.values()):
        raise ValueError("ESPN response contains no knockout fixtures")

    matches = []
    for slug, (stage, offset) in ESPN_KNOCKOUT_STAGES.items():
        events = sorted(
            grouped[slug],
            key=lambda event: (event.get("date", ""), str(event.get("id", ""))),
        )
        max_events = {
            "round_of_32": 16,
            "round_of_16": 8,
            "quarterfinal": 4,
            "semifinal": 2,
            "third_place": 1,
            "final": 1,
        }[stage]
        for index, event in enumerate(events):
            if index >= max_events:
                raise ValueError(f"too many ESPN events for {stage}")
            competition = (event.get("competitions") or [{}])[0]
            competitors = competition.get("competitors") or []
            home_row = next((row for row in competitors if row.get("homeAway") == "home"), None)
            away_row = next((row for row in competitors if row.get("homeAway") == "away"), None)
            if home_row is None or away_row is None:
                raise ValueError(f"missing ESPN knockout competitors for {event.get('id')}")
            status = (competition.get("status") or {}).get("type") or {}
            completed = status.get("completed") is True
            kickoff = _timestamp(event.get("date"))
            if kickoff is None:
                raise ValueError(f"missing ESPN knockout kickoff for {event.get('id')}")
            home = _knockout_team_name(home_row, aliases)
            away = _knockout_team_name(away_row, aliases)
            winner = None
            home_goals = away_goals = None
            if completed:
                try:
                    home_goals = int(home_row["score"])
                    away_goals = int(away_row["score"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"completed ESPN knockout event has no score: {event.get('id')}") from error
                winner_row = next((row for row in competitors if row.get("winner") is True), None)
                winner = _knockout_team_name(winner_row, aliases) if winner_row else (
                    home if home_goals > away_goals else away if away_goals > home_goals else None
                )
            match_number = offset + index
            matches.append({
                "fixture_id": f"WC26-{match_number:03d}",
                "match_number": match_number,
                "stage": stage,
                "date": kickoff.date().isoformat(),
                "kickoff_utc": kickoff.isoformat(),
                "home": home,
                "away": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "winner": winner,
                "provider_match_id": str(event.get("id")) if event.get("id") is not None else None,
                "provider_status": status.get("name"),
            })
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": "knockout-v1",
        "provider": "espn",
        "fetched_at": fetched_at.isoformat(),
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "matches": sorted(matches, key=lambda row: row["match_number"]),
    }


def safe_information_cutoff(
    repository: TournamentRepository,
    additions: list[dict],
    corrections: list[dict],
    *,
    fetched_at: datetime,
) -> datetime:
    recorded = {
        (row["group"], row["home"], row["away"])
        for row in repository.snapshot["results"]
    }
    recorded.update(
        (row["group"], row["home"], row["away"])
        for row in additions + corrections
    )
    missing = [
        fixture
        for fixture in repository.fixtures
        if (fixture.group, fixture.home, fixture.away) not in recorded
        and fixture.kickoff_utc <= fetched_at
    ]
    if not missing:
        return fetched_at
    earliest = min(fixture.kickoff_utc for fixture in missing)
    return min(fetched_at, earliest - timedelta(seconds=1))


def _team_name(team: dict, aliases: dict[str, str]) -> str:
    candidates = [
        str(team.get("id", "")),
        team.get("name"),
        team.get("shortName"),
        team.get("tla"),
    ]
    for candidate in candidates:
        if candidate in aliases:
            return aliases[candidate]
    raise ValueError(f"unmapped provider team: {team}")


def _record_team_id(discovered: dict[str, str], team: dict, name: str) -> None:
    provider_id = team.get("id")
    if provider_id is not None:
        discovered[str(provider_id)] = name


def _espn_team_name(competitor: dict, aliases: dict[str, str]) -> str:
    team = competitor.get("team") or {}
    candidates = [
        str(team.get("id", "")),
        team.get("displayName"),
        team.get("shortDisplayName"),
        team.get("name"),
        team.get("abbreviation"),
    ]
    for candidate in candidates:
        if candidate in aliases:
            return aliases[candidate]
    raise ValueError(f"unmapped ESPN team: {team}")


def _knockout_team_name(competitor: dict | None, aliases: dict[str, str]) -> str:
    if competitor is None:
        raise ValueError("missing ESPN knockout team")
    team = competitor.get("team") or {}
    candidates = [
        str(team.get("id", "")),
        team.get("displayName"),
        team.get("shortDisplayName"),
        team.get("name"),
        team.get("abbreviation"),
    ]
    for candidate in candidates:
        if candidate in aliases:
            return aliases[candidate]
    for candidate in candidates[1:]:
        if candidate:
            return str(candidate)
    raise ValueError(f"unmapped ESPN knockout team: {team}")


def _record_espn_team_id(
    discovered: dict[str, str], competitor: dict, name: str
) -> None:
    team = competitor.get("team") or {}
    provider_id = team.get("id") or competitor.get("id")
    if provider_id is not None:
        discovered[str(provider_id)] = name


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
