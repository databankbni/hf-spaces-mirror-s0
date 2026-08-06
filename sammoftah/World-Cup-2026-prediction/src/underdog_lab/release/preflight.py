from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "underdog-lab-release-preflight",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _url_reachable(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "underdog-lab-release-preflight"})
    try:
        with urlopen(request, timeout=15) as response:
            return 200 <= response.status < 400
    except (HTTPError, URLError, TimeoutError):
        return False


def online_release_checks(config: dict[str, Any]) -> dict[str, bool]:
    github = _fetch_json(
        "https://api.github.com/repos/OsamaMoftah/World-Cup-2026-predicition"
    )
    space = _fetch_json(
        "https://huggingface.co/api/spaces/sammoftah/World-Cup-2026-prediction"
    )
    runtime = space.get("runtime") or {}
    return {
        "github_public": github.get("private") is False,
        "github_url_reachable": _url_reachable(config["github_url"]),
        "space_url_reachable": _url_reachable(config["space_url"]),
        "base_model_url_reachable": _url_reachable(config["base_model_url"]),
        "adapter_url_reachable": _url_reachable(config["adapter_url"]),
        "dataset_url_reachable": _url_reachable(config["dataset_url"]),
        "space_running": runtime.get("stage") == "RUNNING",
        "space_revision_present": bool(space.get("sha")),
    }


def _live_forecast_verified(root: Path, config: dict[str, Any]) -> bool:
    proof_dir = root / config.get("live_forecast_path", "")
    forecast_path = proof_dir / "forecast.json"
    manifest_path = proof_dir / "manifest.json"
    if not forecast_path.exists() or not manifest_path.exists():
        return False
    forecast = _load(forecast_path)
    manifest = _load(manifest_path)
    digest = hashlib.sha256(forecast_path.read_bytes()).hexdigest()
    generated = datetime.fromisoformat(forecast["generated_at"])
    cutoff = datetime.fromisoformat(
        forecast["information_cutoff"].replace("Z", "+00:00")
    )
    fixtures = forecast.get("fixtures", [])
    if len(fixtures) != 1 or not fixtures[0].get("kickoff_utc"):
        return False
    kickoff = datetime.fromisoformat(fixtures[0]["kickoff_utc"])
    return (
        manifest.get("immutable") is True
        and manifest.get("sha256") == digest
        and cutoff <= generated < kickoff
    )


def evaluate_preflight(
    root: Path,
    config: dict[str, Any],
    online_checks: dict[str, bool] | None = None,
) -> dict[str, Any]:
    teams = _load(root / "data/world_cup_2026/teams.json")
    group_sizes = Counter(team["group"] for team in teams)
    fixture_count = sum(size * (size - 1) // 2 for size in group_sizes.values())
    qlora = _load(root / "results/qlora_gate_report.json")
    bracket = _load(root / "results/bracket_verification.json")
    backtest = _load(root / "models/backtest_report.json")
    required_docs = (
        "README.md",
        "LICENSE",
        "data/scenarios/README.md",
    )
    checks = {
        "space_url_declared": bool(config.get("space_url")),
        "github_url_declared": bool(config.get("github_url")),
        "world_cup_teams_48": len(teams) == 48,
        "world_cup_group_fixtures_72": (
            len(group_sizes) == 12
            and set(group_sizes.values()) == {4}
            and fixture_count == 72
        ),
        "qlora_gate_closed": (
            qlora.get("status") == "closed"
            and qlora.get("release_blocking") is False
        ),
        "official_bracket_verified": (
            bracket.get("status") == "verified"
            and bracket.get("annex_c_combinations") == 495
            and bracket.get("release_blocking") is False
        ),
        "forecast_backtest_ship_gate": backtest["ship_gate"]["ship"] is True,
        "parameter_limit": (
            config["base_model_parameters"] <= config["parameter_limit"]
        ),
        "code_license_documented": (
            config["licenses"].get("code") == "MIT"
            and (root / "LICENSE").exists()
        ),
        "base_model_license_documented": (
            config["licenses"].get("base_model") == "Apache-2.0"
        ),
        "adapter_url_declared": bool(config.get("adapter_url")),
        "dataset_url_declared": bool(config.get("dataset_url")),
        "release_docs_present": all(
            (root / path).exists() and (root / path).stat().st_size > 0
            for path in required_docs
        ),
        "live_forecast_proof_verified": _live_forecast_verified(root, config),
    }
    if online_checks is not None:
        checks.update(online_checks)
    human_actions = config.get("human_actions", {})
    pending_human_actions = [
        key for key, value in human_actions.items() if not str(value).strip()
    ]
    failed_checks = [key for key, passed in checks.items() if not passed]
    if failed_checks:
        status = "BLOCKED"
    elif pending_human_actions:
        status = "READY_FOR_HUMAN_SUBMISSION"
    else:
        status = "READY_TO_SUBMIT"
    return {
        "status": status,
        "machine_checks": checks,
        "failed_machine_checks": failed_checks,
        "pending_human_actions": pending_human_actions,
        "urls": {
            key: value
            for key, value in config.items()
            if key.endswith("_url")
        },
        "claim_boundaries": [
            "QLoRA adapter evaluated NO-SHIP; no Well-Tuned performance claim.",
            "Scenario labels remain synthetic and review-pending; extraction metrics are pipeline diagnostics.",
            "Forecast accuracy evidence is the walk-forward Dixon-Coles backtest, not isolated match outcomes.",
        ],
    }


def run_preflight(
    root: Path,
    output_path: Path,
    *,
    online: bool = False,
) -> dict[str, Any]:
    config = _load(root / "release/submission.json")
    checks = online_release_checks(config) if online else None
    report = evaluate_preflight(root, config, online_checks=checks)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
