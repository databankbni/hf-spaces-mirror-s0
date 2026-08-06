---
title: InterStock ML
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# InterStock — ML Prediction Service

LSTM stock-price prediction API (Flask + TensorFlow), deployed on Hugging Face Spaces.

- `POST /predict` — body `{ "symbol": "AAPL" }` → predicted next-day price + direction.
- `GET /health` — service + model status.

Market data via Twelve Data (`TWELVE_DATA_API_KEY` Space secret), with yfinance fallback.
