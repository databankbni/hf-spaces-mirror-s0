"""
Sala AI - Daily Email Digest
Sends a plain-text summary of chat activity and AI-generated suggestions
to management. Uses Resend's HTTP API (https://resend.com) instead of SMTP,
because SMTP ports (25/465/587) are blocked on Hugging Face Spaces' free tier.
HTTP (port 443) is not blocked, so this works there.

Setup:
1. Sign up at https://resend.com (free tier: 3000 emails/month)
2. Create an API key: Dashboard -> API Keys
3. Add to .env:
     RESEND_API_KEY=re_xxxxxxxxxxxx
     DIGEST_RECIPIENT_EMAIL=someone@example.com
     DIGEST_FROM_EMAIL=onboarding@resend.dev   # or your verified domain sender
4. Make sure "requests" is in requirements.txt (add it if missing).

To schedule this daily, use Render's Cron Job feature (or an external
service like cron-job.org) to hit POST /dashboard/send-digest once a day.
"""

import os
import logging
import requests

from analytics.insights import generate_insights

log = logging.getLogger("SalaAI")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_API_URL = "https://api.resend.com/emails"
DIGEST_RECIPIENT_EMAIL = os.getenv("DIGEST_RECIPIENT_EMAIL")
# Resend requires a verified sender domain in production. Until you verify
# your own domain, "onboarding@resend.dev" works for testing.
DIGEST_FROM_EMAIL = os.getenv("DIGEST_FROM_EMAIL", "onboarding@resend.dev")


def _build_digest_text(days: int = 1) -> str:
    data = generate_insights(days=days)
    summary = data.get("summary", {})
    sentiment = summary.get("sentiment_breakdown", {})
    top_products = summary.get("top_products", [])

    lines = [
        f"Sala AI - daily chat summary (last {days} day(s))",
        "",
        f"Total chats: {summary.get('total_interactions', 0)}",
        f"Positive: {sentiment.get('positive', 0)} | Negative: {sentiment.get('negative', 0)} | Neutral: {sentiment.get('neutral', 0)}",
        "",
        "Top asked products:",
    ]
    if top_products:
        for p in top_products[:5]:
            lines.append(f"  - {p['product']} ({p['count']} mentions)")
    else:
        lines.append("  (no product data yet)")

    lines += ["", "AI suggestions:", data.get("insights", "None available.")]
    return "\n".join(lines)


def send_daily_digest(recipient_email: str | None = None, days: int = 1) -> dict:
    """
    Sends the digest email via Resend's HTTP API.
    Returns {"status": "sent", "recipient": ...} or {"status": "failed", "error": ...}.
    Requires RESEND_API_KEY and a recipient to be configured.
    """
    recipient = recipient_email or DIGEST_RECIPIENT_EMAIL
    if not RESEND_API_KEY or not recipient:
        return {
            "status": "failed",
            "error": "RESEND_API_KEY and DIGEST_RECIPIENT_EMAIL must be set in .env",
        }

    # Support comma-separated multiple recipients, e.g. "a@x.com,b@y.com"
    recipient_list = [r.strip() for r in recipient.split(",") if r.strip()]

    body = _build_digest_text(days=days)

    payload = {
        "from": DIGEST_FROM_EMAIL,
        "to": recipient_list,
        "subject": "Sala AI - daily chat summary",
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return {"status": "sent", "recipient": recipient}
        else:
            log.error(f"Resend API error {resp.status_code}: {resp.text}")
            return {"status": "failed", "error": f"Resend API {resp.status_code}: {resp.text}"}
    except Exception as e:
        log.error(f"Email digest send failed: {e}")
        return {"status": "failed", "error": str(e)}