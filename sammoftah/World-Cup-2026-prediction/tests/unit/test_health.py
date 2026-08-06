from datetime import datetime, timezone

from underdog_lab.release.health import application_health


def test_health_check_verifies_schedule_and_snapshot():
    report = application_health(
        now=datetime(2026, 6, 14, 0, 0, tzinfo=timezone.utc)
    )

    assert report["checks"]["teams_48"] is True
    assert report["checks"]["fixtures_72"] is True
    assert report["checks"]["all_kickoffs_present"] is True
    assert report["checks"]["forecast_manifests_valid"] is True
    assert report["checks"]["results_current"] is True
    assert report["forecast_artifact_audit"]["eligible"] >= 1
