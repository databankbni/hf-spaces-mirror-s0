"""LTI 1.3 JWT validation and JWKS utilities."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import pathlib
import time
import uuid

import jwt
from jwt import PyJWKClient

log = logging.getLogger(__name__)

# Module-level JWKS client cache keyed by key_set_url
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(key_set_url: str) -> PyJWKClient:
    if key_set_url not in _jwks_clients:
        _jwks_clients[key_set_url] = PyJWKClient(
            key_set_url,
            cache_jwk_set=True,
            lifespan=300,  # cache JWKS for 5 minutes
        )
    return _jwks_clients[key_set_url]


def _validate_jwt_sync(id_token: str, registration: dict, nonce: str) -> dict:
    """Synchronous JWT validation (called via asyncio.to_thread)."""
    client = _get_jwks_client(registration["key_set_url"])
    signing_key = client.get_signing_key_from_jwt(id_token)

    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=registration["client_id"],
        options={"verify_iss": False},  # We verify iss manually below
    )

    if claims.get("iss") != registration["issuer"]:
        raise ValueError(
            f"ISS mismatch: expected {registration['issuer']!r}, got {claims.get('iss')!r}"
        )
    if claims.get("nonce") != nonce:
        raise ValueError("Nonce mismatch — launch may have been replayed or expired")
    return claims


async def validate_launch_jwt(id_token: str, registration: dict, nonce: str) -> dict:
    """Validate an LTI 1.3 launch JWT and return the decoded claims.

    Raises ValueError on any validation failure.
    """
    return await asyncio.to_thread(_validate_jwt_sync, id_token, registration, nonce)


# ── Tool JWKS (public key served to LMS) ───────────────────────────────────

def _int_to_base64url(n: int) -> str:
    byte_len = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()


def load_tool_jwks(private_key_path: str) -> dict:
    """Load the tool RSA private key and return its public key as a JWKS dict."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    pem = pathlib.Path(private_key_path).read_bytes()
    private_key = load_pem_private_key(pem, password=None)
    pub = private_key.public_key()
    numbers = pub.public_numbers()

    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    kid = hashlib.sha256(n_bytes).hexdigest()[:16]

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _int_to_base64url(numbers.n),
                "e": _int_to_base64url(numbers.e),
            }
        ]
    }


def get_tool_kid(private_key_path: str) -> str:
    """Return the kid for the tool's current private key."""
    jwks = load_tool_jwks(private_key_path)
    return jwks["keys"][0]["kid"]


# ── AGS token + score helpers (synchronous, called via to_thread) ───────────

def fetch_ags_token(auth_token_url: str, client_id: str, private_key_pem: str) -> str:
    """Obtain an OAuth2 access token for AGS via JWT client-credentials (RFC 7523)."""
    import requests  # sync; called via asyncio.to_thread

    now = int(time.time())
    assertion_payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": auth_token_url,
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
    }

    assertion = jwt.encode(assertion_payload, private_key_pem, algorithm="RS256")

    resp = requests.post(
        auth_token_url,
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ),
            "client_assertion": assertion,
            "scope": "https://purl.imsglobal.org/spec/lti-ags/scope/score",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def post_ags_score(
    score_url: str,
    lti_user_id: str,
    score_given: float,
    access_token: str,
) -> None:
    """POST a score to an AGS score endpoint."""
    import requests  # sync; called via asyncio.to_thread
    from datetime import datetime, timezone

    payload = {
        "userId": lti_user_id,
        "scoreGiven": score_given,
        "scoreMaximum": 100.0,
        "activityProgress": "Completed",
        "gradingProgress": "FullyGraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    resp = requests.post(
        score_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/vnd.ims.lis.v1.score+json",
        },
        timeout=30,
    )
    resp.raise_for_status()
