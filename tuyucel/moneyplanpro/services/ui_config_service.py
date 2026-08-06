from typing import Optional
from datetime import datetime
from models.ui_config import UIConfig, ThemeConfig, LayoutConfig
from database import get_db_connection
import json


class UIConfigService:
    """Service for managing UI/UX theme and layout settings"""
    
    # SQL query constants
    _CONFIG_KEY = "ui_config"
    _GET_CONFIG_QUERY = "SELECT value FROM settings WHERE key = 'ui_config'"
    
    # Default UI configuration
    DEFAULT_CONFIG = {
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
            "logo_url": None,
            "welcome_banner": None
        },
        "updated_at": datetime.now().isoformat()
    }
    
    @staticmethod
    async def get_config() -> UIConfig:
        """Get current UI/UX configuration"""
        db = get_db_connection()
        try:
            result = db.execute(UIConfigService._GET_CONFIG_QUERY).fetchone()
            
            if result:
                config_data = json.loads(result[0])
            else:
                # Initialize with defaults
                await UIConfigService._initialize_defaults(db)
                config_data = UIConfigService.DEFAULT_CONFIG
            
            # Ensure updated_at is a datetime object
            if isinstance(config_data.get("updated_at"), str):
                config_data["updated_at"] = datetime.fromisoformat(config_data["updated_at"])
            
            return UIConfig(**config_data)
        finally:
            db.close()
    
    @staticmethod
    async def _initialize_defaults(db):
        """Initialize default UI configuration"""
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (UIConfigService._CONFIG_KEY, 
             json.dumps(UIConfigService.DEFAULT_CONFIG), 
             datetime.now())
        )
        db.commit()
    
    @staticmethod
    async def update_config(updates: dict) -> UIConfig:
        """Update UI configuration"""
        db = get_db_connection()
        try:
            # Get current config
            result = db.execute(UIConfigService._GET_CONFIG_QUERY).fetchone()
            
            if not result:
                await UIConfigService._initialize_defaults(db)
                result = db.execute(UIConfigService._GET_CONFIG_QUERY).fetchone()
            
            config_data = json.loads(result[0])
            
            # Update theme
            if "primary_color" in updates:
                config_data["theme"]["primary_color"] = updates["primary_color"]
            if "secondary_color" in updates:
                config_data["theme"]["secondary_color"] = updates["secondary_color"]
            if "dark_mode_supported" in updates:
                config_data["theme"]["dark_mode_supported"] = updates["dark_mode_supported"]
            if "border_radius" in updates:
                config_data["theme"]["border_radius"] = updates["border_radius"]
            
            # Update layout
            if "home_style" in updates:
                config_data["layout"]["home_style"] = updates["home_style"]
            if "show_onboarding" in updates:
                config_data["layout"]["show_onboarding"] = updates["show_onboarding"]
            if "chart_style" in updates:
                config_data["layout"]["chart_style"] = updates["chart_style"]
            
            # Update timestamp
            config_data["updated_at"] = datetime.now().isoformat()
            
            # Save to database
            db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                (json.dumps(config_data), datetime.now(), UIConfigService._CONFIG_KEY)
            )
            db.commit()
            
            return await UIConfigService.get_config()
        finally:
            db.close()
