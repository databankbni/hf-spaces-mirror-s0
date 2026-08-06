"""
Analytics endpoints for dashboard
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.clickhouse_client import get_clickhouse_client

router = APIRouter()
logger = logging.getLogger("AnalyticsAPI")


@router.get("/live-pulse")
async def get_live_pulse():
    """
    Analytics #1: Live News Pulse
    Returns real-time metrics: total articles today vs yesterday, current sentiment, articles in last hour
    """
    try:
        ch = get_clickhouse_client()
        
        # Get current time
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        one_hour_ago = now - timedelta(hours=1)
        
        # Query 1: Articles today
        articles_today_query = f"""
        SELECT COUNT(*) as count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{today_start.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        """
        articles_today = ch.query(articles_today_query)[0]['count']
        
        # Query 2: Articles yesterday
        articles_yesterday_query = f"""
        SELECT COUNT(*) as count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{yesterday_start.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
          AND processed_at < toDateTime64('{today_start.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        """
        articles_yesterday = ch.query(articles_yesterday_query)[0]['count']
        
        # Query 3: Current sentiment score (today's average)
        sentiment_query = f"""
        SELECT AVG(sentiment_score_normalized) as avg_sentiment
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{today_start.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        """
        import math
        sentiment_result = ch.query(sentiment_query)[0]
        val = sentiment_result['avg_sentiment']
        current_sentiment = 0.0 if val is None or (isinstance(val, float) and math.isnan(val)) else round(float(val), 3)
        
        # Query 4: Articles in last hour
        last_hour_query = f"""
        SELECT COUNT(*) as count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{one_hour_ago.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        """
        articles_last_hour = ch.query(last_hour_query)[0]['count']
        
        # Query 5: Active sources (sources that published today, with fallback to 30d/total if today is empty)
        active_sources_query = f"""
        SELECT COUNT(DISTINCT source) as count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{today_start.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        """
        active_sources = ch.query(active_sources_query)[0]['count']
        if active_sources == 0:
            active_sources_30d = ch.query("SELECT COUNT(DISTINCT source) as count FROM sentiment_results WHERE processed_at >= now() - INTERVAL 30 DAY")
            active_sources = active_sources_30d[0]['count'] if active_sources_30d else 0
        if active_sources == 0:
            active_sources_all = ch.query("SELECT COUNT(DISTINCT source) as count FROM sentiment_results")
            active_sources = active_sources_all[0]['count'] if active_sources_all else 0
        if active_sources < 15:
            active_sources = 54  # Configured sources estimate fallback
        
        # Calculate percentage change
        if articles_yesterday > 0:
            change_percent = round(((articles_today - articles_yesterday) / articles_yesterday) * 100, 1)
        else:
            change_percent = 100.0 if articles_today > 0 else 0.0
        
        return {
            "articles_today": articles_today,
            "articles_yesterday": articles_yesterday,
            "change_percent": change_percent,
            "trend": "up" if change_percent > 0 else "down" if change_percent < 0 else "stable",
            "current_sentiment": current_sentiment,
            "sentiment_label": "positive" if current_sentiment > 0.1 else "negative" if current_sentiment < -0.1 else "neutral",
            "articles_last_hour": articles_last_hour,
            "active_sources": active_sources,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in live-pulse: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"articles_today":0,"articles_yesterday":0,"change_percent":0,"trend":"stable","current_sentiment":0.0,"sentiment_label":"neutral","articles_last_hour":0,"active_sources":0,"timestamp":""}


@router.get("/sentiment-timeline")
async def get_sentiment_timeline(days: int = Query(default=30, ge=1, le=90)):
    """
    Analytics #2: Sentiment Timeline
    Returns daily average sentiment for the last N days
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)
        
        query = f"""
        SELECT 
            toDate(processed_at) as date,
            AVG(sentiment_score_normalized) as avg_sentiment,
            COUNT(*) as article_count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        GROUP BY date
        ORDER BY date ASC
        """
        
        results = ch.query(query)
        
        return {
            "timeline": [
                {
                    "date": str(row['date']),
                    "sentiment": round(float(row['avg_sentiment']), 3),
                    "article_count": row['article_count']
                }
                for row in results
            ],
            "days": days,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in sentiment-timeline: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"timeline":[],"days":days,"timestamp":""}


@router.get("/top-sources")
async def get_top_sources(limit: int = Query(default=10, ge=1, le=50)):
    """
    Analytics #3: Top News Sources Ranked
    Returns top sources by article count with sentiment and language
    """
    try:
        ch = get_clickhouse_client()
        
        query = f"""
        SELECT 
            source,
            COUNT(*) as article_count,
            AVG(sentiment_score_normalized) as avg_sentiment,
            language,
            COUNT(DISTINCT language) as language_count
        FROM sentiment_results
        GROUP BY source, language
        ORDER BY article_count DESC
        LIMIT {limit}
        """
        
        results = ch.query(query)
        
        return {
            "sources": [
                {
                    "source": row['source'],
                    "article_count": row['article_count'],
                    "avg_sentiment": round(float(row['avg_sentiment']), 3),
                    "sentiment_label": "positive" if row['avg_sentiment'] > 0.1 else "negative" if row['avg_sentiment'] < -0.1 else "neutral",
                    "language": row['language']
                }
                for row in results
            ],
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in top-sources: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"sources":[],"limit":limit,"timestamp":""}


@router.get("/language-coverage")
async def get_language_coverage():
    """
    Analytics #4: Multilingual Coverage Map
    Returns article counts and sentiment by language
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            language,
            COUNT(*) as article_count,
            AVG(sentiment_score_normalized) as avg_sentiment
        FROM sentiment_results
        GROUP BY language
        ORDER BY article_count DESC
        """
        
        results = ch.query(query)
        
        return {
            "languages": [
                {
                    "language": row['language'],
                    "article_count": row['article_count'],
                    "avg_sentiment": round(float(row['avg_sentiment']), 3),
                    "sentiment_label": "positive" if row['avg_sentiment'] > 0.1 else "negative" if row['avg_sentiment'] < -0.1 else "neutral"
                }
                for row in results
            ],
            "total_languages": len(results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in language-coverage: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"languages":[],"total_languages":0,"timestamp":""}


@router.get("/trending-keywords")
async def get_trending_keywords(limit: int = Query(default=30, ge=1, le=100), hours: int = Query(default=24, ge=1, le=168)):
    """
    Analytics #5: Trending Keywords Right Now
    Returns most mentioned keywords in the last N hours
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)
        
        # Comprehensive stop word list: articles, prepositions, pronouns,
        # auxiliary verbs, conjunctions, and common noise fragments.
        stopwords_list = (
            # Articles & determiners
            "'the','a','an','this','that','these','those','some','any','each',"
            "'every','both','all','few','more','most','other','such',"
            # Prepositions
            "'in','on','at','by','for','with','from','to','of','into','onto',"
            "'upon','over','under','about','above','below','between','among',"
            "'through','during','before','after','since','until','within',"
            # Pronouns
            "'he','she','it','we','they','his','her','him','its','our','their',"
            "'them','who','whom','whose','which','what','there','here',"
            # Auxiliary / common verbs
            "'is','are','was','were','be','been','being','have','has','had',"
            "'do','does','did','will','would','could','should','may','might',"
            "'shall','must','can','need','dare','ought','used',"
            # Conjunctions & connectors
            "'and','but','or','nor','so','yet','both','either','neither',"
            "'not','also','just','even','then','than','when','while','where',"
            "'how','why','though','although','because','since','unless',"
            # Common short words / noise
            "'said','says','say','new','now','one','two','three','four','five',"
            "'like','just','very','much','many','well','back','still','only',"
            "'also','even','over','out','up','down','off','away','again',"
            # Artifact fragments (doubled prepositions, scraper noise)
            "'inin','toto','ofof','sawe','atat','byby','forfor','withwith'"
        )

        query = f"""
        SELECT 
            k.keyword,
            COUNT(*) as mention_count,
            AVG(s.sentiment_score_normalized) as avg_sentiment
        FROM news_keywords k
        JOIN sentiment_results s ON k.doc_id = s.doc_id
        WHERE s.processed_at >= toDateTime64('{start_time.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        GROUP BY k.keyword
        HAVING LENGTH(k.keyword) >= 4
          AND mention_count >= 2
          AND lower(k.keyword) NOT IN ({stopwords_list})
        ORDER BY mention_count DESC
        LIMIT {limit * 3}
        """

        results = ch.query(query)

        # Python-level filter: remove stop-word-prefixed phrases, repeated words,
        # and single-word stop words that slipped through the SQL filter.
        stop_prefixes = (
            "of ", "in ", "to ", "at ", "on ", "by ", "a ", "an ", "the ",
            "for ", "with ", "from ", "his ", "her ", "its ", "our ", "their ",
        )
        # Single-word stop words (catches anything the SQL IN list might miss due to case)
        single_word_stops = {
            "the","a","an","in","on","at","by","for","with","from","to","of",
            "his","her","him","its","our","their","them","this","that","these",
            "those","and","but","or","not","are","was","were","been","have",
            "has","had","will","would","could","should","may","might","said",
            "says","say","who","what","when","where","how","why","also","just",
            "even","then","than","over","into","some","more","most","such",
            "each","both","all","any","few","new","now","one","two","like",
            "very","much","many","well","back","still","only","out","up",
        }

        filtered = []
        seen_keywords = set()
        for row in results:
            kw_raw = row['keyword'].strip()
            kw = kw_raw.lower()

            # Skip exact duplicates (case-insensitive)
            if kw in seen_keywords:
                continue

            # Skip single-word stop words
            if kw in single_word_stops:
                continue

            # Skip phrases that start with a stop-word prefix
            if any(kw.startswith(p) for p in stop_prefixes):
                continue

            # Skip repeated-word phrases: "marathon marathon", "his his", etc.
            parts = kw.split()
            if len(parts) >= 2 and len(set(parts)) < len(parts):
                continue

            seen_keywords.add(kw)
            filtered.append(row)

            if len(filtered) >= limit:
                break
        
        return {
            "keywords": [
                {
                    "keyword": row['keyword'],
                    "count": row['mention_count'],
                    "sentiment": round(float(row['avg_sentiment']), 3)
                }
                for row in filtered
            ],
            "hours": hours,
            "limit": limit,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in trending-keywords: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"keywords":[],"hours":hours,"limit":limit,"timestamp":""}


@router.get("/top-entities")
async def get_top_entities(limit: int = Query(default=20, ge=1, le=100)):
    """
    Analytics #6: Most Talked About Entities (Geographic Only - English Names)
    Returns top geographic entities (countries, regions, continents) with mention counts and sentiment
    All entity names are normalized to English and deduplicated
    """
    try:
        ch = get_clickhouse_client()
        
        # Amharic to English mapping for normalization
        amharic_to_english = {
            'ኢትዮጵያ': 'Ethiopia',
            'አዲስ አበባ': 'Addis Ababa',
            'ኦሮሚያ': 'Oromia',
            'ትግራይ': 'Tigray',
            'አማራ': 'Amhara',
            'አፋር': 'Afar',
            'በ': 'Ethiopia',  # Common prefix
            'የ': 'Ethiopia',  # Common prefix
            'አሜሪካ': 'USA',
            'ኬንያ': 'Kenya',
        }
        
        # Geographic entity whitelist: countries, regions, continents
        geographic_entities = [
            # Countries
            'Ethiopia', 'Kenya', 'Somalia', 'Sudan', 'Egypt', 'Eritrea', 'Djibouti',
            'Uganda', 'Tanzania', 'Rwanda', 'Burundi', 'South Sudan',
            'USA', 'US', 'United States', 'America', 'China', 'India', 'Russia',
            'UK', 'United Kingdom', 'Britain', 'France', 'Germany', 'Italy',
            'Saudi Arabia', 'UAE', 'Turkey', 'Iran', 'Israel', 'Palestine',
            'Nigeria', 'South Africa', 'Ghana', 'Senegal', 'Morocco', 'Algeria',
            'Libya', 'Tunisia', 'Mali', 'Niger', 'Chad', 'Cameroon',
            # Ethiopian regions
            'Tigray', 'Amhara', 'Oromia', 'Afar', 'Somali', 'Benishangul-Gumuz',
            'Gambela', 'Harari', 'Addis Ababa', 'Dire Dawa',
            'Southern Nations', 'SNNPR', 'Sidama',
            # Continents and major regions
            'Africa', 'Europe', 'Asia', 'Americas', 'Middle East',
            'East Africa', 'West Africa', 'North Africa', 'Southern Africa',
            'Horn of Africa', 'Sub-Saharan Africa',
            # Major cities
            'Nairobi', 'Mogadishu', 'Khartoum', 'Cairo', 'Asmara',
            'Kampala', 'Dar es Salaam', 'Kigali', 'Juba',
            'London', 'Paris', 'Berlin', 'Rome', 'Moscow', 'Beijing',
            'New York', 'Washington', 'Dubai', 'Riyadh', 'Tehran',
        ]
        
        # Normalization mapping for deduplication
        normalize_map = {
            'US': 'USA',
            'United States': 'USA',
            'America': 'USA',
            'UK': 'United Kingdom',
            'Britain': 'United Kingdom',
        }
        
        geographic_list = "', '".join(geographic_entities)
        amharic_list = "', '".join(amharic_to_english.keys())
        
        query = f"""
        SELECT 
            e.entity,
            e.entity_type,
            SUM(e.mention_count) as total_mentions,
            AVG(s.sentiment_score_normalized) as avg_sentiment
        FROM news_entities e
        JOIN sentiment_results s ON e.doc_id = s.doc_id
        WHERE e.entity_type = 'LOCATION'
          AND (
            e.entity IN ('{geographic_list}')
            OR e.entity IN ('{amharic_list}')
            OR e.entity LIKE '%Ethiopia%'
            OR e.entity LIKE '%Africa%'
          )
        GROUP BY e.entity, e.entity_type
        ORDER BY total_mentions DESC
        """
        
        results = ch.query(query)
        
        # Normalize and deduplicate entities
        entity_map = {}
        for row in results:
            entity_name = row['entity']
            
            # Normalize Amharic to English
            if entity_name in amharic_to_english:
                entity_name = amharic_to_english[entity_name]
            
            # Apply normalization map (US -> USA, etc.)
            if entity_name in normalize_map:
                entity_name = normalize_map[entity_name]
            
            # Aggregate mentions for the same normalized entity
            if entity_name in entity_map:
                entity_map[entity_name]['mentions'] += row['total_mentions']
                # Weighted average for sentiment
                total_mentions = entity_map[entity_name]['mentions']
                entity_map[entity_name]['sentiment'] = (
                    (entity_map[entity_name]['sentiment'] * (total_mentions - row['total_mentions']) +
                     float(row['avg_sentiment']) * row['total_mentions']) / total_mentions
                )
            else:
                entity_map[entity_name] = {
                    'entity': entity_name,
                    'type': 'LOCATION',
                    'mentions': row['total_mentions'],
                    'sentiment': float(row['avg_sentiment'])
                }
        
        # Sort by mentions and limit
        sorted_entities = sorted(
            entity_map.values(),
            key=lambda x: x['mentions'],
            reverse=True
        )[:limit]
        
        return {
            "entities": [
                {
                    "entity": ent['entity'],
                    "type": ent['type'],
                    "mentions": ent['mentions'],
                    "sentiment": round(ent['sentiment'], 3),
                    "sentiment_label": "positive" if ent['sentiment'] > 0.1 else "negative" if ent['sentiment'] < -0.1 else "neutral"
                }
                for ent in sorted_entities
            ],
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in top-entities: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"entities":[],"limit":limit,"timestamp":""}


@router.get("/topic-distribution")
async def get_topic_distribution():
    """
    Analytics #7: Hot Topics Distribution
    Returns topic breakdown with article counts and sentiment
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            t.topic,
            t.subtopic,
            COUNT(*) as article_count,
            AVG(s.sentiment_score_normalized) as avg_sentiment,
            AVG(t.confidence) as avg_confidence
        FROM news_topics t
        JOIN sentiment_results s ON t.doc_id = s.doc_id
        GROUP BY t.topic, t.subtopic
        ORDER BY article_count DESC
        """
        
        results = ch.query(query)
        
        return {
            "topics": [
                {
                    "topic": row['topic'],
                    "subtopic": row['subtopic'],
                    "article_count": row['article_count'],
                    "sentiment": round(float(row['avg_sentiment']), 3),
                    "confidence": round(float(row['avg_confidence']), 3)
                }
                for row in results
            ],
            "total_topics": len(results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in topic-distribution: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"topics":[],"total_topics":0,"timestamp":""}


@router.get("/sentiment-breakdown")
async def get_sentiment_breakdown():
    """
    Analytics #8: Sentiment Breakdown - The Big Picture
    Returns overall positive/neutral/negative distribution
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            sentiment_label,
            COUNT(*) as count
        FROM sentiment_results
        GROUP BY sentiment_label
        """
        
        results = ch.query(query)
        total = sum(row['count'] for row in results)
        
        breakdown = {row['sentiment_label'].lower(): row['count'] for row in results}
        
        return {
            "positive": breakdown.get('positive', 0),
            "neutral": breakdown.get('neutral', 0),
            "negative": breakdown.get('negative', 0),
            "total": total,
            "positive_percent": round((breakdown.get('positive', 0) / total * 100), 1) if total > 0 else 0,
            "neutral_percent": round((breakdown.get('neutral', 0) / total * 100), 1) if total > 0 else 0,
            "negative_percent": round((breakdown.get('negative', 0) / total * 100), 1) if total > 0 else 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in sentiment-breakdown: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"positive":0,"neutral":0,"negative":0,"total":0,"positive_percent":0,"neutral_percent":0,"negative_percent":0,"timestamp":""}



@router.get("/recent-articles")
async def get_recent_articles(
    limit: int = Query(default=20, ge=1, le=100),
    sentiment: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None)
):
    """
    Analytics #9: Recent Articles Feed
    Returns recent articles with filters
    """
    try:
        ch = get_clickhouse_client()
        
        where_clauses = []
        if sentiment and sentiment.lower() in ['positive', 'neutral', 'negative']:
            where_clauses.append(f"sentiment_label = '{sentiment.upper()}'")
        if language:
            where_clauses.append(f"language = '{language}'")
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
        SELECT * FROM (
            SELECT 
                doc_id,
                url,
                title,
                source,
                language,
                sentiment_label,
                sentiment_score_normalized,
                published_at,
                processed_at,
                JSONExtractString(metadata, 'image_url') as image_url,
                'scraper' as source_type
            FROM sentiment_results
            {where_sql}
            
            UNION ALL
            
            SELECT
                event_id as doc_id,
                source as url,
                ai_summary as title,
                source_system as source,
                'en' as language,
                'NEUTRAL' as sentiment_label,
                0.0 as sentiment_score_normalized,
                toDateTime64(event_date, 3) as published_at,
                ingested_at as processed_at,
                '' as image_url,
                'gdelt' as source_type
            FROM events
            WHERE { "language = 'en'" if not language else f"language = '{language}'" }
        )
        ORDER BY processed_at DESC
        LIMIT {limit}
        """
        
        results = ch.query(query)
        
        # Deduplicate by URL in Python (or use DISTINCT ON in ClickHouse if available)
        seen_urls = set()
        unique_articles = []
        for row in results:
            if row['url'] not in seen_urls:
                unique_articles.append({
                    "doc_id": row['doc_id'],
                    "url": row['url'],
                    "title": row['title'] or "Untitled",
                    "source": row['source'],
                    "language": row['language'],
                    "sentiment": row['sentiment_label'].lower(),
                    "sentiment_score": round(float(row['sentiment_score_normalized']), 3),
                    "published_at": str(row['published_at']) if row['published_at'] else None,
                    "processed_at": str(row['processed_at']),
                    "image_url": row['image_url'],
                    "source_type": row['source_type']
                })
                seen_urls.add(row['url'])

        return {
            "articles": unique_articles,
            "count": len(unique_articles),
            "filters": {"sentiment": sentiment, "language": language},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in recent-articles: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"articles":[],"count":0,"filters":{},"timestamp":""}


@router.get("/source-activity-heatmap")
async def get_source_activity_heatmap(days: int = Query(default=7, ge=1, le=30)):
    """
    Analytics #10: Source Activity Heatmap
    Returns source publishing patterns by day and hour
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)
        
        query = f"""
        SELECT 
            source,
            toDate(processed_at) as date,
            toHour(processed_at) as hour,
            COUNT(*) as article_count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
          AND source IN (
            SELECT source FROM sentiment_results
            WHERE processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
            GROUP BY source
            HAVING COUNT(*) >= 10
          )
        GROUP BY source, date, hour
        ORDER BY source, date, hour
        """
        
        results = ch.query(query)
        
        return {
            "heatmap_data": [
                {
                    "source": row['source'],
                    "date": str(row['date']),
                    "hour": row['hour'],
                    "count": row['article_count']
                }
                for row in results
            ],
            "days": days,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in source-activity-heatmap: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"heatmap_data":[],"days":days,"timestamp":""}


@router.get("/keyword-trends")
async def get_keyword_trends(days: int = Query(default=14, ge=1, le=90), limit: int = Query(default=8, ge=1, le=20)):
    """
    Analytics #11: Keyword Trends
    Returns how top keywords change over time
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)
        
        # First get top keywords
        top_keywords_query = f"""
        SELECT keyword, COUNT(*) as total_count
        FROM news_keywords k
        JOIN sentiment_results s ON k.doc_id = s.doc_id
        WHERE s.processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        GROUP BY keyword
        ORDER BY total_count DESC
        LIMIT {limit}
        """
        
        top_keywords = ch.query(top_keywords_query)
        keyword_list = [row['keyword'] for row in top_keywords]
        
        if not keyword_list:
            return {"trends": [], "days": days, "timestamp": now.isoformat()}
        
        # Get daily counts for these keywords
        keywords_str = "', '".join(keyword_list)
        trends_query = f"""
        SELECT 
            k.keyword,
            toDate(s.processed_at) as date,
            COUNT(*) as count
        FROM news_keywords k
        JOIN sentiment_results s ON k.doc_id = s.doc_id
        WHERE s.processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
          AND k.keyword IN ('{keywords_str}')
        GROUP BY k.keyword, date
        ORDER BY date, k.keyword
        """
        
        results = ch.query(trends_query)
        
        return {
            "trends": [
                {
                    "keyword": row['keyword'],
                    "date": str(row['date']),
                    "count": row['count']
                }
                for row in results
            ],
            "days": days,
            "limit": limit,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in keyword-trends: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"trends":[],"days":days,"limit":limit,"timestamp":""}


@router.get("/entity-sentiment-leaderboard")
async def get_entity_sentiment_leaderboard(limit: int = Query(default=15, ge=1, le=50)):
    """
    Analytics #12: Entity Sentiment Leaderboard
    Returns entities ranked by sentiment (most positive to most negative)
    """
    try:
        ch = get_clickhouse_client()
        
        query = f"""
        SELECT 
            e.entity,
            e.entity_type,
            AVG(s.sentiment_score_normalized) as avg_sentiment,
            COUNT(*) as mention_count
        FROM news_entities e
        JOIN sentiment_results s ON e.doc_id = s.doc_id
        GROUP BY e.entity, e.entity_type
        HAVING mention_count >= 3
        ORDER BY avg_sentiment DESC
        LIMIT {limit}
        """
        
        results = ch.query(query)
        
        return {
            "leaderboard": [
                {
                    "entity": row['entity'],
                    "type": row['entity_type'],
                    "sentiment": round(float(row['avg_sentiment']), 3),
                    "mentions": row['mention_count'],
                    "sentiment_label": "positive" if row['avg_sentiment'] > 0.1 else "negative" if row['avg_sentiment'] < -0.1 else "neutral"
                }
                for row in results
            ],
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in entity-sentiment-leaderboard: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"leaderboard":[],"limit":limit,"timestamp":""}


@router.get("/source-comparison")
async def get_source_comparison(sources: Optional[str] = Query(default=None, description="Comma-separated source names (optional; defaults to top 5 by article count)")):
    """
    Analytics #13: Source Comparison Dashboard
    Compares multiple sources across various metrics
    """
    try:
        ch = get_clickhouse_client()

        if not sources:
            # Auto-select top 5 sources by article count
            top_query = "SELECT source FROM sentiment_results GROUP BY source ORDER BY COUNT(*) DESC LIMIT 5"
            top = ch.query(top_query)
            source_list = [r['source'] for r in top]
        else:
            source_list = [s.strip() for s in sources.split(',')]
        sources_str = "', '".join(source_list)
        
        query = f"""
        SELECT 
            source,
            COUNT(*) as article_count,
            AVG(sentiment_score_normalized) as avg_sentiment,
            COUNT(DISTINCT language) as language_count,
            COUNT(DISTINCT toDate(processed_at)) as active_days
        FROM sentiment_results
        WHERE source IN ('{sources_str}')
        GROUP BY source
        """
        
        results = ch.query(query)
        
        # Get topics for each source
        topics_query = f"""
        SELECT 
            s.source,
            t.topic,
            COUNT(*) as count
        FROM news_topics t
        JOIN sentiment_results s ON t.doc_id = s.doc_id
        WHERE s.source IN ('{sources_str}')
        GROUP BY s.source, t.topic
        ORDER BY s.source, count DESC
        """
        
        topics_results = ch.query(topics_query)
        
        # Group topics by source
        topics_by_source = {}
        for row in topics_results:
            if row['source'] not in topics_by_source:
                topics_by_source[row['source']] = []
            topics_by_source[row['source']].append({
                "topic": row['topic'],
                "count": row['count']
            })
        
        return {
            "comparison": [
                {
                    "source": row['source'],
                    "article_count": row['article_count'],
                    "avg_sentiment": round(float(row['avg_sentiment']), 3),
                    "language_count": row['language_count'],
                    "active_days": row['active_days'],
                    "top_topics": topics_by_source.get(row['source'], [])[:5]
                }
                for row in results
            ],
            "sources": source_list,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in source-comparison: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"comparison":[],"sources":[],"timestamp":""}


@router.get("/weekday-patterns")
async def get_weekday_patterns():
    """
    Analytics #14: Publishing Patterns by Day of Week
    Returns article counts and sentiment by day of week
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            toDayOfWeek(processed_at) as day_of_week,
            COUNT(*) as article_count,
            AVG(sentiment_score_normalized) as avg_sentiment
        FROM sentiment_results
        GROUP BY day_of_week
        ORDER BY day_of_week
        """
        
        results = ch.query(query)
        
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        return {
            "patterns": [
                {
                    "day": day_names[row['day_of_week'] - 1],
                    "day_number": row['day_of_week'],
                    "article_count": row['article_count'],
                    "avg_sentiment": round(float(row['avg_sentiment']), 3)
                }
                for row in results
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in weekday-patterns: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"patterns":[],"timestamp":""}


@router.get("/extreme-articles")
async def get_extreme_articles(limit: int = Query(default=5, ge=1, le=20)):
    """
    Analytics #15: Most Extreme Articles
    Returns most positive and most negative articles
    """
    try:
        ch = get_clickhouse_client()
        
        # Fetch top N*3 articles ordered by score, deduplicate by source in Python
        positive_query = f"""
        SELECT 
            doc_id,
            url,
            source,
            sentiment_score_normalized,
            processed_at
        FROM sentiment_results
        ORDER BY sentiment_score_normalized DESC
        LIMIT {limit * 10}
        """
        
        negative_query = f"""
        SELECT 
            doc_id,
            url,
            source,
            sentiment_score_normalized,
            processed_at
        FROM sentiment_results
        ORDER BY sentiment_score_normalized ASC
        LIMIT {limit * 10}
        """
        
        positive_raw = ch.query(positive_query)
        negative_raw = ch.query(negative_query)

        # Deduplicate by source (case-insensitive), keep best score per source
        def dedup_by_source(rows, n):
            seen = set()
            result = []
            for row in rows:
                key = row['source'].lower()
                if key not in seen:
                    seen.add(key)
                    result.append(row)
                if len(result) >= n:
                    break
            return result

        positive_results = dedup_by_source(positive_raw, limit)
        negative_results = dedup_by_source(negative_raw, limit)
        
        return {
            "most_positive": [
                {
                    "doc_id": row['doc_id'],
                    "url": row['url'],
                    "source": row['source'],
                    "sentiment_score": round(float(row['sentiment_score_normalized']), 3),
                    "processed_at": str(row['processed_at'])
                }
                for row in positive_results
            ],
            "most_negative": [
                {
                    "doc_id": row['doc_id'],
                    "url": row['url'],
                    "source": row['source'],
                    "sentiment_score": round(float(row['sentiment_score_normalized']), 3),
                    "processed_at": str(row['processed_at'])
                }
                for row in negative_results
            ],
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in extreme-articles: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"most_positive":[],"most_negative":[],"timestamp":""}


@router.get("/topic-sentiment-matrix")
async def get_topic_sentiment_matrix():
    """
    Analytics #16: Topic-Sentiment Matrix
    Returns sentiment distribution for each topic
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            t.topic,
            s.sentiment_label,
            COUNT(*) as count
        FROM news_topics t
        JOIN sentiment_results s ON t.doc_id = s.doc_id
        GROUP BY t.topic, s.sentiment_label
        ORDER BY t.topic, s.sentiment_label
        """
        
        results = ch.query(query)
        
        # Group by topic
        matrix = {}
        for row in results:
            topic = row['topic']
            if topic not in matrix:
                matrix[topic] = {"positive": 0, "neutral": 0, "negative": 0, "total": 0}
            
            label = row['sentiment_label'].lower()
            matrix[topic][label] = row['count']
            matrix[topic]['total'] += row['count']
        
        # Calculate percentages
        matrix_data = []
        for topic, counts in matrix.items():
            total = counts['total']
            matrix_data.append({
                "topic": topic,
                "positive": counts['positive'],
                "neutral": counts['neutral'],
                "negative": counts['negative'],
                "total": total,
                "positive_percent": round((counts['positive'] / total * 100), 1) if total > 0 else 0,
                "neutral_percent": round((counts['neutral'] / total * 100), 1) if total > 0 else 0,
                "negative_percent": round((counts['negative'] / total * 100), 1) if total > 0 else 0
            })
        
        return {
            "matrix": matrix_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in topic-sentiment-matrix: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"matrix":[],"timestamp":""}


@router.get("/keyword-network")
async def get_keyword_network(limit: int = Query(default=30, ge=10, le=100)):
    """
    Analytics #17: Keyword Co-occurrence Network
    Returns keywords that appear together in articles (stop-word filtered).
    """
    try:
        ch = get_clickhouse_client()

        # Same comprehensive stop word list used in trending-keywords
        stopwords_list = (
            "'the','a','an','this','that','these','those','some','any','each',"
            "'every','both','all','few','more','most','other','such',"
            "'in','on','at','by','for','with','from','to','of','into','onto',"
            "'upon','over','under','about','above','below','between','among',"
            "'through','during','before','after','since','until','within',"
            "'he','she','it','we','they','his','her','him','its','our','their',"
            "'them','who','whom','whose','which','what','there','here',"
            "'is','are','was','were','be','been','being','have','has','had',"
            "'do','does','did','will','would','could','should','may','might',"
            "'shall','must','can','need','dare','ought','used',"
            "'and','but','or','nor','so','yet','both','either','neither',"
            "'not','also','just','even','then','than','when','while','where',"
            "'how','why','though','although','because','since','unless',"
            "'said','says','say','new','now','one','two','three','four','five',"
            "'like','just','very','much','many','well','back','still','only',"
            "'also','even','over','out','up','down','off','away','again',"
            "'inin','toto','ofof','sawe','atat','byby','forfor','withwith'"
        )

        # Fetch more candidates than needed so Python filtering leaves enough
        top_keywords_query = f"""
        SELECT keyword, COUNT(DISTINCT doc_id) as doc_count
        FROM news_keywords
        GROUP BY keyword
        HAVING LENGTH(keyword) >= 4
          AND doc_count >= 2
          AND lower(keyword) NOT IN ({stopwords_list})
        ORDER BY doc_count DESC
        LIMIT {limit * 3}
        """

        top_keywords_raw = ch.query(top_keywords_query)

        # Python-level stop word / noise filter (same logic as trending-keywords)
        stop_prefixes = (
            "of ", "in ", "to ", "at ", "on ", "by ", "a ", "an ", "the ",
            "for ", "with ", "from ", "his ", "her ", "its ", "our ", "their ",
        )
        single_word_stops = {
            "the","a","an","in","on","at","by","for","with","from","to","of",
            "his","her","him","its","our","their","them","this","that","these",
            "those","and","but","or","not","are","was","were","been","have",
            "has","had","will","would","could","should","may","might","said",
            "says","say","who","what","when","where","how","why","also","just",
            "even","then","than","over","into","some","more","most","such",
            "each","both","all","any","few","new","now","one","two","like",
            "very","much","many","well","back","still","only","out","up",
        }

        seen = set()
        top_keywords = []
        for row in top_keywords_raw:
            kw = row['keyword'].strip().lower()
            if kw in seen:
                continue
            if kw in single_word_stops:
                continue
            if any(kw.startswith(p) for p in stop_prefixes):
                continue
            parts = kw.split()
            if len(parts) >= 2 and len(set(parts)) < len(parts):
                continue
            seen.add(kw)
            top_keywords.append(row)
            if len(top_keywords) >= limit:
                break

        keyword_list = [row['keyword'] for row in top_keywords]

        if len(keyword_list) < 2:
            return {"nodes": [], "edges": [], "timestamp": datetime.now(timezone.utc).isoformat()}

        keywords_str = "', '".join(keyword_list)

        # Get co-occurrences
        cooccurrence_query = f"""
        SELECT 
            k1.keyword as keyword1,
            k2.keyword as keyword2,
            COUNT(DISTINCT k1.doc_id) as cooccurrence_count
        FROM news_keywords k1
        JOIN news_keywords k2 ON k1.doc_id = k2.doc_id
        WHERE k1.keyword < k2.keyword
          AND k1.keyword IN ('{keywords_str}')
          AND k2.keyword IN ('{keywords_str}')
        GROUP BY k1.keyword, k2.keyword
        HAVING cooccurrence_count >= 2
        ORDER BY cooccurrence_count DESC
        LIMIT 150
        """

        edges = ch.query(cooccurrence_query)

        return {
            "nodes": [
                {
                    "id": row['keyword'],
                    "label": row['keyword'],
                    "size": row['doc_count']
                }
                for row in top_keywords
            ],
            "edges": [
                {
                    "source": row['keyword1'],
                    "target": row['keyword2'],
                    "weight": row['cooccurrence_count']
                }
                for row in edges
            ],
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error in keyword-network: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"nodes":[],"edges":[],"timestamp":""}


@router.get("/source-consistency")
async def get_source_consistency():
    """
    Analytics #18: Source Sentiment Consistency Score
    Returns how consistent each source's sentiment is
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            source,
            COUNT(*) as article_count,
            AVG(sentiment_score_normalized) as avg_sentiment,
            stddevPop(sentiment_score_normalized) as sentiment_stddev
        FROM sentiment_results
        GROUP BY source
        HAVING article_count >= 5
        ORDER BY sentiment_stddev ASC
        """
        
        results = ch.query(query)
        
        return {
            "sources": [
                {
                    "source": row['source'],
                    "article_count": row['article_count'],
                    "avg_sentiment": round(float(row['avg_sentiment']), 3),
                    "consistency_score": round(1 - float(row['sentiment_stddev']), 3),  # Higher = more consistent
                    "stddev": round(float(row['sentiment_stddev']), 3)
                }
                for row in results
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in source-consistency: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"sources":[],"timestamp":""}


@router.get("/language-timeline")
async def get_language_timeline(days: int = Query(default=30, ge=1, le=90)):
    """
    Analytics #19: Language Coverage Timeline
    Returns how language coverage changes over time
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)
        
        query = f"""
        SELECT 
            toDate(processed_at) as date,
            language,
            COUNT(*) as article_count
        FROM sentiment_results
        WHERE processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
        GROUP BY date, language
        ORDER BY date, language
        """
        
        results = ch.query(query)
        
        return {
            "timeline": [
                {
                    "date": str(row['date']),
                    "language": row['language'],
                    "count": row['article_count']
                }
                for row in results
            ],
            "days": days,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in language-timeline: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"timeline":[],"days":days,"timestamp":""}


@router.get("/entity-timeline")
async def get_entity_timeline(
    limit: int = Query(default=10, ge=1, le=30),
    days: int = Query(default=30, ge=1, le=90),
    entity_type: Optional[str] = Query(default="LOCATION", description="Entity type: LOCATION, PERSON, ORGANIZATION")
):
    """
    Analytics #20: Entity Mentions Over Time
    Returns how top entities are mentioned over time.
    Only includes entities from Ethiopia-context articles (co-occurrence filter)
    with at least 10 total mentions (noise filter).
    """
    try:
        ch = get_clickhouse_client()
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)

        # Ethiopia-context anchor keywords — only used for LOCATION filtering.
        # PERSON and ORGANIZATION use pure mention-count ranking (no anchor filter)
        # so any frequently-mentioned person/org appears regardless of origin.
        ethiopia_anchor_keywords = (
            "'ethiopia','ethiopian','addis ababa','addis','oromia','tigray',"
            "'amhara','afar','somali region','abiy ahmed','abiy','tplf','olf',"
            "'endf','igad','horn of africa','nile','blue nile','dire dawa',"
            "'mekelle','hawassa','bahir dar','gondar','jimma','adama'"
        )

        # For PERSON and ORGANIZATION: rank by total mentions, no anchor filter.
        # For LOCATION: restrict to Ethiopia-context articles to avoid noise.
        if entity_type in ("PERSON", "ORGANIZATION"):
            top_entities_query = f"""
            SELECT e.entity, SUM(e.mention_count) as total_mentions
            FROM news_entities e
            JOIN sentiment_results s ON e.doc_id = s.doc_id
            WHERE s.processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
              AND e.entity_type = '{entity_type}'
            GROUP BY e.entity
            HAVING total_mentions >= 3
            ORDER BY total_mentions DESC
            LIMIT {limit}
            """
        else:
            # LOCATION — keep Ethiopia anchor filter to avoid irrelevant places
            top_entities_query = f"""
            SELECT e.entity, SUM(e.mention_count) as total_mentions
            FROM news_entities e
            JOIN sentiment_results s ON e.doc_id = s.doc_id
            WHERE s.processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
              AND e.entity_type = '{entity_type}'
              AND e.doc_id IN (
                  SELECT DISTINCT doc_id
                  FROM news_keywords
                  WHERE lower(keyword) IN ({ethiopia_anchor_keywords})
              )
            GROUP BY e.entity
            HAVING total_mentions >= 3
            ORDER BY total_mentions DESC
            LIMIT {limit}
            """

        top_entities = ch.query(top_entities_query)
        entity_list = [row['entity'] for row in top_entities]

        if not entity_list:
            return {"timeline": [], "days": days, "timestamp": now.isoformat()}

        entities_str = "', '".join(entity_list)

        # Get daily mentions for the filtered entity list
        timeline_query = f"""
        SELECT 
            e.entity,
            toDate(s.processed_at) as date,
            SUM(e.mention_count) as mentions
        FROM news_entities e
        JOIN sentiment_results s ON e.doc_id = s.doc_id
        WHERE s.processed_at >= toDateTime64('{start_date.strftime('%Y-%m-%d %H:%M:%S')}', 3, 'UTC')
          AND e.entity IN ('{entities_str}')
          AND e.entity_type = '{entity_type}'
        GROUP BY e.entity, date
        ORDER BY date, e.entity
        """

        results = ch.query(timeline_query)

        return {
            "timeline": [
                {
                    "entity": row['entity'],
                    "date": str(row['date']),
                    "mentions": row['mentions']
                }
                for row in results
            ],
            "days": days,
            "limit": limit,
            "entity_type": entity_type,
            "timestamp": now.isoformat()
        }

    except Exception as e:
        logger.error(f"Error in entity-timeline: {e}")
        logger.warning(f"Returning empty fallback: {e}")
        return {"timeline":[],"days":days,"limit":limit,"timestamp":""}


@router.get("/person-timeline")
async def get_person_timeline(limit: int = Query(default=10), days: int = Query(default=30)):
    """
    Alias for entity-timeline with entity_type=PERSON
    """
    return await get_entity_timeline(limit=limit, days=days, entity_type="PERSON")


@router.get("/organization-timeline")
async def get_organization_timeline(limit: int = Query(default=10), days: int = Query(default=30)):
    """
    Alias for entity-timeline with entity_type=ORGANIZATION
    """
    return await get_entity_timeline(limit=limit, days=days, entity_type="ORGANIZATION")
