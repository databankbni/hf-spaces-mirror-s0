"""Automatic periodic regrading for individual workouts."""
from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from mktbook.db import queries

if TYPE_CHECKING:
    from mktbook.web.websocket import WSManager

log = logging.getLogger(__name__)


class AutoGrader:
    """Runs LLM grading on a per-workout schedule.

    Each workout can have an independent interval (1–12 hours).
    Settings are persisted in the DB so they survive service restarts.
    """

    def __init__(self, openai_client: AsyncOpenAI, ws: WSManager | None = None) -> None:
        self.openai = openai_client
        self.ws = ws
        self._tasks: dict[int, asyncio.Task] = {}
        self._intervals: dict[int, int] = {}
        self._next_run_at: dict[int, datetime.datetime] = {}

    async def load_from_db(self) -> None:
        """Load saved settings and start scheduled tasks (call once at startup)."""
        rows = await queries.get_all_auto_grade_settings()
        for row in rows:
            await self._start_task(row["workout_id"], row["interval_hours"])
        if rows:
            log.info("AutoGrader: loaded %d scheduled workout(s) from DB", len(rows))

    async def set(self, workout_id: int, interval_hours: int) -> None:
        """Enable or update auto-grading for a workout."""
        await queries.set_auto_grade_setting(workout_id, interval_hours)
        if workout_id in self._tasks and not self._tasks[workout_id].done():
            self._tasks[workout_id].cancel()
        await self._start_task(workout_id, interval_hours)
        log.info("AutoGrader: workout #%d set to every %d hour(s)", workout_id, interval_hours)

    async def clear(self, workout_id: int) -> None:
        """Disable auto-grading for a workout."""
        task = self._tasks.pop(workout_id, None)
        if task and not task.done():
            task.cancel()
        self._intervals.pop(workout_id, None)
        self._next_run_at.pop(workout_id, None)
        await queries.delete_auto_grade_setting(workout_id)
        log.info("AutoGrader: workout #%d auto-grading disabled", workout_id)

    def get_interval(self, workout_id: int) -> int | None:
        """Return the current interval in hours, or None if not scheduled."""
        task = self._tasks.get(workout_id)
        if task and not task.done():
            return self._intervals.get(workout_id)
        return None

    def get_next_run_at(self, workout_id: int) -> datetime.datetime | None:
        """Return the datetime of the next scheduled grading run."""
        task = self._tasks.get(workout_id)
        if task and not task.done():
            return self._next_run_at.get(workout_id)
        return None

    async def stop_all(self) -> None:
        """Cancel all running tasks (call on shutdown)."""
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self._intervals.clear()
        self._next_run_at.clear()

    async def _start_task(self, workout_id: int, interval_hours: int) -> None:
        self._intervals[workout_id] = interval_hours
        self._tasks[workout_id] = asyncio.create_task(
            self._run_loop(workout_id, interval_hours),
            name=f"auto_grader_w{workout_id}",
        )

    async def _run_loop(self, workout_id: int, interval_hours: int) -> None:
        try:
            while True:
                self._next_run_at[workout_id] = (
                    datetime.datetime.now()
                    + datetime.timedelta(hours=interval_hours)
                )
                await asyncio.sleep(interval_hours * 3600)
                await self._run_grading(workout_id)
        except asyncio.CancelledError:
            self._next_run_at.pop(workout_id, None)

    async def _run_grading(self, workout_id: int) -> None:
        from mktbook.grading.evaluator import GradeEvaluator

        run_id = str(uuid.uuid4())[:8]
        log.info("AutoGrader: starting grading run %s for workout #%d", run_id, workout_id)
        try:
            evaluator = GradeEvaluator(self.openai)
            grades = await evaluator.grade_all(run_id, workout_id=workout_id)
            if self.ws:
                await self.ws.broadcast({
                    "type": "grading_complete",
                    "run_id": run_id,
                    "count": len(grades),
                    "workout_id": workout_id,
                })
            log.info("AutoGrader: workout #%d grading complete — %d bots", workout_id, len(grades))
        except Exception:
            log.exception("AutoGrader: grading failed for workout #%d", workout_id)
