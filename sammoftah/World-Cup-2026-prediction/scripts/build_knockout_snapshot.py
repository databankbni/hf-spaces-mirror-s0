#!/usr/bin/env python3
"""Fetch and persist the live ESPN knockout bracket for the 2026 World Cup."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from underdog_lab.world_cup.providers import normalize_espn_knockout_response


ENDPOINT = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/"
    "fifa.world/scoreboard?dates=2026&limit=1000"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/world_cup_2026/knockout.json"),
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("data/world_cup_2026/provider_mappings/espn.json"),
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/world_cup_2026/result_updates"),
        help="Directory where the raw provider response is persisted so the "
        "snapshot's raw_response_sha256 stays independently verifiable.",
    )
    args = parser.parse_args()
    fetched_at = datetime.now(timezone.utc)
    request = Request(ENDPOINT, headers={"User-Agent": "underdog-lab/1.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    snapshot = normalize_espn_knockout_response(
        payload, mapping.get("aliases", {}), fetched_at=fetched_at
    )
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.raw_dir / (
        f"espn-knockout-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    # Persist the exact canonical serialization the normalizer hashes into
    # raw_response_sha256, so the digest stays independently verifiable.
    raw_path.write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    snapshot["raw_response_path"] = str(raw_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    played = sum(match["winner"] is not None for match in snapshot["matches"])
    print(f"wrote {len(snapshot['matches'])} knockout matches ({played} played) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
