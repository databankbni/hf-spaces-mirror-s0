from fastapi import Header, HTTPException
import requests

from services.settings_service import settings_service


def require_admin(authorization: str | None = Header(default=None)) -> dict:
    """Validate a Supabase session and require an active admin role."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Admin session is required")

    token = authorization.split(" ", 1)[1].strip()
    supabase_url = settings_service.get_value("SUPABASE_URL")
    anon_key = settings_service.get_value("SUPABASE_ANON_KEY")
    service_key = settings_service.get_value("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not anon_key:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured")

    try:
        auth_response = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Admin session is invalid or expired")

        user = auth_response.json()
        user_id = user.get("id")
        profile_key = service_key or anon_key
        profile_auth = service_key or token
        profile_response = requests.get(
            f"{supabase_url}/rest/v1/users",
            headers={
                "apikey": profile_key,
                "Authorization": f"Bearer {profile_auth}",
                "Accept": "application/vnd.pgrst.object+json",
            },
            params={
                "id": f"eq.{user_id}",
                "select": "id,email,role,is_active,is_banned,deleted_at",
            },
            timeout=10,
        )
        if profile_response.status_code != 200:
            raise HTTPException(status_code=403, detail="Admin profile could not be verified")

        profile = profile_response.json()
        if (
            profile.get("role") not in {"admin", "super_admin"}
            or not profile.get("is_active")
            or profile.get("is_banned")
            or profile.get("deleted_at") is not None
        ):
            raise HTTPException(status_code=403, detail="Admin permission is required")
        return profile
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable") from exc
