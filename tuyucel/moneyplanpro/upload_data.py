import sqlite3
import json
import urllib.request
import urllib.error
import sys
import os

# Configuration
API_URL = "https://invest-guide-api-wandering-snowflake-2603.fly.dev/api/v1/market/calendar?clear=true"
DB_PATH = "backend/invest_guide.db"

def upload_data():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    print("Reading local database...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM calendar_events").fetchall()
    
    events = []
    for row in rows:
        events.append({
            "event_id": row["event_id"],
            "date_time": row["date_time"],
            "country_id": row["country_id"],
            "currency": row["currency"],
            "title": row["title"],
            "impact": row["impact"],
            "actual": row["actual"],
            "forecast": row["forecast"],
            "previous": row["previous"],
            "unit": row["unit"],
            "category": row["category"],
            "description": row["description"]
        })
    conn.close()
    print(f"Prepared {len(events)} events for upload.")
    
    # Wrap in dict because FastAPI error indicated it expects "events" field in body
    payload = json.dumps({"events": events}).encode('utf-8')
    
    req = urllib.request.Request(API_URL, data=payload, method='POST')

    req.add_header('Content-Type', 'application/json')
    
    print(f"Uploading to {API_URL}...")
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print("Success! Data uploaded to production.")
                resp_body = response.read().decode('utf-8')
                print("Response:", resp_body)
            else:
                print(f"Failed with status {response.status}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")

if __name__ == "__main__":
    upload_data()
