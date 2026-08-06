from __future__ import annotations

"""Build a real historical international match dataset for model fitting.

Source: eloratings.net's per-year results files (e.g.
https://www.eloratings.net/2024_results.tsv), the same source already cited
in data/world_cup_2026/snapshot.json. Each row gives the match date, the two
teams (eloratings.net country codes), the score, the host country (if the
match was played on neutral ground), and each team's Elo rating going into
the match -- so no separate historical-Elo lookup is needed.

Usage:
  python scripts/build_historical_dataset.py --start-year 2015 --end-year 2026
"""

import argparse
import csv
import urllib.request
from datetime import date
from pathlib import Path

from underdog_lab.config import DATA_DIR

RAW_DIR = DATA_DIR / "historical" / "raw"
OUTPUT_PATH = DATA_DIR / "historical" / "matches.csv"

# (date, home_code, away_code) for matches in data/raw/challenge_matches.json
# that fall within the fetched year range. These are reserved for the LLM
# extraction challenge and must not leak into model fitting or evaluation.
CHALLENGE_MATCH_EXCLUSIONS = {
    (date(2022, 11, 22), "AR", "SA"),
    (date(2018, 6, 27), "DE", "KR"),
    (date(2022, 12, 18), "AR", "FR"),
    (date(2022, 12, 10), "MA", "PT"),
    (date(2022, 12, 9), "HR", "BR"),
    (date(2021, 7, 11), "EN", "IT"),
    (date(2018, 7, 15), "FR", "HR"),
    (date(2018, 7, 2), "BE", "JP"),
    (date(2021, 7, 10), "BR", "AR"),
    (date(2022, 11, 25), "EN", "US"),
    (date(2018, 7, 11), "HR", "EN"),
    (date(2016, 7, 10), "FR", "PT"),
}


def fetch_year(year: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{year}_results.tsv"
    if not path.exists():
        url = f"https://www.eloratings.net/{year}_results.tsv"
        with urllib.request.urlopen(url, timeout=30) as response:
            path.write_bytes(response.read())
    return path


def parse_year(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 12:
                continue
            year, month, day, home, away = fields[0:5]
            home_goals, away_goals = fields[5:7]
            tournament, host = fields[7:9]
            home_elo, away_elo = fields[10:12]
            match_date = date(int(year), int(month), int(day))
            if (match_date, home, away) in CHALLENGE_MATCH_EXCLUSIONS:
                continue
            rows.append(
                {
                    "date": match_date.isoformat(),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": int(home_goals),
                    "away_goals": int(away_goals),
                    "home_elo": float(home_elo),
                    "away_elo": float(away_elo),
                    "neutral": host != "" and host != home,
                    "tournament": tournament,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build data/historical/matches.csv from eloratings.net."
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    all_rows = []
    for year in range(args.start_year, args.end_year + 1):
        path = fetch_year(year)
        all_rows.extend(parse_year(path))

    all_rows.sort(key=lambda r: r["date"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "home_team",
                "away_team",
                "home_goals",
                "away_goals",
                "home_elo",
                "away_elo",
                "neutral",
                "tournament",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} matches to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
