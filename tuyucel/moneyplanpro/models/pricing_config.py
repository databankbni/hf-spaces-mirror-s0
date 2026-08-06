from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PricingTier(BaseModel):
    """Pricing tier configuration"""
    monthly_price: float
    yearly_price: float
    currency: str = "TRY"
    currency_symbol: str = "₺"


class PromotionConfig(BaseModel):
    """Promotion/discount configuration"""
    enabled: bool
    discount_percentage: int
    promo_code: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    message: Optional[str] = None
    banner_color: str = "#ff4d4f"


class TrialConfig(BaseModel):
    """Free trial configuration"""
    enabled: bool
    duration_days: int
    features_included: list[str] = []


class PricingConfig(BaseModel):
    """Complete pricing configuration"""
    id: str = "pricing"
    pricing: PricingTier
    promotion: PromotionConfig
    trial: TrialConfig
    show_discount_banner: bool = True
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
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
                    "end_date": "2026-02-01T00:00:00",
                    "message": "🔥 İlk 1000 kullanıcıya özel %25 indirim!",
                    "banner_color": "#ff4d4f"
                },
                "trial": {
                    "enabled": True,
                    "duration_days": 7,
                    "features_included": ["ai_analyst", "scenario_planner"]
                },
                "show_discount_banner": True,
                "updated_at": "2026-01-22T20:00:00"
            }
        }


class PricingUpdate(BaseModel):
    """Update model for pricing config"""
    monthly_price: Optional[float] = None
    yearly_price: Optional[float] = None
    promotion_enabled: Optional[bool] = None
    discount_percentage: Optional[int] = None
    promo_code: Optional[str] = None
    trial_enabled: Optional[bool] = None
    trial_days: Optional[int] = None
