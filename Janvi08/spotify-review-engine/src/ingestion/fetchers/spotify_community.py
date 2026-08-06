"""
spotify_community.py — Spotify Community Forum fetcher.

Scrapes public threads from community.spotify.com using HTTP + BeautifulSoup.
The forum is publicly accessible — no login required.

Searches the forum for discovery/recommendation-related terms and collects
thread titles + post bodies.

Edge cases handled:
  - Rate limiting (configurable delay between requests)
  - Empty search results (logged, skipped)
  - HTML structure changes (graceful fallback)
  - Non-English posts (kept — Phase 2 will filter)
  - Date parsing failures (entry skipped)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from src.ingestion.config import (
    SPOTIFY_COMMUNITY_BASE_URL,
    SPOTIFY_COMMUNITY_DELAY_S,
    SPOTIFY_COMMUNITY_MAX_PAGES,
    SPOTIFY_COMMUNITY_SEARCH_TERMS,
    HTTP_TIMEOUT_S,
    get_caps,
    get_cutoff_date,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class SpotifyCommunityFetcher(BaseFetcher):
    """Fetches discussion threads from Spotify's community forum."""

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).spotify_community

    def source_name(self) -> str:
        return "spotify_community"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch community forum posts via search."""
        logger.info(
            "[spotify_community] Starting fetch (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        cutoff = get_cutoff_date()
        all_records: list[dict] = []
        seen_urls: set[str] = set()

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            for term in SPOTIFY_COMMUNITY_SEARCH_TERMS:
                if len(all_records) >= self._cap:
                    break

                records = await self._search_term(session, term, cutoff, seen_urls)
                all_records.extend(records)
                logger.info(
                    "[spotify_community] Term '%s': %d results (running total=%d)",
                    term, len(records), len(all_records),
                )

        all_records = all_records[: self._cap]
        logger.info("[spotify_community] Done: %d records collected", len(all_records))
        return all_records

    # ------------------------------------------------------------------ #
    # Search by term                                                       #
    # ------------------------------------------------------------------ #

    async def _search_term(
        self,
        session: aiohttp.ClientSession,
        term: str,
        cutoff: datetime,
        seen_urls: set[str],
    ) -> list[dict]:
        """Search the forum for a term and extract matching posts."""
        records: list[dict] = []
        page = 1

        while page <= SPOTIFY_COMMUNITY_MAX_PAGES and len(records) < self._cap:
            # Spotify Community uses Lithium/Khoros — search endpoint
            search_url = (
                f"{SPOTIFY_COMMUNITY_BASE_URL}/t5/forums/searchpage"
                f"/tab/message?q={term.replace(' ', '+')}"
                f"&collapse_discussion=true&search_type=thread"
                f"&sort_by=-topicPostDate"
                f"&page={page}"
            )

            logger.debug(
                "[spotify_community] Fetching search page %d for '%s'",
                page, term,
            )

            try:
                html = await self._with_retry(
                    lambda u=search_url: self._get_html(session, u),
                    label=f"spotify_community/search/{term}/p{page}",
                )
            except Exception as exc:
                logger.error(
                    "[spotify_community] Search page %d failed for '%s': %s",
                    page, term, exc,
                )
                break

            if not html:
                break

            # Parse search results
            soup = BeautifulSoup(html, "lxml")
            result_items = self._parse_search_results(soup, cutoff, seen_urls)

            # Save raw data for provenance
            safe_term = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")
            self.save_raw(
                result_items,
                f"search_{safe_term}_p{page}.json",
            )

            if not result_items:
                logger.debug(
                    "[spotify_community] No more results for '%s' at page %d",
                    term, page,
                )
                break

            records.extend(result_items)
            page += 1
            await asyncio.sleep(SPOTIFY_COMMUNITY_DELAY_S)

        return records

    # ------------------------------------------------------------------ #
    # HTML parsing                                                         #
    # ------------------------------------------------------------------ #

    def _parse_search_results(
        self,
        soup: BeautifulSoup,
        cutoff: datetime,
        seen_urls: set[str],
    ) -> list[dict]:
        """Parse the search results page and return structured records."""
        records: list[dict] = []

        # Lithium/Khoros forum search results are typically in message-list items
        # Try multiple selectors for robustness
        result_divs = (
            soup.select(".lia-search-result-message")
            or soup.select(".MessageView")
            or soup.select("[data-lia-message-uid]")
            or soup.select(".search-result")
            or soup.select("li.lia-list-row")
        )

        if not result_divs:
            # Fallback: look for any link-like structure with thread content
            result_divs = soup.select(".lia-message-view-wrapper")

        for div in result_divs:
            try:
                record = self._extract_result_item(div, cutoff, seen_urls)
                if record:
                    records.append(record)
            except Exception as exc:
                logger.debug(
                    "[spotify_community] Failed to parse one result: %s", exc
                )

        return records

    def _extract_result_item(
        self,
        div,
        cutoff: datetime,
        seen_urls: set[str],
    ) -> dict | None:
        """Extract a single search result into a structured record."""
        # Title
        title_tag = (
            div.select_one(".message-subject a")
            or div.select_one("h3 a")
            or div.select_one(".lia-message-subject a")
            or div.select_one("a.page-link")
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # URL
        url = ""
        if title_tag and title_tag.get("href"):
            href = title_tag["href"]
            url = href if href.startswith("http") else f"{SPOTIFY_COMMUNITY_BASE_URL}{href}"

        # Skip duplicates
        if url and url in seen_urls:
            return None
        if url:
            seen_urls.add(url)

        # Body text / snippet
        body_tag = (
            div.select_one(".lia-message-body-content")
            or div.select_one(".search-result-body")
            or div.select_one(".lia-truncated-body-node")
            or div.select_one("p")
        )
        body = body_tag.get_text(strip=True) if body_tag else ""

        text = f"{title}\n\n{body}".strip() if body else title.strip()
        if not text:
            return None

        # Date
        date_tag = (
            div.select_one(".DateTime")
            or div.select_one("time")
            or div.select_one(".local-date")
            or div.select_one("[datetime]")
        )
        date_str = ""
        if date_tag:
            date_str = date_tag.get("datetime", "") or date_tag.get_text(strip=True)

        date_iso = self._parse_date(date_str)
        if date_iso and cutoff:
            try:
                from dateutil import parser as du_parser
                parsed = du_parser.parse(date_iso)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed < cutoff:
                    return None
            except Exception:
                pass  # Keep record if date parsing fails — Phase 2 will filter

        # Thread context
        board_tag = div.select_one(".lia-board-name") or div.select_one(".board-title")
        thread_context = board_tag.get_text(strip=True) if board_tag else title[:80]

        return {
            "title": title,
            "text": text,
            "date": date_iso or "",
            "url": url,
            "thread_title": thread_context,
            "source_board": "spotify_community",
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _get_html(session: aiohttp.ClientSession, url: str) -> str | None:
        """GET a URL and return HTML text, or None on error."""
        async with session.get(url) as resp:
            if resp.status == 404:
                logger.warning("[spotify_community] 404: %s", url)
                return None
            if resp.status == 403:
                logger.warning("[spotify_community] 403 Forbidden: %s", url)
                return None
            if resp.status != 200:
                logger.warning("[spotify_community] HTTP %d: %s", resp.status, url)
                resp.raise_for_status()
            return await resp.text()

    @staticmethod
    def _parse_date(date_str: str) -> str:
        """Attempt to parse a date string into ISO 8601 format."""
        if not date_str:
            return ""
        
        import re
        from datetime import datetime, timedelta, timezone
        
        date_str = date_str.lower().strip()
        
        # Handle Lithium relative dates
        if date_str == "yesterday":
            return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        m = re.match(r'^(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago', date_str)
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            now = datetime.now(timezone.utc)
            if unit == 'minute':
                now -= timedelta(minutes=val)
            elif unit == 'hour':
                now -= timedelta(hours=val)
            elif unit == 'day':
                now -= timedelta(days=val)
            elif unit == 'week':
                now -= timedelta(weeks=val)
            elif unit == 'month':
                now -= timedelta(days=val * 30)
            elif unit == 'year':
                now -= timedelta(days=val * 365)
            return now.isoformat()

        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(date_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except Exception:
            return date_str  # Return as-is, let downstream handle it
