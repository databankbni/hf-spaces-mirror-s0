from typing import Optional
from datetime import datetime
from models.pricing_config import PricingConfig, PricingTier, PromotionConfig, TrialConfig
from database import get_db_connection
import json


class PricingService:
    """Service for managing pricing and promotions"""
    
    # SQL query constants
    _PRICING_CONFIG_KEY = "pricing_config"
    _GET_PRICING_QUERY = "SELECT value FROM settings WHERE key = 'pricing_config'"
    
    # Default pricing configuration
    DEFAULT_CONFIG = {
        "id": "pricing",
        "pricing": {
            "monthly_price": 59.0,
            "yearly_price": 449.0,
            "currency": "TRY",
            "currency_symbol": "₺"
        },
        "promotion": {
            "enabled": True,
            "discount_percentage": 25,
            "promo_code": "LAUNCH2026",
            "start_date": None,
            "end_date": "2026-02-28T23:59:59",
            "message": "🔥 Lansmana özel %25 indirim!",
            "banner_color": "#ff4d4f"
        },
        "trial": {
            "enabled": True,
            "duration_days": 7,
            "features_included": ["ai_analyst", "scenario_planner", "investment_wizard"]
        },
        "show_discount_banner": True,
        "updated_at": datetime.now().isoformat()
    }
    
    @staticmethod
    async def get_pricing() -> PricingConfig:
        """Get current pricing configuration"""
        db = get_db_connection()
        try:
            result = db.execute(PricingService._GET_PRICING_QUERY).fetchone()
            
            if result:
                config_data = json.loads(result[0])
            else:
                # Initialize with defaults
                await PricingService._initialize_defaults(db)
                config_data = PricingService.DEFAULT_CONFIG
            
            # Parse dates
            if config_data["promotion"].get("start_date"):
                config_data["promotion"]["start_date"] = datetime.fromisoformat(
                    config_data["promotion"]["start_date"]
                )
            if config_data["promotion"].get("end_date"):
                config_data["promotion"]["end_date"] = datetime.fromisoformat(
                    config_data["promotion"]["end_date"]
                )
            
            config_data["updated_at"] = datetime.fromisoformat(config_data["updated_at"])
            
            return PricingConfig(**config_data)
        finally:
            db.close()
    
    @staticmethod
    async def _initialize_defaults(db):
        """Initialize default pricing configuration"""
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (PricingService._PRICING_CONFIG_KEY, json.dumps(PricingService.DEFAULT_CONFIG), datetime.now())
        )
        db.commit()
    
    @staticmethod
    async def update_pricing(updates: dict) -> PricingConfig:
        """Update pricing configuration"""
        db = get_db_connection()
        try:
            # Get current config
            result = db.execute(PricingService._GET_PRICING_QUERY).fetchone()
            
            if not result:
                await PricingService._initialize_defaults(db)
                result = db.execute(PricingService._GET_PRICING_QUERY).fetchone()
            
            config_data = json.loads(result[0])
            
            # Update pricing
            if "monthly_price" in updates:
                config_data["pricing"]["monthly_price"] = updates["monthly_price"]
            if "yearly_price" in updates:
                config_data["pricing"]["yearly_price"] = updates["yearly_price"]
            
            # Update promotion
            if "promotion_enabled" in updates:
                config_data["promotion"]["enabled"] = updates["promotion_enabled"]
            if "discount_percentage" in updates:
                config_data["promotion"]["discount_percentage"] = updates["discount_percentage"]
            if "promo_code" in updates:
                config_data["promotion"]["promo_code"] = updates["promo_code"]
            if "promotion_message" in updates:
                config_data["promotion"]["message"] = updates["promotion_message"]
            if "promotion_end_date" in updates:
                config_data["promotion"]["end_date"] = updates["promotion_end_date"]
            
            # Update trial
            if "trial_enabled" in updates:
                config_data["trial"]["enabled"] = updates["trial_enabled"]
            if "trial_days" in updates:
                config_data["trial"]["duration_days"] = updates["trial_days"]
            
            # Update banner
            if "show_discount_banner" in updates:
                config_data["show_discount_banner"] = updates["show_discount_banner"]
            
            # Update timestamp
            now = datetime.now()
            config_data["updated_at"] = now.isoformat()
            
            # Save to database
            db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                (json.dumps(config_data), now, PricingService._PRICING_CONFIG_KEY)
            )
            db.commit()
            
            # Return updated config
            return await PricingService.get_pricing()
        finally:
            db.close()
    
    @staticmethod
    async def validate_promo_code(code: str) -> dict:
        """Validate a promo code"""
        config = await PricingService.get_pricing()
        
        if not config.promotion.enabled:
            return {"valid": False, "message": "Promosyon aktif değil"}
        
        if config.promotion.promo_code != code:
            return {"valid": False, "message": "Geçersiz promosyon kodu"}
        
        # Check expiry
        if config.promotion.end_date:
            if datetime.now() > config.promotion.end_date:
                return {"valid": False, "message": "Promosyon süresi dolmuş"}
        
        return {
            "valid": True,
            "discount_percentage": config.promotion.discount_percentage,
            "message": f"%{config.promotion.discount_percentage} indirim uygulandı!"
        }
    
    @staticmethod
    async def get_effective_price(tier: str = "yearly") -> dict:
        """Get effective price after discounts"""
        config = await PricingService.get_pricing()
        
        base_price = (
            config.pricing.yearly_price if tier == "yearly" 
            else config.pricing.monthly_price
        )
        
        discount = 0
        if config.promotion.enabled:
            discount = base_price * (config.promotion.discount_percentage / 100)
        
        final_price = base_price - discount
        
        return {
            "tier": tier,
            "base_price": base_price,
            "discount": discount,
            "final_price": final_price,
            "currency": config.pricing.currency,
            "currency_symbol": config.pricing.currency_symbol,
            "promotion_active": config.promotion.enabled,
            "discount_percentage": config.promotion.discount_percentage if config.promotion.enabled else 0
        }
