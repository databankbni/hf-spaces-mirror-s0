"""
app_store.py — App Store review extractor.
"""

from __future__ import annotations

import html
from typing import Any

from src.ingestion.extractors.base_extractor import BaseExtractor


class AppStoreExtractor(BaseExtractor):
    """Extracts unified schema records from raw Apple App Store RSS JSON entries."""

    def source_name(self) -> str:
        return "app_store"

    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted = []
        
        flat_entries = []
        for item in raw_data:
            if isinstance(item, dict) and "feed" in item:
                feed = item.get("feed", {})
                entries = feed.get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]
                flat_entries.extend(entries)
            else:
                flat_entries.append(item)

        for entry in flat_entries:
            # Extract author name
            author_val = entry.get("author", {})
            author = ""
            if isinstance(author_val, dict):
                author = author_val.get("name", {}).get("label", "") if isinstance(author_val.get("name"), dict) else str(author_val.get("name", ""))

            # Extract title and body content
            title_val = entry.get("title", "")
            title = title_val.get("label", "").strip() if isinstance(title_val, dict) else str(title_val).strip()

            content_val = entry.get("content", "")
            content = content_val.get("label", "").strip() if isinstance(content_val, dict) else str(content_val).strip()

            # Handle HTML entities in text (EC-1.2.12)
            if title:
                text = f"{title}\n\n{content}".strip()
            else:
                text = content.strip()
            
            text = html.unescape(text)

            # Rating mapping (EC-1.2.11)
            rating_val = entry.get("im:rating", {})
            rating = None
            if isinstance(rating_val, dict):
                rating_str = rating_val.get("label")
            else:
                rating_str = rating_val

            if rating_str is not None:
                try:
                    rating = int(str(rating_str).strip())
                except (ValueError, TypeError):
                    rating = None

            # Date updated mapping
            updated_val = entry.get("updated", {})
            updated_str = updated_val.get("label", "") if isinstance(updated_val, dict) else str(updated_val)

            # URL link mapping
            link_val = entry.get("link", {})
            url = ""
            if isinstance(link_val, dict):
                url = link_val.get("attributes", {}).get("href", "")
            elif isinstance(link_val, list):
                # Sometimes there's multiple links
                for link in link_val:
                    if isinstance(link, dict) and link.get("attributes", {}).get("rel") == "alternate":
                        url = link.get("attributes", {}).get("href", "")
                        break
                if not url and len(link_val) > 0 and isinstance(link_val[0], dict):
                    url = link_val[0].get("attributes", {}).get("href", "")

            extracted.append({
                "source": self.source_name(),
                "text": text,
                "rating": rating,
                "date": self._parse_and_format_date(updated_str),
                "url": url,
                "thread_or_context": None,
            })
        return extracted
