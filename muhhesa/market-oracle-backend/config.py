import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - Configuration
# =============================================================================

from dotenv import load_dotenv
load_dotenv()

# --- API Keys ---
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
BPS_API_KEY = os.environ.get("BPS_API_KEY", "")
GOAPI_KEY = os.environ.get("GOAPI_KEY", "")

# --- Ticker Symbols ---
TICKERS = {
    "IHSG": "^JKSE",
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DXY": "DX-Y.NYB",
    "USDIDR": "IDR=X",
    "BRENT_OIL": "BZ=F",
    "GOLD": "GC=F",
    "CRUDE_OIL": "CL=F",      # WTI Crude Oil
}

# --- FRED Series IDs ---
FRED_SERIES = {
    "FED_FUNDS_RATE": "FEDFUNDS",
    "US_CPI": "CPIAUCSL",
    "US_GDP_GROWTH": "A191RL1Q225SBEA",
}





# --- Mentor Sentiment File ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MENTOR_SENTIMENT_FILE = os.path.join(BASE_DIR, 'data', 'Laporan_Analisis_Sentimen_Semua_Mentor.xlsx')

# --- Technical Analysis Parameters ---
SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
HISTORICAL_DAYS = 365
CHART_DAYS = 90

# --- Scoring Weights (must sum to 1.0) ---
SCORING_WEIGHTS = {
    # Macro Indicators (80%)
    "BI_FED_SPREAD": 0.25,
    "USDIDR": 0.20,
    "INFLATION_ID": 0.15,
    "GDP_GROWTH_ID": 0.10,
    "TRADE_BALANCE_ID": 0.05,
    "NEWS_SENTIMENT": 0.05,
    
    # Global & Commodities (15%)
    "SP500_TREND": 0.05,
    "DXY": 0.05,
    "COMMODITIES": 0.05,
    
    # Technical IHSG (5%)
    "TECHNICAL": 0.05,
}

# --- Scoring Thresholds ---
BI_FED_SPREAD_THRESHOLDS = {
    "very_bullish": (2.5, float('inf')),
    "bullish": (1.0, 2.5),
    "neutral": (0.0, 1.0),
    "bearish": (-1.0, 0.0),
    "very_bearish": (float('-inf'), -1.0),
}


GDP_GROWTH_ID_THRESHOLDS = {
    "very_bullish": (6.0, float('inf')),
    "bullish": (5.0, 6.0),
    "neutral": (4.0, 5.0),
    "bearish": (3.0, 4.0),
    "very_bearish": (float('-inf'), 3.0),
}

TRADE_BALANCE_ID_THRESHOLDS = {
    "very_bullish": (3.0, float('inf')),
    "bullish": (1.0, 3.0),
    "neutral": (-1.0, 1.0),
    "bearish": (-3.0, -1.0),
    "very_bearish": (float('-inf'), -3.0),
}

USDIDR_THRESHOLDS = {
    "very_bullish": (0, 14500),
    "bullish": (14500, 15500),
    "neutral": (15500, 16200),
    "bearish": (16200, 16800),
    "very_bearish": (16800, 99999),
}

INFLATION_ID_THRESHOLDS = {
    "very_bullish": (1.5, 2.5),
    "bullish": (2.5, 3.5),
    "neutral_low": (0.5, 1.5),
    "neutral_high": (3.5, 4.5),
    "bearish": (4.5, 6.0),
    "very_bearish": (6.0, 100),
    "bearish_deflation": (float('-inf'), 0.5),
}

FED_RATE_THRESHOLDS = {
    "very_bullish": (0, 2.5),
    "bullish": (2.5, 4.0),
    "neutral": (4.0, 5.0),
    "bearish": (5.0, 5.5),
    "very_bearish": (5.5, 100),
}

DXY_THRESHOLDS = {
    "very_bullish": (0, 95),
    "bullish": (95, 100),
    "neutral": (100, 104),
    "bearish": (104, 108),
    "very_bearish": (108, 200),
}

CHINA_PMI_THRESHOLDS = {
    "very_bullish": (53, 100),
    "bullish": (51, 53),
    "neutral": (49, 51),
    "bearish": (47, 49),
    "very_bearish": (0, 47),
}

PER_THRESHOLDS = {
    "very_cheap": (0, 11),
    "cheap": (11, 13),
    "fair": (13, 16),
    "expensive": (16, 19),
    "very_expensive": (19, 100),
}

RSI_THRESHOLDS = {
    "oversold": (0, 30),
    "neutral_low": (30, 45),
    "neutral": (45, 55),
    "neutral_high": (55, 70),
    "overbought": (70, 100),
}

VERDICT_THRESHOLDS = {
    "STRONG_BULLISH": 1.2,
    "BULLISH": 0.4,
    "NEUTRAL_HIGH": 0.4,
    "NEUTRAL_LOW": -0.4,
    "BEARISH": -1.2,
}

VERDICT_LABELS = {
    "STRONG_BULLISH": "SANGAT BULLISH",
    "BULLISH": "BULLISH",
    "NEUTRAL": "NETRAL",
    "BEARISH": "BEARISH",
    "STRONG_BEARISH": "SANGAT BEARISH",
}

DALIO_PHASES = {
    "goldilocks": {
        "label": "Goldilocks (Pertumbuhan Ideal)",
        "description": "Inflasi rendah, suku bunga rendah - kondisi ideal untuk pasar saham.",
        "verdict": "bullish",
    },
    "reflation": {
        "label": "Reflasi",
        "description": "Inflasi mulai naik, bank sentral mulai menaikkan suku bunga secara bertahap.",
        "verdict": "neutral",
    },
    "overheating": {
        "label": "Overheating (Panas Berlebih)",
        "description": "Inflasi tinggi, suku bunga naik agresif - tekanan pada pasar saham.",
        "verdict": "bearish",
    },
    "stagflation": {
        "label": "Stagflasi",
        "description": "Inflasi tinggi tapi pertumbuhan melambat - skenario terburuk untuk saham.",
        "verdict": "very_bearish",
    },
    "deleveraging": {
        "label": "Deleveraging (Penurunan Utang)",
        "description": "Suku bunga turun untuk mengatasi resesi, inflasi mulai mereda.",
        "verdict": "neutral",
    },
}

# --- FastAPI Config ---
API_HOST = "0.0.0.0"
API_PORT = 8000
import os as _os
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:3000",
    # Production frontend (Vercel)
    "https://ihsg-market-terminal.vercel.app",
    "https://www.ihsg-market-terminal.vercel.app",
    # Allow any vercel preview deployment
    # Add CORS_ORIGIN env var for flexible deployment
    *([_os.environ.get("CORS_ORIGIN")] if _os.environ.get("CORS_ORIGIN") else []),
]

INDONESIA_DATA = { 'BI_RATE': 5.75, 'INFLATION_ID': 2.50, 'IHSG_PER': 14.0, 'IHSG_EARNINGS_GROWTH': 8.0 }

