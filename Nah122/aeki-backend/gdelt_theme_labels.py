"""
Human-readable labels for GDELT GKG theme codes (V2Themes / Themes).

Reference: GDELT GKG theme lookup — http://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT
"""

from __future__ import annotations

import re
from typing import Optional

# Exact codes (normalized: uppercase, underscores)
EXACT_LABELS: dict[str, str] = {
    "TAX_FNCACT": "Government & Public Officials",
    "TAX_WORLDLANGUAGES": "Languages & Linguistics",
    "TAX_ETHNICITY": "Ethnicity & Identity",
    "EPU_POLICY": "Economic Policy",
    "EPU_POLICY_GOVERNMENT": "Government Economic Policy",
    "EPU_POLICY_LAW": "Law & Regulation Policy",
    "EPU_POLICY_POLITICAL": "Political Policy",
    "EPU_POLICY_BUDGET": "Budget & Fiscal Policy",
    "CRISISLEX_CRISISLEXREC": "Crisis Events",
    "USPEC_POLICY1": "US Policy",
    "USPEC_POLITICS_GENERAL1": "US Politics",
    "USPEC_UNCERTAINTY1": "US Policy Uncertainty",
    "WB_696_PUBLIC_SECTOR_MANAGEMENT": "Public Sector Management",
    "SOC_POINTSOFINTEREST": "Places & Institutions",
    "SOC_POINTSOFINTEREST_SCHOOL": "Schools",
    "SOC_POINTSOFINTEREST_HOSPITAL": "Hospitals",
    "SOC_POINTSOFINTEREST_UNIVERSITY": "Universities",
    "UNGP_FORESTS_RIVERS_OCEANS": "Environment & Natural Resources",
    "UNGP_CRIME_VIOLENCE": "Crime & Violence",
    "UNGP_HEALTHCARE": "Healthcare",
    "UNGP_CLEAN_WATER_SANITATION": "Clean Water & Sanitation",
    "UN_PRINCIPLES": "UN Principles & Global Goals",
    "UN_PRINCIPLE": "UN Principles",
    "ARMEDCONFLICT": "Armed Conflict",
    "ECONOMY": "Economy",
    "ECON_STOCKMARKET": "Stock Market",
    "ECON_TAXATION": "Taxation",
    "ECON_WORLDCURRENCIES": "World Currencies",
    "GENERAL_GOVERNMENT": "Government",
    "PROTEST": "Protests",
    "TERROR": "Terrorism",
    "WMD": "Weapons of Mass Destruction",
    "NATURAL_DISASTER": "Natural Disaster",
    "FOOD_SECURITY": "Food Security",
    "HUMANITARIAN": "Humanitarian Crisis",
    "MIGRATION": "Migration",
    "REFUGEES": "Refugees",
    "ELECTION": "Elections",
    "EDUCATION": "Education",
    "HEALTH_PANDEMIC": "Health Pandemic",
    "MEDICAL": "Medical",
    "LEADER": "Leadership",
    "DIPLOMACY": "Diplomacy",
}

# Longest-prefix wins (prefix, label)
PREFIX_LABELS: list[tuple[str, str]] = sorted(
    [
        ("CRISISLEX_CRISISLEXREC", "Crisis Events"),
        ("CRISISLEX_", "Crisis & Emergency"),
        ("TAX_FNCACT_", "Officials & Public Actors"),
        ("TAX_FNCACT", "Government & Officials"),
        ("TAX_WORLDLANGUAGES_", "Languages"),
        ("TAX_WORLDLANGUAGES", "Languages & Linguistics"),
        ("TAX_ETHNICITY_", "Ethnicity"),
        ("TAX_ETHNICITY", "Ethnicity & Identity"),
        ("TAX_DISEASE_", "Disease & Health"),
        ("TAX_DISEASE", "Disease & Health"),
        ("TAX_AIDGROUPS_", "Aid Organizations"),
        ("TAX_POLITICAL_PARTY_", "Political Parties"),
        ("TAX_WEAPONS_", "Weapons"),
        ("TAX_WORLDBIRDS_", "Birds & Wildlife"),
        ("TAX_WORLDMAMMALS_", "Mammals & Wildlife"),
        ("WB_", "World Bank Topic"),
        ("UNGP_", "UN Sustainable Development Goal"),
        ("UNGP", "UN Global Goals"),
        ("UN_", "United Nations"),
        ("EPU_POLICY_", "Economic Policy"),
        ("EPU_POLICY", "Economic Policy"),
        ("EPU_", "Economic Policy Uncertainty"),
        ("USPEC_POLICY", "US Policy"),
        ("USPEC_", "US Current Events"),
        ("SOC_POINTSOFINTEREST_", "Places & Institutions"),
        ("SOC_POINTSOFINTEREST", "Points of Interest"),
        ("SOC_", "Social Topics"),
        ("ECON_", "Economy & Markets"),
        ("TAX_", "Topical Classification"),
        ("ARMEDCONFLICT", "Armed Conflict"),
        ("NATURAL_DISASTER_", "Natural Disaster"),
        ("NATURAL_DISASTER", "Natural Disaster"),
        ("FOOD_SECURITY", "Food Security"),
        ("HUMANITARIAN", "Humanitarian"),
        ("MILITARY", "Military"),
        ("PROTEST", "Protests"),
        ("TERROR", "Terrorism"),
        ("REFUGEE", "Refugees"),
        ("ELECTION", "Elections"),
        ("EDUCATION", "Education"),
        ("ENV_", "Environment"),
        ("ENVIRONMENT", "Environment"),
        ("HEALTH", "Health"),
        ("MEDICAL", "Medical"),
        ("DIPLOMACY", "Diplomacy"),
        ("LEADER", "Leadership"),
    ],
    key=lambda x: len(x[0]),
    reverse=True,
)

_TRAILING_DIGITS = re.compile(r"(\d+)$")


def normalize_theme_code(raw: str) -> str:
    if not raw:
        return ""
    code = str(raw).strip().upper()
    code = re.sub(r"[^\w\s]", "_", code)
    code = re.sub(r"\s+", "_", code)
    return re.sub(r"_+", "_", code).strip("_")


def label_gdelt_theme(raw: str) -> str:
    """Map a GDELT theme code to a short human-readable label."""
    code = normalize_theme_code(raw)
    if not code:
        return ""

    if code in EXACT_LABELS:
        return EXACT_LABELS[code]

    for prefix, label in PREFIX_LABELS:
        if code == prefix or code.startswith(prefix + "_"):
            suffix = code[len(prefix) :].lstrip("_")
            if not suffix:
                return label
            # e.g. TAX_FNCACT_PRESIDENT -> Officials: President
            role = _format_suffix(suffix)
            if prefix.endswith("_"):
                return f"{label}: {role}"
            return f"{label} ({role})" if len(role) < 40 else label

    return _fallback_label(code)


def _format_suffix(suffix: str) -> str:
    s = _TRAILING_DIGITS.sub("", suffix)
    return s.replace("_", " ").strip().title()


def _fallback_label(code: str) -> str:
    # Already readable (e.g. "Economy", "Armed Conflict")
    if " " in code and "_" not in code:
        return code.strip().title()
    if len(code) <= 24 and "_" not in code:
        return code.title()

    parts = []
    for part in code.split("_"):
        if not part or part.isdigit():
            continue
        part = _TRAILING_DIGITS.sub("", part)
        if part:
            parts.append(part)
    if not parts:
        return code.replace("_", " ").title()
    return " ".join(parts).title()


def map_themes_field(themes_str: str, max_items: int = 6) -> str:
    """Comma-separated GDELT codes -> comma-separated human labels."""
    if not themes_str:
        return ""
    seen: set[str] = set()
    labels: list[str] = []
    for part in themes_str.split(","):
        raw = part.strip()
        if not raw or len(raw) < 3:
            continue
        label = label_gdelt_theme(raw)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
        if len(labels) >= max_items:
            break
    return ", ".join(labels)


def theme_matches_filter(themes_str: str, topic_raw: str) -> bool:
    """True if article themes contain the selected topic code."""
    if not themes_str or not topic_raw:
        return True
    needle = normalize_theme_code(topic_raw)
    if not needle:
        return True
    for part in themes_str.split(","):
        if normalize_theme_code(part) == needle:
            return True
        # Parent bucket: TAX_FNCACT matches TAX_FNCACT_PRESIDENT
        if normalize_theme_code(part).startswith(needle + "_"):
            return True
    return False
