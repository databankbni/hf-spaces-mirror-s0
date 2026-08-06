from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings


class AuthNotConfiguredError(RuntimeError):
    """Raised when JWT verification settings are intentionally not configured yet."""


class InvalidTokenError(RuntimeError):
    """Raised when a bearer token cannot be verified."""


@dataclass(frozen=True)
class AuthUser:
    id: UUID
    role: str | None
    email: str | None
    claims: dict[str, object]


class SupabaseJWTVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, token: str) -> AuthUser:
        if not self._settings.supabase_jwt_secret:
            raise AuthNotConfiguredError("Supabase JWT secret is not configured")

        try:
            payload = jwt.decode(
                token,
                self._settings.supabase_jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                audience=self._settings.supabase_jwt_audience,
                options={"require": ["sub"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Invalid Supabase JWT") from exc

        return AuthUser(
            id=UUID(str(payload["sub"])),
            role=_claim_as_str(payload.get("role")),
            email=_claim_as_str(payload.get("email")),
            claims=payload,
        )


def _claim_as_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


bearer_scheme = HTTPBearer(auto_error=False)


def get_jwt_verifier(settings: Settings = Depends(get_settings)) -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: SupabaseJWTVerifier = Depends(get_jwt_verifier),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        return verifier.verify(credentials.credentials)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
