"""
Sala AI - Conversation History Tracker
Keeps a short rolling history per session so follow-up questions
("what about its features?") make sense to the LLM.

NOTE: This is in-memory (resets when the server restarts). Good enough
for a single-instance dev/production server. For multi-instance deployments,
this should move to Redis or a DB table instead.
"""

import time
import uuid
from collections import defaultdict, deque

MAX_TURNS = 4          # how many past exchanges to remember per session
SESSION_TTL_SECONDS = 60 * 30  # forget a session after 30 minutes of inactivity

_histories = defaultdict(lambda: deque(maxlen=MAX_TURNS))
_last_seen = {}


def new_session_id() -> str:
    return str(uuid.uuid4())


def _cleanup_expired():
    now = time.time()
    expired = [sid for sid, ts in _last_seen.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        _last_seen.pop(sid, None)
        _histories.pop(sid, None)


def add_exchange(session_id: str, user_message: str, bot_reply_en: str):
    """Store one turn (user message + the LLM's English reply) for this session."""
    if not session_id:
        return
    _cleanup_expired()
    _histories[session_id].append({"user": user_message, "bot": bot_reply_en})
    _last_seen[session_id] = time.time()


def get_history_text(session_id: str) -> str | None:
    """Returns the recent conversation as plain text, or None if there's no history yet."""
    if not session_id or session_id not in _histories or not _histories[session_id]:
        return None

    lines = []
    for turn in _histories[session_id]:
        lines.append(f"User: {turn['user']}")
        lines.append(f"Assistant: {turn['bot']}")
    return "\n".join(lines)