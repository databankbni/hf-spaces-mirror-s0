"""
config.py — Central configuration for the Spotify Review Discovery Engine.

All constants, caps, endpoints, and paths live here so they can be changed
in one place without touching individual fetcher/extractor files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Project root (two levels up from this file: src/ingestion/config.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Data directories
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = DATA_DIR / "output"

RAW_PLAY_STORE_DIR = RAW_DIR / "play_store"
RAW_APP_STORE_DIR = RAW_DIR / "app_store"
RAW_REDDIT_DIR = RAW_DIR / "reddit"
RAW_SPOTIFY_COMMUNITY_DIR = RAW_DIR / "spotify_community"
RAW_TRUSTPILOT_DIR = RAW_DIR / "trustpilot"
RAW_YOUTUBE_DIR = RAW_DIR / "youtube"

# Create directories if they don't exist
for _d in [
    RAW_PLAY_STORE_DIR,
    RAW_APP_STORE_DIR,
    RAW_REDDIT_DIR,
    RAW_SPOTIFY_COMMUNITY_DIR,
    RAW_TRUSTPILOT_DIR,
    RAW_YOUTUBE_DIR,
    OUTPUT_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Time range
# ---------------------------------------------------------------------------
LOOKBACK_DAYS: int = 120  # 4 months

def get_cutoff_date() -> datetime:
    """Return the earliest date we want reviews from (UTC-aware)."""
    return datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------
VALID_MODES = ("smoke", "full")


@dataclass
class SourceCaps:
    """Review / record caps per source, per run mode."""
    play_store: int
    app_store: int
    reddit: int              # posts + comments combined (manual curation)
    spotify_community: int   # forum threads/replies
    trustpilot: int          # reviews
    youtube: int             # comments


SMOKE_CAPS = SourceCaps(
    play_store=50,
    app_store=50,
    reddit=30,               # manual curation — just validate schema loads
    spotify_community=30,
    trustpilot=30,
    youtube=30,
)
FULL_CAPS = SourceCaps(
    play_store=1500,
    app_store=500,
    reddit=150,              # reduced per ADR-011 (manual curation)
    spotify_community=500,
    trustpilot=300,
    youtube=500,
)


def get_caps(mode: str) -> SourceCaps:
    if mode == "smoke":
        return SMOKE_CAPS
    if mode == "full":
        return FULL_CAPS
    raise ValueError(f"Unknown mode '{mode}'. Choose from: {VALID_MODES}")


# ---------------------------------------------------------------------------
# Google Play Store
# ---------------------------------------------------------------------------
PLAY_STORE_APP_ID = "com.spotify.music"
PLAY_STORE_LANG = "en"
PLAY_STORE_COUNTRY = "us"
PLAY_STORE_DELAY_S: float = 1.0          # seconds between pagination batches
PLAY_STORE_MAX_PAGES: int = 30           # safety cap on pagination iterations


# ---------------------------------------------------------------------------
# Apple App Store
# ---------------------------------------------------------------------------
APP_STORE_APP_ID = "324684580"           # Spotify iOS App ID
APP_STORE_COUNTRIES = ["us", "gb", "in", "ca", "au"]
APP_STORE_RSS_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/id={app_id}/sortby=mostrecent/json"
)
APP_STORE_DELAY_S: float = 1.0          # seconds between page fetches
APP_STORE_MAX_PAGES_PER_COUNTRY: int = 10


# ---------------------------------------------------------------------------
# Reddit (manual curation — see ADR-011)
# ---------------------------------------------------------------------------
REDDIT_SUBREDDITS = [
    "spotify",
    "musicsuggestions",
    "WeAreTheMusicMakers",
]

REDDIT_SEARCH_TERMS = [
    "discover weekly",
    "recommendations",
    "same songs",
    "repeat",
    "stuck in a loop",
    "algorithm",
    "new music",
    "music discovery",
]

# Legacy URLs kept for reference — not used in manual curation mode
REDDIT_NEW_URL = "https://www.reddit.com/r/{subreddit}/new.json?limit=100"
REDDIT_HOT_URL = "https://www.reddit.com/r/{subreddit}/hot.json?limit=100"
REDDIT_COMMENTS_URL = "https://www.reddit.com/comments/{post_id}.json"

REDDIT_USER_AGENT = "SpotifyReviewEngine/1.0 (academic research)"
REDDIT_DELAY_S: float = 2.0             # seconds between ALL requests
REDDIT_MAX_COMMENTS_PER_POST: int = 25
REDDIT_MAX_PAGES_PER_QUERY: int = 5     # max pagination pages per (sub, term)


# ---------------------------------------------------------------------------
# Spotify Community Forum
# ---------------------------------------------------------------------------
SPOTIFY_COMMUNITY_BASE_URL = "https://community.spotify.com"
SPOTIFY_COMMUNITY_BOARDS = [
    # Board/section URL slugs — will be resolved during fetch
    "music",
    "content-questions",
]
SPOTIFY_COMMUNITY_SEARCH_TERMS = [
    "recommendations",
    "discover weekly",
    "algorithm",
    "music discovery",
    "same songs",
    "new music",
]
SPOTIFY_COMMUNITY_DELAY_S: float = 1.5   # seconds between page requests
SPOTIFY_COMMUNITY_MAX_PAGES: int = 20    # max pages per search


# ---------------------------------------------------------------------------
# Trustpilot
# ---------------------------------------------------------------------------
TRUSTPILOT_BASE_URL = "https://www.trustpilot.com/review/www.spotify.com"
TRUSTPILOT_DELAY_S: float = 1.5         # seconds between page requests
TRUSTPILOT_MAX_PAGES: int = 30          # safety cap on pagination


# ---------------------------------------------------------------------------
# YouTube Comments
# ---------------------------------------------------------------------------
YOUTUBE_SEARCH_QUERIES = [
    "Spotify Wrapped",
    "Spotify algorithm",
    "how Spotify recommendations work",
    "Spotify Discover Weekly explained",
    "Spotify music discovery",
]
YOUTUBE_MAX_VIDEOS: int = 10             # max videos to search
YOUTUBE_COMMENTS_PER_VIDEO: int = 100    # max comments per video
YOUTUBE_DELAY_S: float = 0.5            # delay between API calls

def _get_youtube_api_key() -> str:
    """Load YouTube Data API v3 key from environment."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        pass
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    return key

def get_youtube_api_key() -> str:
    """Return the YouTube API key or raise if not set."""
    key = _get_youtube_api_key()
    if not key:
        raise RuntimeError(
            "YouTube API key not found.\n"
            "Set YOUTUBE_API_KEY in your .env file or environment.\n"
            "Get a free key from: https://console.cloud.google.com/apis\n"
            "(Enable 'YouTube Data API v3')"
        )
    return key


# ---------------------------------------------------------------------------
# HTTP settings
# ---------------------------------------------------------------------------
HTTP_TIMEOUT_S: int = 30
HTTP_MAX_RETRIES: int = 3
HTTP_BACKOFF_BASE_S: float = 2.0        # exponential backoff base (seconds)
