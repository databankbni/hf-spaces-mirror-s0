import logging
import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Set, Dict, Any, Optional
from telethon import TelegramClient
from telethon.tl.functions.messages import GetScheduledHistoryRequest
from core.models import Channel, Post, ScheduledPost
from core.interfaces import IBookRepository
import config

logger = logging.getLogger("TELEGRAM")

def format_caption(post: Post, signature: str, channel_hashtag: str) -> str:
    """Formats the post caption with emojis and elegant layout using HTML tags, ensuring it fits under 1024 characters."""
    tags = [f"#{tag}" for tag in post.hashtags]
    if channel_hashtag and channel_hashtag not in post.hashtags:
        # Normalize and add channel hashtag
        c_tag = channel_hashtag.replace("#", "").strip()
        tags.append(f"#{c_tag}")
        
    tags_str = " ".join(tags)
    
    # Check if translator and verifier exist
    translator_line = ""
    if getattr(post, "translator", None):
        translator_line = f"🌐 <b>المترجم:</b> {post.translator}\n"
        
    verifier_line = ""
    if getattr(post, "verifier", None):
        verifier_line = f"🔍 <b>تحقيق/تدقيق:</b> {post.verifier}\n"
        
    # Calculate base caption length (everything except summary)
    base_len = (
        len("📚 <b></b>\n") + len(post.title) +
        len("✍️ <b>الكاتب:</b> \n") + len(post.author) +
        len(translator_line) +
        len(verifier_line) +
        len("🗂 <b>التصنيف:</b> #\n\n") + len(post.category) +
        len("📝 <b>ملخص الكتاب:</b>\n\n\n") +
        len("🔗 <b>هاشتاقات:</b>\n\n\n") + len(tags_str) +
        len(signature)
    )
    
    # Telegram photo caption limit is 1024 characters. 
    # Leave a safety margin to ensure the total post never reaches 1000 characters.
    max_summary_len = 980 - base_len
    
    summary = post.summary
    if len(summary) > max_summary_len:
        summary = summary[:max_summary_len - 3] + "..."
        
    caption = (
        f"📚 <b>{post.title}</b>\n"
        f"✍️ <b>الكاتب:</b> {post.author}\n"
        f"{translator_line}"
        f"{verifier_line}"
        f"🗂 <b>التصنيف:</b> #{post.category}\n\n"
        f"📝 <b>ملخص الكتاب:</b>\n{summary}\n\n"
        f"🔗 <b>هاشتاقات:</b>\n{tags_str}\n\n"
        f"{signature}"
    )
    return caption
    
class TelegramPublisher:
    def __init__(self, repository: IBookRepository):
        self.repo = repository

    async def get_scheduled_times(self, client: TelegramClient, channel_entity: Any) -> List[datetime]:
        """
        Queries Telegram for scheduled messages in a channel and returns their send times in UTC.
        """
        try:
            result = await client(GetScheduledHistoryRequest(
                peer=channel_entity,
                hash=0
            ))
            times = []
            for msg in result.messages:
                times.append(msg.date)
            
            logger.telegram(f"Found {len(times)} scheduled message(s) directly on Telegram servers.")
            return times
        except Exception as e:
            logger.error(f"Failed to fetch scheduled history from Telegram: {e}")
            return []

    async def schedule_book_post(
        self, 
        client: TelegramClient, 
        channel: Channel, 
        post: Post, 
        pdf_local_path: str,
        cover_local_path: Optional[str],
        schedule_time_utc: datetime
    ) -> List[int]:
        """
        Schedules a book post on Telegram:
        1. Schedules the cover image with caption (if cover exists).
        2. Schedules the PDF file immediately after (10 seconds later).
        Returns a list of scheduled message IDs.
        """
        channel_entity = await client.get_entity(channel.id)
        caption = format_caption(post, channel.signature, channel.channel_hashtag)
        
        scheduled_ids = []
        naive_schedule_time = schedule_time_utc.replace(tzinfo=None)

        if config.DRY_RUN:
            logger.success(f"[DRY RUN] Would schedule '{post.title}' to channel {channel.name} at {naive_schedule_time} UTC.")
            logger.info(f"[DRY RUN] Caption:\n{caption}")
            return [999991, 999992]

        try:
            if cover_local_path and os.path.exists(cover_local_path):
                logger.telegram(f"Scheduling cover photo for '{post.title}' at {naive_schedule_time}...")
                cover_msg = await client.send_file(
                    channel_entity,
                    file=cover_local_path,
                    caption=caption,
                    parse_mode="html",
                    schedule=naive_schedule_time
                )
                scheduled_ids.append(cover_msg.id)
                logger.telegram(f"Cover photo scheduled. Telegram Message ID: {cover_msg.id}")
                
                # Upload and rename PDF to match book title
                clean_title = "".join(c for c in post.title if c not in r'\/:*?"<>|').strip()
                if not clean_title.lower().endswith(".pdf"):
                    clean_title = f"{clean_title}.pdf"
                logger.telegram(f"Uploading and renaming PDF to '{clean_title}'...")
                uploaded_pdf = await client.upload_file(pdf_local_path, file_name=clean_title)
                
                # Schedule PDF 10 seconds later
                pdf_schedule_time = naive_schedule_time + timedelta(seconds=10)
                logger.telegram(f"Scheduling PDF document for '{post.title}' at {pdf_schedule_time}...")
                pdf_msg = await client.send_file(
                    channel_entity,
                    file=uploaded_pdf,
                    caption=f"📁 ملف PDF للكتاب: <b>{post.title}</b>",
                    parse_mode="html",
                    schedule=pdf_schedule_time
                )
                scheduled_ids.append(pdf_msg.id)
                logger.telegram(f"PDF scheduled. Telegram Message ID: {pdf_msg.id}")
                
            else:
                # Upload and rename PDF to match book title
                clean_title = "".join(c for c in post.title if c not in r'\/:*?"<>|').strip()
                if not clean_title.lower().endswith(".pdf"):
                    clean_title = f"{clean_title}.pdf"
                logger.telegram(f"Uploading and renaming PDF to '{clean_title}'...")
                uploaded_pdf = await client.upload_file(pdf_local_path, file_name=clean_title)
                
                logger.telegram(f"No cover available. Scheduling PDF with full caption at {naive_schedule_time}...")
                pdf_msg = await client.send_file(
                    channel_entity,
                    file=uploaded_pdf,
                    caption=caption,
                    parse_mode="html",
                    schedule=naive_schedule_time
                )
                scheduled_ids.append(pdf_msg.id)
                logger.telegram(f"PDF scheduled with full caption. Telegram Message ID: {pdf_msg.id}")
                
            return scheduled_ids
            
        except Exception as e:
            logger.error(f"Failed to schedule book '{post.title}' on channel {channel.name}: {e}")
            raise
