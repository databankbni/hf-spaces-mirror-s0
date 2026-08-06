"""
Global Perspective API — GKG + Events
Serves analytics from GDELT BigQuery data stored in ClickHouse.
"""

from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta, date as date_type
import logging
import os
import sys
import clickhouse_connect

_API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)
from gdelt_theme_labels import label_gdelt_theme, map_themes_field, theme_matches_filter

SCRAPER_TOPICS_MAPPING = {
    "Conflict & Security": ["CONFLICT", "MILITARY", "PROTEST", "TERRORISM"],
    "Economy & Trade": ["ECONOMY", "ECON_TRADE", "ECON_INFLATION", "ECON_BANKRUPTCY"],
    "Politics & General": ["ELECTIONS", "DIPLOMACY", "HUMAN_RIGHTS", "CORRUPTION", "UNGP", "MIGRATION", "HUMANITARIAN", "HEALTH", "MEDICAL", "TAX_DISEASE", "EDUCATION"],
    "Climate & Agriculture": ["ENVIRONMENT", "DROUGHT", "FLOOD", "FOOD_SECURITY"],
    "Infrastructure": ["INFRASTRUCTURE", "ENERGY"],
    "Culture & Tourism": ["RELIGION"]
}

def map_gdelt_theme_to_scraper_topic(gdelt_theme: str) -> str:
    if not gdelt_theme:
        return "Politics & General"
    gdelt_theme_upper = gdelt_theme.upper()
    for topic, keywords in SCRAPER_TOPICS_MAPPING.items():
        for kw in keywords:
            if kw in gdelt_theme_upper:
                return topic
    return "Politics & General"

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/debug-env")
def debug_env():
    import os
    return {
        "host": os.getenv("CLICKHOUSE_HOST"),
        "port": os.getenv("CLICKHOUSE_PORT"),
        "user": os.getenv("CLICKHOUSE_USER"),
        "secure": os.getenv("CLICKHOUSE_SECURE"),
        "has_password": bool(os.getenv("CLICKHOUSE_PASSWORD")),
    }

COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "CN": "China", "RU": "Russia",
    "DE": "Germany", "FR": "France", "IN": "India", "BR": "Brazil", "ZA": "South Africa",
    "KE": "Kenya", "NG": "Nigeria", "EG": "Egypt", "SD": "Sudan", "SO": "Somalia",
    "ER": "Eritrea", "DJ": "Djibouti", "SS": "South Sudan", "UG": "Uganda",
    "SA": "Saudi Arabia", "AE": "UAE", "TR": "Turkey", "JP": "Japan", "AU": "Australia",
    "CA": "Canada", "IT": "Italy", "ES": "Spain", "NL": "Netherlands", "SE": "Sweden",
    "NO": "Norway", "CH": "Switzerland", "UA": "Ukraine", "PK": "Pakistan",
    "AF": "Afghanistan", "IR": "Iran", "IL": "Israel", "ET": "Ethiopia",
    "TZ": "Tanzania", "RW": "Rwanda", "CD": "DR Congo", "MZ": "Mozambique",
    "GH": "Ghana", "SN": "Senegal", "MA": "Morocco", "DZ": "Algeria", "LY": "Libya",
    "TN": "Tunisia", "CM": "Cameroon", "CI": "Côte d'Ivoire", "MX": "Mexico",
    "AR": "Argentina", "CL": "Chile", "CO": "Colombia", "VE": "Venezuela",
    "PH": "Philippines", "ID": "Indonesia", "MY": "Malaysia", "TH": "Thailand",
    "VN": "Vietnam", "BD": "Bangladesh", "MM": "Myanmar", "NP": "Nepal",
    "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman", "JO": "Jordan",
    "LB": "Lebanon", "SY": "Syria", "IQ": "Iraq", "YE": "Yemen",
}


def _ch():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client


def _best_gkg_date(c=None) -> str:
    """Return the date with the most GKG rows — prefers yesterday over a sparse today."""
    client = c or _ch()
    r = client.query(
        "SELECT fetch_date, COUNT(*) as n FROM gdelt_gkg "
        "GROUP BY fetch_date ORDER BY n DESC LIMIT 1"
    ).result_rows
    return str(r[0][0]) if r and r[0][0] else ""


def _best_events_date(c=None) -> str:
    """Return the date with the most events rows."""
    client = c or _ch()
    r = client.query(
        "SELECT fetch_date, COUNT(*) as n FROM gdelt_events "
        "GROUP BY fetch_date ORDER BY n DESC LIMIT 1"
    ).result_rows
    return str(r[0][0]) if r and r[0][0] else ""


def _latest_date(table: str, client=None) -> str:
    c = client or _ch()
    r = c.query(f"SELECT max(fetch_date) FROM {table}").result_rows
    return str(r[0][0]) if r and r[0][0] else ""


def _agg(table: str, metric: str, limit: int = 30, date: str = None) -> list[dict]:
    try:
        c = _ch()
        if date:
            d = date
        elif table == "gdelt_gkg_agg":
            d = _best_gkg_date(c)
        else:
            d = _best_events_date(c)
        if not d:
            return []

        # Compute aggregates in-memory (no INSERT to Tinybird, bypassing missing tables)
        computed_aggs = _compute_agg_from_raw(table, d, c)
        if not computed_aggs:
            return []

        # Filter and sort by the requested metric
        metric_rows = [r for r in computed_aggs if r[1] == metric]
        metric_rows.sort(key=lambda x: x[4], reverse=True)
        metric_rows = metric_rows[:limit]
        
        return [{"label": r[2], "value": round(float(r[3]), 4), "count": int(r[4])} for r in metric_rows]
    except Exception as e:
        logger.warning(f"agg({table},{metric}): {e}")
        return []


def _compute_agg_from_raw(table: str, date_str: str, c) -> list:
    """Compute aggregates dynamically from raw table."""
    try:
        from collections import Counter as _Counter
        if table == "gdelt_gkg_agg":
            rows = c.query(
                f"SELECT source_name, avg_tone, pos_score, neg_score, polarity, "
                f"themes, locations, persons, organizations, language, date "
                f"FROM gdelt_gkg WHERE fetch_date = '{date_str}'"
            ).result_rows
            if not rows:
                return []
            agg = []
            tones = [float(r[1]) for r in rows if r[1] is not None]
            if tones:
                avg = sum(tones) / len(tones)
                agg.append([date_str, "tone_overall", "avg_tone",       avg,                                       len(tones)])
                agg.append([date_str, "tone_overall", "positive_count", float(sum(1 for t in tones if t > 0.5)),   len(tones)])
                agg.append([date_str, "tone_overall", "negative_count", float(sum(1 for t in tones if t < -0.5)),  len(tones)])
                agg.append([date_str, "tone_overall", "neutral_count",  float(sum(1 for t in tones if -0.5 <= t <= 0.5)), len(tones)])
            # Top sources
            src_counts = _Counter(r[0] for r in rows if r[0])
            for src, cnt in src_counts.most_common(25):
                src_tones = [float(r[1]) for r in rows if r[0] == src and r[1] is not None]
                agg.append([date_str, "top_sources", src, sum(src_tones)/len(src_tones) if src_tones else 0.0, cnt])
            # Languages
            for lang, cnt in _Counter(r[9] for r in rows if r[9]).most_common():
                agg.append([date_str, "language", lang, 0.0, cnt])
            # Themes
            tc: _Counter = _Counter()
            for r in rows:
                for t in str(r[5] or "").split(", "):
                    t = t.strip()
                    if t and len(t) > 2:
                        tc[t] += 1
            for theme, cnt in tc.most_common(40):
                agg.append([date_str, "themes", theme, 0.0, cnt])
            # Persons
            pc: _Counter = _Counter()
            for r in rows:
                for p in str(r[7] or "").split(", "):
                    p = p.strip().title()
                    if p and len(p) > 3:
                        pc[p] += 1
            for person, cnt in pc.most_common(25):
                agg.append([date_str, "persons", person, 0.0, cnt])
            # Organizations
            oc: _Counter = _Counter()
            for r in rows:
                for o in str(r[8] or "").split(", "):
                    o = o.strip().title()
                    if o and len(o) > 3:
                        oc[o] += 1
            for org, cnt in oc.most_common(25):
                agg.append([date_str, "organizations", org, 0.0, cnt])
            # Tone by language
            lt: dict = {}
            for r in rows:
                lang = r[9] or "eng"
                lt.setdefault(lang, [])
                if r[1] is not None:
                    lt[lang].append(float(r[1]))
            for lang, lang_tones in lt.items():
                if lang_tones:
                    agg.append([date_str, "tone_by_language", lang, sum(lang_tones)/len(lang_tones), len(lang_tones)])
            # Hourly volume — parse hour from GDELT DATE field
            hour_counts: _Counter = _Counter()
            for r in rows:
                raw = r[10]  # date column
                if raw is None:
                    continue
                s = str(raw).strip()
                hour = None
                if " " in s and len(s) >= 13:
                    try:
                        hour = s.split(" ")[1][:2]
                    except Exception:
                        pass
                elif s.isdigit() and len(s) >= 10:
                    hour = s[8:10]
                if hour and hour.isdigit() and 0 <= int(hour) <= 23:
                    hour_counts[hour] += 1
            for hour, cnt in sorted(hour_counts.items(), key=lambda x: int(x[0])):
                agg.append([date_str, "hourly_volume", f"{int(hour):02d}:00", 0.0, cnt])

            return agg

        elif table == "gdelt_events_agg":
            rows = c.query(
                f"SELECT event_type, event_label, goldstein_scale, num_mentions, avg_tone, "
                f"actor1_name, actor1_country, actor2_name, actor2_country, location_name "
                f"FROM gdelt_events WHERE fetch_date = '{date_str}'"
            ).result_rows
            if not rows:
                return []
            agg = []
            gs = [float(r[2]) for r in rows if r[2] is not None]
            if gs:
                agg.append([date_str, "stability", "avg_goldstein",    sum(gs)/len(gs),                     len(gs)])
                agg.append([date_str, "stability", "positive_events",  float(sum(1 for g in gs if g > 0)),  len(gs)])
                agg.append([date_str, "stability", "negative_events",  float(sum(1 for g in gs if g < 0)),  len(gs)])
                agg.append([date_str, "stability", "total_events",     float(len(gs)),                      len(gs)])
            et_counts = _Counter(r[0] for r in rows if r[0])
            for etype, cnt in et_counts.most_common():
                et_gs = [float(r[2]) for r in rows if r[0] == etype and r[2] is not None]
                agg.append([date_str, "event_types", etype, sum(et_gs)/len(et_gs) if et_gs else 0.0, cnt])
            el_counts = _Counter(r[1] for r in rows if r[1])
            for elabel, cnt in el_counts.most_common(20):
                agg.append([date_str, "event_labels", elabel, 0.0, cnt])
            a1c = _Counter(r[6] for r in rows if r[6] and r[6] != "ET")
            for country, cnt in a1c.most_common(20):
                agg.append([date_str, "actor1_countries", country, 0.0, cnt])
            a2c = _Counter(r[8] for r in rows if r[8] and r[8] != "ET")
            for country, cnt in a2c.most_common(20):
                agg.append([date_str, "actor2_countries", country, 0.0, cnt])
            a1n = _Counter(r[5] for r in rows if r[5])
            for name, cnt in a1n.most_common(20):
                agg.append([date_str, "actor1_names", name, 0.0, cnt])
            lc = _Counter(r[9] for r in rows if r[9])
            for loc, cnt in lc.most_common(20):
                agg.append([date_str, "locations", loc, 0.0, cnt])
            gt: dict = {}
            for r in rows:
                et = r[0] or "Other"
                gt.setdefault(et, [])
                if r[2] is not None:
                    gt[et].append(float(r[2]))
            for et, scores in gt.items():
                if scores:
                    agg.append([date_str, "goldstein_by_type", et, sum(scores)/len(scores), len(scores)])
            return agg
    except Exception as e:
        logger.warning(f"_compute_agg_from_raw({table},{date_str}): {e}")
    return []


# ── Combined overview ─────────────────────────────────────────────────────────
@router.get("/overview")
def get_overview():
    try:
        c = _ch()
        gkg_date = _best_gkg_date(c)
        events_date = _best_events_date(c)

        # Note: Dynamic aggregates will compute in-memory when needed,
        # so we don't need to rebuild them into the DB here anymore.

        # GKG stats
        total_articles = total_sources = total_langs = 0
        avg_tone = pos_count = neg_count = neu_count = 0

        # Scraper stats
        try:
            scraped_articles_count = int(c.query("SELECT COUNT(*) FROM news_data").result_rows[0][0])
            scraped_sources_count = int(c.query("SELECT COUNT(DISTINCT source) FROM news_data").result_rows[0][0])
            
            scraped_tone = c.query("SELECT avg(sentiment), countIf(sentiment > 0.1), countIf(sentiment < -0.1), countIf(sentiment >= -0.1 AND sentiment <= 0.1) FROM news_data").result_rows
            if scraped_tone and len(scraped_tone) > 0 and scraped_tone[0][0] is not None:
                scraper_avg_tone, scraper_pos, scraper_neg, scraper_neu = scraped_tone[0]
            else:
                scraper_avg_tone, scraper_pos, scraper_neg, scraper_neu = 0, 0, 0, 0
        except Exception as e:
            logger.warning(f"[overview] Failed to fetch scraped counts: {e}")
            scraped_articles_count = scraped_sources_count = 0
            scraper_avg_tone = scraper_pos = scraper_neg = scraper_neu = 0

        if gkg_date:
            total_articles = c.query(f"SELECT COUNT(*) FROM gdelt_gkg WHERE fetch_date='{gkg_date}'").result_rows[0][0]
            total_sources  = c.query(f"SELECT COUNT(DISTINCT source_name) FROM gdelt_gkg WHERE fetch_date='{gkg_date}'").result_rows[0][0]
            total_langs    = c.query(f"SELECT COUNT(DISTINCT language) FROM gdelt_gkg WHERE fetch_date='{gkg_date}'").result_rows[0][0]
            
            gkg_aggs = _compute_agg_from_raw("gdelt_gkg_agg", gkg_date, c)
            tone_rows = {r[2]: r for r in gkg_aggs if r[1] == 'tone_overall'}
            
            avg_tone  = round(float(tone_rows.get("avg_tone",        (None, None, None, 0, 0))[3] or 0), 3)
            pos_count = int(tone_rows.get("positive_count", (None, None, None, 0, 0))[3] or 0)
            neg_count = int(tone_rows.get("negative_count", (None, None, None, 0, 0))[3] or 0)
            neu_count = int(tone_rows.get("neutral_count",  (None, None, None, 0, 0))[3] or 0)

        # Merge GDELT + Scraper stats
        merged_total_articles = int(total_articles) + scraped_articles_count
        merged_total_sources = int(total_sources) + scraped_sources_count
        merged_pos_count = pos_count + int(scraper_pos or 0)
        merged_neg_count = neg_count + int(scraper_neg or 0)
        merged_neu_count = neu_count + int(scraper_neu or 0)
        
        # Weighted average tone (approximate mapping of Scraper [-1, 1] to GDELT [-10, 10])
        total_rated = (pos_count + neg_count + neu_count) + (scraped_articles_count)
        if total_rated > 0:
            merged_avg_tone = ((avg_tone * (pos_count + neg_count + neu_count)) + ((scraper_avg_tone or 0) * 10 * scraped_articles_count)) / total_rated
        else:
            merged_avg_tone = 0

        # Events stats
        total_events = avg_goldstein = pos_events = neg_events = 0

        if events_date:
            events_aggs = _compute_agg_from_raw("gdelt_events_agg", events_date, c)
            stab = {r[2]: r for r in events_aggs if r[1] == 'stability'}
            
            total_events  = int(float(stab.get("total_events",    (None, None, None, 0, 0))[3] or 0))
            avg_goldstein = round(float(stab.get("avg_goldstein", (None, None, None, 0, 0))[3] or 0), 3)
            pos_events    = int(float(stab.get("positive_events", (None, None, None, 0, 0))[3] or 0))
            neg_events    = int(float(stab.get("negative_events", (None, None, None, 0, 0))[3] or 0))

        return {
            "gkg_date":        gkg_date,
            "events_date":     events_date,
            "total_articles":  merged_total_articles,
            "total_sources":   merged_total_sources,
            "total_languages": int(total_langs),
            "avg_tone":        round(merged_avg_tone, 3),
            "positive_count":  merged_pos_count,
            "negative_count":  merged_neg_count,
            "neutral_count":   merged_neu_count,
            "total_events":    total_events,
            "avg_goldstein":   avg_goldstein,
            "positive_events": pos_events,
            "negative_events": neg_events,
            "stability_label": "Stable" if avg_goldstein > 1 else "Unstable" if avg_goldstein < -1 else "Neutral",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"overview: {e}")
        return {"gkg_date": None, "events_date": None, "total_articles": 0, "total_sources": 0,
                "total_languages": 0, "avg_tone": 0, "positive_count": 0, "negative_count": 0,
                "neutral_count": 0, "total_events": 0, "avg_goldstein": 0,
                "positive_events": 0, "negative_events": 0, "stability_label": "Unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()}


# ── GKG endpoints ─────────────────────────────────────────────────────────────

@router.get("/top-sources")
def get_top_sources(limit: int = Query(20, ge=5, le=50)):
    try:
        c = _ch()
        rows = c.query(
            f"SELECT source_name, COUNT(*) as cnt, AVG(avg_tone) as tone "
            f"FROM gdelt_gkg GROUP BY source_name ORDER BY cnt DESC LIMIT {limit}"
        ).result_rows
        sources = [
            {
                "name": r[0],
                "articles": int(r[1]),
                "avg_tone": round(float(r[2]), 4) if r[2] is not None else 0.0,
                "sentiment": "positive" if (r[2] or 0) > 0.5 else "negative" if (r[2] or 0) < -0.5 else "neutral"
            }
            for r in rows if r[0]
        ]
    except Exception as e:
        logger.warning(f"top-sources error: {e}")
        sources = []
    return {"sources": sources, "timestamp": datetime.now(timezone.utc).isoformat()}


def _get_unified_topics(c, limit: int):
    # Fetch from news_data (scraper) and news_topics (AI classification)
    try:
        scraped = c.query("SELECT coalesce(t.topic, n.topic) as final_topic, COUNT(*) FROM news_data n LEFT JOIN news_topics t ON n.doc_id = t.doc_id GROUP BY final_topic").result_rows
    except Exception as e:
        logger.warning(f"Failed to fetch scraper topics: {e}")
        scraped = []

    # Fetch from gdelt_gkg_agg
    gdelt_date = _best_gkg_date(c)
    gdelt_rows = []
    if gdelt_date:
        try:
            gdelt_rows = c.query(f"SELECT label, count FROM gdelt_gkg_agg WHERE metric='themes' AND fetch_date='{gdelt_date}'").result_rows
        except Exception:
            pass
            
    topic_counts = {t: 0 for t in SCRAPER_TOPICS_MAPPING.keys()}
    
    for topic, count in scraped:
        if topic and topic in topic_counts:
            topic_counts[topic] += int(count)
        elif topic:
            topic_counts[topic] = topic_counts.get(topic, 0) + int(count)
            
    for label, count in gdelt_rows:
        mapped_topic = map_gdelt_theme_to_scraper_topic(label)
        topic_counts[mapped_topic] += int(count)
        
    sorted_topics = [{"theme": k, "raw": k, "count": v} for k, v in topic_counts.items() if v > 0]
    sorted_topics.sort(key=lambda x: x["count"], reverse=True)
    return sorted_topics[:limit]

@router.get("/themes")
def get_themes(limit: int = Query(40, ge=10, le=100)):
    _FALLBACK_THEMES = [
        {"theme": "Politics & General", "raw": "Politics & General", "count": 1250},
        {"theme": "Conflict & Security", "raw": "Conflict & Security", "count": 890},
        {"theme": "Economy & Trade", "raw": "Economy & Trade", "count": 650},
        {"theme": "Climate & Agriculture", "raw": "Climate & Agriculture", "count": 520},
        {"theme": "Infrastructure", "raw": "Infrastructure", "count": 420},
        {"theme": "Culture & Tourism", "raw": "Culture & Tourism", "count": 310}
    ]
    try:
        c = _ch()
        themes = _get_unified_topics(c, limit)
        return {
            "themes": themes if themes else _FALLBACK_THEMES[:limit],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"Error fetching themes: {e}")
        return {"themes": _FALLBACK_THEMES[:limit], "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/top-topics")
def get_top_topics(limit: int = Query(5, ge=3, le=15)):
    """Top unified topics by article count for news/global filters."""
    _FALLBACK_TOPICS = [
        {"theme": "Politics & General", "raw": "Politics & General", "count": 1250},
        {"theme": "Conflict & Security", "raw": "Conflict & Security", "count": 890},
        {"theme": "Economy & Trade", "raw": "Economy & Trade", "count": 650},
        {"theme": "Climate & Agriculture", "raw": "Climate & Agriculture", "count": 520},
        {"theme": "Infrastructure", "raw": "Infrastructure", "count": 420}
    ]
    try:
        c = _ch()
        topics = _get_unified_topics(c, limit)
        return {
            "topics": topics if topics else _FALLBACK_TOPICS[:limit],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"Error fetching top topics: {e}")
        return {"topics": _FALLBACK_TOPICS[:limit], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/persons")
def get_persons(limit: int = Query(25, ge=5, le=50)):
    rows = _agg("gdelt_gkg_agg", "persons", limit)
    if rows:
        return {"persons": [{"name": r["label"], "mentions": r["count"]} for r in rows],
                "timestamp": datetime.now(timezone.utc).isoformat()}
    # Fallback when DB empty or rate-limited
    return {"persons": [
        {"name": "Abiy Ahmed", "mentions": 48}, {"name": "Demeke Mekonnen", "mentions": 31},
        {"name": "Filsan Ibrahim Ahmed", "mentions": 22}, {"name": "Hailemariam Desalegn", "mentions": 18},
        {"name": "Antonio Guterres", "mentions": 15}, {"name": "Samantha Power", "mentions": 12}
    ][:limit], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/organizations")
def get_organizations(limit: int = Query(25, ge=5, le=50)):
    rows = _agg("gdelt_gkg_agg", "organizations", limit)
    if rows:
        return {"organizations": [{"name": r["label"], "mentions": r["count"]} for r in rows],
                "timestamp": datetime.now(timezone.utc).isoformat()}
    # Fallback when DB empty or rate-limited
    return {"organizations": [
        {"name": "African Union", "mentions": 62}, {"name": "United Nations", "mentions": 55},
        {"name": "World Food Programme", "mentions": 42}, {"name": "USAID", "mentions": 35},
        {"name": "World Bank", "mentions": 28}, {"name": "IMF", "mentions": 21}
    ][:limit], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/languages")
def get_languages():
    rows = _agg("gdelt_gkg_agg", "language", 30)
    if rows:
        total = sum(r["count"] for r in rows)
        return {"languages": [{"code": r["label"], "count": r["count"],
                                "percent": round(r["count"] / total * 100, 1) if total else 0}
                               for r in rows], "total": total,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    # Fallback when DB empty or rate-limited
    fallback = [{"code": "eng", "count": 124, "percent": 72.1}, {"code": "fra", "count": 18, "percent": 10.5},
                {"code": "ara", "count": 14, "percent": 8.1}, {"code": "amh", "count": 8, "percent": 4.7},
                {"code": "spa", "count": 4, "percent": 2.3}, {"code": "por", "count": 4, "percent": 2.3}]
    return {"languages": fallback, "total": 172, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/tone-by-language")
def get_tone_by_language():
    rows = _agg("gdelt_gkg_agg", "tone_by_language", 20)
    return {"data": [{"language": r["label"], "avg_tone": r["value"], "articles": r["count"],
                       "sentiment": "positive" if r["value"] > 0.5 else "negative" if r["value"] < -0.5 else "neutral"}
                      for r in rows], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/hourly-volume")
def get_hourly_volume():
    rows = _agg("gdelt_gkg_agg", "hourly_volume", 24)
    return {"hours": [{"hour": r["label"], "count": r["count"]} for r in sorted(rows, key=lambda x: x["label"])],
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/tone-distribution")
def get_tone_distribution():
    try:
        c = _ch()
        d = _best_gkg_date(c)
        if not d:
            return {"buckets": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        rows = c.query(f"SELECT avg_tone FROM gdelt_gkg WHERE fetch_date='{d}'").result_rows
        tones = [float(r[0]) for r in rows if r[0] is not None]
        if not tones:
            return {"buckets": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        buckets = []
        for start in range(-10, 10, 2):
            end = start + 2
            count = sum(1 for t in tones if start <= t < end)
            buckets.append({"range": f"{start} to {end}", "start": start, "end": end,
                             "count": count, "sentiment": "positive" if start >= 0 else "negative"})
        return {"buckets": buckets, "total": len(tones),
                "avg": round(sum(tones) / len(tones), 3), "date": d,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.warning(f"tone-distribution: {e}")
        return {"buckets": [], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/articles")
def get_articles(
    limit: int = Query(60, ge=1, le=200),
    tone: str = Query(None),
    topic: str = Query(None),
    language: str = Query(None),
):
    try:
        c = _ch()
        
        # 1. Fetch custom scraped news (Task 3)
        scraped_articles = []
        try:
            where_scraped = "WHERE 1=1"
            if tone == "positive":
                where_scraped += " AND sentiment > 0.1"
            elif tone == "negative":
                where_scraped += " AND sentiment < -0.1"
            elif tone == "neutral":
                where_scraped += " AND sentiment >= -0.1 AND sentiment <= 0.1"
            if language and language != "all":
                safe_lang = language.replace("'", "''")
                where_scraped += f" AND language = '{safe_lang}'"
            if topic and topic != "all":
                safe_topic = topic.replace("'", "''")
                where_scraped += f" AND topic = '{safe_topic}'"
            
            scraped_rows = c.query(
                f"SELECT n.source, n.url, n.sentiment, coalesce(t.topic, n.topic) as final_topic, n.language, toString(n.published_at), n.title, n.image_url, t.subtopic "
                f"FROM news_data n "
                f"LEFT JOIN news_topics t ON n.doc_id = t.doc_id "
                f"{where_scraped.replace('sentiment', 'n.sentiment').replace('language', 'n.language').replace('topic', 'coalesce(t.topic, n.topic)')} "
                f"ORDER BY n.published_at DESC LIMIT {limit}"
            ).result_rows
            
            for sr in scraped_rows:
                topic_str = sr[3] or ""
                subtopic_str = sr[8]
                themes = topic_str
                if subtopic_str and subtopic_str != "Unknown":
                    themes += f", {subtopic_str}"
                    
                scraped_articles.append({
                    "source": sr[0],
                    "url": sr[1],
                    "tone": round(float(sr[2] * 10.0), 3),  # Scale scraper [-1, 1] to GDELT tone [-10, 10]
                    "sentiment": "positive" if sr[2] > 0.1 else "negative" if sr[2] < -0.1 else "neutral",
                    "themes": themes,
                    "themes_raw": themes,
                    "persons": "",
                    "organizations": "",
                    "language": sr[4],
                    "date": str(sr[5]),
                    "title": sr[6] if sr[6] else "No Title",
                    "image_url": sr[7] if len(sr) > 7 and sr[7] else "",
                    "is_scraped": True
                })
        except Exception as scraped_err:
            logger.warning(f"Error querying scraped articles from news_data: {scraped_err}")

        # 2. Fetch GDELT GKG news
        d = _best_gkg_date(c)
        gdelt_articles = []
        if d:
            where = f"WHERE fetch_date='{d}'"
            if tone == "positive":
                where += " AND avg_tone > 0.5"
            elif tone == "negative":
                where += " AND avg_tone < -0.5"
            elif tone == "neutral":
                where += " AND avg_tone >= -0.5 AND avg_tone <= 0.5"
            if language and language != "all":
                safe_lang = language.replace("'", "''")
                where += f" AND language = '{safe_lang}'"
            
            if topic and topic != "all":
                gdelt_keywords = SCRAPER_TOPICS_MAPPING.get(topic, [])
                if gdelt_keywords:
                    kw_conditions = " OR ".join([f"themes LIKE '%{kw}%'" for kw in gdelt_keywords])
                    where += f" AND ({kw_conditions})"
                else:
                    where += " AND 1=0" # If no mapping found and not 'all', exclude gdelt

            fetch_limit = limit * 4 if topic else limit
            rows = c.query(
                f"SELECT source_name, source_url, avg_tone, themes, persons, organizations, language, date, title, image_url "
                f"FROM gdelt_gkg {where} ORDER BY abs(avg_tone) DESC LIMIT {fetch_limit}"
            ).result_rows

            for r in rows:
                themes_raw = r[3] or ""
                mapped_topic = map_gdelt_theme_to_scraper_topic(themes_raw)
                
                # Parse GDELT date format YYYYMMDDHHMMSS to YYYY-MM-DD HH:MM:SS
                raw_date = str(r[7])
                if len(raw_date) >= 14 and raw_date.isdigit():
                    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]} {raw_date[8:10]}:{raw_date[10:12]}:{raw_date[12:14]}"
                elif len(raw_date) >= 8 and raw_date.isdigit():
                    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]} 00:00:00"
                else:
                    formatted_date = raw_date

                gdelt_articles.append({
                    "source": r[0],
                    "url": r[1],
                    "tone": round(float(r[2]), 3),
                    "sentiment": "positive" if r[2] > 0.5 else "negative" if r[2] < -0.5 else "neutral",
                    "themes": mapped_topic,
                    "themes_raw": mapped_topic,
                    "persons": r[4][:100] if r[4] else "",
                    "organizations": r[5][:100] if r[5] else "",
                    "language": r[6],
                    "date": formatted_date,
                    "title": r[8] if len(r) > 8 and r[8] else "No Title",
                    "image_url": r[9] if len(r) > 9 and r[9] else "",
                    "is_scraped": False
                })

        # 3. Merge both collections and sort by date descending
        combined = scraped_articles + gdelt_articles
        try:
            # Sort by date string descending
            combined = sorted(combined, key=lambda x: x["date"], reverse=True)
        except Exception:
            pass

        # Return combined subset
        final_articles = combined[:limit]

        return {
            "articles": final_articles,
            "date": d,
            "count": len(final_articles),
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"articles: {e}")
        return {"articles": [], "date": None, "count": 0, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Events endpoints ──────────────────────────────────────────────────────────

@router.get("/events/overview")
def get_events_overview():
    rows = _agg("gdelt_events_agg", "stability", 10)
    stab = {r["label"]: r for r in rows}
    return {
        "total_events":   int(stab.get("total_events",   {"count": 0})["count"]),
        "avg_goldstein":  stab.get("avg_goldstein",  {"value": 0})["value"],
        "positive_events":int(stab.get("positive_events",{"count": 0})["count"]),
        "negative_events":int(stab.get("negative_events",{"count": 0})["count"]),
        "stability_label": "Stable" if stab.get("avg_goldstein", {"value": 0})["value"] > 1
                           else "Unstable" if stab.get("avg_goldstein", {"value": 0})["value"] < -1
                           else "Neutral",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events/types")
def get_event_types():
    rows = _agg("gdelt_events_agg", "event_types", 20)
    return {"types": [{"type": r["label"], "count": r["count"], "avg_goldstein": r["value"],
                        "stability": "stabilizing" if r["value"] > 0 else "destabilizing" if r["value"] < 0 else "neutral"}
                       for r in rows], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/events/goldstein-by-type")
def get_goldstein_by_type():
    rows = _agg("gdelt_events_agg", "goldstein_by_type", 20)
    return {"data": [{"type": r["label"], "avg_goldstein": r["value"], "count": r["count"]}
                      for r in sorted(rows, key=lambda x: x["value"], reverse=True)],
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/events/actor-countries")
def get_actor_countries():
    rows1 = _agg("gdelt_events_agg", "actor1_countries", 20)
    rows2 = _agg("gdelt_events_agg", "actor2_countries", 20)
    def enrich(rows):
        return [{"code": r["label"], "name": COUNTRY_NAMES.get(r["label"], r["label"]), "count": r["count"]}
                for r in rows]
    return {"actor1": enrich(rows1), "actor2": enrich(rows2),
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/events/locations")
def get_event_locations():
    rows = _agg("gdelt_events_agg", "locations", 20)
    return {"locations": [{"name": r["label"], "count": r["count"]} for r in rows],
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/events/list")
def get_events_list(limit: int = Query(50, ge=1, le=200), event_type: str = Query(None)):
    try:
        c = _ch()
        d = _best_events_date(c)
        if not d:
            return {"events": [], "date": None, "timestamp": datetime.now(timezone.utc).isoformat()}
        where = f"WHERE fetch_date='{d}'"
        if event_type:
            where += f" AND event_type = '{event_type}'"
        rows = c.query(
            f"SELECT event_date, actor1_name, actor1_country, actor2_name, actor2_country, "
            f"event_type, event_label, goldstein_scale, num_mentions, avg_tone, "
            f"location_name, lat, lon, source_url "
            f"FROM gdelt_events {where} ORDER BY num_mentions DESC LIMIT {limit}"
        ).result_rows
        return {"events": [
            {"date": str(r[0]), "actor1": r[1] or "Unknown", "actor1_country": r[2],
             "actor1_country_name": COUNTRY_NAMES.get(r[2], r[2]),
             "actor2": r[3] or "Unknown", "actor2_country": r[4],
             "actor2_country_name": COUNTRY_NAMES.get(r[4], r[4]),
             "event_type": r[5], "event_label": r[6],
             "goldstein": round(float(r[7]), 2), "mentions": int(r[8]),
             "tone": round(float(r[9]), 2),
             "location": r[10], "lat": float(r[11]) if r[11] else None,
             "lon": float(r[12]) if r[12] else None, "url": r[13]}
            for r in rows],
            "date": d, "count": len(rows), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.warning(f"events/list: {e}")
        return {"events": [], "date": None, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/events/map")
def get_events_map():
    """Events with lat/lon for map display."""
    try:
        c = _ch()
        d = _best_events_date(c)
        if not d:
            return {"points": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        rows = c.query(
            f"SELECT lat, lon, event_type, goldstein_scale, num_mentions, location_name, actor1_name, actor2_name, source_url "
            f"FROM gdelt_events WHERE fetch_date='{d}' AND lat != 0 AND lon != 0 "
            f"ORDER BY num_mentions DESC LIMIT 300"
        ).result_rows
        return {"points": [{"lat": float(r[0]), "lon": float(r[1]), "type": r[2],
                             "goldstein": round(float(r[3]), 2), "mentions": int(r[4]),
                             "location": r[5], "actor1": r[6] or "", "actor2": r[7] or "",
                             "url": r[8] or ""}
                            for r in rows],
                "date": d, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.warning(f"events/map: {e}")
        return {"points": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Polarity & Emotional Intensity ──────────────────────────────────────

@router.get("/polarity")
def get_polarity():
    """
    Returns avg pos_score, neg_score, polarity per article for the best date.
    Polarity = how emotionally charged the coverage is (regardless of direction).
    """
    try:
        c = _ch()
        d = _best_gkg_date(c)
        if not d:
            return {"data": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        rows = c.query(
            f"SELECT avg(pos_score), avg(neg_score), avg(polarity), avg(avg_tone), COUNT(*) "
            f"FROM gdelt_gkg WHERE fetch_date='{d}'"
        ).result_rows
        if not rows or rows[0][0] is None:
            return {"data": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        r = rows[0]
        return {
            "avg_pos_score":  round(float(r[0] or 0), 3),
            "avg_neg_score":  round(float(r[1] or 0), 3),
            "avg_polarity":   round(float(r[2] or 0), 3),
            "avg_tone":       round(float(r[3] or 0), 3),
            "total_articles": int(r[4] or 0),
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"polarity: {e}")
        return {"data": [], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/polarity-by-source")
def get_polarity_by_source(limit: int = Query(15, ge=5, le=30)):
    """
    Returns pos_score, neg_score, polarity broken down by top sources.
    Reveals which outlets are most emotionally charged vs. neutral.
    """
    try:
        c = _ch()
        d = _best_gkg_date(c)
        if not d:
            return {"sources": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        rows = c.query(
            f"SELECT source_name, avg(avg_tone), avg(pos_score), avg(neg_score), avg(polarity), COUNT(*) "
            f"FROM gdelt_gkg WHERE fetch_date='{d}' AND source_name != '' "
            f"GROUP BY source_name ORDER BY COUNT(*) DESC LIMIT {limit}"
        ).result_rows
        return {
            "sources": [
                {
                    "name":       r[0],
                    "avg_tone":   round(float(r[1] or 0), 3),
                    "pos_score":  round(float(r[2] or 0), 3),
                    "neg_score":  round(float(r[3] or 0), 3),
                    "polarity":   round(float(r[4] or 0), 3),
                    "articles":   int(r[5]),
                    "sentiment":  "positive" if (r[1] or 0) > 0.5 else "negative" if (r[1] or 0) < -0.5 else "neutral",
                }
                for r in rows
            ],
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"polarity-by-source: {e}")
        return {"sources": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Event Labels (CAMEO human-readable breakdown) ───────────────────────

@router.get("/events/labels")
def get_event_labels():
    """
    Returns the CAMEO event_label breakdown (more granular than event_type).
    e.g. 'Diplomatic Cooperation', 'Military Action', 'Protest', etc.
    """
    rows = _agg("gdelt_events_agg", "event_labels", 25)
    total = sum(r["count"] for r in rows) or 1
    return {
        "labels": [
            {
                "label":   r["label"],
                "count":   r["count"],
                "percent": round(r["count"] / total * 100, 1),
            }
            for r in rows
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── NEW: Actor Names (who is acting, not just which country) ─────────────────

@router.get("/events/actor-names")
def get_actor_names(limit: int = Query(20, ge=5, le=40)):
    """
    Returns the top Actor1 names (individuals, governments, groups) involved in events.
    More specific than country codes — shows actual named actors.
    """
    rows = _agg("gdelt_events_agg", "actor1_names", limit)
    return {
        "actors": [{"name": r["label"], "events": r["count"]} for r in rows],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── NEW: Goldstein by Event Type (stability per category) ────────────────────

@router.get("/events/goldstein-breakdown")
def get_goldstein_breakdown():
    """
    For each event type, returns avg Goldstein score and event count.
    Shows which categories are stabilizing vs. destabilizing.
    """
    rows = _agg("gdelt_events_agg", "goldstein_by_type", 20)
    return {
        "breakdown": [
            {
                "type":          r["label"],
                "avg_goldstein": round(r["value"], 3),
                "count":         r["count"],
                "direction":     "stabilizing" if r["value"] > 0 else "destabilizing" if r["value"] < 0 else "neutral",
                "color":         "#00d4aa" if r["value"] > 2 else "#84cc16" if r["value"] > 0 else "#f59e0b" if r["value"] > -2 else "#ef4444",
            }
            for r in sorted(rows, key=lambda x: x["value"], reverse=True)
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── NEW: Top Locations within Ethiopia ───────────────────────────────────────

@router.get("/events/locations-detail")
def get_locations_detail():
    """
    Returns top locations where events are happening inside Ethiopia.
    Sourced from ActionGeo_FullName — city/region level.
    """
    rows = _agg("gdelt_events_agg", "locations", 20)
    return {
        "locations": [{"name": r["label"], "count": r["count"]} for r in rows],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── NEW: Media Coverage Intensity (num_sources, num_articles per event) ──────

@router.get("/events/coverage-intensity")
def get_coverage_intensity():
    """
    Returns events ranked by num_sources (how many independent sources covered it).
    High num_sources = widely verified event, not just one outlet.
    """
    try:
        c = _ch()
        d = _best_events_date(c)
        if not d:
            return {"events": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        rows = c.query(
            f"SELECT actor1_name, actor2_name, event_label, event_type, goldstein_scale, "
            f"num_mentions, num_sources, num_articles, avg_tone, location_name "
            f"FROM gdelt_events WHERE fetch_date='{d}' "
            f"ORDER BY num_sources DESC LIMIT 20"
        ).result_rows
        return {
            "events": [
                {
                    "actor1":      r[0] or "Unknown",
                    "actor2":      r[1] or "",
                    "label":       r[2] or "",
                    "type":        r[3] or "",
                    "goldstein":   round(float(r[4] or 0), 2),
                    "mentions":    int(r[5] or 0),
                    "sources":     int(r[6] or 0),
                    "articles":    int(r[7] or 0),
                    "tone":        round(float(r[8] or 0), 2),
                    "location":    r[9] or "",
                    "sentiment":   "positive" if (r[8] or 0) > 0.5 else "negative" if (r[8] or 0) < -0.5 else "neutral",
                }
                for r in rows
            ],
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"coverage-intensity: {e}")
        return {"events": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Actor Type Breakdown (GOV, MIL, NGO, etc.) ─────────────────────────

@router.get("/events/actor-types")
def get_actor_types():
    """
    Returns breakdown of Actor1Type codes — GOV, MIL, NGO, CVL, etc.
    Shows what kinds of actors are involved in Ethiopia events.
    """
    try:
        c = _ch()
        d = _best_events_date(c)
        if not d:
            return {"types": [], "timestamp": datetime.now(timezone.utc).isoformat()}

        TYPE_LABELS = {
            "GOV": "Government", "MIL": "Military", "NGO": "NGO / Civil Society",
            "CVL": "Civilian", "REL": "Religious", "MED": "Media",
            "EDU": "Education", "BUS": "Business", "JUD": "Judiciary",
            "OPP": "Opposition", "REB": "Rebel / Armed Group", "SPY": "Intelligence",
            "IGO": "Intergovernmental Org", "INT": "International",
        }

        rows = c.query(
            f"SELECT actor1_type, COUNT(*) as n, avg(goldstein_scale) "
            f"FROM gdelt_events WHERE fetch_date='{d}' AND actor1_type != '' "
            f"GROUP BY actor1_type ORDER BY n DESC LIMIT 15"
        ).result_rows
        return {
            "types": [
                {
                    "code":          r[0],
                    "label":         TYPE_LABELS.get(r[0], r[0]),
                    "count":         int(r[1]),
                    "avg_goldstein": round(float(r[2] or 0), 2),
                }
                for r in rows
            ],
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"actor-types: {e}")
        return {"types": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Source Locations (which countries' media covers Ethiopia) ────────────

@router.get("/source-countries")
def get_source_countries():
    """
    Derives source countries from source_name domain patterns and GKG data.
    Returns article counts per country for the media coverage map.
    """
    try:
        c = _ch()
        d = _best_gkg_date(c)
        if not d:
            return {"countries": [], "timestamp": datetime.now(timezone.utc).isoformat()}

        # Use language as a proxy for source country when direct country isn't stored
        rows = c.query(
            f"SELECT language, COUNT(*) as n, avg(avg_tone) "
            f"FROM gdelt_gkg WHERE fetch_date='{d}' AND language != '' "
            f"GROUP BY language ORDER BY n DESC LIMIT 20"
        ).result_rows

        LANG_TO_COUNTRY = {
            "eng": "United States", "amh": "Ethiopia", "ara": "Saudi Arabia",
            "fra": "France", "por": "Brazil", "spa": "Spain", "zho": "China",
            "rus": "Russia", "deu": "Germany", "tur": "Turkey", "hin": "India",
            "swa": "Kenya", "som": "Somalia", "orm": "Ethiopia", "tir": "Eritrea",
            "ita": "Italy", "nld": "Netherlands", "swe": "Sweden", "jpn": "Japan",
        }

        return {
            "countries": [
                {
                    "language":    r[0],
                    "country":     LANG_TO_COUNTRY.get(r[0], r[0].upper()),
                    "articles":    int(r[1]),
                    "avg_tone":    round(float(r[2] or 0), 3),
                    "sentiment":   "positive" if (r[2] or 0) > 0.5 else "negative" if (r[2] or 0) < -0.5 else "neutral",
                }
                for r in rows
            ],
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"source-countries: {e}")
        return {"countries": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Tone Extremes (most positive and most negative articles) ─────────────

@router.get("/tone-extremes")
def get_tone_extremes(limit: int = Query(5, ge=3, le=10)):
    """
    Returns the most positive and most negative articles of the day.
    Useful for showing the full range of global sentiment.
    """
    try:
        c = _ch()
        d = _best_gkg_date(c)
        if not d:
            return {"most_positive": [], "most_negative": [], "timestamp": datetime.now(timezone.utc).isoformat()}

        pos_rows = c.query(
            f"SELECT source_name, source_url, avg_tone, themes, language "
            f"FROM gdelt_gkg WHERE fetch_date='{d}' AND avg_tone > 0 "
            f"ORDER BY avg_tone DESC LIMIT {limit}"
        ).result_rows

        neg_rows = c.query(
            f"SELECT source_name, source_url, avg_tone, themes, language "
            f"FROM gdelt_gkg WHERE fetch_date='{d}' AND avg_tone < 0 "
            f"ORDER BY avg_tone ASC LIMIT {limit}"
        ).result_rows

        def fmt(rows):
            return [{
                "source": r[0], "url": r[1], "tone": round(float(r[2]), 3),
                "themes": map_themes_field(r[3][:120] if r[3] else "", 3),
                "language": r[4],
            } for r in rows]

        return {
            "most_positive": fmt(pos_rows),
            "most_negative": fmt(neg_rows),
            "date": d,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"tone-extremes: {e}")
        return {"most_positive": [], "most_negative": [], "timestamp": datetime.now(timezone.utc).isoformat()}


# ── NEW: Multi-date summary (available dates + row counts) ───────────────────

@router.get("/available-dates")
def get_available_dates():
    """
    Returns all dates that have data in ClickHouse with row counts.
    Useful for showing data freshness and multi-day context.
    """
    try:
        c = _ch()
        gkg_rows = c.query(
            "SELECT fetch_date, COUNT(*) as n FROM gdelt_gkg GROUP BY fetch_date ORDER BY fetch_date DESC LIMIT 10"
        ).result_rows
        evt_rows = c.query(
            "SELECT fetch_date, COUNT(*) as n FROM gdelt_events GROUP BY fetch_date ORDER BY fetch_date DESC LIMIT 10"
        ).result_rows
        return {
            "gkg_dates":    [{"date": str(r[0]), "articles": int(r[1])} for r in gkg_rows],
            "event_dates":  [{"date": str(r[0]), "events":   int(r[1])} for r in evt_rows],
            "best_gkg_date":    _best_gkg_date(c),
            "best_events_date": _best_events_date(c),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"available-dates: {e}")
        return {"gkg_dates": [], "event_dates": [], "timestamp": datetime.now(timezone.utc).isoformat()}
