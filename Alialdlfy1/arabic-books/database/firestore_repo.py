import logging
from typing import List, Optional, Dict, Any
from google.cloud import firestore
from core.interfaces import IBookRepository
from core.models import Book, Post, Channel, ScheduledPost, SourceMetrics
from database.connection import get_firestore_client

logger = logging.getLogger("DATABASE")

class FirestoreBookRepository(IBookRepository):
    def __init__(self):
        self.db = get_firestore_client()

    async def is_book_published(self, fingerprint: str) -> bool:
        try:
            doc_ref = self.db.collection("published_books").document(fingerprint)
            doc = await doc_ref.get()
            return doc.exists
        except Exception as e:
            logger.error(f"Error checking if book is published: {e}")
            return False

    async def is_title_duplicate(self, title: str) -> bool:
        try:
            from books.fingerprint import normalize_arabic
            norm_title = normalize_arabic(title)
            if not norm_title:
                return False
                
            # Check published_books
            query_pub = self.db.collection("published_books").where("normalized_title", "==", norm_title).limit(1)
            docs_pub = await query_pub.get()
            if len(docs_pub) > 0:
                return True
                
            # Check queue
            query_q = self.db.collection("queue").where("normalized_title", "==", norm_title).limit(1)
            docs_q = await query_q.get()
            if len(docs_q) > 0:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking duplicate title: {e}")
            return False

    async def is_isbn_duplicate(self, isbn: str) -> bool:
        try:
            if not isbn:
                return False
                
            # Check published_books
            query_pub = self.db.collection("published_books").where("isbn", "==", isbn).limit(1)
            docs_pub = await query_pub.get()
            if len(docs_pub) > 0:
                return True
                
            # Check queue
            query_q = self.db.collection("queue").where("isbn", "==", isbn).limit(1)
            docs_q = await query_q.get()
            if len(docs_q) > 0:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking duplicate ISBN: {e}")
            return False

    async def mark_book_published(self, book: Book) -> None:
        try:
            doc_ref = self.db.collection("published_books").document(book.fingerprint)
            await doc_ref.set(book.to_dict())
            logger.database(f"Book '{book.title}' marked as published.")
        except Exception as e:
            logger.error(f"Error marking book as published: {e}")

    async def add_post_to_queue(self, post: Post) -> str:
        try:
            doc_ref = self.db.collection("queue").document()
            await doc_ref.set(post.to_dict())
            logger.database(f"Post for '{post.title}' added to queue with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error adding post to queue: {e}")
            raise

    async def get_pending_queue(self, limit: int = 56) -> List[Post]:
        try:
            query = (
                self.db.collection("queue")
                .where("status", "==", "pending")
                .limit(limit)
            )
            posts = []
            async for doc in query.stream():
                data = doc.to_dict()
                posts.append(
                    Post(
                        id=doc.id,
                        fingerprint=data["fingerprint"],
                        title=data["title"],
                        author=data["author"],
                        description=data["description"],
                        summary=data["summary"],
                        hashtags=data["hashtags"],
                        pdf_url=data["pdf_url"],
                        category=data["category"],
                        cover_url=data.get("cover_url"),
                        created_at=data["created_at"],
                        status=data["status"],
                        translator=data.get("translator"),
                        verifier=data.get("verifier"),
                        page_count=data.get("page_count"),
                        isbn=data.get("isbn"),
                    )
                )
            # Sort locally in Python to avoid Firestore composite index requirement
            posts.sort(key=lambda x: x.created_at)
            return posts
        except Exception as e:
            logger.error(f"Error fetching pending queue: {e}")
            return []

    async def get_queue_count(self) -> int:
        try:
            # Optimize counting using aggregate count query if supported
            query = self.db.collection("queue").where("status", "==", "pending")
            alias = "pending_count"
            aggregate_query = query.count(alias=alias)
            results = await aggregate_query.get()
            return results[0][0].value
        except Exception as e:
            logger.warning(f"Aggregate count failed, falling back to manual stream count: {e}")
            count = 0
            try:
                query = self.db.collection("queue").where("status", "==", "pending")
                async for _ in query.stream():
                    count += 1
                return count
            except Exception as ex:
                logger.error(f"Failed manual queue count: {ex}")
                return 0

    async def update_post_status(self, post_id: str, status: str) -> None:
        try:
            from datetime import datetime, timezone
            doc_ref = self.db.collection("queue").document(post_id)
            updates = {"status": status}
            if status == "posted":
                updates["posted_at"] = datetime.now(timezone.utc)
            await doc_ref.update(updates)
            logger.database(f"Post {post_id} status updated to: {status}")
        except Exception as e:
            logger.error(f"Error updating post status: {e}")

    async def save_scheduled_post(self, scheduled_post: ScheduledPost) -> None:
        try:
            doc_ref = self.db.collection("scheduled_posts").document(scheduled_post.id)
            await doc_ref.set(scheduled_post.to_dict())
            logger.database(f"Scheduled post saved: {scheduled_post.id}")
        except Exception as e:
            logger.error(f"Error saving scheduled post: {e}")

    async def get_scheduled_posts(self, channel_id: str) -> List[ScheduledPost]:
        try:
            query = (
                self.db.collection("scheduled_posts")
                .where("channel_id", "==", channel_id)
                .where("status", "==", "scheduled")
            )
            posts = []
            async for doc in query.stream():
                data = doc.to_dict()
                posts.append(
                    ScheduledPost(
                        id=doc.id,
                        queue_id=data["queue_id"],
                        channel_id=data["channel_id"],
                        scheduled_time=data["scheduled_time"],
                        telegram_message_id=data["telegram_message_id"],
                        status=data["status"],
                    )
                )
            return posts
        except Exception as e:
            logger.error(f"Error fetching scheduled posts: {e}")
            return []

    async def remove_scheduled_posts(self, channel_id: str, msg_ids: List[int]) -> None:
        try:
            batch = self.db.batch()
            for msg_id in msg_ids:
                doc_id = f"{channel_id}_{msg_id}"
                doc_ref = self.db.collection("scheduled_posts").document(doc_id)
                batch.delete(doc_ref)
            await batch.commit()
            logger.database(f"Deleted {len(msg_ids)} scheduled posts from database.")
        except Exception as e:
            logger.error(f"Error deleting scheduled posts: {e}")

    async def add_channel(self, channel: Channel) -> None:
        try:
            doc_ref = self.db.collection("channels").document(channel.id)
            await doc_ref.set(channel.to_dict())
            logger.database(f"Channel '{channel.name}' added/updated in DB.")
        except Exception as e:
            logger.error(f"Error adding channel: {e}")

    async def get_active_channels(self) -> List[Channel]:
        try:
            query = self.db.collection("channels").where("enabled", "==", True)
            channels = []
            async for doc in query.stream():
                data = doc.to_dict()
                channels.append(
                    Channel(
                        id=doc.id,
                        name=data["name"],
                        signature=data["signature"],
                        channel_hashtag=data["channel_hashtag"],
                        enabled=data["enabled"],
                    )
                )
            return channels
        except Exception as e:
            logger.error(f"Error fetching active channels: {e}")
            return []

    async def get_ai_cache(self, description_hash: str) -> Optional[Dict[str, Any]]:
        try:
            doc_ref = self.db.collection("ai_cache").document(description_hash)
            doc = await doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting AI cache: {e}")
            return None

    async def set_ai_cache(self, description_hash: str, cache_data: Dict[str, Any]) -> None:
        try:
            doc_ref = self.db.collection("ai_cache").document(description_hash)
            await doc_ref.set(cache_data)
        except Exception as e:
            logger.error(f"Error setting AI cache: {e}")

    async def get_source_metrics(self, source_name: str) -> SourceMetrics:
        try:
            doc_ref = self.db.collection("sources").document(source_name)
            doc = await doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return SourceMetrics(
                    source_name=source_name,
                    score=data.get("score", 100),
                    success_rate=data.get("success_rate", 100.0),
                    failure_rate=data.get("failure_rate", 0.0),
                    total_scraped=data.get("total_scraped", 0),
                    total_failed=data.get("total_failed", 0),
                    blacklisted_until=data.get("blacklisted_until"),
                )
            return SourceMetrics(source_name=source_name)
        except Exception as e:
            logger.error(f"Error getting source metrics for {source_name}: {e}")
            return SourceMetrics(source_name=source_name)

    async def update_source_metrics(self, metrics: SourceMetrics) -> None:
        try:
            doc_ref = self.db.collection("sources").document(metrics.source_name)
            await doc_ref.set(metrics.to_dict())
        except Exception as e:
            logger.error(f"Error updating source metrics for {metrics.source_name}: {e}")

    async def get_system_setting(self, key: str, default: Any = None) -> Any:
        try:
            doc_ref = self.db.collection("settings").document("system")
            doc = await doc_ref.get()
            if doc.exists:
                return doc.to_dict().get(key, default)
            return default
        except Exception as e:
            logger.error(f"Error reading system setting {key}: {e}")
            return default

    async def set_system_setting(self, key: str, value: Any) -> None:
        try:
            doc_ref = self.db.collection("settings").document("system")
            await doc_ref.set({key: value}, merge=True)
            logger.database(f"System setting {key} updated to: {value}")
        except Exception as e:
            logger.error(f"Error saving system setting {key}: {e}")
