from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from underdog_lab.config import DATA_DIR
from underdog_lab.world_cup.models import Standing


@dataclass(frozen=True)
class RoundOf32Slot:
    match: int
    first_kind: str
    first_group: str
    second_kind: str
    second_groups: frozenset[str]


ROUND_OF_32_SLOTS = (
    RoundOf32Slot(73, "runner_up", "A", "runner_up", frozenset("B")),
    RoundOf32Slot(74, "winner", "E", "third", frozenset("ABCDF")),
    RoundOf32Slot(75, "winner", "F", "runner_up", frozenset("C")),
    RoundOf32Slot(76, "winner", "C", "runner_up", frozenset("F")),
    RoundOf32Slot(77, "winner", "I", "third", frozenset("CDFGH")),
    RoundOf32Slot(78, "runner_up", "E", "runner_up", frozenset("I")),
    RoundOf32Slot(79, "winner", "A", "third", frozenset("CEHFI")),
    RoundOf32Slot(80, "winner", "L", "third", frozenset("EHIJK")),
    RoundOf32Slot(81, "winner", "D", "third", frozenset("BEFIJ")),
    RoundOf32Slot(82, "winner", "G", "third", frozenset("AEHIJ")),
    RoundOf32Slot(83, "runner_up", "K", "runner_up", frozenset("L")),
    RoundOf32Slot(84, "winner", "H", "runner_up", frozenset("J")),
    RoundOf32Slot(85, "winner", "B", "third", frozenset("EFGIJ")),
    RoundOf32Slot(86, "winner", "J", "runner_up", frozenset("H")),
    RoundOf32Slot(87, "winner", "K", "third", frozenset("DEIJL")),
    RoundOf32Slot(88, "runner_up", "D", "runner_up", frozenset("G")),
)

KNOCKOUT_PATH = {
    "round_of_16": (
        (89, 73, 75),
        (90, 74, 77),
        (91, 76, 78),
        (92, 79, 80),
        (93, 83, 84),
        (94, 81, 82),
        (95, 86, 88),
        (96, 85, 87),
    ),
    "quarterfinal": (
        (97, 89, 90),
        (98, 93, 94),
        (99, 91, 92),
        (100, 95, 96),
    ),
    "semifinal": ((101, 97, 98), (102, 99, 100)),
    "champion": ((104, 101, 102),),
}

THIRD_PLACE_MATCH = (103, 101, 102)


def load_annex_c(path: Path | None = None) -> dict[str, dict[str, str]]:
    path = path or DATA_DIR / "world_cup_2026/annex_c_third_place.json"
    return json.loads(path.read_text(encoding="utf-8"))["combinations"]


def assign_third_place_groups(
    qualified_groups: Sequence[str],
    annex_c: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[int, str]:
    groups = frozenset(qualified_groups)
    if len(groups) != 8 or not groups <= frozenset("ABCDEFGHIJKL"):
        raise ValueError("Exactly eight distinct groups A-L must qualify in third place")
    key = "".join(sorted(groups))
    official = (annex_c or load_annex_c()).get(key)
    if official is None:
        raise ValueError(f"Annex C has no assignment for third-place groups {key}")
    return {int(match): group for match, group in official.items()}


def build_round_of_32(
    ranked_groups: Mapping[str, Sequence[Standing]],
    best_thirds: Sequence[Standing],
    group_by_team: Mapping[str, str],
) -> list[tuple[int, str, str]]:
    third_by_group = {group_by_team[row.team]: row.team for row in best_thirds}
    assignment = assign_third_place_groups(sorted(third_by_group))
    matches = []
    for slot in ROUND_OF_32_SLOTS:
        first_index = 0 if slot.first_kind == "winner" else 1
        first = ranked_groups[slot.first_group][first_index].team
        if slot.second_kind == "third":
            second = third_by_group[assignment[slot.match]]
        else:
            second_group = next(iter(slot.second_groups))
            second = ranked_groups[second_group][1].team
        matches.append((slot.match, first, second))
    return matches
