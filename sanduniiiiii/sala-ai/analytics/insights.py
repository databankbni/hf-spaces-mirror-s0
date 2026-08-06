"""
Sala AI - Insights Generator
"""
import time
from analytics.aggregator import get_analytics_summary
try:
    from core.model_router import get_ai_response
except ImportError:
    get_ai_response = None

_SYSTEM_PROMPT = (
    "You are a business analyst reviewing chatbot activity for an electronics "
    "store (Sala Enterprises, Sri Lanka). You give short, specific, actionable "
    "suggestions to store management based on chat data."
)

# Cache: avoid burning a Groq call every time the dashboard Overview tab loads.
# Insights only need to refresh periodically, not on every page view.
_CACHE_TTL_SECONDS = 3600  # 1 hour
_cache = {"days": None, "timestamp": 0, "result": None}


def _build_prompt(summary: dict) -> str:
    return f"""
Data for the last {summary['period_days']} days:
- Total interactions: {summary['total_interactions']}
- Sentiment breakdown: {summary['sentiment_breakdown']}
- Top products asked about: {summary['top_products']}
- Top questions: {summary['top_questions']}
- Languages used: {summary['language_breakdown']}

Based on this data, write 3-5 short, specific, actionable suggestions for the store management.
Focus on things like: stock/demand signals, customer complaints or negative sentiment patterns,
missing information customers keep asking about, and marketing opportunities.
Keep each suggestion to 1-2 sentences. Return them as a simple numbered list, no extra preamble.
"""


def generate_insights(days: int = 7, force_refresh: bool = False) -> dict:
    """
    Returns AI-generated insights based on recent chat analytics.
    Cached for _CACHE_TTL_SECONDS to avoid an LLM call on every dashboard load.
    Falls back to a plain-text summary if the AI call fails or is unavailable.
    """
    now = time.time()
    cache_fresh = (
        not force_refresh
        and _cache["result"] is not None
        and _cache["days"] == days
        and (now - _cache["timestamp"]) < _CACHE_TTL_SECONDS
    )
    if cache_fresh:
        return _cache["result"]

    summary = get_analytics_summary(days=days)
    if summary["total_interactions"] == 0:
        result = {
            "summary": summary,
            "insights": "No chat activity in this period yet.",
        }
        _cache.update(days=days, timestamp=now, result=result)
        return result

    if get_ai_response is None:
        result = {
            "summary": summary,
            "insights": "AI insights unavailable (model_router not configured).",
        }
        _cache.update(days=days, timestamp=now, result=result)
        return result

    prompt = _build_prompt(summary)
    try:
        ai_text = get_ai_response(prompt, _SYSTEM_PROMPT)
    except Exception as e:
        ai_text = f"AI insights could not be generated right now ({str(e)}). Showing raw stats only."

    result = {
        "summary": summary,
        "insights": ai_text,
    }
    _cache.update(days=days, timestamp=now, result=result)
    return result