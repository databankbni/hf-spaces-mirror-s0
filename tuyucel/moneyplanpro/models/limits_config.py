from pydantic import BaseModel
from typing import Optional


class TierLimits(BaseModel):
    """Limits for a specific tier (free/pro)"""
    max_transactions: int
    max_portfolios: int
    max_alerts: int
    max_bank_accounts: int
    ai_requests_per_day: int
    export_per_day: int
    can_use_email_sync: bool = False
    can_use_advanced_charts: bool = False
    can_use_ai_analyst: bool = False


class RateLimits(BaseModel):
    """Rate limiting configuration"""
    api_calls_per_minute: int = 60
    export_per_hour: int = 10
    ai_requests_per_hour: int = 20
    search_per_minute: int = 30


class UsageQuotas(BaseModel):
    """Usage quotas and fair use policy"""
    max_storage_mb: int = 100
    max_api_calls_per_day: int = 10000
    max_concurrent_sessions: int = 3
    data_retention_days: int = 365


class LimitsConfig(BaseModel):
    """Complete limits configuration"""
    id: str = "limits"
    free_tier: TierLimits
    pro_tier: TierLimits
    rate_limits: RateLimits
    quotas: UsageQuotas
    enforce_limits: bool = True  # Global kill switch
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "limits",
                "free_tier": {
                    "max_transactions": 100,
                    "max_portfolios": 3,
                    "max_alerts": 5,
                    "max_bank_accounts": 2,
                    "ai_requests_per_day": 1,
                    "export_per_day": 1,
                    "can_use_email_sync": False,
                    "can_use_advanced_charts": False,
                    "can_use_ai_analyst": False
                },
                "pro_tier": {
                    "max_transactions": -1,
                    "max_portfolios": -1,
                    "max_alerts": -1,
                    "max_bank_accounts": -1,
                    "ai_requests_per_day": -1,
                    "export_per_day": -1,
                    "can_use_email_sync": True,
                    "can_use_advanced_charts": True,
                    "can_use_ai_analyst": True
                },
                "rate_limits": {
                    "api_calls_per_minute": 60,
                    "export_per_hour": 10,
                    "ai_requests_per_hour": 20,
                    "search_per_minute": 30
                },
                "quotas": {
                    "max_storage_mb": 100,
                    "max_api_calls_per_day": 10000,
                    "max_concurrent_sessions": 3,
                    "data_retention_days": 365
                },
                "enforce_limits": True,
                "updated_at": "2026-01-22T20:00:00"
            }
        }


class LimitsUpdate(BaseModel):
    """Update model for limits config"""
    # Free tier
    free_max_transactions: Optional[int] = None
    free_max_portfolios: Optional[int] = None
    free_max_alerts: Optional[int] = None
    free_ai_requests_per_day: Optional[int] = None
    
    # Pro tier
    pro_max_transactions: Optional[int] = None
    pro_max_portfolios: Optional[int] = None
    pro_max_alerts: Optional[int] = None
    
    # Rate limits
    api_calls_per_minute: Optional[int] = None
    export_per_hour: Optional[int] = None
    
    # Global
    enforce_limits: Optional[bool] = None
