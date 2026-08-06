"""
Sala AI - Analytics Aggregator
Reads from chat_logs and produces dashboard-ready summaries:
- total interactions
- sentiment breakdown
- most-asked-about products
- most common questions (simple text grouping)
- daily trend (chats per day, for charting)
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from db.database import SessionLocal
from db.models import ChatLog


def get_analytics_summary(days: int = 7) -> dict:
    """
    Returns a summary of chat activity for the last `days` days.
    """
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = db.query(ChatLog).filter(ChatLog.created_at >= since).all()

        total = len(rows)

        sentiment_counts = Counter(r.sentiment or "neutral" for r in rows)

        product_counts = Counter(r.product_tag for r in rows if r.product_tag)
        top_products = product_counts.most_common(10)

        normalized_queries = [
            " ".join(r.query.strip().lower().split()) for r in rows if r.query
        ]
        query_counts = Counter(normalized_queries)
        top_questions = query_counts.most_common(10)

        language_counts = Counter(r.language or "unknown" for r in rows)

        daily = defaultdict(lambda: {"total": 0, "positive": 0, "negative": 0, "neutral": 0})
        for r in rows:
            day_key = r.created_at.strftime("%Y-%m-%d")
            daily[day_key]["total"] += 1
            sentiment = r.sentiment or "neutral"
            if sentiment in daily[day_key]:
                daily[day_key][sentiment] += 1
        daily_trend = [
            {"date": day, **counts} for day, counts in sorted(daily.items())
        ]

        return {
            "period_days": days,
            "total_interactions": total,
            "sentiment_breakdown": dict(sentiment_counts),
            "top_products": [{"product": p, "count": c} for p, c in top_products],
            "top_questions": [{"question": q, "count": c} for q, c in top_questions],
            "language_breakdown": dict(language_counts),
            "daily_trend": daily_trend,
        }
    finally:
        db.close()