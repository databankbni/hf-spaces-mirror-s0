import logging
from langdetect import detect, DetectorFactory

# Set seed for deterministic results
DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

class LanguageDetector:
    """Detects the language of a given text."""

    def detect_language(self, text: str) -> str:
        """Returns ISO 639-1 language code or 'unknown' if detection fails."""
        if not text or not text.strip():
            return "unknown"
        try:
            return detect(text)
        except Exception as e:
            logger.debug(f"Langdetect failed: {e}")
            return "unknown"
