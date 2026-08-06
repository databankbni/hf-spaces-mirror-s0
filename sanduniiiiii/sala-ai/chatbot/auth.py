"""
Sala AI - Admin authentication (HTTP Basic Auth)
"""
import os
import logging
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

log = logging.getLogger("SalaAI")
security = HTTPBasic()

# --- Admin auth (for /admin) ---
ADMIN_USERNAMES = ["sanduni_admin", "sala_admin"]
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "sala1234#")

# ============================================================================
# TEMPORARY: Admin login is DISABLED right now (password login was failing -
# likely a keyboard-layout issue with the "#" character - and /admin access
# was needed immediately). /admin is currently open to anyone with the URL.
#
# TO RE-ENABLE LOGIN LATER:
#   1. Delete the `verify_admin` function below (the no-op one).
#   2. Uncomment the real `verify_admin` function further down.
#   3. Redeploy.
# ============================================================================


def verify_admin() -> str:
    """
    TEMPORARY no-op - admin auth is disabled. Always succeeds, no username/
    password prompt at all. See the block above for how to turn login back on.
    """
    log.warning(
        "verify_admin() is currently DISABLED (no-op) - /admin is open "
        "without a password. Re-enable real auth in chatbot/auth.py when ready."
    )
    return "admin (auth disabled)"


# --- Real admin auth - commented out while login is disabled above ---
# def verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
#     submitted_username = credentials.username.strip()
#     submitted_password = credentials.password.strip()
#
#     correct_username = any(
#         secrets.compare_digest(submitted_username, u) for u in ADMIN_USERNAMES
#     )
#     correct_password = secrets.compare_digest(submitted_password, ADMIN_PASSWORD)
#
#     if not (correct_username and correct_password):
#         log.warning(
#             "Admin login failed - username_ok=%s password_ok=%s "
#             "(submitted username: %r)",
#             correct_username,
#             correct_password,
#             submitted_username,
#         )
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Basic"},
#         )
#     return submitted_username


# --- Demo auth (for /demo) - restricted to @salaent.com emails ---
# Left fully active - only /admin's login was disabled above.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "sala2026#")
ALLOWED_DOMAIN = "@salaent.com"


def verify_demo_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    email = credentials.username.strip().lower()
    submitted_password = credentials.password.strip()

    is_allowed_domain = email.endswith(ALLOWED_DOMAIN)
    correct_password = secrets.compare_digest(submitted_password, DEMO_PASSWORD)

    if not (is_allowed_domain and correct_password):
        log.warning(
            "Demo login failed - domain_ok=%s password_ok=%s (submitted email: %r)",
            is_allowed_domain,
            correct_password,
            email,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access restricted to @salaent.com accounts",
            headers={"WWW-Authenticate": "Basic"},
        )
    return email