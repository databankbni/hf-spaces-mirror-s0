from __future__ import annotations

import json

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.optimization import bounded_minimize

from tournament_experiment_common import (
    CONFIRMATION_EDITIONS,
    collect_edition_rows,
    edition_cluster_interval,
    mean_loss,
    production_forecast,
    split_selection_confirmation,
)

REPORT_PATH = MODEL_DIR / "host_adjustment_evaluation.json"
CANDIDATE_BOOSTS = (0.0, 25.0, 50.0)


def main() -> None:
    host_rows = [
        row
        for row in collect_edition_rows()
        if row["home_is_host"] or row["away_is_host"]
    ]
    selection, confirmation = split_selection_confirmation(host_rows)

    def selection_loss(boost: float) -> float:
        return mean_loss(
            selection,
            lambda row: production_forecast(
                row,
                host_boost=boost,
                force_neutral=True,
            ),
        )

    fitted_boost = bounded_minimize(selection_loss, -50.0, 100.0)
    candidates = sorted({*CANDIDATE_BOOSTS, fitted_boost})
    evaluations = {}
    for boost in candidates:
        def forecast_fn(row, value=boost):
            return production_forecast(
                row,
                host_boost=value,
                force_neutral=True,
            )

        evaluations[str(boost)] = {
            "selection_log_loss": mean_loss(selection, forecast_fn),
            "confirmation_log_loss": mean_loss(confirmation, forecast_fn),
        }

    def baseline_fn(row):
        return production_forecast(
            row,
            host_boost=0.0,
            force_neutral=True,
        )

    def fitted_fn(row):
        return production_forecast(
            row,
            host_boost=fitted_boost,
            force_neutral=True,
        )

    selection_interval = edition_cluster_interval(
        selection,
        fitted_fn,
        baseline_fn,
    )
    confirmation_interval = edition_cluster_interval(
        confirmation,
        fitted_fn,
        baseline_fn,
    )
    fitted = evaluations[str(fitted_boost)]
    baseline = evaluations["0.0"]
    adopted = (
        fitted_boost != 0.0
        and fitted["selection_log_loss"] < baseline["selection_log_loss"]
        and fitted["confirmation_log_loss"] < baseline["confirmation_log_loss"]
        and selection_interval[1] < 0.0
        and confirmation_interval[1] < 0.0
    )
    report = {
        "candidate_boosts": CANDIDATE_BOOSTS,
        "fitted_host_elo_boost": fitted_boost,
        "selection_editions": sorted(
            {row["edition_id"] for row in selection}
        ),
        "confirmation_editions": sorted(CONFIRMATION_EDITIONS),
        "n_selection": len(selection),
        "n_confirmation": len(confirmation),
        "evaluations": evaluations,
        "edition_cluster_bootstrap_95": {
            "selection": selection_interval,
            "confirmation": confirmation_interval,
        },
        "adopted": adopted,
        "criterion": (
            "A host boost is adopted only if the fitted one-parameter value "
            "beats no boost on both selection and completed-edition "
            "confirmation data, with edition-cluster bootstrap intervals "
            "entirely below zero."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
