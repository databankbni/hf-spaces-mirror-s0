from flask import Flask, request, jsonify, render_template
import yfinance as yf
import pandas as pd
from prophet import Prophet

app = Flask(__name__)

# Horizons we support, in days
HORIZONS = [7, 30, 90, 180, 365]


def fetch_and_clean(ticker, include_volume=False):
    """Fetch live data for a ticker and run it through the cleaning pipeline."""
    stock = yf.Ticker(ticker)
    data = stock.history(start="2019-01-01")

    if data.empty:
        return None

    data = data.reset_index()
    data = data.rename(columns={"Date": "ds", "Close": "y"})
    data["ds"] = data["ds"].dt.tz_localize(None)

    # Cleaning pipeline
    data = data.dropna()
    data = data.drop_duplicates(subset=["ds"])
    data = data.sort_values("ds").reset_index(drop=True)

    if include_volume:
        data = data[["ds", "y", "Volume"]]
    else:
        data = data[["ds", "y"]]

    return data


# Based on backtesting experiments: which model performs better per horizon
# True  = Volume-enhanced model
# False = Baseline model (ds + y only)
BEST_MODEL_PER_HORIZON = {
    7:   True,   # Volume wins: 1.72% vs 1.92% MAPE
    30:  False,  # Baseline wins: 5.81% vs 6.00% MAPE
    90:  True,   # Volume wins: 10.89% vs 11.23% MAPE
    180: True,   # Volume wins: 19.93% vs 20.32% MAPE
    365: False,  # Baseline wins: 32.93% vs 32.99% MAPE
}


def build_and_predict(data, horizon, use_volume=False):
    """Train Prophet on full data and return forecast for the given horizon."""
    m = Prophet(daily_seasonality=False)

    if use_volume:
        m.add_regressor("Volume")
        m.fit(data)
        future = m.make_future_dataframe(periods=horizon)
        avg_volume = data["Volume"].mean()
        future = future.merge(data[["ds", "Volume"]], on="ds", how="left")
        future["Volume"] = future["Volume"].fillna(avg_volume)
    else:
        m.fit(data)
        future = m.make_future_dataframe(periods=horizon)

    forecast = m.predict(future)
    return forecast


def evaluate_horizon(data, horizon_days, use_volume=False):
    """Train on everything except the last `horizon_days`, test on that holdout window."""
    cutoff = data["ds"].max() - pd.DateOffset(days=horizon_days)
    train = data[data["ds"] <= cutoff]
    test = data[data["ds"] > cutoff]

    if len(train) < 60 or len(test) == 0:
        return None

    m = Prophet(daily_seasonality=False)

    if use_volume:
        m.add_regressor("Volume")
        m.fit(train)
        future = m.make_future_dataframe(periods=horizon_days)
        avg_volume = train["Volume"].mean()
        future = future.merge(data[["ds", "Volume"]], on="ds", how="left")
        future["Volume"] = future["Volume"].fillna(avg_volume)
    else:
        m.fit(train)
        future = m.make_future_dataframe(periods=horizon_days)

    forecast = m.predict(future)
    forecast = forecast[["ds", "yhat"]]

    results = test.merge(forecast, on="ds")
    if results.empty:
        return None

    mae = (results["y"] - results["yhat"]).abs().mean()
    mape = ((results["y"] - results["yhat"]).abs() / results["y"]).mean() * 100
    rmse = ((results["y"] - results["yhat"]) ** 2).mean() ** 0.5

    return {"horizon": horizon_days, "mae": round(mae, 2), "mape": round(mape, 2), "rmse": round(rmse, 2)}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/predict", methods=["POST"])
def predict():
    payload = request.json or {}
    ticker = payload.get("ticker", "GOOG").upper()
    horizon = int(payload.get("horizon", 30))

    if horizon not in HORIZONS:
        return jsonify({"error": f"Horizon must be one of {HORIZONS}"}), 400

    # --- Determine best model for this horizon based on backtesting ---
    use_volume = BEST_MODEL_PER_HORIZON.get(horizon, False)

    # Fetch data — include Volume column if the best model for this horizon needs it
    data = fetch_and_clean(ticker, include_volume=use_volume)
    if data is None:
        return jsonify({"error": f"No data found for ticker '{ticker}'. Please check the symbol and try again."}), 400

    if len(data) < 90:
        return jsonify({"error": f"Not enough history for '{ticker}' to make a reliable forecast."}), 400

    # --- Main forecast using the best model for this horizon ---
    forecast = build_and_predict(data, horizon, use_volume=use_volume)

    result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(horizon)
    result["ds"] = result["ds"].dt.strftime("%Y-%m-%d")

    # Recent actual history to plot alongside the forecast (last 180 days for context)
    history = data.tail(180).copy()
    history["ds"] = history["ds"].dt.strftime("%Y-%m-%d")

    # --- Accuracy metrics across all horizons (backtested, using best model per horizon) ---
    # We need volume data for horizons that use the Volume model
    data_with_volume = fetch_and_clean(ticker, include_volume=True)

    accuracy_table = []
    for h in HORIZONS:
        h_use_volume = BEST_MODEL_PER_HORIZON.get(h, False)
        h_data = data_with_volume if h_use_volume else data
        if h_data is not None:
            metrics = evaluate_horizon(h_data, h, use_volume=h_use_volume)
            if metrics:
                accuracy_table.append(metrics)

    # --- Plain-language summary: current price vs target date price ---
    current_price = round(float(data["y"].iloc[-1]), 2)
    current_date = data["ds"].iloc[-1].strftime("%Y-%m-%d")

    target_row = result.iloc[-1]
    target_price = round(float(target_row["yhat"]), 2)
    target_date = target_row["ds"]
    target_low = round(float(target_row["yhat_lower"]), 2)
    target_high = round(float(target_row["yhat_upper"]), 2)

    change_amount = round(target_price - current_price, 2)
    change_percent = round((change_amount / current_price) * 100, 2)

    summary = {
        "current_price": current_price,
        "current_date": current_date,
        "target_price": target_price,
        "target_date": target_date,
        "target_low": target_low,
        "target_high": target_high,
        "change_amount": change_amount,
        "change_percent": change_percent
    }

    return jsonify({
        "ticker": ticker,
        "horizon": horizon,
        "history": history.to_dict(orient="records"),
        "forecast": result.to_dict(orient="records"),
        "accuracy_table": accuracy_table,
        "summary": summary
    })

# Old
# if __name__ == "__main__":
#     app.run(debug=True)

# Making ts accessible from outside the container
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=False)