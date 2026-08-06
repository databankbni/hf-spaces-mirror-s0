# ============================================================
# config.py - Secure Configuration & Constants
# ============================================================
import os
from dotenv import load_dotenv

# Try to load local .env file
load_dotenv()

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# App Constants
UPLOAD_DIR = "/tmp/busnx_uploads"
WAREHOUSE_DIR = "/tmp/busnx_warehouse"
CLEANED_DIR = "/tmp/busnx_cleaned"
STATE_FILE = "/tmp/busnx_state.pkl"

# Ensure directories exist
for d in [UPLOAD_DIR, WAREHOUSE_DIR, CLEANED_DIR]:
    os.makedirs(d, exist_ok=True)