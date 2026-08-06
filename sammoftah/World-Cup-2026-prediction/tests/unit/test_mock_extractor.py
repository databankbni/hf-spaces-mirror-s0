from underdog_lab.scenarios.mock_extractor import MockScenarioExtractor
from underdog_lab.scenarios.taxonomy import FactorType


def test_extracts_team_and_attacker(neutral_match):
    result = MockScenarioExtractor().extract(
        f"{neutral_match.away_team}'s striker is confirmed out.",
        neutral_match,
    )
    assert result.factors[0].factor_type == FactorType.KEY_ATTACKER_UNAVAILABLE
    assert result.factors[0].team == "away"


def test_irrelevant_text_is_unsupported(neutral_match):
    result = MockScenarioExtractor().extract(
        "The supporters have excellent songs.",
        neutral_match,
    )
    assert result.factors == []
    assert result.unsupported_claims


def test_paraphrases_map_to_same_factor(neutral_match):
    extractor = MockScenarioExtractor()
    first = extractor.extract("The home striker is out.", neutral_match)
    second = extractor.extract("The hosts' top scorer is unavailable.", neutral_match)
    assert first.factors[0].factor_type == second.factors[0].factor_type
