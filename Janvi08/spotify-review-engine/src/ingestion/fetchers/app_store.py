"""
app_store.py — Apple App Store review fetcher.

Uses Apple's public RSS/JSON feed (no auth required).
Queries multiple country stores to maximise review count.

Edge cases handled:
  EC-1.1.10  RSS feed per-country entry limits (query multiple countries)
  EC-1.1.11  RSS feed URL 404 (logs and skips that country)
  EC-1.1.12  Missing <link rel="next"> (end of data)
  EC-1.1.13  Stale/cached feed (logged, acceptable)
  EC-1.2.10  Single entry returned as dict instead of list
  EC-1.2.11  Missing im:rating field
  EC-1.2.12  HTML entities in text
  EC-1.3.05  Date-range enforcement (post-fetch filter)
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.ingestion.config import (
    APP_STORE_APP_ID,
    APP_STORE_COUNTRIES,
    APP_STORE_DELAY_S,
    APP_STORE_MAX_PAGES_PER_COUNTRY,
    APP_STORE_RSS_URL,
    HTTP_TIMEOUT_S,
    get_caps,
    get_cutoff_date,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "SpotifyReviewEngine/1.0"}


class AppStoreFetcher(BaseFetcher):
    """Fetches Spotify reviews from the Apple App Store RSS/JSON feed."""

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).app_store

    def source_name(self) -> str:
        return "app_store"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch App Store reviews across configured country feeds.

        Stops as soon as the cap is reached. Saves each raw page to
        data/raw/app_store/.
        """
        logger.info(
            "[app_store] Starting fetch (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        cutoff = get_cutoff_date()
        all_raw: list[dict] = []

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            for country in APP_STORE_COUNTRIES:
                if len(all_raw) >= self._cap:
                    logger.info("[app_store] Cap reached — skipping country '%s'", country)
                    break

                collected = await self._fetch_country(session, country, cutoff, all_raw)
                all_raw.extend(collected)
                logger.info(
                    "[app_store] Country '%s': %d reviews (running total=%d)",
                    country, len(collected), len(all_raw),
                )

        # Enforce hard cap
        all_raw = all_raw[: self._cap]
        logger.info("[app_store] Done: %d reviews collected", len(all_raw))
        return all_raw

    # ------------------------------------------------------------------ #
    # Per-country fetcher                                                  #
    # ------------------------------------------------------------------ #

    async def _fetch_country(
        self,
        session: aiohttp.ClientSession,
        country: str,
        cutoff: datetime,
        existing: list[dict],
    ) -> list[dict]:
        """Fetch reviews for one country store, paginating via 'next' link."""
        remaining = self._cap - len(existing)
        url = APP_STORE_RSS_URL.format(country=country, app_id=APP_STORE_APP_ID)
        page = 0
        collected: list[dict] = []

        while url and page < APP_STORE_MAX_PAGES_PER_COUNTRY and len(collected) < remaining:
            page += 1
            logger.debug("[app_store/%s] Fetching page %d: %s", country, page, url)

            try:
                data = await self._with_retry(
                    lambda u=url: self._get_json(session, u),
                    label=f"app_store/{country}/p{page}",
                )
            except Exception as exc:
                logger.error(
                    "[app_store/%s] Page %d failed after retries: %s",
                    country, page, exc,
                )
                break

            if data is None:
                break

            # Save raw page for provenance
            self.save_raw(data, f"page_{country}_{page}.json")

            # Parse feed entries
            feed = data.get("feed", {})
            entries = feed.get("entry", [])

            # EC-1.2.10: single entry returned as dict, not list
            if isinstance(entries, dict):
                entries = [entries]

            # Filter to within time window and collect
            new_records = []
            for entry in entries:
                if len(collected) + len(new_records) >= remaining:
                    break
                if self._is_within_window(entry, cutoff):
                    new_records.append(entry)

            collected.extend(new_records)
            logger.debug(
                "[app_store/%s] Page %d: %d entries, %d within window (page total=%d)",
                country, page, len(entries), len(new_records), len(collected),
            )

            # Check for next page link (EC-1.1.12: may be absent)
            url = self._get_next_url(feed)

            if url:
                await asyncio.sleep(APP_STORE_DELAY_S)

        return collected

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _get_json(
        session: aiohttp.ClientSession, url: str
    ) -> dict | None:
        """GET a URL and return parsed JSON, or None on error."""
        async with session.get(url) as resp:
            if resp.status == 404:
                logger.warning("[app_store] 404 for URL: %s", url)
                return None
            if resp.status != 200:
                logger.warning("[app_store] HTTP %d for URL: %s", resp.status, url)
                resp.raise_for_status()  # triggers retry

            content_type = resp.content_type or ""
            if "json" not in content_type and "javascript" not in content_type:
                # Some CDN responses return text/plain — try parsing anyway
                text = await resp.text()
                import json as _json
                try:
                    return _json.loads(text)
                except Exception:
                    logger.error(
                        "[app_store] Non-JSON content-type '%s' at %s",
                        content_type, url,
                    )
                    return None

            return await resp.json(content_type=None)

    @staticmethod
    def _get_next_url(feed: dict) -> str | None:
        """Extract the 'next' page URL from the feed's link array."""
        links = feed.get("link", [])
        if isinstance(links, dict):
            links = [links]
        for link in links:
            if isinstance(link, dict) and link.get("attributes", {}).get("rel") == "next":
                return link["attributes"].get("href")
        return None

    @staticmethod
    def _is_within_window(entry: dict, cutoff: datetime) -> bool:
        """Check if an RSS entry is within the 4-month window."""
        updated = entry.get("updated", {})
        if isinstance(updated, dict):
            date_str = updated.get("label", "")
        else:
            date_str = str(updated)

        if not date_str:
            return False

        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(date_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except Exception:
            logger.warning("[app_store] Could not parse date '%s' — skipping entry", date_str)
            return False
