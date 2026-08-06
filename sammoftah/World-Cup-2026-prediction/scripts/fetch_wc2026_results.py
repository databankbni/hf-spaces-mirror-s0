from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from underdog_lab.config import DATA_DIR
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.providers import (
    normalize_espn_response,
    normalize_football_data_response,
)

FOOTBALL_DATA_API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
ESPN_API_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/"
    "fifa.world/scoreboard"
)
MAPPING_DIR = DATA_DIR / "world_cup_2026/provider_mappings"
UPDATE_PATH = DATA_DIR / "world_cup_2026/result_updates/pending-football-data.json"


def fetch_football_data_payload(token: str) -> dict:
    query = urllib.parse.urlencode({"season": 2026, "stage": "GROUP_STAGE"})
    request = urllib.request.Request(
        f"{FOOTBALL_DATA_API_URL}?{query}",
        headers={"X-Auth-Token": token, "User-Agent": "underdog-lab-results"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"football-data.org returned HTTP {error.code}"
        ) from error


def fetch_espn_payload() -> dict:
    query = urllib.parse.urlencode(
        {"dates": "20260611-20260719", "limit": 200}
    )
    request = urllib.request.Request(
        f"{ESPN_API_URL}?{query}",
        headers={"User-Agent": "underdog-lab-results"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ESPN returned HTTP {error.code}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--output", type=Path, default=UPDATE_PATH)
    parser.add_argument(
        "--provider",
        choices=("auto", "football-data", "espn"),
        default="auto",
    )
    args = parser.parse_args()
    token = os.getenv("FOOTBALL_DATA_API_KEY")
    if args.input_json:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        provider = args.provider
        if provider == "auto":
            provider = "football-data" if "matches" in payload else "espn"
    else:
        provider = args.provider
        if provider == "auto":
            provider = "football-data" if token else "espn"
        if provider == "football-data":
            if not token:
                parser.error(
                    "FOOTBALL_DATA_API_KEY is required for --provider football-data"
                )
            payload = fetch_football_data_payload(token)
        else:
            payload = fetch_espn_payload()

    mapping_name = "football_data.json" if provider == "football-data" else "espn.json"
    mapping = json.loads((MAPPING_DIR / mapping_name).read_text(encoding="utf-8"))
    normalizer = (
        normalize_football_data_response
        if provider == "football-data"
        else normalize_espn_response
    )
    normalized = normalizer(
        payload, TournamentRepository(), mapping["aliases"],
        fetched_at=datetime.now(timezone.utc),
    )
    for fixture_id in normalized.get("unscored_finished", []):
        print(
            f"::warning::{fixture_id} is reported FINISHED but the provider "
            "has not published a score yet; skipping for this poll."
        )

    if not normalized["results"] and not normalized["corrections"]:
        print(f"provider={provider}")
        print("no new results")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    print(f"provider={provider}")
    print(
        f"additions={len(normalized['results'])} "
        f"corrections={len(normalized['corrections'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
