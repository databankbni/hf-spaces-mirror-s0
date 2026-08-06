from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date

from underdog_lab.forecasting.calibration import apply_temperature
from underdog_lab.forecasting.scoring import log_loss
from underdog_lab.forecasting.tournament_editions import assign_edition_metadata
from underdog_lab.world_cup.forecasting import CALIBRATION_TEMPERATURE

from backtest_common import (
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
)

HALF_LIFE_DAYS = 180.0
CONFIRMATION_EDITIONS = frozenset({"AC-2024", "CA-2024", "EC-2024", "WC-2022"})


def collect_edition_rows() -> list[dict]:
    all_matches = load_matches_with_self_elo(date(2026, 6, 12))
    major = assign_edition_metadata(all_matches)
    rows = []
    for edition_id in sorted({match["edition_id"] for match in major}):
        if edition_id.endswith("-2026"):
            continue
        edition_matches = [
            match for match in major if match["edition_id"] == edition_id
        ]
        cutoff = min(match["date"] for match in edition_matches)
        train_cutoff = cutoff.fromordinal(cutoff.toordinal() - 1)
        train = [match for match in all_matches if match["date"] <= train_cutoff]
        model = fit_dixon_coles(train, train_cutoff, HALF_LIFE_DAYS)
        for match in edition_matches:
            rows.append(
                {
                    **match,
                    "model": model,
                    "outcome": observed_outcome(
                        match["home_goals"],
                        match["away_goals"],
                    ),
                }
            )
    return rows


def production_forecast(
    row: dict,
    *,
    host_boost: float = 0.0,
    force_neutral: bool = False,
):
    home_elo = row["home_elo"] + (host_boost if row["home_is_host"] else 0.0)
    away_elo = row["away_elo"] + (host_boost if row["away_is_host"] else 0.0)
    return apply_temperature(
        row["model"].forecast(
            home_elo,
            away_elo,
            neutral_venue=True if force_neutral else row["neutral"],
        ),
        CALIBRATION_TEMPERATURE,
    )


def mean_loss(rows: list[dict], forecast_fn: Callable[[dict], object]) -> float:
    return sum(log_loss(forecast_fn(row), row["outcome"]) for row in rows) / len(
        rows
    )


def edition_cluster_interval(
    rows: list[dict],
    candidate_fn: Callable[[dict], object],
    baseline_fn: Callable[[dict], object],
    *,
    iterations: int = 4000,
    seed: int = 2026,
) -> list[float]:
    by_edition: dict[str, list[float]] = {}
    for row in rows:
        by_edition.setdefault(row["edition_id"], []).append(
            log_loss(candidate_fn(row), row["outcome"])
            - log_loss(baseline_fn(row), row["outcome"])
        )
    editions = sorted(by_edition)
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(editions) for _ in editions]
        differences = [
            difference
            for edition in selected
            for difference in by_edition[edition]
        ]
        samples.append(sum(differences) / len(differences))
    samples.sort()
    return [
        samples[int(0.025 * iterations)],
        samples[int(0.975 * iterations)],
    ]


def split_selection_confirmation(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    selection = [
        row for row in rows if row["edition_id"] not in CONFIRMATION_EDITIONS
    ]
    confirmation = [
        row for row in rows if row["edition_id"] in CONFIRMATION_EDITIONS
    ]
    return selection, confirmation
