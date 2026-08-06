"""Manages the fleet of internal bot workers for mktbook_2."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from mktbook_2.bots.bot_client import SingleBot
from mktbook.db import queries
from mktbook.db.models import Bot

if TYPE_CHECKING:
    from mktbook.web.websocket import WSManager

log = logging.getLogger(__name__)


class BotFleet:
    """Manages all active internal bot workers (mktbook_2)."""

    def __init__(self, openai_client: AsyncOpenAI, ws: WSManager | None = None) -> None:
        self.openai = openai_client
        self.ws = ws
        self._bots: dict[int, SingleBot] = {}

    @property
    def active_bots(self) -> dict[int, SingleBot]:
        return dict(self._bots)

    def get_bot(self, bot_id: int) -> SingleBot | None:
        return self._bots.get(bot_id)

    async def start_bot(self, bot_row: Bot) -> None:
        if bot_row.id in self._bots:
            log.warning("Bot %s already registered", bot_row.bot_name)
            return
        worker = SingleBot(bot_row, self.openai, self.ws)
        self._bots[bot_row.id] = worker
        log.info("Registered mktbook_2 bot %s (id=%d)", bot_row.bot_name, bot_row.id)

    async def stop_bot(self, bot_id: int) -> None:
        worker = self._bots.pop(bot_id, None)
        if worker:
            log.info("Unregistered mktbook_2 bot id=%d", bot_id)

    async def start_all(self) -> None:
        bots = await queries.get_active_bots(workout_id=2)
        for bot in bots:
            await self.start_bot(bot)

    async def stop_all(self) -> None:
        for bid in list(self._bots.keys()):
            await self.stop_bot(bid)

    async def reload_bot(self, bot_id: int) -> None:
        await self.stop_bot(bot_id)
        bot_row = await queries.get_bot(bot_id)
        if bot_row and bot_row.is_active:
            await self.start_bot(bot_row)

    async def poll_new_bots(self, interval: int = 30) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                bots = await queries.get_active_bots(workout_id=2)
                for bot in bots:
                    if bot.id not in self._bots:
                        log.info("New bot detected: %s — registering", bot.bot_name)
                        await self.start_bot(bot)
            except Exception:
                log.exception("Error polling for new bots")
