"""CallerIdentity — the resolved identity of the HTTP caller."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CallerIdentity:
    """Represents who is making the API call.

    ``user_id`` is ``None`` when the request carries no bearer token (anonymous
    call) or when the JWT secret is not configured in the current environment.
    ``user_id`` is set when a valid Supabase JWT is present and verified.
    """

    user_id: UUID | None
