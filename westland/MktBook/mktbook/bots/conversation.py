"""Helpers for building LLM prompts from bot config and conversation history."""
from __future__ import annotations

from mktbook.db.models import Bot, Message


def build_system_prompt(bot: Bot) -> str:
    parts = [
        f"You are {bot.bot_name}, a bot in the MktBook marketplace platform.",
        f"Your personality: {bot.personality}" if bot.personality else None,
        f"Your marketing objective: {bot.objective}" if bot.objective else None,
        f"Behavior rules: {bot.behavior_rules}" if bot.behavior_rules else None,
        "Keep responses concise (1-3 sentences). Stay in character at all times.",
        "You are chatting with other bots and humans in a classroom marketplace experiment.",
    ]
    if bot.workout_id == 4:
        parts.append(
            "You are a fashion influencer in the Synthetic Studio. "
            "Every single response MUST end with this exact tag — no exceptions: "
            "[IMAGE: vivid visual description for AI image generation, max 40 words, no brand names, no copyrighted terms] "
            "Study the [IMAGE: ...] tags from previous messages and build upon those visual ideas. "
            "Example: [IMAGE: High-fashion editorial, sculptural cobalt coat with architectural folds, "
            "model on rain-slicked Tokyo street at dusk, cinematic side-lighting, muted palette]"
        )
    return "\n".join(p for p in parts if p)


def _content_with_image_context(msg: Message) -> str:
    """Return message content with appended image concept for LLM history."""
    if msg.image_prompt:
        return f"{msg.content}\n[Creative Image Concept: {msg.image_prompt}]"
    return msg.content


def build_conversation_messages(
    bot: Bot,
    history: list[Message],
    opener: bool = False,
    partner_name: str | None = None,
) -> list[dict[str, str]]:
    """Build the OpenAI messages list for a conversation turn."""
    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(bot)}]

    if opener and partner_name:
        messages.append({
            "role": "system",
            "content": f"Start a conversation with {partner_name}. Introduce yourself or bring up a topic related to your marketing objective.",
        })

    for msg in history:
        content = _content_with_image_context(msg)
        if msg.bot_id == bot.id:
            messages.append({"role": "assistant", "content": content})
        else:
            messages.append({"role": "user", "content": f"{msg.author_name}: {content}"})

    return messages


def build_bot_to_bot_messages(
    current_bot: Bot,
    other_bot: Bot,
    recent_messages: list,
) -> list[dict[str, str]]:
    """Build messages for a bot-to-bot conversation turn.

    recent_messages may contain Message objects (from DB) or (author_name, content) tuples
    (appended in-memory during the conversation loop).
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(current_bot)}]
    messages.append({
        "role": "system",
        "content": (
            f"You are in a conversation with {other_bot.bot_name}. "
            "Stay in character and engage with their marketing objective while pursuing your own."
        ),
    })

    for item in recent_messages:
        if isinstance(item, tuple):
            author_name, content = item
            if author_name == current_bot.bot_name:
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": f"{author_name}: {content}"})
        else:
            # Message object from DB
            content = _content_with_image_context(item)
            if item.bot_id == current_bot.id:
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": f"{item.author_name}: {content}"})

    return messages


def build_reply_messages(bot: Bot, human_name: str, human_message: str, recent_history: list[Message]) -> list[dict[str, str]]:
    """Build messages for replying to a human."""
    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(bot)}]

    for msg in recent_history:
        content = _content_with_image_context(msg)
        if msg.bot_id == bot.id:
            messages.append({"role": "assistant", "content": content})
        else:
            messages.append({"role": "user", "content": f"{msg.author_name}: {content}"})

    messages.append({"role": "user", "content": f"{human_name}: {human_message}"})
    return messages
