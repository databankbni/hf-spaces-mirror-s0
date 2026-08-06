import sys
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - Data Fetcher
# Fetches real-time market data from yfinance and FRED
# =============================================================================

import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import base64
import gzip
import json
import urllib.request
import urllib.error
import urllib.parse
import os
from fredapi import Fred

from config import (
    FRED_API_KEY, BPS_API_KEY, TICKERS, FRED_SERIES,
    SMA_SHORT, SMA_LONG, RSI_PERIOD, HISTORICAL_DAYS, CHART_DAYS, INDONESIA_DATA,
    BASE_DIR
)


def _compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI (Relative Strength Index) for a price series."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    last_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50.0
    return round(float(last_rsi), 2)


def _compute_sma(series: pd.Series, period: int) -> float:
    """Compute Simple Moving Average."""
    sma = series.rolling(window=period, min_periods=period).mean()
    last_sma = sma.dropna().iloc[-1] if not sma.dropna().empty else float(series.iloc[-1])
    return round(float(last_sma), 2)


def _safe_fetch_ticker(symbol: str, period_days: int = HISTORICAL_DAYS) -> dict:
    """
    Safely fetch ticker data from yfinance.
    Returns dict with price, change_pct, sma_50, sma_200, rsi_14, history.
    """
    result = {
        "price": None,
        "change_pct": None,
        "sma_50": None,
        "sma_200": None,
        "rsi_14": None,
        "sma_cross": None,  # 'golden_cross' or 'death_cross' or 'none'
        "trend": None,      # 'uptrend' or 'downtrend' or 'sideways'
        "history": [],
        "error": None,
    }

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                              end=end_date.strftime("%Y-%m-%d"))

        if hist.empty:
            result["error"] = f"Data kosong untuk {symbol}"
            return result

        close = hist["Close"]
        result["price"] = round(float(close.iloc[-1]), 2)

        # Percentage change (1 day)
        if len(close) >= 2:
            prev = float(close.iloc[-2])
            curr = float(close.iloc[-1])
            result["change_pct"] = round(((curr - prev) / prev) * 100, 2) if prev != 0 else 0.0

        # SMA
        if len(close) >= SMA_SHORT:
            result["sma_50"] = _compute_sma(close, SMA_SHORT)
        if len(close) >= SMA_LONG:
            result["sma_200"] = _compute_sma(close, SMA_LONG)

        # SMA Cross detection
        if result["sma_50"] is not None and result["sma_200"] is not None:
            if result["sma_50"] > result["sma_200"]:
                result["sma_cross"] = "golden_cross"
            elif result["sma_50"] < result["sma_200"]:
                result["sma_cross"] = "death_cross"
            else:
                result["sma_cross"] = "none"

        # RSI
        if len(close) >= RSI_PERIOD + 1:
            result["rsi_14"] = _compute_rsi(close, RSI_PERIOD)

        # Trend based on 20-day vs 60-day performance
        if len(close) >= 60:
            pct_20d = (float(close.iloc[-1]) / float(close.iloc[-20]) - 1) * 100
            pct_60d = (float(close.iloc[-1]) / float(close.iloc[-60]) - 1) * 100
            if pct_20d > 2 and pct_60d > 5:
                result["trend"] = "uptrend"
            elif pct_20d < -2 and pct_60d < -5:
                result["trend"] = "downtrend"
            else:
                result["trend"] = "sideways"
        elif len(close) >= 20:
            pct_20d = (float(close.iloc[-1]) / float(close.iloc[-20]) - 1) * 100
            if pct_20d > 2:
                result["trend"] = "uptrend"
            elif pct_20d < -2:
                result["trend"] = "downtrend"
            else:
                result["trend"] = "sideways"

        # Store recent history for charting (last CHART_DAYS entries)
        recent = hist.tail(CHART_DAYS)
        result["history"] = [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            }
            for idx, row in recent.iterrows()
        ]

    except Exception as e:
        result["error"] = f"Error fetching {symbol}: {str(e)}"

    return result


def _fetch_fred_data() -> dict:
    """Fetch US macro data from FRED API."""
    result = {
        "fed_funds_rate": None,
        "fed_funds_rate_history": [],
        "us_cpi": None,
        "us_cpi_yoy": None,
        "us_cpi_history": [],
        "us_gdp_growth": None,
        "us_gdp_history": [],
        "china_pmi": None,
        "china_pmi_history": [],
        "errors": [],
    }

    try:
        fred = Fred(api_key=FRED_API_KEY)

        # Fed Funds Rate
        try:
            series = fred.get_series(FRED_SERIES["FED_FUNDS_RATE"])
            if not series.empty:
                s_drop = series.dropna()
                result["fed_funds_rate"] = round(float(s_drop.iloc[-1]), 2)
                result["fed_funds_rate_history"] = [
                    {"date": idx.strftime("%Y-%m-%d"), "value": round(float(val), 2)}
                    for idx, val in s_drop.tail(12).items()
                ]
        except Exception as e:
            result["errors"].append(f"Fed Funds Rate: {str(e)}")

        # US CPI (compute YoY inflation)
        try:
            cpi_series = fred.get_series(FRED_SERIES["US_CPI"])
            if not cpi_series.empty:
                cpi_series = cpi_series.dropna()
                result["us_cpi"] = round(float(cpi_series.iloc[-1]), 2)
                if len(cpi_series) >= 13:
                    current_cpi = float(cpi_series.iloc[-1])
                    year_ago_cpi = float(cpi_series.iloc[-13])
                    yoy = ((current_cpi - year_ago_cpi) / year_ago_cpi) * 100
                    result["us_cpi_yoy"] = round(yoy, 2)
                    
                    # Compute YoY history for the last 12 months
                    history = []
                    for i in range(12, 0, -1):
                        curr = float(cpi_series.iloc[-i])
                        prev = float(cpi_series.iloc[-(i + 12)])
                        yoy_val = ((curr - prev) / prev) * 100
                        idx = cpi_series.index[-i]
                        history.append({"date": idx.strftime("%Y-%m-%d"), "value": round(yoy_val, 2)})
                    result["us_cpi_history"] = history
        except Exception as e:
            result["errors"].append(f"US CPI: {str(e)}")

        # US GDP Growth
        try:
            gdp_series = fred.get_series(FRED_SERIES["US_GDP_GROWTH"])
            if not gdp_series.empty:
                s_drop = gdp_series.dropna()
                result["us_gdp_growth"] = round(float(s_drop.iloc[-1]), 2)
                result["us_gdp_history"] = [
                    {"date": idx.strftime("%Y-%m-%d"), "value": round(float(val), 2)}
                    for idx, val in s_drop.tail(12).items()
                ]
        except Exception as e:
            result["errors"].append(f"US GDP Growth: {str(e)}")



    except Exception as e:
        result["errors"].append(f"FRED connection error: {str(e)}")

    return result


def _fetch_bi_rate_live() -> dict:
    """Fetch BI Rate live from TradingEconomics."""
    result = {"value": 5.75, "is_live": False, "error": None} # fallback to 5.75
    try:
        import urllib.request, re
        req = urllib.request.Request('https://tradingeconomics.com/indonesia/interest-rate', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        match = re.search(r'recorded at ([\d\.]+) percent', html)
        if match:
            result["value"] = float(match.group(1))
            result["is_live"] = True
        else:
            result["error"] = "Regex match failed (element 'recorded at' not found)"
            try:
                from telegram_notifier import send_telegram_message
                send_telegram_message("🚨 *CRITICAL ERROR* 🚨\nScraper BI Rate HTTP Sukses tapi gagal regex match (TradingEconomics mungkin ganti layout)!")
            except Exception:
                pass
    except Exception as e:
        result["error"] = str(e)
        try:
            from telegram_notifier import send_telegram_message
            send_telegram_message(f"🚨 *CRITICAL ERROR* 🚨\nScraper BI Rate gagal di Data Fetcher!\nError: {e}")
        except Exception:
            pass
    return result

def _get_fallback_age_days() -> int:
    try:
        from datetime import datetime
        snapshot_date = datetime(2026, 7, 12)
        return (datetime.now() - snapshot_date).days
    except:
        return 0


def _get_static_macro_history():
    """
    Data historis ASLI Indonesia Makro.
    Sumber:
      - BI Rate: https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx (scraped table)
    """
    return {
        # Sumber: bi.go.id - tabel BI-Rate halaman 1 (scraped 12 Juli 2026)
        "bi_rate": [
            {"date": "18 Juni 2026", "value": 5.75},
            {"date": "9 Juni 2026", "value": 5.50},
            {"date": "20 Mei 2026", "value": 5.25},
            {"date": "22 April 2026", "value": 4.75},
            {"date": "17 Maret 2026", "value": 4.75},
            {"date": "19 Februari 2026", "value": 4.75},
            {"date": "21 Januari 2026", "value": 4.75},
            {"date": "17 Desember 2025", "value": 4.75},
            {"date": "19 November 2025", "value": 4.75},
            {"date": "22 Oktober 2025", "value": 4.75},
        ],
        "inflation": [
            {"date": "Jun 2026", "value": 3.34},
            {"date": "Mei 2026", "value": 3.08},
            {"date": "Apr 2026", "value": 2.42},
            {"date": "Mar 2026", "value": 3.48},
            {"date": "Feb 2026", "value": 4.76},
            {"date": "Jan 2026", "value": 3.55},
            {"date": "Des 2025", "value": 2.92},
            {"date": "Nov 2025", "value": 2.72},
            {"date": "Okt 2025", "value": 2.86},
            {"date": "Sep 2025", "value": 2.65},
            {"date": "Agt 2025", "value": 2.31},
            {"date": "Jul 2025", "value": 2.37}
        ],
        "gdp": [
            {"date": "Triwulan 1 2026", "value": 5.61},
            {"date": "Triwulan 4 2025", "value": 5.39},
            {"date": "Triwulan 3 2025", "value": 5.04},
            {"date": "Triwulan 2 2025", "value": 5.12},
            {"date": "Triwulan 1 2025", "value": 4.87},
            {"date": "Triwulan 4 2024", "value": 5.02},
            {"date": "Triwulan 3 2024", "value": 4.95},
            {"date": "Triwulan 2 2024", "value": 5.05}
        ],
        "trade": [
            {"date": "Jun 2026", "value": 1.0},
            {"date": "Mei 2026", "value": 1.5},
            {"date": "Apr 2026", "value": 2.1},
            {"date": "Mar 2026", "value": 1.8},
            {"date": "Feb 2026", "value": 2.5},
            {"date": "Jan 2026", "value": 3.0},
            {"date": "Des 2025", "value": 2.4},
            {"date": "Nov 2025", "value": 2.2},
            {"date": "Okt 2025", "value": 3.1},
            {"date": "Sep 2025", "value": 2.8},
            {"date": "Agt 2025", "value": 3.5},
            {"date": "Jul 2025", "value": 3.2}
        ]
    }

def _fetch_trading_economics_live(symbol: str, span: str = "1y", is_gdp: bool = False) -> list:
    """
    Fetch direct from Trading Economics CDN and decrypt the payload.
    """
    url = f"https://d3ii0wo49og5mi.cloudfront.net/economics/{symbol}?span={span}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://id.tradingeconomics.com',
        'Referer': 'https://id.tradingeconomics.com/',
        'x-api-key': '20260324:loboantunes'
    }
    
    months_id = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "Mei", "06": "Jun",
        "07": "Jul", "08": "Agt", "09": "Sep", "10": "Okt", "11": "Nov", "12": "Des"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read().decode('utf-8').strip('"')
        
        # TE obfuscation key
        key = b'tradingeconomics-charts-core-api-key'
        data = base64.b64decode(content)
        # XOR decrypt
        xored = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
        # GZIP decompress
        unzipped = gzip.decompress(xored)
        
        parsed = json.loads(unzipped)
        if parsed and len(parsed) > 0 and "series" in parsed[0] and len(parsed[0]["series"]) > 0:
            raw_data = parsed[0]["series"][0]["serie"]["data"]
            
            history = []
            for item in raw_data:
                date_str = item[3] # e.g. "2026-06-01"
                parts = date_str.split("-")
                
                if is_gdp and len(parts) >= 2:
                    month = parts[1]
                    if month == "03": q = 1
                    elif month == "06": q = 2
                    elif month == "09": q = 3
                    elif month == "12": q = 4
                    else: q = int(month) // 3
                    formatted_date = f"Triwulan {q} {parts[0]}"
                elif len(parts) >= 2:
                    formatted_date = f"{months_id.get(parts[1], parts[1])} {parts[0]}"
                else:
                    formatted_date = date_str
                    
            return history[:12] # Limit to 12 points max
            
    except Exception as e:
        print(f"[TE API Error] {symbol}: {e}")
        try:
            from telegram_notifier import send_telegram_message
            send_telegram_message(f"🚨 *CRITICAL ERROR* 🚨\nTE API gagal untuk {symbol}!\nError: {e}")
        except Exception:
            pass
        
    return []

def _combine_live_with_history(live_val: float, history_array: list, is_gdp: bool = False) -> list:
    """Ensure the top history item matches the live fetched value without duplicating."""
    if not live_val or not history_array:
        return history_array
    
    new_hist = history_array.copy()
    
    # If the live value differs from the top history element, we assume it's a new period.
    # However, to prevent cluttering the chart with duplicate 'today' dates when data hasn't changed,
    # we just update the top element if the value is the same.
    # If the value changed, we insert it at the top with today's date.
    
    if round(live_val, 2) == round(new_hist[0]["value"], 2):
        # Value matches the latest historical data, do nothing
        return new_hist
    else:
        # New data point detected!
        if is_gdp:
            # We don't auto-append dates for GDP because of the string formatting
            new_hist[0]["value"] = live_val
        else:
            current_date = datetime.now().strftime("%Y-%m-%d")
            new_hist.insert(0, {"date": current_date, "value": live_val})
        return new_hist[:12]

def fetch_all_data() -> dict:
    """
    Main function: fetch all market data and return as a clean dictionary.
    """
    print("[DataFetcher] Mulai mengambil data pasar...")
    data = {
        "timestamp": datetime.now().isoformat(),
        "market": {},
        "macro": {},
        "indonesia": {},
        "technicals": {},
        "errors": [],
    }

    # --- Fetch all yfinance tickers ---
    for name, symbol in TICKERS.items():
        print(f"[DataFetcher] Mengambil data {name} ({symbol})...")
        ticker_data = _safe_fetch_ticker(symbol)
        data["market"][name] = ticker_data
        if ticker_data["error"]:
            data["errors"].append(ticker_data["error"])

    # Remove COAL fallback logic
    
    # --- Fetch FRED macro data ---
    print("[DataFetcher] Mengambil data makro dari FRED...")
    fred_data = _fetch_fred_data()
    data["macro"] = {
        "fed_funds_rate": fred_data.get("fed_funds_rate"),
        "fed_funds_rate_history": fred_data.get("fed_funds_rate_history", []),
        "us_cpi": fred_data.get("us_cpi"),
        "us_cpi_yoy": fred_data.get("us_cpi_yoy"),
    }
    if fred_data["errors"]:
        data["errors"].extend(fred_data["errors"])

    # --- Real-time Indonesia data ---
    print("[DataFetcher] Mengambil BI Rate live...")
    bi_rate_data = _fetch_bi_rate_live()
    if bi_rate_data.get("error"):
        data["errors"].append(f"BI Rate fetch error: {bi_rate_data['error']}")
    # Default to static history for realistic UI representation
    static_hist = _get_static_macro_history()
    
    # Reuse the already-fetched bi_rate_data (avoid double HTTP request)
    bi_rate_live = INDONESIA_DATA["BI_RATE"]
    bi_rate_is_live = False
    if bi_rate_data["is_live"]:
        bi_rate_live = bi_rate_data["value"]
        bi_rate_is_live = True
    
    # Fetch LIVE history from Trading Economics API
    print("[DataFetcher] Mengambil data historis dari Trading Economics (Live API)...")
    te_inflation = _fetch_trading_economics_live("idcpiy", "1y")
    te_gdp = _fetch_trading_economics_live("idgdpy", "5y", is_gdp=True)
    te_trade = _fetch_trading_economics_live("idbaltol", "1y")
    
    # --- Local Caching for TE Data ---
    TE_CACHE_FILE = os.path.join(BASE_DIR, 'data', 'te_macro_cache.json')
    te_cache = {}
    if os.path.exists(TE_CACHE_FILE):
        try:
            with open(TE_CACHE_FILE, 'r') as f:
                te_cache = json.load(f)
        except Exception as e:
            print(f"[TE Cache] Error reading cache: {e}")

    # Save to cache if successful
    if te_inflation and te_gdp and te_trade:
        te_cache = {
            "inflation": te_inflation,
            "gdp": te_gdp,
            "trade": te_trade
        }
        os.makedirs(os.path.dirname(TE_CACHE_FILE), exist_ok=True)
        try:
            with open(TE_CACHE_FILE, 'w') as f:
                json.dump(te_cache, f)
        except Exception as e:
            print(f"[TE Cache] Error writing cache: {e}")

    # Default fallback values in case TE API fails and cache is empty
    inflation_live = INDONESIA_DATA.get("INFLATION_ID", 2.5)
    gdp_live = INDONESIA_DATA.get("GDP_GROWTH_ID", 5.0)
    trade_live = INDONESIA_DATA.get("TRADE_BALANCE_ID", 1.0)
    
    inflation_source = "static_fallback"
    gdp_source = "static_fallback"
    trade_source = "static_fallback"

    # If live API succeeded, use it, otherwise fallback
    if te_inflation:
        inflation_live = te_inflation[0]["value"]
        inflation_history = te_inflation
        inflation_source = "trading_economics_live"
    elif "inflation" in te_cache:
        inflation_live = te_cache["inflation"][0]["value"]
        inflation_history = te_cache["inflation"]
        inflation_source = "trading_economics_cache"
    else:
        # Ultimate fallback if TE fails and cache is empty
        inflation_history = static_hist["inflation"]
        if inflation_history: inflation_live = inflation_history[0]["value"]
        
    if te_gdp:
        gdp_live = te_gdp[0]["value"]
        gdp_history = te_gdp
        gdp_source = "trading_economics_live"
    elif "gdp" in te_cache:
        gdp_live = te_cache["gdp"][0]["value"]
        gdp_history = te_cache["gdp"]
        gdp_source = "trading_economics_cache"
    else:
        gdp_history = static_hist["gdp"]
        if gdp_history: gdp_live = gdp_history[0]["value"]
        
    if te_trade:
        trade_live = te_trade[0]["value"]
        trade_history = te_trade
        trade_source = "trading_economics_live"
    elif "trade" in te_cache:
        trade_live = te_cache["trade"][0]["value"]
        trade_history = te_cache["trade"]
        trade_source = "trading_economics_cache"
    else:
        trade_history = static_hist["trade"]
        if trade_history: trade_live = trade_history[0]["value"]

    # BI Rate is already from BI
    bi_rate_history = _combine_live_with_history(bi_rate_live, static_hist["bi_rate"])

    fallback_age = _get_fallback_age_days()
    warnings = []
    if fallback_age > 30 and (inflation_source == "static_fallback" or gdp_source == "static_fallback" or trade_source == "static_fallback"):
        warnings.append(f"Data makro statis (fallback) digunakan dan sudah berusia >30 hari ({fallback_age} hari).")

    if "warnings" not in data:
        data["warnings"] = []
    data["warnings"].extend(warnings)

    data["indonesia"] = {
        "bi_rate": round(bi_rate_live, 2),
        "bi_rate_history": bi_rate_history,
        "bi_rate_is_live": bi_rate_is_live,
        "inflation": round(inflation_live, 2),
        "inflation_history": inflation_history,
        "inflation_source": inflation_source,
        "gdp_growth": round(gdp_live, 2),
        "gdp_growth_history": gdp_history,
        "gdp_growth_source": gdp_source,
        "trade_balance": round(trade_live, 2),
        "trade_balance_history": trade_history,
        "trade_balance_source": trade_source,
        "static_fallback_age_days": fallback_age,
        "ihsg_per": INDONESIA_DATA["IHSG_PER"],
        "ihsg_per_source": "static_permanent",
        "ihsg_earnings_growth": INDONESIA_DATA["IHSG_EARNINGS_GROWTH"],
        "ihsg_earnings_growth_source": "static_permanent",
        "note": "Realistic static history combined with live data."
    }

    # --- Extract IHSG technicals ---
    ihsg = data["market"].get("IHSG", {})
    data["technicals"] = {
        "ihsg_price": ihsg.get("price"),
        "ihsg_sma_50": ihsg.get("sma_50"),
        "ihsg_sma_200": ihsg.get("sma_200"),
        "ihsg_rsi_14": ihsg.get("rsi_14"),
        "ihsg_sma_cross": ihsg.get("sma_cross"),
        "ihsg_trend": ihsg.get("trend"),
    }

    print(f"[DataFetcher] Selesai. {len(data['errors'])} error ditemukan.")
    return data


def fetch_chart_data(ticker_symbol: str = "^JKSE", period: str = "3mo") -> list:
    """Fetch historical data specifically for charting with dynamic timeframe."""
    try:
        # Determine interval based on period
        interval = "1d"
        if period == "1d":
            interval = "5m"
        elif period == "5d" or period == "1w":
            period = "5d"
            interval = "15m"
        elif period == "1mo":
            interval = "1h"
            
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
            # Fallback if 5m/15m/1h interval fails or no data
            hist = ticker.history(period=period, interval="1d")
            
        if hist.empty:
            return []

        # We don't always need SMA for small intervals, but let's compute it if interval is 1d
        sma_20 = None
        sma_50 = None
        if interval == "1d" and len(hist) > 10:
            close_full = hist["Close"]
            sma_20 = close_full.rolling(window=20, min_periods=1).mean()
            sma_50 = close_full.rolling(window=SMA_SHORT, min_periods=1).mean()

        chart_data = []
        for idx, row in hist.iterrows():
            # For intraday, format time. For daily, format date.
            if interval in ["1d", "1wk", "1mo"]:
                date_str = idx.strftime("%Y-%m-%d")
            else:
                date_str = idx.strftime("%Y-%m-%d %H:%M")
                
            entry = {
                "date": date_str,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            }
            # Add SMA if available
            if sma_20 is not None and idx in sma_20.index and not pd.isna(sma_20[idx]):
                entry["sma_20"] = round(float(sma_20[idx]), 2)
            if sma_50 is not None and idx in sma_50.index and not pd.isna(sma_50[idx]):
                entry["sma_50"] = round(float(sma_50[idx]), 2)
            chart_data.append(entry)

        return chart_data

    except Exception as e:
        print(f"[DataFetcher] Error fetching chart data for {ticker_symbol} ({period}): {e}")
        return []


if __name__ == "__main__":
    data = fetch_all_data()
    print("\n=== Market Data Summary ===")
    for name, info in data["market"].items():
        price = info.get("price", "N/A")
        change = info.get("change_pct", "N/A")
        print(f"  {name}: {price} ({change}%)")
    print("\n=== Macro Data ===")
    for key, val in data["macro"].items():
        print(f"  {key}: {val}")
    print("\n=== Indonesia Data ===")
    for key, val in data["indonesia"].items():
        print(f"  {key}: {val}")
    print("\n=== Technicals ===")
    for key, val in data["technicals"].items():
        print(f"  {key}: {val}")
    if data["errors"]:
        print(f"\n=== Errors ({len(data['errors'])}) ===")
        for err in data["errors"]:
            print(f"  - {err}")
