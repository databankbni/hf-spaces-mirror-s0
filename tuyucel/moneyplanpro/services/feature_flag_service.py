from typing import Dict, Optional
from datetime import datetime, timedelta
from models.feature_flag import FeatureFlag, FeatureFlagsResponse
import json


class FeatureFlagService:
    """Service for managing feature flags"""

    # SQL sabit — tekrar eden sorgu (SonarLint S1192)
    _SQL_GET_FLAGS = "SELECT value FROM settings WHERE key = 'feature_flags'"
    _SQL_GET_FLAGS_WITH_TS = "SELECT value, updated_at FROM settings WHERE key = 'feature_flags'"

    # Default feature flags (fallback if DB is empty)
    DEFAULT_FLAGS = {
        "crypto_market_data": {
            "id": "crypto_market_data",
            "name": "Kripto Piyasa Verileri",
            "description": "CoinGecko kaynaklı kripto fiyatları ve grafikler (15 dk önbellek)",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": None,
            "metadata": {
                "provider": "CoinGecko",
                "attribution_url": "https://www.coingecko.com/en/api",
                "attribution_text": "Powered by CoinGecko",
                "cache_minutes": 15,
                "commercial_plan_required": True,
                "release_blocker": "coingecko_commercial_license",
            },
        },
        "market_ticker": {
            "id": "market_ticker",
            "name": "Kripto Kayan Yazısı",
            "description": "CoinGecko kaynaklı kripto fiyatlarının üstteki kayan akışı",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": None,
            "metadata": {
                "provider": "CoinGecko",
                "depends_on": "crypto_market_data",
                "source_scope": "crypto_only",
                "policy_version": 2,
            },
        },
        "market_news": {
            "id": "market_news",
            "name": "Piyasa Haberleri",
            "description": "Yazılı yayın izni doğrulanmış finans haber akışı",
            "is_pro": False,
            "is_enabled": False,
            "daily_free_limit": None,
            "metadata": {
                "source_scope": "licensed_news_only",
                "release_blocker": "news_republication_permission",
                "policy_version": 2,
            },
        },
        "financial_calendar": {
            "id": "financial_calendar",
            "name": "Finansal Takvim",
            "description": "Yönetim panelinden girilen, kaynağı doğrulanmış etkinlikler",
            "is_pro": False,
            "is_enabled": False,
            "daily_free_limit": None,
            "metadata": {
                "source_scope": "admin_curated_official_events",
                "release_blocker": "calendar_source_process",
                "policy_version": 2,
            },
        },
        "financial_calendar_fxstreet": {
            "id": "financial_calendar_fxstreet",
            "name": "FXStreet Takvim Yedeği",
            "description": "Finansal takvim boşsa FXStreet verisini yedek kaynak olarak kullanır",
            "is_pro": False,
            "is_enabled": False,
            "daily_free_limit": None,
            "metadata": {
                "depends_on": "financial_calendar",
                "provider": "FXStreet",
                "release_blocker": "fxstreet_api_license_and_credentials",
                "source_scope": "disabled_unlicensed_fallback",
            },
        },
        "live_market_data": {
            "id": "live_market_data",
            "name": "Canlı Piyasa Verileri",
            "description": "BIST, fon, hisse, döviz, altın ve teknik analiz ekranları",
            "is_pro": False,
            "is_enabled": False,
            "daily_free_limit": None,
            "metadata": {"release_blocker": "commercial_data_license"}
        },
        "gmail_import": {
            "id": "gmail_import",
            "name": "Gmail İçe Aktarma",
            "description": "Google OAuth ile e-posta işlemlerini cüzdana aktarma",
            "is_pro": True,
            "is_enabled": False,
            "daily_free_limit": 0,
            "metadata": {"release_blocker": "google_oauth_verification"}
        },
        "ai_features": {
            "id": "ai_features",
            "name": "AI Eğitim Özellikleri",
            "description": "Gemini kullanan analiz, ekstre okuma ve eğitim özetleri",
            "is_pro": True,
            "is_enabled": False,
            "daily_free_limit": 0,
            "metadata": {"release_blocker": "gemini_key_and_terms"}
        },
        "ai_analyst": {
            "id": "ai_analyst",
            "name": "AI Portföy Analisti",
            "description": "Yapay zeka ile portföy analizi ve öneriler",
            "is_pro": True,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"min_version": "1.0.0"}
        },
        "scenario_planner": {
            "id": "scenario_planner",
            "name": "Gelecek Simülasyonu",
            "description": "30 yıllık finansal projeksiyon",
            "is_pro": True,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"min_version": "1.0.0"}
        },
        "investment_wizard": {
            "id": "investment_wizard",
            "name": "Yatırım Asistanı",
            "description": "Risk ve getiri analizi",
            "is_pro": True,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"min_version": "1.0.0"}
        },
        "import_statement_ai": {
            "id": "import_statement_ai",
            "name": "AI Ekstre Okuma",
            "description": "Banka ekstresini AI ile otomatik işleme",
            "is_pro": True,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"min_version": "1.0.0"}
        },
        "email_automation": {
            "id": "email_automation",
            "name": "E-posta Otomasyonu",
            "description": "Gmail entegrasyonu ile otomatik işlem",
            "is_pro": True,
            "is_enabled": True,
            "daily_free_limit": 0,
            "metadata": {"min_version": "1.0.0"}
        },
        "export_csv": {
            "id": "export_csv",
            "name": "CSV Export",
            "description": "İşlemleri CSV olarak dışa aktar",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"show_ad": True}
        },
        "export_pdf": {
            "id": "export_pdf",
            "name": "PDF Export",
            "description": "İşlemleri PDF olarak dışa aktar",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": 1,
            "metadata": {"show_ad": True}
        },
        "compound_interest": {
            "id": "compound_interest",
            "name": "Bileşik Faiz Hesaplayıcı",
            "description": "Bileşik faiz ve yatırım hesaplaması",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": None,
            "metadata": {}
        },
        "loan_calculator": {
            "id": "loan_calculator",
            "name": "Kredi & Mevduat Hesaplayıcı",
            "description": "Kredi ve mevduat hesaplama araçları",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": None,
            "metadata": {}
        },
        "credit_card_assistant": {
            "id": "credit_card_assistant",
            "name": "Kredi Kartı Asistanı",
            "description": "Kredi kartı yönetimi ve öneriler",
            "is_pro": False,
            "is_enabled": True,
            "daily_free_limit": None,
            "metadata": {}
        }
    }

    @staticmethod
    def _apply_release_policy(flags_data: dict, now: Optional[datetime] = None) -> bool:
        """Apply one-time safety defaults without blocking later admin choices."""
        changed = False
        policy_time = now or datetime.now()

        for flag_id in ("market_ticker", "market_news", "financial_calendar"):
            default_flag = FeatureFlagService.DEFAULT_FLAGS[flag_id]
            current_flag = flags_data.get(flag_id)
            if not current_flag:
                continue

            metadata = current_flag.get("metadata") or {}
            if metadata.get("policy_version", 0) >= 2:
                continue

            current_flag.update({
                "name": default_flag["name"],
                "description": default_flag["description"],
                "is_pro": default_flag["is_pro"],
                "is_enabled": default_flag["is_enabled"],
                "daily_free_limit": default_flag["daily_free_limit"],
                "metadata": default_flag["metadata"],
                "updated_at": policy_time.isoformat(),
            })
            changed = True

        return changed
    
    @staticmethod
    async def get_all_flags() -> FeatureFlagsResponse:
        """Get all feature flags from database"""
        from database import get_db_connection
        db = get_db_connection()
        try:
            # Get from settings table
            result = db.execute(
                FeatureFlagService._SQL_GET_FLAGS_WITH_TS
            ).fetchone()
            
            if result:
                flags_data = json.loads(result[0])
                # result[1] should be a datetime object now due to detect_types
                ts = result[1]
                if hasattr(ts, 'timestamp'):
                    version = int(ts.timestamp())
                elif isinstance(ts, str):
                    try:
                        # SQLite format YYYY-MM-DD HH:MM:SS
                        version = int(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp())
                    except (ValueError, TypeError):
                        version = int(datetime.now().timestamp())
                else:
                    version = int(datetime.now().timestamp())
            else:
                # Initialize with defaults
                await FeatureFlagService._initialize_defaults(db)
                flags_data = FeatureFlagService.DEFAULT_FLAGS
                version = int(datetime.now().timestamp())

            # Add newly introduced flags without overwriting choices already
            # made in the dashboard.
            missing_flags = {
                flag_id: flag_data
                for flag_id, flag_data in FeatureFlagService.DEFAULT_FLAGS.items()
                if flag_id not in flags_data
            }
            now = datetime.now()
            flags_changed = bool(missing_flags)
            if missing_flags:
                for flag_id, flag_data in missing_flags.items():
                    flags_data[flag_id] = {
                        **flag_data,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat()
                    }

            # One-time release policy migration. News redistribution and the old
            # unauthenticated calendar fallback must be explicitly reviewed
            # before an administrator can enable them again.
            flags_changed = (
                FeatureFlagService._apply_release_policy(flags_data, now)
                or flags_changed
            )

            if flags_changed:
                db.execute(
                    "UPDATE settings SET value = ?, updated_at = ? WHERE key = 'feature_flags'",
                    (json.dumps(flags_data), now)
                )
                db.commit()
                version = int(now.timestamp())
            
            # Convert to FeatureFlag objects
            features = {}
            for flag_id, flag_data in flags_data.items():
                # Ensure created_at and updated_at exist
                if "created_at" not in flag_data:
                    flag_data["created_at"] = datetime.now()
                if "updated_at" not in flag_data:
                    flag_data["updated_at"] = datetime.now()
                    
                features[flag_id] = FeatureFlag(**flag_data)
            
            return FeatureFlagsResponse(
                features=features,
                version=version,
                cached_until=datetime.now() + timedelta(minutes=5)
            )
        finally:
            db.close()
    
    @staticmethod
    async def _initialize_defaults(db):
        """Initialize default feature flags in database"""
        now = datetime.now()
        flags_with_timestamps = {}
        
        for flag_id, flag_data in FeatureFlagService.DEFAULT_FLAGS.items():
            flags_with_timestamps[flag_id] = {
                **flag_data,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat()
            }
        
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("feature_flags", json.dumps(flags_with_timestamps), now)
        )
        db.commit()
    
    @staticmethod
    async def update_flag(flag_id: str, updates: dict) -> Optional[FeatureFlag]:
        """Update a specific feature flag"""
        from database import get_db_connection
        db = get_db_connection()
        try:
            # Get current flags
            result = db.execute(
                FeatureFlagService._SQL_GET_FLAGS
            ).fetchone()
            
            if not result:
                await FeatureFlagService._initialize_defaults(db)
                result = db.execute(
                    FeatureFlagService._SQL_GET_FLAGS
                ).fetchone()
            
            flags_data = json.loads(result[0])
            
            if flag_id not in flags_data:
                return None
            
            # Update the flag
            now = datetime.now()
            for key, value in updates.items():
                if value is not None:
                    flags_data[flag_id][key] = value
            
            flags_data[flag_id]["updated_at"] = now.isoformat()
            
            # Save back to database
            db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = 'feature_flags'",
                (json.dumps(flags_data), now)
            )
            db.commit()
            
            return FeatureFlag(
                **flags_data[flag_id],
                created_at=datetime.fromisoformat(flags_data[flag_id]["created_at"]),
                updated_at=now
            )
        finally:
            db.close()
    
    @staticmethod
    async def get_flag(flag_id: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag"""
        flags_response = await FeatureFlagService.get_all_flags()
        return flags_response.features.get(flag_id)
    
    @staticmethod
    async def is_feature_available(flag_id: str, is_pro_user: bool) -> bool:
        """Check if a feature is available for a user"""
        flag = await FeatureFlagService.get_flag(flag_id)
        
        if not flag or not flag.is_enabled:
            return False
        
        # If feature is not PRO, it's available to everyone
        if not flag.is_pro:
            return True
        
        # If user is PRO, they have access
        if is_pro_user:
            return True
        
        # If feature has daily free limit > 0, it's available (usage tracking is separate)
        if flag.daily_free_limit and flag.daily_free_limit > 0:
            return True
        
        return False

    @staticmethod
    def is_enabled_sync(flag_id: str, default: bool = False) -> bool:
        """Read a global kill switch for synchronous FastAPI dependencies."""
        from database import get_db_connection

        db = get_db_connection()
        try:
            result = db.execute(
                FeatureFlagService._SQL_GET_FLAGS
            ).fetchone()
            if result:
                flags_data = json.loads(result[0])
                if FeatureFlagService._apply_release_policy(flags_data):
                    now = datetime.now()
                    db.execute(
                        "UPDATE settings SET value = ?, updated_at = ? WHERE key = 'feature_flags'",
                        (json.dumps(flags_data), now),
                    )
                    db.commit()
                flag = flags_data.get(flag_id)
                if flag is not None:
                    return bool(flag.get("is_enabled", False))

            fallback = FeatureFlagService.DEFAULT_FLAGS.get(flag_id)
            if fallback is not None:
                return bool(fallback.get("is_enabled", False))
            return default
        except (TypeError, json.JSONDecodeError):
            return default
        finally:
            db.close()
