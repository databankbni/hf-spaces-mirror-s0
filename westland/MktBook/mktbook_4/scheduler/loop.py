"""Fashion trend cycle scheduler for mktbook_4: Synthetic Studio Economy."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)


class TrendScheduler:
    """Orchestrates fashion trend proposal/evaluation cycles (mktbook_4)."""

    def __init__(self, fleet, openai_client, image_generator=None) -> None:
        self.fleet = fleet
        self.openai = openai_client
        self.image_generator = image_generator
        self._running = False
        self._task: asyncio.Task | None = None
        self.cycle_count = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("mktbook_4 TrendScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("mktbook_4 TrendScheduler stopped")

    async def _loop(self) -> None:
        from mktbook_4.config import settings
        while self._running:
            try:
                active = list(self.fleet.active_bots.values())
                if len(active) >= 1:
                    await self._run_trend_cycle(active)
                else:
                    log.debug("No active fashion bots yet")
            except Exception:
                log.exception("Error in trend cycle")
            await asyncio.sleep(settings.trend_cycle_interval)

    async def _run_trend_cycle(self, bots: list) -> None:
        self.cycle_count += 1
        cycle_id = f"cycle_{self.cycle_count}_{datetime.now().strftime('%H%M%S')}"
        context = (
            "Current fashion context: sustainability meets innovation, "
            "inclusive luxury, cultural relevance, post-digital aesthetics"
        )
        log.info("Starting fashion trend cycle %d (%d bots)", self.cycle_count, len(bots))

        proposals = []
        for bot in bots:
            try:
                proposal = await bot.propose_fashion_trend(context, cycle_id)
                if proposal.trend_description:
                    proposals.append((bot, proposal))
                    log.info("%s proposed: %s", bot.bot_row.bot_name, proposal.trend_description[:60])
            except Exception:
                log.exception("Error getting proposal from %s", bot.bot_row.bot_name)

        # Post each proposal to marketplace and collect evaluations
        adoption_counts: dict[int, int] = {bot.bot_row.id: 0 for bot, _ in proposals}

        for proposer_bot, proposal in proposals:
            # Generate image if image_generator available, else text-only post
            image_url: str | None = None
            if self.image_generator:
                try:
                    img_prompt = f"{proposal.trend_description} — {proposal.aesthetic_focus}"
                    image_url, _ = await self.image_generator.generate_fashion_image(
                        proposal.trend_description, img_prompt, proposal.visual_strategy
                    )
                except Exception:
                    log.exception("Image generation failed for %s", proposer_bot.bot_row.bot_name)

            # Post to marketplace
            title = f"Fashion Proposal: {proposal.aesthetic_focus}"
            body = (
                f"{proposal.trend_description}\n\n"
                f"**Strategy:** {proposal.visual_strategy} | "
                f"**Cultural:** {proposal.cultural_angle}"
            )
            try:
                await proposer_bot.send_embed_to_marketplace(title, body, image_url)
            except Exception:
                log.exception("Failed to post proposal to marketplace")
                await proposer_bot.send_to_marketplace(
                    f"**{proposer_bot.bot_row.bot_name}** proposes: {proposal.trend_description}"
                )

            await asyncio.sleep(2)

            # Have all other bots evaluate this proposal
            for eval_bot in bots:
                if eval_bot.bot_row.id == proposer_bot.bot_row.id:
                    continue
                try:
                    evaluation = await eval_bot.evaluate_fashion_trend(proposal, image_url)
                    # High adoption likelihood = bot adopts the trend
                    if evaluation["adoption_likelihood"] > 60:
                        adoption_counts[proposer_bot.bot_row.id] += 1
                    # Post evaluation to marketplace
                    eval_msg = (
                        f"**{eval_bot.bot_row.bot_name}** on "
                        f"**{proposer_bot.bot_row.bot_name}**'s trend: "
                        f"{evaluation['assessment']} "
                        f"_(Influence: {evaluation['influence_score']:.0f}/100)_"
                    )
                    await eval_bot.send_to_marketplace(eval_msg)
                    await asyncio.sleep(1)
                except Exception:
                    log.exception("Evaluation error")

        # Update influence scores
        for bot, proposal in proposals:
            adoptions = adoption_counts.get(bot.bot_row.id, 0)
            bot.update_influence_score(adoptions, self.cycle_count)
            log.info(
                "%s influence: %.1f (adoptions: %d)",
                bot.bot_row.bot_name, bot.influence_score, adoptions,
            )

        log.info("Fashion cycle %d complete", self.cycle_count)
