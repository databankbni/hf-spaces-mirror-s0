"""Per-student internal bot worker (no Discord dependency)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from mktbook.bots.conversation import build_reply_messages
from mktbook.bots.image_gen import extract_image_prompt, generate_image, w4_image_gate
from mktbook.config import settings
from mktbook.db import queries
from mktbook.db.models import Bot

if TYPE_CHECKING:
    from mktbook.web.websocket import WSManager

log = logging.getLogger(__name__)


class SingleBot:
    """An internal bot worker for one student's bot.

    No Discord connection — bots participate in the internal platform only.
    """

    def __init__(self, bot_row: Bot, openai_client: AsyncOpenAI, ws: WSManager | None = None) -> None:
        self.bot_row = bot_row
        self.openai = openai_client
        self.ws = ws

    @property
    def marketplace_channel(self) -> bool:
        """Always True — no real channel needed, signals bot is ready."""
        return True

    async def wait_until_marketplace_ready(self) -> None:
        """No-op: internal bots are ready immediately."""
        return

    async def generate_response(self, llm_messages: list[dict[str, str]], max_tokens: int = 256) -> str:
        """Generate an LLM response given prebuilt messages."""
        try:
            resp = await self.openai.chat.completions.create(
                model=settings.openai_model,
                messages=llm_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=0.8,
            )
            return resp.choices[0].message.content or "(no response)"
        except Exception:
            log.exception("OpenAI error for bot %s", self.bot_row.bot_name)
            return "(error generating response)"

    async def send_to_marketplace(self, content: str) -> None:
        """No-op: content is stored directly in the DB by the scheduler."""
        return None

    async def post_to_auditor_logs(self, content: str) -> None:
        """No-op: auditor log is stored in DB / shown in grading UI."""
        return None

    async def respond_to_human(
        self,
        human_name: str,
        message_content: str,
        conversation_id: int,
    ) -> str | None:
        """Generate and persist a reply to a human message on the platform."""
        recent = await queries.get_messages(limit=10, bot_id=self.bot_row.id)
        recent.reverse()

        llm_messages = build_reply_messages(
            self.bot_row, human_name, message_content, recent
        )

        is_studio = self.bot_row.workout_id == 4
        tokens = 350 if is_studio else 256
        try:
            resp = await self.openai.chat.completions.create(
                model=settings.openai_model,
                messages=llm_messages,  # type: ignore[arg-type]
                max_tokens=tokens,
                temperature=0.8,
            )
            raw_text = resp.choices[0].message.content or "(no response)"
        except Exception:
            log.exception("OpenAI error for bot %s responding to human", self.bot_row.bot_name)
            return None

        # For workout #4: extract [IMAGE: ...] tag; generate image only when gate fires.
        if is_studio:
            reply_text, _prompt = extract_image_prompt(raw_text)
            if _prompt and w4_image_gate.should_trigger():
                image_prompt = _prompt
                image_url = await generate_image(image_prompt)
            else:
                image_prompt, image_url = None, None
        else:
            reply_text, image_prompt, image_url = raw_text, None, None

        await queries.create_message(
            conversation_id=conversation_id,
            bot_id=self.bot_row.id,
            author_type="bot",
            author_name=self.bot_row.bot_name,
            content=reply_text,
            image_url=image_url,
            image_prompt=image_prompt,
        )

        if self.ws:
            await self.ws.broadcast({
                "type": "message",
                "workout_id": self.bot_row.workout_id,
                "bot": self.bot_row.bot_name,
                "content": reply_text,
                "image_url": image_url,
                "conversation_type": "bot-human",
            })

        return reply_text
