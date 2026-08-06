"""mktbook_4 — Workout #4 bot ecosystem launcher (Synthetic Studio Economy).

Runs three concurrent subsystems:
1. Discord bot fleet (per-student fashion bots)
2. Autonomous fashion trend cycle scheduler
3. New-bot poller (detects newly registered bots without restart)

Web dashboard is shared with mktbook (same database).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from openai import AsyncOpenAI

from mktbook_4.bots.fleet import BotFleet
from mktbook_4.config import settings
from mktbook_4.scheduler.loop import TrendScheduler
from mktbook.db.connection import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mktbook_4")


async def main() -> None:
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    await get_db()
    log.info("Database initialized at %s", settings.database_path)

    # Optional: image generator (requires DALL-E quota)
    image_generator = None
    try:
        from mktbook_4.image_generator import ImageGenerator
        img_path = Path(settings.image_storage_path)
        img_path.mkdir(parents=True, exist_ok=True)
        image_generator = ImageGenerator(openai_client, settings)
        log.info("Image generator initialized (DALL-E enabled)")
    except Exception:
        log.warning("Image generator unavailable — text-only mode")

    fleet = BotFleet(openai_client)
    scheduler = TrendScheduler(fleet, openai_client, image_generator)

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
        log.info("mktbook_4 Bot fleet started (%d bots)", len(fleet.active_bots))
        await shutdown_event.wait()
        await fleet.stop_all()
        log.info("mktbook_4 Bot fleet stopped")

    async def run_scheduler() -> None:
        await asyncio.sleep(5)
        await scheduler.start()
        await shutdown_event.wait()
        await scheduler.stop()

    async def run_poller() -> None:
        await fleet.poll_new_bots(interval=30)

    try:
        await asyncio.gather(run_fleet(), run_scheduler(), run_poller())
    except asyncio.CancelledError:
        pass
    finally:
        await close_db()
        log.info("mktbook_4 shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
