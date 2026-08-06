from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from core.models import Book, Post, Channel, ScheduledPost, SourceMetrics

class IBookRepository(ABC):
    @abstractmethod
    async def is_book_published(self, fingerprint: str) -> bool:
        """Check if the book has already been published to avoid duplicates."""
        pass

    @abstractmethod
    async def is_title_duplicate(self, title: str) -> bool:
        """Check if a book with a highly similar/normalized title already exists in the queue or published list."""
        pass

    @abstractmethod
    async def is_isbn_duplicate(self, isbn: str) -> bool:
        """Check if a book with the same ISBN already exists in the queue or published list."""
        pass

    @abstractmethod
    async def mark_book_published(self, book: Book) -> None:
        """Mark a book as published in the database."""
        pass

    @abstractmethod
    async def add_post_to_queue(self, post: Post) -> str:
        """Add a newly prepared post to the scheduling queue. Returns the queue ID."""
        pass

    @abstractmethod
    async def get_pending_queue(self, limit: int = 56) -> List[Post]:
        """Fetch pending posts from the queue."""
        pass

    @abstractmethod
    async def get_queue_count(self) -> int:
        """Get the count of pending posts in the queue."""
        pass

    @abstractmethod
    async def update_post_status(self, post_id: str, status: str) -> None:
        """Update the status of a post in the queue (e.g. pending, scheduled, failed)."""
        pass

    @abstractmethod
    async def save_scheduled_post(self, scheduled_post: ScheduledPost) -> None:
        """Save information about a scheduled message."""
        pass

    @abstractmethod
    async def get_scheduled_posts(self, channel_id: str) -> List[ScheduledPost]:
        """Get list of posts currently marked as scheduled for a channel in DB."""
        pass

    @abstractmethod
    async def remove_scheduled_posts(self, channel_id: str, msg_ids: List[int]) -> None:
        """Remove scheduled posts from DB if they were sent or cancelled."""
        pass

    @abstractmethod
    async def add_channel(self, channel: Channel) -> None:
        """Add a Telegram channel to the system."""
        pass

    @abstractmethod
    async def get_active_channels(self) -> List[Channel]:
        """Retrieve all active channels configured for publishing."""
        pass

    @abstractmethod
    async def get_ai_cache(self, description_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached AI result if available."""
        pass

    @abstractmethod
    async def set_ai_cache(self, description_hash: str, cache_data: Dict[str, Any]) -> None:
        """Cache an AI result for future use."""
        pass

    @abstractmethod
    async def get_source_metrics(self, source_name: str) -> SourceMetrics:
        """Retrieve success metrics and scores for a specific source scraper."""
        pass

    @abstractmethod
    async def update_source_metrics(self, metrics: SourceMetrics) -> None:
        """Update the success metrics and scores of a scraper."""
        pass

class IAIService(ABC):
    @abstractmethod
    async def process_book(self, title: str, author: str, description: Optional[str]) -> Dict[str, Any]:
        """Process book information using AI to get a summary, hashtags, and category."""
        pass

    async def extract_title_author_from_text(self, text: str, cover_image_path: Optional[str] = None) -> Dict[str, str]:
        """Extract real title and author name in Arabic from text content and optional cover image."""
        return {}

class IBookSource(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Get the identifier name of the source."""
        pass

    @abstractmethod
    async def search_books(self, query: str, limit: int = 10) -> List[Book]:
        """Search and parse books from the source."""
        pass
