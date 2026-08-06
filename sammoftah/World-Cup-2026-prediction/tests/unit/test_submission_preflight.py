import json
import hashlib

from underdog_lab.release.preflight import evaluate_preflight


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _root(tmp_path):
    _write_json(
        tmp_path / "data/world_cup_2026/teams.json",
        [{"group": group} for group in "ABCDEFGHIJKL" for _ in range(4)],
    )
    _write_json(
        tmp_path / "results/qlora_gate_report.json",
        {"status": "closed", "release_blocking": False},
    )
    _write_json(
        tmp_path / "results/bracket_verification.json",
        {
            "status": "verified",
            "annex_c_combinations": 495,
            "release_blocking": False,
        },
    )
    _write_json(
        tmp_path / "models/backtest_report.json",
        {"ship_gate": {"ship": True}},
    )
    proof = tmp_path / "predictions/live/proof"
    _write_json(
        proof / "forecast.json",
        {
            "generated_at": "2026-06-13T16:00:00+00:00",
            "information_cutoff": "2026-06-13T04:30:00Z",
            "fixtures": [{"kickoff_utc": "2026-06-13T19:00:00+00:00"}],
        },
    )
    _write_json(
        proof / "manifest.json",
        {
            "immutable": True,
            "sha256": hashlib.sha256(
                (proof / "forecast.json").read_bytes()
            ).hexdigest(),
        },
    )
    for path in (
        "README.md",
        "LICENSE",
        "data/scenarios/README.md",
    ):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("present", encoding="utf-8")
    return tmp_path


def _config(human_value=""):
    return {
        "space_url": "https://example.com/space",
        "github_url": "https://example.com/code",
        "adapter_url": "https://example.com/adapter",
        "dataset_url": "https://example.com/data",
        "base_model_parameters": 360_000_000,
        "parameter_limit": 32_000_000_000,
        "licenses": {"code": "MIT", "base_model": "Apache-2.0"},
        "live_forecast_path": "predictions/live/proof",
        "human_actions": {"demo_video_url": human_value},
    }


def test_preflight_separates_human_actions_from_machine_blockers(tmp_path):
    report = evaluate_preflight(_root(tmp_path), _config())

    assert report["status"] == "READY_FOR_HUMAN_SUBMISSION"
    assert report["failed_machine_checks"] == []
    assert report["pending_human_actions"] == ["demo_video_url"]


def test_preflight_is_ready_when_human_actions_are_recorded(tmp_path):
    report = evaluate_preflight(
        _root(tmp_path),
        _config("https://example.com/demo"),
    )

    assert report["status"] == "READY_TO_SUBMIT"


def test_online_failures_become_machine_blockers(tmp_path):
    report = evaluate_preflight(
        _root(tmp_path),
        _config("https://example.com/demo"),
        online_checks={
            "github_public": False,
            "space_running": True,
        },
    )

    assert report["status"] == "BLOCKED"
    assert report["failed_machine_checks"] == ["github_public"]
