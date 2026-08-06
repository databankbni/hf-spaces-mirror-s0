import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from core.interfaces import IBookSource, IBookRepository
from core.models import Book, SourceMetrics
from sources.archive import ArchiveOrgSource
from sources.hindawi import HindawiSource
from sources.openlibrary import OpenLibrarySource
import config

logger = logging.getLogger("BOOK")

class SourcesManager:
    def __init__(self, repository: IBookRepository):
        self.repo = repository
        self.sources: Dict[str, IBookSource] = {
            "archive": ArchiveOrgSource(),
            "hindawi": HindawiSource(),
            "openlibrary": OpenLibrarySource()
        }
        # Independent rate limiter delays per source (in seconds)
        self.rate_limits: Dict[str, float] = {
            "archive": 1.5,
            "hindawi": 3.0,     # Hindawi scraping is heavier, be gentler
            "openlibrary": 2.0
        }

    async def get_ranked_sources(self) -> List[IBookSource]:
        """
        Retrieves active, non-blacklisted sources sorted by their score (descending).
        """
        ranked_sources = []
        now = datetime.now(timezone.utc)

        for name, source in self.sources.items():
            metrics = await self.repo.get_source_metrics(name)
            
            # Check if blacklisted (only if score is below threshold)
            if metrics.score < config.SOURCE_BLACKLIST_THRESHOLD and metrics.blacklisted_until and now < metrics.blacklisted_until:
                logger.warning(
                    f"Source '{name}' is currently blacklisted until {metrics.blacklisted_until}. Skipping."
                )
                continue
                
            ranked_sources.append((source, metrics.score))
            
        # Sort by score descending
        ranked_sources.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in ranked_sources]

    async def search_all(self, query: str, limit_per_source: int = 10) -> List[Book]:
        """
        Searches all active sources in order of their score.
        Respects rate-limit delays.
        """
        active_sources = await self.get_ranked_sources()
        all_books: List[Book] = []

        if not active_sources:
            logger.error("No active book sources available (all blacklisted or disabled).")
            return []

        for source in active_sources:
            name = source.get_name()
            
            # 1. Enforce rate-limit delay
            delay = self.rate_limits.get(name, 1.0)
            logger.book(f"Rate limiter: Sleeping {delay}s before calling source '{name}'...")
            await asyncio.sleep(delay)

            try:
                # 2. Search books
                books = await source.search_books(query, limit=limit_per_source)
                
                if books:
                    all_books.extend(books)
                    # Report search success to improve score slightly
                    await self.report_success(name)
                else:
                    logger.book(f"Source '{name}' returned 0 books for query '{query}'.")
                    
            except Exception as e:
                logger.error(f"Failed to query source '{name}': {e}")
                await self.report_failure(name, "network_error")

        return all_books

    async def report_success(self, source_name: str):
        """
        Increases quality score and updates success rates.
        """
        metrics = await self.repo.get_source_metrics(source_name)
        metrics.total_scraped += 1
        
        # Increase score up to 100
        metrics.score = min(100, metrics.score + config.SOURCE_SUCCESS_REWARD)
        
        # Recalculate success rate
        total = metrics.total_scraped + metrics.total_failed
        if total > 0:
            metrics.success_rate = (metrics.total_scraped / total) * 100.0
            metrics.failure_rate = 100.0 - metrics.success_rate
            
        await self.repo.update_source_metrics(metrics)
        logger.database(f"Source '{source_name}' success reported. New score: {metrics.score}")

    async def report_failure(self, source_name: str, error_type: str):
        """
        Decreases quality score and blacklists source if score falls below threshold.
        """
        metrics = await self.repo.get_source_metrics(source_name)
        metrics.total_failed += 1
        
        # Apply penalty depending on failure type
        penalty = config.SOURCE_NETWORK_ERROR_PENALTY
        if error_type == "invalid_file":
            penalty = config.SOURCE_INVALID_FILE_PENALTY
            
        metrics.score = max(0, metrics.score - penalty)
        
        # Recalculate rates
        total = metrics.total_scraped + metrics.total_failed
        if total > 0:
            metrics.success_rate = (metrics.total_scraped / total) * 100.0
            metrics.failure_rate = 100.0 - metrics.success_rate

        # Check for blacklist
        if metrics.score < config.SOURCE_BLACKLIST_THRESHOLD:
            blacklist_duration = timedelta(hours=config.SOURCE_BLACKLIST_DURATION_HOURS)
            metrics.blacklisted_until = datetime.now(timezone.utc) + blacklist_duration
            logger.error(
                f"Source '{source_name}' score ({metrics.score}) fell below threshold ({config.SOURCE_BLACKLIST_THRESHOLD}). "
                f"Blacklisting for {config.SOURCE_BLACKLIST_DURATION_HOURS} hours."
            )
        else:
            logger.warning(f"Source '{source_name}' failure reported. New score: {metrics.score}")
            
        await self.repo.update_source_metrics(metrics)
