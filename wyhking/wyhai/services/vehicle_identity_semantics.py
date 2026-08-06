from __future__ import annotations

import re
import unicodedata
from typing import Iterable


_ASCII_CHUNK_RE = re.compile(r"[a-z]+|\d+", flags=re.I)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_SERIES_FAMILY_RE = re.compile(r"(?i)(?<![a-z])([a-z])\s*(?:级|系)|(\d)\s*系")
_NON_IDENTITY_CODES = {
    "amg",
    "bev",
    "cvt",
    "dm",
    "dmi",
    "dct",
    "ev",
    "hev",
    "phev",
    "pro",
    "max",
    "plus",
    "suv",
}


def normalize_identity_text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).lower()


def _ascii_chunks(value: object) -> list[str]:
    return _ASCII_CHUNK_RE.findall(normalize_identity_text(value))


def vehicle_code_tokens(value: object) -> set[str]:
    """Return token-aware model codes without joining unrelated numbers.

    The old matcher removed every separator before searching.  That made
    ``E63 2021`` contain the accidental substring ``320``.  Here we only join
    adjacent ASCII chunks when the group contains both letters and digits.
    """

    chunks = _ascii_chunks(value)
    tokens: set[str] = set()
    for chunk in chunks:
        if _YEAR_RE.fullmatch(chunk):
            continue
        if len(chunk) >= 2:
            tokens.add(chunk)

    for start in range(len(chunks)):
        for width in (2, 3):
            group = chunks[start : start + width]
            if len(group) != width:
                continue
            if any(_YEAR_RE.fullmatch(part) for part in group):
                continue
            joined = "".join(group)
            if len(joined) > 14:
                continue
            if not (any(part.isalpha() for part in group) and any(part.isdigit() for part in group)):
                continue
            tokens.add(joined)
    return tokens


def distinctive_vehicle_codes(value: object) -> set[str]:
    codes: set[str] = set()
    for token in vehicle_code_tokens(value):
        if token in _NON_IDENTITY_CODES or _YEAR_RE.fullmatch(token):
            continue
        if re.fullmatch(r"[a-z]+\d+[a-z]*", token):
            codes.add(token)
        elif re.fullmatch(r"\d+[a-z]+", token):
            # Engine descriptions such as 2.0T normalize into 20t and are not
            # stable vehicle identities.  Generic suffixes such as Max/Pro do
            # not turn that displacement into a configuration code.
            if not re.fullmatch(r"\d{1,2}[tl](?:pro|max|plus)?", token):
                codes.add(token)
        elif re.fullmatch(r"\d{3,4}", token):
            codes.add(token)
    return codes


def series_family_tokens(value: object) -> set[str]:
    text = normalize_identity_text(value)
    families: set[str] = set()
    for match in _SERIES_FAMILY_RE.finditer(text):
        family = match.group(1) or match.group(2)
        if family:
            families.add(family.lower())
    return families


def code_compatibility(query: object, candidate: object) -> bool | None:
    """Check whether explicit model codes can refer to the same identity.

    ``None`` means the query did not contain a distinctive code and therefore
    this guard has no opinion.  A one-character family such as ``E级`` or
    ``3系`` may contain a more specific query code such as ``E63`` or
    ``320Li``.  Different explicit codes are rejected.
    """

    query_codes = distinctive_vehicle_codes(query)
    if not query_codes:
        return None

    candidate_codes = distinctive_vehicle_codes(candidate)
    if query_codes & candidate_codes:
        return True

    candidate_families = series_family_tokens(candidate)
    if candidate_families and any(
        query_code.startswith(family)
        for query_code in query_codes
        for family in candidate_families
    ):
        return True

    if candidate_codes:
        return False
    return False


def alias_occurs_in_message(alias: object, message: object) -> bool:
    return alias_match_kind(alias, message) is not None


def alias_match_kind(alias: object, message: object) -> str | None:
    alias_text = normalize_identity_text(alias)
    message_text = normalize_identity_text(message)
    if not alias_text or not message_text:
        return None

    alias_codes = distinctive_vehicle_codes(alias_text)
    if alias_codes:
        message_codes = distinctive_vehicle_codes(message_text)
        if alias_codes & message_codes:
            return "exact_code"

    compact_alias = re.sub(r"[\s,，。._/()（）·・\-]+", "", alias_text)
    compact_message = re.sub(r"[\s,，。._/()（）·・\-]+", "", message_text)
    if _CHINESE_RE.search(compact_alias) and compact_alias in compact_message:
        return "exact_text"

    # Plain ASCII aliases use semantic tokens instead of arbitrary substrings.
    if compact_alias in vehicle_code_tokens(message_text):
        return "exact_token"

    alias_families = series_family_tokens(alias_text)
    if alias_families:
        message_codes = distinctive_vehicle_codes(message_text)
        if any(
            code.startswith(family)
            for code in message_codes
            for family in alias_families
        ):
            return "family_code"
    return None


def find_explicit_brand(message: object, brands: Iterable[str]) -> str | None:
    text = normalize_identity_text(message)
    matches = [brand for brand in brands if normalize_identity_text(brand) in text]
    return max(matches, key=len) if matches else None


def most_specific_query_code(value: object) -> str | None:
    codes = distinctive_vehicle_codes(value)
    if not codes:
        return None
    return max(codes, key=lambda code: (len(code), any(char.isalpha() for char in code)))
