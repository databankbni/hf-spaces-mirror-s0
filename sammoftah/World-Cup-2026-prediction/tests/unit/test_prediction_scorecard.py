import math

import pytest

from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.predictions import _summarize, scored_track_records


def test_evidence_summary_explains_freezing_and_proper_scores():
    from underdog_lab.ui.components import evidence_summary_html

    html = evidence_summary_html(
        {
            "coverage": {
                "completed": 72,
                "scored": 65,
                "rate": 65 / 72,
                "excluded": 7,
                "exclusion_reason": "no_verified_pre_kickoff_artifact",
            },
            "prospective": {
                "n": 65,
                "log_loss_skill_vs_uniform": 0.169,
            },
        }
    )

    assert "pre-registered forecast scored against a real result" in html
    assert "65 of 72" in html
    assert "sealed with SHA-256 manifests" in html
    assert "rejected automatically, not silently backfilled" in html
    assert "+16.9%" in html


def test_track_record_labels_retrospective_replay_as_diagnostic():
    from pathlib import Path

    source = Path("src/underdog_lab/ui/app.py").read_text(encoding="utf-8")

    assert "evidence_summary_html(records)" in source
    assert "Retrospective diagnostic — not prospective evidence" in source


def test_summary_reports_accuracy_and_log_loss_skill():
    summary = _summarize(
        [
            {"log_loss": 0.4, "brier": 0.2, "rps": 0.1, "correct": True},
            {"log_loss": 1.2, "brier": 0.8, "rps": 0.3, "correct": False},
        ]
    )

    assert summary["correct"] == 1
    assert summary["accuracy"] == 0.5
    assert summary["log_loss_skill_vs_uniform"] == pytest.approx(
        1 - summary["mean_log_loss"] / -math.log(1 / 3)
    )


def test_empty_summary_uses_none_for_unavailable_metrics():
    summary = _summarize([])

    assert summary["correct"] == 0
    assert summary["accuracy"] is None
    assert summary["log_loss_skill_vs_uniform"] is None


def test_complete_snapshot_scores_only_verified_artifacts():
    repository = TournamentRepository()
    records = scored_track_records(
        repository.fixtures,
        repository.team_by_name,
    )

    assert records["coverage"]["completed"] == 72
    assert records["coverage"]["scored"] == 65
    assert records["coverage"]["rate"] == pytest.approx(65 / 72)
    assert records["prospective"]["n"] == 65
    assert records["artifact_audit"]["eligible"] == 65
    assert records["coverage"]["excluded_fixture_ids"] == [
        "WC26-001",
        "WC26-002",
        "WC26-007",
        "WC26-013",
        "WC26-014",
        "WC26-019",
        "WC26-020",
    ]
