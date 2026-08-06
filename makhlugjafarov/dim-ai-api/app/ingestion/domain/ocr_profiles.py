"""OCR language profiles per education sector — single source of truth.

The product serves the **Azerbaijani sector** today (`az` → Tesseract `aze+eng`).
The **Russian sector** (`ru`) is a future target: its profile ships here
present-but-unused so enabling it later is a one-line *data* change — tag a
source `language: "ru"` and it resolves to the `ru` profile with no code edit.
Adding another sector = add one entry to ``OCR_LANGUAGE_PROFILES``.

Why this matters: Tesseract resolves OCR'd glyphs against the union of its
enabled language models. Giving it `rus` while reading Azerbaijani (a Latin
script) lets it mis-resolve stylized Latin text into Cyrillic — the garble
signature measured in GRO-143. So the language set must track the book's actual
sector, not a blanket default. This module is the seam that keeps that decision
in one place instead of scattered per-source language lists.

Pure domain: no I/O, no imports from other bounded contexts (and deliberately
none from ``models`` so callers can import it without a cycle).
"""
from __future__ import annotations

# Sector code (matches ``ManifestSource.language``) → Tesseract language models,
# most-specific first. `eng` stays in every profile: Latin digits, units, and
# loanwords appear in every book regardless of sector.
OCR_LANGUAGE_PROFILES: dict[str, list[str]] = {
    "az": ["aze", "eng"],          # Azerbaijani sector — the only active target
    "ru": ["rus", "aze", "eng"],   # Russian sector — future; present but unused
}

DEFAULT_SECTOR = "az"


def languages_for_sector(sector: str | None) -> list[str]:
    """Tesseract language list for a sector code, falling back to the default.

    An unknown or missing sector resolves to the default (`az`) profile rather
    than raising, so a typo degrades to the safe Azerbaijani set instead of
    breaking ingestion. Returns a fresh list so callers can't mutate the registry.
    """
    return list(OCR_LANGUAGE_PROFILES.get(sector or DEFAULT_SECTOR, OCR_LANGUAGE_PROFILES[DEFAULT_SECTOR]))
