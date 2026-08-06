"""
Sala AI - Lightweight Sentiment Detector
Keyword-based (no extra LLM call / cost) - good enough for dashboard trend signals.
Covers Sinhala, Singlish, and English keywords.
"""

POSITIVE_WORDS = [
    "sthuti", "thanks", "thank you", "hodai", "hondai", "supiri", "niyamai",
    "හොඳයි", "සුපිරි", "නියමයි", "ස්තූතියි", "පුදුම", "wada", "excellent",
    "good", "great", "awesome", "helpful", "santhosai", "සන්තෝෂයි",
]

NEGATIVE_WORDS = [
    "naraka", "narakai", "poor", "bad", "waradi", "issue", "problem",
    "amaruyi", "amarui", "hari naha", "eka na", "ganan wadi", "kanagatui",
    "නරකයි", "වැරදියි", "ප්‍රශ්නයක්", "අමාරුයි", "කනගාටුයි", "sad", "angry",
    "disappointed", "not working", "vada karanne na", "refund", "complaint",
]


def detect_sentiment(text: str) -> str:
    """Returns 'positive', 'negative', or 'neutral' based on keyword presence."""
    if not text:
        return "neutral"

    lower_text = text.lower()

    pos_hit = any(word in lower_text for word in POSITIVE_WORDS)
    neg_hit = any(word in lower_text for word in NEGATIVE_WORDS)

    if neg_hit and not pos_hit:
        return "negative"
    if pos_hit and not neg_hit:
        return "positive"
    return "neutral"