from typing import Optional
from datetime import datetime
from models.notification_config import (
    NotificationConfig,
    AnnouncementConfig,
    MaintenanceConfig,
    ForceUpdateConfig
)
from database import get_db_connection
import json


class NotificationConfigService:
    """Service for managing in-app notifications and announcements"""
    
    # SQL query constants
    _CONFIG_KEY = "notification_config"
    _GET_CONFIG_QUERY = "SELECT value FROM settings WHERE key = 'notification_config'"
    
    # Default notification configuration
    DEFAULT_CONFIG = {
        "id": "notifications",
        "announcement": {
            "enabled": False,
            "type": "info",
            "title": None,
            "message": "",
            "action_url": None,
            "action_text": None,
            "dismissible": True,
            "icon": None,
            "background_color": None
        },
        "maintenance": {
            "enabled": False,
            "message": "Bakım çalışması devam ediyor. Kısa süre sonra tekrar deneyin.",
            "estimated_end": None,
            "show_countdown": False,
            "allow_pro_users": False
        },
        "force_update": {
            "enabled": False,
            "min_version": "1.0.0",
            "message": "Yeni sürüm mevcut. Lütfen uygulamayı güncelleyin.",
            "blocking": False,
            "store_url_ios": None,
            "store_url_android": None
        },
        "updated_at": datetime.now().isoformat()
    }
    
    @staticmethod
    async def get_config() -> NotificationConfig:
        """Get current notification configuration"""
        db = get_db_connection()
        try:
            result = db.execute(NotificationConfigService._GET_CONFIG_QUERY).fetchone()
            
            if result:
                config_data = json.loads(result[0])
            else:
                # Initialize with defaults
                await NotificationConfigService._initialize_defaults(db)
                config_data = NotificationConfigService.DEFAULT_CONFIG
            
            # Parse dates
            if config_data["maintenance"].get("estimated_end"):
                config_data["maintenance"]["estimated_end"] = datetime.fromisoformat(
                    config_data["maintenance"]["estimated_end"]
                )
            
            config_data["updated_at"] = datetime.fromisoformat(config_data["updated_at"])
            
            return NotificationConfig(**config_data)
        finally:
            db.close()
    
    @staticmethod
    async def _initialize_defaults(db):
        """Initialize default notification configuration"""
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (NotificationConfigService._CONFIG_KEY, 
             json.dumps(NotificationConfigService.DEFAULT_CONFIG), 
             datetime.now())
        )
        db.commit()
    
    @staticmethod
    async def update_config(updates: dict) -> NotificationConfig:
        """Update notification configuration"""
        db = get_db_connection()
        try:
            # Get current config
            result = db.execute(NotificationConfigService._GET_CONFIG_QUERY).fetchone()
            
            if not result:
                await NotificationConfigService._initialize_defaults(db)
                result = db.execute(NotificationConfigService._GET_CONFIG_QUERY).fetchone()
            
            config_data = json.loads(result[0])
            
            # Update announcement
            if "announcement_enabled" in updates:
                config_data["announcement"]["enabled"] = updates["announcement_enabled"]
            if "announcement_type" in updates:
                config_data["announcement"]["type"] = updates["announcement_type"]
            if "announcement_title" in updates:
                config_data["announcement"]["title"] = updates["announcement_title"]
            if "announcement_message" in updates:
                config_data["announcement"]["message"] = updates["announcement_message"]
            if "announcement_action_url" in updates:
                config_data["announcement"]["action_url"] = updates["announcement_action_url"]
            if "announcement_action_text" in updates:
                config_data["announcement"]["action_text"] = updates["announcement_action_text"]
            if "announcement_dismissible" in updates:
                config_data["announcement"]["dismissible"] = updates["announcement_dismissible"]
            if "announcement_icon" in updates:
                config_data["announcement"]["icon"] = updates["announcement_icon"]
            if "announcement_background_color" in updates:
                config_data["announcement"]["background_color"] = updates["announcement_background_color"]
            
            # Update maintenance
            if "maintenance_enabled" in updates:
                config_data["maintenance"]["enabled"] = updates["maintenance_enabled"]
            if "maintenance_message" in updates:
                config_data["maintenance"]["message"] = updates["maintenance_message"]
            if "maintenance_end" in updates:
                config_data["maintenance"]["estimated_end"] = updates["maintenance_end"]
            if "maintenance_show_countdown" in updates:
                config_data["maintenance"]["show_countdown"] = updates["maintenance_show_countdown"]
            if "maintenance_allow_pro" in updates:
                config_data["maintenance"]["allow_pro_users"] = updates["maintenance_allow_pro"]
            
            # Update force update
            if "force_update_enabled" in updates:
                config_data["force_update"]["enabled"] = updates["force_update_enabled"]
            if "force_update_min_version" in updates:
                config_data["force_update"]["min_version"] = updates["force_update_min_version"]
            if "force_update_message" in updates:
                config_data["force_update"]["message"] = updates["force_update_message"]
            if "force_update_blocking" in updates:
                config_data["force_update"]["blocking"] = updates["force_update_blocking"]
            if "force_update_store_url_ios" in updates:
                config_data["force_update"]["store_url_ios"] = updates["force_update_store_url_ios"]
            if "force_update_store_url_android" in updates:
                config_data["force_update"]["store_url_android"] = updates["force_update_store_url_android"]
            
            # Update timestamp
            now = datetime.now()
            config_data["updated_at"] = now.isoformat()
            
            # Save to database
            db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                (json.dumps(config_data), now, NotificationConfigService._CONFIG_KEY)
            )
            db.commit()
            
            # Return updated config
            return await NotificationConfigService.get_config()
        finally:
            db.close()
    
    @staticmethod
    async def check_version_requirement(current_version: str) -> dict:
        """Check if app version meets minimum requirement"""
        config = await NotificationConfigService.get_config()
        
        if not config.force_update.enabled:
            return {"update_required": False}
        
        # Simple version comparison (assumes semantic versioning)
        def version_tuple(v):
            return tuple(map(int, v.split('.')))
        
        try:
            current = version_tuple(current_version)
            required = version_tuple(config.force_update.min_version)
            
            update_required = current < required
            
            return {
                "update_required": update_required,
                "blocking": config.force_update.blocking if update_required else False,
                "message": config.force_update.message if update_required else None,
                "min_version": config.force_update.min_version,
                "current_version": current_version,
                "store_url_ios": config.force_update.store_url_ios,
                "store_url_android": config.force_update.store_url_android
            }
        except Exception:
            # If version parsing fails, don't block
            return {"update_required": False}
