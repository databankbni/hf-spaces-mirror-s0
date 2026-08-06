from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "data").exists():
            return candidate
    raise FileNotFoundError("Cannot locate project root containing pyproject.toml and data/")


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    config: dict[str, Any]

    @classmethod
    def load(cls, config_path: str | Path = "config/v192.json", root: Path | None = None) -> "ProjectPaths":
        project_root = (root or find_project_root()).resolve()
        path = Path(config_path)
        if not path.is_absolute():
            path = project_root / path
        return cls(project_root, json.loads(path.read_text(encoding="utf-8")))

    def resolve(self, key: str) -> Path:
        value = Path(self.config[key])
        return value if value.is_absolute() else self.root / value

