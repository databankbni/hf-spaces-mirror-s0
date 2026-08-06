from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bot:
    id: int
    student_name: str
    bot_name: str
    personality: str
    objective: str
    behavior_rules: str
    is_active: bool
    workout_id: int
    created_at: str


@dataclass
class Conversation:
    id: int
    channel_id: str | None
    type: str
    initiator_bot_id: int | None
    responder_bot_id: int | None
    turn_count: int
    started_at: str
    ended_at: str | None


@dataclass
class Message:
    id: int
    conversation_id: int | None
    bot_id: int | None
    author_type: str
    author_name: str
    content: str
    created_at: str
    image_url: str | None = None
    image_prompt: str | None = None


@dataclass
class Grade:
    id: int
    bot_id: int
    grading_run_id: str
    objective_score: float
    quality_score: float
    human_score: float
    volume_score: float
    overall_score: float
    llm_reasoning: str
    total_messages: int
    total_conversations: int
    human_interactions: int
    created_at: str
