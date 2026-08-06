from fastapi import Header, HTTPException
import requests

from services.settings_service import settings_service


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Validate a Supabase access token and return the authenticated user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor")

    token = authorization.split(" ", 1)[1].strip()
    supabase_url = settings_service.get_value("SUPABASE_URL")
    anon_key = settings_service.get_value("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise HTTPException(
            status_code=503,
            detail="Supabase kimlik doğrulaması yapılandırılmamış",
        )

    try:
        response = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail="Kimlik doğrulama servisine ulaşılamıyor",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Oturum geçersiz veya süresi dolmuş")
    user = response.json()
    user["_access_token"] = token
    return user
