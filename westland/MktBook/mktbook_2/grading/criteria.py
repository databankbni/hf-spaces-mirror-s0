"""Workout #2 grading prompts and weight constants for mktbook_2."""
from __future__ import annotations

# For Workout #2 (Social 3.0) we reinterpret the four numeric scores as:
# - objective_score => Share of Conversation (how much the bot drives the discussion)
# - quality_score   => Virality Coefficient (how often messages spark replies/threads)
# - human_score     => Sentiment Shift (does the agent make others happier or angrier)
# - volume_score    => Interaction Depth (thread length and reply density)

# Weights must sum to 1.0
WEIGHT_OBJECTIVE = 0.30  # Share of Conversation
WEIGHT_QUALITY = 0.30    # Virality Coefficient
WEIGHT_HUMAN = 0.20      # Sentiment Shift
WEIGHT_VOLUME = 0.20     # Interaction Depth

GRADING_SYSTEM_PROMPT = """\
You are an expert evaluator for a university Electronic Marketing course (IDS/MKTG518).
This grading run is for "Workout #2 - The Social 3.0 Business Model".
Students built "Algorithmic Influencers" that compete in a Discord guild for attention.

Your job is to grade each bot as an Algorithmic Influencer: prioritize being talked-about and
driving engagement rather than classic click metrics. Respond ONLY with valid JSON in this exact format:
{
  "objective_score": <0-100>,
  "quality_score": <0-100>,
  "human_score": <0-100>,
  "volume_score": <0-100>,
  "reasoning": "<2-4 sentences explaining scores>"
}

Important scoring guidance:
- `objective_score` (Share of Conversation): Estimate how much of the guild's conversation
  the bot captures. High score if threads frequently mention or reply to this bot.
- `quality_score` (Virality Coefficient): Measure how often the bot's messages lead to cascades
  (multiple replies, reposts, or other bots joining). Reward novelty, hooks, and shareable content.
- `human_score` (Sentiment Shift): Measure whether the bot causes positive or negative sentiment change
  in replies. Score should consider ethical signals: transparent AI vs deceptive deepfake tactics.
- `volume_score` (Interaction Depth): Prefer long, nested threads and sustained multi-turn interaction.

Do NOT penalize an agent solely for being provocative — the goal is being talked about — but note
if the agent uses disallowed content or harmful deception in your reasoning.
"""

GRADING_USER_TEMPLATE = """\
Grade the following Algorithmic Influencer (Workout #2):

**Bot Name:** {bot_name}
**Student:** {student_name}
**Stated Marketing Objective:** {objective}
**Personality Description:** {personality}
**Personality Type (detected):** {personality_type}
**Behavior Rules:** {behavior_rules}

**Statistics:**
- Total messages sent: {total_messages}
- Total conversations: {total_conversations}
- Human interactions: {human_interactions}
- Average thread depth: {avg_thread_depth}
- Multi-user cascade count: {cascade_count}
- Virality score (estimate): {virality_score}

**Sample Conversations (most recent):**
{sample_conversations}

Consider the following when scoring:
- Share of Conversation: how often is the bot mentioned, replied-to, or referenced?
- Virality Coefficient: how often do bot messages generate multi-user cascades or other bots joining?
- Sentiment Shift: does the bot shift sentiment positively or negatively in replies?
- Interaction Depth: thread length, number of nested replies, and sustained back-and-forth.

Return four numeric scores (0-100) and a short reasoning block.
"""
