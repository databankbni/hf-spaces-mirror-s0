"""LTI 1.3 database operations."""
from __future__ import annotations

import json
import logging

from mktbook.db.connection import get_db

log = logging.getLogger(__name__)


# ── Registrations ──────────────────────────────────────────────────────────

async def get_active_registrations() -> list[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM lti_registrations WHERE is_active = 1 ORDER BY label")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_registrations() -> list[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM lti_registrations ORDER BY created_at DESC")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_registration_by_iss_and_client_id(issuer: str, client_id: str) -> dict | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM lti_registrations WHERE issuer = ? AND client_id = ? AND is_active = 1",
        (issuer, client_id),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def create_registration(
    label: str,
    issuer: str,
    client_id: str,
    auth_login_url: str,
    auth_token_url: str,
    key_set_url: str,
    deployment_ids: list[str],
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO lti_registrations
           (label, issuer, client_id, auth_login_url, auth_token_url, key_set_url, deployment_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (label, issuer, client_id, auth_login_url, auth_token_url, key_set_url,
         json.dumps(deployment_ids)),
    )
    await db.commit()


async def delete_registration(reg_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM lti_registrations WHERE id = ?", (reg_id,))
    await db.commit()


# ── OIDC State ─────────────────────────────────────────────────────────────

async def save_oidc_state(
    state: str,
    nonce: str,
    target_link_uri: str,
    issuer: str,
    client_id: str,
) -> None:
    db = await get_db()
    # Lazy-clean expired states
    await db.execute("DELETE FROM lti_oidc_state WHERE expires_at < datetime('now')")
    await db.execute(
        """INSERT OR REPLACE INTO lti_oidc_state
           (state, nonce, target_link_uri, issuer, client_id, expires_at)
           VALUES (?, ?, ?, ?, ?, datetime('now', '+10 minutes'))""",
        (state, nonce, target_link_uri, issuer, client_id),
    )
    await db.commit()


async def get_oidc_state(state: str) -> dict | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM lti_oidc_state WHERE state = ? AND expires_at > datetime('now')",
        (state,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def delete_oidc_state(state: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM lti_oidc_state WHERE state = ?", (state,))
    await db.commit()


# ── Sessions ───────────────────────────────────────────────────────────────

async def save_lti_session(
    token: str,
    lti_user_id: str,
    lti_user_name: str,
    lti_user_email: str,
    lti_roles: list[str],
    issuer: str,
    client_id: str,
    deployment_id: str,
    context_id: str,
    resource_link_id: str,
    workout_id: int,
    ags_lineitem_url: str | None,
    ags_score_url: str | None,
    ags_token_url: str | None,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO lti_sessions (
               token, lti_user_id, lti_user_name, lti_user_email, lti_roles,
               issuer, client_id, deployment_id, context_id, resource_link_id,
               workout_id, ags_lineitem_url, ags_score_url, ags_token_url,
               expires_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+8 hours'))""",
        (
            token, lti_user_id, lti_user_name, lti_user_email, json.dumps(lti_roles),
            issuer, client_id, deployment_id, context_id, resource_link_id,
            workout_id, ags_lineitem_url, ags_score_url, ags_token_url,
        ),
    )
    await db.commit()


async def get_lti_session(token: str) -> dict | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM lti_sessions WHERE token = ? AND expires_at > datetime('now')",
        (token,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_lti_sessions_by_user(lti_user_id: str, workout_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        """SELECT * FROM lti_sessions
           WHERE lti_user_id = ? AND workout_id = ?
           ORDER BY created_at DESC""",
        (lti_user_id, workout_id),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── User-Bot Links ─────────────────────────────────────────────────────────

async def link_user_to_bot(
    lti_user_id: str, issuer: str, bot_id: int, workout_id: int
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO lti_user_bots (lti_user_id, issuer, bot_id, workout_id)
           VALUES (?, ?, ?, ?)""",
        (lti_user_id, issuer, bot_id, workout_id),
    )
    await db.commit()


async def get_linked_bot(
    lti_user_id: str, issuer: str, workout_id: int
) -> dict | None:
    db = await get_db()
    cur = await db.execute(
        """SELECT ub.*, b.bot_name, b.student_name, b.personality, b.objective
           FROM lti_user_bots ub
           JOIN bots b ON ub.bot_id = b.id
           WHERE ub.lti_user_id = ? AND ub.issuer = ? AND ub.workout_id = ?""",
        (lti_user_id, issuer, workout_id),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_linked_bot_ids_for_workout(workout_id: int) -> set[int]:
    db = await get_db()
    cur = await db.execute(
        "SELECT bot_id FROM lti_user_bots WHERE workout_id = ?",
        (workout_id,),
    )
    rows = await cur.fetchall()
    return {r["bot_id"] for r in rows}


async def get_all_user_bot_links_for_workout(workout_id: int) -> list[dict]:
    """Returns all user-bot links for a workout (for grade passback)."""
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM lti_user_bots WHERE workout_id = ?",
        (workout_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
