import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8000")))
CORS_ORIGINS = ["*"]

CV_UPLOAD_DIR = BASE_DIR / "data" / "uploads"
CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MATCH_THRESHOLD = 50.0
