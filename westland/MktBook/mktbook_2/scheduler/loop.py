"""Conversation scheduler for mktbook_2."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from mktbook.db import queries
from mktbook.bots import conversation

if TYPE_CHECKING:
    from mktbook_2.bots.fleet import BotFleet

log = logging.getLogger(__name__)


class ConversationScheduler:
    """Coordinates autonomous bot-to-bot conversations for mktbook_2."""

    def __init__(self, fleet: BotFleet) -> None:
        self.fleet = fleet
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the scheduler background loop."""
        if self._running:
            log.warning("Scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("mktbook_2 ConversationScheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("mktbook_2 ConversationScheduler stopped")

    async def _loop(self) -> None:
        """Main loop: pick pairs and run conversations."""
        while self._running:
            try:
                await self._run_one_conversation()
            except Exception:
                log.exception("Error in conversation loop")
            
            # Wait between conversations
            from mktbook_2.config import settings
            interval = random.randint(settings.conversation_min_interval, settings.conversation_max_interval)
            await asyncio.sleep(interval)

    async def _run_one_conversation(self) -> None:
        """Pick a random pair and run one conversation."""
        from mktbook_2.config import settings
        
        active_bots = list(self.fleet.active_bots.values())
        if len(active_bots) < 2:
            log.debug("Not enough active bots for conversation")
            return

        # Weighted random selection: pairs that have conversed less get higher weight
        pair = await self._pick_weighted_pair(active_bots)
        if not pair:
            return

        initiator, responder = pair
        log.info("Starting mktbook_2 conversation: %s ↔ %s", 
                 initiator.bot_row.bot_name, responder.bot_row.bot_name)

        # Record conversation
        conv = await queries.create_conversation(
            channel_id=None,
            conv_type="bot-bot",
            initiator_bot_id=initiator.bot_row.id,
            responder_bot_id=responder.bot_row.id,
        )

        # Build initial context
        recent_messages = await queries.get_messages(limit=20, bot_id=initiator.bot_row.id)
        recent_messages.reverse()

        # Run conversation turns
        current_bot = initiator
        other_bot = responder
        
        for turn in range(settings.conversation_turns):
            # Generate current bot's message
            llm_messages = conversation.build_bot_to_bot_messages(
                current_bot.bot_row,
                other_bot.bot_row,
                recent_messages,
            )
            
            reply = await current_bot.generate_response(llm_messages)
            
            # Record message
            await queries.create_message(
                conversation_id=conv.id,
                bot_id=current_bot.bot_row.id,
                author_type="bot",
                author_name=current_bot.bot_row.bot_name,
                content=reply,
                discord_msg_id=None,
            )
            
            # Send to Discord if we have the channel
            if current_bot.marketplace_channel:
                try:
                    msg = await current_bot.send_to_marketplace(reply)
                    if msg:
                        await queries.update_message_discord_id(
                            conversation_id=conv.id,
                            bot_id=current_bot.bot_row.id,
                            discord_msg_id=str(msg.id),
                        )
                except Exception:
                    log.exception("Failed to send message to Discord")
            
            # Add to recent messages for context
            recent_messages.append((current_bot.bot_row.bot_name, reply))
            
            # Swap roles
            current_bot, other_bot = other_bot, current_bot
            
            # Small delay between messages
            await asyncio.sleep(2)

        # Mark conversation as ended
        await queries.end_conversation(conv.id, settings.conversation_turns)
        log.info("Conversation %d ended", conv.id)

    async def _pick_weighted_pair(self, bots: list) -> tuple | None:
        """Pick a random pair weighted by how much they've already conversed."""
        if len(bots) < 2:
            return None

        # Count past conversations between each pair
        pair_weights: dict[tuple[int, int], int] = {}
        
        for i in range(len(bots)):
            for j in range(i + 1, len(bots)):
                bot_a, bot_b = bots[i], bots[j]
                past_convos = await queries.count_conversations_between(
                    bot_a.bot_row.id, bot_b.bot_row.id
                )
                # Inverse weight: fewer past convos = higher weight
                weight = max(1, 5 - past_convos)
                pair_weights[(i, j)] = weight

        if not pair_weights:
            return None

        # Weighted random selection
        indices = list(pair_weights.keys())
        weights = [pair_weights[idx] for idx in indices]
        chosen_idx = random.choices(indices, weights=weights, k=1)[0]
        i, j = chosen_idx
        
        return (bots[i], bots[j])
