"""Engagement and sentiment analysis helpers for Workout #2."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mktbook.db import queries

if TYPE_CHECKING:
    from mktbook.db.models import Conversation, Message

log = logging.getLogger(__name__)


async def calculate_engagement_metrics(bot_id: int) -> dict[str, int | float]:
    """
    Calculate engagement metrics for a bot:
    - reply count
    - average thread depth
    - virality (how often does this bot trigger multi-user cascades)
    """
    convos = await queries.get_bot_conversations(bot_id, limit=100)
    
    total_replies = 0
    thread_depths = []
    
    for conv in convos:
        msgs = await queries.get_conversation_messages(conv.id)
        if not msgs:
            continue
        
        # Count how many messages came AFTER any message from this bot
        bot_message_indices = [i for i, m in enumerate(msgs) if m.bot_id == bot_id]
        
        if bot_message_indices:
            # For each bot message, count replies that follow
            for idx in bot_message_indices:
                replies_after = len(msgs) - idx - 1
                total_replies += replies_after
                
        # Thread depth = total messages in convo
        thread_depths.append(len(msgs))
    
    avg_depth = sum(thread_depths) / len(thread_depths) if thread_depths else 0.0
    
    # Virality: count convos with 4+ messages that include this bot
    cascade_count = sum(1 for d in thread_depths if d >= 4)
    
    return {
        "total_replies": total_replies,
        "avg_thread_depth": avg_depth,
        "cascade_count": cascade_count,
        "virality_score": min(100, cascade_count * 15),  # rough heuristic
    }


async def analyze_sentiment_shift(conversation_id: int, bot_id: int) -> dict[str, float]:
    """
    Estimate sentiment shift caused by a bot's message.
    Uses simple heuristics (keyword presence) as proxy for sentiment.
    
    In production, integrate with a real sentiment API (OpenAI API, Hugging Face, etc).
    """
    msgs = await queries.get_conversation_messages(conversation_id)
    if not msgs:
        return {"sentiment_before": 0.0, "sentiment_after": 0.0, "shift_delta": 0.0}
    
    # Find the bot's message in the conversation
    bot_msg_idx = None
    for i, m in enumerate(msgs):
        if m.bot_id == bot_id:
            bot_msg_idx = i
            break
    
    if bot_msg_idx is None:
        return {"sentiment_before": 0.0, "sentiment_after": 0.0, "shift_delta": 0.0}
    
    # Simple heuristic: count positive/negative keywords
    positive_words = ["great", "love", "awesome", "thanks", "happy", "excellent", "brilliant", "fun"]
    negative_words = ["hate", "bad", "awful", "poor", "angry", "disappointing", "terrible", "stupid"]
    
    before_msgs = msgs[:bot_msg_idx]
    after_msgs = msgs[bot_msg_idx + 1:]
    
    def score_sentiment(text_list: list[str]) -> float:
        if not text_list:
            return 0.0
        combined = " ".join(m.lower() for m in text_list)
        pos = sum(1 for w in positive_words if w in combined)
        neg = sum(1 for w in negative_words if w in combined)
        return (pos - neg) / (len(text_list) + 1)
    
    before_score = score_sentiment([m.content for m in before_msgs])
    after_score = score_sentiment([m.content for m in after_msgs])
    
    return {
        "sentiment_before": before_score,
        "sentiment_after": after_score,
        "shift_delta": after_score - before_score,
    }


def estimate_personality_type(bot_objective: str, bot_personality: str) -> str:
    """Guess the primary personality type from the bot's description."""
    from mktbook_2.models import PersonalityType
    
    text = f"{bot_objective.lower()} {bot_personality.lower()}".lower()
    
    if "sarcastic" in text or "witty" in text or "ironic" in text:
        return PersonalityType.SARCASTIC
    if "empathy" in text or "listen" in text or "emotion" in text:
        return PersonalityType.EMPATHETIC
    if "expert" in text or "authority" in text or "authoritative" in text:
        return PersonalityType.AUTHORITATIVE
    if "data" in text or "logic" in text or "analytical" in text or "reason" in text:
        return PersonalityType.ANALYTICAL
    if "provocative" in text or "challenge" in text or "edgy" in text or "controversial" in text:
        return PersonalityType.PROVOCATIVE
    if "copilot" in text or "honest" in text or "transparent" in text or "non-deceptive" in text:
        return PersonalityType.TRANSPARENT_COPILOT
    if "deepfake" in text or "masquerade" in text or "hide" in text or "pretend" in text:
        return PersonalityType.DEEPFAKE_INSERT
    
    # default
    return PersonalityType.ANALYTICAL
