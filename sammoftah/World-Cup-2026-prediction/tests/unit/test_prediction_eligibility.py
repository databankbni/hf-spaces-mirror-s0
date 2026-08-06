import json
import hashlib

from underdog_lab.world_cup.data import TournamentRepository
from underdog_lab.world_cup.predictions import audit_forecasts, eligible_forecasts


def _write_forecast(path, *, generated_at, cutoff, fixture_id):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "live-forecast-v2",
                "forecast_date": path.parent.name,
                "generated_at": generated_at,
                "information_cutoff": cutoff,
                "model": "test",
                "provenance": {
                    "model_version": "test-v1",
                    "calibration_temperature": 1.0,
                    "team_ratings_sha256": "a" * 64,
                    "snapshot_sha256": "b" * 64,
                },
                "fixtures": [
                    {
                        "fixture_id": fixture_id,
                        "p_home": 0.5,
                        "p_draw": 0.3,
                        "p_away": 0.2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (path.parent / "manifest.json").write_text(
        json.dumps(
            {
                "immutable": True,
                "file": "forecast.json",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def test_future_cutoff_and_post_kickoff_forecasts_are_excluded(tmp_path):
    repository = TournamentRepository()
    fixture = next(f for f in repository.fixtures if f.fixture_id == "WC26-007")
    _write_forecast(
        tmp_path / "future-cutoff" / "forecast.json",
        generated_at="2026-06-11T10:00:00+00:00",
        cutoff="2026-06-12T10:00:00Z",
        fixture_id=fixture.fixture_id,
    )
    _write_forecast(
        tmp_path / "same-day" / "forecast.json",
        generated_at="2026-06-12T19:00:01+00:00",
        cutoff="2026-06-11T23:00:00Z",
        fixture_id=fixture.fixture_id,
    )

    assert eligible_forecasts([fixture], tmp_path) == {}


def test_latest_valid_pre_match_forecast_is_selected(tmp_path):
    repository = TournamentRepository()
    fixture = next(f for f in repository.fixtures if f.fixture_id == "WC26-003")
    _write_forecast(
        tmp_path / "older" / "forecast.json",
        generated_at="2026-06-12T10:00:00+00:00",
        cutoff="2026-06-12T09:00:00Z",
        fixture_id=fixture.fixture_id,
    )
    _write_forecast(
        tmp_path / "newer" / "forecast.json",
        generated_at="2026-06-13T10:00:00+00:00",
        cutoff="2026-06-13T09:00:00Z",
        fixture_id=fixture.fixture_id,
    )

    selected = eligible_forecasts([fixture], tmp_path)
    assert selected[fixture.fixture_id]["forecast_date"] == "newer"


def test_exact_kickoff_allows_valid_same_day_forecast(tmp_path):
    repository = TournamentRepository()
    fixture = next(f for f in repository.fixtures if f.fixture_id == "WC26-008")
    _write_forecast(
        tmp_path / "live" / "proof" / "forecast.json",
        generated_at="2026-06-13T16:00:00+00:00",
        cutoff="2026-06-13T04:30:00Z",
        fixture_id=fixture.fixture_id,
    )

    selected = eligible_forecasts([fixture], tmp_path)

    assert selected[fixture.fixture_id]["generated_at"] == (
        "2026-06-13T16:00:00+00:00"
    )


def test_exact_kickoff_rejects_post_kickoff_forecast(tmp_path):
    repository = TournamentRepository()
    fixture = next(f for f in repository.fixtures if f.fixture_id == "WC26-008")
    _write_forecast(
        tmp_path / "live" / "late" / "forecast.json",
        generated_at="2026-06-13T19:00:01+00:00",
        cutoff="2026-06-13T18:00:00Z",
        fixture_id=fixture.fixture_id,
    )

    assert eligible_forecasts([fixture], tmp_path) == {}


def test_invalid_manifest_is_reported_not_scored(tmp_path):
    repository = TournamentRepository()
    fixture = next(f for f in repository.fixtures if f.fixture_id == "WC26-003")
    path = tmp_path / "proof" / "forecast.json"
    _write_forecast(
        path,
        generated_at="2026-06-17T10:00:00+00:00",
        cutoff="2026-06-17T09:00:00Z",
        fixture_id=fixture.fixture_id,
    )
    manifest = json.loads((path.parent / "manifest.json").read_text())
    manifest["sha256"] = "0" * 64
    (path.parent / "manifest.json").write_text(json.dumps(manifest))

    audit = audit_forecasts([fixture], tmp_path)

    assert audit["counts"]["invalid_manifest"] == 1
