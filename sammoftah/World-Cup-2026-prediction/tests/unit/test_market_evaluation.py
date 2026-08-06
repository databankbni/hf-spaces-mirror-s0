from pathlib import Path

import pytest

from underdog_lab.forecasting.market_data import load_odds_csv


def _write(path: Path, captured_at: str, horizon: str = "closing") -> None:
    path.write_text(
        "date,home_team,away_team,kickoff_utc,captured_at,horizon,"
        "home_odds,draw_odds,away_odds\n"
        f"2026-01-01,AA,BB,2026-01-01T20:00:00Z,{captured_at},"
        f"{horizon},2.0,3.2,4.0\n",
        encoding="utf-8",
    )


def test_load_odds_accepts_timestamped_pre_kickoff_row(tmp_path):
    path = tmp_path / "odds.csv"
    _write(path, "2026-01-01T19:59:00Z")

    rows = load_odds_csv(path, "closing")

    assert len(rows) == 1


def test_load_odds_rejects_post_kickoff_row(tmp_path):
    path = tmp_path / "odds.csv"
    _write(path, "2026-01-01T20:00:00Z")

    with pytest.raises(ValueError, match="before kickoff"):
        load_odds_csv(path, "closing")


def test_load_odds_keeps_horizons_separate(tmp_path):
    path = tmp_path / "odds.csv"
    _write(path, "2026-01-01T10:00:00Z", horizon="opening")

    assert load_odds_csv(path, "closing") == {}
