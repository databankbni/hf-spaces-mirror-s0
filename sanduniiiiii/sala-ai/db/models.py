"""
Sala AI - Database Models
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ChatLog(Base):
    """One row per chat interaction - powers the analytics dashboard."""
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    reply = Column(Text, nullable=False)
    language = Column(String(10), nullable=True)          # si / en / ta
    product_tag = Column(String(255), nullable=True)       # matched product name, if any
    sentiment = Column(String(20), nullable=True)           # positive / neutral / negative
    source = Column(String(20), nullable=True, default="web")  # web / facebook / etc (future use)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ApiQuotaUsage(Base):
    """
    One row per (provider, date). Tracks daily requests/tokens used per
    provider (groq / gemini / openrouter), persisted in Supabase so usage
    survives Space restarts (unlike the old local-JSON-file approach).
    """
    __tablename__ = "api_quota_usage"
    __table_args__ = (UniqueConstraint("provider", "usage_date", name="uq_provider_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(20), nullable=False)      # "groq" / "gemini" / "openrouter"
    usage_date = Column(Date, default=date.today, nullable=False)
    requests = Column(Integer, default=0, nullable=False)
    tokens = Column(Integer, default=0, nullable=False)