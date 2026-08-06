import sys
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - FastAPI Server
# Main entry point for the backend API
# =============================================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import traceback
import asyncio
import math

from config import CORS_ORIGINS, API_HOST, API_PORT
from oracle import get_verdict
from backtest_engine import run_backtest


def _sanitize_for_json(obj):
    """Recursively replace NaN/Infinity floats with None to prevent JSON serialization errors."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


# --- Initialize FastAPI ---
app = FastAPI(
    title="The Market Oracle API",
    description="IHSG Market Direction Dashboard - Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Cache for oracle results (simple in-memory) ---
_cache = {
    "oracle_result": None,
    "oracle_timestamp": None,
    "cache_ttl_seconds": 300,  # 5 minutes
}


def _is_cache_valid() -> bool:
    """Check if cached oracle result is still valid."""
    if _cache["oracle_result"] is None or _cache["oracle_timestamp"] is None:
        return False
    elapsed = (datetime.now() - _cache["oracle_timestamp"]).total_seconds()
    return elapsed < _cache["cache_ttl_seconds"]


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "The Market Oracle API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "message": "Server berjalan normal",
    }


@app.get("/api/oracle")
async def get_oracle_verdict():
    """
    Run the full Oracle analysis and return the complete verdict.
    Results are cached for 5 minutes to avoid excessive API calls.
    """
    try:
        # Check cache first
        if _is_cache_valid():
            result = _cache["oracle_result"]
            result["from_cache"] = True
            result["cache_expires_in"] = round(
                _cache["cache_ttl_seconds"]
                - (datetime.now() - _cache["oracle_timestamp"]).total_seconds()
            )
            return JSONResponse(content=_sanitize_for_json(result))

        # Run fresh analysis
        result = get_verdict()
        result["from_cache"] = False

        # Update cache
        _cache["oracle_result"] = result
        _cache["oracle_timestamp"] = datetime.now()

        return JSONResponse(content=_sanitize_for_json(result))

    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"[API Error] /api/oracle: {error_detail}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Gagal menjalankan analisis Oracle",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        )


@app.get("/api/market-data")
async def get_market_data(ticker: str = "^JKSE", period: str = "3mo"):
    """
    Return historical data for charting.
    Accepts ticker (e.g. ^JKSE, ^GSPC) and period (e.g. 1d, 1w, 1mo, 3mo, ytd)
    """
    try:
        from data_fetcher import fetch_chart_data
        chart_data = fetch_chart_data(ticker_symbol=ticker, period=period)

        if not chart_data:
            return JSONResponse(
                content={
                    "status": "warning",
                    "message": f"Data chart {ticker} tidak tersedia",
                    "data": [],
                    "count": 0,
                    "timestamp": datetime.now().isoformat(),
                },
                status_code=200,
            )

        return JSONResponse(content={
            "status": "ok",
            "ticker": ticker,
            "name": f"Market Data ({ticker})",
            "data": chart_data,
            "count": len(chart_data),
            "period": period,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"[API Error] /api/market-data: {error_detail}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Gagal mengambil data pasar IHSG",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        )


@app.get("/api/cache/clear")
async def clear_cache():
    """Clear the oracle result cache to force a fresh analysis."""
    _cache["oracle_result"] = None
    _cache["oracle_timestamp"] = None
    return {
        "status": "ok",
        "message": "Cache berhasil dihapus. Analisis berikutnya akan fresh.",
        "timestamp": datetime.now().isoformat(),
    }

from fastapi import Request

@app.get("/api/backtest")
async def get_backtest_stats():
    try:
        # Panggil fungsi backtest, secara default akan membaca dari cache jika ada
        results = run_backtest(force_refresh=False)
        return JSONResponse(content=_sanitize_for_json({"status": "success", "data": results}))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)

@app.post("/api/simulate-macro")
async def simulate_macro(request: Request):
    try:
        override_data = await request.json()
        from oracle import get_simulated_verdict
        
        # Gunakan data cache jika ada agar simulasi instan
        if _cache.get("oracle_result"):
            cached_result = _cache["oracle_result"]
            simulated_verdict = get_simulated_verdict(cached_result, override_data)
            return JSONResponse(content=_sanitize_for_json(simulated_verdict))
        else:
            return JSONResponse(content={"status": "error", "error": "Cache is empty. Please run a Live analysis first."}, status_code=400)
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)

@app.post("/api/simulate-reverse")
async def simulate_reverse(request: Request):
    try:
        body = await request.json()
        target_price_raw = body.get("target_price")
        if not target_price_raw:
            return JSONResponse(content={"status": "error", "error": "target_price is required"}, status_code=400)
            
        target_price = float(target_price_raw)
        from oracle import get_reverse_simulated_verdict
        
        if _cache.get("oracle_result"):
            cached_result = _cache["oracle_result"]
            result = get_reverse_simulated_verdict(cached_result, target_price)
            return JSONResponse(content=result)
        else:
            return JSONResponse(content={"status": "error", "error": "Cache is empty. Please run a Live analysis first."}, status_code=400)
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


from pydantic import BaseModel

class TelegramSetupRequest(BaseModel):
    bot_token: str
    chat_id: str

@app.get("/api/telegram/config")
def get_telegram_config():
    from telegram_notifier import load_config
    return load_config()

@app.post("/api/telegram/config")
def save_telegram_config(req: TelegramSetupRequest):
    from telegram_notifier import save_config
    return save_config(req.bot_token, req.chat_id)

@app.post("/api/telegram/test")
def test_telegram_message():
    from telegram_notifier import send_telegram_message
    res = send_telegram_message("✅ *THE MARKET ORACLE*\n\nKoneksi Telegram berhasil! Anda akan menerima peringatan dini pergerakan market di sini.")
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res


@app.get("/api/calendar")
async def get_macro_calendar_high_impact():
    """Fetch high impact macroeconomic calendar from Trading Economics."""
    try:
        from trading_economics import scrape_calendar
        from datetime import timedelta
        
        cache_key = "te_calendar"
        if cache_key in _cache:
            if datetime.now() - _cache.get(f"{cache_key}_timestamp", datetime.min) < timedelta(minutes=15):
                return JSONResponse(content=_cache[cache_key])
                
        result = scrape_calendar()
        
        if result.get("status") == "success":
            _cache[cache_key] = result
            _cache[f"{cache_key}_timestamp"] = datetime.now()
            return JSONResponse(content=result)
        else:
            return JSONResponse(content=result, status_code=500)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/fear-and-greed")
async def get_fear_and_greed():
    try:
        from fear_greed import fetch_fear_and_greed
        from datetime import timedelta
        
        cache_key = "fear_and_greed"
        if cache_key in _cache:
            if datetime.now() - _cache.get(f"{cache_key}_timestamp", datetime.min) < timedelta(hours=1):
                return JSONResponse(content=_cache[cache_key])
                
        result = fetch_fear_and_greed()
        
        if result.get("status") == "success":
            _cache[cache_key] = result
            _cache[f"{cache_key}_timestamp"] = datetime.now()
            return JSONResponse(content=result)
        else:
            return JSONResponse(content=result, status_code=500)
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)}, 
            status_code=500
        )


# ==========================================
# AUTONOMOUS TELEGRAM BOT DAEMON
# ==========================================
async def autonomous_oracle_bot():
    """
    Runs continuously in the background every 5 minutes.
    Fetches the market data, checks if verdict changed, and sends Telegram alert.
    """
    print("[Oracle Bot] 🤖 Autonomous bot is now running in the background...")
    # Wait for server to fully initialize before first run
    await asyncio.sleep(30)
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Oracle Bot] Memeriksa kondisi pasar...")
            result = get_verdict()
            
            # Fetch Fear & Greed to inject into result for Telegram
            try:
                from fear_greed import fetch_fear_and_greed
                fg_data = fetch_fear_and_greed()
                result["fear_and_greed"] = fg_data
            except Exception as fg_err:
                print(f"[Oracle Bot] Failed to fetch fear and greed: {fg_err}")
                result["fear_and_greed"] = {}
                
            from telegram_notifier import broadcast_verdict_change
            
            old_result = _cache.get("oracle_result")
            
            # Send alert if it's the first run, OR if the verdict key changed
            if old_result is None:
                print("[Oracle Bot] First run detected, sending initial Telegram broadcast...")
                broadcast_verdict_change(result)
            else:
                old_verdict = old_result.get("verdict", {}).get("key")
                new_verdict = result.get("verdict", {}).get("key")
                if old_verdict != new_verdict:
                    print(f"[Oracle Bot] 🚨 Verdict changed from {old_verdict} to {new_verdict}! Broadcasting...")
                    broadcast_verdict_change(result)
                    
            # Update cache safely
            _cache["oracle_result"] = result
            _cache["oracle_timestamp"] = datetime.now()
            
        except Exception as e:
            print(f"[Oracle Bot] Error during background check: {e}")
            
        # Sleep for 5 minutes (300 seconds)
        await asyncio.sleep(300)

@app.on_event("startup")
async def startup_event():
    # Jalankan bot telegram di background saat server menyala
    asyncio.create_task(autonomous_oracle_bot())

# ============================================================================
# Run server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  THE MARKET ORACLE - API Server")
    print("=" * 60)
    print(f"  Starting on http://{API_HOST}:{API_PORT}")
    print(f"  Docs: http://localhost:{API_PORT}/docs")
    print(f"  CORS Origins: {CORS_ORIGINS}")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
