from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class FeatureFlag(BaseModel):
    """Feature flag model for remote config"""
    id: str  # e.g., "ai_analyst", "scenario_planner"
    name: str  # Human readable name
    description: str
    is_pro: bool  # Is this a PRO feature?
    is_enabled: bool  # Is this feature enabled globally?
    daily_free_limit: Optional[int] = None  # Daily free usage limit (None = unlimited for free users)
    metadata: Optional[Dict[str, Any]] = None  # Extra config (e.g., {"min_version": "1.2.0"})
    created_at: datetime
    updated_at: datetime


class FeatureFlagUpdate(BaseModel):
    """Update model for feature flags"""
    is_pro: Optional[bool] = None
    is_enabled: Optional[bool] = None
    daily_free_limit: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class FeatureFlagsResponse(BaseModel):
    """Response model for feature flags"""
    features: Dict[str, FeatureFlag]
    version: int  # Increment this when flags change
    cached_until: datetime  # Client should cache until this time
