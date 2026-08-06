"""
Sala AI - Translation Layer
The LLM always composes its answer in English (more reliable/consistent
output quality). This module translates that English text into the
user's target language, while protecting brand names, store URLs,
prices, product codes, and common English/hybrid loanwords from being
altered by translation.
"""
import re
import logging
from deep_translator import GoogleTranslator

log = logging.getLogger("SalaAI")

# Things that should NEVER be translated / transliterated:
# - store domain (sala.lk)
# - prices like "Rs. 17,350" or "Rs.17350.00"
# - product codes / SKUs (e.g. "DL-7306", "AC1200", "AP13000")
PROTECT_PATTERN = re.compile(
    r"(sala\.lk|Rs\.\s?[\d,]+(?:\.\d+)?|\b[A-Z]{2,}[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b)"
)

# Common tech/shopping words that Sri Lankan customers already use as
# English/hybrid loanwords in everyday Sinhala and Tamil chat (e.g. "online
# ekක", "WiFi eka thiyenawada"). Google Translate tends to convert these into
# overly formal, literal words (e.g. "online" -> "සබැඳිව") that sound stiff
# and unnatural in casual chat. Protecting them the same way as brand names
# keeps them in English inside the translated reply, matching how people
# actually type. Extend this list as more mistranslated terms come up.
HYBRID_TERMS = [
    "online", "offline", "Wi-Fi", "WiFi", "wifi", "router", "extender",
    "access point", "UPS", "PBX", "IP PBX", "FXO", "FXS", "invoice",
    "warranty", "app", "email", "hotline", "delivery", "stock",
    "USB", "HDMI", "LED", "LCD", "CCTV", "DVR", "NVR", "GPS",
    "double-conversion", "double conversion", "line-interactive",
    "line interactive", "true online", "surge protection", "voltage",
]
# Longest-first so multi-word terms (e.g. "access point", "IP PBX") match
# before any shorter overlapping term does; re.escape handles the hyphen
# in "Wi-Fi" safely.
_HYBRID_ALTERNATION = "|".join(
    re.escape(term) for term in sorted(HYBRID_TERMS, key=len, reverse=True)
)
HYBRID_PATTERN = re.compile(r"\b(?:" + _HYBRID_ALTERNATION + r")\b", re.IGNORECASE)


def _protect(text: str):
    """Replace protected terms with placeholders so translation leaves them untouched."""
    placeholders = {}

    def _replace(match):
        token = f"XPROTECTX{len(placeholders)}X"
        placeholders[token] = match.group(0)
        return token

    # Pass 1: brand names / prices / SKUs (case-sensitive - relies on
    # capitalization patterns to avoid over-matching ordinary words).
    protected_text = PROTECT_PATTERN.sub(_replace, text)
    # Pass 2: common English/hybrid loanwords (case-insensitive), run on
    # whatever text pass 1 left untouched.
    protected_text = HYBRID_PATTERN.sub(_replace, protected_text)
    return protected_text, placeholders


def _restore(text: str, placeholders: dict):
    """Put the original protected terms back after translation."""
    for token, original in placeholders.items():
        # translation services sometimes alter case/spacing of placeholders slightly
        text = re.sub(re.escape(token), original, text, flags=re.IGNORECASE)
    return text


def translate_text(text: str, target_lang: str) -> str:
    """
    Translates English text into the target language ('si' or 'ta').
    Returns the original text unchanged if target_lang is 'en' or unsupported,
    or if translation fails for any reason.
    """
    if not text or not text.strip():
        return text
    if target_lang not in ("si", "ta"):
        return text  # English or unknown -> no translation needed
    try:
        protected_text, placeholders = _protect(text)
        translated = GoogleTranslator(source="en", target=target_lang).translate(protected_text)
        return _restore(translated, placeholders)
    except Exception as e:
        log.error(f"Translation failed ({target_lang}): {e}")
        return text  # fail safe: return the English text rather than crash