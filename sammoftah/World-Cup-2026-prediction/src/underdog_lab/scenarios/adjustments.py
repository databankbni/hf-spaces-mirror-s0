from __future__ import annotations

import math
from dataclasses import dataclass

from underdog_lab.config import RULESET_VERSION
from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.schemas import (
    AdjustmentResult,
    AppliedAdjustment,
    ExtractedFactor,
    ScenarioExtraction,
)
from underdog_lab.scenarios.taxonomy import FactorType
from underdog_lab.world_cup.forecasting import MODEL


@dataclass(frozen=True)
class Rule:
    affected_attack: float = 0.0
    opponent_attack: float = 0.0
    both_attacks: float = 0.0
    rationale: str = ""


RULES: dict[FactorType, Rule] = {
    FactorType.KEY_ATTACKER_UNAVAILABLE: Rule(
        affected_attack=-0.12, rationale="A key attacker is unavailable."
    ),
    FactorType.KEY_DEFENDER_UNAVAILABLE: Rule(
        opponent_attack=0.08, rationale="The opponent faces a weakened defence."
    ),
    FactorType.GOALKEEPER_UNAVAILABLE: Rule(
        opponent_attack=0.10, rationale="The opponent faces a reserve goalkeeper."
    ),
    FactorType.MULTIPLE_STARTERS_UNAVAILABLE: Rule(
        affected_attack=-0.08,
        opponent_attack=0.06,
        rationale="Several absences weaken both phases.",
    ),
    FactorType.SQUAD_ROTATION: Rule(
        affected_attack=-0.06,
        opponent_attack=0.04,
        rationale="Rotation lowers continuity and expected quality.",
    ),
    FactorType.FATIGUE_DISADVANTAGE: Rule(
        affected_attack=-0.05,
        opponent_attack=0.03,
        rationale="Fatigue reduces attacking output and defensive resistance.",
    ),
    FactorType.REST_ADVANTAGE: Rule(
        affected_attack=0.04,
        opponent_attack=-0.02,
        rationale="Additional rest benefits both phases.",
    ),
    FactorType.TRAVEL_DISADVANTAGE: Rule(
        affected_attack=-0.04, rationale="Difficult travel suppresses attacking output."
    ),
    FactorType.ALTITUDE_DISADVANTAGE: Rule(
        affected_attack=-0.05,
        opponent_attack=0.03,
        rationale="Altitude can reduce intensity for an unacclimatized team.",
    ),
    FactorType.HEAT_DISADVANTAGE: Rule(
        affected_attack=-0.03, rationale="Heat can reduce attacking intensity."
    ),
    FactorType.HOME_ADVANTAGE: Rule(
        affected_attack=0.06, rationale="Counterfactual home support increases attack."
    ),
    FactorType.NEUTRAL_VENUE: Rule(
        affected_attack=-0.06, rationale="A neutral venue removes home advantage."
    ),
    FactorType.DEFENSIVE_GAME_STATE: Rule(
        both_attacks=-0.06, rationale="A draw-oriented setup lowers match tempo."
    ),
    FactorType.MUST_WIN_INCENTIVE: Rule(
        affected_attack=0.05,
        opponent_attack=0.02,
        rationale=(
            "A must-win team attacks more, while the opponent also benefits from "
            "the space created."
        ),
    ),
}


def apply_extraction(
    match: MatchRecord,
    extraction: ScenarioExtraction,
) -> AdjustmentResult:
    home = match.lambda_home
    away = match.lambda_away
    adjustments: list[AppliedAdjustment] = []
    seen: set[tuple[FactorType, str]] = set()

    for factor in extraction.factors:
        key = (factor.factor_type, factor.team)
        if key in seen:
            adjustments.append(
                AppliedAdjustment(
                    factor=factor,
                    applied=False,
                    explanation="Duplicate factor ignored.",
                )
            )
            continue
        seen.add(key)

        venue_guard = _venue_guard(match, factor)
        if venue_guard is not None:
            adjustments.append(
                AppliedAdjustment(
                    factor=factor,
                    applied=False,
                    explanation=venue_guard,
                )
            )
            continue

        if factor.team == "unknown":
            adjustments.append(
                AppliedAdjustment(
                    factor=factor,
                    applied=False,
                    explanation="Team reference could not be resolved.",
                )
            )
            continue

        rule = RULES[factor.factor_type]
        weight = factor.severity * factor.certainty
        if weight < 0.05:
            adjustments.append(
                AppliedAdjustment(
                    factor=factor,
                    applied=False,
                    explanation=(
                        "Severity × certainty is below the minimum "
                        "0.05 confidence weight."
                    ),
                )
            )
            continue
        home_multiplier, away_multiplier = _multipliers(factor, rule, weight)
        home *= home_multiplier
        away *= away_multiplier
        adjustments.append(
            AppliedAdjustment(
                factor=factor,
                applied=True,
                explanation=f"{rule.rationale} Applied with {weight:.0%} weight.",
                home_multiplier=home_multiplier,
                away_multiplier=away_multiplier,
            )
        )

    return AdjustmentResult(
        lambda_home=_clamp(home),
        lambda_away=_clamp(away),
        adjustments=adjustments,
    )


def _venue_guard(match: MatchRecord, factor: ExtractedFactor) -> str | None:
    if factor.factor_type == FactorType.NEUTRAL_VENUE and match.neutral_venue:
        return "Dropped: the baseline already records a neutral venue."
    if factor.factor_type == FactorType.HOME_ADVANTAGE and not match.neutral_venue:
        return "Dropped: the baseline already includes home advantage."
    return None


def _multipliers(
    factor: ExtractedFactor,
    rule: Rule,
    weight: float,
) -> tuple[float, float]:
    home = 1.0 + rule.both_attacks * weight
    away = 1.0 + rule.both_attacks * weight

    if factor.team in {"home", "both"}:
        home += rule.affected_attack * weight
        away += rule.opponent_attack * weight
    if factor.team in {"away", "both"}:
        away += rule.affected_attack * weight
        home += rule.opponent_attack * weight
    return max(0.5, home), max(0.5, away)


def _clamp(value: float) -> float:
    return min(4.0, max(0.15, value))


def elo_equivalent_points(multiplier_delta: float) -> float:
    """Convert a RULES multiplier delta (e.g. -0.12) to an Elo-point shift.

    ``MODEL.elo_scale`` is the fitted log-rate change per Elo point
    (``models/elo_fit_report.json``), so a multiplicative change of
    ``1 + multiplier_delta`` to a team's expected goals corresponds to a
    shift of ``log(1 + multiplier_delta) / elo_scale`` Elo-equivalent
    points in that team's effective rating. This grounds each hand-set
    adjustment against the model's own fitted scale rather than leaving it
    as an unanchored percentage.
    """
    return math.log(1.0 + multiplier_delta) / MODEL.elo_scale


def ruleset_metadata() -> dict[str, object]:
    elo_equivalents = {
        factor.value: {
            "affected_attack_elo": elo_equivalent_points(rule.affected_attack),
            "opponent_attack_elo": elo_equivalent_points(rule.opponent_attack),
            "both_attacks_elo": elo_equivalent_points(rule.both_attacks),
        }
        for factor, rule in RULES.items()
    }
    return {
        "version": RULESET_VERSION,
        "limitation": (
            "These are transparent product assumptions, not learned causal effects."
        ),
        "elo_equivalents": elo_equivalents,
        "elo_equivalent_note": (
            "Each magnitude above is converted to Elo-equivalent points "
            "using the fitted MODEL.elo_scale (models/elo_fit_report.json). "
            "Every rule's magnitude is smaller than the model's own fitted "
            "home_advantage_elo "
            f"({MODEL.home_advantage_elo:.1f} points), so no single "
            "scenario adjustment overrides a larger, data-fit effect."
        ),
    }
