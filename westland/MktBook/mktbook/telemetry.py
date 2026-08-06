"""Usage telemetry — sends an email on first page load per IP per day.

Data collected and transmitted:
  - IP address of the visitor
  - Approximate geographic location (city, region, country) via ip-api.com
  - ISP name via ip-api.com
  - LTI user email (when launched via Canvas/Blackboard; otherwise "not available")
  - Browser User-Agent string
  - Requested URL and timestamp

Emails are sent via Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD in .env)
to the address configured in TELEMETRY_RECIPIENT.
Each IP address is recorded at most once per calendar day; server restarts
reset the in-memory deduplication table.

See MANUAL.md § Data Collection for the instructor-facing description.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)

# In-memory deduplication: set of (ip, iso_date) tuples.
# Cleared on server restart — intentional; a daily email per IP is the goal.
_seen: set[tuple[str, str]] = set()


def _get_ip(request: "Request") -> str:
    """Return the real client IP, honouring X-Forwarded-For from a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_private(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1", "unknown") or ip.startswith(
        ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
         "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
         "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")
    )


async def _geolocate(ip: str) -> dict:
    """Look up IP location via ip-api.com (free, no API key required)."""
    if _is_private(ip):
        return {"city": "localhost", "regionName": "", "country": "local", "isp": ""}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "city,regionName,country,isp"},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        logger.debug("Telemetry geo lookup failed: %s", exc)
    return {}


def _send_gmail_sync(subject: str, body: str, gmail_user: str, gmail_app_password: str, recipient: str) -> None:
    """Send email via Gmail SMTP using STARTTLS (runs in a thread pool)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(msg)


async def _send_email(subject: str, body: str) -> None:
    from mktbook.config import settings

    if not settings.gmail_user or not settings.gmail_app_password:
        logger.warning("Telemetry: GMAIL_USER or GMAIL_APP_PASSWORD not configured — skipping email")
        return

    try:
        await asyncio.to_thread(
            _send_gmail_sync,
            subject,
            body,
            settings.gmail_user,
            settings.gmail_app_password,
            settings.telemetry_recipient,
        )
    except Exception as exc:
        logger.warning("Telemetry email error: %s", exc)


async def _fire(request: "Request", ip: str, lti_email: str | None) -> None:
    """Background task: geolocate + send email."""
    geo = await _geolocate(ip)
    location_parts = [p for p in [geo.get("city"), geo.get("regionName"), geo.get("country")] if p]
    location = ", ".join(location_parts) or "Unknown"
    isp = geo.get("isp") or "Unknown"

    user_agent = request.headers.get("user-agent", "unknown")
    url = str(request.url)
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    body = (
        "MktBook Access Notification\n"
        "============================\n"
        f"Timestamp  : {ts}\n"
        f"IP Address : {ip}\n"
        f"Location   : {location}\n"
        f"ISP        : {isp}\n"
        f"User Email : {lti_email or 'Not available (no LTI session)'}\n"
        f"User-Agent : {user_agent}\n"
        f"URL        : {url}\n"
        "\n"
        "--\n"
        "This notification is sent automatically by MktBook.\n"
        "See MANUAL.md § Data Collection for details.\n"
    )
    subject = f"MktBook: visitor from {location} ({ip})"
    await _send_email(subject, body)


async def maybe_send_telemetry(
    request: "Request",
    lti_user_email: str | None = None,
) -> None:
    """Send a telemetry email if this is the first visit from this IP today.

    Returns immediately; the actual geolocation + email work runs as a
    background asyncio task so the HTTP response is never delayed.
    """
    from mktbook.config import settings

    if not settings.telemetry_enabled:
        return

    ip = _get_ip(request)
    today = datetime.date.today().isoformat()
    key = (ip, today)
    if key in _seen:
        return
    _seen.add(key)

    asyncio.create_task(_fire(request, ip, lti_user_email))
