"""OCR text-quality heuristics shared across bounded contexts.

The textbook corpus is OCR'd from scanned Azerbaijani books; heading detection
sometimes captures noise lines (Cyrillic mis-recognitions, symbol runs, figure
captions, chapter-icon "badges") as section titles. These end up in
``section_blocks.section_title`` and, untreated, would surface verbatim in
user-facing citations (e.g. a citation titled ``Е a`` or ``UN"4``).

``sanitize_section_title`` normalises a raw stored title for display:
strip junk, keep readable titles, and return ``None`` for irrecoverable garble
so callers degrade to a page-based citation. Calibrated against all 572
distinct titles in the dev corpus (GRO-140); thresholds favour dropping a
borderline title over showing garbage.

Lives in ``app.platform`` (foundational kernel, no bounded-context imports)
because both retrieval (display-time, GRO-140) and ingestion (write-time,
GRO-141) need it.
"""

from __future__ import annotations

# Azerbaijani titles are Latin-script (incl. ə/ğ/ş/ç/ö/ü/ı); Cyrillic letters in
# this corpus are OCR mis-recognitions, not legitimate content.
_CYRILLIC_LO, _CYRILLIC_HI = "Ѐ", "ӿ"
_NOISE_SYMBOLS = set('"«»|_~^*#@<>')
_EDGE_STRIP = " -—=~:|_.,;"

# A readable title needs at least this many letters overall…
_MIN_LETTERS = 6
# …at most this share of Cyrillic among them…
_MAX_CYRILLIC_RATIO = 0.25
# …at most this share of garbled tokens…
_MAX_GARBLED_TOKEN_RATIO = 0.3
# …and must not be a paragraph grabbed as a heading.
_MAX_LENGTH = 70


def _is_cyrillic(ch: str) -> bool:
    return _CYRILLIC_LO <= ch <= _CYRILLIC_HI


def _is_chapter_number(token: str) -> bool:
    """Numbered-chapter prefixes are part of real titles, not OCR junk.

    Covers plain chapters (``9.`` / ``12:``) and dotted/decimal section numbers
    (``1.1``, ``2.3.4``). Without the dotted case, write-time gating (GRO-145)
    would strip the ``1.1`` off ``"1.1 Çoxluqlar"`` as a letter-less junk token
    and silently demote a real subsection title. A number-only token can never
    promote garble to "kept" — the letter/Cyrillic gates downstream still apply.
    """
    stripped = token.rstrip(".:")
    if not stripped:
        return False
    parts = stripped.split(".")
    return all(part.isdigit() for part in parts)


def _is_garbled_token(token: str) -> bool:
    """A token that signals OCR noise rather than a word.

    Single stray letters/symbols (``Ы``, ``©``, ``=``) and Cyrillic-dominant
    fragments (``ЕЕТЗ``, ``сори``) are noise. Two-letter Latin words are NOT
    noise — Azerbaijani uses real two-letter words (``və``, ``ya``, ``iş``).
    """
    letters = [c for c in token if c.isalpha()]
    if len(letters) < 2:
        return True
    cyrillic = sum(1 for c in letters if _is_cyrillic(c))
    return cyrillic / len(letters) > 0.5


def sanitize_section_title(raw: str | None) -> str | None:
    """Normalise an OCR section title for display; ``None`` if irrecoverable.

    Multi-line titles are collapsed to one line. Leading/trailing junk tokens
    (chapter-icon badges like ``ЕВ)``/``EEE``, symbol runs) are stripped while
    numbered-chapter prefixes are kept. The remainder is dropped entirely when
    it is still garble — too few letters, Cyrillic-dominant, too many garbled
    tokens, symbol noise, or paragraph-length text captured as a heading.
    """
    if not raw:
        return None
    tokens = raw.split()

    while tokens and not _is_chapter_number(tokens[0]) and _is_garbled_token(tokens[0]):
        tokens = tokens[1:]
    while (
        tokens and not _is_chapter_number(tokens[-1]) and _is_garbled_token(tokens[-1])
    ):
        tokens = tokens[:-1]

    title = " ".join(tokens).strip(_EDGE_STRIP)
    if not title:
        return None

    letters = [c for c in title if c.isalpha()]
    if len(letters) < _MIN_LETTERS:
        return None
    if sum(1 for c in letters if _is_cyrillic(c)) / len(letters) > _MAX_CYRILLIC_RATIO:
        return None

    inner_tokens = title.split()
    garbled = sum(
        1 for t in inner_tokens if _is_garbled_token(t) and not _is_chapter_number(t)
    )
    if garbled / len(inner_tokens) > _MAX_GARBLED_TOKEN_RATIO:
        return None

    if sum(1 for ch in title if ch in _NOISE_SYMBOLS) >= 2:
        return None
    if len(title) > _MAX_LENGTH:
        return None
    return title


def cyrillic_garble_token_ratio(text: str) -> float:
    """Calculates the share of Cyrillic-garbled alphabetic tokens in a text.

    Azerbaijani is Latin-script, so any token where > 50% of its letters are Cyrillic
    is OCR garble. The denominator is the number of tokens containing ≥1 alphabetic char.
    Calibrated against all 6 books in Family 1 to exactly reproduce manual garble counts.
    """
    tokens = text.split()
    alphabetic_tokens = 0
    garbled_tokens = 0
    for token in tokens:
        letters = [c for c in token if c.isalpha()]
        if not letters:
            continue
        alphabetic_tokens += 1
        cyrillic_count = sum(1 for c in letters if _is_cyrillic(c))
        if cyrillic_count / len(letters) > 0.5:
            garbled_tokens += 1
    return garbled_tokens / alphabetic_tokens if alphabetic_tokens else 0.0


def spaced_letter_run_count(text: str) -> int:
    """Counts occurrences of 'Q a r a b a ğ'-style OCR artifacts.

    A run is defined as 5 or more consecutive single-letter alphabetic tokens
    (e.g., 'Q', 'a', 'r', 'a', 'b'). This was calibrated against the Family 1
    books to approximate the target artifact density.
    """
    tokens = text.split()
    runs = 0
    current_run = 0
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            current_run += 1
        else:
            if current_run >= 5:
                runs += 1
            current_run = 0
    if current_run >= 5:
        runs += 1
    return runs


def title_keep_rate(titles: list[str | None]) -> float:
    """Measures the fraction of titles that survive sanitization.

    Returns 1.0 if the input sequence is empty, as no titles were incorrectly dropped.
    """
    if not titles:
        return 1.0
    kept = sum(1 for t in titles if sanitize_section_title(t) is not None)
    return kept / len(titles)
