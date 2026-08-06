import sqlite3
import os
from datetime import datetime


_APP_DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def _resolve_data_directory() -> tuple[str, bool]:
    """Return a writable database directory and whether it survives Space restarts.

    Hugging Face Spaces' repository filesystem is ephemeral. A read-write
    Storage Bucket can be mounted at /data (or an operator can provide an
    explicit MONEYPLAN_DATA_DIR), so prefer that location for mutable runtime
    state such as dashboard settings, feature flags and notification history.
    """
    configured_directory = os.getenv("MONEYPLAN_DATA_DIR")
    candidate = configured_directory or (
        "/data" if os.path.isdir("/data") else _APP_DIRECTORY
    )
    try:
        os.makedirs(candidate, exist_ok=True)
        return candidate, candidate != _APP_DIRECTORY
    except OSError:
        # Local development must remain usable when a configured volume has not
        # been mounted yet. Diagnostics reports this fallback as non-persistent.
        return _APP_DIRECTORY, False

# Register datetime adapters for SQLite
def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(s):
    try:
        return datetime.fromisoformat(s.decode())
    except (ValueError, TypeError):
        return s.decode()

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("TIMESTAMP", convert_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

DATA_DIRECTORY, USING_PERSISTENT_STORAGE = _resolve_data_directory()
DB_PATH = os.path.join(DATA_DIRECTORY, "invest_guide.db")


def get_storage_status():
    """Expose deployment-safe storage state without leaking a filesystem path."""
    if USING_PERSISTENT_STORAGE:
        return {
            "status": "ok",
            "persistent": True,
            "message": "Runtime settings are stored on the configured data volume.",
        }
    return {
        "status": "warning",
        "persistent": False,
        "message": (
            "Runtime settings use ephemeral Space storage. Mount a writable "
            "Storage Bucket and set MONEYPLAN_DATA_DIR to its mount path."
        ),
    }

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ekonomik Takvim Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            date_time TEXT, -- ISO format: YYYY-MM-DD HH:MM:SS
            country_id INTEGER,
            currency TEXT,
            title TEXT,
            impact TEXT, -- Low, Medium, High
            actual TEXT DEFAULT '-',
            forecast TEXT DEFAULT '-',
            previous TEXT DEFAULT '-',
            unit TEXT DEFAULT '',
            category TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # System Jobs Table - Manages scripts and internal tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            type TEXT NOT NULL, -- 'script', 'internal'
            path TEXT,          -- for script type
            args TEXT,          -- JSON list for script type
            service TEXT,       -- for internal type
            method TEXT,        -- for internal type
            last_run TEXT,      -- ISO timestamp
            status TEXT DEFAULT 'idle',
            output TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed initial jobs if table is empty
    cursor.execute("SELECT COUNT(*) FROM system_jobs")
    if cursor.fetchone()[0] == 0:
        initial_jobs = [
            ("import_calendar", "Economic Calendar Import", "Imports latest economic calendar from sample file", "script", "import_calendar.py", '["17-jan-26-weekly.json"]', None, None),
            ("fetch_news", "News Refresh", "Triggers news source crawl and cache refresh", "internal", None, '[]', "news_service", "get_latest_news"),
            ("sync_twelve_data", "Twelve Data Sync", "Syncs global stock data from Twelve Data API", "script", "scripts/sync_all_twelve.py", '[]', None, None)
        ]
        cursor.executemany("""
            INSERT INTO system_jobs (id, name, description, type, path, args, service, method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_jobs)
    
    # Ad Placements Table - Manage AdMob/Provider IDs remotely
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ad_placements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            placement_key TEXT UNIQUE NOT NULL, -- e.g. 'home_banner', 'detail_interstitial'
            provider TEXT DEFAULT 'admob',
            ad_unit_id TEXT,
            is_enabled INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed initial ad placements if empty
    cursor.execute("SELECT COUNT(*) FROM ad_placements")
    if cursor.fetchone()[0] == 0:
        initial_ads = [
            ("Main Home Banner", "home_banner", "admob", "ca-app-pub-3940256099942544/6300978111"), # Test ID
            ("Market Detail Footer", "detail_footer", "admob", "ca-app-pub-3940256099942544/6300978111"),
            ("Interstitial After Action", "action_interstitial", "admob", "ca-app-pub-3940256099942544/1033173712")
        ]
        cursor.executemany("""
            INSERT INTO ad_placements (name, placement_key, provider, ad_unit_id)
            VALUES (?, ?, ?, ?)
        """, initial_ads)
    
    # Notifications Table - Track sent push notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            image_url TEXT,
            action_url TEXT,
            target_segment TEXT DEFAULT 'all', -- 'all', 'premium', 'free'
            status TEXT DEFAULT 'pending', -- 'sent', 'failed'
            delivered_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Settings Table - For feature flags and app configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Price Alerts Table - For background monitoring
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            target_price REAL NOT NULL,
            is_above INTEGER DEFAULT 1, -- 1 for above, 0 for below
            is_active INTEGER DEFAULT 1,
            last_triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(
        DB_PATH, 
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    conn.row_factory = sqlite3.Row
    return conn

# Uygulama başladığında DB'yi hazırla
init_db()
