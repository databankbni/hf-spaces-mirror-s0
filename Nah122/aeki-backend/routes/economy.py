"""
Economy & Growth Intelligence API
Provides economic indicators and growth metrics for Ethiopia
"""

from fastapi import APIRouter, Query
from datetime import datetime
import clickhouse_connect
import os
import logging
from typing import List, Dict, Any

router = APIRouter()
logger = logging.getLogger(__name__)

# ClickHouse connection
def get_ch_client():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client


@router.get("/overview")
def get_economy_overview():
    """
    Economic overview with key metrics
    """
    try:
        client = get_ch_client()
        
        # Get latest values for key indicators
        indicators = {
            'NY.GDP.MKTP.KD.ZG': 'gdp_growth',
            'FP.CPI.TOTL.ZG': 'inflation',
            'SP.POP.TOTL': 'population',
            'NY.GNP.PCAP.CD': 'gni_per_capita',
            'NE.TRD.GNFS.ZS': 'trade_gdp',
            'BX.TRF.PWKR.DT.GD.ZS': 'remittances_gdp',
            'EG.ELC.ACCS.ZS': 'electricity_access',
            'SL.UEM.TOTL.ZS': 'unemployment'
        }
        
        overview = {}
        
        for code, key in indicators.items():
            query = f"""
                SELECT year, value
                FROM wb_indicators
                WHERE indicator_code = '{code}'
                AND value IS NOT NULL
                ORDER BY year DESC
                LIMIT 1
            """
            try:
                result = client.query(query).result_rows
                if result:
                    overview[key] = {
                        'value': round(result[0][1], 2),
                        'year': result[0][0]
                    }
            except Exception as e:
                logger.warning(f"Error fetching indicator {code}: {e}")
        
        # Get IMF Forecasts/Projections
        imf_forecasts = {}
        try:
            imf_query = """
                SELECT indicator_code, year, value
                FROM imf_projections
                WHERE year IN (2024, 2025, 2026)
                  AND indicator_code IN ('NGDP_RPCH', 'PCPIPCH')
            """
            imf_res = client.query(imf_query).result_rows
            for row in imf_res:
                code, year, value = row[0], int(row[1]), float(row[2])
                prefix = "gdp" if code == "NGDP_RPCH" else "inflation"
                imf_forecasts[f"{prefix}_{year}"] = round(value, 2)
        except Exception as e:
            logger.warning(f"Error fetching IMF projections: {e}")

        forecasts = {
            "gdp_2024": imf_forecasts.get("gdp_2024"),
            "gdp_2025": imf_forecasts.get("gdp_2025", 6.5),
            "gdp_2026": imf_forecasts.get("gdp_2026"),
            "inflation_2025": imf_forecasts.get("inflation_2025", 20.0),
            "inflation_2026": imf_forecasts.get("inflation_2026"),
        }
        # Backward compatibility
        forecasts["gdp_growth_next_year"] = forecasts["gdp_2025"]
        forecasts["inflation_next_year"] = forecasts["inflation_2025"]

        if not overview:
            # Fallback if DB is unavailable
            overview = {
                "gdp_growth": {"value": 7.2, "year": 2023},
                "inflation": {"value": 28.5, "year": 2023},
                "population": {"value": 126527060, "year": 2023},
            }

        return {
            "overview": overview,
            "forecasts": forecasts,
            "data_source": "World Bank & IMF Projections (Live/Fallback)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Critical error in get_economy_overview: {e}")
        return {
            "overview": {
                "gdp_growth": {"value": 7.2, "year": 2023},
                "inflation": {"value": 28.5, "year": 2023},
                "population": {"value": 126527060, "year": 2023},
            },
            "forecasts": {
                "gdp_2025": 6.5,
                "inflation_2025": 20.0,
                "gdp_growth_next_year": 6.5,
                "inflation_next_year": 20.0,
            },
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/projections")
def get_economic_projections():
    """
    IMF Projections for GDP and Inflation
    """
    client = get_ch_client()
    try:
        results = client.query("""
            SELECT indicator_code, indicator_label, year, value, is_forecast
            FROM imf_projections
            ORDER BY indicator_code, year
        """).result_rows
        
        projections = {}
        for row in results:
            code = row[0]
            if code not in projections:
                projections[code] = {"label": row[1], "history": [], "forecast": []}
            
            item = {"year": row[2], "value": round(row[3], 2)}
            if row[4]:
                projections[code]["forecast"].append(item)
            else:
                projections[code]["history"].append(item)
                
        return {
            "projections": projections,
            "source": "IMF Data Mapper",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "projections": {}}


@router.get("/gdp-growth")
def get_gdp_growth(years: int = Query(15, ge=5, le=30)):
    """
    GDP growth rate over time
    """
    try:
        client = get_ch_client()
        
        query = f"""
            SELECT year, value
            FROM wb_indicators
            WHERE indicator_code = 'NY.GDP.MKTP.KD.ZG'
            AND value IS NOT NULL
            ORDER BY year DESC
            LIMIT {years}
        """
        
        results = client.query(query).result_rows
        
        # Reverse to get chronological order
        timeline = [
            {
                "year": row[0],
                "growth_rate": round(row[1], 2)
            }
            for row in reversed(results)
        ]
        
        # Calculate statistics
        if timeline:
            values = [t['growth_rate'] for t in timeline]
            avg_growth = sum(values) / len(values)
            max_growth = max(values)
            min_growth = min(values)
            latest_growth = timeline[-1]['growth_rate']
        else:
            avg_growth = max_growth = min_growth = latest_growth = 0
        
        return {
            "timeline": timeline,
            "statistics": {
                "latest": latest_growth,
                "average": round(avg_growth, 2),
                "highest": max_growth,
                "lowest": min_growth,
                "period": f"{timeline[0]['year']}-{timeline[-1]['year']}" if timeline else "N/A"
            },
            "data_source": "World Bank",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "timeline": [],
            "statistics": {"latest": 0, "average": 0, "highest": 0, "lowest": 0, "period": "N/A"},
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/inflation")
def get_inflation(years: int = Query(15, ge=5, le=30)):
    """
    Inflation rate over time
    """
    try:
        client = get_ch_client()
        
        query = f"""
            SELECT year, value
            FROM wb_indicators
            WHERE indicator_code = 'FP.CPI.TOTL.ZG'
            AND value IS NOT NULL
            ORDER BY year DESC
            LIMIT {years}
        """
        
        results = client.query(query).result_rows
        
        # Reverse to get chronological order
        timeline = [
            {
                "year": row[0],
                "inflation_rate": round(row[1], 2)
            }
            for row in reversed(results)
        ]
        
        # Calculate statistics
        if timeline:
            values = [t['inflation_rate'] for t in timeline]
            avg_inflation = sum(values) / len(values)
            max_inflation = max(values)
            min_inflation = min(values)
            latest_inflation = timeline[-1]['inflation_rate']
        else:
            avg_inflation = max_inflation = min_inflation = latest_inflation = 0
        
        return {
            "timeline": timeline,
            "statistics": {
                "latest": latest_inflation,
                "average": round(avg_inflation, 2),
                "peak": max_inflation,
                "lowest": min_inflation,
                "period": f"{timeline[0]['year']}-{timeline[-1]['year']}" if timeline else "N/A"
            },
            "data_source": "World Bank",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "timeline": [],
            "statistics": {"latest": 0, "average": 0, "peak": 0, "lowest": 0, "period": "N/A"},
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/population")
def get_population(years: int = Query(15, ge=5, le=30)):
    """
    Population over time
    """
    try:
        client = get_ch_client()
        
        query = f"""
            SELECT year, value
            FROM wb_indicators
            WHERE indicator_code = 'SP.POP.TOTL'
            AND value IS NOT NULL
            ORDER BY year DESC
            LIMIT {years}
        """
        
        results = client.query(query).result_rows
        
        # Reverse to get chronological order
        timeline = [
            {
                "year": row[0],
                "population": int(row[1])
            }
            for row in reversed(results)
        ]
        
        # Calculate growth
        if len(timeline) >= 2:
            latest_pop = timeline[-1]['population']
            previous_pop = timeline[-2]['population']
            growth_rate = ((latest_pop - previous_pop) / previous_pop) * 100
        else:
            growth_rate = 0
        
        return {
            "timeline": timeline,
            "statistics": {
                "latest": timeline[-1]['population'] if timeline else 0,
                "growth_rate": round(growth_rate, 2),
                "period": f"{timeline[0]['year']}-{timeline[-1]['year']}" if timeline else "N/A"
            },
            "data_source": "World Bank",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "timeline": [],
            "statistics": {"latest": 0, "growth_rate": 0, "period": "N/A"},
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/indicators")
def get_all_indicators():
    """
    Get all available indicators with latest values
    """
    client = get_ch_client()
    
    query = """
        SELECT 
            indicator_code,
            indicator_name,
            MAX(year) as latest_year,
            argMax(value, year) as latest_value
        FROM wb_indicators
        WHERE value IS NOT NULL
        GROUP BY indicator_code, indicator_name
        ORDER BY indicator_name
    """
    
    results = client.query(query).result_rows
    
    indicators = [
        {
            "code": row[0],
            "name": row[1],
            "latest_year": row[2],
            "latest_value": round(row[3], 2)
        }
        for row in results
    ]
    
    return {
        "indicators": indicators,
        "total": len(indicators),
        "data_source": "World Bank",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/indicator/{code}")
def get_indicator_detail(code: str, years: int = Query(20, ge=5, le=50)):
    """
    Get detailed data for a specific indicator
    """
    client = get_ch_client()
    
    # Get indicator name
    name_query = f"""
        SELECT DISTINCT indicator_name
        FROM wb_indicators
        WHERE indicator_code = '{code}'
        LIMIT 1
    """
    name_result = client.query(name_query).result_rows
    indicator_name = name_result[0][0] if name_result else code
    
    # Get time series data
    query = f"""
        SELECT year, value
        FROM wb_indicators
        WHERE indicator_code = '{code}'
        AND value IS NOT NULL
        ORDER BY year DESC
        LIMIT {years}
    """
    
    results = client.query(query).result_rows
    
    # Reverse to get chronological order
    timeline = [
        {
            "year": row[0],
            "value": round(row[1], 2)
        }
        for row in reversed(results)
    ]
    
    return {
        "indicator_code": code,
        "indicator_name": indicator_name,
        "timeline": timeline,
        "data_source": "World Bank",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/growth-story")
def get_growth_story():
    """
    Ethiopia's economic growth story with key milestones
    """
    try:
        client = get_ch_client()
        
        gdp_query = """
            SELECT year, value FROM wb_indicators
            WHERE indicator_code = 'NY.GDP.MKTP.KD.ZG' AND value IS NOT NULL AND year >= 2010
            ORDER BY year
        """
        gdp_results = client.query(gdp_query).result_rows
        
        inflation_query = """
            SELECT year, value FROM wb_indicators
            WHERE indicator_code = 'FP.CPI.TOTL.ZG' AND value IS NOT NULL AND year >= 2010
            ORDER BY year
        """
        inflation_results = client.query(inflation_query).result_rows
        
        gdp_data = [(row[0], round(row[1], 2)) for row in gdp_results]
        inflation_data = [(row[0], round(row[1], 2)) for row in inflation_results]
        
        peak_growth = [g for g in gdp_data if 2010 <= g[0] <= 2015]
        avg_peak = sum(g[1] for g in peak_growth) / len(peak_growth) if peak_growth else 0
        conflict_period = [g for g in gdp_data if 2020 <= g[0] <= 2022]
        avg_conflict = sum(g[1] for g in conflict_period) / len(conflict_period) if conflict_period else 0
        recovery_period = [g for g in gdp_data if g[0] >= 2023]
        avg_recovery = sum(g[1] for g in recovery_period) / len(recovery_period) if recovery_period else 0
        
        inflation_peak = max(inflation_data, key=lambda x: x[1]) if inflation_data else (0, 0)
        inflation_latest = inflation_data[-1] if inflation_data else (0, 0)
        improvement = round(inflation_peak[1] - inflation_latest[1], 2) if inflation_data else 0
        
        return {
            "story": {
                "peak_growth_period": {
                    "years": "2010-2015",
                    "average_growth": round(avg_peak, 2),
                    "description": "Ethiopia's golden decade - double-digit growth"
                },
                "conflict_period": {
                    "years": "2020-2022",
                    "average_growth": round(avg_conflict, 2),
                    "description": "Growth slowdown due to internal conflict and global shocks"
                },
                "recovery_period": {
                    "years": "2023-Present",
                    "average_growth": round(avg_recovery, 2),
                    "description": "Economic recovery and reform implementation"
                },
                "inflation_story": {
                    "peak": {"year": inflation_peak[0], "rate": inflation_peak[1], "description": "Inflation peaked during conflict"},
                    "latest": {"year": inflation_latest[0], "rate": inflation_latest[1], "description": "Inflation declining after reforms"},
                    "improvement": improvement
                }
            },
            "inflation_context": {
                "peak_year": inflation_peak[0],
                "peak_rate": inflation_peak[1],
                "latest_rate": inflation_latest[1]
            },
            "gdp_timeline": gdp_data,
            "inflation_timeline": inflation_data,
            "data_source": "World Bank",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "story": {
                "peak_growth_period": {"years": "2010-2015", "average_growth": 10.5, "description": "Ethiopia's golden decade - double-digit growth"},
                "conflict_period": {"years": "2020-2022", "average_growth": 5.6, "description": "Growth slowdown due to internal conflict and global shocks"},
                "recovery_period": {"years": "2023-Present", "average_growth": 7.2, "description": "Economic recovery and reform implementation"},
                "inflation_story": {
                    "peak": {"year": 2022, "rate": 33.9, "description": "Inflation peaked during conflict"},
                    "latest": {"year": 2023, "rate": 28.5, "description": "Inflation declining after reforms"},
                    "improvement": 5.4
                }
            },
            "inflation_context": {"peak_year": 2022, "peak_rate": 33.9, "latest_rate": 28.5},
            "gdp_timeline": [],
            "inflation_timeline": [],
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }

