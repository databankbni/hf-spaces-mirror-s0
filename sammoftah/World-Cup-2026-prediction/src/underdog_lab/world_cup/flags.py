"""Flag emoji for the countries that appear in this app.

Covers the 48 World Cup 2026 teams plus a couple of extra countries that
show up in the historical "Challenge" dataset (Greece, Italy). Flags are
rendered as standard Unicode regional-indicator emoji, generated from each
country's ISO 3166-1 alpha-2 code, so no image assets are needed.
"""

from __future__ import annotations

import html

_TAG_BASE = 0xE0000


def _flag_from_iso(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def _subdivision_flag(code: str) -> str:
    """England/Scotland use the black-flag + tag-sequence emoji."""
    return "\U0001F3F4" + "".join(chr(_TAG_BASE + ord(c)) for c in code) + "\U000E007F"


_ISO_CODES: dict[str, str] = {
    "Algeria": "DZ",
    "Argentina": "AR",
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia and Herzegovina": "BA",
    "Brazil": "BR",
    "Canada": "CA",
    "Cape Verde": "CV",
    "Colombia": "CO",
    "Croatia": "HR",
    "Curacao": "CW",
    "Czechia": "CZ",
    "DR Congo": "CD",
    "Ecuador": "EC",
    "Egypt": "EG",
    "France": "FR",
    "Germany": "DE",
    "Ghana": "GH",
    "Greece": "GR",
    "Haiti": "HT",
    "Iran": "IR",
    "Iraq": "IQ",
    "Italy": "IT",
    "Ivory Coast": "CI",
    "Japan": "JP",
    "Jordan": "JO",
    "Mexico": "MX",
    "Morocco": "MA",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Norway": "NO",
    "Panama": "PA",
    "Paraguay": "PY",
    "Portugal": "PT",
    "Qatar": "QA",
    "Saudi Arabia": "SA",
    "Senegal": "SN",
    "South Africa": "ZA",
    "South Korea": "KR",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Tunisia": "TN",
    "Turkey": "TR",
    "United States": "US",
    "Uruguay": "UY",
    "Uzbekistan": "UZ",
}

TEAM_FLAGS: dict[str, str] = {
    team: _flag_from_iso(code) for team, code in _ISO_CODES.items()
}
TEAM_FLAGS["England"] = _subdivision_flag("gbeng")
TEAM_FLAGS["Scotland"] = _subdivision_flag("gbsct")


def flag(team: str) -> str:
    """Return the flag emoji for ``team``, or '' if none is known."""
    return TEAM_FLAGS.get(team, "")


def team_label(team: str) -> str:
    """HTML-safe '<flag> Name' label, falling back to the plain name."""
    emoji = flag(team)
    name = html.escape(team)
    if not emoji:
        return name
    return f'<span class="flag">{emoji}</span>{name}'
