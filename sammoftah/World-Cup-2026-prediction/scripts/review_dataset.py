from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively approve or reject scenario labels."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    changed = False
    for index, row in enumerate(rows, start=1):
        if row.get("review_status") == "approved":
            continue
        print(f"\n[{index}/{len(rows)}] {row['id']}")
        print(f"{row['home_team']} vs {row['away_team']}")
        print(f"Text: {row['text']}")
        print(json.dumps(row["expected"], indent=2, ensure_ascii=False))
        decision = input("[a]pprove, [r]eject, [s]kip, [q]uit: ").strip().lower()
        if decision == "q":
            break
        if decision == "a":
            row["review_status"] = "approved"
            changed = True
        elif decision == "r":
            row["review_status"] = "rejected"
            changed = True

    if changed:
        with args.path.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"Updated {args.path}")


if __name__ == "__main__":
    main()
