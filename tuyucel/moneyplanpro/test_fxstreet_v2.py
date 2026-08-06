import requests

# Try endpoint from common scraping patterns
url = "https://calendar-api.fxstreet.com/en/api/v1/eventDates/2026-01-24/2026-01-27"
headers = {
    "Accept": "application/json",
    "Origin": "https://www.fxstreet.com",
    "Referer": "https://www.fxstreet.com/",
    "User-Agent": "Mozilla/5.0"
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Items: {len(data)}")
        first = data[0] if len(data) > 0 else "None"
        print("First:", first)
    else:
        print("Response:", resp.text[:200])
except Exception as e:
    print(f"Error: {e}")
