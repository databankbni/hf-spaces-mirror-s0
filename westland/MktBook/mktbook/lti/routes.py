"""LTI 1.3 endpoints for MktBook."""
from __future__ import annotations

import json
import logging
import pathlib
import re
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mktbook.config import settings
from mktbook.lti import db as lti_db
from mktbook.lti.jwt_validator import load_tool_jwks, validate_launch_jwt
from mktbook.lti.passback import push_grades_to_lms
from mktbook.lti.session import (
    LTI_COOKIE_NAME,
    LTI_SESSION_MAX_AGE,
    get_lti_user_id,
    make_lti_token,
)
from mktbook.web.auth import is_authenticated, redirect_to_login
from mktbook.web.workouts import WORKOUTS, all_workouts, get_workout

log = logging.getLogger(__name__)

router = APIRouter()

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "web" / "templates"
TEMPLATES = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Helpers ────────────────────────────────────────────────────────────────

def _lti_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        "lti_error.html",
        {"request": request, "error_message": message},
        status_code=status_code,
    )


def _extract_workout_id(target_link_uri: str) -> int | None:
    """Extract workout_id from URIs like /lti/inbox/3 or /w/3/platform."""
    m = re.search(r"/(?:lti/inbox|w)/(\d+)", target_link_uri)
    if m:
        wid = int(m.group(1))
        return wid if wid in WORKOUTS else None
    return None


# ── Metadata endpoints ─────────────────────────────────────────────────────

@router.get("/lti/jwks")
async def lti_jwks() -> JSONResponse:
    """Serve the tool's public RSA key as a JWKS document."""
    key_path = settings.lti_private_key_path
    if not pathlib.Path(key_path).exists():
        return JSONResponse(
            {"error": "Private key not configured. Run: openssl genrsa -out "
                       f"{key_path} 2048"},
            status_code=503,
        )
    jwks = load_tool_jwks(key_path)
    return JSONResponse(jwks, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/lti/config")
async def lti_config() -> JSONResponse:
    """Return a Canvas-compatible JSON tool configuration document."""
    base = settings.lti_tool_base_url.rstrip("/")
    config = {
        "title": "MktBook",
        "description": "Marketing Simulation Bot Marketplace",
        "oidc_initiation_url": f"{base}/lti/login",
        "target_link_uri": f"{base}/lti/launch",
        "scopes": [
            "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            "https://purl.imsglobal.org/spec/lti-ags/scope/score",
        ],
        "extensions": [
            {
                "platform": "canvas.instructure.com",
                "settings": {
                    "placements": [
                        {
                            "placement": "assignment_selection",
                            "message_type": "LtiDeepLinkingRequest",
                            "target_link_uri": f"{base}/lti/launch",
                        },
                        {
                            "placement": "link_selection",
                            "message_type": "LtiDeepLinkingRequest",
                            "target_link_uri": f"{base}/lti/launch",
                        },
                    ]
                },
            }
        ],
        "public_jwk_url": f"{base}/lti/jwks",
    }
    return JSONResponse(config)


# ── OIDC Login initiation ──────────────────────────────────────────────────

@router.api_route("/lti/login", methods=["GET", "POST"])
async def lti_login(request: Request) -> Response:
    """OIDC login initiation. Canvas uses GET; Blackboard uses POST."""
    if request.method == "POST":
        form = await request.form()
        get_param = lambda k: str(form.get(k, ""))  # noqa: E731
    else:
        get_param = lambda k: request.query_params.get(k, "")  # noqa: E731

    iss = get_param("iss")
    client_id = get_param("client_id")
    login_hint = get_param("login_hint")
    target_link_uri = get_param("target_link_uri")
    lti_message_hint = get_param("lti_message_hint")

    if not iss or not client_id:
        return _lti_error(request, "Missing required LTI login parameters (iss, client_id).")

    reg = await lti_db.get_registration_by_iss_and_client_id(iss, client_id)
    if not reg:
        return _lti_error(
            request,
            f"This LMS is not registered with MktBook. "
            f"Contact your administrator to register issuer: {iss!r}",
            status_code=403,
        )

    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())

    await lti_db.save_oidc_state(state, nonce, target_link_uri, iss, client_id)

    base = settings.lti_tool_base_url.rstrip("/")
    redirect_uri = f"{base}/lti/launch"

    params: dict[str, str] = {
        "response_type": "id_token",
        "scope": "openid",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "login_hint": login_hint,
        "state": state,
        "nonce": nonce,
        "prompt": "none",
        "response_mode": "form_post",
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint

    auth_url = reg["auth_login_url"] + "?" + urlencode(params)
    return RedirectResponse(url=auth_url, status_code=302)


# ── JWT Launch ─────────────────────────────────────────────────────────────

@router.post("/lti/launch", response_model=None)
async def lti_launch(request: Request) -> Response:
    """Validate the LTI 1.3 JWT launch and create a session."""
    form = await request.form()
    id_token = str(form.get("id_token", ""))
    state = str(form.get("state", ""))

    if not id_token or not state:
        return _lti_error(request, "Invalid launch request — missing id_token or state.")

    # Validate state from DB
    state_row = await lti_db.get_oidc_state(state)
    if not state_row:
        return _lti_error(
            request,
            "Launch expired or invalid. Please return to your course and try the link again.",
        )

    reg = await lti_db.get_registration_by_iss_and_client_id(
        state_row["issuer"], state_row["client_id"]
    )
    if not reg:
        return _lti_error(request, "Platform registration not found.", status_code=403)

    try:
        claims = await validate_launch_jwt(
            id_token=id_token,
            registration=reg,
            nonce=state_row["nonce"],
        )
    except Exception as exc:
        log.error("JWT validation failed: %s", exc)
        return _lti_error(request, f"Launch validation failed: {exc}")

    # Clean up used OIDC state
    await lti_db.delete_oidc_state(state)

    # Extract standard LTI claims
    lti_user_id = claims.get("sub", "")
    lti_user_name = (
        claims.get("name")
        or claims.get("given_name", "")
        or "Student"
    )
    lti_user_email = claims.get("email", "")
    lti_roles: list[str] = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/roles", []
    )
    deployment_id = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id", ""
    )
    message_type = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/message_type", ""
    )
    target_link_uri = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/target_link_uri",
        state_row.get("target_link_uri", ""),
    )

    context_claim = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/context", {}
    ) or {}
    context_id = context_claim.get("id", "")

    resource_link_claim = claims.get(
        "https://purl.imsglobal.org/spec/lti/claim/resource_link", {}
    ) or {}
    resource_link_id = resource_link_claim.get("id", "")

    ags_claim = claims.get(
        "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint", {}
    ) or {}
    ags_lineitem_url: str | None = ags_claim.get("lineitem")
    ags_score_url: str | None = (
        ags_lineitem_url.rstrip("/") + "/scores" if ags_lineitem_url else None
    )
    ags_token_url: str | None = reg["auth_token_url"] if ags_claim else None

    # Handle Deep Linking request
    if message_type == "LtiDeepLinkingRequest":
        dl_settings = claims.get(
            "https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings", {}
        ) or {}
        return TEMPLATES.TemplateResponse(
            "lti_deep_link.html",
            {
                "request": request,
                "workouts": all_workouts(),
                "dl_settings": dl_settings,
                "dl_return_url": dl_settings.get("deep_link_return_url", ""),
                "reg_issuer": reg["issuer"],
                "reg_client_id": reg["client_id"],
                "deployment_id": deployment_id,
                "base_url": settings.lti_tool_base_url.rstrip("/"),
            },
            headers={"Content-Security-Policy": "frame-ancestors *"},
        )

    # Determine workout_id from target_link_uri
    workout_id = _extract_workout_id(target_link_uri) or 1

    # Create LTI session
    session_token = make_lti_token(lti_user_id)
    await lti_db.save_lti_session(
        token=session_token,
        lti_user_id=lti_user_id,
        lti_user_name=lti_user_name,
        lti_user_email=lti_user_email,
        lti_roles=lti_roles,
        issuer=reg["issuer"],
        client_id=reg["client_id"],
        deployment_id=deployment_id,
        context_id=context_id,
        resource_link_id=resource_link_id,
        workout_id=workout_id,
        ags_lineitem_url=ags_lineitem_url,
        ags_score_url=ags_score_url,
        ags_token_url=ags_token_url,
    )

    response = RedirectResponse(url=f"/lti/inbox/{workout_id}", status_code=303)
    response.set_cookie(
        LTI_COOKIE_NAME,
        session_token,
        max_age=LTI_SESSION_MAX_AGE,
        httponly=True,
        samesite="none",
        secure=True,
    )
    return response


# ── InBox page ─────────────────────────────────────────────────────────────

@router.get("/lti/inbox/{workout_id}", response_class=HTMLResponse)
async def lti_inbox(request: Request, workout_id: int) -> Response:
    """The LTI InBox — stripped-down, iframe-friendly platform view."""
    from mktbook.db import queries

    lti_user_id = get_lti_user_id(request)
    if not lti_user_id:
        return _lti_error(
            request,
            "Your session has expired. Please return to your course and click the link again.",
        )

    # Load LTI session for display name / issuer
    token = request.cookies.get(LTI_COOKIE_NAME, "")
    session = await lti_db.get_lti_session(token)
    if not session:
        return _lti_error(
            request,
            "Session not found. Please return to your course and click the link again.",
        )

    workout = get_workout(workout_id)
    if not workout:
        return _lti_error(request, f"Workout #{workout_id} not found.", status_code=404)

    # Check for existing bot link
    linked_bot = await lti_db.get_linked_bot(
        lti_user_id, session["issuer"], workout_id
    )

    # Load all bots for the link-bot dropdown
    bots = await queries.get_all_bots(workout_id=workout_id)

    # Load recent messages for the platform feed
    messages = await queries.get_messages_for_workout(workout_id=workout_id, limit=200)

    resp = TEMPLATES.TemplateResponse(
        "lti_inbox.html",
        {
            "request": request,
            "workout": workout,
            "lti_user_name": session["lti_user_name"],
            "linked_bot": linked_bot,
            "bots": bots,
            "messages": messages,
        },
    )
    resp.headers["Content-Security-Policy"] = "frame-ancestors *"
    return resp


# ── Bot linking ────────────────────────────────────────────────────────────

@router.post("/lti/inbox/{workout_id}/link-bot", response_model=None)
async def lti_link_bot(
    request: Request,
    workout_id: int,
    bot_id: int = Form(...),
) -> Response:
    """Link the current LTI user to one of their registered bots."""
    lti_user_id = get_lti_user_id(request)
    if not lti_user_id:
        return _lti_error(request, "Session expired. Please relaunch from your course.")

    token = request.cookies.get(LTI_COOKIE_NAME, "")
    session = await lti_db.get_lti_session(token)
    if not session:
        return _lti_error(request, "Session not found. Please relaunch from your course.")

    await lti_db.link_user_to_bot(lti_user_id, session["issuer"], bot_id, workout_id)

    return RedirectResponse(url=f"/lti/inbox/{workout_id}", status_code=303)


# ── InBox human post ───────────────────────────────────────────────────────

@router.post("/lti/inbox/{workout_id}/post", response_model=None)
async def lti_inbox_post(
    request: Request,
    workout_id: int,
    message_content: str = Form(...),
) -> Response:
    """Post a human message to the platform from within the InBox."""
    lti_user_id = get_lti_user_id(request)
    if not lti_user_id:
        return RedirectResponse(url=f"/lti/inbox/{workout_id}", status_code=303)

    token = request.cookies.get(LTI_COOKIE_NAME, "")
    session = await lti_db.get_lti_session(token)
    author_name = session["lti_user_name"] if session else "Student"

    fleet = request.app.state.fleet
    if fleet and message_content.strip():
        await fleet.dispatch_human_message(
            workout_id=workout_id,
            author_name=author_name.strip() or "Student",
            content=message_content.strip(),
        )

    return RedirectResponse(url=f"/lti/inbox/{workout_id}", status_code=303)


# ── Grade passback ─────────────────────────────────────────────────────────

@router.post("/lti/passback/{workout_id}")
async def lti_passback(request: Request, workout_id: int) -> JSONResponse:
    """Push grades to the LMS via AGS. Requires admin auth."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await push_grades_to_lms(workout_id)
    return JSONResponse(result)


# ── LTI Admin — platform registrations ────────────────────────────────────

@router.get("/admin/lti", response_class=HTMLResponse)
async def lti_admin_page(request: Request, done: str = "") -> Response:
    if not is_authenticated(request):
        return redirect_to_login("/admin/lti")

    registrations = await lti_db.get_all_registrations()
    for reg in registrations:
        reg["deployment_ids_list"] = json.loads(reg.get("deployment_ids", "[]"))
    base = settings.lti_tool_base_url.rstrip("/")
    return TEMPLATES.TemplateResponse(
        "lti_admin.html",
        {
            "request": request,
            "registrations": registrations,
            "done": done,
            "base_url": base,
            "lti_key_path": settings.lti_private_key_path,
        },
    )


@router.post("/admin/lti/register", response_model=None)
async def lti_admin_register(
    request: Request,
    label: str = Form(...),
    issuer: str = Form(...),
    client_id: str = Form(...),
    auth_login_url: str = Form(...),
    auth_token_url: str = Form(...),
    key_set_url: str = Form(...),
    deployment_ids_raw: str = Form(""),
) -> Response:
    if not is_authenticated(request):
        return redirect_to_login("/admin/lti")

    deployment_ids = [
        line.strip() for line in deployment_ids_raw.splitlines() if line.strip()
    ]
    try:
        await lti_db.create_registration(
            label=label.strip(),
            issuer=issuer.strip(),
            client_id=client_id.strip(),
            auth_login_url=auth_login_url.strip(),
            auth_token_url=auth_token_url.strip(),
            key_set_url=key_set_url.strip(),
            deployment_ids=deployment_ids,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            registrations = await lti_db.get_all_registrations()
            for reg in registrations:
                reg["deployment_ids_list"] = json.loads(reg.get("deployment_ids", "[]"))
            return TEMPLATES.TemplateResponse(
                "lti_admin.html",
                {
                    "request": request,
                    "registrations": registrations,
                    "done": "",
                    "base_url": settings.lti_tool_base_url.rstrip("/"),
                    "lti_key_path": settings.lti_private_key_path,
                    "error": f"A registration already exists for issuer {issuer!r} + client_id {client_id!r}.",
                },
                status_code=400,
            )
        raise

    return RedirectResponse(url="/admin/lti?done=registered", status_code=303)


@router.post("/admin/lti/{reg_id}/delete", response_model=None)
async def lti_admin_delete(request: Request, reg_id: int) -> Response:
    if not is_authenticated(request):
        return redirect_to_login("/admin/lti")

    await lti_db.delete_registration(reg_id)
    return RedirectResponse(url="/admin/lti?done=deleted", status_code=303)


# ── Deep Link response ─────────────────────────────────────────────────────

@router.post("/lti/deep-link/submit", response_model=None)
async def lti_deep_link_submit(
    request: Request,
    workout_id: int = Form(...),
    dl_return_url: str = Form(...),
    reg_issuer: str = Form(...),
    reg_client_id: str = Form(...),
    deployment_id: str = Form(""),
) -> Response:
    """Generate and return a signed LtiDeepLinkingResponse JWT to the LMS."""
    import time as _time

    key_path = settings.lti_private_key_path
    if not pathlib.Path(key_path).exists():
        return _lti_error(request, "Tool private key not configured.", status_code=503)

    workout = get_workout(workout_id)
    if not workout:
        return _lti_error(request, f"Workout #{workout_id} not found.", status_code=404)

    from mktbook.lti.jwt_validator import get_tool_kid

    kid = get_tool_kid(key_path)
    private_key_pem = pathlib.Path(key_path).read_text()
    base = settings.lti_tool_base_url.rstrip("/")
    now = int(_time.time())

    dl_claims = {
        "iss": reg_client_id,
        "aud": reg_issuer,
        "iat": now,
        "exp": now + 600,
        "nonce": str(uuid.uuid4()),
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment_id,
        "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": [
            {
                "type": "ltiResourceLink",
                "title": (
                    f"MktBook \u2014 {workout['icon']} "
                    f"Workout #{workout_id}: {workout['title']}"
                ),
                "url": f"{base}/lti/inbox/{workout_id}",
                "lineItem": {
                    "scoreMaximum": 100,
                    "label": f"MktBook Workout #{workout_id}",
                },
            }
        ],
    }

    import jwt as _jwt

    dl_jwt = _jwt.encode(
        dl_claims,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )

    # Return a self-submitting form that posts the JWT back to the LMS
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Linking Workout…</title></head>
<body>
<p>Linking workout to your course…</p>
<form id="dl-form" method="POST" action="{dl_return_url}">
    <input type="hidden" name="JWT" value="{dl_jwt}">
</form>
<script>document.getElementById('dl-form').submit();</script>
</body>
</html>"""
    return HTMLResponse(
        content=html,
        headers={"Content-Security-Policy": "frame-ancestors *"},
    )
