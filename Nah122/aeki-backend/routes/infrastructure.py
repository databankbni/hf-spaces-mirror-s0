"""
Infrastructure & Healthcare API
Powered by Ethiopian Health Facilities Dataset (40,525 facilities)
"""

from fastapi import APIRouter, Query
from datetime import datetime, timezone
import clickhouse_connect
import os
import math
import re
import httpx

router = APIRouter()

# Region population estimates (2023, millions) for per-capita scoring
REGION_POPULATION = {
    "Oromia": 42.0, "Amhara": 22.0, "SNNP": 20.0, "Somali": 8.0,
    "Tigray": 6.0, "Addis Ababa": 5.5, "Afar": 2.0, "South West Ethiopia": 4.0,
    "Sidama": 4.5, "Benishangul Gumz": 1.2, "Gambela": 0.5,
    "Harari": 0.3, "Dire Dawa": 0.5,
}

# ── WHO Disease Outbreak News ─────────────────────────────────────────────────

WHO_DON_URL = "https://www.who.int/api/emergencies/diseaseoutbreaknews"

DISEASE_KEYWORDS = {
    "Cholera":   ["cholera"],
    "Malaria":   ["malaria"],
    "Measles":   ["measles"],
    "Dengue":    ["dengue"],
    "Marburg":   ["marburg"],
    "Ebola":     ["ebola", "sudan virus"],
    "Mpox":      ["mpox", "monkeypox"],
    "Meningitis":["meningitis", "meningococcal"],
    "Anthrax":   ["anthrax"],
    "Rabies":    ["rabies"],
}

def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()

def classify_disease(title: str, overview: str) -> str:
    text = (title + " " + overview).lower()
    for disease, keywords in DISEASE_KEYWORDS.items():
        if any(k in text for k in keywords):
            return disease
    return "Other"

def time_ago(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        days = diff.days
        if days == 0:
            hours = diff.seconds // 3600
            return f"{hours}h ago" if hours > 0 else "Just now"
        elif days < 7:
            return f"{days}d ago"
        elif days < 30:
            return f"{days // 7}w ago"
        else:
            return f"{days // 30}mo ago"
    except Exception:
        return "Unknown"


@router.get("/healthcare/disease-outbreaks")
async def get_disease_outbreaks(limit: int = Query(20, ge=5, le=100)):
    """
    Fetch real-time disease outbreak news for Ethiopia from WHO DON API.
    Filters global WHO DON feed for Ethiopia-specific alerts.
    Source: https://www.who.int/emergencies/disease-outbreak-news
    """
    ethiopia_alerts = []
    skip = 0
    max_pages = 10  # scan up to 500 records

    async with httpx.AsyncClient(timeout=15.0) as client:
        while len(ethiopia_alerts) < limit and skip < max_pages * 50:
            try:
                resp = await client.get(
                    WHO_DON_URL,
                    params={"$skip": skip, "$top": 50,
                            "$orderby": "PublicationDateAndTime desc"}
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("value", [])
                if not items:
                    break

                for item in items:
                    title    = item.get("Title", "")
                    overview = strip_html(item.get("Overview", ""))
                    summary  = item.get("Summary", "") or overview[:300]
                    pub_date = item.get("PublicationDateAndTime", "")
                    url_name = item.get("ItemDefaultUrl", "")

                    # Filter for Ethiopia
                    combined = (title + " " + overview).lower()
                    if "ethiopia" not in combined:
                        continue

                    disease = classify_disease(title, overview)

                    ethiopia_alerts.append({
                        "id":       item.get("Id", ""),
                        "title":    title,
                        "disease":  disease,
                        "summary":  summary[:400],
                        "location": "Ethiopia",
                        "published": pub_date,
                        "updated":  time_ago(pub_date),
                        "url":      f"https://www.who.int/emergencies/disease-outbreak-news/item{url_name}",
                        "source":   "WHO Disease Outbreak News",
                    })

                    if len(ethiopia_alerts) >= limit:
                        break

                skip += 50
                if "nextLink" not in data:
                    break

            except Exception as e:
                break

    return {
        "outbreaks":   ethiopia_alerts,
        "total":       len(ethiopia_alerts),
        "source":      "WHO Disease Outbreak News (live)",
        "source_url":  "https://www.who.int/emergencies/disease-outbreak-news",
        "timestamp":   datetime.utcnow().isoformat(),
    }

def get_ch_client():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client


def calculate_access_score(total_facilities: int, hospitals: int, region: str) -> float:
    """
    Per-capita access score (0–100).
    Uses facilities per 100k population as the primary driver.
    """
    pop_millions = REGION_POPULATION.get(region, 5.0)
    pop_100k = pop_millions * 10
    facilities_per_100k = total_facilities / pop_100k if pop_100k > 0 else 0
    hospitals_per_100k  = hospitals / pop_100k if pop_100k > 0 else 0

    # Score: 60% weight on general facilities, 40% on hospitals
    # Benchmarks: 50 facilities/100k = full score; 2 hospitals/100k = full score
    facility_score = min(facilities_per_100k / 50 * 60, 60)
    hospital_score = min(hospitals_per_100k / 2 * 40, 40)
    return round(facility_score + hospital_score, 1)


@router.get("/healthcare/overview")
def get_healthcare_overview():
    try:
        client = get_ch_client()

        type_results = client.query("""
            SELECT facility_type, COUNT(*) AS n
            FROM healthcare_facilities
            GROUP BY facility_type ORDER BY n DESC
        """).result_rows

        regional_results = client.query("""
            SELECT region, COUNT(*) AS n
            FROM healthcare_facilities
            GROUP BY region ORDER BY n DESC
        """).result_rows

        hospitals_count = next((r[1] for r in type_results if r[0] == "Hospital"), 0)
        health_posts    = next((r[1] for r in type_results if r[0] == "Health Post"), 0)
        total           = sum(r[1] for r in type_results)

        return {
            "total_facilities":     total,
            "total_beds":           0,
            "emergency_facilities": hospitals_count,
            "hospitals":            hospitals_count,
            "health_posts":         health_posts,
            "regions_covered":      len(regional_results),
            "by_type":   [{"type": r[0], "count": r[1]} for r in type_results],
            "by_region": [{"region": r[0], "count": r[1]} for r in regional_results],
            "data_source": "OpenStreetMap (live)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "total_facilities":     40525,
            "total_beds":           0,
            "emergency_facilities": 1520,
            "hospitals":            1520,
            "health_posts":         22500,
            "regions_covered":      13,
            "by_type":   [{"type": "Health Post", "count": 22500}, {"type": "Clinic", "count": 14000}, {"type": "Hospital", "count": 1520}],
            "by_region": [{"region": "Oromia", "count": 14200}, {"region": "Amhara", "count": 9100}, {"region": "SNNP", "count": 7800}],
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/healthcare/regional-analysis")
def get_regional_analysis():
    try:
        client = get_ch_client()

        results = client.query("""
            SELECT
                region,
                COUNT(*) AS total_facilities,
                SUM(CASE WHEN facility_type = 'Hospital'      THEN 1 ELSE 0 END) AS hospitals,
                SUM(CASE WHEN facility_type = 'Clinic'        THEN 1 ELSE 0 END) AS clinics,
                SUM(CASE WHEN facility_type = 'Health Post'   THEN 1 ELSE 0 END) AS health_posts,
                SUM(CASE WHEN facility_type = 'Doctors Office' THEN 1 ELSE 0 END) AS doctors,
                SUM(CASE WHEN ownership LIKE '%Public%'       THEN 1 ELSE 0 END) AS public_count,
                SUM(CASE WHEN ownership LIKE '%Private%'      THEN 1 ELSE 0 END) AS private_count
            FROM healthcare_facilities
            GROUP BY region
            ORDER BY total_facilities DESC
        """).result_rows

        data = []
        for row in results:
            region = row[0]
            total  = row[1]
            hosp   = row[2]
            pop    = REGION_POPULATION.get(region, 5.0)
            data.append({
                "region":           region,
                "total_facilities": total,
                "hospitals":        hosp,
                "clinics":          row[3],
                "health_posts":     row[4],
                "doctors_offices":  row[5],
                "public_count":     row[6],
                "private_count":    row[7],
                "population_m":     pop,
                "per_100k":         round(total / (pop * 10), 1),
                "access_score":     calculate_access_score(total, hosp, region),
            })

        return {
            "regional_analysis": data,
            "data_source": "OpenStreetMap (live)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "regional_analysis": [
                {
                    "region": "Oromia", "total_facilities": 14200, "hospitals": 310,
                    "clinics": 4500, "health_posts": 8200, "doctors_offices": 110,
                    "public_count": 9100, "private_count": 5100, "population_m": 42.0,
                    "per_100k": 33.8, "access_score": 52.4
                },
                {
                    "region": "Amhara", "total_facilities": 9100, "hospitals": 215,
                    "clinics": 2800, "health_posts": 5600, "doctors_offices": 85,
                    "public_count": 6800, "private_count": 2300, "population_m": 22.0,
                    "per_100k": 41.4, "access_score": 60.1
                }
            ],
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/healthcare/coverage-gaps")
def get_coverage_gaps():
    """Regions with lowest facilities-per-100k population."""
    try:
        client = get_ch_client()

        results = client.query("""
            SELECT region, COUNT(*) AS n
            FROM healthcare_facilities
            GROUP BY region ORDER BY n ASC
        """).result_rows

        gaps = []
        for row in results:
            region = row[0]
            count  = row[1]
            pop    = REGION_POPULATION.get(region, 5.0)
            per_100k = round(count / (pop * 10), 1)
            # Flag regions below 30 facilities per 100k as underserved
            if per_100k < 30:
                severity = "Critical" if per_100k < 10 else "High" if per_100k < 20 else "Moderate"
                gaps.append({
                    "region":        region,
                    "facility_count": count,
                    "per_100k":      per_100k,
                    "severity":      severity,
                })

        return {
            "coverage_gaps": gaps,
            "total_underserved_regions": len(gaps),
            "threshold": "< 30 facilities per 100k population",
            "data_source": "OpenStreetMap (live)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        # Fallback when rate limits or DB errors occur
        return {
            "coverage_gaps": [
                {"region": "Somali", "facility_count": 820, "per_100k": 10.2, "severity": "High"},
                {"region": "Afar", "facility_count": 215, "per_100k": 10.7, "severity": "High"},
                {"region": "Gambela", "facility_count": 85, "per_100k": 17.0, "severity": "High"}
            ],
            "total_underserved_regions": 3,
            "threshold": "< 30 facilities per 100k population",
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/healthcare/ownership-breakdown")
def get_ownership_breakdown():
    """Public vs Private vs NGO breakdown — national and per region."""
    try:
        client = get_ch_client()

        national = client.query("""
            SELECT ownership, COUNT(*) AS n
            FROM healthcare_facilities
            GROUP BY ownership ORDER BY n DESC
        """).result_rows

        by_region = client.query("""
            SELECT region, ownership, COUNT(*) AS n
            FROM healthcare_facilities
            GROUP BY region, ownership ORDER BY region, n DESC
        """).result_rows

        # Group by region
        region_map: dict = {}
        for row in by_region:
            r = row[0]
            if r not in region_map:
                region_map[r] = []
            region_map[r].append({"ownership": row[1], "count": row[2]})

        return {
            "national": [{"ownership": r[0], "count": r[1]} for r in national],
            "by_region": [{"region": k, "breakdown": v} for k, v in region_map.items()],
            "data_source": "OpenStreetMap (live)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "national": [{"ownership": "Public", "count": 25000}, {"ownership": "Private", "count": 15000}, {"ownership": "NGO", "count": 525}],
            "by_region": [{"region": "Oromia", "breakdown": [{"ownership": "Public", "count": 9100}, {"ownership": "Private", "count": 5100}]}],
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/healthcare/life-expectancy")
async def get_life_expectancy():
    """
    Fetch Ethiopia life expectancy from World Bank API (SP.DYN.LE00.IN).
    Also fetches Sub-Saharan Africa average (ZG) for comparison.
    Source: https://api.worldbank.org/v2/country/ET/indicator/SP.DYN.LE00.IN
    Updated: annually by World Bank (latest confirmed: 2024 = 67.6 years)
    """
    import asyncio
    async with httpx.AsyncClient(timeout=15.0) as client:
        et_url  = "https://api.worldbank.org/v2/country/ET/indicator/SP.DYN.LE00.IN"
        ssa_url = "https://api.worldbank.org/v2/country/ZG/indicator/SP.DYN.LE00.IN"
        params  = {"format": "json", "per_page": "40", "mrv": "40"}

        et_resp, ssa_resp = await asyncio.gather(
            client.get(et_url,  params=params),
            client.get(ssa_url, params=params),
        )

        et_data  = et_resp.json()[1]  if et_resp.status_code  == 200 else []
        ssa_data = ssa_resp.json()[1] if ssa_resp.status_code == 200 else []

    et_map  = {int(r["date"]): round(r["value"], 1) for r in et_data  if r.get("value") is not None}
    ssa_map = {int(r["date"]): round(r["value"], 1) for r in ssa_data if r.get("value") is not None}

    years  = sorted(set(list(et_map.keys()) + list(ssa_map.keys())))
    years  = [y for y in years if y >= 1990]

    series = []
    for year in years:
        et_val = et_map.get(year)
        if et_val is not None:
            series.append({
                "year":     year,
                "ethiopia": et_val,
                "africa":   ssa_map.get(year),
            })

    latest = series[-1] if series else {}
    first  = next((s for s in series if s["year"] == 1990), None)
    gain   = round(latest.get("ethiopia", 0) - (first.get("ethiopia", 0) if first else 0), 1)

    return {
        "series":          series,
        "latest_year":     latest.get("year"),
        "latest_value":    latest.get("ethiopia"),
        "gain_since_1990": gain,
        "source":          "World Bank SP.DYN.LE00.IN",
        "source_url":      "https://data.worldbank.org/indicator/SP.DYN.LE00.IN?locations=ET",
        "timestamp":       datetime.utcnow().isoformat(),
    }


@router.get("/healthcare/vaccination-coverage")
async def get_vaccination_coverage():
    """
    Ethiopia national vaccination coverage trend from World Bank API.
    Indicators: SH.IMM.MEAS (Measles/MCV1), SH.IMM.IDPT (DPT3)
    Latest: 2024 data (released 2025)
    Source: World Bank / WHO-UNICEF WUENIC
    """
    import asyncio
    async with httpx.AsyncClient(timeout=15.0) as client:
        measles_url = "https://api.worldbank.org/v2/country/ET/indicator/SH.IMM.MEAS"
        dpt_url     = "https://api.worldbank.org/v2/country/ET/indicator/SH.IMM.IDPT"
        params = {"format": "json", "per_page": "30", "mrv": "30"}

        measles_resp, dpt_resp = await asyncio.gather(
            client.get(measles_url, params=params),
            client.get(dpt_url,     params=params),
        )

        measles_data = measles_resp.json()[1] if measles_resp.status_code == 200 else []
        dpt_data     = dpt_resp.json()[1]     if dpt_resp.status_code     == 200 else []

    measles_map = {int(r["date"]): r["value"] for r in measles_data if r.get("value") is not None}
    dpt_map     = {int(r["date"]): r["value"] for r in dpt_data     if r.get("value") is not None}

    years = sorted(set(list(measles_map.keys()) + list(dpt_map.keys())))
    years = [y for y in years if y >= 2000]

    series = [
        {
            "year":    y,
            "measles": measles_map.get(y),
            "dpt3":    dpt_map.get(y),
        }
        for y in years
        if measles_map.get(y) is not None or dpt_map.get(y) is not None
    ]

    latest = series[-1] if series else {}

    return {
        "series":          series,
        "latest_year":     latest.get("year"),
        "latest_measles":  latest.get("measles"),
        "latest_dpt3":     latest.get("dpt3"),
        "target":          95,
        "source":          "World Bank / WHO-UNICEF WUENIC (SH.IMM.MEAS, SH.IMM.IDPT)",
        "source_url":      "https://data.worldbank.org/indicator/SH.IMM.MEAS?locations=ET",
        "note":            "National estimates only. Regional breakdown from Ethiopia DHS 2019.",
        "timestamp":       datetime.utcnow().isoformat(),
    }


@router.get("/healthcare/hospitals-map")
def get_hospitals_map(
    facility_type: str = Query(None, description="all | Hospital | Clinic | Health Post | Pharmacy | Health Center")
):
    """
    Facilities for map.
    - Single type: returns up to 1000 facilities
    - 'all': returns up to 300 per type (sampled) for performance
    """
    try:
        client = get_ch_client()

        if facility_type and facility_type.lower() == "all":
            # Sample 300 per type to keep total under ~2000 markers
            types = ["Hospital", "Health Center", "Clinic", "Health Post", "Pharmacy"]
            all_rows = []
            for t in types:
                rows = client.query(f"""
                    SELECT id, name, facility_type, latitude, longitude,
                           region, ownership, woreda, zone
                    FROM healthcare_facilities
                    WHERE facility_type = '{t}'
                    ORDER BY rand()
                    LIMIT 300
                """).result_rows
                all_rows.extend(rows)
            results = all_rows
        elif facility_type:
            results = client.query(f"""
                SELECT id, name, facility_type, latitude, longitude,
                       region, ownership, woreda, zone
                FROM healthcare_facilities
                WHERE facility_type = '{facility_type}'
                ORDER BY region, name
                LIMIT 1000
            """).result_rows
        else:
            results = client.query("""
                SELECT id, name, facility_type, latitude, longitude,
                       region, ownership, woreda, zone
                FROM healthcare_facilities
                WHERE facility_type = 'Hospital'
                ORDER BY region, name
                LIMIT 1000
            """).result_rows

        return {
            "hospitals": [
                {
                    "id":            row[0],
                    "name":          row[1],
                    "facility_type": row[2],
                    "latitude":      row[3],
                    "longitude":     row[4],
                    "region":        row[5],
                    "ownership":     row[6],
                    "woreda":        row[7],
                    "zone":          row[8],
                }
                for row in results
            ],
            "total": len(results),
            "data_source": "OpenStreetMap (live)",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "hospitals": [
                {
                    "id": 1,
                    "name": "Addis Ababa General Hospital",
                    "facility_type": "Hospital",
                    "latitude": 9.0300,
                    "longitude": 38.7400,
                    "region": "Addis Ababa",
                    "ownership": "Public",
                    "woreda": "Kirkos",
                    "zone": "Addis Ababa"
                }
            ],
            "total": 1,
            "data_source": "Fallback Data",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/healthcare/facilities")
def get_all_facilities(
    facility_type: str = Query(None),
    region: str = Query(None)
):
    client = get_ch_client()
    clauses = []
    if facility_type: clauses.append(f"facility_type = '{facility_type}'")
    if region:        clauses.append(f"region = '{region}'")
    where = " AND ".join(clauses) if clauses else "1=1"

    results = client.query(f"""
        SELECT id, name, facility_type, latitude, longitude,
               region, ownership, woreda, zone
        FROM healthcare_facilities WHERE {where}
        ORDER BY facility_type, name LIMIT 2000
    """).result_rows

    return {
        "facilities": [
            {"id": r[0], "name": r[1], "facility_type": r[2],
             "latitude": r[3], "longitude": r[4], "region": r[5],
             "ownership": r[6], "woreda": r[7], "zone": r[8]}
            for r in results
        ],
        "total": len(results),
        "data_source": "OpenStreetMap (live)",
        "timestamp": datetime.utcnow().isoformat()
    }


# ── Legacy endpoints kept for compatibility ───────────────────────────────────

@router.get("/healthcare/by-type")
def get_facilities_by_type():
    client = get_ch_client()
    rows = client.query("""
        SELECT facility_type, ownership, COUNT(*) AS n
        FROM healthcare_facilities
        GROUP BY facility_type, ownership ORDER BY n DESC
    """).result_rows
    return {
        "by_type_ownership": [{"facility_type": r[0], "ownership": r[1], "count": r[2]} for r in rows],
        "data_source": "OpenStreetMap (live)",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/healthcare/facility-deserts")
def get_facility_deserts():
    client = get_ch_client()
    hospitals = client.query("""
        SELECT name, latitude, longitude FROM healthcare_facilities
        WHERE facility_type = 'Hospital'
    """).result_rows

    region_centers = [
        {"region": "Tigray",            "lat": 13.5, "lon": 39.0},
        {"region": "Afar",              "lat": 11.5, "lon": 41.0},
        {"region": "Amhara",            "lat": 11.5, "lon": 38.0},
        {"region": "Oromia",            "lat":  8.5, "lon": 38.5},
        {"region": "Somali",            "lat":  7.0, "lon": 44.0},
        {"region": "Benishangul Gumz",  "lat": 10.5, "lon": 35.0},
        {"region": "SNNP",              "lat":  6.5, "lon": 37.5},
        {"region": "Gambela",           "lat":  8.0, "lon": 34.5},
        {"region": "Harari",            "lat":  9.3, "lon": 42.1},
        {"region": "Dire Dawa",         "lat":  9.6, "lon": 41.9},
    ]

    deserts = []
    for rc in region_centers:
        min_d = float("inf")
        nearest = None
        for h in hospitals:
            d = haversine_distance(rc["lat"], rc["lon"], h[1], h[2])
            if d < min_d:
                min_d = d; nearest = h[0]
        if min_d > 50:
            deserts.append({
                "region": rc["region"],
                "distance_to_nearest_hospital_km": round(min_d, 1),
                "nearest_hospital": nearest,
                "severity": "Critical" if min_d > 100 else "High"
            })

    return {"facility_deserts": deserts, "total_desert_regions": len(deserts),
            "threshold_km": 50, "data_source": "Ethiopian Health Facilities Dataset",
            "timestamp": datetime.utcnow().isoformat()}


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

