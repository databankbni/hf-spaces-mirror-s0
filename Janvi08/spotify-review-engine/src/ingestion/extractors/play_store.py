"""
play_store.py — Play Store review extractor.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class PlayStoreExtractor(BaseExtractor):
    """Extracts unified schema records from raw Google Play Store data."""

    def source_name(self) -> str:
        return "play_store"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        for entry in raw_data:
            review_id = entry.get("reviewId", "")
            url = ""
            if review_id:
                url = f"https://play.google.com/store/apps/details?id=com.spotify.music&reviewId={review_id}"

            rating = entry.get("score")
            if rating is not None:
                try:
                    rating = int(rating)
                except (ValueError, TypeError):
                    rating = None

            extracted.append({
                "source": self.source_name(),
                "text": entry.get("content", ""),
                "rating": rating,
                "date": self._parse_and_format_date(entry.get("at")),
                "url": url,
                "thread_or_context": None,
            })
        return extracted
