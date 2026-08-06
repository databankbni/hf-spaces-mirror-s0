from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from underdog_lab.config import DATA_DIR

KNOCKOUT_STAGES = ("advance", "round_of_16", "quarterfinal", "semifinal", "final")

OUTFIELD_ATTRIBUTES = (
    ("pace", "PAC"),
    ("shooting", "SHO"),
    ("passing", "PAS"),
    ("dribbling", "DRI"),
    ("defending", "DEF"),
    ("physical", "PHY"),
)
GOALKEEPER_ATTRIBUTES = (
    ("diving", "DIV"),
    ("handling", "HAN"),
    ("kicking", "KIC"),
    ("reflexes", "REF"),
    ("speed", "SPD"),
    ("positioning", "POS"),
)


def card_attributes(player: dict) -> tuple[tuple[str, str], ...]:
    """Attribute keys and EA FC-style labels appropriate for this player's position."""
    return GOALKEEPER_ATTRIBUTES if player["position"] == "GK" else OUTFIELD_ATTRIBUTES


def load_players(root: Path | None = None) -> dict:
    root = root or DATA_DIR / "world_cup_2026"
    return json.loads((root / "players.json").read_text(encoding="utf-8"))


def expected_matches_played(team_probabilities: dict[str, float]) -> float:
    """Group-stage matches (3) plus each knockout round the team is projected to reach."""
    return 3.0 + sum(team_probabilities[stage] for stage in KNOCKOUT_STAGES)


def deep_run_weight(team_probabilities: dict[str, float]) -> float:
    """How likely a team is to go deep enough for its best player to be in award contention."""
    return (
        team_probabilities["semifinal"]
        + team_probabilities["final"]
        + team_probabilities["champion"]
    )


def _ranked(rows: list[dict], limit: int) -> list[dict]:
    """Sort by index and convert it into a 0-99 "form rating" — the same
    scale as the OVR/POT badges on the cards.

    The rating is min-max scaled against the *entire* eligible pool (not
    just the shortlist), so it reflects standing against every contender
    for that award rather than an artificial split among however many
    cards happen to be shown. The floor is set to 35 rather than 0:
    everyone here is a real World Cup squad player, so even the weakest
    contender on the list shouldn't read as "zero chance".
    """
    rows.sort(key=lambda row: row["index"], reverse=True)
    indices = [row["index"] for row in rows]
    lo, hi = min(indices), max(indices)
    spread = (hi - lo) or 1.0
    for row in rows:
        row["form_rating"] = round(35 + 64 * (row["index"] - lo) / spread)
    return rows[:limit]


def golden_boot_rankings(
    players: list[dict],
    probabilities: dict[str, dict[str, float]],
    limit: int = 8,
) -> list[dict]:
    """Top-scorer index: club goal-rate, sharpened by the EA FC shooting attribute,
    scaled by the team's expected number of tournament appearances."""
    rows = [
        {
            **player,
            "index": (
                player["goal_rate"]
                * (player["attributes"]["shooting"] / 100)
                * expected_matches_played(probabilities[player["team"]])
            ),
        }
        for player in players
        if player["position"] != "GK" and player["goal_rate"] > 0
    ]
    return _ranked(rows, limit)


def golden_glove_rankings(
    players: list[dict],
    probabilities: dict[str, dict[str, float]],
    limit: int = 5,
) -> list[dict]:
    """Best-goalkeeper index: EA FC overall rating scaled by expected appearances
    and by how far the team is projected to go. A keeper's Golden Glove case
    rests on knockout-stage clean sheets, not just minutes on the pitch, so a
    deep run counts for more than the same number of group-stage matches."""
    rows = [
        {
            **player,
            "index": (
                player["overall_rating"]
                * expected_matches_played(probabilities[player["team"]])
                * (1.0 + deep_run_weight(probabilities[player["team"]]))
            ),
        }
        for player in players
        if player["position"] == "GK"
    ]
    return _ranked(rows, limit)


def golden_ball_rankings(
    players: list[dict],
    probabilities: dict[str, dict[str, float]],
    limit: int = 8,
) -> list[dict]:
    """Best-overall-player index: EA FC overall rating weighted by the team's
    chance of a deep (semifinal or further) run."""
    rows = [
        {
            **player,
            "index": player["overall_rating"] * (1.0 + deep_run_weight(probabilities[player["team"]])),
        }
        for player in players
        if player["position"] != "GK"
    ]
    return _ranked(rows, limit)


def young_player_rankings(
    players: list[dict],
    probabilities: dict[str, dict[str, float]],
    cutoff: date,
    limit: int = 5,
) -> list[dict]:
    """Best Young Player index: EA FC *potential* rating (not current overall) weighted
    by the team's deep-run chance, restricted to players born on/after ``cutoff``."""
    rows = [
        {
            **player,
            "index": player["potential_rating"] * (1.0 + deep_run_weight(probabilities[player["team"]])),
        }
        for player in players
        if player["position"] != "GK" and date.fromisoformat(player["birth_date"]) >= cutoff
    ]
    return _ranked(rows, limit)


def award_predictions(
    probabilities: dict[str, dict[str, float]],
    root: Path | None = None,
) -> dict[str, list[dict]]:
    data = load_players(root)
    players = data["players"]
    cutoff = date.fromisoformat(data["young_player_cutoff"])
    return {
        "golden_ball": golden_ball_rankings(players, probabilities),
        "golden_boot": golden_boot_rankings(players, probabilities),
        "golden_glove": golden_glove_rankings(players, probabilities),
        "young_player": young_player_rankings(players, probabilities, cutoff),
    }
