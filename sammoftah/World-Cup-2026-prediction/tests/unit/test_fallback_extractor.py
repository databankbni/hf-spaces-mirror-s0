from underdog_lab.scenarios.factory import FallbackExtractor
from underdog_lab.scenarios.mock_extractor import MockScenarioExtractor
from underdog_lab.scenarios.schemas import ExtractedFactor, ScenarioExtraction
from underdog_lab.scenarios.taxonomy import FactorType


class BrokenExtractor:
    name = "broken local model"

    def extract(self, text, match):
        raise RuntimeError("model could not load")


def test_fallback_exposes_backend_and_error(neutral_match):
    extractor = FallbackExtractor()
    extractor.primary = BrokenExtractor()
    extractor.fallback = MockScenarioExtractor()

    result = extractor.extract(
        f"{neutral_match.home_team}'s striker is out.",
        neutral_match,
    )

    assert result.factors
    assert extractor.last_backend == "deterministic fallback"
    assert "RuntimeError" in extractor.last_error


class EmptyExtractor:
    name = "empty local model"

    def extract(self, text, match):
        return ScenarioExtraction()


def test_empty_primary_result_uses_honest_semantic_recovery(neutral_match):
    extractor = FallbackExtractor()
    extractor.primary = EmptyExtractor()
    extractor.fallback = MockScenarioExtractor()

    result = extractor.extract(
        f"{neutral_match.home_team}'s striker is confirmed out.",
        neutral_match,
    )

    assert len(result.factors) == 1
    assert extractor.last_backend == "deterministic fallback"
    assert "deterministic recovery" in extractor.last_error


class ZeroWeightExtractor:
    name = "zero-weight local model"

    def extract(self, text, match):
        return ScenarioExtraction(
            factors=[
                ExtractedFactor(
                    factor_type=FactorType.HOME_ADVANTAGE,
                    team="both",
                    severity=0.0,
                    certainty=0.0,
                    evidence="irrelevant",
                )
            ]
        )


def test_zero_weight_hallucination_uses_semantic_recovery(neutral_match):
    extractor = FallbackExtractor()
    extractor.primary = ZeroWeightExtractor()
    extractor.fallback = MockScenarioExtractor()

    result = extractor.extract(
        f"{neutral_match.home_team}'s striker is confirmed out.",
        neutral_match,
    )

    assert result.factors[0].factor_type == FactorType.KEY_ATTACKER_UNAVAILABLE
    assert extractor.last_backend == "deterministic fallback"


class CountingBrokenExtractor:
    name = "broken local model"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, text, match):
        self.calls += 1
        raise RuntimeError("model could not load")

    def warmup(self) -> None:
        raise RuntimeError("model could not load")


def test_primary_failure_is_remembered_and_not_retried(neutral_match):
    extractor = FallbackExtractor()
    broken = CountingBrokenExtractor()
    extractor.primary = broken
    extractor.fallback = MockScenarioExtractor()

    text = f"{neutral_match.home_team}'s striker is out."

    first = extractor.extract(text, neutral_match)
    assert extractor.primary_unavailable is True
    assert extractor.last_backend == "deterministic fallback"
    assert "RuntimeError" in extractor.last_error
    assert broken.calls == 1

    second = extractor.extract(text, neutral_match)
    assert broken.calls == 1
    assert extractor.last_backend == "deterministic fallback"
    assert second.factors == first.factors


def test_warmup_failure_is_remembered_and_skips_primary(neutral_match):
    extractor = FallbackExtractor()
    broken = CountingBrokenExtractor()
    extractor.primary = broken
    extractor.fallback = MockScenarioExtractor()

    extractor.warmup()
    assert extractor.primary_unavailable is True
    assert extractor.last_backend == "deterministic fallback"
    assert "RuntimeError" in extractor.last_error

    extractor.extract(f"{neutral_match.home_team}'s striker is out.", neutral_match)
    assert broken.calls == 0
