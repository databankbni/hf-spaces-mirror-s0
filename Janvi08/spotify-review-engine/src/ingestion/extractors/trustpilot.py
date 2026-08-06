"""
trustpilot.py — Trustpilot review extractor.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class TrustpilotExtractor(BaseExtractor):
    """Extracts unified schema records from raw Trustpilot reviews."""

    def source_name(self) -> str:
        return "trustpilot"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        for entry in raw_data:
            rating = entry.get("rating")
            if rating is not None:
                try:
                    rating = int(rating)
                except (ValueError, TypeError):
                    rating = None

            extracted.append({
                "source": self.source_name(),
                "text": entry.get("text", ""),
                "rating": rating,
                "date": self._parse_and_format_date(entry.get("date")),
                "url": entry.get("url", ""),
                "thread_or_context": None,
            })
        return extracted
