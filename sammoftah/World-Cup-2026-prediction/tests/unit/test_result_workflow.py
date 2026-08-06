from pathlib import Path


def test_result_workflow_has_keyless_fallback():
    workflow = Path(".github/workflows/result-check.yml").read_text(
        encoding="utf-8"
    )

    assert "--provider auto" in workflow
    assert "FOOTBALL_DATA_API_KEY is not configured" not in workflow
    assert "provider=" in workflow


def test_result_workflow_does_not_poll_after_tournament_end():
    workflow = Path(".github/workflows/result-check.yml").read_text(
        encoding="utf-8"
    )

    assert "schedule:" not in workflow
    assert "workflow_dispatch:" in workflow


def test_result_workflow_keeps_human_review_gate():
    workflow = Path(".github/workflows/result-check.yml").read_text(
        encoding="utf-8"
    )

    assert "peter-evans/create-pull-request" in workflow
    assert "--allow-corrections" not in workflow
    assert "Refresh knockout bracket" in workflow
    assert "health_check.py --ignore-overdue-results" in workflow


def test_deploy_workflow_fails_when_token_is_missing():
    workflow = Path(".github/workflows/deploy-space.yml").read_text(
        encoding="utf-8"
    )

    assert "Validate deployment configuration" in workflow
    assert 'echo "::error::HF_TOKEN is not configured."' in workflow
    assert "exit 1" in workflow
    assert "if: env.HF_TOKEN != ''" not in workflow
