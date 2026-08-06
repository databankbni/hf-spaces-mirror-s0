from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# The guard scripts import underdog_lab; run them with src/ on PYTHONPATH so
# a missing editable install fails the guard assertion, not the import.
_SCRIPT_ENV = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join(
        filter(
            None,
            [
                str(Path(__file__).resolve().parents[2] / "src"),
                os.environ.get("PYTHONPATH"),
            ],
        )
    ),
}


def test_generate_synthetic_data_rejects_frozen_test_without_flag():
    """The frozen test split cannot be regenerated without --allow-overwrite-test."""
    script = Path("scripts/generate_synthetic_data.py")
    result = subprocess.run(
        [sys.executable, str(script), "--split", "test", "--count", "1", "--seed", "9999"],
        capture_output=True,
        text=True,
        env=_SCRIPT_ENV,
    )
    assert result.returncode != 0, (
        "generate_synthetic_data.py must reject --split test without "
        "--allow-overwrite-test"
    )
    assert "allow-overwrite-test" in result.stderr, (
        f"expected the frozen-test-split guard, got: {result.stderr}"
    )


def test_generate_synthetic_data_allows_test_with_flag():
    """The --allow-overwrite-test flag permits intentional test regeneration."""
    import tempfile

    script = Path("scripts/generate_synthetic_data.py")
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--split", "test",
                "--count", "1",
                "--seed", "9999",
                "--allow-overwrite-test",
                "--output", str(tmp_path),
            ],
            capture_output=True,
            text=True,
            env=_SCRIPT_ENV,
        )
        assert result.returncode == 0, (
            f"--allow-overwrite-test must permit test generation: {result.stderr}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_modal_train_guard_rejects_test_dataset_name():
    """modal_train.py rejects dataset repos that contain 'test'."""
    train_module_path = Path("training/modal_train.py")
    source = train_module_path.read_text()

    import re
    assert re.search(
        r'Refusing to train on a dataset that appears to be a test split',
        source,
    ), "modal_train.py must contain the test-dataset guard"
