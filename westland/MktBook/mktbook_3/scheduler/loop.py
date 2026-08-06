"""Negotiation scheduler for mktbook_3: The Agentic Economy."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime

from mktbook_3.engagement import EngagementAnalyzer
from mktbook_3.models import NegotiationContext, DealState, NegotiationPersona

log = logging.getLogger(__name__)

AGREEMENT_TOKENS = ["i accept", "deal", "agreed", "sounds good", "i'm in",
                    "let's do it", "confirmed", "we have a deal", "you've got a deal"]


class NegotiationScheduler:
    """Orchestrates autonomous negotiations between student bots (mktbook_3)."""

    def __init__(self, fleet, openai_client) -> None:
        self.fleet = fleet
        self.openai = openai_client
        self._running = False
        self._task: asyncio.Task | None = None
        self.analyzer = EngagementAnalyzer()
        self.closed_negotiations: list[NegotiationContext] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("mktbook_3 NegotiationScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("mktbook_3 NegotiationScheduler stopped")

    async def _loop(self) -> None:
        from mktbook_3.config import settings
        while self._running:
            try:
                active = list(self.fleet.active_bots.values())
                if len(active) >= 2:
                    await self._run_negotiation(active)
                else:
                    log.debug("Not enough bots for negotiation (%d active)", len(active))
            except Exception:
                log.exception("Error in negotiation loop")
            await asyncio.sleep(settings.negotiation_cooldown)

    async def _run_negotiation(self, bots: list) -> None:
        from mktbook_3.config import settings

        # Pick random pair (weighted toward less-frequent pairs)
        initiator, responder = random.sample(bots, 2)
        log.info("Negotiation: %s ↔ %s", initiator.bot_row.bot_name, responder.bot_row.bot_name)

        try:
            initiator_persona = NegotiationPersona[initiator.persona.upper()]
        except KeyError:
            initiator_persona = NegotiationPersona.OUTREACH
        try:
            responder_persona = NegotiationPersona[responder.persona.upper()]
        except KeyError:
            responder_persona = NegotiationPersona.OUTREACH

        neg_id = f"neg_{int(datetime.now().timestamp())}"
        negotiation = NegotiationContext(
            negotiation_id=neg_id,
            initiator=str(initiator.bot_row.id),
            responder=str(responder.bot_row.id),
            initiator_persona=initiator_persona,
            responder_persona=responder_persona,
        )

        conversation_history: list[dict] = []
        current_bot = initiator
        other_bot = responder
        deal_closed = False

        for turn in range(settings.max_negotiation_turns):
            is_init = (turn == 0)
            reply = await current_bot.generate_negotiation_message(
                counterparty_name=other_bot.bot_row.bot_name,
                counterparty_persona=other_bot.persona,
                conversation_history=conversation_history,
                is_initiator=is_init,
            )

            # Strip [THINKING] prefix if present
            if "[ACTUAL RESPONSE]" in reply:
                reply = reply.split("[ACTUAL RESPONSE]", 1)[-1].strip()

            display = f"**{current_bot.bot_row.bot_name}**: {reply}"
            await current_bot.send_to_marketplace(display)
            conversation_history.append({"role": "assistant", "content": display})
            negotiation.turn_count += 1

            # Check for deal closure
            reply_lower = reply.lower()
            if any(token in reply_lower for token in AGREEMENT_TOKENS):
                negotiation.mark_deal_closed("semantic_agreement")
                deal_closed = True
                log.info("Deal CLOSED in %s after %d turns", neg_id, negotiation.turn_count)
                break

            # Analyse for circular logic
            self.analyzer.update_circular_detection(negotiation)
            if negotiation.is_circular_loop():
                log.warning("Circular logic detected in %s — ending", neg_id)
                break

            current_bot, other_bot = other_bot, current_bot
            await asyncio.sleep(2)

        if not deal_closed:
            negotiation.close_stalled()

        self.closed_negotiations.append(negotiation)
        log.info(
            "Negotiation %s ended: %s (%d turns)",
            neg_id,
            "CLOSED" if deal_closed else "STALLED",
            negotiation.turn_count,
        )

    def get_stats(self) -> dict:
        total = len(self.closed_negotiations)
        closed = sum(1 for n in self.closed_negotiations if n.is_deal_closed())
        return {
            "total_negotiations": total,
            "deals_closed": closed,
            "conversion_rate": closed / total if total > 0 else 0.0,
        }
