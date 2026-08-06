"""
Sala AI - Unified API Quota Tracker
Tracks daily usage across Groq, Gemini, and OpenRouter so the admin
dashboard can show "how much is left today" for each provider.

Persisted in Supabase (ApiQuotaUsage table) instead of a local JSON file,
so usage counts survive Space restarts/redeploys.

Limits below are approximate free-tier reference values (as published by
each provider). They are used only to estimate a remaining percentage -
the providers themselves are still the source of truth for actual limits.
"""

from datetime import date

from db.database import SessionLocal
from db.models import ApiQuotaUsage

# Approximate free-tier daily reference limits (adjust if providers change these)
LIMITS = {
    "groq": {
        "requests_per_day": 1000,
        "tokens_per_day": 100000,
    },
    "gemini": {
        "requests_per_day": 1500,
        "tokens_per_day": 900000,
    },
    "openrouter": {
        "requests_per_day": 1000,   # soft estimate - OpenRouter free models are mainly RPM-limited
        "tokens_per_day": None,     # no fixed daily token cap published
    },
}


def _get_or_create_row(db, provider: str, today: date) -> ApiQuotaUsage:
    row = (
        db.query(ApiQuotaUsage)
        .filter(ApiQuotaUsage.provider == provider, ApiQuotaUsage.usage_date == today)
        .first()
    )
    if row is None:
        row = ApiQuotaUsage(provider=provider, usage_date=today, requests=0, tokens=0)
        db.add(row)
        db.flush()  # get it inserted within this transaction before we update it
    return row


def record_usage(provider: str, requests: int = 1, tokens: int = 0):
    """Call this after every successful API call to a provider."""
    if provider not in LIMITS:
        return
    today = date.today()
    db = SessionLocal()
    try:
        row = _get_or_create_row(db, provider, today)
        row.requests += requests
        row.tokens += tokens
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_quota_summary() -> dict:
    """Returns today's usage + remaining estimate for each provider."""
    today = date.today()
    db = SessionLocal()
    try:
        summary = {"date": str(today), "providers": {}}

        for provider, limits in LIMITS.items():
            row = (
                db.query(ApiQuotaUsage)
                .filter(ApiQuotaUsage.provider == provider, ApiQuotaUsage.usage_date == today)
                .first()
            )
            used_requests = row.requests if row else 0
            used_tokens = row.tokens if row else 0

            req_limit = limits["requests_per_day"]
            tok_limit = limits["tokens_per_day"]

            req_remaining = max(req_limit - used_requests, 0) if req_limit else None
            tok_remaining = max(tok_limit - used_tokens, 0) if tok_limit else None

            req_pct_used = round((used_requests / req_limit) * 100, 1) if req_limit else None
            tok_pct_used = round((used_tokens / tok_limit) * 100, 1) if tok_limit else None

            summary["providers"][provider] = {
                "requests_used": used_requests,
                "requests_limit": req_limit,
                "requests_remaining": req_remaining,
                "requests_pct_used": req_pct_used,
                "tokens_used": used_tokens,
                "tokens_limit": tok_limit,
                "tokens_remaining": tok_remaining,
                "tokens_pct_used": tok_pct_used,
            }

        return summary
    finally:
        db.close()