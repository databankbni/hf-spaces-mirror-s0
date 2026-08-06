"""
reddit.py — Reddit manual curation stub (ADR-011).

Reddit's "Responsible Builder Policy" (updated June 2026) restricts
programmatic API access, making automated fetching unreliable. This
module is now a **manual curation loader** instead of an API fetcher.

Workflow:
  1. The user manually browses Reddit (r/spotify, r/musicsuggestions,
     r/WeAreTheMusicMakers) and collects relevant posts/comments about
     music discovery and recommendations.
  2. The user saves curated entries as JSON files in data/raw/reddit/
     following the schema documented below.
  3. This loader reads those files and returns them as raw records.

Expected input file format (data/raw/reddit/curated.json):
    [
        {
            "text": "post or comment text",
            "title": "optional post title",
            "date": "2026-03-15T10:30:00Z",
            "url": "https://www.reddit.com/r/spotify/comments/...",
            "subreddit": "spotify",
            "type": "post"
        },
        ...
    ]

Edge cases handled:
  - No curated file exists (returns empty list with warning)
  - Malformed JSON (logged, returns empty)
  - Missing required fields (entry skipped with warning)
  - Entries outside 4-month window (filtered out)

Supersedes: ADR-004, ADR-010
See: docs/decisions.md (ADR-011)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingestion.config import (
    RAW_REDDIT_DIR,
    get_caps,
    get_cutoff_date,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

# Accepted curated file names (searched in order)
_CURATED_FILES = [
    "curated.json",
    "curated.jsonl",
    "manual_curated.json",
    "reddit_curated.json",
]


class RedditFetcher(BaseFetcher):
    """Loads manually curated Reddit posts/comments from data/raw/reddit/.

    This is NOT an automated fetcher — it expects a human to have placed
    curated JSON files in the raw data directory. See module docstring
    for the expected format.
    """

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).reddit

    def source_name(self) -> str:
        return "reddit"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Load curated Reddit entries from disk.

        Returns raw record dicts loaded from JSON files in data/raw/reddit/.
        If no curated files exist, returns an empty list with a warning.
        """
        logger.info(
            "[reddit] Loading manually curated data (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        cutoff = get_cutoff_date()
        all_records: list[dict] = []

        # Try to find curated files
        found_files = self._find_curated_files()

        if not found_files:
            logger.warning(
                "[reddit] No curated data files found in %s. "
                "To add Reddit data, manually create one of: %s "
                "with an array of JSON objects. See docs for format.",
                RAW_REDDIT_DIR,
                ", ".join(_CURATED_FILES),
            )
            return []

        for filepath in found_files:
            if len(all_records) >= self._cap:
                break

            records = self._load_file(filepath, cutoff)
            all_records.extend(records)
            logger.info(
                "[reddit] Loaded %d records from %s (running total=%d)",
                len(records), filepath.name, len(all_records),
            )

        all_records = all_records[: self._cap]
        logger.info("[reddit] Done: %d curated records loaded", len(all_records))
        return all_records

    # ------------------------------------------------------------------ #
    # File loading                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_curated_files() -> list[Path]:
        """Find curated JSON files in data/raw/reddit/."""
        found: list[Path] = []

        # Check well-known names first
        for name in _CURATED_FILES:
            path = RAW_REDDIT_DIR / name
            if path.exists():
                found.append(path)

        # Also pick up any other .json files (except metadata)
        for path in sorted(RAW_REDDIT_DIR.glob("*.json")):
            if path not in found and path.name != "meta.json":
                found.append(path)

        # And .jsonl files
        for path in sorted(RAW_REDDIT_DIR.glob("*.jsonl")):
            if path not in found:
                found.append(path)

        return found

    def _load_file(self, filepath: Path, cutoff: datetime) -> list[dict]:
        """Load and validate records from a single JSON or JSONL file."""
        records: list[dict] = []

        try:
            content = filepath.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("[reddit] Could not read %s: %s", filepath, exc)
            return []

        # Try JSONL first (one object per line)
        if filepath.suffix == ".jsonl":
            raw_list = self._parse_jsonl(content, filepath)
        else:
            raw_list = self._parse_json(content, filepath)

        if not raw_list:
            return []

        # Validate and filter each entry
        for i, entry in enumerate(raw_list):
            if not isinstance(entry, dict):
                logger.warning("[reddit] Entry %d in %s is not a dict — skipping", i, filepath.name)
                continue

            # Must have text
            text = entry.get("text", "").strip()
            if not text:
                title = entry.get("title", "").strip()
                body = entry.get("body", "").strip()
                selftext = entry.get("selftext", "").strip()
                text = body or selftext or title
            if not text:
                logger.warning("[reddit] Entry %d in %s has no text — skipping", i, filepath.name)
                continue

            # Date filter
            date_str = entry.get("date", "") or entry.get("created_utc", "")
            if date_str and not self._is_within_window(date_str, cutoff):
                continue

            # Normalise the entry to our expected raw format
            records.append({
                "_type": entry.get("type", entry.get("_type", "post")),
                "text": text,
                "title": entry.get("title", ""),
                "date": date_str,
                "url": entry.get("url", entry.get("permalink", "")),
                "subreddit": entry.get("subreddit", "spotify"),
                "author": entry.get("author", ""),
            })

        return records

    @staticmethod
    def _parse_json(content: str, filepath: Path) -> list[dict]:
        """Parse a JSON file — expects a list of dicts or a single dict."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("[reddit] Invalid JSON in %s: %s", filepath, exc)
            return []

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        logger.warning("[reddit] Unexpected JSON type in %s: %s", filepath, type(data).__name__)
        return []

    @staticmethod
    def _parse_jsonl(content: str, filepath: Path) -> list[dict]:
        """Parse a JSONL file (one JSON object per line)."""
        entries: list[dict] = []
        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entries.append(obj)
            except json.JSONDecodeError as exc:
                logger.warning("[reddit] Invalid JSON at %s:%d — %s", filepath.name, line_num, exc)
        return entries

    @staticmethod
    def _is_within_window(date_str: str, cutoff: datetime) -> bool:
        """Check if a date string is within the 4-month window."""
        try:
            # Handle Unix timestamps
            if isinstance(date_str, (int, float)):
                dt = datetime.fromtimestamp(float(date_str), tz=timezone.utc)
                return dt >= cutoff

            from dateutil import parser as du_parser
            parsed = du_parser.parse(str(date_str))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except Exception:
            return True  # Keep if unparseable — let Phase 2 handle
