"""Safe snapshot update: add match results without modifying historical data.

Usage:
  # Add a single result
  python scripts/update_snapshot.py --group A --home Mexico --away "South Africa" --home-goals 2 --away-goals 0

  # Update the information cutoff
  python scripts/update_snapshot.py --cutoff "2026-06-13T19:00:00Z"

  # Preview changes without writing
  python scripts/update_snapshot.py --group A --home Mexico --away "South Africa" --home-goals 2 --away-goals 0 --dry-run
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from underdog_lab.config import DATA_DIR
from underdog_lab.world_cup.data import TournamentRepository

SNAPSHOT_PATH = DATA_DIR / "world_cup_2026" / "snapshot.json"
BACKUP_DIR = DATA_DIR / "world_cup_2026" / "backups"


def load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def save_snapshot(data: dict) -> None:
    SNAPSHOT_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def create_backup(data: dict) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = BACKUP_DIR / f"snapshot-{timestamp}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return path


def add_result(
    snapshot: dict,
    group: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    *,
    allow_correction: bool = False,
) -> dict:
    updated = copy.deepcopy(snapshot)
    results = updated.setdefault("results", [])

    # Update existing or append new
    for result in results:
        if result["group"] == group and result["home"] == home and result["away"] == away:
            unchanged = (
                result["home_goals"] == home_goals
                and result["away_goals"] == away_goals
            )
            if unchanged:
                return updated
            if not allow_correction:
                raise ValueError(
                    f"Result correction requires --allow-corrections: "
                    f"{home} {result['home_goals']}-{result['away_goals']} "
                    f"{away} -> {home_goals}-{away_goals}"
                )
            result["home_goals"] = home_goals
            result["away_goals"] = away_goals
            return updated

    results.append({
        "group": group,
        "home": home,
        "away": away,
        "home_goals": home_goals,
        "away_goals": away_goals,
    })
    return updated


def add_results(
    snapshot: dict,
    rows: list[dict],
    *,
    allow_corrections: bool = False,
) -> dict:
    updated = snapshot
    for row in rows:
        updated = add_result(
            updated,
            row["group"],
            row["home"],
            row["away"],
            int(row["home_goals"]),
            int(row["away_goals"]),
            allow_correction=allow_corrections,
        )
    return updated


def validate_result_rows(rows: list[dict]) -> None:
    repository = TournamentRepository()
    fixtures = {
        (fixture.group, fixture.home, fixture.away)
        for fixture in repository.fixtures
    }
    for row in rows:
        key = (row["group"], row["home"], row["away"])
        if key not in fixtures:
            raise ValueError(f"Unknown tournament fixture: {key}")
        if int(row["home_goals"]) < 0 or int(row["away_goals"]) < 0:
            raise ValueError(f"Goals must be non-negative: {key}")


def update_cutoff(snapshot: dict, cutoff: str) -> dict:
    updated = copy.deepcopy(snapshot)
    updated["information_cutoff"] = cutoff
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely update the World Cup 2026 tournament snapshot."
    )
    parser.add_argument("--group", help="Group letter (A-L)")
    parser.add_argument("--home", help="Home team name")
    parser.add_argument("--away", help="Away team name")
    parser.add_argument("--home-goals", type=int, help="Home goals scored")
    parser.add_argument("--away-goals", type=int, help="Away goals scored")
    parser.add_argument(
        "--cutoff",
        help="Update information_cutoff timestamp (ISO 8601).",
    )
    parser.add_argument(
        "--results-file",
        type=Path,
        help=(
            "JSON file containing {'results': [...], 'information_cutoff': ...}. "
            "This is an audited ingestion boundary; it performs no scraping."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing.",
    )
    parser.add_argument(
        "--allow-corrections",
        action="store_true",
        help="Apply explicitly reported score corrections for human review.",
    )
    args = parser.parse_args()

    original = load_snapshot()
    updated = copy.deepcopy(original)
    actions = []

    if args.results_file:
        payload = json.loads(args.results_file.read_text(encoding="utf-8"))
        rows = [
            *payload.get("results", []),
            *payload.get("corrections", []),
        ]
        validate_result_rows(rows)
        updated = add_results(
            updated,
            rows,
            allow_corrections=args.allow_corrections,
        )
        actions.append(
            f"Import {len(payload.get('results', []))} result(s) and "
            f"{len(payload.get('corrections', []))} correction(s) from "
            f"{args.results_file}"
        )
        if payload.get("information_cutoff"):
            updated = update_cutoff(updated, payload["information_cutoff"])
            actions.append(
                f"Update cutoff to {payload['information_cutoff']}"
            )
        sources = updated.setdefault("sources", [])
        for source in payload.get("sources", []):
            if source not in sources:
                sources.append(source)

    if args.cutoff:
        updated = update_cutoff(updated, args.cutoff)
        actions.append(f"Update cutoff to {args.cutoff}")

    if args.group and args.home and args.away:
        if args.home_goals is None or args.away_goals is None:
            parser.error("--home-goals and --away-goals are required when adding a result.")
        updated = add_result(
            updated, args.group, args.home, args.away,
            args.home_goals, args.away_goals,
        )
        actions.append(
            f"Group {args.group}: {args.home} {args.home_goals}-{args.away_goals} {args.away}"
        )

    if not actions:
        parser.error("No action specified. Use --cutoff or --group/--home/--away/--home-goals/--away-goals.")

    if args.dry_run:
        print("DRY RUN — no changes written.")
        print("Actions that would be taken:")
        for action in actions:
            print(f"  • {action}")
        print()
        print("Resulting snapshot diff:")
        orig_json = json.dumps(original, indent=2, sort_keys=True)
        upd_json = json.dumps(updated, indent=2, sort_keys=True)
        if orig_json == upd_json:
            print("  (no change)")
        else:
            import difflib
            diff = difflib.unified_diff(
                orig_json.splitlines(),
                upd_json.splitlines(),
                fromfile="original",
                tofile="updated",
            )
            for line in diff:
                print(f"  {line}")
        return

    if updated == original:
        print("No snapshot changes required.")
        return

    # Back up before writing
    backup_path = create_backup(original)
    print(f"Backup saved to {backup_path}")

    save_snapshot(updated)
    for action in actions:
        print(f"✓ {action}")

    # Verify round-trip
    reloaded = load_snapshot()
    assert reloaded == updated, "Snapshot round-trip verification failed."
    print("✓ Round-trip verification passed.")


if __name__ == "__main__":
    main()
