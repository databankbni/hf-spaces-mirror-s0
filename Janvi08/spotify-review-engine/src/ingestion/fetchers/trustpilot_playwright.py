"""
trustpilot_playwright.py — Playwright-based Trustpilot scraper.

Used when cloudscraper cannot bypass the WAF (e.g. AWS WAF with JS challenge).
Playwright drives a real headless Chromium browser, so WAF challenges are solved
automatically just like a human visitor would.

Requires:
    python -m pip install playwright
    python -m playwright install chromium

Usage (called from TrustpilotFetcher when cloudscraper returns 403):
    records = await scrape_with_playwright(cutoff, cap, max_pages)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingestion.config import (
    RAW_TRUSTPILOT_DIR,
    TRUSTPILOT_DELAY_S,
    TRUSTPILOT_MAX_PAGES,
)

logger = logging.getLogger(__name__)

_REVIEW_PAGE_URL = "https://www.trustpilot.com/review/www.spotify.com"


async def scrape_with_playwright(
    cutoff: datetime,
    cap: int,
    max_pages: int = TRUSTPILOT_MAX_PAGES,
) -> list[dict[str, Any]]:
    """
    Scrape Trustpilot reviews using Playwright (real headless Chromium).

    Args:
        cutoff: Only include reviews published after this UTC datetime.
        cap: Maximum number of records to return.
        max_pages: Safety limit on pagination.

    Returns:
        List of review dicts with keys: text, title, rating, date, author, url.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error(
            "[trustpilot/playwright] Playwright not installed. "
            "Run: python -m pip install playwright && python -m playwright install chromium"
        )
        return []

    records: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
        )

        # Remove automation indicators
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        try:
            for page_num in range(1, max_pages + 1):
                if len(records) >= cap:
                    break

                url = f"{_REVIEW_PAGE_URL}?page={page_num}&sort=recency"
                logger.info("[trustpilot/playwright] Loading page %d: %s", page_num, url)

                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:
                    logger.error(
                        "[trustpilot/playwright] Navigation failed page %d: %s",
                        page_num, exc,
                    )
                    break

                http_status = response.status if response else 0
                logger.info(
                    "[trustpilot/playwright] HTTP %d on page %d — waiting for JS render",
                    http_status, page_num,
                )

                # NOTE: Trustpilot returns HTTP 403 as the *initial* status, but
                # the AWS WAF JS challenge resolves in-browser and renders the full
                # page. We must wait for the review cards to appear in the DOM
                # before concluding success or failure.
                try:
                    await page.wait_for_selector(
                        '[data-service-review-card-paper]',
                        timeout=20_000,
                    )
                    logger.info(
                        "[trustpilot/playwright] Review cards visible on page %d",
                        page_num,
                    )
                except Exception:
                    logger.warning(
                        "[trustpilot/playwright] Review cards not found on page %d "
                        "after 20s — WAF may still be blocking.",
                        page_num,
                    )
                    # If we never got a 200 and reviews aren't there, give up
                    if http_status not in (200, 304):
                        break

                html = await page.content()

                # Save HTML snapshot for provenance
                snap_path = RAW_TRUSTPILOT_DIR / f"page_{page_num:03d}_playwright.html"
                snap_path.write_text(html, encoding="utf-8")

                # Extract from __NEXT_DATA__
                page_records, stop = _parse_next_data(html, cutoff)
                if not page_records and not stop:
                    page_records, stop = _parse_json_ld(html, cutoff)

                records.extend(page_records)
                logger.info(
                    "[trustpilot/playwright] Page %d: %d records (total=%d)",
                    page_num, len(page_records), len(records),
                )

                if stop or not page_records:
                    break

                await asyncio.sleep(TRUSTPILOT_DELAY_S + 1.0)  # extra delay for politeness

        finally:
            await browser.close()

    return records[:cap]


# ------------------------------------------------------------------ #
# Parsing helpers (shared with trustpilot.py)                         #
# ------------------------------------------------------------------ #

def _parse_next_data(html: str, cutoff: datetime) -> tuple[list[dict], bool]:
    match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not match:
        return [], False

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return [], False

    reviews_raw = (
        data.get("props", {}).get("pageProps", {}).get("reviews", [])
        or data.get("props", {}).get("pageProps", {}).get("businessUnit", {}).get("reviews", [])
    )

    records: list[dict] = []
    oldest: datetime | None = None

    for review in reviews_raw:
        title = (review.get("title", "") or "").strip()
        text = (review.get("text", "") or "").strip()
        full = f"{title}\n\n{text}".strip() if text else title
        if not full:
            continue

        date_str = (
            review.get("dates", {}).get("publishedDate", "")
            or review.get("publishedDate", "")
            or review.get("date", "")
        )
        dt = _to_dt(date_str)
        if dt:
            if oldest is None or dt < oldest:
                oldest = dt
            if dt < cutoff:
                continue

        rating = review.get("rating")
        try:
            rating = int(rating) if rating is not None else None
        except (ValueError, TypeError):
            rating = None

        consumer = review.get("consumer", {}) or {}
        records.append({
            "text": full,
            "title": title,
            "rating": rating,
            "date": _fmt_date(date_str),
            "author": consumer.get("displayName", "") or "",
            "url": review.get("reviewUrl", "") or "",
        })

    stop = oldest is not None and oldest < cutoff and not records
    return records, stop


def _parse_json_ld(html: str, cutoff: datetime) -> tuple[list[dict], bool]:
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
            body = (review.get("reviewBody", "") or "").strip()
            if not body:
                continue
            date_str = review.get("datePublished", "")
            dt = _to_dt(date_str)
            if dt and dt < cutoff:
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
                "title": (review.get("name", "") or "").strip(),
                "rating": rating,
                "date": _fmt_date(date_str),
                "author": author,
                "url": "",
            })
    return records, False


def _to_dt(date_str: str) -> datetime | None:
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


def _fmt_date(date_str: str) -> str:
    dt = _to_dt(date_str)
    return dt.isoformat() if dt else date_str
