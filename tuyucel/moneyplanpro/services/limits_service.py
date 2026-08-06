from typing import Optional
from datetime import datetime
from models.limits_config import LimitsConfig, TierLimits, RateLimits, UsageQuotas
from database import get_db_connection
import json


class LimitsService:
    """Service for managing tier limits and restrictions"""
    
    # SQL query constants
    _CONFIG_KEY = "limits_config"
    _GET_CONFIG_QUERY = "SELECT value FROM settings WHERE key = 'limits_config'"
    
    # Default limits configuration
    DEFAULT_CONFIG = {
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
            "max_transactions": -1,  # unlimited
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
        "updated_at": datetime.now().isoformat()
    }
    
    @staticmethod
    async def get_config() -> LimitsConfig:
        """Get current limits configuration"""
        db = get_db_connection()
        try:
            result = db.execute(LimitsService._GET_CONFIG_QUERY).fetchone()
            
            if result:
                config_data = json.loads(result[0])
            else:
                # Initialize with defaults
                await LimitsService._initialize_defaults(db)
                config_data = LimitsService.DEFAULT_CONFIG
            
            return LimitsConfig(**config_data)
        finally:
            db.close()
    
    @staticmethod
    async def _initialize_defaults(db):
        """Initialize default limits configuration"""
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (LimitsService._CONFIG_KEY, 
             json.dumps(LimitsService.DEFAULT_CONFIG), 
             datetime.now())
        )
        db.commit()
    
    @staticmethod
    async def update_config(updates: dict) -> LimitsConfig:
        """Update limits configuration"""
        db = get_db_connection()
        try:
            # Get current config
            result = db.execute(LimitsService._GET_CONFIG_QUERY).fetchone()
            
            if not result:
                await LimitsService._initialize_defaults(db)
                result = db.execute(LimitsService._GET_CONFIG_QUERY).fetchone()
            
            config_data = json.loads(result[0])
            
            # Update Config Data using mapping to reduce cognitive complexity
            update_mapping = {
                "free_tier": {
                    "free_max_transactions": "max_transactions",
                    "free_max_portfolios": "max_portfolios",
                    "free_max_alerts": "max_alerts",
                    "free_max_bank_accounts": "max_bank_accounts",
                    "free_ai_requests_per_day": "ai_requests_per_day",
                    "free_export_per_day": "export_per_day"
                },
                "pro_tier": {
                    "pro_max_transactions": "max_transactions",
                    "pro_max_portfolios": "max_portfolios",
                    "pro_max_alerts": "max_alerts"
                },
                "rate_limits": {
                    "api_calls_per_minute": "api_calls_per_minute",
                    "export_per_hour": "export_per_hour",
                    "ai_requests_per_hour": "ai_requests_per_hour",
                    "search_per_minute": "search_per_minute"
                },
                "quotas": {
                    "max_storage_mb": "max_storage_mb",
                    "max_api_calls_per_day": "max_api_calls_per_day"
                }
            }

            for section, fields in update_mapping.items():
                for update_key, target_key in fields.items():
                    if update_key in updates:
                        config_data[section][target_key] = updates[update_key]

            # Update global settings
            if "enforce_limits" in updates:
                config_data["enforce_limits"] = updates["enforce_limits"]
            
            # Update timestamp
            config_data["updated_at"] = datetime.now().isoformat()
            
            # Save to database
            db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                (json.dumps(config_data), datetime.now(), LimitsService._CONFIG_KEY)
            )
            db.commit()
            
            # Return updated config
            return await LimitsService.get_config()
        finally:
            db.close()
    
    @staticmethod
    async def get_tier_limits(is_pro: bool) -> TierLimits:
        """Get limits for a specific tier"""
        config = await LimitsService.get_config()
        return config.pro_tier if is_pro else config.free_tier
    
    @staticmethod
    async def check_limit(is_pro: bool, limit_type: str, current_count: int) -> dict:
        """Check if user has reached a limit"""
        if not (await LimitsService.get_config()).enforce_limits:
            return {"allowed": True, "limit_reached": False}
        
        limits = await LimitsService.get_tier_limits(is_pro)
        
        # Map limit types to tier limit fields
        limit_map = {
            "transactions": limits.max_transactions,
            "portfolios": limits.max_portfolios,
            "alerts": limits.max_alerts,
            "bank_accounts": limits.max_bank_accounts,
            "ai_requests": limits.ai_requests_per_day,
            "exports": limits.export_per_day
        }
        
        if limit_type not in limit_map:
            return {"allowed": True, "limit_reached": False, "error": "Unknown limit type"}
        
        max_allowed = limit_map[limit_type]
        
        # -1 means unlimited
        if max_allowed == -1:
            return {
                "allowed": True,
                "limit_reached": False,
                "current": current_count,
                "max": "unlimited"
            }
        
        limit_reached = current_count >= max_allowed
        
        return {
            "allowed": not limit_reached,
            "limit_reached": limit_reached,
            "current": current_count,
            "max": max_allowed,
            "remaining": max(0, max_allowed - current_count)
        }
