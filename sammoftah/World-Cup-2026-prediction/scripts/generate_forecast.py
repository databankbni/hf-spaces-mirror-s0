"""Generate and write an immutable forecast file under predictions/YYYY-MM-DD/.

Usage:
  python scripts/generate_forecast.py [--date 2026-06-14] [--iterations 3000]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from underdog_lab.config import RULESET_VERSION
from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.forecasting import match_forecast
from underdog_lab.world_cup.integrity import validate_snapshot_integrity
from underdog_lab.world_cup.provenance import forecast_provenance
from underdog_lab.world_cup.simulation import simulate_tournament


def get_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def generate(forecast_date: str, iterations: int, output_dir: Path) -> Path:
    repo = TournamentRepository()
    validate_snapshot_integrity(repo)

    # Fixture predictions
    fixtures = []
    for fixture in repo.fixtures:
        if not fixture.played:
            fc = match_forecast(fixture, repo.team_by_name)
            fixtures.append({
                "fixture_id": fixture.fixture_id,
                "group": fixture.group,
                "date": str(fixture.date),
                "kickoff_utc": (
                    fixture.kickoff_utc.isoformat()
                    if fixture.kickoff_utc is not None
                    else None
                ),
                "home": fixture.home,
                "away": fixture.away,
                "p_home": round(fc.p_home, 6),
                "p_draw": round(fc.p_draw, 6),
                "p_away": round(fc.p_away, 6),
                "lambda_home": round(fc.lambda_home, 6),
                "lambda_away": round(fc.lambda_away, 6),
            })

    # Tournament simulation
    raw_probs = simulate_tournament(repo, iterations=iterations)
    champion = {
        team: round(p["champion"], 6) for team, p in raw_probs.items()
    }

    forecast = {
        "forecast_date": forecast_date,
        "information_cutoff": repo.snapshot["information_cutoff"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": get_commit(),
        "model": "Elo-to-goals Dixon-Coles (fitted, see models/elo_fit_report.json)",
        "provenance": forecast_provenance(),
        "ruleset_version": RULESET_VERSION,
        "iterations": iterations,
        "fixtures": fixtures,
        "champion_probabilities": champion,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "forecast.json"
    output_path.write_text(
        json.dumps(forecast, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a pre-registered tournament forecast."
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Forecast date (default: today).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3000,
        help="Monte Carlo iterations (default: 3000).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: predictions/<date>/).",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or Path("predictions") / args.date
    if output_dir.exists():
        parser.error(
            f"{output_dir} already exists. Past forecast files must never be "
            "rewritten. Use a new date."
        )

    path = generate(args.date, args.iterations, output_dir)
    print(f"Wrote forecast to {path}")


if __name__ == "__main__":
    main()
