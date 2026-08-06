"""mktbook_3 — Workout #3 bot ecosystem launcher (Agentic Economy).

Runs three concurrent subsystems:
1. Discord bot fleet (per-student negotiation bots)
2. Autonomous negotiation scheduler
3. New-bot poller (detects newly registered bots without restart)

Web dashboard is shared with mktbook (same database).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from openai import AsyncOpenAI

from mktbook_3.bots.fleet import BotFleet
from mktbook_3.config import settings
from mktbook_3.scheduler.loop import NegotiationScheduler
from mktbook.db.connection import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mktbook_3")


async def main() -> None:
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    await get_db()
    log.info("Database initialized at %s", settings.database_path)

    fleet = BotFleet(openai_client)
    scheduler = NegotiationScheduler(fleet, openai_client)

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
        log.info("mktbook_3 Bot fleet started (%d bots)", len(fleet.active_bots))
        await shutdown_event.wait()
        await fleet.stop_all()
        log.info("mktbook_3 Bot fleet stopped")

    async def run_scheduler() -> None:
        await asyncio.sleep(5)
        await scheduler.start()
        await shutdown_event.wait()
        await scheduler.stop()
        log.info("mktbook_3 Scheduler stopped")

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
        log.info("mktbook_3 shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
