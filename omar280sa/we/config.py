"""
config.py
---------
Loads all configuration for the app:
- settings.json (quality, target_size, max_width, format)
- Cloudinary accounts (multiple, for automatic failover)

Keep this file dumb on purpose: read files, expose plain values.
No classes, no magic.
"""

import json
import logging
import os

logger = logging.getLogger("config")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

# Sensible fallback values in case settings.json is missing or broken.
DEFAULT_SETTINGS = {
    "quality": 80,
    "target_size": 100,   # KB
    "max_width": 1200,    # px
    "format": "webp",
}


def load_settings() -> dict:
    """
    Read settings.json from disk every time it's called so the server
    always reflects the latest values (no restart needed to tweak them).
    Falls back to defaults if the file is missing or invalid.
    """
    if not os.path.exists(SETTINGS_PATH):
        logger.warning("settings.json not found, using defaults")
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        # Fill in any missing keys with defaults, just in case.
        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read settings.json: {e}. Using defaults.")
        return DEFAULT_SETTINGS.copy()


# ---------------------------------------------------------------------------
# Cloudinary accounts
# ---------------------------------------------------------------------------
# Configure via environment variables so secrets never live in code.
#
# For up to 3 accounts, set:
#   CLOUDINARY_CLOUD_NAME_1 / CLOUDINARY_API_KEY_1 / CLOUDINARY_API_SECRET_1
#   CLOUDINARY_CLOUD_NAME_2 / CLOUDINARY_API_KEY_2 / CLOUDINARY_API_SECRET_2
#   CLOUDINARY_CLOUD_NAME_3 / CLOUDINARY_API_KEY_3 / CLOUDINARY_API_SECRET_3
#
# Only fully-filled-in accounts (all 3 values present) are used.
# This keeps upload.py simple: it just loops over CLOUDINARY_ACCOUNTS.

def _load_accounts_from_env() -> list:
    accounts = []
    for i in range(1, 4):  # supports account 1, 2, 3
        cloud_name = os.environ.get(f"CLOUDINARY_CLOUD_NAME_{i}")
        api_key = os.environ.get(f"CLOUDINARY_API_KEY_{i}")
        api_secret = os.environ.get(f"CLOUDINARY_API_SECRET_{i}")

        if cloud_name and api_key and api_secret:
            accounts.append({
                "name": f"Cloudinary #{i}",
                "cloud_name": cloud_name,
                "api_key": api_key,
                "api_secret": api_secret,
            })
        elif cloud_name or api_key or api_secret:
            # Partially configured — warn so the user notices the typo/gap.
            logger.warning(f"Cloudinary account {i} is partially configured; skipping it")

    return accounts


CLOUDINARY_ACCOUNTS = _load_accounts_from_env()

if not CLOUDINARY_ACCOUNTS:
    logger.warning(
        "No Cloudinary accounts configured. "
        "Set CLOUDINARY_CLOUD_NAME_1 / CLOUDINARY_API_KEY_1 / CLOUDINARY_API_SECRET_1 "
        "(and _2, _3 optionally) as environment variables."
    )
