"""FastAPI dependency: resolve an optional CallerIdentity from a bearer token.

Design notes
------------
- Auth is **optional**: the API remains accessible without a token. Unauthenticated
  callers get ``CallerIdentity(user_id=None)``.
- A *present but invalid* token returns HTTP 401 — sending a malformed JWT is
  clearly a client error, not a silent fallback.
- ``AuthNotConfiguredError`` (JWT secret not set in the environment) is treated
  as anonymous because CP12 is about **observability**, not access control. The
  API should not degrade in environments that haven't yet wired the secret.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.platform.config import Settings, get_settings
from app.identity.domain.caller import CallerIdentity
from app.identity.infrastructure.supabase_auth import (
    AuthNotConfiguredError,
    InvalidTokenError,
    SupabaseJWTVerifier,
)

_bearer = HTTPBearer(auto_error=False)


def get_optional_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CallerIdentity:
    """Return a ``CallerIdentity`` with ``user_id`` set for authenticated callers.

    Returns ``CallerIdentity(user_id=None)`` when:
    - No ``Authorization`` header is present (anonymous request).
    - The JWT secret is not configured in this environment.

    Raises HTTP 401 when a bearer token is present but cryptographically invalid.
    """
    if credentials is None:
        return CallerIdentity(user_id=None)

    try:
        auth_user = SupabaseJWTVerifier(settings).verify(credentials.credentials)
        return CallerIdentity(user_id=auth_user.id)
    except AuthNotConfiguredError:
        # JWT secret not configured — degrade gracefully to anonymous.
        return CallerIdentity(user_id=None)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from exc
