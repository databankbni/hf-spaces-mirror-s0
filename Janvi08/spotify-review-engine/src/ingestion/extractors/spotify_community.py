"""
spotify_community.py — Spotify Community Forum post extractor.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class SpotifyCommunityExtractor(BaseExtractor):
    """Extracts unified schema records from raw Spotify Community Forum messages."""

    def source_name(self) -> str:
        return "spotify_community"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        for entry in raw_data:
            extracted.append({
                "source": self.source_name(),
                "text": entry.get("text", entry.get("body", "")),
                "rating": None,
                "date": self._parse_and_format_date(entry.get("date")),
                "url": entry.get("url", ""),
                "thread_or_context": entry.get("thread_title", entry.get("title", "")),
            })
        return extracted
