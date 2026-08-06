
import requests
import json
import sys

# Dosya adı
FILENAME = "17-jan-26-weekly.json"

# API Endpoint (Hugging Face)
API_URL = "https://tuyucel-moneyplanpro.hf.space/api/v1/market/calendar"

def upload_calendar():
    try:
        with open(FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        if not events:
            print("No events found in JSON.")
            return

        print(f"Uploading {len(events)} events to {API_URL}...")
        
        # Body(..., embed=True) olduğu için {"events": [...]} şeklinde gitmeli
        payload = {"events": events}
        resp = requests.post(API_URL, json=payload)
        
        if resp.status_code == 200:
            print("Successfully uploaded calendar events!")
            print(resp.json())
        else:
            print(f"Failed to upload. Status: {resp.status_code}")
            print(resp.text)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    upload_calendar()
