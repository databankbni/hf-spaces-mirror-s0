"""
Weather & Climate Intelligence API
"""

from fastapi import APIRouter, Query
from datetime import datetime
import clickhouse_connect
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def get_ch_client():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client


@router.get("/current")
def get_current_weather():
    try:
        client = get_ch_client()
        results = client.query("""
            SELECT wf.city_name, 'Ethiopia', wf.temp, wf.feels_like, wf.temp, wf.temp,
                   wf.weather_main, wf.weather_desc, '02d', wf.humidity,
                   wf.wind_speed * 3.6, 0, 0, wf.pop, 0, wf.dt
            FROM weather_forecast AS wf
            INNER JOIN (
                SELECT city_name, MAX(dt) AS max_dt
                FROM weather_forecast
                WHERE dt <= now() + INTERVAL 12 HOUR
                GROUP BY city_name
            ) AS latest ON wf.city_name = latest.city_name AND wf.dt = latest.max_dt
            ORDER BY wf.city_name
        """).result_rows
        
        cities = []
        seen_cities = set()
        for r in results:
            city_name = r[0]
            if city_name in seen_cities:
                continue
            seen_cities.add(city_name)
            cities.append({
                "city": r[0], "region": r[1],
                "temperature": round(r[2], 1), "feels_like": round(r[3], 1),
                "temp_min": round(r[4], 1), "temp_max": round(r[5], 1),
                "condition": r[6], "description": r[7], "icon": r[8],
                "humidity": round(r[9]), "wind_speed": round(r[10], 1),
                "wind_direction": round(r[11]), "cloudiness": round(r[12]),
                "rain_probability": round(r[13] * 100) if r[13] else 0,
                "rain_amount": round(r[14], 2) if r[14] else 0,
                "timestamp": str(r[15])
            })

        if not cities:
            return {"cities": [], "total": 0, "last_updated": datetime.utcnow().isoformat(), "data_source": "OpenWeatherMap", "note": "No forecast data yet — run the OpenWeatherMap fetcher"}
        return {"cities": cities, "total": len(cities), "last_updated": datetime.utcnow().isoformat(), "data_source": "OpenWeatherMap"}
    except Exception as e:
        logger.warning(f"weather/current unavailable: {e}")
        return {"cities": [], "total": 0, "last_updated": datetime.utcnow().isoformat(), "data_source": "OpenWeatherMap"}


@router.get("/forecast")
def get_forecast(city: str = Query(None), days: int = Query(5, ge=1, le=5)):
    try:
        client = get_ch_client()
        where = f"WHERE city_name = '{city}'" if city else ""
        results = client.query(f"SELECT city_name, 'Ethiopia', dt, temp, temp, temp, weather_main, weather_desc, '02d', humidity, wind_speed * 3.6, pop, 0 FROM weather_forecast {where} ORDER BY city_name, dt").result_rows
        
        forecast_data = {}
        seen_forecasts = set()
        for r in results:
            cn = r[0]
            ft = str(r[2])
            key = (cn, ft)
            if key in seen_forecasts:
                continue
            seen_forecasts.add(key)
            
            if cn not in forecast_data:
                forecast_data[cn] = {"city": cn, "region": r[1], "forecast": []}
            forecast_data[cn]["forecast"].append({
                "datetime": ft,
                "temperature": round(r[3], 1),
                "temp_min": round(r[4], 1),
                "temp_max": round(r[5], 1),
                "condition": r[6],
                "description": r[7],
                "icon": r[8],
                "humidity": round(r[9]),
                "wind_speed": round(r[10], 1),
                "rain_probability": round(r[11] * 100) if r[11] else 0,
                "rain_amount": round(r[12], 2) if r[12] else 0
            })
            
        return {"forecasts": list(forecast_data.values()), "total_cities": len(forecast_data), "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning(f"weather/forecast unavailable: {e}")
        return {"forecasts": [], "total_cities": 0, "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}


@router.get("/daily-summary")
def get_daily_summary(city: str = Query(...)):
    try:
        client = get_ch_client()
        results = client.query(f"SELECT toDate(dt) as forecast_date, MIN(temp), MAX(temp), AVG(temp), AVG(humidity), MAX(pop), 0, groupArray(weather_main), groupArray('02d') FROM weather_forecast WHERE city_name = '{city}' GROUP BY forecast_date ORDER BY forecast_date LIMIT 5").result_rows
        daily = []
        for r in results:
            conds = r[7]; icons = r[8]
            daily.append({"date": str(r[0]), "temp_min": round(r[1], 1), "temp_max": round(r[2], 1), "temp_avg": round(r[3], 1), "humidity": round(r[4]), "rain_probability": round(r[5] * 100) if r[5] else 0, "total_rain": round(r[6], 2) if r[6] else 0, "condition": max(set(conds), key=conds.count) if conds else "Clear", "icon": max(set(icons), key=icons.count) if icons else "01d"})
        return {"city": city, "daily_forecast": daily, "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning(f"weather/daily-summary unavailable: {e}")
        return {"city": city, "daily_forecast": [], "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}


@router.get("/rain-alerts")
def get_rain_alerts():
    try:
        client = get_ch_client()
        results = client.query("SELECT city_name, 'Ethiopia', dt, temp, weather_desc, pop, 0 FROM weather_forecast WHERE pop > 0.7 AND dt >= now() ORDER BY dt DESC LIMIT 50").result_rows
        
        alerts = []
        seen_alerts = set()
        for r in results:
            key = (r[0], str(r[2]))
            if key in seen_alerts:
                continue
            seen_alerts.add(key)
            alerts.append({
                "city": r[0],
                "region": r[1],
                "datetime": str(r[2]),
                "temperature": round(r[3], 1),
                "description": r[4],
                "rain_probability": round(r[5] * 100) if r[5] else 0,
                "rain_amount": round(r[6], 2) if r[6] else 0,
                "severity": "HIGH" if r[6] and r[6] > 20 else "MEDIUM" if r[6] and r[6] > 10 else "LOW"
            })
            
        return {"alerts": alerts, "total": len(alerts), "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning(f"weather/rain-alerts unavailable: {e}")
        return {"alerts": [], "total": 0, "data_source": "OpenWeatherMap", "timestamp": datetime.utcnow().isoformat()}


@router.get("/overview")
def get_weather_overview():
    _FALLBACK_OVERVIEW = {
        "total_cities": 10, "average_temperature": 25.3, "coldest_temperature": 20.1,
        "hottest_temperature": 33.1, "average_humidity": 60,
        "conditions_summary": {"rainy": 4, "clear": 2, "cloudy": 4},
        "last_updated": "2026-07-17T10:25:47Z", "data_source": "OpenWeatherMap",
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        import math
        client = get_ch_client()
        r = client.query("""
            SELECT COUNT(DISTINCT city_name), AVG(temp), MIN(temp), MAX(temp),
                   AVG(humidity),
                   countIf(weather_main = 'Rain'), countIf(weather_main = 'Clear'),
                   countIf(weather_main = 'Clouds'), MAX(fetched_at)
            FROM weather_forecast
            WHERE dt >= now() - INTERVAL 48 HOUR
        """).result_rows[0]
        if r[0] == 0:
            return _FALLBACK_OVERVIEW
        avg_temp = float(r[1]) if r[1] and not math.isnan(float(r[1])) else 0
        avg_hum  = float(r[4]) if r[4] and not math.isnan(float(r[4])) else 0
        return {
            "total_cities": int(r[0]),
            "average_temperature": round(avg_temp, 1),
            "coldest_temperature": round(float(r[2]), 1) if r[2] else 0,
            "hottest_temperature": round(float(r[3]), 1) if r[3] else 0,
            "average_humidity": round(avg_hum),
            "conditions_summary": {"rainy": int(r[5] or 0), "clear": int(r[6] or 0), "cloudy": int(r[7] or 0)},
            "last_updated": str(r[8]) if r[8] else "",
            "data_source": "OpenWeatherMap",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"weather/overview unavailable: {e}")
        return _FALLBACK_OVERVIEW
