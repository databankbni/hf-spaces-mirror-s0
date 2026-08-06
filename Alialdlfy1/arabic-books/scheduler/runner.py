import logging
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import List, Set
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.interfaces import IBookRepository
from core.models import Channel, Post, ScheduledPost
from telegram.client_manager import client_manager
from telegram.publisher import TelegramPublisher
from book_queue.manager import QueueManager
from monitoring.logger import rotate_and_clean_logs
from books.downloader import download_pdf
from books.validator import extract_cover
import config

logger = logging.getLogger("SYSTEM")

class SystemScheduler:
    def __init__(self, repository: IBookRepository, queue_manager: QueueManager, publisher: TelegramPublisher):
        self.repo = repository
        self.queue_manager = queue_manager
        self.publisher = publisher
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.replenish_lock = asyncio.Lock()
        self._startup_tasks = set()

    async def start(self):
        """Starts the background scheduler jobs."""
        if self.is_running:
            return
            
        logger.system("Starting system background scheduler...")
        
        # 1. Run initial synchronization and queue check immediately (with strong references to prevent GC)
        t1 = asyncio.create_task(self.sync_and_schedule_posts(is_startup=True))
        self._startup_tasks.add(t1)
        t1.add_done_callback(self._startup_tasks.discard)
        
        t2 = asyncio.create_task(self.check_and_replenish_queue())
        self._startup_tasks.add(t2)
        t2.add_done_callback(self._startup_tasks.discard)
        
        # 2. Schedule recurring jobs
        # Sync Telegram scheduled queues every 1 hour
        self.scheduler.add_job(self.sync_and_schedule_posts, "interval", hours=1, name="sync_posts")
        # Check and replenish queue every 4 days
        self.scheduler.add_job(self.check_and_replenish_queue, "interval", days=4, name="replenish_queue")
        # Rotates and cleans log files daily
        self.scheduler.add_job(self.run_log_maintenance, "interval", days=1, name="log_maintenance")
        
        # 3. Schedule instant posting cron for Bot clients
        # Translate local SCHEDULE_HOURS to UTC
        utc_hours = [str((h - config.UTC_OFFSET_HOURS) % 24) for h in config.SCHEDULE_HOURS]
        utc_hours_str = ",".join(utc_hours)
        self.scheduler.add_job(
            self.post_next_book_instantly_wrapper,
            "cron",
            hour=utc_hours_str,
            minute="0",
            name="instant_post_cron"
        )
        
        self.scheduler.start()
        self.is_running = True
        logger.success("System scheduler started successfully.")

    async def stop(self):
        """Stops the scheduler."""
        if not self.is_running:
            return
        logger.system("Stopping system scheduler...")
        self.scheduler.shutdown()
        self.is_running = False
        logger.success("System scheduler stopped.")

    async def check_and_replenish_queue(self):
        """Background wrapper for queue replenishment."""
        if config.MAINTENANCE_MODE:
            logger.warning("System is in Maintenance Mode. Skipping queue replenishment.")
            return
            
        if self.replenish_lock.locked():
            logger.debug("Queue replenishment is already in progress. Skipping concurrent run.")
            return
            
        async with self.replenish_lock:
            try:
                logger.system("Running scheduled queue check...")
                await self.queue_manager.check_and_replenish()
            except Exception as e:
                logger.error(f"Error in background queue replenishment: {e}")

    async def run_log_maintenance(self):
        """Background wrapper for log rotations."""
        try:
            rotate_and_clean_logs()
        except Exception as e:
            logger.error(f"Error in log maintenance job: {e}")

    async def sync_and_schedule_posts(self, is_startup: bool = False):
        """
        Core Scheduling and Recovery Loop:
        1. Syncs DB state with what Telegram actually holds in scheduled history.
        2. Calculates free slots for the next 7 days.
        3. Fills free slots with pending books from the queue.
        """
        if config.MAINTENANCE_MODE:
            logger.warning("System is in Maintenance Mode. Skipping posting scheduling.")
            return

        if not config.ENABLE_TELEGRAM:
            logger.warning("Telegram features are disabled via feature flag.")
            return
            
        logger.system("Running Telegram schedule synchronizer...")
        
        client = await client_manager.get_healthy_client()
        if not client:
            logger.error("Could not obtain a healthy Telegram client. Posting scheduling aborted.")
            return
            
        if client_manager.is_bot_active():
            if is_startup:
                logger.telegram("Bot client active. Running initial startup missed slots recovery check.")
                try:
                    await self._check_and_post_missed_slots(client)
                except Exception as e:
                    logger.error(f"Error in Bot startup missed slots check: {e}")
            else:
                logger.telegram("Bot client active. Skipping recovery check during hourly sync to avoid double posting.")
            return
            
        try:
            channels = await self.repo.get_active_channels()
            if not channels:
                logger.warning("No active channels configured in database. Please configure a channel.")
                return
                
            for channel in channels:
                logger.telegram(f"Synchronizing schedule for channel: {channel.name} ({channel.id})...")
                
                # A. Fetch actual scheduled messages on Telegram
                channel_entity = await client.get_entity(channel.id)
                telegram_times_utc = await self.publisher.get_scheduled_times(client, channel_entity)
                
                # Ensure all times from Telegram are timezone-aware UTC
                telegram_times_utc = [
                    t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)
                    for t in telegram_times_utc
                ]
                
                # B. Sync database scheduled posts list
                db_scheduled = await self.repo.get_scheduled_posts(channel.id)
                now_utc = datetime.now(timezone.utc)
                
                expired_msg_ids = []
                for db_post in db_scheduled:
                    # Ensure db scheduled_time is timezone aware UTC
                    db_time_utc = db_post.scheduled_time
                    if db_time_utc.tzinfo is None:
                        db_time_utc = db_time_utc.replace(tzinfo=timezone.utc)
                    else:
                        db_time_utc = db_time_utc.astimezone(timezone.utc)

                    # If scheduled time is in the past, Telegram has already sent it
                    if db_time_utc < now_utc:
                        expired_msg_ids.append(db_post.telegram_message_id)
                        await self.repo.update_post_status(db_post.queue_id, "posted")
                        
                    # If in the future, but not present on Telegram servers (deleted manually on Telegram)
                    elif db_time_utc > now_utc:
                        matched = False
                        for tg_time in telegram_times_utc:
                            if abs((db_time_utc - tg_time).total_seconds()) < 60:
                                matched = True
                                break
                        if not matched:
                            logger.warning(
                                f"Post {db_post.queue_id} scheduled in DB for {db_time_utc} UTC "
                                f"was not found on Telegram servers. Removing from DB scheduled list to reschedule."
                            )
                            expired_msg_ids.append(db_post.telegram_message_id)
                            # Reset post status in queue back to pending
                            await self.repo.update_post_status(db_post.queue_id, "pending")
                            
                if expired_msg_ids:
                    await self.repo.remove_scheduled_posts(channel.id, expired_msg_ids)

                # C. Find and fill empty slots for the next 7 days
                await self._fill_schedule_slots(client, channel, telegram_times_utc)
                
        except Exception as e:
            logger.error(f"Error in sync_and_schedule_posts: {e}")

    async def _fill_schedule_slots(self, client, channel: Channel, telegram_times_utc: List[datetime]):
        """
        Fills empty target slots in the next 7 days with books from the queue.
        """
        now = datetime.now() # Local time of the application
        
        for day_offset in range(7):
            target_date = now + timedelta(days=day_offset)
            
            for hour in config.SCHEDULE_HOURS:
                slot_local = datetime(
                    target_date.year, target_date.month, target_date.day,
                    hour, 0, 0
                )
                
                # Convert KSA local time to UTC and set timezone aware
                slot_utc = (slot_local - timedelta(hours=config.UTC_OFFSET_HOURS)).replace(tzinfo=timezone.utc)
                
                # Check if this slot is in the past (or within 5 minutes)
                if slot_utc < datetime.now(timezone.utc) + timedelta(minutes=5):
                    continue
                    
                # Check if there is already a post scheduled in this slot on Telegram
                slot_taken = False
                for tg_time in telegram_times_utc:
                    if abs((slot_utc - tg_time).total_seconds()) < 900:  # 15 minutes window
                        slot_taken = True
                        break
                        
                if slot_taken:
                    continue
                    
                # Slot is FREE! Fetch next pending post from queue
                logger.telegram(f"Found free schedule slot: {slot_local.strftime('%Y-%m-%d %H:%M')} (KSA time) / {slot_utc.strftime('%H:%M')} UTC. Assigning book...")
                
                pending_posts = await self.repo.get_pending_queue(limit=1)
                if not pending_posts:
                    logger.warning("Queue is empty! Cannot fill free schedule slot. Replenishment triggered.")
                    asyncio.create_task(self.check_and_replenish_queue())
                    return
                    
                post = pending_posts[0]
                
                # Process and schedule the post
                success = await self._process_and_schedule_item(client, channel, post, slot_utc)
                if success:
                    telegram_times_utc.append(slot_utc)
                    await asyncio.sleep(2)

    async def _process_and_schedule_item(self, client, channel: Channel, post: Post, slot_utc: datetime) -> bool:
        """
        Downloads PDF, extracts cover, schedules to Telegram, saves state, and cleans up.
        """
        pdf_path = None
        cover_path = None
        try:
            pdf_path = await download_pdf(post.pdf_url)
            cover_path = extract_cover(pdf_path)
            
            msg_ids = await self.publisher.schedule_book_post(
                client, channel, post, str(pdf_path), 
                str(cover_path) if cover_path else None, 
                slot_utc
            )
            
            primary_msg_id = msg_ids[0]
            db_id = f"{channel.id}_{primary_msg_id}"
            
            scheduled_post = ScheduledPost(
                id=db_id,
                queue_id=post.id,
                channel_id=channel.id,
                scheduled_time=slot_utc,
                telegram_message_id=primary_msg_id,
                status="scheduled"
            )
            
            await self.repo.save_scheduled_post(scheduled_post)
            await self.repo.update_post_status(post.id, "scheduled")
            logger.success(f"Successfully scheduled '{post.title}' on Telegram for {slot_utc} UTC.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process and schedule item '{post.title}': {e}")
            return False
            
        finally:
            try:
                if pdf_path and pdf_path.exists():
                    pdf_path.unlink()
                if cover_path and cover_path.exists():
                    cover_path.unlink()
            except Exception as ce:
                logger.error(f"Error cleaning up temp files: {ce}")

    async def post_next_book_instantly_wrapper(self):
        """Cron wrapper that triggers instant posting if the bot client is active."""
        if config.MAINTENANCE_MODE:
            return
            
        client = await client_manager.get_healthy_client()
        if not client:
            return
            
        if client_manager.is_bot_active():
            logger.system("Instant post cron triggered for Bot client.")
            await self.publish_next_book_instantly(client)

    async def publish_next_book_instantly(self, client):
        """Fetches the next pending book from queue and posts it instantly to all active channels."""
        channels = await self.repo.get_active_channels()
        if not channels:
            logger.warning("No active channels configured in database. Skipping instant post.")
            return
            
        pending_posts = await self.repo.get_pending_queue(limit=1)
        if not pending_posts:
            logger.warning("Queue is empty! Cannot post instantly. Replenishment triggered.")
            asyncio.create_task(self.check_and_replenish_queue())
            return
            
        post = pending_posts[0]
        
        for channel in channels:
            logger.telegram(f"Bot publishing '{post.title}' instantly to channel {channel.name}...")
            pdf_path = None
            cover_path = None
            try:
                pdf_path = await download_pdf(post.pdf_url)
                cover_path = extract_cover(pdf_path)
                
                # Send photo and pdf instantly
                channel_entity = await client.get_entity(channel.id)
                from telegram.publisher import format_caption
                caption = format_caption(post, channel.signature, channel.channel_hashtag)
                
                if cover_path and cover_path.exists():
                    cover_msg = await client.send_file(
                        channel_entity,
                        file=str(cover_path),
                        caption=caption,
                        parse_mode="html"
                    )
                    await asyncio.sleep(2)
                    
                    # Upload and rename PDF to match book title
                    clean_title = "".join(c for c in post.title if c not in r'\/:*?"<>|').strip()
                    if not clean_title.lower().endswith(".pdf"):
                        clean_title = f"{clean_title}.pdf"
                    logger.telegram(f"Uploading and renaming PDF to '{clean_title}'...")
                    uploaded_pdf = await client.upload_file(str(pdf_path), file_name=clean_title)
                    
                    pdf_msg = await client.send_file(
                        channel_entity,
                        file=uploaded_pdf,
                        caption=f"📁 ملف PDF للكتاب: <b>{post.title}</b>",
                        parse_mode="html"
                    )
                else:
                    # Upload and rename PDF to match book title
                    clean_title = "".join(c for c in post.title if c not in r'\/:*?"<>|').strip()
                    if not clean_title.lower().endswith(".pdf"):
                        clean_title = f"{clean_title}.pdf"
                    logger.telegram(f"Uploading and renaming PDF to '{clean_title}'...")
                    uploaded_pdf = await client.upload_file(str(pdf_path), file_name=clean_title)
                    
                    await client.send_file(
                        channel_entity,
                        file=uploaded_pdf,
                        caption=caption,
                        parse_mode="html"
                    )
                    
                # Mark as posted in DB
                await self.repo.update_post_status(post.id, "posted")
                logger.success(f"Successfully posted '{post.title}' instantly to channel {channel.name}.")
                
            except Exception as e:
                logger.error(f"Failed to post '{post.title}' instantly to channel {channel.name}: {e}")
            finally:
                if pdf_path and pdf_path.exists():
                    pdf_path.unlink()
                if cover_path and cover_path.exists():
                    cover_path.unlink()

    async def _check_and_post_missed_slots(self, client):
        """Checks if the bot missed the most recent slot, and posts if so."""
        now_utc = datetime.now(timezone.utc)
        now_ksa = now_utc + timedelta(hours=config.UTC_OFFSET_HOURS)
        
        # Find the latest scheduled slot time
        latest_slot_hour = None
        for hour in sorted(config.SCHEDULE_HOURS, reverse=True):
            if now_ksa.hour >= hour:
                latest_slot_hour = hour
                break
                
        if latest_slot_hour is None:
            latest_slot_hour = sorted(config.SCHEDULE_HOURS, reverse=True)[0]
            latest_slot_date = now_ksa.date() - timedelta(days=1)
        else:
            latest_slot_date = now_ksa.date()
            
        latest_slot_local = datetime(
            latest_slot_date.year, latest_slot_date.month, latest_slot_date.day,
            latest_slot_hour, 0, 0
        )
        latest_slot_utc = (latest_slot_local - timedelta(hours=config.UTC_OFFSET_HOURS)).replace(tzinfo=timezone.utc)
        
        # Query for recently posted books
        query = self.repo.db.collection("queue").where("status", "==", "posted").limit(20)
        posted_times = []
        async for doc in query.stream():
            data = doc.to_dict()
            posted_at = data.get("posted_at")
            if posted_at:
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                posted_times.append(posted_at)
                
        if posted_times:
            posted_times.sort(reverse=True)
            last_posted_time = posted_times[0]
        else:
            last_posted_time = datetime.min.replace(tzinfo=timezone.utc)
            
        # If the last post time is older than the latest slot time, we missed the slot!
        if last_posted_time < latest_slot_utc:
            logger.telegram(f"Missed slot detected: {latest_slot_local} KSA time. Posting next book instantly...")
            await self.publish_next_book_instantly(client)
        else:
            logger.telegram("Latest slot is already posted. No instant posting needed.")
