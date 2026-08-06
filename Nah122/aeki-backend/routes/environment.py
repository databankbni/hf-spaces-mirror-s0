from fastapi import APIRouter
from datetime import datetime, timezone
import logging
import os
import clickhouse_connect

router = APIRouter()
logger = logging.getLogger(__name__)

def _ch():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client

@router.get("/alerts")
def get_alerts(limit: int = 50):
    """Returns real-time environmental alerts (Flood, Deforestation, etc.)"""
    try:
        c = _ch()
        rows = c.query(
            f"SELECT id, source, type, date, region, lat, lon, severity, confidence, metadata "
            f"FROM environmental_alerts FINAL ORDER BY date DESC, ingested_at DESC LIMIT {limit}"
        ).result_rows
        return {
            "alerts": [
                {
                    "id": r[0], "source": r[1], "type": r[2], "date": str(r[3]),
                    "region": r[4], "lat": r[5], "lon": r[6], "severity": r[7],
                    "confidence": r[8], "metadata": r[9]
                } for r in rows
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        # Fallback when DB empty or rate-limited
        return {
            "alerts": [
                {
                    "id": "1", "source": "GDELT", "type": "Drought", "date": datetime.now(timezone.utc).isoformat(),
                    "region": "Somali", "lat": 6.5, "lon": 43.0, "severity": "HIGH",
                    "confidence": 0.85, "metadata": "{}"
                },
                {
                    "id": "2", "source": "GDELT", "type": "Flood", "date": datetime.now(timezone.utc).isoformat(),
                    "region": "Afar", "lat": 11.5, "lon": 41.0, "severity": "MODERATE",
                    "confidence": 0.70, "metadata": "{}"
                }
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@router.get("/vegetation")
def get_vegetation(region: str = None):
    """Returns regional vegetation health indicators (VCI, VHI, NDVI)"""
    try:
        c = _ch()
        where = f"WHERE region = '{region}'" if region else ""
        rows = c.query(
            f"SELECT region, admin2, date, vci, vhi, ndvi "
            f"FROM vegetation_health FINAL {where} ORDER BY date DESC LIMIT 100"
        ).result_rows
        return {
            "data": [
                {
                    "region": r[0], "admin2": r[1], "date": str(r[2]),
                    "vci": round(float(r[3]), 2), "vhi": round(float(r[4]), 2),
                    "ndvi": round(float(r[5]), 2)
                } for r in rows
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching vegetation: {e}")
        # Fallback when DB empty or rate-limited
        return {
            "data": [
                {
                    "region": "Oromia", "admin2": "Bale", "date": datetime.now(timezone.utc).isoformat(),
                    "vci": 45.2, "vhi": 50.1, "ndvi": 0.65
                },
                {
                    "region": "Amhara", "admin2": "Gondar", "date": datetime.now(timezone.utc).isoformat(),
                    "vci": 30.5, "vhi": 35.2, "ndvi": 0.45
                }
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@router.get("/media")
def get_media_alerts(limit: int = 50):
    """Returns media-detected environmental alerts (GDELT based)"""
    try:
        c = _ch()
        rows = c.query(
            f"SELECT id, theme, url, source, date, location, tone, sentiment "
            f"FROM environmental_media_alerts FINAL ORDER BY date DESC, ingested_at DESC LIMIT {limit}"
        ).result_rows
        return {
            "media_alerts": [
                {
                    "id": r[0], "theme": r[1], "url": r[2], "source": r[3],
                    "date": str(r[4]), "location": r[5], "tone": r[6], "sentiment": r[7]
                } for r in rows
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching media alerts: {e}")
        # Fallback when DB empty or rate-limited
        return {
            "media_alerts": [
                {
                    "id": "1", "theme": "Water Scarcity", "url": "https://example.com/news1", "source": "Local News",
                    "date": datetime.now(timezone.utc).isoformat(), "location": "Tigray", "tone": -5.2, "sentiment": "NEGATIVE"
                }
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }
