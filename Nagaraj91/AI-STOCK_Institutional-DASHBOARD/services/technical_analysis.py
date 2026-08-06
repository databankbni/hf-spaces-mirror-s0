import yfinance as yf
import pandas as pd
import numpy as np
import ta
from models import TechnicalData

def analyze_technicals(ticker: str) -> TechnicalData:
    stock = yf.Ticker(ticker)
    df = stock.history(period="1y")
    
    if df.empty or len(df) < 50:
        raise ValueError(f"Not enough price data for {ticker}")
        
    current_price = float(df['Close'].iloc[-1])
    high_52w = float(df['High'].max())
    low_52w = float(df['Low'].min())
    avg_volume = float(df['Volume'].mean())
    
    # EMAs
    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=20)
    df['EMA_50'] = ta.trend.ema_indicator(df['Close'], window=50)
    df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=200)
    
    # MACD
    macd_indicator = ta.trend.MACD(df['Close'])
    df['MACD'] = macd_indicator.macd()
    df['MACD_Signal'] = macd_indicator.macd_signal()
    
    # RSI
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    
    # ADX
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['ADX'] = adx_indicator.adx()
    
    # Bollinger Bands
    bb_indicator = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
    df['BB_Upper'] = bb_indicator.bollinger_hband()
    df['BB_Lower'] = bb_indicator.bollinger_lband()
    
    # Basic Support / Resistance (using 3-month min/max)
    recent_3m = df.tail(60)
    support_1 = float(recent_3m['Low'].min())
    resistance_1 = float(recent_3m['High'].max())
    
    # Trend Analysis
    ema_20 = float(df['EMA_20'].iloc[-1])
    ema_50 = float(df['EMA_50'].iloc[-1])
    ema_200 = float(df['EMA_200'].iloc[-1]) if not np.isnan(df['EMA_200'].iloc[-1]) else ema_50
    
    trend = "Bullish" if current_price > ema_50 and ema_50 > ema_200 else "Bearish" if current_price < ema_50 and ema_50 < ema_200 else "Neutral"
    trend_strength = "Strong" if float(df['ADX'].iloc[-1]) > 25 else "Weak"
    
    # Beta
    beta = stock.info.get("beta", 1.0)
    
    return {
        "current_price": current_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "avg_volume": avg_volume,
        "beta": beta,
        "trend": trend,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "macd": float(df['MACD'].iloc[-1]),
        "macd_signal": float(df['MACD_Signal'].iloc[-1]),
        "rsi": float(df['RSI'].iloc[-1]),
        "adx": float(df['ADX'].iloc[-1]),
        "bollinger_upper": float(df['BB_Upper'].iloc[-1]),
        "bollinger_lower": float(df['BB_Lower'].iloc[-1]),
        "support_1": support_1,
        "resistance_1": resistance_1,
        "trend_strength": trend_strength
    }
