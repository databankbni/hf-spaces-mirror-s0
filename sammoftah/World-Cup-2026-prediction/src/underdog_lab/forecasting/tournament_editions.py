from __future__ import annotations

from collections.abc import Iterable
from datetime import date

MAJOR_GROUP_TOURNAMENTS = frozenset({"WC", "EC", "AC", "CA"})

# Host-team codes for editions represented in data/historical/matches.csv.
# Multi-host editions intentionally contain every host team.
EDITION_HOSTS: dict[tuple[str, int], frozenset[str]] = {
    ("AC", 2015): frozenset({"AU"}),
    ("AC", 2019): frozenset({"AE"}),
    ("AC", 2024): frozenset({"QA"}),
    ("CA", 2015): frozenset({"CL"}),
    ("CA", 2016): frozenset({"US"}),
    ("CA", 2019): frozenset({"BR"}),
    ("CA", 2021): frozenset({"BR"}),
    ("CA", 2024): frozenset({"US"}),
    ("EC", 2016): frozenset({"FR"}),
    ("EC", 2021): frozenset(
        {"AZ", "DK", "EN", "DE", "HU", "IT", "NL", "RO", "RU", "SQ", "ES"}
    ),
    ("EC", 2024): frozenset({"DE"}),
    ("WC", 2018): frozenset({"RU"}),
    ("WC", 2022): frozenset({"QA"}),
    ("WC", 2026): frozenset({"CA", "MX", "US"}),
}


def assign_edition_metadata(
    matches: Iterable[dict],
    *,
    max_gap_days: int = 90,
) -> list[dict]:
    """Return major-tournament rows with inferred edition and opener metadata.

    The source data has tournament codes but no edition or stage column.
    Editions are therefore inferred by date gaps and must remain research
    metadata rather than being presented as an official stage annotation.
    """
    selected = [
        dict(match)
        for match in matches
        if match.get("tournament") in MAJOR_GROUP_TOURNAMENTS
    ]
    by_tournament: dict[str, list[dict]] = {}
    for match in selected:
        by_tournament.setdefault(match["tournament"], []).append(match)

    enriched: list[dict] = []
    for tournament, rows in by_tournament.items():
        rows.sort(key=lambda row: row["date"])
        editions: list[list[dict]] = []
        for row in rows:
            if (
                not editions
                or (row["date"] - editions[-1][-1]["date"]).days > max_gap_days
            ):
                editions.append([row])
            else:
                editions[-1].append(row)

        for edition_rows in editions:
            edition_year = edition_rows[0]["date"].year
            first_date_by_team: dict[str, date] = {}
            for row in edition_rows:
                for key in ("home_team", "away_team"):
                    first_date_by_team.setdefault(row[key], row["date"])
            hosts = EDITION_HOSTS.get((tournament, edition_year), frozenset())
            edition_id = f"{tournament}-{edition_year}"
            for row in edition_rows:
                row["edition_id"] = edition_id
                row["edition_year"] = edition_year
                row["is_inferred_opener"] = (
                    row["date"] == first_date_by_team[row["home_team"]]
                    and row["date"] == first_date_by_team[row["away_team"]]
                )
                row["home_is_host"] = row["home_team"] in hosts
                row["away_is_host"] = row["away_team"] in hosts
                enriched.append(row)
    return sorted(enriched, key=lambda row: row["date"])
