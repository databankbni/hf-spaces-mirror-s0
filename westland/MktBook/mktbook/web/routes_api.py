"""REST API routes."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from mktbook.db import queries
from mktbook.web.auth import is_authenticated

router = APIRouter(prefix="/api")





class BotCreate(BaseModel):
    student_name: str
    bot_name: str
    personality: str = ""
    objective: str = ""
    behavior_rules: str = ""
    workout_id: int = 1


class BotUpdate(BaseModel):
    student_name: str | None = None
    bot_name: str | None = None
    personality: str | None = None
    objective: str | None = None
    behavior_rules: str | None = None
    is_active: bool | None = None


def _bot_to_dict(bot) -> dict[str, Any]:
    return {
        "id": bot.id,
        "student_name": bot.student_name,
        "bot_name": bot.bot_name,
        "personality": bot.personality,
        "objective": bot.objective,
        "behavior_rules": bot.behavior_rules,
        "is_active": bot.is_active,
        "workout_id": bot.workout_id,
        "created_at": bot.created_at,
    }


# ── Bots ──────────────────────────────────────────────────────────────

@router.get("/bots")
async def list_bots() -> list[dict[str, Any]]:
    bots = await queries.get_all_bots()
    return [_bot_to_dict(b) for b in bots]


@router.post("/bots")
async def create_bot(body: BotCreate, request: Request) -> dict[str, Any]:
    bot = await queries.create_bot(
        student_name=body.student_name,
        bot_name=body.bot_name,
        personality=body.personality,
        objective=body.objective,
        behavior_rules=body.behavior_rules,
        workout_id=body.workout_id,
    )
    # Register the bot in the fleet
    fleet = request.app.state.fleet
    if fleet:
        await fleet.start_bot(bot)

    ws = request.app.state.ws
    if ws:
        await ws.broadcast({"type": "bot_added", "bot": _bot_to_dict(bot)})

    return _bot_to_dict(bot)


@router.get("/bots/{bot_id}")
async def get_bot(bot_id: int) -> dict[str, Any]:
    bot = await queries.get_bot(bot_id)
    if not bot:
        return {"error": "not found"}
    data = _bot_to_dict(bot)
    data["stats"] = await queries.get_bot_stats(bot_id)
    data["grades"] = [
        {
            "grading_run_id": g.grading_run_id,
            "overall_score": g.overall_score,
            "objective_score": g.objective_score,
            "quality_score": g.quality_score,
            "human_score": g.human_score,
            "volume_score": g.volume_score,
            "llm_reasoning": g.llm_reasoning,
            "created_at": g.created_at,
        }
        for g in await queries.get_bot_grades(bot_id)
    ]
    return data


@router.put("/bots/{bot_id}")
async def update_bot(bot_id: int, body: BotUpdate, request: Request) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True)
    bot = await queries.update_bot(bot_id, **fields)
    if not bot:
        return {"error": "not found"}

    fleet = request.app.state.fleet
    if fleet:
        await fleet.reload_bot(bot_id)

    return _bot_to_dict(bot)


@router.delete("/bots/{bot_id}", response_model=None)
async def delete_bot(bot_id: int, request: Request) -> JSONResponse | dict[str, str]:
    if not is_authenticated(request):
        return JSONResponse(
            {"error": "Admin authentication required"},
            status_code=401,
        )
    fleet = request.app.state.fleet
    if fleet:
        await fleet.stop_bot(bot_id)
    await queries.delete_bot(bot_id)
    return {"status": "deleted"}


# ── Messages ──────────────────────────────────────────────────────────

@router.get("/messages")
async def list_messages(limit: int = 100, bot_id: int | None = None) -> list[dict[str, Any]]:
    msgs = await queries.get_messages(limit=limit, bot_id=bot_id)
    return [
        {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "bot_id": m.bot_id,
            "author_type": m.author_type,
            "author_name": m.author_name,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


# ── Leaderboard ───────────────────────────────────────────────────────

@router.get("/leaderboard")
async def leaderboard() -> list[dict[str, Any]]:
    grades = await queries.get_latest_grades()
    bots = {b.id: b for b in await queries.get_all_bots()}
    result = []
    for g in grades:
        bot = bots.get(g.bot_id)
        result.append({
            "bot_id": g.bot_id,
            "bot_name": bot.bot_name if bot else "Unknown",
            "student_name": bot.student_name if bot else "Unknown",
            "overall_score": g.overall_score,
            "objective_score": g.objective_score,
            "quality_score": g.quality_score,
            "human_score": g.human_score,
            "volume_score": g.volume_score,
            "created_at": g.created_at,
        })
    return result


# ── Grading ───────────────────────────────────────────────────────────

@router.post("/grading/run", response_model=None)
async def run_grading(request: Request) -> dict[str, Any] | JSONResponse:
    if not is_authenticated(request):
        return JSONResponse({"error": "Admin authentication required"}, status_code=401)
    from mktbook.grading.evaluator import GradeEvaluator

    openai_client = request.app.state.openai
    if not openai_client:
        return {"error": "OpenAI client not configured"}

    run_id = str(uuid.uuid4())[:8]
    evaluator = GradeEvaluator(openai_client)
    grades = await evaluator.grade_all(run_id)

    ws = request.app.state.ws
    if ws:
        await ws.broadcast({"type": "grading_complete", "run_id": run_id, "count": len(grades)})

    return {
        "run_id": run_id,
        "grades": [
            {
                "bot_id": g.bot_id,
                "overall_score": g.overall_score,
                "llm_reasoning": g.llm_reasoning,
            }
            for g in grades
        ],
    }


@router.get("/grading/export")
async def export_grades(request: Request) -> StreamingResponse:
    from mktbook.grading.export import export_all_csv
    csv_text = await export_all_csv()
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mktbook_grade_history_all.csv"'},
    )


# ── Grade history CSV export ───────────────────────────────────────────

@router.get("/w/{workout_id}/grades/history.csv")
async def export_grades_history_csv(workout_id: int, request: Request) -> StreamingResponse:
    """Download full grade history for a workout as a CSV file (auth required)."""
    if not is_authenticated(request):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Admin authentication required"}, status_code=401)

    rows = await queries.get_grades_for_workout(workout_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "grading_run_id", "student_name", "bot_name",
        "overall_score", "objective_score", "quality_score", "human_score", "volume_score",
        "total_messages", "total_conversations", "human_interactions", "llm_reasoning",
    ])
    for r in rows:
        writer.writerow([
            r["created_at"],
            r["grading_run_id"],
            r["student_name"],
            r["bot_name"],
            round(r["overall_score"], 2),
            round(r["objective_score"], 2),
            round(r["quality_score"], 2),
            round(r["human_score"], 2),
            round(r["volume_score"], 2),
            r["total_messages"],
            r["total_conversations"],
            r["human_interactions"],
            r["llm_reasoning"],
        ])

    output.seek(0)
    filename = f"mktbook_w{workout_id}_grade_history.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Platform CSV export ────────────────────────────────────────────────

@router.get("/w/{workout_id}/messages/export.csv")
async def export_messages_csv(workout_id: int) -> StreamingResponse:
    """Download all messages for a workout as a CSV file, grouped by conversation."""
    # No limit — fetch all messages for the full workout period
    msgs = await queries.get_messages_for_workout(workout_id=workout_id)

    # Sort by conversation_id then by id (chronological within each conversation)
    sorted_msgs = sorted(
        msgs,
        key=lambda m: (m.conversation_id or 0, m.id),
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["conversation_id", "id", "timestamp", "author_name", "author_type", "content"])
    for m in sorted_msgs:
        writer.writerow([
            m.conversation_id or "",
            m.id,
            m.created_at,
            m.author_name,
            m.author_type,
            m.content,
        ])

    output.seek(0)
    filename = f"mktbook_w{workout_id}_messages.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
