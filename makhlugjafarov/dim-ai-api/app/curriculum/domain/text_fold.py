"""Azerbaijani-aware text folding for diacritic-insensitive topic lookup.

A module (or an LLM) referring to a topic types it the natural way — ``"iqlim"``,
``"funksiya"`` — without the book's diacritics or dotted/dotless casing. Postgres
``ILIKE`` is diacritic-sensitive and Python's ``str.casefold`` mishandles the
Turkic dotted/dotless ``I`` (``"İ".casefold()`` yields a combining dot), so we map
the Azerbaijani-specific letters explicitly *before* casefolding. This keeps topic
resolution robust to how people and models actually write Azerbaijani.
"""

from __future__ import annotations

# Map the letters that ASCII-folding / casefold get wrong for Azerbaijani onto a
# plain ASCII base. Applied before casefold so the dotted/dotless I is handled
# deterministically rather than via Unicode default casing.
_AZ_FOLD = str.maketrans(
    {
        "ı": "i", "İ": "i", "I": "i",
        "ə": "e", "Ə": "e",
        "ö": "o", "Ö": "o",
        "ü": "u", "Ü": "u",
        "ş": "s", "Ş": "s",
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
    }
)


def az_fold(text: str) -> str:
    """Fold ``text`` to a diacritic-insensitive, case-insensitive comparison key."""
    return text.translate(_AZ_FOLD).casefold().strip()
