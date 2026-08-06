"""
base_extractor.py — Abstract base class for all source extractors.

Every concrete extractor (PlayStoreExtractor, AppStoreExtractor, etc.)
must inherit from this and implement `extract()` and `source_name()`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as du_parser


class BaseExtractor(ABC):
    """Abstract base for all source extractors."""

    @abstractmethod
    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform raw API data into unified schema dicts.

        Args:
            raw_data: A list of raw dictionaries retrieved by the Fetcher.

        Returns:
            A list of dictionaries matching the unified schema.
        """
        pass

    @abstractmethod
    def source_name(self) -> str:
        """Return the canonical source name, matching the Fetcher's source_name."""
        pass

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_and_format_date(date_val: Any) -> str:
        """Parse a date value and return an ISO 8601 string in UTC.

        Returns an empty string if parsing fails or input is empty.
        Expected format: YYYY-MM-DDTHH:MM:SSZ
        """
        if not date_val:
            return ""

        # Handle Unix timestamps (int or float)
        if isinstance(date_val, (int, float)):
            try:
                dt = datetime.fromtimestamp(float(date_val), tz=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                return ""

        if isinstance(date_val, datetime):
            dt = date_val
        else:
            try:
                dt = du_parser.parse(str(date_val))
            except Exception:
                return str(date_val)  # Fallback to string if parsing fails

        # Normalise timezone to UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
