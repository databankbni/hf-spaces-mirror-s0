"""
trustpilot.py — Trustpilot review fetcher for Spotify.

Scraping strategy (in priority order):
  1. **cloudscraper** (primary): Bypasses Cloudflare's JS challenge and basic
     WAF rules. Uses a real browser fingerprint; works for most Trustpilot pages.
  2. **aiohttp fallback**: Plain HTTP with custom headers — used if cloudscraper
     is not installed. Will likely be blocked (403) by Trustpilot's Cloudflare
     WAF, but retained as a fallback for completeness.
  3. **Manual curated file**: If both HTTP paths fail (or the caller prefers it),
     load reviews from data/raw/trustpilot/curated.json. This file should contain
     *real* reviews hand-copied from Trustpilot, never synthetic data.

Trustpilot review page structure (as of 2026):
  - Pages are server-side rendered with Next.js.
  - Review data is embedded in <script id="__NEXT_DATA__"> as JSON.
  - Each page shows ~20 reviews; paginated via `?page=N`.
  - Reviews are sorted by "Newest" by default.

Edge cases handled:
  - Cloudflare 403 / 503 blocks (switched to cloudscraper).
  - Missing __NEXT_DATA__ (falls back to JSON-LD parsing).
  - Pagination — iterates pages up to TRUSTPILOT_MAX_PAGES.
  - Date filtering — only reviews within the 4-month window are kept.
  - Missing title / author fields — defaults to empty strings.
  - Malformed JSON in embedded data — logged and skipped.
  - Rate limiting — TRUSTPILOT_DELAY_S sleep between pages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingestion.config import (
    RAW_TRUSTPILOT_DIR,
    TRUSTPILOT_DELAY_S,
    TRUSTPILOT_MAX_PAGES,
    get_caps,
    get_cutoff_date,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

_REVIEW_PAGE_URL = "https://www.trustpilot.com/review/www.spotify.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_CURATED_FILES = [
    "curated.json",
    "curated.jsonl",
    "trustpilot_curated.json",
]


class TrustpilotFetcher(BaseFetcher):
    """Fetches Spotify reviews from Trustpilot.

    Primary mode: cloudscraper-based scraping to bypass Cloudflare WAF.
    Fallback mode: loads manually curated reviews from data/raw/trustpilot/.
    """

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).trustpilot

    def source_name(self) -> str:
        return "trustpilot"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch Trustpilot reviews: scrape first, curated file as fallback."""
        logger.info(
            "[trustpilot] Starting fetch (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        cutoff = get_cutoff_date()

        # Step 1: Try cloudscraper (primary — bypasses Cloudflare)
        scraped = await self._fetch_cloudscraper(cutoff)
        if scraped:
            scraped = scraped[: self._cap]
            logger.info("[trustpilot] Done: %d reviews scraped via cloudscraper", len(scraped))
            self.save_raw(scraped, "cloudscraper_records.json")
            return scraped

        # Step 2: Try Playwright (real headless browser — bypasses AWS WAF)
        logger.warning(
            "[trustpilot] Cloudscraper returned no results (blocked by AWS WAF). "
            "Trying Playwright headless browser."
        )
        try:
            from src.ingestion.fetchers.trustpilot_playwright import scrape_with_playwright
            playwright_records = await scrape_with_playwright(cutoff, self._cap)
        except Exception as exc:
            logger.warning("[trustpilot] Playwright scraping failed: %s", exc)
            playwright_records = []

        if playwright_records:
            playwright_records = playwright_records[: self._cap]
            logger.info(
                "[trustpilot] Done: %d reviews scraped via Playwright",
                len(playwright_records),
            )
            # Save the parsed records as raw data for the Extractor
            self.save_raw(playwright_records, "playwright_records.json")
            return playwright_records

        # Step 3: Fall back to curated file
        logger.warning(
            "[trustpilot] Playwright scraping returned no results. "
            "Trying manually curated file."
        )
        curated = self._load_curated(cutoff)
        if curated:
            curated = curated[: self._cap]
            logger.info("[trustpilot] Done: %d reviews from curated file", len(curated))
            return curated

        # Step 4: Nothing available
        logger.warning(
            "[trustpilot] No reviews collected from Trustpilot.\n"
            "Options:\n"
            "  1. Ensure Playwright + Chromium are installed:\n"
            "       python -m pip install playwright\n"
            "       python -m playwright install chromium\n"
            "  2. Manually add REAL reviews to data/raw/trustpilot/curated.json.\n"
            "     (see tests/fixtures/trustpilot/README_TEST_ONLY.md for the schema)\n"
            "  3. Trustpilot may now require a logged-in session — try using\n"
            "     Playwright with stored auth cookies if needed."
        )
        return []

    # ------------------------------------------------------------------ #
    # cloudscraper-based scraping (primary)                               #
    # ------------------------------------------------------------------ #

    async def _fetch_cloudscraper(self, cutoff: datetime) -> list[dict]:
        """Scrape Trustpilot pages using cloudscraper to bypass Cloudflare."""
        try:
            import cloudscraper  # type: ignore
        except ImportError:
            logger.warning(
                "[trustpilot] cloudscraper not installed. "
                "Run: python -m pip install cloudscraper"
            )
            return []

        records: list[dict] = []
        # cloudscraper is synchronous — run in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        records = await loop.run_in_executor(
            None, self._scrape_pages_sync, cloudscraper, cutoff
        )
        return records

    def _scrape_pages_sync(self, cloudscraper_module: Any, cutoff: datetime) -> list[dict]:
        """Synchronous page-scraping loop (runs in a thread pool executor)."""
        import re

        scraper = cloudscraper_module.create_scraper(
            browser={
                "browser": "chrome",
                "platform": "windows",
                "desktop": True,
            }
        )

        records: list[dict] = []
        stopped_early = False

        for page_num in range(1, TRUSTPILOT_MAX_PAGES + 1):
            if len(records) >= self._cap:
                break

            url = f"{_REVIEW_PAGE_URL}?page={page_num}&sort=recency"
            logger.info("[trustpilot] Fetching page %d: %s", page_num, url)

            try:
                resp = scraper.get(url, headers=_HEADERS, timeout=30)
            except Exception as exc:
                logger.error("[trustpilot] Request failed on page %d: %s", page_num, exc)
                break

            if resp.status_code in (403, 503, 429):
                logger.warning(
                    "[trustpilot] HTTP %d on page %d — Cloudflare still blocking. "
                    "Consider adding a longer delay or rotating user agents.",
                    resp.status_code, page_num,
                )
                break

            if resp.status_code != 200:
                logger.warning("[trustpilot] HTTP %d on page %d", resp.status_code, page_num)
                break

            html = resp.text
            logger.debug("[trustpilot] Page %d: %d bytes received", page_num, len(html))

            # Save raw page snapshot for provenance
            raw_filename = f"page_{page_num:03d}.html"
            (RAW_TRUSTPILOT_DIR / raw_filename).write_text(html, encoding="utf-8")

            # Parse embedded Next.js JSON
            page_records, stop = self._parse_next_data(html, cutoff)
            if not page_records and not stop:
                # Try JSON-LD as fallback
                page_records, stop = self._parse_json_ld(html, cutoff)

            records.extend(page_records)
            logger.info(
                "[trustpilot] Page %d: %d records (running total=%d)",
                page_num, len(page_records), len(records),
            )

            if stop:
                logger.info(
                    "[trustpilot] Stopping pagination — all reviews older than cutoff."
                )
                stopped_early = True
                break

            if not page_records:
                logger.info("[trustpilot] Page %d: no records — stopping.", page_num)
                break

            time.sleep(TRUSTPILOT_DELAY_S)

        return records

    # ------------------------------------------------------------------ #
    # HTML parsers                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_next_data(html: str, cutoff: datetime) -> tuple[list[dict], bool]:
        """Extract reviews from Trustpilot's __NEXT_DATA__ JSON blob.

        Returns (records, stop_pagination) where stop_pagination=True means
        all remaining pages would be outside the time window.
        """
        import re

        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        if not match:
            return [], False

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("[trustpilot] __NEXT_DATA__ parse error: %s", exc)
            return [], False

        reviews_raw = (
            data.get("props", {})
                .get("pageProps", {})
                .get("reviews", [])
        )
        if not reviews_raw:
            # Try alternate path
            reviews_raw = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("businessUnit", {})
                    .get("reviews", [])
            )

        records: list[dict] = []
        oldest_in_page: datetime | None = None

        for review in reviews_raw:
            title = review.get("title", "") or ""
            text = review.get("text", "") or ""
            full_text = f"{title}\n\n{text}".strip() if text else title.strip()
            if not full_text:
                continue

            date_str = (
                review.get("dates", {}).get("publishedDate", "")
                or review.get("publishedDate", "")
                or review.get("date", "")
            )
            parsed_date = TrustpilotFetcher._parse_date(date_str)
            dt = TrustpilotFetcher._to_datetime(date_str)

            if dt:
                if oldest_in_page is None or dt < oldest_in_page:
                    oldest_in_page = dt
                if not TrustpilotFetcher._is_within_window(date_str, cutoff):
                    continue  # Skip out-of-window but keep paginating

            rating = review.get("rating")
            try:
                rating = int(rating) if rating is not None else None
            except (ValueError, TypeError):
                rating = None

            consumer = review.get("consumer", {}) or {}
            author = consumer.get("displayName", "") or ""

            records.append({
                "text": full_text,
                "title": title.strip(),
                "rating": rating,
                "date": parsed_date,
                "author": author,
                "url": review.get("reviewUrl", "") or "",
            })

        # If all records on this page predate the cutoff, no need to fetch more pages
        stop = oldest_in_page is not None and oldest_in_page < cutoff and not records

        return records, stop

    @staticmethod
    def _parse_json_ld(html: str, cutoff: datetime) -> tuple[list[dict], bool]:
        """Extract reviews from JSON-LD structured data as a fallback."""
        import re

        records: list[dict] = []
        for match in re.finditer(
            r'<script\s+type="application/ld\+json">(.*?)</script>',
            html, re.DOTALL,
        ):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            if data.get("@type") != "LocalBusiness":
                continue

            for review in data.get("review", []):
                body = review.get("reviewBody", "").strip()
                if not body:
                    continue

                date_str = review.get("datePublished", "")
                if date_str and not TrustpilotFetcher._is_within_window(date_str, cutoff):
                    continue

                rating_val = review.get("reviewRating", {}).get("ratingValue")
                try:
                    rating = int(rating_val) if rating_val is not None else None
                except (ValueError, TypeError):
                    rating = None

                author_info = review.get("author", {})
                author = (
                    author_info.get("name", "")
                    if isinstance(author_info, dict)
                    else str(author_info)
                )

                records.append({
                    "text": body,
                    "title": review.get("name", "").strip(),
                    "rating": rating,
                    "date": TrustpilotFetcher._parse_date(date_str),
                    "author": author,
                    "url": "",
                })

        return records, False

    # ------------------------------------------------------------------ #
    # Curated file loading (fallback)                                     #
    # ------------------------------------------------------------------ #

    def _load_curated(self, cutoff: datetime) -> list[dict]:
        """Load curated Trustpilot reviews from data/raw/trustpilot/."""
        found_files = self._find_curated_files()
        if not found_files:
            return []

        records: list[dict] = []
        for filepath in found_files:
            file_records = self._load_file(filepath, cutoff)
            records.extend(file_records)
            logger.info(
                "[trustpilot] Loaded %d records from %s",
                len(file_records), filepath.name,
            )

        # Reject if all records look like the known synthetic fixture IDs
        if self._looks_synthetic(records):
            logger.warning(
                "[trustpilot] Curated file appears to contain synthetic fixture data "
                "(UUIDs matching test fixture pattern). Rejecting. "
                "Please populate with real Trustpilot reviews."
            )
            return []

        return records

    @staticmethod
    def _looks_synthetic(records: list[dict]) -> bool:
        """Heuristic: if all URLs share the synthetic fixture UUID pattern, reject."""
        if not records:
            return False
        synthetic_prefix = "574e4bc0-c23d-4910-a45c"
        flagged = sum(
            1 for r in records if synthetic_prefix in r.get("url", "")
        )
        return flagged == len(records) and len(records) > 0

    @staticmethod
    def _find_curated_files() -> list[Path]:
        """Find curated JSON files in data/raw/trustpilot/."""
        found: list[Path] = []
        for name in _CURATED_FILES:
            path = RAW_TRUSTPILOT_DIR / name
            if path.exists():
                found.append(path)
        for path in sorted(RAW_TRUSTPILOT_DIR.glob("*.json")):
            if path not in found and path.name != "meta.json":
                found.append(path)
        for path in sorted(RAW_TRUSTPILOT_DIR.glob("*.jsonl")):
            if path not in found:
                found.append(path)
        return found

    def _load_file(self, filepath: Path, cutoff: datetime) -> list[dict]:
        """Load and validate records from a single JSON file."""
        records: list[dict] = []

        try:
            content = filepath.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("[trustpilot] Could not read %s: %s", filepath, exc)
            return []

        if not content or content in ("[]", "{}"):
            return []

        if filepath.suffix == ".jsonl":
            raw_list = self._parse_jsonl(content, filepath)
        else:
            raw_list = self._parse_json(content, filepath)

        for entry in raw_list:
            if not isinstance(entry, dict):
                continue

            text = entry.get("text", "").strip()
            title = entry.get("title", "").strip()
            full_text = f"{title}\n\n{text}".strip() if text else title
            if not full_text:
                continue

            date_str = entry.get("date", "")
            if date_str and not self._is_within_window(date_str, cutoff):
                continue

            rating = entry.get("rating")
            if rating is not None:
                try:
                    rating = int(rating)
                except (ValueError, TypeError):
                    rating = None

            records.append({
                "text": full_text,
                "title": title,
                "rating": rating,
                "date": self._parse_date(date_str),
                "author": entry.get("author", ""),
                "url": entry.get("url", ""),
            })

        return records

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_json(content: str, filepath: Path) -> list[dict]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("[trustpilot] Invalid JSON in %s: %s", filepath, exc)
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    @staticmethod
    def _parse_jsonl(content: str, filepath: Path) -> list[dict]:
        entries: list[dict] = []
        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "[trustpilot] Invalid JSON at %s:%d — %s",
                    filepath.name, line_num, exc,
                )
        return entries

    @staticmethod
    def _parse_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(date_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except Exception:
            return date_str

    @staticmethod
    def _to_datetime(date_str: str) -> datetime | None:
        if not date_str:
            return None
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(date_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    @staticmethod
    def _is_within_window(date_str: str, cutoff: datetime) -> bool:
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(str(date_str))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except Exception:
            return True
