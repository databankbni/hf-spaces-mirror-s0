"""
Sala AI - Language Detection
Detects Sinhala / Tamil / English (including romanized Singlish)
"""

SINHALA_CHARS = set("අආඇඈඉඊඋඌඑඒඔඕකඛගඝඞඤටඨඩඪණතථදධනපඵබභමයරලවශෂසහළෆ")

SINGLISH_WORDS = {
    "machan", "aiyo", "kohomada", "oyata", "api", "eka", "neda",
    "puluwan", "badu", "yako", "aney", "ado", "wada", "kawda",
    "monawada", "koheda", "hadanne", "kiyanne", "danno", "inne",
    "ganna", "oni", "epa", "ow", "na", "meka", "eka", "mokakda",
}

LANGUAGE_NAMES = {
    "si": "Sinhala",
    "en": "English",
    "ta": "Tamil",
}
DEFAULT_LANGUAGE = "si"


def detect_language(text: str) -> str:
    """Returns 'si', 'ta', or 'en' based on unicode ranges and Singlish keywords."""
    if any(ch in SINHALA_CHARS for ch in text):
        return "si"
    if any('\u0B80' <= ch <= '\u0BFF' for ch in text):
        return "ta"
    words = set(text.lower().split())
    if words & SINGLISH_WORDS:
        return "si"
    return "en"
