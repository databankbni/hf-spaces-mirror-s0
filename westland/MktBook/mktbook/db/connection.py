from __future__ import annotations

import logging
import pathlib

import aiosqlite

from mktbook.config import settings

log = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None
_SCHEMA = (pathlib.Path(__file__).parent / "schema.sql").read_text()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.database_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.executescript(_SCHEMA)
        await _db.commit()
        # Migrate existing databases: add workout_id column if missing
        try:
            await _db.execute("ALTER TABLE bots ADD COLUMN workout_id INTEGER NOT NULL DEFAULT 1")
            await _db.commit()
        except Exception:
            pass  # Column already exists

        try:
            await _db.execute("ALTER TABLE messages ADD COLUMN image_url TEXT")
            await _db.commit()
        except Exception:
            pass  # Column already exists

        try:
            await _db.execute("ALTER TABLE messages ADD COLUMN image_prompt TEXT")
            await _db.commit()
        except Exception:
            pass  # Column already exists

        # Migrate: change global UNIQUE on bot_name to per-workout UNIQUE(bot_name, workout_id)
        # Removes orphan bots_new if a previous migration attempt was interrupted.
        # Uses individual execute() calls so PRAGMA foreign_keys=OFF is properly respected.
        try:
            cur = await _db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='bots'"
            )
            row = await cur.fetchone()
            if row and "unique(bot_name, workout_id)" not in row["sql"].lower():
                await _db.execute("PRAGMA foreign_keys=OFF")
                await _db.execute("DROP TABLE IF EXISTS bots_new")
                await _db.execute("""
                    CREATE TABLE bots_new (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_name    TEXT    NOT NULL,
                        bot_name        TEXT    NOT NULL,
                        personality     TEXT    NOT NULL DEFAULT '',
                        objective       TEXT    NOT NULL DEFAULT '',
                        behavior_rules  TEXT    NOT NULL DEFAULT '',
                        is_active       INTEGER NOT NULL DEFAULT 1,
                        workout_id      INTEGER NOT NULL DEFAULT 1,
                        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(bot_name, workout_id)
                    )
                """)
                await _db.execute("""
                    INSERT OR IGNORE INTO bots_new
                        (id, student_name, bot_name, personality, objective,
                         behavior_rules, is_active, workout_id, created_at)
                        SELECT id, student_name, bot_name, personality, objective,
                               behavior_rules, is_active, workout_id, created_at
                        FROM bots
                """)
                await _db.execute("DROP TABLE bots")
                await _db.execute("ALTER TABLE bots_new RENAME TO bots")
                await _db.commit()
                await _db.execute("PRAGMA foreign_keys=ON")
                log.info("Migrated bots table: unique constraint is now per-workout (bot_name, workout_id)")
        except Exception as exc:
            log.warning("bots unique-constraint migration skipped: %s", exc)
            await _db.execute("PRAGMA foreign_keys=ON")

        # LTI 1.3 tables (v1.34+)
        try:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS lti_registrations (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    label          TEXT    NOT NULL,
                    issuer         TEXT    NOT NULL,
                    client_id      TEXT    NOT NULL,
                    auth_login_url TEXT    NOT NULL,
                    auth_token_url TEXT    NOT NULL,
                    key_set_url    TEXT    NOT NULL,
                    deployment_ids TEXT    NOT NULL DEFAULT '[]',
                    is_active      INTEGER NOT NULL DEFAULT 1,
                    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(issuer, client_id)
                )
            """)
            await _db.commit()
        except Exception as exc:
            log.warning("lti_registrations migration skipped: %s", exc)

        try:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS lti_oidc_state (
                    state           TEXT PRIMARY KEY,
                    nonce           TEXT NOT NULL,
                    target_link_uri TEXT NOT NULL,
                    issuer          TEXT NOT NULL,
                    client_id       TEXT NOT NULL,
                    expires_at      TEXT NOT NULL
                )
            """)
            await _db.commit()
        except Exception as exc:
            log.warning("lti_oidc_state migration skipped: %s", exc)

        try:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS lti_sessions (
                    token            TEXT PRIMARY KEY,
                    lti_user_id      TEXT NOT NULL,
                    lti_user_name    TEXT NOT NULL DEFAULT '',
                    lti_user_email   TEXT NOT NULL DEFAULT '',
                    lti_roles        TEXT NOT NULL DEFAULT '[]',
                    issuer           TEXT NOT NULL,
                    client_id        TEXT NOT NULL,
                    deployment_id    TEXT NOT NULL,
                    context_id       TEXT NOT NULL DEFAULT '',
                    resource_link_id TEXT NOT NULL DEFAULT '',
                    workout_id       INTEGER NOT NULL DEFAULT 1,
                    ags_lineitem_url TEXT,
                    ags_score_url    TEXT,
                    ags_token_url    TEXT,
                    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                    expires_at       TEXT NOT NULL
                )
            """)
            await _db.commit()
        except Exception as exc:
            log.warning("lti_sessions migration skipped: %s", exc)

        try:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS auto_grade_settings (
                    workout_id     INTEGER PRIMARY KEY,
                    interval_hours INTEGER NOT NULL,
                    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            await _db.commit()
        except Exception as exc:
            log.warning("auto_grade_settings migration skipped: %s", exc)

        try:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS lti_user_bots (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    lti_user_id TEXT    NOT NULL,
                    issuer      TEXT    NOT NULL,
                    bot_id      INTEGER NOT NULL REFERENCES bots(id),
                    workout_id  INTEGER NOT NULL,
                    linked_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(lti_user_id, issuer, workout_id)
                )
            """)
            await _db.commit()
        except Exception as exc:
            log.warning("lti_user_bots migration skipped: %s", exc)

    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
