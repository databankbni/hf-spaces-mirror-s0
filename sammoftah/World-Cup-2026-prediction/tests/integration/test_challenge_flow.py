from underdog_lab.domain import Forecast
from underdog_lab.scenarios.mock_extractor import MockScenarioExtractor
from underdog_lab.service import analyze_scenario, baseline_forecast


def test_complete_challenge_flow(neutral_match):
    baseline = baseline_forecast(neutral_match)
    extraction, result, adjusted = analyze_scenario(
        neutral_match,
        f"{neutral_match.home_team}'s striker is confirmed out.",
        MockScenarioExtractor(),
    )
    assert extraction.factors
    assert result.adjustments[0].applied
    assert isinstance(adjusted, Forecast)
    assert adjusted.p_home < baseline.p_home


def test_repository_has_twenty_matches(repository):
    assert len(repository.list()) >= 20
