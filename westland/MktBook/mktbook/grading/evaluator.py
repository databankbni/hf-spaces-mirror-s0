"""LLM-based grading evaluator."""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from mktbook.config import settings
from mktbook.db import queries
from mktbook.db.models import Grade
from mktbook.ecosystem import detect_ecosystem
from mktbook.grading.criteria import (
    WEIGHT_HUMAN,
    WEIGHT_OBJECTIVE,
    WEIGHT_QUALITY,
    WEIGHT_VOLUME,
    W5_WEIGHT_HUMAN,
    W5_WEIGHT_OBJECTIVE,
    W5_WEIGHT_QUALITY,
    W5_WEIGHT_VOLUME,
    get_grading_prompts,
)

log = logging.getLogger(__name__)


class GradeEvaluator:
    def __init__(self, openai_client: AsyncOpenAI) -> None:
        self.openai = openai_client

    async def grade_all(self, run_id: str, workout_id: int | None = None) -> list[Grade]:
        bots = await queries.get_active_bots(workout_id=workout_id)
        results: list[Grade] = []

        # Precompute ecosystem message totals for W5 bots
        w5_bots = [b for b in bots if b.workout_id == 5]
        eco_totals: dict[str, int] = {"Ecosystem A": 0, "Ecosystem B": 0}
        for b in w5_bots:
            s = await queries.get_bot_stats(b.id)
            eco = self._detect_ecosystem(b)
            eco_totals[eco] += s["messages"]

        for bot in bots:
            try:
                if bot.workout_id == 5:
                    grade = await self._grade_bot_w5(bot, run_id, eco_totals)
                else:
                    grade = await self._grade_bot(bot, run_id, workout_id=workout_id)
                results.append(grade)
            except Exception:
                log.exception("Failed to grade bot %s", bot.bot_name)

        return results

    @staticmethod
    def _detect_ecosystem(bot) -> str:
        return detect_ecosystem(bot)

    async def _grade_bot(self, bot, run_id: str, workout_id: int | None = None) -> Grade:
        stats = await queries.get_bot_stats(bot.id)
        sample_convos = await self._build_sample_conversations(bot.id)

        effective_workout_id = workout_id if workout_id is not None else getattr(bot, "workout_id", None)
        system_prompt, user_template = get_grading_prompts(effective_workout_id or 0)

        user_prompt = user_template.format(
            bot_name=bot.bot_name,
            student_name=bot.student_name,
            objective=bot.objective or "(not specified)",
            personality=bot.personality or "(not specified)",
            behavior_rules=bot.behavior_rules or "(not specified)",
            total_messages=stats["messages"],
            total_conversations=stats["conversations"],
            human_interactions=stats["human_interactions"],
            sample_conversations=sample_convos or "(no conversations yet)",
        )

        resp = await self.openai.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0.2,
        )

        raw = resp.choices[0].message.content or "{}"
        # Strip markdown fences if present
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

        log.info("Graded %s: %.1f (obj=%.0f, qual=%.0f, hum=%.0f, vol=%.0f)",
                 bot.bot_name, overall, obj, qual, hum, vol)
        return grade

    async def _grade_bot_w5(self, bot, run_id: str, eco_totals: dict[str, int]) -> Grade:
        """Grade a W5 bot using engagement metrics (Share of Conversation) with ecosystem context."""
        stats = await queries.get_bot_stats(bot.id)
        sample_convos = await self._build_sample_conversations(bot.id)
        ecosystem = self._detect_ecosystem(bot)
        eco_total = eco_totals.get(ecosystem, 0)
        eco_share = (stats["messages"] / eco_total * 100) if eco_total > 0 else 0.0

        w5_system, w5_user_template = get_grading_prompts(5)
        user_prompt = w5_user_template.format(
            ecosystem=ecosystem,
            bot_name=bot.bot_name,
            student_name=bot.student_name,
            objective=bot.objective or "(not specified)",
            personality=bot.personality or "(not specified)",
            behavior_rules=bot.behavior_rules or "(not specified)",
            total_messages=stats["messages"],
            total_conversations=stats["conversations"],
            human_interactions=stats["human_interactions"],
            ecosystem_share=eco_share,
            ecosystem_total=eco_total,
            sample_conversations=sample_convos or "(no conversations yet)",
        )

        resp = await self.openai.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": w5_system},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0.2,
        )

        raw = (resp.choices[0].message.content or "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.error("Failed to parse W5 grading response for %s: %s", bot.bot_name, raw)
            data = {
                "objective_score": 0, "quality_score": 0,
                "human_score": 0, "volume_score": 0,
                "reasoning": f"Parse error: {raw[:200]}",
            }

        obj = float(data.get("objective_score", 0))
        qual = float(data.get("quality_score", 0))
        hum = float(data.get("human_score", 0))
        vol = float(data.get("volume_score", 0))
        overall = (
            obj * W5_WEIGHT_OBJECTIVE
            + qual * W5_WEIGHT_QUALITY
            + hum * W5_WEIGHT_HUMAN
            + vol * W5_WEIGHT_VOLUME
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

        log.info("W5 Graded %s [%s]: %.1f (share=%.0f, viral=%.0f, sentiment=%.0f, depth=%.0f)",
                 bot.bot_name, ecosystem, overall, obj, qual, hum, vol)
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
