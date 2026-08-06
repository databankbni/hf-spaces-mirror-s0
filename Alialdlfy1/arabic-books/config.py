import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists (useful for local development)
load_dotenv()

# Project Paths
BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
TEMP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Application Information
APP_NAME = "Arabic Books Publisher"
VERSION = "1.0.0"

# Target Scheduled Hours (UTC+3 / Saudi Arabia Time)
SCHEDULE_HOURS = [9, 11, 13, 15, 17, 19, 21, 23]  # 8 times a day
UTC_OFFSET_HOURS = 3  # Target is UTC+3 (KSA Time)

# Queue & Replenishment Settings
QUEUE_TARGET_SIZE = 56       # 7 days * 8 posts/day
QUEUE_REPLENISH_THRESHOLD = 24  # Trigger replenishment when below this
MAX_BOOK_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Scraper Settings
MAX_DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_BACKOFF_FACTOR = 2  # Exponential factor (2s, 4s, 8s)
DOWNLOAD_TIMEOUT_SECONDS = 120

# Sources Quality Score Settings
SOURCE_INITIAL_SCORE = 100
SOURCE_BLACKLIST_THRESHOLD = 30
SOURCE_BLACKLIST_DURATION_HOURS = 12
SOURCE_SUCCESS_REWARD = 1
SOURCE_NETWORK_ERROR_PENALTY = 5
SOURCE_INVALID_FILE_PENALTY = 15

# Feature Flags (Can be toggled via Env vars)
DRY_RUN = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes")
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "False").lower() in ("true", "1", "yes")
SAFE_MODE = os.getenv("SAFE_MODE", "True").lower() in ("true", "1", "yes")
ENABLE_AI = os.getenv("ENABLE_AI", "True").lower() in ("true", "1", "yes")
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "True").lower() in ("true", "1", "yes")

# AI Settings
PROMPT_VERSION = "v1"
AI_CACHE_EXPIRY_DAYS = 90

# Logging & Rotation Settings
LOG_ROTATION_DAYS = 2
LOG_MAX_BYTES = 512 * 1024  # 512 KB to prevent page freezes
LOG_RETENTION_DAYS = 2
