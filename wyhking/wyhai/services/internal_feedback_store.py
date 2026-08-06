from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


_SENSITIVE_KEYS = {
    "password", "secret", "secretaccesskey", "accesskeyid", "api_key",
    "apikey", "authorization", "cookie", "token",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 7:
        return "[内容过深，已省略]"
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > 8000:
            return value[:8000] + "…"
        return value
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in list(value.items())[:120]:
            key_text = str(key)
            if key_text.replace("-", "_").lower() in _SENSITIVE_KEYS:
                continue
            result[key_text] = _safe(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth=depth + 1) for item in list(value)[:120]]
    return str(value)[:8000]


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, allow_nan=False, default=str)


def _loads(value: Optional[str]) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


class InternalFeedbackStore:
    """Thread-safe, auditable gray-test interaction and feedback store."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "runtime" / "internal_feedback.sqlite3"
        self.db_path = Path(db_path or os.environ.get("INTERNAL_FEEDBACK_DB_PATH") or default_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    module TEXT NOT NULL,
                    user_question TEXT NOT NULL,
                    request_context_json TEXT NOT NULL,
                    response_context_json TEXT NOT NULL,
                    release_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_interactions_session
                    ON interactions(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id TEXT NOT NULL UNIQUE,
                    turn_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    module TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    user_question TEXT NOT NULL,
                    request_context_json TEXT NOT NULL,
                    response_context_json TEXT NOT NULL,
                    release_version TEXT NOT NULL,
                    simulation_run_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(turn_id) REFERENCES interactions(turn_id)
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_created
                    ON feedback(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_module_rating
                    ON feedback(module, rating, created_at DESC);
                """
            )

    def record_interaction(
        self,
        *,
        turn_id: str,
        session_id: str,
        username: str,
        module: str,
        user_question: str,
        request_context: Dict[str, Any],
        response_context: Dict[str, Any],
        release_version: str,
    ) -> None:
        if not turn_id:
            return
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO interactions(
                    turn_id, session_id, username, module, user_question,
                    request_context_json, response_context_json, release_version, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    username=excluded.username,
                    module=excluded.module,
                    user_question=excluded.user_question,
                    request_context_json=excluded.request_context_json,
                    response_context_json=excluded.response_context_json,
                    release_version=excluded.release_version
                """,
                (
                    str(turn_id), str(session_id or ""), str(username or ""), str(module or ""),
                    str(user_question or ""), _json(request_context), _json(response_context),
                    str(release_version or ""), _now(),
                ),
            )

    def add_feedback(
        self,
        *,
        turn_id: str,
        username: str,
        rating: int,
        comment: str = "",
        tags: Optional[Iterable[str]] = None,
        simulation_run_id: str = "",
    ) -> Dict[str, Any]:
        normalized_rating = int(rating)
        if normalized_rating not in {-1, 0, 1}:
            raise ValueError("rating must be -1, 0 or 1")
        with self._lock, self._connect() as connection:
            interaction = connection.execute(
                "SELECT * FROM interactions WHERE turn_id=?", (str(turn_id),)
            ).fetchone()
            if interaction is None:
                raise KeyError("turn_not_found")
            feedback_id = f"fb_{uuid.uuid4().hex}"
            created_at = _now()
            connection.execute(
                """
                INSERT INTO feedback(
                    feedback_id, turn_id, session_id, username, module, rating,
                    comment, tags_json, user_question, request_context_json,
                    response_context_json, release_version, simulation_run_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id, interaction["turn_id"], interaction["session_id"],
                    str(username or interaction["username"]), interaction["module"],
                    normalized_rating, str(comment or "")[:4000], _json(list(tags or [])),
                    interaction["user_question"], interaction["request_context_json"],
                    interaction["response_context_json"], interaction["release_version"],
                    str(simulation_run_id or "")[:120], created_at,
                ),
            )
        return {"feedback_id": feedback_id, "turn_id": str(turn_id), "created_at": created_at}

    def stats(self) -> Dict[str, Any]:
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) total,
                       SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) positive,
                       SUM(CASE WHEN rating=0 THEN 1 ELSE 0 END) neutral,
                       SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) negative,
                       COUNT(DISTINCT username) users,
                       COUNT(DISTINCT session_id) sessions
                FROM feedback
                """
            ).fetchone()
            by_module = [dict(row) for row in connection.execute(
                "SELECT module, COUNT(*) total, ROUND(AVG(rating), 3) average_rating FROM feedback GROUP BY module ORDER BY module"
            ).fetchall()]
            interaction_total = connection.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        result = dict(totals or {})
        result.update({"interactions": interaction_total, "by_module": by_module})
        for key in ("total", "positive", "neutral", "negative", "users", "sessions"):
            result[key] = int(result.get(key) or 0)
        return result

    def records(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        module: str = "",
        rating: Optional[int] = None,
        simulation_run_id: str = "",
    ) -> Dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if module:
            clauses.append("module=?")
            params.append(module)
        if rating is not None:
            clauses.append("rating=?")
            params.append(int(rating))
        if simulation_run_id:
            clauses.append("simulation_run_id=?")
            params.append(simulation_run_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        with self._connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM feedback{where}", params).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM feedback{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, safe_limit, safe_offset],
            ).fetchall()
        records = []
        for row in rows:
            item = dict(row)
            item["tags"] = _loads(item.pop("tags_json", "[]"))
            item["request_context"] = _loads(item.pop("request_context_json", "{}"))
            item["response_context"] = _loads(item.pop("response_context_json", "{}"))
            records.append(item)
        return {"total": int(total), "limit": safe_limit, "offset": safe_offset, "records": records}

    def export_csv(self) -> str:
        rows = self.records(limit=500, offset=0)["records"]
        output = io.StringIO()
        fields = [
            "feedback_id", "created_at", "username", "module", "rating", "comment",
            "user_question", "tags", "turn_id", "session_id", "release_version",
            "simulation_run_id", "request_context", "response_context",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "tags": _json(row.get("tags")),
                "request_context": _json(row.get("request_context")),
                "response_context": _json(row.get("response_context")),
            })
        return output.getvalue()


_STORE: Optional[InternalFeedbackStore] = None
_STORE_LOCK = threading.Lock()


def get_internal_feedback_store() -> InternalFeedbackStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = InternalFeedbackStore()
    return _STORE
