import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from underdog_lab.release.live_forecast import generate_live_forecast


FIXTURES = Path(__file__).parents[1] / "fixtures" / "world_cup"


def test_live_forecast_writes_a_verifiable_manifest(tmp_path):
    forecast_path, manifest_path = generate_live_forecast(
        "WC26-008",
        tmp_path / "proof",
        now=datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc),
        snapshot_path=FIXTURES / "pre_wc26_008.json",
    )

    payload = json.loads(forecast_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["fixtures"][0]["kickoff_utc"] == (
        "2026-06-13T19:00:00+00:00"
    )
    assert manifest["sha256"] == hashlib.sha256(
        forecast_path.read_bytes()
    ).hexdigest()
    assert payload["provenance"]["calibration_temperature"] > 0
    assert len(payload["provenance"]["team_ratings_sha256"]) == 64


def test_live_forecast_refuses_post_kickoff_generation(tmp_path):
    with pytest.raises(ValueError, match="before kickoff"):
        generate_live_forecast(
            "WC26-008",
            tmp_path / "late",
            now=datetime(2026, 6, 13, 19, 1, tzinfo=timezone.utc),
            snapshot_path=FIXTURES / "pre_wc26_008.json",
        )


def test_live_forecast_can_reproduce_second_frozen_fixture(tmp_path):
    forecast_path, _ = generate_live_forecast(
        "WC26-013",
        tmp_path / "proof",
        now=datetime(2026, 6, 13, 20, 0, tzinfo=timezone.utc),
        snapshot_path=FIXTURES / "pre_wc26_013.json",
    )

    payload = json.loads(forecast_path.read_text(encoding="utf-8"))
    assert payload["fixtures"][0]["fixture_id"] == "WC26-013"
    assert payload["information_cutoff"] == "2026-06-13T19:30:00Z"


def test_live_forecast_supports_resolved_knockout_fixture(tmp_path):
    from underdog_lab.world_cup.data import TournamentRepository

    repository = TournamentRepository()
    final = next(
        fixture
        for fixture in repository.knockout_fixtures
        if fixture.stage == "final"
    )
    if final.played:
        pytest.skip("final already has a recorded result in the snapshot")

    forecast_path, manifest_path = generate_live_forecast(
        final.fixture_id,
        tmp_path / "proof",
        now=final.kickoff_utc.replace(hour=0, minute=0),
    )

    payload = json.loads(forecast_path.read_text(encoding="utf-8"))
    prediction = payload["fixtures"][0]
    assert prediction["stage"] == "final"
    assert prediction["match_number"] == 104
    assert abs(
        prediction["p_home"] + prediction["p_draw"] + prediction["p_away"] - 1.0
    ) < 1e-6
    assert abs(
        prediction["p_home_advance"] + prediction["p_away_advance"] - 1.0
    ) < 1e-6
    assert "regulation-90-minute" in prediction["probability_note"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["sha256"] == hashlib.sha256(
        forecast_path.read_bytes()
    ).hexdigest()
