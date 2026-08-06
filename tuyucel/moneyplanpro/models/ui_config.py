from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime


class ThemeConfig(BaseModel):
    """UI Theme configuration"""
    primary_color: str = "#1890ff"
    secondary_color: str = "#52c41a"
    dark_mode_supported: bool = True
    default_dark_mode: bool = False
    border_radius: int = 8
    font_family: str = "Roboto"


class LayoutConfig(BaseModel):
    """App Layout configuration"""
    home_style: str = "cards"  # "cards", "list", "minimal"
    show_onboarding: bool = True
    bottom_nav_enabled: bool = True
    sidebar_enabled: bool = False
    chart_style: str = "line"


class UIConfig(BaseModel):
    """Complete UI/UX configuration"""
    id: str = "ui_config"
    theme: ThemeConfig
    layout: LayoutConfig
    custom_assets: Dict[str, Optional[str]] = {}
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "ui_config",
                "theme": {
                    "primary_color": "#1890ff",
                    "secondary_color": "#52c41a",
                    "dark_mode_supported": True,
                    "default_dark_mode": False,
                    "border_radius": 8,
                    "font_family": "Roboto"
                },
                "layout": {
                    "home_style": "cards",
                    "show_onboarding": True,
                    "bottom_nav_enabled": True,
                    "sidebar_enabled": False,
                    "chart_style": "line"
                },
                "custom_assets": {
                    "logo_url": "https://...",
                    "promo_banner": "https://..."
                },
                "updated_at": "2026-01-22T20:00:00"
            }
        }
