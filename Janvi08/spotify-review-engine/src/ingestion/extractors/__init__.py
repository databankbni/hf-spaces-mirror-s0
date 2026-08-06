"""
extractors package — exposes all source-specific extractors.
"""

from __future__ import annotations

from src.ingestion.extractors.app_store import AppStoreExtractor
from src.ingestion.extractors.base_extractor import BaseExtractor
from src.ingestion.extractors.play_store import PlayStoreExtractor
from src.ingestion.extractors.reddit import RedditExtractor
from src.ingestion.extractors.spotify_community import SpotifyCommunityExtractor
from src.ingestion.extractors.trustpilot import TrustpilotExtractor
from src.ingestion.extractors.youtube import YouTubeExtractor

__all__ = [
    "BaseExtractor",
    "PlayStoreExtractor",
    "AppStoreExtractor",
    "RedditExtractor",
    "SpotifyCommunityExtractor",
    "TrustpilotExtractor",
    "YouTubeExtractor",
]
