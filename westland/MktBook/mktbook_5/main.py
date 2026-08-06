"""mktbook_5 — Workout #5 bot ecosystem launcher (Bayesian Showdown).

Runs three concurrent subsystems:
1. Discord bot fleet (per-student A/B marketing bots)
2. Autonomous pitch scheduler + Bayesian comparison engine
3. New-bot poller (detects newly registered bots without restart)

Web dashboard is shared with mktbook (same database).
"""
from __future__ import annotations

import asyncio
import logging
import random
import signal
import sys

from openai import AsyncOpenAI

from mktbook_5.bots.fleet import BotFleet
from mktbook_5.config import settings
from mktbook.db.connection import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mktbook_5")

PITCH_CONTEXTS = [
    "A new productivity app launches today",
    "A sustainable fashion brand seeks buyers",
    "A fintech startup offers early-adopter deals",
    "An online education platform wants students",
    "A health-tech wearable is looking for beta users",
]


async def run_pitch_scheduler(fleet: BotFleet) -> None:
    """Have each bot pitch products on a schedule; track engagement by ecosystem."""
    while True:
        await asyncio.sleep(settings.pitch_interval)
        active = list(fleet.active_bots.values())
        if not active:
            continue
        try:
            context = random.choice(PITCH_CONTEXTS)
            # Each bot pitches; bots in the other ecosystem respond (simulates cross-ecosystem engagement)
            ecosystems = fleet.bots_by_ecosystem()
            for ecosystem_label, bots in ecosystems.items():
                for bot in bots:
                    pitch = await bot.generate_marketing_pitch(context)
                    await bot.send_to_marketplace(
                        f"**[Ecosystem {bot.ecosystem}] {bot.bot_row.bot_name}**: {pitch}"
                    )
                    await asyncio.sleep(1)
                    # Simulate engagement: opposing ecosystem bots respond
                    opposing = "B" if ecosystem_label == "A" else "A"
                    for responder in ecosystems.get(opposing, []):
                        response = await responder.generate_marketing_pitch(
                            f"Responding to: {pitch}"
                        )
                        await responder.send_to_marketplace(
                            f"**[Ecosystem {responder.ecosystem}] {responder.bot_row.bot_name}**: "
                            f"{response}"
                        )
                        bot.record_engagement()
                        await asyncio.sleep(1)
            # Log Bayesian comparison
            a_bots = ecosystems.get("A", [])
            b_bots = ecosystems.get("B", [])
            if a_bots and b_bots:
                a_rate = sum(b.engagement_rate for b in a_bots) / len(a_bots)
                b_rate = sum(b.engagement_rate for b in b_bots) / len(b_bots)
                log.info(
                    "Bayesian snapshot — Ecosystem A avg engagement: %.2f | B: %.2f | Winner: %s",
                    a_rate, b_rate, "A" if a_rate >= b_rate else "B",
                )
        except Exception:
            log.exception("Error in pitch scheduler")


async def main() -> None:
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    await get_db()
    log.info("Database initialized at %s", settings.database_path)

    fleet = BotFleet(openai_client)

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
        log.info("mktbook_5 Bot fleet started (%d bots)", len(fleet.active_bots))
        await shutdown_event.wait()
        await fleet.stop_all()
        log.info("mktbook_5 Bot fleet stopped")

    async def run_scheduler() -> None:
        await asyncio.sleep(5)
        await run_pitch_scheduler(fleet)

    async def run_poller() -> None:
        await fleet.poll_new_bots(interval=30)

    try:
        await asyncio.gather(run_fleet(), run_scheduler(), run_poller())
    except asyncio.CancelledError:
        pass
    finally:
        await close_db()
        log.info("mktbook_5 shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
