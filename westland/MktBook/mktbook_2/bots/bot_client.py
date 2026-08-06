"""Per-student internal bot worker for mktbook_2."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from mktbook.bots.conversation import build_reply_messages
from mktbook.db import queries
from mktbook.db.models import Bot
from mktbook_2.config import settings

if TYPE_CHECKING:
    from mktbook.web.websocket import WSManager

log = logging.getLogger(__name__)


class SingleBot:
    """An internal bot worker for one student's bot (mktbook_2)."""

    def __init__(self, bot_row: Bot, openai_client: AsyncOpenAI, ws: WSManager | None = None) -> None:
        self.bot_row = bot_row
        self.openai = openai_client
        self.ws = ws

    @property
    def marketplace_channel(self) -> bool:
        return True

    async def wait_until_marketplace_ready(self) -> None:
        return

    async def generate_response(self, llm_messages: list[dict[str, str]]) -> str:
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

    async def send_to_marketplace(self, content: str) -> None:
        return None

    async def post_to_auditor_logs(self, content: str) -> None:
        return None

    async def respond_to_human(
        self,
        human_name: str,
        message_content: str,
        conversation_id: int,
    ) -> str | None:
        recent = await queries.get_messages(limit=10, bot_id=self.bot_row.id)
        recent.reverse()
        llm_messages = build_reply_messages(self.bot_row, human_name, message_content, recent)
        try:
            resp = await self.openai.chat.completions.create(
                model=settings.openai_model,
                messages=llm_messages,  # type: ignore[arg-type]
                max_tokens=256,
                temperature=0.8,
            )
            reply_text = resp.choices[0].message.content or "(no response)"
        except Exception:
            log.exception("OpenAI error for bot %s responding to human", self.bot_row.bot_name)
            return None
        await queries.create_message(
            conversation_id=conversation_id,
            bot_id=self.bot_row.id,
            author_type="bot",
            author_name=self.bot_row.bot_name,
            content=reply_text,
        )
        if self.ws:
            await self.ws.broadcast({
                "type": "message",
                "bot": self.bot_row.bot_name,
                "content": reply_text,
                "conversation_type": "bot-human",
            })
        return reply_text
