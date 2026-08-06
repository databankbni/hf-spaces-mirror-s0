from __future__ import annotations

from enum import Enum


class FactorType(str, Enum):
    KEY_ATTACKER_UNAVAILABLE = "key_attacker_unavailable"
    KEY_DEFENDER_UNAVAILABLE = "key_defender_unavailable"
    GOALKEEPER_UNAVAILABLE = "goalkeeper_unavailable"
    MULTIPLE_STARTERS_UNAVAILABLE = "multiple_starters_unavailable"
    SQUAD_ROTATION = "squad_rotation"
    FATIGUE_DISADVANTAGE = "fatigue_disadvantage"
    REST_ADVANTAGE = "rest_advantage"
    TRAVEL_DISADVANTAGE = "travel_disadvantage"
    ALTITUDE_DISADVANTAGE = "altitude_disadvantage"
    HEAT_DISADVANTAGE = "heat_disadvantage"
    HOME_ADVANTAGE = "home_advantage"
    NEUTRAL_VENUE = "neutral_venue"
    DEFENSIVE_GAME_STATE = "defensive_game_state"
    MUST_WIN_INCENTIVE = "must_win_incentive"
