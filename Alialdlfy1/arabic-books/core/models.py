from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

@dataclass
class Book:
    fingerprint: str
    title: str
    author: str
    source: str
    url: str
    size_bytes: int
    checksum: str
    cover_url: Optional[str] = None
    description: Optional[str] = None
    downloaded_path: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.now)
    translator: Optional[str] = None
    verifier: Optional[str] = None
    page_count: Optional[int] = None
    isbn: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        from books.fingerprint import normalize_arabic
        return {
            "fingerprint": self.fingerprint,
            "title": self.title,
            "normalized_title": normalize_arabic(self.title),
            "author": self.author,
            "source": self.source,
            "url": self.url,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "cover_url": self.cover_url,
            "description": self.description,
            "scraped_at": self.scraped_at,
            "translator": self.translator,
            "verifier": self.verifier,
            "page_count": self.page_count,
            "isbn": self.isbn
        }

@dataclass
class Post:
    fingerprint: str
    title: str
    author: str
    description: str
    summary: str
    hashtags: List[str]
    pdf_url: str
    category: str
    cover_url: Optional[str] = None
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, scheduled, failed
    translator: Optional[str] = None
    verifier: Optional[str] = None
    page_count: Optional[int] = None
    isbn: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        from books.fingerprint import normalize_arabic
        return {
            "fingerprint": self.fingerprint,
            "title": self.title,
            "normalized_title": normalize_arabic(self.title),
            "author": self.author,
            "description": self.description,
            "summary": self.summary,
            "hashtags": self.hashtags,
            "pdf_url": self.pdf_url,
            "category": self.category,
            "cover_url": self.cover_url,
            "created_at": self.created_at,
            "status": self.status,
            "translator": self.translator,
            "verifier": self.verifier,
            "page_count": self.page_count,
            "isbn": self.isbn
        }

@dataclass
class Channel:
    id: str
    name: str
    signature: str
    channel_hashtag: str
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "signature": self.signature,
            "channel_hashtag": self.channel_hashtag,
            "enabled": self.enabled
        }

@dataclass
class ScheduledPost:
    id: str  # Format: channelId_msgId
    queue_id: str
    channel_id: str
    scheduled_time: datetime
    telegram_message_id: int
    status: str = "scheduled"  # scheduled, posted, failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "channel_id": self.channel_id,
            "scheduled_time": self.scheduled_time,
            "telegram_message_id": self.telegram_message_id,
            "status": self.status
        }

@dataclass
class SourceMetrics:
    source_name: str
    score: int = 100
    success_rate: float = 100.0
    failure_rate: float = 0.0
    total_scraped: int = 0
    total_failed: int = 0
    blacklisted_until: Optional[datetime] = None

    def is_blacklisted(self) -> bool:
        if self.blacklisted_until and datetime.now() < self.blacklisted_until:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "score": self.score,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "total_scraped": self.total_scraped,
            "total_failed": self.total_failed,
            "blacklisted_until": self.blacklisted_until
        }
