"""LLM-based grading evaluator for mktbook_2 (Workout #2)."""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from mktbook.db import queries
from mktbook.db.models import Grade
from mktbook_2.grading.criteria import (
    GRADING_SYSTEM_PROMPT,
    GRADING_USER_TEMPLATE,
    WEIGHT_HUMAN,
    WEIGHT_OBJECTIVE,
    WEIGHT_QUALITY,
    WEIGHT_VOLUME,
)
from mktbook_2.config import settings
from mktbook_2 import engagement

log = logging.getLogger(__name__)


class GradeEvaluator:
    def __init__(self, openai_client: AsyncOpenAI) -> None:
        self.openai = openai_client

    async def grade_all(self, run_id: str) -> list[Grade]:
        bots = await queries.get_active_bots()
        results: list[Grade] = []

        for bot in bots:
            try:
                grade = await self._grade_bot(bot, run_id)
                results.append(grade)
            except Exception:
                log.exception("Failed to grade bot %s", bot.bot_name)

        return results

    async def _grade_bot(self, bot, run_id: str) -> Grade:
        stats = await queries.get_bot_stats(bot.id)
        sample_convos = await self._build_sample_conversations(bot.id)
        
        # Calculate Workout #2-specific engagement metrics
        eng_metrics = await engagement.calculate_engagement_metrics(bot.id)
        personality_type = engagement.estimate_personality_type(bot.objective or "", bot.personality or "")
        
        # Build enhanced user prompt with engagement data
        user_prompt = GRADING_USER_TEMPLATE.format(
            bot_name=bot.bot_name,
            student_name=bot.student_name,
            objective=bot.objective or "(not specified)",
            personality=bot.personality or "(not specified)",
            behavior_rules=bot.behavior_rules or "(not specified)",
            total_messages=stats["messages"],
            total_conversations=stats["conversations"],
            human_interactions=stats["human_interactions"],
            sample_conversations=sample_convos or "(no conversations yet)",
            avg_thread_depth=f"{eng_metrics['avg_thread_depth']:.1f}",
            cascade_count=eng_metrics["cascade_count"],
            virality_score=f"{eng_metrics['virality_score']:.0f}",
            personality_type=personality_type,
        )

        resp = await self.openai.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": GRADING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0.2,
        )

        raw = resp.choices[0].message.content or "{}"
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.error("Failed to parse grading response for %s: %s", bot.bot_name, raw)
            data = {
                "objective_score": 0,
                "quality_score": 0,
                "human_score": 0,
                "volume_score": 0,
                "reasoning": f"Parse error: {raw[:200]}",
            }

        obj = float(data.get("objective_score", 0))
        qual = float(data.get("quality_score", 0))
        hum = float(data.get("human_score", 0))
        vol = float(data.get("volume_score", 0))
        overall = (
            obj * WEIGHT_OBJECTIVE
            + qual * WEIGHT_QUALITY
            + hum * WEIGHT_HUMAN
            + vol * WEIGHT_VOLUME
        )
        reasoning = data.get("reasoning", "")

        grade = await queries.create_grade(
            bot_id=bot.id,
            grading_run_id=run_id,
            objective_score=obj,
            quality_score=qual,
            human_score=hum,
            volume_score=vol,
            overall_score=overall,
            llm_reasoning=reasoning,
            total_messages=stats["messages"],
            total_conversations=stats["conversations"],
            human_interactions=stats["human_interactions"],
        )

        log.info("mktbook_2 Graded %s: %.1f (share=%.0f, viral=%.0f, sentiment=%.0f, depth=%.0f)",
                 bot.bot_name, overall, obj, qual, hum, vol)
        return grade

    async def _build_sample_conversations(self, bot_id: int, max_convos: int = 5) -> str:
        conversations = await queries.get_bot_conversations(bot_id, limit=max_convos)
        if not conversations:
            return ""

        parts: list[str] = []
        for conv in conversations:
            msgs = await queries.get_conversation_messages(conv.id)
            if not msgs:
                continue
            lines = [f"[{conv.type} conversation #{conv.id}]"]
            for m in msgs:
                lines.append(f"  {m.author_name}: {m.content[:200]}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)
