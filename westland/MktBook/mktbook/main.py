"""MktBook Bot Marketplace — entry point.

Runs three concurrent subsystems on one asyncio event loop:
1. FastAPI web server (Uvicorn)
2. Internal bot fleet
3. Autonomous conversation scheduler
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

import uvicorn
from openai import AsyncOpenAI

from mktbook.bots.fleet import BotFleet
from mktbook.config import settings
from mktbook.db.connection import close_db, get_db
from mktbook.grading.auto_grader import AutoGrader
from mktbook.scheduler.loop import ConversationScheduler
from mktbook.web.app import create_app
from mktbook.web.websocket import WSManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mktbook")


async def main() -> None:
    # Shared resources
    openai_client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base if settings.openai_api_base else None
    )
    ws = WSManager()

    # Initialize database
    await get_db()
    log.info("Database initialized at %s", settings.database_path)

    # Create subsystems
    fleet = BotFleet(openai_client, ws)
    scheduler = ConversationScheduler(fleet, ws)
    auto_grader = AutoGrader(openai_client, ws)
    app = create_app(ws)
    app.state.fleet = fleet
    app.state.scheduler = scheduler
    app.state.auto_grader = auto_grader
    app.state.openai = openai_client

    # Uvicorn server config
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        loop="asyncio",
        ws="wsproto",
    )
    server = uvicorn.Server(config)

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Shutdown signal received")
        shutdown_event.set()
        scheduler.stop()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

    async def run_server() -> None:
        await server.serve()

    async def run_fleet() -> None:
        await fleet.start_all()
        log.info("Bot fleet started (%d bots)", len(fleet.active_bots))
        await auto_grader.load_from_db()
        await shutdown_event.wait()
        await auto_grader.stop_all()
        await fleet.stop_all()
        log.info("Bot fleet stopped")

    async def run_scheduler() -> None:
        # Brief delay to let fleet connect first
        await asyncio.sleep(5)
        await scheduler.run()

    async def run_poller() -> None:
        await fleet.poll_new_bots(interval=30)

    try:
        await asyncio.gather(
            run_server(),
            run_fleet(),
            run_scheduler(),
            run_poller(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        await close_db()
        log.info("MktBook shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
