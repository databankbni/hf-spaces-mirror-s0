"""AGS grade passback — push MktBook grades to the LMS gradebook."""
from __future__ import annotations

import asyncio
import logging
import pathlib

from mktbook.config import settings
from mktbook.db import queries
from mktbook.lti import db as lti_db
from mktbook.lti.jwt_validator import fetch_ags_token, post_ags_score

log = logging.getLogger(__name__)


async def push_grades_to_lms(workout_id: int) -> dict:
    """Push the latest grades for a workout to the LMS via AGS.

    Returns a summary dict with keys:
        pushed, skipped_unlinked, skipped_no_session, errors
    """
    private_key_path = settings.lti_private_key_path
    if not pathlib.Path(private_key_path).exists():
        return {
            "pushed": 0,
            "skipped_unlinked": 0,
            "skipped_no_session": 0,
            "errors": [f"Private key not found at {private_key_path}"],
        }

    private_key_pem = pathlib.Path(private_key_path).read_text()

    # Get all grades for this workout
    bots = await queries.get_all_bots(workout_id=workout_id)
    bot_ids = {b.id for b in bots}
    all_grades = await queries.get_latest_grades()
    grades = [g for g in all_grades if g.bot_id in bot_ids]

    # Get all user-bot links for this workout
    links = await lti_db.get_all_user_bot_links_for_workout(workout_id)
    link_by_bot_id = {lnk["bot_id"]: lnk for lnk in links}

    pushed = 0
    skipped_unlinked = 0
    skipped_no_session = 0
    errors: list[str] = []

    for grade in grades:
        link = link_by_bot_id.get(grade.bot_id)
        if not link:
            skipped_unlinked += 1
            continue

        # Find a session with AGS configured for this user + workout
        sessions = await lti_db.get_lti_sessions_by_user(
            link["lti_user_id"], workout_id
        )
        ags_session = next(
            (s for s in sessions if s.get("ags_score_url")), None
        )

        if not ags_session:
            skipped_no_session += 1
            continue

        try:
            access_token = await asyncio.to_thread(
                fetch_ags_token,
                ags_session["ags_token_url"],
                ags_session["client_id"],
                private_key_pem,
            )
            await asyncio.to_thread(
                post_ags_score,
                ags_session["ags_score_url"],
                link["lti_user_id"],
                grade.overall_score,
                access_token,
            )
            pushed += 1
            log.info(
                "AGS passback: pushed grade %.1f for user %s bot %d",
                grade.overall_score,
                link["lti_user_id"],
                grade.bot_id,
            )
        except Exception as exc:
            err = f"Bot {grade.bot_id} ({link['lti_user_id']}): {exc}"
            errors.append(err)
            log.error("AGS passback failed: %s", err)

    return {
        "pushed": pushed,
        "skipped_unlinked": skipped_unlinked,
        "skipped_no_session": skipped_no_session,
        "errors": errors,
    }
