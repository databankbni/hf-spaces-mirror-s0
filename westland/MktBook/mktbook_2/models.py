"""Workout #2-specific data models for personality and engagement metrics."""
from __future__ import annotations

from dataclasses import dataclass


# Personality archetypes for Workout #2
class PersonalityType:
    """Enum of personality archetypes for Algorithmic Influencers."""
    AUTHORITATIVE = "authoritative"
    EMPATHETIC = "empathetic"
    SARCASTIC = "sarcastic"
    ANALYTICAL = "analytical"
    PROVOCATIVE = "provocative"
    TRANSPARENT_COPILOT = "transparent_copilot"
    DEEPFAKE_INSERT = "deepfake_insert"

    ALL = [
        AUTHORITATIVE, EMPATHETIC, SARCASTIC, ANALYTICAL,
        PROVOCATIVE, TRANSPARENT_COPILOT, DEEPFAKE_INSERT
    ]


PERSONALITY_DESCRIPTIONS = {
    PersonalityType.AUTHORITATIVE: "Expert voice; confident, decisive, takes control of conversation.",
    PersonalityType.EMPATHETIC: "Listener-first; validates emotions, builds rapport, caring tone.",
    PersonalityType.SARCASTIC: "Witty, irreverent; uses humor and irony to stand out.",
    PersonalityType.ANALYTICAL: "Data-driven, logical; explains reasoning, cites patterns.",
    PersonalityType.PROVOCATIVE: "Edgy, contrarian; challenges norms, drives strong reactions.",
    PersonalityType.TRANSPARENT_COPILOT: "Honest about being AI; helpful, non-deceptive.",
    PersonalityType.DEEPFAKE_INSERT: "Masquerades as human; hides AI nature; high engagement risk.",
}


@dataclass
class EngagementMetrics:
    """Per-bot engagement metrics for Workout #2."""
    bot_id: int
    total_replies: int  # count of human/bot replies to this bot's messages
    reaction_count: int  # emoji reactions on Discord
    thread_length_avg: float  # average length of threads this bot starts/participates in
    reply_cascade_count: int  # count of multi-user reply chains triggered by this bot
    virality_score: float  # composite virality (0-100)
    

@dataclass
class SentimentShift:
    """Sentiment analysis for Workout #2: does the bot shift sentiment positive or negative?"""
    conversation_id: int
    bot_id: int
    sentiment_before: float  # -1 to 1 (negative to positive) of messages before bot spoke
    sentiment_after: float   # sentiment of messages after bot spoke
    shift_delta: float       # after - before
    created_at: str


@dataclass  
class CloutScore:
    """Clout/influence metrics for the bot from LLM evaluation."""
    bot_id: int
    grading_run_id: str
    personality_type: str  # e.g., "sarcastic", "empathetic", etc.
    share_of_conversation: float  # 0-100: what % of guild discussion mentions/involves bot
    virality_coefficient: float  # 0-100: how often does bot spark multi-user cascades
    sentiment_shift_score: float  # 0-100: avg sentiment lift (higher = more positive reactions)
    interaction_depth: float  # 0-100: avg thread depth and multi-turn engagement
    overall_clout: float  # weighted composite (0-100)
    created_at: str
