"""
base_fetcher.py — Abstract base class for all source fetchers.

Every concrete fetcher (PlayStoreFetcher, AppStoreFetcher, RedditFetcher)
must inherit from this and implement `fetch()` and `source_name()`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.ingestion.config import RAW_DIR, HTTP_MAX_RETRIES, HTTP_BACKOFF_BASE_S

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Abstract base for all source fetchers.

    Provides:
    - `save_raw()` — serialise a page of raw data to data/raw/{source}/
    - `_with_retry()` — async coroutine wrapper with exponential backoff
    """

    # ------------------------------------------------------------------ #
    # Abstract interface                                                   #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw data from the source.

        Returns a flat list of raw response dicts (one dict per review /
        post / comment as returned by the API, before any normalisation).
        """
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Return the canonical source identifier, e.g. 'play_store'."""
        ...

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    def save_raw(self, data: Any, filename: str) -> Path:
        """Save raw API response data to data/raw/{source}/{filename}.

        Args:
            data: Any JSON-serialisable object (list, dict, …).
            filename: E.g. 'page_1.json' or 'search_spotify_discover.json'.

        Returns:
            Path to the saved file.
        """
        dest_dir = RAW_DIR / self.source_name()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename

        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)

        logger.debug("Saved raw data → %s (%d items)", dest, len(data) if isinstance(data, list) else 1)
        return dest

    async def _with_retry(
        self,
        coro_factory,  # callable returning a coroutine
        label: str = "",
    ) -> Any:
        """Execute a coroutine with exponential backoff on transient errors.

        Retries on aiohttp.ClientError, asyncio.TimeoutError, and
        generic Exception up to HTTP_MAX_RETRIES times.

        Args:
            coro_factory: Zero-arg callable that creates a fresh coroutine.
            label: Human-readable label for log messages.

        Returns:
            The return value of the coroutine on success.

        Raises:
            The last exception if all retries are exhausted.
        """
        import aiohttp

        last_exc: Exception | None = None
        for attempt in range(1, HTTP_MAX_RETRIES + 1):
            try:
                return await coro_factory()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                wait = HTTP_BACKOFF_BASE_S ** attempt
                logger.warning(
                    "[%s] Attempt %d/%d failed (%s: %s). Retrying in %.1f s…",
                    label, attempt, HTTP_MAX_RETRIES,
                    type(exc).__name__, exc, wait,
                )
                await asyncio.sleep(wait)
            except Exception as exc:
                # Non-retryable — re-raise immediately
                logger.error("[%s] Non-retryable error: %s", label, exc)
                raise

        logger.error("[%s] All %d retries exhausted. Last error: %s", label, HTTP_MAX_RETRIES, last_exc)
        raise last_exc  # type: ignore[misc]
