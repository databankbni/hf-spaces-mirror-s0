from __future__ import annotations

import json
from pathlib import Path

from underdog_lab.config import DATA_DIR
from underdog_lab.domain import MatchRecord


class MatchRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "processed" / "matches.json"
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        self._matches = [MatchRecord.model_validate(row) for row in rows]
        self._by_id = {match.match_id: match for match in self._matches}

    def list(self) -> list[MatchRecord]:
        return list(self._matches)

    def labels(self) -> list[str]:
        return [match.label for match in self._matches]

    def by_label(self, label: str) -> MatchRecord:
        for match in self._matches:
            if match.label == label:
                return match
        raise KeyError(f"Unknown match label: {label}")

    def get(self, match_id: str) -> MatchRecord:
        return self._by_id[match_id]
