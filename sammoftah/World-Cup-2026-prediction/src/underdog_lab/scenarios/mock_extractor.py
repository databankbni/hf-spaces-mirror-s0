from __future__ import annotations

import re

from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.schemas import ExtractedFactor, ScenarioExtraction
from underdog_lab.scenarios.taxonomy import FactorType


class MockScenarioExtractor:
    """Deterministic keyword extractor used for tests and offline fallback."""

    name = "deterministic fallback"

    def extract(self, text: str, match: MatchRecord) -> ScenarioExtraction:
        normalized = text.strip().lower()
        if not normalized:
            return ScenarioExtraction()

        team = self._infer_team(normalized, match)
        certainty = 1.0 if any(
            word in normalized for word in ("confirmed", "definitely", "will")
        ) else 0.8
        severity = self._infer_severity(normalized)
        factors: list[ExtractedFactor] = []

        patterns: list[tuple[FactorType, tuple[str, ...]]] = [
            (
                FactorType.KEY_ATTACKER_UNAVAILABLE,
                ("striker", "forward", "attacker", "top scorer"),
            ),
            (
                FactorType.KEY_DEFENDER_UNAVAILABLE,
                ("defender", "centre back", "center back", "fullback"),
            ),
            (
                FactorType.GOALKEEPER_UNAVAILABLE,
                ("goalkeeper", "keeper"),
            ),
            (
                FactorType.MULTIPLE_STARTERS_UNAVAILABLE,
                ("multiple starters", "several starters", "five starters"),
            ),
            (FactorType.SQUAD_ROTATION, ("rotate", "rotation", "second team")),
            (FactorType.FATIGUE_DISADVANTAGE, ("fatigue", "tired", "exhausted")),
            (FactorType.REST_ADVANTAGE, ("well rested", "extra rest", "more rest")),
            (FactorType.TRAVEL_DISADVANTAGE, ("long travel", "jet lag", "travel")),
            (FactorType.ALTITUDE_DISADVANTAGE, ("altitude", "high elevation")),
            (FactorType.HEAT_DISADVANTAGE, ("heat", "hot weather", "humidity")),
            (FactorType.NEUTRAL_VENUE, ("neutral ground", "neutral venue")),
            (FactorType.HOME_ADVANTAGE, ("at home", "home crowd", "home ground")),
            (
                FactorType.DEFENSIVE_GAME_STATE,
                ("only need a draw", "play for a draw", "defensive setup"),
            ),
            (FactorType.MUST_WIN_INCENTIVE, ("must win", "need to win")),
        ]

        for factor_type, keywords in patterns:
            if any(keyword in normalized for keyword in keywords):
                factors.append(
                    ExtractedFactor(
                        factor_type=factor_type,
                        team=team if factor_type not in {
                            FactorType.NEUTRAL_VENUE,
                            FactorType.DEFENSIVE_GAME_STATE,
                        } else "both",
                        severity=severity,
                        certainty=certainty,
                        evidence=self._evidence(normalized, keywords),
                    )
                )

        unsupported = []
        if not factors:
            unsupported.append(text.strip())
        return ScenarioExtraction(factors=factors[:6], unsupported_claims=unsupported)

    @staticmethod
    def _infer_severity(text: str) -> float:
        if any(word in text for word in ("minor", "slight", "doubt")):
            return 0.35
        if any(word in text for word in ("multiple", "several", "confirmed", "out")):
            return 1.0
        return 0.7

    @staticmethod
    def _infer_team(text: str, match: MatchRecord) -> str:
        home = match.home_team.lower()
        away = match.away_team.lower()
        home_pos = text.find(home)
        away_pos = text.find(away)
        if home_pos >= 0 and away_pos < 0:
            return "home"
        if away_pos >= 0 and home_pos < 0:
            return "away"
        if re.search(r"\b(home team|hosts?|favorite|favourite)\b", text):
            return "home"
        if re.search(r"\b(away team|visitors?|underdog)\b", text):
            return "away"
        return "unknown"

    @staticmethod
    def _evidence(text: str, keywords: tuple[str, ...]) -> str:
        keyword = next(keyword for keyword in keywords if keyword in text)
        return keyword
