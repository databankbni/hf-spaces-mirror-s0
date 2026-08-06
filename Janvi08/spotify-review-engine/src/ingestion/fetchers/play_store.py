"""
play_store.py — Google Play Store review fetcher.

Uses the `google-play-scraper` library (sync), wrapped in asyncio.to_thread()
so it integrates cleanly with the async pipeline.

Edge cases handled:
  EC-1.1.07  Library raises an exception internally
  EC-1.1.08  Non-English reviews (lang/country params)
  EC-1.1.09  Continuation token loops
  EC-1.2.07  Missing score field
  EC-1.2.08  Missing reviewId
  EC-1.2.09  Timezone-naive datetime
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.ingestion.config import (
    PLAY_STORE_APP_ID,
    PLAY_STORE_COUNTRY,
    PLAY_STORE_DELAY_S,
    PLAY_STORE_LANG,
    PLAY_STORE_MAX_PAGES,
    get_caps,
    get_cutoff_date,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)


class PlayStoreFetcher(BaseFetcher):
    """Fetches Spotify reviews from Google Play Store."""

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).play_store

    def source_name(self) -> str:
        return "play_store"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch Play Store reviews up to the configured cap.

        Returns raw review dicts as produced by google-play-scraper,
        filtered to the 4-month window, saved to data/raw/play_store/.
        """
        logger.info(
            "[play_store] Starting fetch (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        try:
            raw_reviews = await asyncio.to_thread(self._fetch_sync)
        except Exception as exc:
            logger.error("[play_store] Fetch failed: %s", exc, exc_info=True)
            return []

        # Post-fetch date filter
        cutoff = get_cutoff_date()
        filtered = [r for r in raw_reviews if self._is_within_window(r, cutoff)]
        dropped = len(raw_reviews) - len(filtered)
        if dropped:
            logger.info("[play_store] Dropped %d reviews outside 4-month window", dropped)

        logger.info("[play_store] Done: %d reviews collected", len(filtered))
        return filtered

    # ------------------------------------------------------------------ #
    # Sync implementation (runs in thread pool via asyncio.to_thread)      #
    # ------------------------------------------------------------------ #

    def _fetch_sync(self) -> list[dict[str, Any]]:
        """Synchronous fetch logic — called from a thread pool."""
        try:
            from google_play_scraper import Sort, reviews as gps_reviews
        except ImportError as exc:
            raise ImportError(
                "google-play-scraper is not installed. "
                "Run: pip install google-play-scraper"
            ) from exc

        all_reviews: list[dict] = []
        continuation_token = None
        seen_tokens: set[str] = set()
        page = 0

        while len(all_reviews) < self._cap and page < PLAY_STORE_MAX_PAGES:
            page += 1
            batch_size = min(200, self._cap - len(all_reviews))

            try:
                result, new_token = gps_reviews(
                    PLAY_STORE_APP_ID,
                    lang=PLAY_STORE_LANG,
                    country=PLAY_STORE_COUNTRY,
                    sort=Sort.NEWEST,
                    count=batch_size,
                    continuation_token=continuation_token,
                )
            except Exception as exc:
                logger.error(
                    "[play_store] google-play-scraper error on page %d: %s",
                    page, exc, exc_info=True,
                )
                break

            if not result:
                logger.info("[play_store] Empty batch on page %d — end of data", page)
                break

            all_reviews.extend(result)
            logger.debug("[play_store] Page %d: fetched %d reviews (total=%d)", page, len(result), len(all_reviews))

            # Save raw page for provenance
            self.save_raw(result, f"page_{page}.json")

            # EC-1.1.09: guard against token loop
            token_key = str(getattr(new_token, "token", new_token))
            if not new_token or token_key in seen_tokens:
                logger.info("[play_store] No new pagination token — stopping at page %d", page)
                break
            seen_tokens.add(token_key)
            continuation_token = new_token

            import time
            time.sleep(PLAY_STORE_DELAY_S)

        logger.info(
            "[play_store] Sync fetch complete: %d raw reviews across %d pages",
            len(all_reviews), page,
        )
        return all_reviews

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_within_window(review: dict, cutoff: datetime) -> bool:
        """Return True if the review's date is within the 4-month window."""
        at = review.get("at")
        if at is None:
            return False  # EC-1.3.07: missing date → drop

        # google-play-scraper returns datetime objects; make UTC-aware
        if isinstance(at, datetime):
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)  # EC-1.2.09
            return at >= cutoff

        # Fallback: try parsing a string
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(str(at))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except Exception:
            logger.warning("[play_store] Could not parse date '%s' — dropping review", at)
            return False
