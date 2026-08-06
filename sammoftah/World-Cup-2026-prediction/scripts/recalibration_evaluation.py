"""Post-hoc temperature-scaling recalibration for the shipped Dixon-Coles Elo
model.

The walk-forward folds from ``backtest_walk_forward.py`` (refit per test
year at ``HALF_LIFE_DAYS=180.0``, the current shipped half-life -- see
``models/upgrade_evaluation.json``) are reused to collect out-of-fold
forecasts for every match 2018-2026. A single temperature ``T`` (see
``forecasting/calibration.py``) is fit on the pooled SELECTION_YEARS
(2018-2025) out-of-fold forecasts and evaluated against the ``T=1``
(no-op) baseline using the same three-way selection/confirmation discipline
as ``upgrade_evaluation.py``:

  - SELECTION_YEARS (2018-2025): the fitted T must beat T=1 on mean log loss
    here.
  - CONFIRMATION_YEAR (2026): held out from fitting. The fitted T must ALSO
    beat T=1 on this fold, both overall and on the neutral-venue subset.

Writes models/recalibration_evaluation.json. Does not modify
src/underdog_lab/world_cup/forecasting.py or models/backtest_report.json --
adopting the fitted temperature is a separate, human-reviewed step.

Usage:
  python scripts/recalibration_evaluation.py
"""

from __future__ import annotations

import json
import random
from datetime import date

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.calibration import apply_temperature, fit_temperature

from backtest_common import (
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
    score_candidate,
)

REPORT_PATH = MODEL_DIR / "recalibration_evaluation.json"

HALF_LIFE_DAYS = 180.0
SELECTION_YEARS = list(range(2018, 2026))
CONFIRMATION_YEAR = 2026
ALL_YEARS = SELECTION_YEARS + [CONFIRMATION_YEAR]

EMPTY_TOTALS = {"log_loss": 0.0, "brier": 0.0, "rps": 0.0}
BOOTSTRAP_ITERATIONS = 2000


def fold_matches(all_matches: list[dict], test_year: int):
    train_cutoff = date(test_year - 1, 12, 31)
    train_matches = [m for m in all_matches if m["date"] <= train_cutoff]
    test_matches = [m for m in all_matches if m["date"].year == test_year]
    return train_cutoff, train_matches, test_matches


def collect_out_of_fold(all_matches: list[dict], years: list[int]) -> dict[int, list[tuple]]:
    """For each year, fit a model on data strictly before it and forecast
    every match played during it. Returns {year: [(forecast, outcome, is_neutral), ...]}."""
    per_year: dict[int, list[tuple]] = {}
    for year in years:
        train_cutoff, train_matches, test_matches = fold_matches(all_matches, year)
        if not test_matches:
            continue
        model = fit_dixon_coles(train_matches, train_cutoff, HALF_LIFE_DAYS)
        rows = []
        for match in test_matches:
            forecast = model.forecast(match["home_elo"], match["away_elo"], neutral_venue=match["neutral"])
            outcome = observed_outcome(match["home_goals"], match["away_goals"])
            rows.append((forecast, outcome, match["neutral"]))
        per_year[year] = rows
    return per_year


def _aggregate(rows: list[tuple], temperature: float) -> tuple[dict, dict, int, int]:
    """rows: list of (forecast, outcome, is_neutral). Returns (mean_all, mean_neutral, n_all, n_neutral)."""
    totals_all = dict(EMPTY_TOTALS)
    totals_neutral = dict(EMPTY_TOTALS)
    n_all = 0
    n_neutral = 0
    for forecast, outcome, is_neutral in rows:
        scores = score_candidate(apply_temperature(forecast, temperature), outcome)
        for key, value in scores.items():
            totals_all[key] += value
        n_all += 1
        if is_neutral:
            for key, value in scores.items():
                totals_neutral[key] += value
            n_neutral += 1
    mean_all = {k: v / n_all for k, v in totals_all.items()} if n_all else {}
    mean_neutral = {k: v / n_neutral for k, v in totals_neutral.items()} if n_neutral else {}
    return mean_all, mean_neutral, n_all, n_neutral


def paired_log_loss_interval(
    rows: list[tuple],
    temperature: float,
    *,
    seed: int = 2026,
) -> list[float]:
    """Bootstrap fitted-minus-baseline log-loss differences."""
    differences = [
        score_candidate(apply_temperature(forecast, temperature), outcome)[
            "log_loss"
        ]
        - score_candidate(forecast, outcome)["log_loss"]
        for forecast, outcome, _ in rows
    ]
    rng = random.Random(seed)
    samples = [
        sum(rng.choice(differences) for _ in differences) / len(differences)
        for _ in range(BOOTSTRAP_ITERATIONS)
    ]
    samples.sort()
    return [
        samples[int(0.025 * BOOTSTRAP_ITERATIONS)],
        samples[int(0.975 * BOOTSTRAP_ITERATIONS)],
    ]


def main() -> None:
    all_matches = load_matches_with_self_elo(date(2026, 6, 12))
    per_year = collect_out_of_fold(all_matches, ALL_YEARS)

    selection_rows = [row for year in SELECTION_YEARS for row in per_year.get(year, [])]
    confirmation_rows = per_year.get(CONFIRMATION_YEAR, [])
    confirmation_neutral_rows = [
        row for row in confirmation_rows if row[2]
    ]

    temperature = fit_temperature([(forecast, outcome) for forecast, outcome, _ in selection_rows])

    selection_baseline, _, n_selection, _ = _aggregate(selection_rows, 1.0)
    selection_fitted, _, _, _ = _aggregate(selection_rows, temperature)

    confirm_baseline_all, confirm_baseline_neutral, n_confirm, n_confirm_neutral = _aggregate(
        confirmation_rows, 1.0
    )
    confirm_fitted_all, confirm_fitted_neutral, _, _ = _aggregate(confirmation_rows, temperature)

    beats_on_selection = selection_fitted["log_loss"] < selection_baseline["log_loss"]
    beats_on_confirmation = confirm_fitted_all["log_loss"] < confirm_baseline_all["log_loss"]
    beats_on_confirmation_neutral = (
        confirm_fitted_neutral["log_loss"] < confirm_baseline_neutral["log_loss"]
    )
    intervals = {
        "selection": paired_log_loss_interval(selection_rows, temperature),
        "confirmation": paired_log_loss_interval(
            confirmation_rows,
            temperature,
        ),
        "confirmation_neutral": paired_log_loss_interval(
            confirmation_neutral_rows,
            temperature,
        ),
    }
    intervals_below_zero = all(interval[1] < 0.0 for interval in intervals.values())
    adopted = (
        temperature != 1.0
        and beats_on_selection
        and beats_on_confirmation
        and beats_on_confirmation_neutral
        and intervals_below_zero
    )

    report = {
        "half_life_days": HALF_LIFE_DAYS,
        "selection_years": SELECTION_YEARS,
        "confirmation_year": CONFIRMATION_YEAR,
        "n_selection": n_selection,
        "n_confirmation": n_confirm,
        "n_confirmation_neutral": n_confirm_neutral,
        "fitted_temperature": temperature,
        "selection": {
            "baseline_t1": selection_baseline,
            "fitted_t": selection_fitted,
        },
        "confirmation": {
            "baseline_t1": confirm_baseline_all,
            "fitted_t": confirm_fitted_all,
        },
        "confirmation_neutral": {
            "baseline_t1": confirm_baseline_neutral,
            "fitted_t": confirm_fitted_neutral,
        },
        "paired_log_loss_difference_bootstrap_95": intervals,
        "gate": {
            "beats_baseline_on_selection": beats_on_selection,
            "beats_baseline_on_confirmation": beats_on_confirmation,
            "beats_baseline_on_confirmation_neutral": beats_on_confirmation_neutral,
            "all_paired_bootstrap_intervals_below_zero": intervals_below_zero,
        },
        "adopted": adopted,
        "criterion": (
            "The fitted temperature must differ from 1.0 and produce a lower "
            "mean log loss than the T=1 (no-op) baseline on the pooled "
            "2018-2025 selection folds AND on the held-out 2026 confirmation "
            "fold, both overall and on its neutral-venue subset. Paired 95% "
            "bootstrap intervals for all three reported slices must remain "
            "below zero. The neutral subset overlaps the overall 2026 fold "
            "and is not an independent confirmation sample."
        ),
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print("fitted temperature:", temperature, "(adopted:", adopted, ")")
    print(json.dumps(report["selection"], indent=2))
    print(json.dumps(report["confirmation"], indent=2))
    print(json.dumps(report["confirmation_neutral"], indent=2))
    print(json.dumps(report["gate"], indent=2))


if __name__ == "__main__":
    main()
