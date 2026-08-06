"""Workstream 1 & 2 experiments: recency half-life and a second-model ensemble.

Two changes to the walk-forward-fitted Dixon-Coles Elo model are evaluated
here, both gated by the same no-lookahead, selection/confirmation discipline
used in ``backtest_walk_forward.py``'s ship gate:

  1. Recency half-life (Workstream 1): ``HALF_LIFE_DAYS=1095`` (3 years) in
     the shipped fit was never tuned. This sweeps a range of half-lives.

  2. Ensemble with a second, independently-computed rating (Workstream 2):
     ``forecasting/self_elo.py`` computes a strength rating from scratch
     (fixed K-factor, goal-difference multiplier, neutral start) using only
     match results -- independent of the eloratings.net ``home_elo``/
     ``away_elo`` columns the shipped model uses. A second Dixon-Coles model
     is fit on this rating and blended with the eloratings-Elo model via a
     logarithmic opinion pool (``forecasting/ensemble.py``).

Selection vs confirmation:

  - SELECTION_YEARS (2018-2025): candidates are ranked by mean log loss here.
  - CONFIRMATION_YEAR (2026): held out from selection entirely. A candidate
    is only declared a winner if it ALSO beats the baseline on this fold,
    both overall and on the neutral-venue subset -- the same three-way
    criterion as the official ship gate, applied here for selection instead
    of being skipped.

Writes models/upgrade_evaluation.json. Does not modify
src/underdog_lab/world_cup/forecasting.py, models/elo_fit_report.json, or
models/backtest_report.json -- promoting a winning configuration into the
shipped MODEL is a separate, human-reviewed step.

Usage:
  python scripts/upgrade_evaluation.py
"""

from __future__ import annotations

import json
from datetime import date

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.ensemble import blend_forecasts

from backtest_common import (
    fit_dixon_coles,
    load_matches_with_self_elo,
    observed_outcome,
    score_candidate,
)

REPORT_PATH = MODEL_DIR / "upgrade_evaluation.json"

SELECTION_YEARS = list(range(2018, 2026))
CONFIRMATION_YEAR = 2026
ALL_YEARS = SELECTION_YEARS + [CONFIRMATION_YEAR]

CURRENT_HALF_LIFE = 1095.0
HALF_LIFE_SWEEP = [180.0, 365.0, 547.0, 730.0, 1095.0, 1460.0, 2190.0]
ENSEMBLE_WEIGHTS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

EMPTY_TOTALS = {"log_loss": 0.0, "brier": 0.0, "rps": 0.0}


def fold_matches(all_matches: list[dict], test_year: int):
    train_cutoff = date(test_year - 1, 12, 31)
    train_matches = [m for m in all_matches if m["date"] <= train_cutoff]
    test_matches = [m for m in all_matches if m["date"].year == test_year]
    return train_cutoff, train_matches, test_matches


def _aggregate(rows: list[tuple[dict, bool]]) -> tuple[dict, dict, int, int]:
    """rows: list of (score_dict, is_neutral). Returns (mean_all, mean_neutral, n_all, n_neutral)."""
    totals_all = dict(EMPTY_TOTALS)
    totals_neutral = dict(EMPTY_TOTALS)
    n_all = 0
    n_neutral = 0
    for scores, is_neutral in rows:
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


def eval_eloratings_model(all_matches: list[dict], years: list[int], half_life: float) -> dict:
    """Fit the eloratings-Elo Dixon-Coles model per fold and score it."""
    rows: list[tuple[dict, bool]] = []
    per_year: dict[int, dict] = {}
    for year in years:
        train_cutoff, train_matches, test_matches = fold_matches(all_matches, year)
        if not test_matches:
            continue
        model = fit_dixon_coles(train_matches, train_cutoff, half_life)
        year_rows = []
        for match in test_matches:
            forecast = model.forecast(match["home_elo"], match["away_elo"], neutral_venue=match["neutral"])
            outcome = observed_outcome(match["home_goals"], match["away_goals"])
            scores = score_candidate(forecast, outcome)
            year_rows.append((scores, match["neutral"]))
        rows.extend(year_rows)
        mean_all, mean_neutral, n_all, n_neutral = _aggregate(year_rows)
        per_year[year] = {"mean_scores": mean_all, "neutral_mean_scores": mean_neutral, "n": n_all, "n_neutral": n_neutral}
    mean_all, mean_neutral, n_all, n_neutral = _aggregate(rows)
    return {"per_year": per_year, "mean_scores": mean_all, "neutral_mean_scores": mean_neutral, "n": n_all, "n_neutral": n_neutral}


def fit_fold_models(all_matches: list[dict], years: list[int], half_life: float) -> dict[int, dict]:
    """Fit BOTH the eloratings-Elo and self-Elo models per fold."""
    folds = {}
    for year in years:
        train_cutoff, train_matches, test_matches = fold_matches(all_matches, year)
        if not test_matches:
            continue
        elo_model = fit_dixon_coles(train_matches, train_cutoff, half_life)
        self_model = fit_dixon_coles(train_matches, train_cutoff, half_life, elo_keys=("self_home_elo", "self_away_elo"))
        folds[year] = {"test_matches": test_matches, "elo_model": elo_model, "self_model": self_model}
    return folds


def eval_ensemble(folds: dict[int, dict], years: list[int], weight: float) -> dict:
    rows: list[tuple[dict, bool]] = []
    per_year: dict[int, dict] = {}
    for year in years:
        if year not in folds:
            continue
        fold = folds[year]
        year_rows = []
        for match in fold["test_matches"]:
            elo_forecast = fold["elo_model"].forecast(match["home_elo"], match["away_elo"], neutral_venue=match["neutral"])
            self_forecast = fold["self_model"].forecast(match["self_home_elo"], match["self_away_elo"], neutral_venue=match["neutral"])
            forecast = blend_forecasts(elo_forecast, self_forecast, weight) if weight < 1.0 else elo_forecast
            outcome = observed_outcome(match["home_goals"], match["away_goals"])
            scores = score_candidate(forecast, outcome)
            year_rows.append((scores, match["neutral"]))
        rows.extend(year_rows)
        mean_all, mean_neutral, n_all, n_neutral = _aggregate(year_rows)
        per_year[year] = {"mean_scores": mean_all, "neutral_mean_scores": mean_neutral, "n": n_all, "n_neutral": n_neutral}
    mean_all, mean_neutral, n_all, n_neutral = _aggregate(rows)
    return {"per_year": per_year, "mean_scores": mean_all, "neutral_mean_scores": mean_neutral, "n": n_all, "n_neutral": n_neutral}


def main() -> None:
    all_matches = load_matches_with_self_elo(date(2026, 6, 12))

    # --- Workstream 1: half-life sweep, selected on 2018-2025 only ---
    half_life_results = {}
    for half_life in HALF_LIFE_SWEEP:
        half_life_results[half_life] = eval_eloratings_model(all_matches, ALL_YEARS, half_life)

    def selection_mean(res: dict, metric: str = "log_loss") -> float:
        total = 0.0
        n = 0
        for year in SELECTION_YEARS:
            if year not in res["per_year"]:
                continue
            total += res["per_year"][year]["mean_scores"][metric] * res["per_year"][year]["n"]
            n += res["per_year"][year]["n"]
        return total / n

    half_life_selection = {hl: selection_mean(res) for hl, res in half_life_results.items()}
    best_half_life = min(half_life_selection, key=half_life_selection.get)

    confirm_current = half_life_results[CURRENT_HALF_LIFE]["per_year"][CONFIRMATION_YEAR]
    confirm_best = half_life_results[best_half_life]["per_year"][CONFIRMATION_YEAR]

    half_life_beats_on_selection = half_life_selection[best_half_life] < half_life_selection[CURRENT_HALF_LIFE]
    half_life_beats_on_confirmation = (
        confirm_best["mean_scores"]["log_loss"] < confirm_current["mean_scores"]["log_loss"]
    )
    half_life_beats_on_confirmation_neutral = (
        confirm_best["neutral_mean_scores"]["log_loss"] < confirm_current["neutral_mean_scores"]["log_loss"]
    )
    half_life_winner = (
        best_half_life
        if (
            best_half_life != CURRENT_HALF_LIFE
            and half_life_beats_on_selection
            and half_life_beats_on_confirmation
            and half_life_beats_on_confirmation_neutral
        )
        else CURRENT_HALF_LIFE
    )

    # --- Workstream 2: ensemble with self-Elo model, using half_life_winner ---
    folds = fit_fold_models(all_matches, ALL_YEARS, half_life_winner)

    ensemble_results = {weight: eval_ensemble(folds, ALL_YEARS, weight) for weight in ENSEMBLE_WEIGHTS}

    def ensemble_selection_mean(res: dict, metric: str = "log_loss") -> float:
        total = 0.0
        n = 0
        for year in SELECTION_YEARS:
            if year not in res["per_year"]:
                continue
            total += res["per_year"][year]["mean_scores"][metric] * res["per_year"][year]["n"]
            n += res["per_year"][year]["n"]
        return total / n

    ensemble_selection = {w: ensemble_selection_mean(res) for w, res in ensemble_results.items()}
    best_weight = min(ensemble_selection, key=ensemble_selection.get)

    confirm_ensemble_best = ensemble_results[best_weight]["per_year"][CONFIRMATION_YEAR]
    confirm_ensemble_baseline = ensemble_results[1.0]["per_year"][CONFIRMATION_YEAR]

    ensemble_beats_on_selection = ensemble_selection[best_weight] < ensemble_selection[1.0]
    ensemble_beats_on_confirmation = (
        confirm_ensemble_best["mean_scores"]["log_loss"] < confirm_ensemble_baseline["mean_scores"]["log_loss"]
    )
    ensemble_beats_on_confirmation_neutral = (
        confirm_ensemble_best["neutral_mean_scores"]["log_loss"]
        < confirm_ensemble_baseline["neutral_mean_scores"]["log_loss"]
    )
    ensemble_winner = (
        best_weight < 1.0
        and ensemble_beats_on_selection
        and ensemble_beats_on_confirmation
        and ensemble_beats_on_confirmation_neutral
    )

    report = {
        "selection_years": SELECTION_YEARS,
        "confirmation_year": CONFIRMATION_YEAR,
        "half_life_sweep": {
            "current_half_life": CURRENT_HALF_LIFE,
            "candidates": HALF_LIFE_SWEEP,
            "selection_mean_log_loss": half_life_selection,
            "best_half_life_by_selection": best_half_life,
            "confirmation": {
                "current": confirm_current,
                "best_candidate": confirm_best,
            },
            "gate": {
                "beats_current_on_selection": half_life_beats_on_selection,
                "beats_current_on_confirmation": half_life_beats_on_confirmation,
                "beats_current_on_confirmation_neutral": half_life_beats_on_confirmation_neutral,
            },
            "winner": half_life_winner,
            "adopted": half_life_winner != CURRENT_HALF_LIFE,
        },
        "ensemble": {
            "half_life_used": half_life_winner,
            "weights": ENSEMBLE_WEIGHTS,
            "weight_is_share_on_eloratings_model": True,
            "selection_mean_log_loss": ensemble_selection,
            "best_weight_by_selection": best_weight,
            "confirmation": {
                "eloratings_only": confirm_ensemble_baseline,
                "best_ensemble": confirm_ensemble_best,
            },
            "gate": {
                "beats_eloratings_only_on_selection": ensemble_beats_on_selection,
                "beats_eloratings_only_on_confirmation": ensemble_beats_on_confirmation,
                "beats_eloratings_only_on_confirmation_neutral": ensemble_beats_on_confirmation_neutral,
            },
            "adopted": ensemble_winner,
        },
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print("half_life winner:", half_life_winner, "(adopted:", report["half_life_sweep"]["adopted"], ")")
    print("ensemble best weight:", best_weight, "(adopted:", ensemble_winner, ")")
    print(json.dumps(half_life_selection, indent=2))
    print(json.dumps(ensemble_selection, indent=2))


if __name__ == "__main__":
    main()
