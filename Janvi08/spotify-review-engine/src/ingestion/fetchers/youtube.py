"""
youtube.py — YouTube Comments fetcher.

Uses the YouTube Data API v3 (free tier) to fetch comments from public videos
about Spotify recommendations, Discover Weekly, algorithm, etc.

Requires a free Google Cloud API key (no OAuth user login needed for reading
public comments). Set YOUTUBE_API_KEY in your .env file.

Workflow:
  1. Search YouTube for relevant videos using search.list
  2. For each video, fetch comments using commentThreads.list
  3. Filter comments to the 4-month time window
  4. Save raw API responses for provenance

Edge cases handled:
  - API key missing (graceful skip with warning)
  - Comments disabled on a video (logged, skipped)
  - Empty comment pages (pagination stop)
  - Date parsing for publishedAt (ISO 8601 from API)
  - Rate limiting / quota exceeded (logged)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.ingestion.config import (
    HTTP_TIMEOUT_S,
    YOUTUBE_COMMENTS_PER_VIDEO,
    YOUTUBE_DELAY_S,
    YOUTUBE_MAX_VIDEOS,
    YOUTUBE_SEARCH_QUERIES,
    get_caps,
    get_cutoff_date,
    get_youtube_api_key,
)
from src.ingestion.fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

_YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_YT_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
_YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeFetcher(BaseFetcher):
    """Fetches comments from YouTube videos about Spotify."""

    def __init__(self, mode: str = "smoke") -> None:
        self._mode = mode
        self._cap = get_caps(mode).youtube

    def source_name(self) -> str:
        return "youtube"

    # ------------------------------------------------------------------ #
    # Main fetch                                                           #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[dict[str, Any]]:
        """Search for relevant videos, then fetch their comments."""
        logger.info(
            "[youtube] Starting fetch (mode=%s, cap=%d)",
            self._mode, self._cap,
        )

        try:
            api_key = get_youtube_api_key()
        except RuntimeError as exc:
            logger.error("[youtube] %s", exc)
            logger.warning("[youtube] Skipping YouTube source — no API key.")
            return []

        cutoff = get_cutoff_date()
        all_records: list[dict] = []
        seen_video_ids: set[str] = set()

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 1: Find relevant videos
            videos = await self._search_videos(session, api_key, seen_video_ids)
            logger.info("[youtube] Found %d relevant videos", len(videos))

            # Step 2: Fetch comments from each video
            for video in videos:
                if len(all_records) >= self._cap:
                    break

                video_id = video["video_id"]
                video_title = video["title"]
                remaining = self._cap - len(all_records)

                comments = await self._fetch_comments(
                    session, api_key, video_id, video_title, cutoff,
                    limit=min(YOUTUBE_COMMENTS_PER_VIDEO, remaining),
                )
                all_records.extend(comments)
                logger.info(
                    "[youtube] Video '%s' (%s): %d comments (running total=%d)",
                    video_title[:40], video_id, len(comments), len(all_records),
                )

        all_records = all_records[: self._cap]
        logger.info("[youtube] Done: %d comments collected", len(all_records))
        return all_records

    # ------------------------------------------------------------------ #
    # Video search                                                         #
    # ------------------------------------------------------------------ #

    async def _search_videos(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        seen: set[str],
    ) -> list[dict]:
        """Search YouTube for Spotify-related videos."""
        videos: list[dict] = []

        for query in YOUTUBE_SEARCH_QUERIES:
            if len(videos) >= YOUTUBE_MAX_VIDEOS:
                break

            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "relevance",
                "maxResults": min(5, YOUTUBE_MAX_VIDEOS - len(videos)),
                "key": api_key,
            }

            try:
                data = await self._with_retry(
                    lambda p=params: self._get_json(session, _YT_SEARCH_URL, p),
                    label=f"youtube/search/{query}",
                )
            except Exception as exc:
                logger.error("[youtube] Search failed for '%s': %s", query, exc)
                continue

            if not data:
                continue

            # Save raw search results
            safe_q = query.replace(" ", "_")[:30]
            self.save_raw(data, f"search_{safe_q}.json")

            for item in data.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)

                snippet = item.get("snippet", {})
                videos.append({
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                })

            await asyncio.sleep(YOUTUBE_DELAY_S)

        return videos

    # ------------------------------------------------------------------ #
    # Comment fetching                                                     #
    # ------------------------------------------------------------------ #

    async def _fetch_comments(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        video_id: str,
        video_title: str,
        cutoff: datetime,
        limit: int,
    ) -> list[dict]:
        """Fetch top-level comments for a single video."""
        comments: list[dict] = []
        page_token: str | None = None
        page = 0

        while len(comments) < limit:
            page += 1
            params = {
                "part": "snippet",
                "videoId": video_id,
                "order": "time",
                "maxResults": min(100, limit - len(comments)),
                "key": api_key,
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                data = await self._with_retry(
                    lambda p=params: self._get_json(session, _YT_COMMENTS_URL, p),
                    label=f"youtube/comments/{video_id}/p{page}",
                )
            except Exception as exc:
                # 403 = comments disabled; other errors
                err_str = str(exc)
                if "403" in err_str or "commentsDisabled" in err_str:
                    logger.warning(
                        "[youtube] Comments disabled for video %s", video_id
                    )
                else:
                    logger.error(
                        "[youtube] Comment fetch failed for %s: %s",
                        video_id, exc,
                    )
                break

            if not data:
                break

            # Save raw comments page
            self.save_raw(data, f"comments_{video_id}_p{page}.json")

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if len(comments) >= limit:
                    break

                snippet = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                )
                if not snippet:
                    continue

                # Date filter
                published = snippet.get("publishedAt", "")
                if published and not self._is_within_window(published, cutoff):
                    continue

                text = snippet.get("textOriginal", "") or snippet.get("textDisplay", "")
                if not text or not text.strip():
                    continue

                comment_id = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("id", "")
                )

                comments.append({
                    "comment_id": comment_id,
                    "video_id": video_id,
                    "video_title": video_title,
                    "text": text.strip(),
                    "author": snippet.get("authorDisplayName", ""),
                    "published_at": published,
                    "like_count": snippet.get("likeCount", 0),
                    "permalink": (
                        f"https://www.youtube.com/watch?v={video_id}"
                        f"&lc={comment_id}" if comment_id else
                        f"https://www.youtube.com/watch?v={video_id}"
                    ),
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            await asyncio.sleep(YOUTUBE_DELAY_S)

        return comments

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _get_json(
        session: aiohttp.ClientSession,
        url: str,
        params: dict,
    ) -> dict | None:
        """GET a URL with query params and return parsed JSON."""
        async with session.get(url, params=params) as resp:
            if resp.status == 403:
                body = await resp.text()
                logger.warning("[youtube] 403 Forbidden: %s — %s", url, body[:200])
                # Check if it's comments disabled vs quota exceeded
                if "commentsDisabled" in body:
                    raise Exception("commentsDisabled")
                if "quotaExceeded" in body:
                    raise Exception("quotaExceeded — YouTube API daily limit reached")
                return None
            if resp.status != 200:
                logger.warning("[youtube] HTTP %d: %s", resp.status, url)
                resp.raise_for_status()
            return await resp.json()

    @staticmethod
    def _is_within_window(date_str: str, cutoff: datetime) -> bool:
        """Check if an ISO 8601 date string is within the 4-month window."""
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(date_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except Exception:
            return True  # Keep if unparseable
