"""
reddit.py — Reddit post/comment extractor.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class RedditExtractor(BaseExtractor):
    """Extracts unified schema records from raw Reddit posts and comments."""

    def source_name(self) -> str:
        return "reddit"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        for entry in raw_data:
            subreddit = entry.get("subreddit", "spotify")
            thread_or_context = f"r/{subreddit}" if subreddit else None

            # Normalise Reddit date which could be a Unix timestamp or an ISO string
            raw_date = entry.get("date") or entry.get("created_utc")

            # Fallback URL construction if permalink exists
            url = entry.get("url") or entry.get("permalink") or ""
            if url and url.startswith("/r/"):
                url = f"https://www.reddit.com{url}"

            extracted.append({
                "source": self.source_name(),
                "text": entry.get("text", ""),
                "rating": None,
                "date": self._parse_and_format_date(raw_date),
                "url": url,
                "thread_or_context": thread_or_context,
            })
        return extracted
