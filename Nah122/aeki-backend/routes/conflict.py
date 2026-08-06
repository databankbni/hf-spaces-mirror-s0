"""
Conflict Intelligence API
Uses ACLED + GDELT data from the 'events' table
"""

from fastapi import APIRouter, Query
from datetime import datetime, timedelta
import clickhouse_connect
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# UCDP = verified conflict statistics
UCDP_FILTER = "year >= 2026"

# Pipeline table `events` (conflict-fetch-and-processing)
# Note: event_type filter removed — AI may produce varied category strings.
# We filter only on source_system and verification status.
GDELT_EVENTS_FILTER = """
    source_system LIKE 'gdelt%'
    AND event_type != 'Noise'
    AND is_verified = 1
    AND toYear(event_date) >= 2026
"""

# Unverified (pending review) fallback — shown when no verified events exist
GDELT_PENDING_FILTER = """
    source_system LIKE 'gdelt%'
    AND is_verified = 0
    AND toYear(event_date) >= 2026
"""

# GDELT BigQuery table `gdelt_events` (gdelt-bq fetcher) — primary live source today
GDELT_LIVE_TYPES = (
    "Military Action", "Protest", "Demand / Pressure", "Armed Assault",
    "Violence against civilians", "Explosions/Remote violence", "Fight",
    "Coercion", "Threats", "Investigate",
)
GDELT_LIVE_TYPES_SQL = ", ".join(f"'{t}'" for t in GDELT_LIVE_TYPES)


def _parse_gdelt_event_date(raw) -> str:
    """gdelt_events.event_date is YYYYMMDD string."""
    if raw is None:
        return ""
    s = str(raw).strip()[:8]
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return str(raw)[:10]


def _gdelt_live_where(extra: str = "") -> str:
    base = f"""
        (location_country = 'ET' OR location_name ILIKE '%Ethiopia%')
        AND event_type IN ({GDELT_LIVE_TYPES_SQL})
    """
    return f"{base} AND {extra}" if extra else base


def _severity_from_goldstein(goldstein: float, mentions: int) -> str:
    if goldstein <= -7 or mentions >= 50:
        return "CRITICAL"
    if goldstein <= -3 or mentions >= 20:
        return "HIGH"
    if goldstein < 0 or mentions >= 5:
        return "MODERATE"
    return "LOW"


def _row_from_gdelt_events(row) -> dict:
    """Map gdelt_events query row to live-feed API shape."""
    event_date = _parse_gdelt_event_date(row[0])
    event_type = row[1] or "Conflict event"
    location = row[2] or "Ethiopia"
    actor1, actor2 = row[3] or "", row[4] or ""
    actor = actor1 if actor1 and actor1.upper() not in ("N/A", "NONE", "UNKNOWN") else actor2
    goldstein = float(row[5] or 0)
    mentions = int(row[6] or 0)
    source_url = row[7] or ""
    lat, lon = float(row[8] or 0), float(row[9] or 0)
    event_label = row[10] or ""

    description = (
        f"{event_type} ({event_label}) reported in {location}."
        + (f" Actors: {actor1} vs {actor2}." if actor1 and actor2 else "")
        + " Source: GDELT media monitoring."
    )

    return {
        "date": event_date,
        "type": event_type,
        "location": location,
        "region": "Ethiopia",
        "fatalities": 0,
        "actor": actor,
        "description": description[:500],
        "source_url": source_url,
        "source_system": "gdelt_live",
        "severity": _severity_from_goldstein(goldstein, mentions),
        "latitude": lat,
        "longitude": lon,
    }


def _row_from_events_table(row) -> dict:
    """Map legacy `events` table row to live-feed API shape."""
    notes = row[7] or ""
    if notes.startswith("GDELT EventCode="):
        notes = ""
    actor_raw = row[5] or row[6] or ""
    actor = "" if actor_raw.upper() in ("N/A", "NONE", "UNKNOWN", "NULL") else actor_raw
    source_system = row[9] or "gdelt"
    ai_summary = row[10] or ""
    description = ai_summary if ai_summary else notes
    if not description and str(source_system).startswith("gdelt"):
        event_type = row[1] or "Conflict event"
        location = row[2] or "Ethiopia"
        actor_str = f" involving {actor}" if actor else ""
        description = f"{event_type} reported in {location}{actor_str}. Source: GDELT media monitoring."

    return {
        "date": str(row[0]),
        "type": row[1],
        "location": row[2],
        "region": row[3],
        "fatalities": row[4],
        "actor": actor,
        "description": description[:500] if description else "",
        "source_url": row[8] if str(source_system).startswith("gdelt") else "",
        "source_system": source_system,
        "severity": "CRITICAL" if row[4] > 20 else "HIGH" if row[4] > 10 else "MODERATE" if row[4] > 0 else "LOW",
        "latitude": row[11],
        "longitude": row[12],
    }


def _fetch_live_gdelt_events(client, limit: int) -> list[dict]:
    """Live feed from verified events instead of raw gdelt_events to avoid unverified noise."""
    return _fetch_pipeline_gdelt_events(client, limit)


def _fetch_pipeline_gdelt_events(client, limit: int) -> list[dict]:
    """Live feed from `events` table (conflict-fetch-and-processing pipeline).
    Falls back to unverified (pending AI review) events if no verified ones exist.
    """
    try:
        rows = client.query(f"""
            SELECT DISTINCT event_date, event_type, location, admin2, fatalities,
                   actor1, actor2, notes, source, source_system, ai_summary, lat, lon
            FROM events FINAL
            WHERE {GDELT_EVENTS_FILTER}
            ORDER BY event_date DESC, ingested_at DESC
            LIMIT {limit}
        """).result_rows
        if rows:
            return [_row_from_events_table(r) for r in rows]

        # Fallback: show unverified pending events if no verified ones exist
        logger.info("No verified GDELT events found; falling back to unverified pending queue")
        rows = client.query(f"""
            SELECT DISTINCT event_date, event_type, location, admin2, fatalities,
                   actor1, actor2, notes, source, source_system, ai_summary, lat, lon
            FROM events FINAL
            WHERE {GDELT_PENDING_FILTER}
            ORDER BY event_date DESC, ingested_at DESC
            LIMIT {limit}
        """).result_rows
        result = [_row_from_events_table(r) for r in rows]
        # Tag them as pending so the UI knows
        for ev in result:
            ev["source_system"] = "gdelt_pending"
            ev["severity"] = "LOW"
        return result

    except Exception as e:
        logger.warning(f"events table GDELT query failed: {e}")
        return []


def get_ch_client():
    try:
        from database.clickhouse_client import get_clickhouse_client
        return get_clickhouse_client().client
    except Exception as e:
        logger.error(f"❌ ClickHouse Connection Failed: {e}")
        raise e


def ensure_schema():
    """Ensure the events table has columns for verification and dashboard requirements."""
    try:
        client = get_ch_client()
        columns = client.query("DESCRIBE TABLE events").result_rows
        col_names = [c[0] for c in columns]
        
        if "is_verified" not in col_names:
            client.command("ALTER TABLE events ADD COLUMN is_verified UInt8 DEFAULT 0")
        
        if "ai_summary" not in col_names:
            client.command("ALTER TABLE events ADD COLUMN ai_summary String DEFAULT ''")

        if "admin2" not in col_names:
            client.command("ALTER TABLE events ADD COLUMN admin2 String DEFAULT ''")

        if "fatalities" not in col_names:
            client.command("ALTER TABLE events ADD COLUMN fatalities Int32 DEFAULT 0")

        if "ingested_at" not in col_names:
            client.command("ALTER TABLE events ADD COLUMN ingested_at DateTime DEFAULT now()")
            
        logger.info("✅ Events schema verified")
    except Exception as e:
        logger.warning(f"⚠️ Schema verification skipped: {e}")


# Schema check runs lazily on first request (avoids startup failure on HF)
_schema_checked = False

def _lazy_ensure_schema():
    global _schema_checked
    if not _schema_checked:
        ensure_schema()
        _schema_checked = True


@router.get("/overview")
@router.get("/statistics")
def get_conflict_overview():
    """
    Conflict Command Center Overview.
    Uses MAX(event_date) as reference so it works regardless of data lag.
    """
    try:
        _lazy_ensure_schema()
        logger.info("📡 Incoming request for /overview")
        client = get_ch_client()

        total_result = client.query(f"""
            SELECT COUNT(*), SUM(deaths_total), MIN(date_start), MAX(date_start)
            FROM ucdp_events
            WHERE {UCDP_FILTER}
        """).result_rows[0]

        latest_date = total_result[3]

        if not latest_date:
            return {
                "total_events": 0,
                "total_fatalities": 0,
                "data_source": "Empty Database",
                "date_range": {"start": "N/A", "end": "N/A"},
                "recent_30_days": {"events": 0, "fatalities": 0, "trend_percent": 0},
                "intensity_score": 0,
                "intensity_level": "LOW",
                "event_types": []
            }

        type_results_raw = client.query(f"""
            SELECT 
                CASE 
                    WHEN type_of_violence = 1 THEN 'STATE-BASED'
                    WHEN type_of_violence = 2 THEN 'NON-STATE'
                    WHEN type_of_violence = 3 THEN 'ONE-SIDED'
                    ELSE 'OTHER'
                END as type, 
                COUNT(*) as count, SUM(deaths_total) as fatalities
            FROM ucdp_events 
            WHERE {UCDP_FILTER}
            GROUP BY type ORDER BY count DESC
        """).result_rows

        # --- Simple Cleanup Logic ---
        normalized_types = {}
        for row in type_results_raw:
            t = row[0] or "UNKNOWN"
            if t not in normalized_types:
                normalized_types[t] = {"count": 0, "fatalities": 0}
            normalized_types[t]["count"] += row[1]
            normalized_types[t]["fatalities"] += row[2]

        # Convert back to sorted list for the frontend
        type_results = sorted(
            [(k, v["count"], v["fatalities"]) for k, v in normalized_types.items()],
            key=lambda x: x[1], reverse=True
        )

        recent_result = client.query(f"""
            SELECT COUNT(*), SUM(deaths_total) FROM ucdp_events
            WHERE date_start >= toDate('{latest_date}') - INTERVAL 30 DAY
              AND {UCDP_FILTER}
        """).result_rows[0]

        previous_result = client.query(f"""
            SELECT COUNT(*), SUM(deaths_total) FROM ucdp_events
            WHERE date_start >= toDate('{latest_date}') - INTERVAL 60 DAY
              AND date_start <  toDate('{latest_date}') - INTERVAL 30 DAY
              AND {UCDP_FILTER}
        """).result_rows[0]

        recent_count      = recent_result[0] or 0
        recent_fatalities = recent_result[1] or 0
        previous_count    = previous_result[0] or 0
        trend = round(((recent_count - previous_count) / previous_count * 100), 1) if previous_count > 0 else 0

        events_score   = min((recent_count / 500) * 100, 100) * 0.4
        fatality_rate  = (recent_fatalities / recent_count) if recent_count > 0 else 0
        fatality_score = min((fatality_rate / 10) * 100, 100) * 0.4
        diversity_score = (len(type_results) / 6) * 100 * 0.2
        intensity_score = round(events_score + fatality_score + diversity_score, 1)

        return {
            "total_events":     total_result[0],
            "total_fatalities": total_result[1],
            "data_source":      "UCDP Verified Intelligence",
            "data_source_url":  "https://ucdp.uu.se",
            "date_range": {"start": str(total_result[2]), "end": str(total_result[3])},
            "recent_30_days": {
                "events":         recent_count,
                "fatalities":     recent_fatalities,
                "trend_percent":  trend,
                "reference_date": str(latest_date),
                "note":           f"Last Updated: {latest_date}"
            },
            "intensity_score": intensity_score,
            "intensity_level": "CRITICAL" if intensity_score > 75 else "HIGH" if intensity_score > 50 else "MODERATE" if intensity_score > 25 else "LOW",
            "event_types": [
                {"type": r[0], "count": r[1], "fatalities": r[2],
                 "percentage": round((r[1] / total_result[0]) * 100, 1)}
                for r in type_results
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/overview unavailable: {e}")
        return {"total_events": 0, "total_fatalities": 0, "date_range": {},
                "recent_30_days": {"events": 0, "fatalities": 0, "trend_percent": 0, "note": ""},
                "intensity_score": 0, "intensity_level": "LOW", "event_types": [],
                "timestamp": datetime.utcnow().isoformat()}


@router.get("/timeline")
def get_conflict_timeline(
    days: int = Query(90, ge=7, le=1000),
    year: int = Query(None)
):
    """Daily conflict timeline — supports relative days or specific year."""
    try:
        client = get_ch_client()
        
        if year:
            where_clause = f"WHERE year = {year} AND {UCDP_FILTER}"
        else:
            latest_date_res = client.query(f"SELECT MAX(date_start) FROM ucdp_events WHERE {UCDP_FILTER}").result_rows[0][0]
            if not latest_date_res:
                return {"timeline": [], "days": days, "total_events": 0, "total_fatalities": 0, "timestamp": datetime.utcnow().isoformat()}
            where_clause = f"WHERE date_start >= toDate('{latest_date_res}') - INTERVAL {days} DAY AND {UCDP_FILTER}"

        # 1. Get UCDP Data (The Foundation)
        ucdp_results = client.query(f"""
            SELECT date_start as date, COUNT(*) as events, SUM(deaths_total) as fatalities, 'ucdp' as source
            FROM ucdp_events
            {where_clause}
            GROUP BY date ORDER BY date
        """).result_rows

        # 2. Get GDELT Data for the "Gap" (From last UCDP date to today)
        last_ucdp_date = ucdp_results[-1][0] if ucdp_results else datetime.now().date() - timedelta(days=90)
        
        gdelt_results = client.query(f"""
            SELECT
                event_date AS date,
                COUNT(*) AS events,
                SUM(fatalities) AS total_fatalities,
                'gdelt' AS source
            FROM events FINAL
            WHERE event_date > toDate('{last_ucdp_date}')
              AND is_verified = 1
              AND source_system LIKE 'gdelt%'
            GROUP BY date
            ORDER BY date
        """).result_rows

        # 3. Combine and Format
        combined = []
        for r in ucdp_results:
            combined.append({"date": str(r[0]), "events": r[1], "fatalities": r[2], "source": "verified"})
        for r in gdelt_results:
            combined.append({"date": str(r[0]), "events": r[1], "fatalities": r[2], "source": "live"})
        
        return {
            "timeline": combined,
            "days": days,
            "total_events": sum(r[1] for r in ucdp_results + gdelt_results),
            "total_fatalities": sum(r[2] for r in ucdp_results + gdelt_results),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/timeline unavailable: {e}")
        return {"timeline": [], "days": days, "total_events": 0, "total_fatalities": 0,
                "timestamp": datetime.utcnow().isoformat()}


@router.get("/heatmap")
def get_conflict_heatmap(limit: int = Query(500, ge=10, le=3000)):
    """Geographic heatmap — includes source_system for 2026 GDELT badge."""
    try:
        client = get_ch_client()
        # 1. Get UCDP Data (Verified)
        ucdp_results = client.query(f"""
            SELECT latitude, longitude, conflict_name, deaths_total, date_start, region, 'ucdp' as source_system, source_headline
            FROM ucdp_events
            WHERE latitude != 0 AND longitude != 0
              AND latitude BETWEEN 3.0 AND 15.5
              AND longitude BETWEEN 33.0 AND 48.0
              AND {UCDP_FILTER}
            ORDER BY date_start DESC
            LIMIT {limit}
        """).result_rows

        # 2. Get GDELT Data (Live Signals for the Gap)
        # We only pull GDELT events that are NEWER than our latest UCDP data
        last_ucdp_date = ucdp_results[0][4] if ucdp_results else datetime.now().date() - timedelta(days=60)
        
        gdelt_results = client.query(f"""
            SELECT lat, lon, event_type, fatalities, event_date, location,
                   source_system, ai_summary
            FROM events FINAL
            WHERE lat != 0 AND lon != 0
              AND is_verified = 1
              AND source_system LIKE 'gdelt%'
              AND event_date > toDate('{last_ucdp_date}')
              AND lat BETWEEN 3.0 AND 15.5
              AND lon BETWEEN 33.0 AND 48.0
            ORDER BY event_date DESC, ingested_at DESC
            LIMIT 200
        """).result_rows

        # 3. Combine
        combined_events = []
        for r in ucdp_results:
            combined_events.append({
                "lat": r[0], "lon": r[1], "type": r[2], "fatalities": r[3],
                "date": str(r[4]), "location": r[5], "source_system": r[6], "description": r[7],
                "is_2026": True
            })
        for r in gdelt_results:
            combined_events.append({
                "lat": r[0], "lon": r[1], "type": r[2],
                "fatalities": int(r[3] or 0),
                "date": _parse_gdelt_event_date(r[4]),
                "location": r[5], "source_system": r[6],
                "description": f"GDELT: {r[7]}" if r[7] else f"Live report from {r[5]}",
                "is_2026": True,
            })

        return {
            "events": combined_events,
            "count": len(combined_events),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/heatmap unavailable: {e}")
        return {"events": [], "count": 0, "timestamp": datetime.utcnow().isoformat()}


@router.get("/actors")
def get_top_actors(limit: int = Query(15, ge=5, le=50)):
    try:
        client = get_ch_client()
        results = client.query(f"""
            SELECT side_a, COUNT(*) as events, SUM(deaths_total) as fatalities
            FROM ucdp_events WHERE side_a != '' AND {UCDP_FILTER}
            GROUP BY side_a ORDER BY events DESC LIMIT {limit}
        """).result_rows
        return {
            "actors": [{"name": r[0], "events": r[1], "fatalities": r[2],
                        "lethality_rate": round(r[2] / r[1], 2) if r[1] > 0 else 0}
                       for r in results],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/actors unavailable: {e}")
        return {"actors": [], "timestamp": datetime.utcnow().isoformat()}


@router.get("/hotspots")
def get_conflict_hotspots(limit: int = Query(10, ge=5, le=30)):
    try:
        client = get_ch_client()
        results = client.query(f"""
            SELECT region, 'Ethiopia' as admin2, COUNT(*) as events, SUM(deaths_total) as fatalities, MAX(date_start) as last_event
            FROM ucdp_events WHERE region != '' AND {UCDP_FILTER}
            GROUP BY region ORDER BY events DESC LIMIT {limit}
        """).result_rows
        return {
            "hotspots": [{"location": r[0], "region": r[1], "events": r[2], "fatalities": r[3],
                          "last_event": str(r[4]),
                          "risk_level": "EXTREME" if r[2] > 100 else "HIGH" if r[2] > 50 else "MODERATE" if r[2] > 20 else "LOW"}
                         for r in results],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/hotspots unavailable: {e}")
        return {"hotspots": [], "timestamp": datetime.utcnow().isoformat()}


@router.get("/monthly-trends")
def get_monthly_trends():
    try:
        client = get_ch_client()
        results = client.query(f"""
            SELECT toStartOfMonth(date_start) as month, COUNT(*) as events,
                   SUM(deaths_total) as fatalities, COUNT(DISTINCT type_of_violence) as event_types,
                   COUNT(DISTINCT region) as locations
            FROM ucdp_events 
            WHERE {UCDP_FILTER}
            GROUP BY month ORDER BY month
        """).result_rows
        return {
            "trends": [{"month": str(r[0]), "events": r[1], "fatalities": r[2],
                        "event_types": r[3], "locations": r[4],
                        "intensity": round((r[1] / 100) * 50 + (r[2] / 200) * 50, 1)}
                       for r in results],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/monthly-trends unavailable: {e}")
        return {"trends": [], "timestamp": datetime.utcnow().isoformat()}


@router.get("/recent-events")
@router.get("/events/live")
def get_recent_events(limit: int = Query(20, ge=5, le=100)):
    """
    Live conflict feed: GDELT BigQuery (`gdelt_events`) plus optional pipeline (`events`).
    UCDP remains on map/overview; this endpoint is real-time GDELT only.
    """
    try:
        _lazy_ensure_schema()
        client = get_ch_client()

        live = _fetch_live_gdelt_events(client, limit)
        pipeline = _fetch_pipeline_gdelt_events(client, limit)

        seen = set()
        merged = []
        for ev in live + pipeline:
            key = (ev.get("date"), ev.get("type"), ev.get("location"), ev.get("source_url"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(ev)

        merged.sort(key=lambda e: e.get("date") or "", reverse=True)
        events = merged[:limit]

        return {
            "events": events,
            "sources": {
                "gdelt_live": len(live),
                "gdelt_pipeline": len(pipeline),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.warning(f"conflict/recent-events unavailable: {e}")
        return {"events": [], "timestamp": datetime.utcnow().isoformat()}


@router.get("/regional-breakdown")
def get_regional_breakdown():
    try:
        client = get_ch_client()
        results = client.query(f"""
            SELECT region, COUNT(*) as events, SUM(deaths_total) as fatalities,
                   COUNT(DISTINCT type_of_violence) as event_types, MAX(date_start) as last_event
            FROM ucdp_events 
            WHERE region != '' AND {UCDP_FILTER}
            GROUP BY region ORDER BY events DESC
        """).result_rows
        total_events = sum(r[1] for r in results)
        return {
            "regions": [{"name": r[0], "events": r[1], "fatalities": r[2],
                         "event_types": r[3], "last_event": str(r[4]),
                         "percentage": round((r[1] / total_events) * 100, 1) if total_events > 0 else 0,
                         "risk_score": min(round((r[1] / 50) * 100, 1), 100)}
                        for r in results],
            "total_regions": len(results),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning(f"conflict/regional-breakdown unavailable: {e}")
        return {"regions": [], "total_regions": 0, "timestamp": datetime.utcnow().isoformat()}


@router.get("/clear-stale-events")
def clear_stale_events():
    """Reset events that were incorrectly auto-verified (AI skipped or AI format errors).
    Safe to call multiple times — idempotent mutation."""
    try:
        client = get_ch_client()
        # Reset events with bad AI summaries back to pending for re-verification
        client.command("""
            ALTER TABLE events 
            UPDATE is_verified = 0, 
                   ai_summary = '', 
                   source_system = 'gdelt_pending'
            WHERE ai_summary LIKE 'AI skipped%'
               OR ai_summary LIKE 'AI Format Error%'
        """)
        return {"status": "success", "message": "Triggered mutation to reset stale AI-skipped and AI-error events to pending state."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/map")
def get_conflict_map(limit: int = Query(200, ge=10, le=1000)):
    """Geographic map points for the conflict dashboard map."""
    try:
        client = get_ch_client()
        # Use unified events table (UCDP + GDELT)
        results = client.query(f"""
            SELECT lat, lon, location, fatalities, event_date,
                   region, source_system, actor1, event_type
            FROM events
            WHERE lat != 0 AND lon != 0
              AND lat BETWEEN 3.0 AND 15.5
              AND lon BETWEEN 33.0 AND 48.0
            ORDER BY event_date DESC
            LIMIT {limit}
        """).result_rows
        points = [
            {
                "lat": float(r[0]), "lon": float(r[1]),
                "name": r[2] or r[8] or "Unknown",
                "fatalities": int(r[3] or 0),
                "date": str(r[4]),
                "region": r[5] or "Ethiopia",
                "source": r[6] or "ucdp",
                "actor": r[7] or "",
                "intensity": "CRITICAL" if (r[3] or 0) > 50 else "HIGH" if (r[3] or 0) > 10 else "MODERATE"
            }
            for r in results
        ]
        if not points:
            # Fallback without geographic boundaries
            results2 = client.query(f"""
                SELECT lat, lon, location, fatalities, event_date,
                       region, source_system, actor1, event_type
                FROM events
                WHERE lat != 0 AND lon != 0
                ORDER BY event_date DESC
                LIMIT {limit}
            """).result_rows
            points = [
                {
                    "lat": float(r[0]), "lon": float(r[1]),
                    "name": r[2] or r[8] or "Unknown",
                    "fatalities": int(r[3] or 0),
                    "date": str(r[4]),
                    "region": r[5] or "Ethiopia",
                    "source": r[6] or "ucdp",
                    "actor": r[7] or "",
                    "intensity": "CRITICAL" if (r[3] or 0) > 50 else "HIGH" if (r[3] or 0) > 10 else "MODERATE"
                }
                for r in results2
            ]
        return {"points": points, "total": len(points), "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning(f"conflict/map unavailable: {e}")
        return {"points": [], "total": 0, "timestamp": datetime.utcnow().isoformat()}
