from __future__ import annotations

from typing import Protocol

from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.schemas import ScenarioExtraction


class ScenarioExtractor(Protocol):
    name: str

    def extract(self, text: str, match: MatchRecord) -> ScenarioExtraction:
        ...
