import re

class PIIScrubber:
    """Removes sensitive personal information like emails and phone numbers."""

    def __init__(self):
        # Basic email regex
        self.email_pattern = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
        # Basic phone regex (international and US formats, ~10-15 digits with common separators)
        self.phone_pattern = re.compile(r'\+?\d{1,3}?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')

    def scrub(self, text: str) -> str:
        """Scrub PII from text."""
        if not text:
            return text
        text = self.email_pattern.sub('[EMAIL_REMOVED]', text)
        text = self.phone_pattern.sub('[PHONE_REMOVED]', text)
        return text
