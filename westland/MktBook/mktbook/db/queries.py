from __future__ import annotations

from typing import Any

from mktbook.db.connection import get_db
from mktbook.db.models import Bot, Conversation, Grade, Message


def _row_to_bot(row: Any) -> Bot:
    return Bot(
        id=row["id"],
        student_name=row["student_name"],
        bot_name=row["bot_name"],
        personality=row["personality"],
        objective=row["objective"],
        behavior_rules=row["behavior_rules"],
        is_active=bool(row["is_active"]),
        workout_id=row["workout_id"] if "workout_id" in row.keys() else 1,
        created_at=row["created_at"],
    )


def _row_to_conversation(row: Any) -> Conversation:
    return Conversation(
        id=row["id"],
        channel_id=row["channel_id"],
        type=row["type"],
        initiator_bot_id=row["initiator_bot_id"],
        responder_bot_id=row["responder_bot_id"],
        turn_count=row["turn_count"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )


def _row_to_message(row: Any) -> Message:
    keys = row.keys() if hasattr(row, "keys") else []
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        bot_id=row["bot_id"],
        author_type=row["author_type"],
        author_name=row["author_name"],
        content=row["content"],
        created_at=row["created_at"],
        image_url=row["image_url"] if "image_url" in keys else None,
        image_prompt=row["image_prompt"] if "image_prompt" in keys else None,
    )


def _row_to_grade(row: Any) -> Grade:
    return Grade(
        id=row["id"],
        bot_id=row["bot_id"],
        grading_run_id=row["grading_run_id"],
        objective_score=row["objective_score"],
        quality_score=row["quality_score"],
        human_score=row["human_score"],
        volume_score=row["volume_score"],
        overall_score=row["overall_score"],
        llm_reasoning=row["llm_reasoning"],
        total_messages=row["total_messages"],
        total_conversations=row["total_conversations"],
        human_interactions=row["human_interactions"],
        created_at=row["created_at"],
    )


# ── Bots ──────────────────────────────────────────────────────────────

async def create_bot(
    student_name: str,
    bot_name: str,
    personality: str = "",
    objective: str = "",
    behavior_rules: str = "",
    workout_id: int = 1,
) -> Bot:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO bots (student_name, bot_name, personality, objective, behavior_rules, workout_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (student_name, bot_name, personality, objective, behavior_rules, workout_id),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM bots WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return _row_to_bot(row)


async def get_bot(bot_id: int) -> Bot | None:
    db = await get_db()
    row = await (await db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,))).fetchone()
    return _row_to_bot(row) if row else None


async def get_bot_by_name(bot_name: str) -> Bot | None:
    db = await get_db()
    row = await (await db.execute("SELECT * FROM bots WHERE bot_name = ?", (bot_name,))).fetchone()
    return _row_to_bot(row) if row else None


async def get_all_bots(workout_id: int | None = None) -> list[Bot]:
    db = await get_db()
    if workout_id is not None:
        rows = await (await db.execute(
            "SELECT * FROM bots WHERE workout_id = ? ORDER BY created_at DESC", (workout_id,)
        )).fetchall()
    else:
        rows = await (await db.execute("SELECT * FROM bots ORDER BY created_at DESC")).fetchall()
    return [_row_to_bot(r) for r in rows]


async def get_active_bots(workout_id: int | None = None) -> list[Bot]:
    db = await get_db()
    if workout_id is not None:
        rows = await (await db.execute(
            "SELECT * FROM bots WHERE is_active = 1 AND workout_id = ? ORDER BY bot_name", (workout_id,)
        )).fetchall()
    else:
        rows = await (await db.execute("SELECT * FROM bots WHERE is_active = 1 ORDER BY bot_name")).fetchall()
    return [_row_to_bot(r) for r in rows]


async def update_bot(bot_id: int, **fields: Any) -> Bot | None:
    if not fields:
        return await get_bot(bot_id)
    allowed = {"student_name", "bot_name", "personality", "objective", "behavior_rules", "is_active", "workout_id"}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return await get_bot(bot_id)
    sets = ", ".join(f"{k} = ?" for k in filtered)
    vals = list(filtered.values()) + [bot_id]
    db = await get_db()
    await db.execute(f"UPDATE bots SET {sets} WHERE id = ?", vals)
    await db.commit()
    return await get_bot(bot_id)


async def delete_bot(bot_id: int) -> None:
    db = await get_db()
    # Collect all conversations this bot participated in
    cur = await db.execute(
        "SELECT id FROM conversations WHERE initiator_bot_id = ? OR responder_bot_id = ?",
        (bot_id, bot_id),
    )
    conv_ids = [r[0] for r in await cur.fetchall()]
    # Delete ALL messages in those conversations (partner bot's messages too),
    # otherwise the conversations DELETE hits a FK constraint on messages.conversation_id
    if conv_ids:
        ph = ",".join("?" * len(conv_ids))
        await db.execute(f"DELETE FROM messages WHERE conversation_id IN ({ph})", conv_ids)
    # Delete any remaining messages authored by this bot (e.g. human-conv records)
    await db.execute("DELETE FROM messages WHERE bot_id = ?", (bot_id,))
    # Now safe to delete conversations
    await db.execute(
        "DELETE FROM conversations WHERE initiator_bot_id = ? OR responder_bot_id = ?",
        (bot_id, bot_id),
    )
    await db.execute("DELETE FROM grades WHERE bot_id = ?", (bot_id,))
    await db.execute(
        "DELETE FROM conversation_pairs WHERE bot_a_id = ? OR bot_b_id = ?",
        (bot_id, bot_id),
    )
    # lti_user_bots.bot_id has FK → bots.id, must delete before the bot row
    await db.execute("DELETE FROM lti_user_bots WHERE bot_id = ?", (bot_id,))
    await db.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
    await db.commit()


# ── Conversations ─────────────────────────────────────────────────────

async def create_conversation(
    channel_id: str | None,
    conv_type: str,
    initiator_bot_id: int | None,
    responder_bot_id: int | None,
) -> Conversation:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO conversations (channel_id, type, initiator_bot_id, responder_bot_id)
           VALUES (?, ?, ?, ?)""",
        (channel_id, conv_type, initiator_bot_id, responder_bot_id),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM conversations WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return _row_to_conversation(row)


async def end_conversation(conv_id: int, turn_count: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE conversations SET ended_at = datetime('now'), turn_count = ? WHERE id = ?",
        (turn_count, conv_id),
    )
    await db.commit()


async def get_conversations(limit: int = 50) -> list[Conversation]:
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM conversations ORDER BY started_at DESC LIMIT ?", (limit,)
    )).fetchall()
    return [_row_to_conversation(r) for r in rows]


async def get_bot_conversations(bot_id: int, limit: int = 50) -> list[Conversation]:
    db = await get_db()
    rows = await (await db.execute(
        """SELECT * FROM conversations
           WHERE initiator_bot_id = ? OR responder_bot_id = ?
           ORDER BY started_at DESC LIMIT ?""",
        (bot_id, bot_id, limit),
    )).fetchall()
    return [_row_to_conversation(r) for r in rows]


# ── Messages ──────────────────────────────────────────────────────────

async def create_message(
    conversation_id: int | None,
    bot_id: int | None,
    author_type: str,
    author_name: str,
    content: str,
    image_url: str | None = None,
    image_prompt: str | None = None,
) -> Message:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO messages
               (conversation_id, bot_id, author_type, author_name, content, image_url, image_prompt)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (conversation_id, bot_id, author_type, author_name, content, image_url, image_prompt),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return _row_to_message(row)


async def get_conversation_messages(conv_id: int) -> list[Message]:
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conv_id,)
    )).fetchall()
    return [_row_to_message(r) for r in rows]


async def get_messages(limit: int = 100, bot_id: int | None = None) -> list[Message]:
    db = await get_db()
    if bot_id is not None:
        rows = await (await db.execute(
            "SELECT * FROM messages WHERE bot_id = ? ORDER BY created_at DESC LIMIT ?",
            (bot_id, limit),
        )).fetchall()
    else:
        rows = await (await db.execute(
            "SELECT * FROM messages ORDER BY created_at DESC LIMIT ?", (limit,)
        )).fetchall()
    return [_row_to_message(r) for r in rows]


async def get_messages_for_workout(workout_id: int, limit: int | None = None) -> list[Message]:
    """Return all messages (bot + human) scoped to a specific workout."""
    db = await get_db()
    if limit is not None:
        rows = await (await db.execute(
            """SELECT DISTINCT m.* FROM messages m
               LEFT JOIN bots b ON m.bot_id = b.id
               WHERE b.workout_id = ?
                  OR (m.author_type = 'human' AND m.conversation_id IN (
                        SELECT c.id FROM conversations c
                        JOIN bots b2 ON (b2.id = c.initiator_bot_id OR b2.id = c.responder_bot_id)
                        WHERE b2.workout_id = ?
                      ))
               ORDER BY m.created_at DESC LIMIT ?""",
            (workout_id, workout_id, limit),
        )).fetchall()
    else:
        rows = await (await db.execute(
            """SELECT DISTINCT m.* FROM messages m
               LEFT JOIN bots b ON m.bot_id = b.id
               WHERE b.workout_id = ?
                  OR (m.author_type = 'human' AND m.conversation_id IN (
                        SELECT c.id FROM conversations c
                        JOIN bots b2 ON (b2.id = c.initiator_bot_id OR b2.id = c.responder_bot_id)
                        WHERE b2.workout_id = ?
                      ))
               ORDER BY m.created_at ASC""",
            (workout_id, workout_id),
        )).fetchall()
    return [_row_to_message(r) for r in rows]


# ── Conversation Pairs ────────────────────────────────────────────────

async def count_conversations_between(bot_a_id: int, bot_b_id: int) -> int:
    """Count past conversations between two specific bots."""
    db = await get_db()
    row = await (await db.execute(
        """SELECT COUNT(*) as c FROM conversations
           WHERE (initiator_bot_id = ? AND responder_bot_id = ?)
              OR (initiator_bot_id = ? AND responder_bot_id = ?)""",
        (bot_a_id, bot_b_id, bot_b_id, bot_a_id),
    )).fetchone()
    return row["c"] if row else 0


async def get_pair_counts() -> dict[tuple[int, int], int]:
    db = await get_db()
    rows = await (await db.execute("SELECT * FROM conversation_pairs")).fetchall()
    return {(r["bot_a_id"], r["bot_b_id"]): r["conversation_count"] for r in rows}


async def increment_pair(bot_a_id: int, bot_b_id: int) -> None:
    a, b = min(bot_a_id, bot_b_id), max(bot_a_id, bot_b_id)
    db = await get_db()
    await db.execute(
        """INSERT INTO conversation_pairs (bot_a_id, bot_b_id, conversation_count, last_conversation_at)
           VALUES (?, ?, 1, datetime('now'))
           ON CONFLICT(bot_a_id, bot_b_id)
           DO UPDATE SET conversation_count = conversation_count + 1, last_conversation_at = datetime('now')""",
        (a, b),
    )
    await db.commit()


# ── Grades ────────────────────────────────────────────────────────────

async def create_grade(
    bot_id: int,
    grading_run_id: str,
    objective_score: float,
    quality_score: float,
    human_score: float,
    volume_score: float,
    overall_score: float,
    llm_reasoning: str,
    total_messages: int,
    total_conversations: int,
    human_interactions: int,
) -> Grade:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO grades
           (bot_id, grading_run_id, objective_score, quality_score, human_score, volume_score,
            overall_score, llm_reasoning, total_messages, total_conversations, human_interactions)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (bot_id, grading_run_id, objective_score, quality_score, human_score, volume_score,
         overall_score, llm_reasoning, total_messages, total_conversations, human_interactions),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM grades WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return _row_to_grade(row)


async def get_bot_grades(bot_id: int) -> list[Grade]:
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM grades WHERE bot_id = ? ORDER BY created_at DESC", (bot_id,)
    )).fetchall()
    return [_row_to_grade(r) for r in rows]


async def get_latest_grades() -> list[Grade]:
    """Return the most recent grade for each bot."""
    db = await get_db()
    rows = await (await db.execute(
        """SELECT g.* FROM grades g
           INNER JOIN (
               SELECT bot_id, MAX(created_at) as max_created
               FROM grades GROUP BY bot_id
           ) latest ON g.bot_id = latest.bot_id AND g.created_at = latest.max_created
           ORDER BY g.overall_score DESC"""
    )).fetchall()
    return [_row_to_grade(r) for r in rows]


async def get_grades_by_run(grading_run_id: str) -> list[Grade]:
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM grades WHERE grading_run_id = ? ORDER BY overall_score DESC",
        (grading_run_id,),
    )).fetchall()
    return [_row_to_grade(r) for r in rows]


async def get_grades_for_workout(workout_id: int) -> list[dict]:
    """Return all grade records for a workout, joined with bot info, newest first."""
    db = await get_db()
    rows = await (await db.execute(
        """SELECT g.*, b.student_name, b.bot_name, b.workout_id
           FROM grades g
           INNER JOIN bots b ON g.bot_id = b.id
           WHERE b.workout_id = ?
           ORDER BY g.created_at DESC""",
        (workout_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def get_all_grades_history() -> list[dict]:
    """Return ALL grade records across all workouts, joined with bot info, newest first."""
    db = await get_db()
    rows = await (await db.execute(
        """SELECT g.*, b.student_name, b.bot_name, b.workout_id
           FROM grades g
           INNER JOIN bots b ON g.bot_id = b.id
           ORDER BY g.created_at DESC"""
    )).fetchall()
    return [dict(r) for r in rows]


# ── Admin / Reset ─────────────────────────────────────────────────────

async def get_workout_stats(workout_id: int) -> dict[str, int]:
    """Return bot, message, and conversation counts for a workout."""
    db = await get_db()
    bot_count = (await (await db.execute(
        "SELECT COUNT(*) as c FROM bots WHERE workout_id = ?", (workout_id,)
    )).fetchone())["c"]
    msg_count = (await (await db.execute(
        """SELECT COUNT(*) as c FROM messages m
           LEFT JOIN bots b ON m.bot_id = b.id
           WHERE b.workout_id = ?""", (workout_id,)
    )).fetchone())["c"]
    conv_count = (await (await db.execute(
        """SELECT COUNT(DISTINCT c.id) as c FROM conversations c
           LEFT JOIN bots b ON (b.id = c.initiator_bot_id OR b.id = c.responder_bot_id)
           WHERE b.workout_id = ?""", (workout_id,)
    )).fetchone())["c"]
    return {"bots": bot_count, "messages": msg_count, "conversations": conv_count}


async def get_global_stats() -> dict[str, int]:
    """Return total bot, message, and conversation counts across all workouts."""
    db = await get_db()
    bot_count = (await (await db.execute("SELECT COUNT(*) as c FROM bots")).fetchone())["c"]
    msg_count = (await (await db.execute("SELECT COUNT(*) as c FROM messages")).fetchone())["c"]
    conv_count = (await (await db.execute("SELECT COUNT(*) as c FROM conversations")).fetchone())["c"]
    return {"bots": bot_count, "messages": msg_count, "conversations": conv_count}


async def reset_conversations_for_workout(workout_id: int) -> dict[str, int]:
    """Delete all messages, conversations, grades, and pair counts for a workout."""
    db = await get_db()
    bot_rows = await (await db.execute(
        "SELECT id FROM bots WHERE workout_id = ?", (workout_id,)
    )).fetchall()
    bot_ids = [r["id"] for r in bot_rows]
    if not bot_ids:
        return {"messages": 0, "conversations": 0, "grades": 0}

    ph = ",".join("?" * len(bot_ids))

    # Get all conversation IDs involving these bots (same approach as delete_bot)
    conv_rows = await (await db.execute(
        f"SELECT id FROM conversations WHERE initiator_bot_id IN ({ph}) OR responder_bot_id IN ({ph})",
        bot_ids + bot_ids,
    )).fetchall()
    conv_ids = [r["id"] for r in conv_rows]

    # Delete ALL messages in those conversations (bot AND human messages)
    msg_count = 0
    if conv_ids:
        cph = ",".join("?" * len(conv_ids))
        r1 = await db.execute(f"DELETE FROM messages WHERE conversation_id IN ({cph})", conv_ids)
        msg_count += r1.rowcount
    # Also remove any orphan bot messages not attached to a conversation
    r1b = await db.execute(f"DELETE FROM messages WHERE bot_id IN ({ph})", bot_ids)
    msg_count += r1b.rowcount

    # Now safe to delete conversations (no messages reference them)
    r2 = await db.execute(
        f"DELETE FROM conversations WHERE initiator_bot_id IN ({ph}) OR responder_bot_id IN ({ph})",
        bot_ids + bot_ids,
    )
    r3 = await db.execute(f"DELETE FROM grades WHERE bot_id IN ({ph})", bot_ids)
    await db.execute(
        f"DELETE FROM conversation_pairs WHERE bot_a_id IN ({ph}) OR bot_b_id IN ({ph})",
        bot_ids + bot_ids,
    )
    await db.commit()
    return {"messages": msg_count, "conversations": r2.rowcount, "grades": r3.rowcount}


async def reset_bots_for_workout(workout_id: int) -> dict[str, int]:
    """Delete all bots AND their conversations/messages/grades for a workout."""
    counts = await reset_conversations_for_workout(workout_id)
    db = await get_db()
    # lti_user_bots.bot_id has FK → bots.id; must delete before bots
    bot_rows = await (await db.execute(
        "SELECT id FROM bots WHERE workout_id = ?", (workout_id,)
    )).fetchall()
    bot_ids = [r["id"] for r in bot_rows]
    if bot_ids:
        ph = ",".join("?" * len(bot_ids))
        await db.execute(f"DELETE FROM lti_user_bots WHERE bot_id IN ({ph})", bot_ids)
    r = await db.execute("DELETE FROM bots WHERE workout_id = ?", (workout_id,))
    counts["bots"] = r.rowcount
    await db.commit()
    return counts


async def reset_all_conversations() -> dict[str, int]:
    """Delete all messages, conversations, grades, and pair counts across all workouts."""
    db = await get_db()
    r1 = await db.execute("DELETE FROM messages")
    r2 = await db.execute("DELETE FROM conversations")
    r3 = await db.execute("DELETE FROM grades")
    await db.execute("DELETE FROM conversation_pairs")
    await db.commit()
    return {"messages": r1.rowcount, "conversations": r2.rowcount, "grades": r3.rowcount}


async def reset_all() -> dict[str, int]:
    """Nuclear option — delete everything: all bots and all conversation data."""
    counts = await reset_all_conversations()
    db = await get_db()
    await db.execute("DELETE FROM lti_user_bots")
    r = await db.execute("DELETE FROM bots")
    counts["bots"] = r.rowcount
    await db.commit()
    return counts


# ── Stats ─────────────────────────────────────────────────────────────

async def get_bot_stats(bot_id: int) -> dict[str, int]:
    db = await get_db()
    msg_count = (await (await db.execute(
        "SELECT COUNT(*) as c FROM messages WHERE bot_id = ?", (bot_id,)
    )).fetchone())["c"]
    conv_count = (await (await db.execute(
        "SELECT COUNT(*) as c FROM conversations WHERE initiator_bot_id = ? OR responder_bot_id = ?",
        (bot_id, bot_id),
    )).fetchone())["c"]
    human_count = (await (await db.execute(
        """SELECT COUNT(DISTINCT conversation_id) as c FROM messages
           WHERE conversation_id IN (
               SELECT id FROM conversations WHERE initiator_bot_id = ? OR responder_bot_id = ?
           ) AND author_type = 'human'""",
        (bot_id, bot_id),
    )).fetchone())["c"]
    return {"messages": msg_count, "conversations": conv_count, "human_interactions": human_count}


# ── Auto-grade settings ────────────────────────────────────────────────

async def get_all_auto_grade_settings() -> list[dict]:
    db = await get_db()
    rows = await (await db.execute(
        "SELECT workout_id, interval_hours FROM auto_grade_settings ORDER BY workout_id"
    )).fetchall()
    return [{"workout_id": r["workout_id"], "interval_hours": r["interval_hours"]} for r in rows]


async def get_auto_grade_setting(workout_id: int) -> int | None:
    """Return interval_hours for a workout, or None if not set."""
    db = await get_db()
    row = await (await db.execute(
        "SELECT interval_hours FROM auto_grade_settings WHERE workout_id = ?", (workout_id,)
    )).fetchone()
    return row["interval_hours"] if row else None


async def set_auto_grade_setting(workout_id: int, interval_hours: int) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO auto_grade_settings (workout_id, interval_hours, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(workout_id) DO UPDATE SET
               interval_hours = excluded.interval_hours,
               updated_at     = excluded.updated_at""",
        (workout_id, interval_hours),
    )
    await db.commit()


async def delete_auto_grade_setting(workout_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM auto_grade_settings WHERE workout_id = ?", (workout_id,))
    await db.commit()
