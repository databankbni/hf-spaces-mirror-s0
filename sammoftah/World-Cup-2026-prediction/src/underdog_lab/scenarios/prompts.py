from __future__ import annotations

from underdog_lab.domain import MatchRecord


SYSTEM_PROMPT = (
    "You extract football scenario factors into JSON.\n"
    "Use only the allowed factor taxonomy. Do not predict scores or probabilities.\n"
    "Resolve team references as home, away, both, or unknown.\n"
    "Put claims outside the taxonomy in unsupported_claims.\n"
    "Put unclear team references or contradictions in ambiguities.\n"
    "Keep evidence short and copied from the user text.\n"
    "\n"
    "Examples:\n"
    '- "Canada\'s striker is confirmed out." means\n'
    "  key_attacker_unavailable for the home team.\n"
    '- "The away goalkeeper is injured." means\n'
    "  goalkeeper_unavailable for the away team.\n"
    '- "They are playing at home." means home_advantage only when a team is clear.\n'
    "- Never emit home_advantage, neutral_venue, or squad_rotation unless the\n"
    "  scenario explicitly says so.\n"
    "\n"
    "Return only the JSON object."
)


def user_content(
    *,
    match: MatchRecord | None = None,
    text: str = "",
    home_team: str = "",
    away_team: str = "",
    neutral_venue: bool = True,
) -> str:
    """Build the user message content.

    Accepts either a MatchRecord or keyword args so both runtime and training
    can share the exact format string.
    """
    if match is not None:
        home_team = match.home_team
        away_team = match.away_team
        neutral_venue = match.neutral_venue
    venue = "neutral" if neutral_venue else "home venue"
    return (
        f"Home team: {home_team}\n"
        f"Away team: {away_team}\n"
        f"Recorded venue: {venue}\n"
        f"Scenario: {text}"
    )


def build_prompt(text: str, match: MatchRecord) -> str:
    return f"{SYSTEM_PROMPT}\n\n{user_content(match=match, text=text)}\nJSON:"


def build_messages(text: str, match: MatchRecord) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content(match=match, text=text)},
    ]
