"""
InterStock — LSTM Prediction API Server
=========================================
Loads the trained model and serves stock price predictions via REST API.

Usage:
    python server.py

API:
    POST /predict
    Body: { "symbol": "AAPL" }
    Response: { "symbol": "AAPL", "current_price": 175.50, "predicted_price": 178.23, ... }

    GET /health
    Response: { "status": "ok", "model_loaded": true }
"""

import os
import json
import urllib.request
import urllib.parse
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# ─── Configuration ─────────────────────────────────────────────
MODEL_DIR = 'models'
LOOKBACK = 60

FEATURE_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume',
                   'MA_7', 'MA_21', 'RSI', 'MACD', 'MACD_Signal',
                   'Price_Change', 'Volume_Change', 'Volatility']

# ─── Load Model & Scaler ──────────────────────────────────────
# Resolve paths relative to this file so the server works regardless of the
# current working directory (important under gunicorn / Render).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, MODEL_DIR)

model = None
scaler = None


def load_model():
    """Load the trained LSTM model and scaler."""
    global model, scaler

    model_path = os.path.join(MODEL_DIR, 'stock_model.h5')
    scaler_path = os.path.join(MODEL_DIR, 'scaler.pkl')

    if not os.path.exists(model_path):
        print(f"[!] Model not found at {model_path}. Run train.py first!")
        return False

    import tensorflow as tf
    model = tf.keras.models.load_model(model_path)
    scaler = joblib.load(scaler_path)
    print("[OK] Model and scaler loaded successfully")
    return True


# Load the model at import time so it is available under a WSGI server
# (gunicorn `server:app`), not only when run directly with `python server.py`.
load_model()


# ─── Feature Engineering (same as train.py) ────────────────────
def add_technical_indicators(df):
    """Add the same technical indicators used during training."""
    df['MA_7'] = df['Close'].rolling(window=7).mean()
    df['MA_21'] = df['Close'].rolling(window=21).mean()

    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    df['Price_Change'] = df['Close'].pct_change() * 100
    df['Volume_Change'] = df['Volume'].pct_change() * 100
    df['Volatility'] = df['Close'].rolling(window=14).std()

    return df


def _fetch_twelvedata(symbol):
    """Fetch daily OHLCV from Twelve Data (reliable from cloud IPs)."""
    api_key = os.environ.get('TWELVE_DATA_API_KEY')
    if not api_key:
        return None
    qs = urllib.parse.urlencode({
        'symbol': symbol, 'interval': '1day', 'outputsize': 200, 'apikey': api_key,
    })
    url = f'https://api.twelvedata.com/time_series?{qs}'
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if data.get('status') == 'error' or 'values' not in data:
        raise RuntimeError(data.get('message', 'Twelve Data error'))
    df = pd.DataFrame(data['values']).rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
    })
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    # Twelve Data returns newest-first; reverse to oldest-first
    df = df.iloc[::-1].reset_index(drop=True)
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()


def _fetch_yfinance(symbol):
    """Fallback data source (rate-limited from datacenter IPs)."""
    import yfinance as yf
    days_needed = LOOKBACK + 30
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_needed * 2)
    df = yf.Ticker(symbol).history(start=start_date, end=end_date, interval="1d")
    if df.empty:
        return None
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].copy().dropna()


def fetch_and_prepare(symbol):
    """Fetch recent stock data and prepare features for prediction."""
    # Prefer Twelve Data; fall back to yfinance if no key or on error.
    df = None
    try:
        df = _fetch_twelvedata(symbol)
    except Exception as e:
        print(f"Twelve Data fetch failed for {symbol}: {e}")
    if df is None or df.empty:
        df = _fetch_yfinance(symbol)

    if df is None or df.empty or len(df) < LOOKBACK:
        return None, None

    # Add technical indicators
    df = add_technical_indicators(df)
    df = df.dropna()

    if len(df) < LOOKBACK:
        return None, None

    # Get current price
    current_price = float(df['Close'].iloc[-1])

    # Take last LOOKBACK days
    features = df[FEATURE_COLUMNS].tail(LOOKBACK).values

    return features, current_price


# ─── Prediction Endpoint ───────────────────────────────────────
@app.route('/predict', methods=['POST'])
def predict():
    """Predict next day's stock price."""
    if model is None:
        return jsonify({'error': 'Model not loaded. Run train.py first.'}), 503

    data = request.get_json()
    symbol = data.get('symbol', '').upper()

    if not symbol:
        return jsonify({'error': 'Symbol is required'}), 400

    try:
        features, current_price = fetch_and_prepare(symbol)

        if features is None:
            return jsonify({'error': f'Not enough data for {symbol}'}), 400

        # Normalize
        scaled = scaler.transform(features)

        # Reshape for LSTM: (1, 60, 13)
        X = scaled.reshape(1, LOOKBACK, len(FEATURE_COLUMNS))

        # Predict
        prediction_scaled = model.predict(X, verbose=0)[0][0]

        # Inverse scale the prediction (Close is at index 3)
        pred_full = np.zeros((1, len(FEATURE_COLUMNS)))
        pred_full[0, 3] = prediction_scaled
        predicted_price = float(scaler.inverse_transform(pred_full)[0, 3])

        # Calculate change
        price_change = predicted_price - current_price
        change_percent = (price_change / current_price) * 100

        # Determine direction and confidence
        direction = 'bullish' if price_change > 0 else 'bearish'

        # Simple confidence based on magnitude of change
        abs_change = abs(change_percent)
        if abs_change > 3:
            confidence = 85
        elif abs_change > 1.5:
            confidence = 72
        elif abs_change > 0.5:
            confidence = 60
        else:
            confidence = 50

        # Multi-day forecast (simple extrapolation for display)
        forecast = []
        last_price = current_price
        daily_change = price_change
        for day in range(1, 8):
            day_price = last_price + (daily_change * (1 - day * 0.1))  # dampening
            forecast.append({
                'day': day,
                'price': round(day_price, 2),
            })
            last_price = day_price

        return jsonify({
            'symbol': symbol,
            'current_price': round(current_price, 2),
            'predicted_price': round(predicted_price, 2),
            'price_change': round(price_change, 2),
            'change_percent': round(change_percent, 2),
            'direction': direction,
            'confidence': confidence,
            'forecast': forecast,
            'model_info': {
                'type': 'LSTM',
                'lookback_days': LOOKBACK,
                'features_used': len(FEATURE_COLUMNS),
            },
            'timestamp': datetime.now().isoformat(),
        })

    except Exception as e:
        print(f"Prediction error for {symbol}: {e}")
        return jsonify({'error': f'Prediction failed: {str(e)}'}), 500


# ─── Health Check ──────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'model_loaded': model is not None,
        'supported_features': FEATURE_COLUMNS,
        'lookback_days': LOOKBACK,
    })


# ─── Main ──────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("  InterStock — ML Prediction Server")
    print("=" * 50)

    # model already loaded at import; reload here only if it failed
    if model is not None or load_model():
        port = int(os.environ.get('PORT', 8000))
        print(f"\n>> Starting prediction server on http://0.0.0.0:{port}")
        print("   POST /predict  — Get stock price prediction")
        print("   GET  /health   — Server status\n")
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        print("\n[ERROR] Cannot start server without a trained model.")
        print("   Run 'python train.py' first to train the model.")
