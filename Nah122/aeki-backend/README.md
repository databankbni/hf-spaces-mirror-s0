---
title: News Dashboard Analytics API
emoji: 📊
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
license: mit
---

# Dashboard Analytics API

FastAPI service providing 20 analytics endpoints for the multilingual news dashboard.

## Features

- 20 comprehensive analytics endpoints
- Real-time metrics
- Historical trends
- Sentiment analysis
- Multilingual support
- Source analytics
- Entity and keyword tracking

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables in .env
CLICKHOUSE_HOST=your-host
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your-password
CLICKHOUSE_SECURE=true

# Run the API
python main.py
```

## API will run on: http://localhost:8001

## Endpoints

### 1. Live News Pulse ✅ IMPLEMENTED
`GET /api/dashboard/live-pulse`

Returns real-time metrics:
- Articles today vs yesterday
- Current sentiment score
- Articles in last hour
- Active sources

**Response:**
```json
{
  "articles_today": 150,
  "articles_yesterday": 120,
  "change_percent": 25.0,
  "trend": "up",
  "current_sentiment": 0.234,
  "sentiment_label": "positive",
  "articles_last_hour": 12,
  "active_sources": 15,
  "timestamp": "2026-04-28T14:00:00Z"
}
```

### 2-20. Coming soon...

## Testing

```bash
# Start the API
python main.py

# Test endpoint
curl http://localhost:8001/api/dashboard/live-pulse
```
