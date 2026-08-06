"""
Sala AI - Database Connection Setup
Uses PostgreSQL (Supabase) for chat logging / analytics when DATABASE_URL is
set in the environment; falls back to a local SQLite file otherwise (useful
for quick local testing without a Supabase connection).
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db/sala_ai.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # PostgreSQL (Supabase) - pool_pre_ping avoids errors from stale/dropped
    # connections after the DB has been idle for a while.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables if they don't exist yet. Call this once at app startup."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Yields a DB session (for use as a dependency or plain context)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
