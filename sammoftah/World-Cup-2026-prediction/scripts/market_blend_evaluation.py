"""Gate a one-parameter market-assisted forecast against the independent model.

The input CSV must contain timestamped pre-kickoff decimal odds. Opening and
closing snapshots are evaluated separately via ``--horizon``; they must never
be mixed because they represent different information sets.

Required columns:
  date,home_team,away_team,kickoff_utc,captured_at,horizon,
  home_odds,draw_odds,away_odds

Team identifiers must match ``data/historical/matches.csv``. Rows captured at
or after kickoff are rejected. The independent Dixon-Coles model is refit
walk-forward for each test year, exactly as in the other forecasting gates.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.calibration import apply_temperature
from underdog_lab.forecasting.market import (
    fit_market_weight,
    market_assisted_forecast,
    market_probabilities,
)
from underdog_lab.forecasting.market_data import load_odds_csv
from underdog_lab.forecasting.scoring import log_loss
from underdog_lab.world_cup.forecasting import CALIBRATION_TEMPERATURE

from backtest_common import (
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
)

HALF_LIFE_DAYS = 180.0
SELECTION_YEARS = list(range(2018, 2026))
CONFIRMATION_YEAR = 2026
METHODS = ("proportional", "power", "shin")
MIN_SELECTION = 500
MIN_CONFIRMATION = 30
MIN_CONFIRMATION_NEUTRAL = 10


def collect_rows(
    all_matches: list[dict],
    odds: dict[tuple[date, str, str], dict],
    method: str,
) -> dict[int, list[tuple]]:
    per_year: dict[int, list[tuple]] = {}
    for year in SELECTION_YEARS + [CONFIRMATION_YEAR]:
        train_cutoff = date(year - 1, 12, 31)
        train = [match for match in all_matches if match["date"] <= train_cutoff]
        test = [match for match in all_matches if match["date"].year == year]
        model = fit_dixon_coles(train, train_cutoff, HALF_LIFE_DAYS)
        year_rows = []
        for match in test:
            key = (match["date"], match["home_team"], match["away_team"])
            odds_row = odds.get(key)
            if odds_row is None:
                continue
            independent = apply_temperature(
                model.forecast(
                    match["home_elo"],
                    match["away_elo"],
                    neutral_venue=match["neutral"],
                ),
                CALIBRATION_TEMPERATURE,
            )
            market = market_probabilities(odds_row["decimal_odds"], method)
            outcome = observed_outcome(
                match["home_goals"],
                match["away_goals"],
            )
            year_rows.append((independent, market, outcome, match["neutral"]))
        per_year[year] = year_rows
    return per_year


def mean_log_loss(rows: list[tuple], market_weight: float) -> float:
    return sum(
        log_loss(
            market_assisted_forecast(independent, market, market_weight),
            outcome,
        )
        for independent, market, outcome, _ in rows
    ) / len(rows)


def market_mean_log_loss(rows: list[tuple]) -> float:
    return sum(log_loss(market, outcome) for _, market, outcome, _ in rows) / len(
        rows
    )


def paired_interval(
    rows: list[tuple],
    market_weight: float,
    *,
    iterations: int = 2000,
    seed: int = 2026,
) -> list[float]:
    """Bootstrap paired log-loss difference: assisted minus independent."""
    differences = [
        log_loss(
            market_assisted_forecast(independent, market, market_weight),
            outcome,
        )
        - log_loss(independent, outcome)
        for independent, market, outcome, _ in rows
    ]
    rng = random.Random(seed)
    samples = [
        sum(rng.choice(differences) for _ in differences) / len(differences)
        for _ in range(iterations)
    ]
    samples.sort()
    return [samples[int(0.025 * iterations)], samples[int(0.975 * iterations)]]


def evaluate_method(per_year: dict[int, list[tuple]]) -> dict:
    selection = [
        row for year in SELECTION_YEARS for row in per_year.get(year, ())
    ]
    confirmation = per_year.get(CONFIRMATION_YEAR, [])
    confirmation_neutral = [row for row in confirmation if row[3]]
    if not selection:
        raise ValueError("no selection rows matched the historical dataset")

    market_weight = fit_market_weight(
        [
            (independent, market, outcome)
            for independent, market, outcome, _ in selection
        ]
    )

    def metrics(rows: list[tuple]) -> dict:
        if not rows:
            return {"n": 0}
        baseline = mean_log_loss(rows, 0.0)
        assisted = mean_log_loss(rows, market_weight)
        return {
            "n": len(rows),
            "calibrated_independent_log_loss": baseline,
            "market_only_log_loss": market_mean_log_loss(rows),
            "assisted_log_loss": assisted,
            "difference": assisted - baseline,
            "paired_bootstrap_95": paired_interval(rows, market_weight),
        }

    return {
        "market_weight": market_weight,
        "selection": metrics(selection),
        "confirmation": metrics(confirmation),
        "confirmation_neutral": metrics(confirmation_neutral),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odds", type=Path, required=True)
    parser.add_argument(
        "--horizon",
        choices=("opening", "closing"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    odds = load_odds_csv(args.odds, args.horizon)
    if not odds:
        parser.error(f"no {args.horizon} odds rows found in {args.odds}")

    all_matches = load_matches_with_self_elo(date(2026, 6, 12))
    methods = {
        method: evaluate_method(collect_rows(all_matches, odds, method))
        for method in METHODS
    }
    selected_method = min(
        methods,
        key=lambda method: methods[method]["selection"]["assisted_log_loss"],
    )
    winner = methods[selected_method]

    enough_data = (
        winner["selection"]["n"] >= MIN_SELECTION
        and winner["confirmation"]["n"] >= MIN_CONFIRMATION
        and winner["confirmation_neutral"]["n"] >= MIN_CONFIRMATION_NEUTRAL
    )
    improves_all = all(
        winner[name].get("difference", 1.0) < 0.0
        for name in ("selection", "confirmation", "confirmation_neutral")
    )
    all_intervals_below_zero = all(
        winner[name].get("paired_bootstrap_95", [1.0, 1.0])[1] < 0.0
        for name in ("selection", "confirmation", "confirmation_neutral")
    )
    adopted = enough_data and improves_all and all_intervals_below_zero

    report = {
        "odds_file": str(args.odds),
        "horizon": args.horizon,
        "half_life_days": HALF_LIFE_DAYS,
        "independent_calibration_temperature": CALIBRATION_TEMPERATURE,
        "selection_years": SELECTION_YEARS,
        "confirmation_year": CONFIRMATION_YEAR,
        "methods": methods,
        "selected_method": selected_method,
        "gate": {
            "minimum_rows": {
                "selection": MIN_SELECTION,
                "confirmation": MIN_CONFIRMATION,
                "confirmation_neutral": MIN_CONFIRMATION_NEUTRAL,
            },
            "enough_data": enough_data,
            "improves_all_three_slices": improves_all,
            "all_paired_bootstrap_intervals_below_zero": (
                all_intervals_below_zero
            ),
        },
        "adopted": adopted,
        "claim_boundary": (
            "The market-assisted forecast is reported separately and is not "
            "evidence that the independent model beats the market. Its "
            "baseline is the calibrated production forecast, not raw T=1 "
            "Dixon-Coles output."
        ),
    }
    output = args.output or MODEL_DIR / f"market_blend_{args.horizon}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    print(
        f"selected={selected_method} "
        f"market_weight={winner['market_weight']:.4f} adopted={adopted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
