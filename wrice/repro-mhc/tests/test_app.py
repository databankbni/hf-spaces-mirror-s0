from pathlib import Path

import app


def test_space_summary_exposes_all_five_honest_statuses():
    rows = app.evidence_summary()
    assert len(rows) == 5
    assert [row[1] for row in rows] == [
        "partial",
        "partial",
        "partial",
        "unavailable",
        "unavailable",
    ]
    assert "27B" in rows[-1][4]


def test_space_readme_has_exact_discovery_tags():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "paper-mDhyxu8WRb" in readme
    assert "icml2026-repro" in readme
    assert "app_file: app.py" in readme
