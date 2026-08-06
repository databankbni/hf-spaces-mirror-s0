"""mktbook_2 — Workout #2 bot ecosystem launcher (no web UI).

Runs two concurrent subsystems:
1. Discord bot fleet
2. Autonomous conversation scheduler

Web dashboard is shared with mktbook (same database).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from openai import AsyncOpenAI

from mktbook_2.bots.fleet import BotFleet
from mktbook_2.config import settings
from mktbook_2.scheduler.loop import ConversationScheduler
from mktbook.db.connection import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mktbook_2")


async def main() -> None:
    # Shared resources
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Initialize database (shared with mktbook)
    await get_db()
    log.info("Database initialized at %s", settings.database_path)

    # Create subsystems
    fleet = BotFleet(openai_client)
    scheduler = ConversationScheduler(fleet)

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

    async def run_fleet() -> None:
        await fleet.start_all()
        log.info("mktbook_2 Bot fleet started (%d bots)", len(fleet.active_bots))
        await shutdown_event.wait()
        await fleet.stop_all()
        log.info("mktbook_2 Bot fleet stopped")

    async def run_scheduler() -> None:
        # Brief delay to let fleet connect first
        await asyncio.sleep(5)
        await scheduler.start()
        await shutdown_event.wait()
        await scheduler.stop()
        log.info("mktbook_2 Scheduler stopped")

    async def run_poller() -> None:
        await fleet.poll_new_bots(interval=30)

    try:
        await asyncio.gather(
            run_fleet(),
            run_scheduler(),
            run_poller(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        await close_db()
        log.info("mktbook_2 shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
