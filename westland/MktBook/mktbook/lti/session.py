"""mktbook_lti cookie sign/verify helpers."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Request

from mktbook.config import settings

LTI_COOKIE_NAME = "mktbook_lti"
LTI_SESSION_MAX_AGE = 8 * 3600  # 8 hours


def make_lti_token(lti_user_id: str) -> str:
    """Create a signed session token embedding the LTI user ID and current timestamp."""
    ts = str(int(time.time()))
    payload = f"{lti_user_id}:{ts}"
    sig = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def verify_lti_token(token: str) -> str | None:
    """Validate a signed LTI token. Returns lti_user_id if valid and not expired, else None."""
    try:
        # Format: {lti_user_id}:{timestamp}.{signature}
        # lti_user_id itself may contain colons, so split from the right on '.'
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(
            settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        # Extract timestamp (last colon-separated segment of payload)
        *id_parts, ts = payload.split(":")
        lti_user_id = ":".join(id_parts)
        if time.time() - int(ts) > LTI_SESSION_MAX_AGE:
            return None
        return lti_user_id
    except Exception:
        return None


def get_lti_user_id(request: Request) -> str | None:
    """Extract and verify the LTI user ID from the request cookie, or None."""
    token = request.cookies.get(LTI_COOKIE_NAME, "")
    return verify_lti_token(token) if token else None
