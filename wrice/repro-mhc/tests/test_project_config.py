import subprocess
from pathlib import Path


def test_validation_uses_non_package_project_with_versioned_lock() -> None:
    project = Path(__file__).resolve().parents[1]
    config = (project / "pyproject.toml").read_text()
    assert "[tool.uv]\npackage = false" in config

    repository = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    subprocess.run(
        [
            "git",
            "ls-files",
            "--error-unmatch",
            str((project / "uv.lock").relative_to(repository)),
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
