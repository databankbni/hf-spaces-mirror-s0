"""Simple cookie-based admin authentication (no extra dependencies)."""
from __future__ import annotations

import hashlib
import hmac
import pathlib
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

from mktbook.config import settings

COOKIE_NAME = "mktbook_admin"
SESSION_MAX_AGE = 8 * 3600  # 8 hours

# Password override file — lives next to the DB so it survives deploys
_PASSWORD_FILE = pathlib.Path(settings.database_path).parent / "admin_password.txt"


def get_password() -> str:
    """Return the current admin password (file override beats config default)."""
    try:
        pw = _PASSWORD_FILE.read_text().strip()
        if pw == "mktbook" or not pw:
            return settings.admin_password
        return pw
    except OSError:
        return settings.admin_password


def set_password(new_password: str) -> None:
    """Persist a new admin password to the override file."""
    _PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PASSWORD_FILE.write_text(new_password.strip())


def _sign(value: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()


def make_session_cookie() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def verify_session_cookie(token: str) -> bool:
    try:
        ts, sig = token.split(".", 1)
        if not hmac.compare_digest(_sign(ts), sig):
            return False
        return time.time() - int(ts) <= SESSION_MAX_AGE
    except Exception:
        return False


def is_authenticated(request: Request) -> bool:
    return verify_session_cookie(request.cookies.get(COOKIE_NAME, ""))


def redirect_to_login(next_url: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={next_url}", status_code=302)
