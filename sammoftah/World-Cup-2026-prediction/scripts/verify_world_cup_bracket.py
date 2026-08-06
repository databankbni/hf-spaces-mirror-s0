from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from underdog_lab.world_cup.bracket import (
    KNOCKOUT_PATH,
    ROUND_OF_32_SLOTS,
    THIRD_PLACE_MATCH,
    assign_third_place_groups,
    load_annex_c,
)


def verify(root: Path) -> dict:
    annex = load_annex_c(root / "data/world_cup_2026/annex_c_third_place.json")
    third_slots = {
        slot.match: slot.second_groups
        for slot in ROUND_OF_32_SLOTS
        if slot.second_kind == "third"
    }
    failures = []
    checked = 0
    for groups in combinations("ABCDEFGHIJKL", 8):
        assignment = assign_third_place_groups(groups, annex)
        if set(assignment) != set(third_slots):
            failures.append({"groups": "".join(groups), "reason": "slot mismatch"})
        elif set(assignment.values()) != set(groups):
            failures.append({"groups": "".join(groups), "reason": "group mismatch"})
        elif any(
            group not in third_slots[match]
            for match, group in assignment.items()
        ):
            failures.append({"groups": "".join(groups), "reason": "illegal opponent"})
        checked += 1

    downstream_matches = [
        match
        for matches in KNOCKOUT_PATH.values()
        for match, _, _ in matches
    ] + [THIRD_PLACE_MATCH[0]]
    report = {
        "status": "verified" if not failures and checked == 495 else "failed",
        "release_blocking": bool(failures) or checked != 495,
        "round_of_32_slots": len(ROUND_OF_32_SLOTS),
        "annex_c_combinations": checked,
        "annex_c_failures": failures,
        "downstream_matches_verified": downstream_matches,
        "sources": [
            "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/fifa-world-cup-2026-match-schedule-fixtures-results-teams-stadiums",
            "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage",
        ],
        "scope": (
            "Published matches 73-104, including the third-place match, and "
            "all 495 Annex C third-place "
            "assignments. Fair-play data is not available in the snapshot."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/bracket_verification.json"),
    )
    args = parser.parse_args()
    report = verify(args.root.resolve())
    args.output.resolve().write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Bracket verification: {report['status']} "
        f"({report['annex_c_combinations']} Annex C combinations)"
    )
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
