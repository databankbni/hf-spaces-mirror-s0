import json
import logging
import os
from database import get_db_connection

logger = logging.getLogger(__name__)

class SettingsService:
    SENSITIVE_KEYS = {
        "BINANCE_API_KEY",
        "COINGECKO_API_KEY",
        "TWELVEAPI_TOKEN",
        "FMP_API_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "APNS_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_PRIVATE_KEY",
        "ONESIGNAL_APP_ID",
        "ONESIGNAL_REST_API_KEY",
        "APPLE_IAP_KEY_ID",
        "APPLE_IAP_ISSUER_ID",
        "APPLE_IAP_PRIVATE_KEY",
        "GEMINI_API_KEY",
    }
    # External provider credentials may be rotated from the authenticated admin
    # dashboard. A configured dashboard value takes precedence over a stale
    # Space environment value; empty dashboard fields still fall back to env.
    DASHBOARD_FIRST_KEYS = {
        "BINANCE_API_KEY",
        "COINGECKO_API_KEY",
        "TWELVEAPI_TOKEN",
        "FMP_API_KEY",
        "ONESIGNAL_APP_ID",
        "ONESIGNAL_REST_API_KEY",
        "APNS_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_PRIVATE_KEY",
        "APPLE_IAP_KEY_ID",
        "APPLE_IAP_ISSUER_ID",
        "APPLE_IAP_PRIVATE_KEY",
        "GEMINI_API_KEY",
    }
    ENVIRONMENT_OVERRIDES = {
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "APNS_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_BUNDLE_ID",
        "APNS_PRIVATE_KEY",
        "APPLE_IAP_KEY_ID",
        "APPLE_IAP_ISSUER_ID",
        "APPLE_IAP_PRIVATE_KEY",
        "APPLE_IAP_BUNDLE_ID",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
    }

    def __init__(self):
        self._cache = {}
        self._init_table()
        self._load_cache()

    def _init_table(self):
        try:
            conn = get_db_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    description TEXT,
                    category TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Seed default settings if empty
            defaults = [
                ("COINGECKO_API_KEY", "", "Optional CoinGecko Demo API Key", "api_keys"),
                ("TWELVEAPI_TOKEN", "", "Twelve Data API Key for Global Stocks", "api_keys"),
                ("FMP_API_KEY", "", "Legacy FMP API Key (optional)", "api_keys"),
                ("NEWS_SOURCES", json.dumps([
                    {"name": "Bloomberg HT", "url": "https://www.bloomberght.com/rss"},
                    {"name": "Habertürk", "url": "https://www.haberturk.com/rss/ekonomi.xml"},
                    {"name": "Investing", "url": "https://tr.investing.com/rss/news.rss"}
                ]), "Active RSS News Sources", "content"),
                ("ENABLE_FEAR_GREED", "true", "Toggle Crypto Fear & Greed Index", "features"),
                ("SUPABASE_URL", "https://fadzhvakdivhisnmfyqn.supabase.co", "Supabase API URL", "api_keys"),
                ("SUPABASE_ANON_KEY", "sb_publishable_l9-UK9xkD4sV5PBYGuZnaA_-FD-k_hB", "Supabase Publishable Key", "api_keys"),
                ("SUPABASE_SERVICE_ROLE_KEY", "", "Supabase Service Role Key (CRITICAL: Private)", "api_keys"),
                ("APNS_KEY_ID", "", "Apple Push Notifications key ID", "api_keys"),
                ("APNS_TEAM_ID", "", "Apple Developer team ID", "api_keys"),
                ("APNS_BUNDLE_ID", "pro.moneyplan.app", "iOS push notification topic", "api_keys"),
                ("APNS_PRIVATE_KEY", "", "Apple APNs .p8 private key (CRITICAL: Private)", "api_keys"),
                ("APPLE_IAP_KEY_ID", "", "App Store Connect API key ID", "api_keys"),
                ("APPLE_IAP_ISSUER_ID", "", "App Store Connect issuer ID", "api_keys"),
                ("APPLE_IAP_PRIVATE_KEY", "", "App Store Connect .p8 private key (CRITICAL: Private)", "api_keys"),
                ("APPLE_IAP_BUNDLE_ID", "pro.moneyplan.app", "App Store bundle ID", "api_keys"),
                ("GEMINI_API_KEY", "", "Google Gemini API key (CRITICAL: Private)", "api_keys"),
                ("GEMINI_MODEL", "gemini-3.1-flash-lite", "Gemini model used by the backend", "features"),
                ("ALERT_MONITOR_ENABLED", "1", "Enable/Disable Price Alert Monitoring", "features"),
                ("ALERT_MONITOR_INTERVAL_SEC", "60", "Monitoring check interval in seconds", "performance")
            ]
            
            cursor = conn.cursor()
            for key, val, desc, cat in defaults:
                cursor.execute("INSERT OR IGNORE INTO app_settings (key, value, description, category) VALUES (?, ?, ?, ?)", (key, val, desc, cat))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing settings table: {e}")

    def _load_cache(self):
        try:
            conn = get_db_connection()
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            conn.close()
            self._cache = {row["key"]: row["value"] for row in rows}
        except Exception as e:
            logger.error(f"Error loading settings cache: {e}")

    def get_all(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT * FROM app_settings").fetchall()
        conn.close()
        settings = [dict(r) for r in rows]
        
        # Deployment credentials must reflect the Space environment even when
        # the persistent SQLite database still contains values from an older
        # Supabase project.
        for s in settings:
            env_val = os.getenv(s["key"])
            if env_val and (
                s["key"] in self.ENVIRONMENT_OVERRIDES or not s.get("value")
            ):
                s["value"] = env_val
            if s["key"] in self.SENSITIVE_KEYS:
                s["is_configured"] = bool(s.get("value"))
                s["value"] = ""
        return settings

    def update(self, key, value):
        try:
            conn = get_db_connection()
            row = conn.execute(
                "SELECT 1 FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                conn.close()
                return False

            if key in self.SENSITIVE_KEYS and not value:
                conn.close()
                return False

            conn.execute(
                "UPDATE app_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                (value, key),
            )
            conn.commit()
            conn.close()
            self._cache[key] = value
            return True
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")
            return False

    def get_value(self, key, default=None):
        dashboard_val = self._cache.get(key)
        if key in self.DASHBOARD_FIRST_KEYS and dashboard_val:
            return dashboard_val

        # Space-level Supabase credentials are the deployment source of truth.
        if key in self.ENVIRONMENT_OVERRIDES:
            env_val = os.getenv(key)
            if env_val:
                return env_val

        # 1. Check cache (DB values populate cache)
        if dashboard_val:
            return dashboard_val
        
        # 2. Check os.environ if DB/Cache is empty
        env_val = os.getenv(key)
        if env_val:
            return env_val
        
        # 3. Last fallback to DB just in case cache missed (shouldn't happen)
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            conn.close()
            if row and row["value"]:
                self._cache[key] = row["value"]
                return row["value"]
        except:
            pass

        return default

settings_service = SettingsService()
