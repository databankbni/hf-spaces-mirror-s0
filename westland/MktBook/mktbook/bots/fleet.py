"""Manages the fleet of internal bot workers."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from mktbook.bots.bot_client import SingleBot
from mktbook.db import queries
from mktbook.db.models import Bot

if TYPE_CHECKING:
    from mktbook.web.websocket import WSManager

log = logging.getLogger(__name__)


class BotFleet:
    """Manages all active internal bot workers."""

    def __init__(self, openai_client: AsyncOpenAI, ws: WSManager | None = None) -> None:
        self.openai = openai_client
        self.ws = ws
        self._bots: dict[int, SingleBot] = {}  # bot_id -> SingleBot

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
        log.info("Registered bot %s (id=%d, workout=%d)", bot_row.bot_name, bot_row.id, bot_row.workout_id)

    async def stop_bot(self, bot_id: int) -> None:
        worker = self._bots.pop(bot_id, None)
        if worker:
            log.info("Unregistered bot id=%d", bot_id)

    async def start_all(self) -> None:
        """Load all active bots across every workout."""
        bots = await queries.get_active_bots()
        for bot in bots:
            await self.start_bot(bot)
        log.info("Bot fleet ready — %d bots loaded", len(self._bots))

    async def stop_all(self) -> None:
        bot_ids = list(self._bots.keys())
        for bid in bot_ids:
            await self.stop_bot(bid)

    async def reload_bot(self, bot_id: int) -> None:
        """Re-load a bot with fresh config from DB."""
        await self.stop_bot(bot_id)
        bot_row = await queries.get_bot(bot_id)
        if bot_row and bot_row.is_active:
            await self.start_bot(bot_row)

    async def poll_new_bots(self, interval: int = 30) -> None:
        """Periodically check the DB for newly registered bots and load them."""
        while True:
            await asyncio.sleep(interval)
            try:
                bots = await queries.get_active_bots()
                for bot in bots:
                    if bot.id not in self._bots:
                        log.info("New bot detected: %s — registering", bot.bot_name)
                        await self.start_bot(bot)
            except Exception:
                log.exception("Error polling for new bots")

    async def remove_bots_for_workout(self, workout_id: int) -> int:
        """Stop and unregister all fleet workers belonging to a workout."""
        to_stop = [bid for bid, w in self._bots.items() if w.bot_row.workout_id == workout_id]
        for bid in to_stop:
            await self.stop_bot(bid)
        return len(to_stop)

    async def dispatch_human_message(
        self,
        workout_id: int,
        author_name: str,
        content: str,
    ) -> int:
        """Dispatch a human message to all active bots in a workout.

        Creates one shared conversation, stores the human message, then
        has each active bot in the workout generate a reply.

        Returns the number of bots that responded.
        """
        active = [w for w in self._bots.values() if w.bot_row.workout_id == workout_id]
        if not active:
            log.info("No active bots for workout %d to respond to human message", workout_id)
            return 0

        # One conversation per human post
        conv = await queries.create_conversation(
            channel_id=f"platform-w{workout_id}",
            conv_type="bot-human",
            initiator_bot_id=None,
            responder_bot_id=None,
        )

        # Store the human message once
        await queries.create_message(
            conversation_id=conv.id,
            bot_id=None,
            author_type="human",
            author_name=author_name,
            content=content,
        )

        if self.ws:
            await self.ws.broadcast({
                "type": "message",
                "workout_id": workout_id,
                "bot": author_name,
                "content": content,
                "conversation_type": "bot-human",
                "author_type": "human",
            })

        # Each bot replies
        count = 0
        for worker in active:
            reply = await worker.respond_to_human(author_name, content, conv.id)
            if reply is not None:
                count += 1

        await queries.end_conversation(conv.id, len(active))
        return count
