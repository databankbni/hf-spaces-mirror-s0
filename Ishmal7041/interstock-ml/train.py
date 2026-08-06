"""
InterStock LSTM Stock Price Prediction — Training Script
=========================================================
Downloads historical stock data, engineers features, trains an LSTM model,
evaluates it, and saves the trained model + scaler for the prediction API.

Usage:
    python train.py

Output:
    - models/stock_model.h5      (trained LSTM model)
    - models/scaler.pkl          (MinMaxScaler for normalization)
    - models/training_report.txt (accuracy metrics)
"""

import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib

# ─── Configuration ─────────────────────────────────────────────
SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD', 'NFLX', 'ABNB']
LOOKBACK = 60          # Use last 60 days to predict next day
EPOCHS = 50            # Training epochs
BATCH_SIZE = 32        # Batch size
TRAIN_SPLIT = 0.8      # 80% train, 20% test
DATA_YEARS = 5         # Years of historical data to download
MODEL_DIR = 'models'

# ─── Step 1: Download Data ─────────────────────────────────────
def download_data():
    """Download historical stock data from Yahoo Finance."""
    print("\n[>>] Step 1: Downloading historical data...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=DATA_YEARS * 365)

    all_data = []

    for symbol in SYMBOLS:
        print(f"   Downloading {symbol}...", end=" ")
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")

            if df.empty:
                print("[!] No data")
                continue

            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df['Symbol'] = symbol
            df = df.dropna()
            all_data.append(df)
            print(f"[OK] {len(df)} days")
        except Exception as e:
            print(f"[X] Error: {e}")

    if not all_data:
        raise RuntimeError("No data downloaded. Check your internet connection.")

    combined = pd.concat(all_data)
    print(f"\n   Total records: {len(combined)}")
    return combined


# ─── Step 2: Feature Engineering ────────────────────────────────
def add_technical_indicators(df):
    """Add RSI, MACD, Moving Averages and other technical indicators."""

    # Moving Averages
    df['MA_7'] = df['Close'].rolling(window=7).mean()
    df['MA_21'] = df['Close'].rolling(window=21).mean()

    # RSI (Relative Strength Index)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # Price change percentage
    df['Price_Change'] = df['Close'].pct_change() * 100

    # Volume change
    df['Volume_Change'] = df['Volume'].pct_change() * 100

    # Volatility (standard deviation of close over 14 days)
    df['Volatility'] = df['Close'].rolling(window=14).std()

    return df


def prepare_features(combined_df):
    """Engineer features for each stock and combine."""
    print("\n[>>] Step 2: Engineering features...")

    processed = []

    for symbol in combined_df['Symbol'].unique():
        df = combined_df[combined_df['Symbol'] == symbol].copy()
        df = df.sort_index()
        df = add_technical_indicators(df)
        df = df.dropna()
        processed.append(df)
        print(f"   {symbol}: {len(df)} samples after feature engineering")

    result = pd.concat(processed)
    print(f"\n   Total samples: {len(result)}")
    return result


# ─── Step 3: Normalize & Create Sequences ───────────────────────
FEATURE_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume',
                   'MA_7', 'MA_21', 'RSI', 'MACD', 'MACD_Signal',
                   'Price_Change', 'Volume_Change', 'Volatility']

def create_sequences(data_df):
    """Normalize data and create sliding window sequences."""
    print("\n[>>] Step 3: Normalizing data & creating sequences...")

    scaler = MinMaxScaler(feature_range=(0, 1))

    all_X, all_y = [], []

    for symbol in data_df['Symbol'].unique():
        df = data_df[data_df['Symbol'] == symbol].copy()
        df = df.sort_index()

        features = df[FEATURE_COLUMNS].values

        # Fit scaler on this stock's data
        scaled = scaler.fit_transform(features)

        # Create sliding windows
        for i in range(LOOKBACK, len(scaled)):
            all_X.append(scaled[i - LOOKBACK:i])  # Last 60 days
            all_y.append(scaled[i, 3])              # Next day's Close (index 3)

    X = np.array(all_X)
    y = np.array(all_y)

    print(f"   Sequences created: {len(X)}")
    print(f"   Input shape: {X.shape} (samples, timesteps, features)")

    return X, y, scaler


# ─── Step 4: Train/Test Split ───────────────────────────────────
def split_data(X, y):
    """Split data chronologically into train and test sets."""
    print("\n[>>] Step 4: Splitting data (80% train / 20% test)...")

    split_idx = int(len(X) * TRAIN_SPLIT)

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"   Training samples: {len(X_train)}")
    print(f"   Testing samples:  {len(X_test)}")

    return X_train, X_test, y_train, y_test


# ─── Step 5: Build & Train LSTM Model ──────────────────────────
def build_and_train(X_train, y_train, X_test, y_test):
    """Build LSTM architecture and train the model."""
    print("\n[>>] Step 5: Building & training LSTM model...")

    # Import TensorFlow here so script doesn't crash if not installed
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
    from tensorflow.keras.callbacks import EarlyStopping

    n_timesteps = X_train.shape[1]  # 60
    n_features = X_train.shape[2]   # 13

    print(f"   Input: {n_timesteps} timesteps × {n_features} features")

    # Build model
    model = Sequential([
        Input(shape=(n_timesteps, n_features)),

        # LSTM Layer 1 — extracts sequential patterns
        LSTM(50, return_sequences=True),
        Dropout(0.2),

        # LSTM Layer 2 — deeper pattern recognition
        LSTM(50, return_sequences=False),
        Dropout(0.2),

        # Dense layers — combine patterns into prediction
        Dense(25, activation='relu'),
        Dense(1)  # Output: predicted normalized close price
    ])

    model.compile(
        optimizer='adam',
        loss='mean_squared_error',
        metrics=['mae']
    )

    model.summary()

    # Early stopping — stop if validation loss doesn't improve for 10 epochs
    early_stop = EarlyStopping(
        monitor='val_loss',
        patience=10,
        restore_best_weights=True,
        verbose=1
    )

    print(f"\n   Training for up to {EPOCHS} epochs (with early stopping)...\n")

    history = model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_data=(X_test, y_test),
        callbacks=[early_stop],
        verbose=1
    )

    return model, history


# ─── Step 6: Evaluate Model ────────────────────────────────────
def evaluate_model(model, X_test, y_test, scaler):
    """Evaluate model performance with standard metrics."""
    print("\n[>>] Step 6: Evaluating model...")

    predictions = model.predict(X_test, verbose=0)

    # Create dummy arrays to inverse transform just the Close price
    n_features = len(FEATURE_COLUMNS)

    # Inverse scale predictions
    pred_full = np.zeros((len(predictions), n_features))
    pred_full[:, 3] = predictions.flatten()  # Close is index 3
    pred_prices = scaler.inverse_transform(pred_full)[:, 3]

    # Inverse scale actual values
    actual_full = np.zeros((len(y_test), n_features))
    actual_full[:, 3] = y_test
    actual_prices = scaler.inverse_transform(actual_full)[:, 3]

    # Calculate metrics
    rmse = np.sqrt(mean_squared_error(actual_prices, pred_prices))
    mae = mean_absolute_error(actual_prices, pred_prices)
    r2 = r2_score(actual_prices, pred_prices)

    # MAPE (avoid division by zero)
    non_zero = actual_prices != 0
    mape = np.mean(np.abs((actual_prices[non_zero] - pred_prices[non_zero]) / actual_prices[non_zero])) * 100

    metrics = {
        'rmse': round(float(rmse), 4),
        'mae': round(float(mae), 4),
        'mape': round(float(mape), 4),
        'r2_score': round(float(r2), 4),
    }

    print(f"\n   === MODEL EVALUATION RESULTS ===")
    print(f"   RMSE:  ${rmse:.2f}")
    print(f"   MAE:   ${mae:.2f}")
    print(f"   MAPE:  {mape:.2f}%")
    print(f"   R2:    {r2:.4f}")
    print(f"   ===================================")


    return metrics


# ─── Step 7: Save Everything ───────────────────────────────────
def save_model(model, scaler, metrics):
    """Save the trained model, scaler, and training report."""
    print("\n[>>] Step 7: Saving model and artifacts...")

    os.makedirs(MODEL_DIR, exist_ok=True)

    model_path = os.path.join(MODEL_DIR, 'stock_model.h5')
    scaler_path = os.path.join(MODEL_DIR, 'scaler.pkl')
    report_path = os.path.join(MODEL_DIR, 'training_report.json')

    # Save model
    model.save(model_path)
    print(f"   [OK] Model saved: {model_path}")

    # Save scaler
    joblib.dump(scaler, scaler_path)
    print(f"   [OK] Scaler saved: {scaler_path}")

    # Save training report
    report = {
        'trained_at': datetime.now().isoformat(),
        'symbols': SYMBOLS,
        'lookback_days': LOOKBACK,
        'epochs': EPOCHS,
        'features': FEATURE_COLUMNS,
        'metrics': metrics,
    }

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"   [OK] Report saved: {report_path}")


# ─── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("   InterStock — LSTM Stock Price Prediction Training")
    print("=" * 60)

    # Step 1: Download data
    raw_data = download_data()

    # Step 2: Feature engineering
    featured_data = prepare_features(raw_data)

    # Step 3: Normalize & create sequences
    X, y, scaler = create_sequences(featured_data)

    # Step 4: Split data
    X_train, X_test, y_train, y_test = split_data(X, y)

    # Step 5: Build & train model
    model, history = build_and_train(X_train, y_train, X_test, y_test)

    # Step 6: Evaluate
    metrics = evaluate_model(model, X_test, y_test, scaler)

    # Step 7: Save
    save_model(model, scaler, metrics)

    print("\n" + "=" * 60)
    print("   [DONE] Training complete! Model is ready for predictions.")
    print("   Run 'python server.py' to start the prediction API.")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()
