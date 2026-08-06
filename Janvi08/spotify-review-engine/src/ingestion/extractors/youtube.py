"""
youtube.py — YouTube comment extractor.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class YouTubeExtractor(BaseExtractor):
    """Extracts unified schema records from raw YouTube comment threads."""

    def source_name(self) -> str:
        return "youtube"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            
            # Case 1: Raw JSON API response dictionary loaded from file (has 'items')
            if "items" in item:
                for yt_item in item.get("items", []):
                    snippet = (
                        yt_item.get("snippet", {})
                        .get("topLevelComment", {})
                        .get("snippet", {})
                    )
                    if not snippet:
                        continue
                    text = snippet.get("textOriginal", "") or snippet.get("textDisplay", "")
                    published = snippet.get("publishedAt", "")
                    comment_id = (
                        yt_item.get("snippet", {})
                        .get("topLevelComment", {})
                        .get("id", "")
                    )
                    video_id = yt_item.get("snippet", {}).get("videoId", "")
                    extracted.append({
                        "source": self.source_name(),
                        "text": text.strip(),
                        "rating": None,
                        "date": self._parse_and_format_date(published),
                        "url": f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}" if video_id and comment_id else f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                        "thread_or_context": video_id,
                    })
            
            # Case 2: Processed comments from in-memory list or custom files
            elif "comment_id" in item or "video_id" in item or "text" in item:
                extracted.append({
                    "source": self.source_name(),
                    "text": item.get("text", ""),
                    "rating": None,
                    "date": self._parse_and_format_date(item.get("published_at", item.get("date", ""))),
                    "url": item.get("permalink", item.get("url", "")),
                    "thread_or_context": item.get("video_title", ""),
                })
        return extracted
