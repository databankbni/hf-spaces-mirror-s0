from __future__ import annotations

import pytest

from underdog_lab.scenarios.adjustments import RULES, apply_extraction, ruleset_metadata
from underdog_lab.scenarios.schemas import ExtractedFactor, ScenarioExtraction
from underdog_lab.scenarios.taxonomy import FactorType


def extraction(
    factor_type: FactorType,
    team: str = "home",
    severity: float = 1.0,
) -> ScenarioExtraction:
    return ScenarioExtraction(
        factors=[
            ExtractedFactor(
                factor_type=factor_type,
                team=team,
                severity=severity,
                certainty=1.0,
                evidence="test",
            )
        ]
    )


def test_attacker_absence_never_improves_attack(neutral_match):
    result = apply_extraction(
        neutral_match,
        extraction(FactorType.KEY_ATTACKER_UNAVAILABLE),
    )
    assert result.lambda_home < neutral_match.lambda_home
    assert result.lambda_away == neutral_match.lambda_away


def test_severity_is_monotonic(neutral_match):
    low = apply_extraction(
        neutral_match,
        extraction(FactorType.KEY_ATTACKER_UNAVAILABLE, severity=0.25),
    )
    high = apply_extraction(
        neutral_match,
        extraction(FactorType.KEY_ATTACKER_UNAVAILABLE, severity=1.0),
    )
    assert high.lambda_home < low.lambda_home < neutral_match.lambda_home


def test_neutral_venue_restatement_is_dropped(neutral_match):
    result = apply_extraction(
        neutral_match,
        extraction(FactorType.NEUTRAL_VENUE, team="both"),
    )
    assert result.lambda_home == neutral_match.lambda_home
    assert result.lambda_away == neutral_match.lambda_away
    assert result.adjustments[0].applied is False


def test_home_advantage_restatement_is_dropped(home_match):
    result = apply_extraction(
        home_match,
        extraction(FactorType.HOME_ADVANTAGE),
    )
    assert result.lambda_home == home_match.lambda_home
    assert result.adjustments[0].applied is False


def test_counterfactual_neutral_venue_removes_home_advantage(home_match):
    result = apply_extraction(
        home_match,
        extraction(FactorType.NEUTRAL_VENUE, team="both"),
    )
    assert result.lambda_home < home_match.lambda_home
    assert result.adjustments[0].applied is True


def test_unknown_team_is_not_applied(neutral_match):
    result = apply_extraction(
        neutral_match,
        extraction(FactorType.KEY_ATTACKER_UNAVAILABLE, team="unknown"),
    )
    assert result.lambda_home == neutral_match.lambda_home
    assert result.lambda_away == neutral_match.lambda_away


def test_zero_weight_factor_is_not_applied(neutral_match):
    result = apply_extraction(
        neutral_match,
        ScenarioExtraction(
            factors=[
                ExtractedFactor(
                    factor_type=FactorType.HOME_ADVANTAGE,
                    team="home",
                    severity=0.0,
                    certainty=0.0,
                    evidence="uncertain claim",
                )
            ]
        ),
    )

    assert result.lambda_home == neutral_match.lambda_home
    assert result.lambda_away == neutral_match.lambda_away
    assert result.adjustments[0].applied is False
    assert "below the minimum" in result.adjustments[0].explanation


def test_duplicate_factor_does_not_stack(neutral_match):
    factor = ExtractedFactor(
        factor_type=FactorType.FATIGUE_DISADVANTAGE,
        team="home",
        severity=1.0,
        certainty=1.0,
        evidence="test",
    )
    result = apply_extraction(
        neutral_match,
        ScenarioExtraction(factors=[factor, factor]),
    )
    assert sum(item.applied for item in result.adjustments) == 1


def test_must_win_opens_space_for_opponent(neutral_match):
    result = apply_extraction(
        neutral_match,
        extraction(FactorType.MUST_WIN_INCENTIVE),
    )
    assert result.lambda_home > neutral_match.lambda_home
    assert result.lambda_away > neutral_match.lambda_away


def test_lambdas_are_clamped(neutral_match):
    factor = ExtractedFactor(
        factor_type=FactorType.REST_ADVANTAGE,
        team="both",
        severity=1.0,
        certainty=1.0,
        evidence="test",
    )
    result = apply_extraction(
        neutral_match,
        ScenarioExtraction(factors=[factor]),
    )
    assert 0.15 <= result.lambda_home <= 4.0
    assert 0.15 <= result.lambda_away <= 4.0


def test_stacked_worst_case_does_not_silently_clamp(neutral_match):
    """The 6 most negative `affected_attack` factors, all on the home team
    at full severity, are the worst-case stack the schema allows
    (``ScenarioExtraction.factors`` has ``max_length=6``). Their combined
    multiplier should land comfortably inside the [0.5, 1.0) range used by
    ``_multipliers`` -- if a realistic worst case ever reaches the 0.5 floor
    or the final [0.15, 4.0] clamp, the RULES magnitudes have become too
    aggressive when stacked and this test should fail.
    """
    factor_types = [
        FactorType.KEY_ATTACKER_UNAVAILABLE,
        FactorType.MULTIPLE_STARTERS_UNAVAILABLE,
        FactorType.SQUAD_ROTATION,
        FactorType.FATIGUE_DISADVANTAGE,
        FactorType.ALTITUDE_DISADVANTAGE,
        FactorType.TRAVEL_DISADVANTAGE,
    ]
    factors = [
        ExtractedFactor(
            factor_type=factor_type,
            team="home",
            severity=1.0,
            certainty=1.0,
            evidence="test",
        )
        for factor_type in factor_types
    ]
    result = apply_extraction(
        neutral_match,
        ScenarioExtraction(factors=factors),
    )

    assert sum(item.applied for item in result.adjustments) == len(factor_types)

    # Each factor's per-step home multiplier (applied multiplicatively, in
    # order) stays well clear of the 0.5 floor in `_multipliers`.
    per_step_multipliers = [
        1.0 + RULES[factor_type].affected_attack for factor_type in factor_types
    ]
    assert all(0.5 < multiplier < 1.0 for multiplier in per_step_multipliers)

    expected_lambda_home = neutral_match.lambda_home
    for multiplier in per_step_multipliers:
        expected_lambda_home *= multiplier
    assert result.lambda_home == pytest.approx(expected_lambda_home)
    assert 0.15 < result.lambda_home < 4.0


def test_ruleset_metadata_elo_equivalents_below_home_advantage():
    import math

    from underdog_lab.world_cup.forecasting import MODEL

    metadata = ruleset_metadata()
    assert metadata["elo_equivalent_note"]

    for factor_metadata in metadata["elo_equivalents"].values():
        for points in factor_metadata.values():
            assert math.isfinite(points)
            assert abs(points) < MODEL.home_advantage_elo
