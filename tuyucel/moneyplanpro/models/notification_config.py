from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AnnouncementConfig(BaseModel):
    """In-app announcement banner configuration"""
    enabled: bool
    type: str = "info"  # "info", "warning", "success", "error"
    title: Optional[str] = None
    message: str
    action_url: Optional[str] = None
    action_text: Optional[str] = None
    dismissible: bool = True
    icon: Optional[str] = None
    background_color: Optional[str] = None


class MaintenanceConfig(BaseModel):
    """Maintenance mode configuration"""
    enabled: bool
    message: str = "Bakım çalışması devam ediyor"
    estimated_end: Optional[datetime] = None
    show_countdown: bool = False
    allow_pro_users: bool = False


class ForceUpdateConfig(BaseModel):
    """Force update configuration"""
    enabled: bool
    min_version: str  # e.g., "1.2.0"
    message: str = "Lütfen uygulamayı güncelleyin"
    blocking: bool = True  # If true, app won't work without update
    store_url_ios: Optional[str] = None
    store_url_android: Optional[str] = None


class NotificationConfig(BaseModel):
    """Complete notification configuration"""
    id: str = "notifications"
    announcement: AnnouncementConfig
    maintenance: MaintenanceConfig
    force_update: ForceUpdateConfig
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "notifications",
                "announcement": {
                    "enabled": True,
                    "type": "success",
                    "title": "Yeni Özellik!",
                    "message": "🎉 AI Portföy Analisti artık kullanımda!",
                    "action_url": "/tools/ai-analyst",
                    "action_text": "Dene",
                    "dismissible": True,
                    "icon": "celebration",
                    "background_color": "#52c41a"
                },
                "maintenance": {
                    "enabled": False,
                    "message": "Bakım çalışması: 22:00-23:00",
                    "estimated_end": "2026-01-23T23:00:00",
                    "show_countdown": True,
                    "allow_pro_users": False
                },
                "force_update": {
                    "enabled": False,
                    "min_version": "1.2.0",
                    "message": "Yeni sürüm mevcut. Lütfen güncelleyin.",
                    "blocking": False,
                    "store_url_ios": "https://apps.apple.com/...",
                    "store_url_android": "https://play.google.com/..."
                },
                "updated_at": "2026-01-22T20:00:00"
            }
        }


class NotificationUpdate(BaseModel):
    """Update model for notification config"""
    # Announcement
    announcement_enabled: Optional[bool] = None
    announcement_type: Optional[str] = None
    announcement_title: Optional[str] = None
    announcement_message: Optional[str] = None
    announcement_action_url: Optional[str] = None
    announcement_dismissible: Optional[bool] = None
    
    # Maintenance
    maintenance_enabled: Optional[bool] = None
    maintenance_message: Optional[str] = None
    maintenance_end: Optional[str] = None
    
    # Force Update
    force_update_enabled: Optional[bool] = None
    force_update_min_version: Optional[str] = None
    force_update_blocking: Optional[bool] = None
