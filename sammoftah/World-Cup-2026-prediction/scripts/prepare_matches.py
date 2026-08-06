from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from underdog_lab.forecasting.elo_goals import EloGoalModel


def prepare(source: Path, destination: Path, model: EloGoalModel) -> None:
    rows = json.loads(source.read_text(encoding="utf-8"))
    prepared = []
    for row in rows:
        lambda_home, lambda_away = model.lambdas(
            row["pre_match_home_elo"],
            row["pre_match_away_elo"],
            neutral_venue=row["neutral_venue"],
        )
        prepared.append(
            {
                **row,
                "lambda_home": round(lambda_home, 6),
                "lambda_away": round(lambda_away, 6),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(prepared, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive Poisson scoring rates from pre-match Elo ratings. "
            "The challenge outcomes are never used in this derivation."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/challenge_matches.json"),
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("data/processed/matches.json"),
    )
    parser.add_argument("--base-goals", type=float, default=1.18)
    parser.add_argument("--elo-scale", type=float, default=0.00175)
    parser.add_argument("--home-advantage-elo", type=float, default=70.0)
    args = parser.parse_args()

    model = EloGoalModel(
        intercept=math.log(args.base_goals),
        elo_scale=args.elo_scale,
        home_advantage_elo=args.home_advantage_elo,
    )
    prepare(args.source, args.destination, model)


if __name__ == "__main__":
    main()
