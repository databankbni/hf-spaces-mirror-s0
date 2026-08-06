"""
Sala AI - Analytics Logger
Saves every chat interaction into the database for later analysis.
"""

import logging
from db.database import SessionLocal
from db.models import ChatLog
from analytics.sentiment import detect_sentiment
from analytics.product_tagger import tag_product

log = logging.getLogger("SalaAI")


def log_interaction(query: str, reply: str, language: str = None, source: str = "web"):
    """
    Call this after every chat response.
    Runs sentiment + product tagging, then writes one row to chat_logs.
    Safe to call as a background task - never raises to the caller.
    """
    try:
        sentiment = detect_sentiment(query)
        product = tag_product(query)

        db = SessionLocal()
        try:
            entry = ChatLog(
                query=query,
                reply=reply,
                language=language,
                product_tag=product,
                sentiment=sentiment,
                source=source,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        log.error(f"Analytics logging failed: {e}")