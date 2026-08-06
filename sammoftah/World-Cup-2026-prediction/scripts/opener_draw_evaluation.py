from __future__ import annotations

import json

from underdog_lab.config import MODEL_DIR
from underdog_lab.forecasting.draw_adjustment import (
    apply_draw_logit_adjustment,
    fit_draw_logit_adjustment,
)

from tournament_experiment_common import (
    CONFIRMATION_EDITIONS,
    collect_edition_rows,
    edition_cluster_interval,
    mean_loss,
    production_forecast,
    split_selection_confirmation,
)

REPORT_PATH = MODEL_DIR / "opener_draw_evaluation.json"


def main() -> None:
    opener_rows = [
        row for row in collect_edition_rows() if row["is_inferred_opener"]
    ]
    selection, confirmation = split_selection_confirmation(opener_rows)
    adjustment = fit_draw_logit_adjustment(
        [(production_forecast(row), row["outcome"]) for row in selection]
    )
    baseline_fn = production_forecast

    def candidate_fn(row):
        return apply_draw_logit_adjustment(
            production_forecast(row),
            adjustment,
        )

    selection_baseline = mean_loss(selection, baseline_fn)
    selection_candidate = mean_loss(selection, candidate_fn)
    confirmation_baseline = mean_loss(confirmation, baseline_fn)
    confirmation_candidate = mean_loss(confirmation, candidate_fn)
    intervals = {
        "selection": edition_cluster_interval(
            selection,
            candidate_fn,
            baseline_fn,
        ),
        "confirmation": edition_cluster_interval(
            confirmation,
            candidate_fn,
            baseline_fn,
        ),
    }
    gate_passed = (
        selection_candidate < selection_baseline
        and confirmation_candidate < confirmation_baseline
        and all(interval[1] < 0.0 for interval in intervals.values())
    )
    report = {
        "label_status": (
            "Inferred from tournament code, date gaps, and each team's first "
            "match because the source CSV has no official stage/matchday field."
        ),
        "draw_logit_adjustment": adjustment,
        "selection_editions": sorted(
            {row["edition_id"] for row in selection}
        ),
        "confirmation_editions": sorted(CONFIRMATION_EDITIONS),
        "n_selection": len(selection),
        "n_confirmation": len(confirmation),
        "selection": {
            "production_log_loss": selection_baseline,
            "candidate_log_loss": selection_candidate,
        },
        "confirmation": {
            "production_log_loss": confirmation_baseline,
            "candidate_log_loss": confirmation_candidate,
        },
        "edition_cluster_bootstrap_95": intervals,
        "research_gate_passed": gate_passed,
        "production_adopted": False,
        "criterion": (
            "This is research-only. Even a passing historical gate must be "
            "pre-registered before prospective evaluation; 2026 matches are "
            "excluded because they motivated the hypothesis."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
