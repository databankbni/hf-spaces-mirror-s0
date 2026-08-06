from __future__ import annotations

import json
import random
from datetime import date

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.calibration import apply_temperature
from underdog_lab.forecasting.scoring import (
    brier_score,
    log_loss,
    rank_probability_score,
)
from underdog_lab.forecasting.vector_calibration import (
    apply_vector_scaling,
    fit_vector_scaling,
)
from underdog_lab.world_cup.forecasting import CALIBRATION_TEMPERATURE

from backtest_common import (
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
)

REPORT_PATH = MODEL_DIR / "vector_calibration_evaluation.json"
HALF_LIFE_DAYS = 180.0
SELECTION_YEARS = list(range(2018, 2026))
ROBUSTNESS_YEAR = 2026
REGULARIZATION_GRID = (0.0001, 0.001, 0.01, 0.1)


def collect_rows() -> dict[int, list[tuple]]:
    matches = load_matches_with_self_elo(date(2026, 6, 12))
    per_year = {}
    for year in [*SELECTION_YEARS, ROBUSTNESS_YEAR]:
        cutoff = date(year - 1, 12, 31)
        train = [match for match in matches if match["date"] <= cutoff]
        test = [match for match in matches if match["date"].year == year]
        model = fit_dixon_coles(train, cutoff, HALF_LIFE_DAYS)
        per_year[year] = [
            (
                apply_temperature(
                    model.forecast(
                        match["home_elo"],
                        match["away_elo"],
                        neutral_venue=match["neutral"],
                    ),
                    CALIBRATION_TEMPERATURE,
                ),
                observed_outcome(match["home_goals"], match["away_goals"]),
                match["neutral"],
            )
            for match in test
        ]
    return per_year


def metrics(rows: list[tuple], parameters: list[float] | None = None) -> dict:
    forecasts = [
        (
            apply_vector_scaling(forecast, parameters)
            if parameters is not None
            else forecast,
            outcome,
        )
        for forecast, outcome, _ in rows
    ]
    return {
        "n": len(rows),
        "log_loss": sum(log_loss(fc, outcome) for fc, outcome in forecasts)
        / len(rows),
        "brier": sum(brier_score(fc, outcome) for fc, outcome in forecasts)
        / len(rows),
        "rps": sum(rank_probability_score(fc, outcome) for fc, outcome in forecasts)
        / len(rows),
        "ece": expected_calibration_error(forecasts),
    }


def expected_calibration_error(rows: list[tuple], bins: int = 10) -> float:
    buckets = [[] for _ in range(bins)]
    for forecast, outcome in rows:
        probabilities = (forecast.p_home, forecast.p_draw, forecast.p_away)
        index = max(range(3), key=probabilities.__getitem__)
        confidence = probabilities[index]
        correct = outcome == ("home", "draw", "away")[index]
        buckets[min(bins - 1, int(confidence * bins))].append(
            (confidence, correct)
        )
    total = len(rows)
    return sum(
        len(bucket)
        / total
        * abs(
            sum(confidence for confidence, _ in bucket) / len(bucket)
            - sum(correct for _, correct in bucket) / len(bucket)
        )
        for bucket in buckets
        if bucket
    )


def blocked_interval(
    rows: list[tuple],
    parameters: list[float],
    *,
    iterations: int = 3000,
) -> list[float]:
    differences = [
        log_loss(apply_vector_scaling(forecast, parameters), outcome)
        - log_loss(forecast, outcome)
        for forecast, outcome, _ in rows
    ]
    rng = random.Random(2026)
    block = 20
    blocks = [
        differences[index : index + block]
        for index in range(0, len(differences), block)
    ]
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(blocks) for _ in blocks]
        values = [value for group in selected for value in group]
        samples.append(sum(values) / len(values))
    samples.sort()
    return [samples[int(iterations * 0.025)], samples[int(iterations * 0.975)]]


def main() -> None:
    per_year = collect_rows()
    rolling_scores = {}
    for regularization in REGULARIZATION_GRID:
        fold_losses = []
        for validation_year in range(2021, 2026):
            train_rows = [
                row
                for year in SELECTION_YEARS
                if year < validation_year
                for row in per_year[year]
            ]
            validation_rows = per_year[validation_year]
            parameters = fit_vector_scaling(
                [(forecast, outcome) for forecast, outcome, _ in train_rows],
                regularization=regularization,
            )
            fold_losses.append(metrics(validation_rows, parameters)["log_loss"])
        rolling_scores[str(regularization)] = sum(fold_losses) / len(fold_losses)
    selected_regularization = min(
        REGULARIZATION_GRID,
        key=lambda value: rolling_scores[str(value)],
    )
    selection = [
        row for year in SELECTION_YEARS for row in per_year[year]
    ]
    parameters = fit_vector_scaling(
        [(forecast, outcome) for forecast, outcome, _ in selection],
        regularization=selected_regularization,
    )
    robustness = per_year[ROBUSTNESS_YEAR]
    robustness_neutral = [row for row in robustness if row[2]]
    slices = {
        "selection_descriptive": selection,
        "robustness_2026_viewed": robustness,
        "robustness_2026_neutral_viewed": robustness_neutral,
    }
    report_slices = {
        name: {
            "baseline": metrics(rows),
            "candidate": metrics(rows, parameters),
            "blocked_log_loss_difference_95": blocked_interval(rows, parameters),
        }
        for name, rows in slices.items()
    }
    improves_robustness = all(
        value["candidate"]["log_loss"] < value["baseline"]["log_loss"]
        and value["candidate"]["brier"] <= value["baseline"]["brier"]
        and value["candidate"]["rps"] <= value["baseline"]["rps"] + 0.001
        and value["candidate"]["ece"] <= value["baseline"]["ece"] + 0.01
        and value["blocked_log_loss_difference_95"][1] < 0
        for name, value in report_slices.items()
        if name.startswith("robustness")
    )
    report = {
        "baseline": "shipped global temperature calibration",
        "method": "regularized five-parameter multiclass vector scaling",
        "rolling_origin_regularization_scores": rolling_scores,
        "selected_regularization": selected_regularization,
        "parameters": parameters,
        "slices": report_slices,
        "research_gate_passed": improves_robustness,
        "production_adopted": False,
        "claim_boundary": (
            "The 2026 slice has already been viewed and used in prior model "
            "decisions. It is a robustness diagnostic, not pristine "
            "confirmation. Production adoption requires a future "
            "pre-registered evaluation period."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
