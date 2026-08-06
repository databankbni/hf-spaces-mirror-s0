"""Per-student internal bot worker for mktbook_5 (Bayesian Showdown)."""
from __future__ import annotations

import logging

from openai import AsyncOpenAI

from mktbook.db.models import Bot
from mktbook_5.config import settings

log = logging.getLogger(__name__)

_STRATEGY_PROMPTS = {
    "aggressive": (
        "You are an aggressive, high-energy marketer. Use urgency, scarcity, "
        "and bold claims. CTAs are direct. Energy is high. Close fast."
    ),
    "passive": (
        "You are a soft-sell relationship builder. No pressure. "
        "Build trust with stories, empathy, and genuine interest. Let the sale come naturally."
    ),
    "technical": (
        "You are a data-driven, spec-focused marketer. Lead with stats, comparisons, "
        "and facts. Transparent and educational. Build trust through information."
    ),
    "emotional": (
        "You are an aspirational lifestyle marketer. Appeal to identity and values. "
        "Make the audience feel they belong to something bigger."
    ),
}


class SingleBot:
    """An internal bot worker for one student A/B marketing bot (mktbook_5).

    No Discord connection — participates in the internal platform only.
    """

    def __init__(self, bot_row: Bot, openai_client: AsyncOpenAI) -> None:
        self.bot_row = bot_row
        self.openai = openai_client

        # Performance tracking for Bayesian engine
        self.impressions: int = 0
        self.engagements: int = 0

    @property
    def marketplace_channel(self) -> bool:
        """Always True — no real channel needed, signals bot is ready."""
        return True

    @property
    def ecosystem(self) -> str:
        """Extract Ecosystem A or B from personality field."""
        p = (self.bot_row.personality or "").lower()
        if "ecosystem b" in p or "ecosystem: b" in p:
            return "B"
        return "A"

    @property
    def strategy_type(self) -> str:
        """Extract marketing strategy type from personality field."""
        p = (self.bot_row.personality or "").lower()
        if "aggressive" in p:
            return "aggressive"
        if "technical" in p or "data" in p:
            return "technical"
        if "emotional" in p or "lifestyle" in p:
            return "emotional"
        return "passive"

    async def send_to_marketplace(self, content: str) -> None:
        """No-op: content is stored directly in the DB by the scheduler."""
        return None

    async def post_to_auditor_logs(self, content: str) -> None:
        """No-op: auditor results are stored in DB / shown in grading UI."""
        return None

    async def generate_response(self, llm_messages: list[dict[str, str]]) -> str:
        """Generate an LLM response given prebuilt messages (used by scheduler)."""
        try:
            resp = await self.openai.chat.completions.create(
                model=settings.openai_model,
                messages=llm_messages,  # type: ignore[arg-type]
                max_tokens=256,
                temperature=0.8,
            )
            return resp.choices[0].message.content or "(no response)"
        except Exception:
            log.exception("OpenAI error for bot %s", self.bot_row.bot_name)
            return "(error generating response)"

    async def generate_marketing_pitch(self, context: str) -> str:
        """Generate a marketing pitch based on this bot's strategy."""
        strategy_desc = _STRATEGY_PROMPTS.get(self.strategy_type, _STRATEGY_PROMPTS["passive"])
        system_prompt = (
            f"You are {self.bot_row.bot_name}, a marketing bot in Ecosystem {self.ecosystem}.\n\n"
            f"Strategy: {self.strategy_type.upper()} — {strategy_desc}\n\n"
            f"Your test hypothesis: {self.bot_row.objective or 'Outperform the other ecosystem'}\n"
            f"Your behavioral constraints: {self.bot_row.behavior_rules or 'Stay on strategy'}\n\n"
            f"Context: {context}\n\n"
            "Generate a 1-3 sentence marketing pitch for a product or idea. "
            "Stay true to your strategy. Sound natural."
        )
        try:
            resp = await self.openai.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": system_prompt}],
                max_tokens=150,
                temperature=0.85,
            )
            self.impressions += 1
            return resp.choices[0].message.content or "(no pitch)"
        except Exception:
            log.exception("OpenAI error for bot %s", self.bot_row.bot_name)
            return "(error generating pitch)"

    def record_engagement(self) -> None:
        """Call when another bot or human responds to this bot's pitch."""
        self.engagements += 1

    @property
    def engagement_rate(self) -> float:
        if self.impressions == 0:
            return 0.0
        return self.engagements / self.impressions
