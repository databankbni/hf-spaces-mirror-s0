import requests

url = "https://calendar-api.fxstreet.com/en/api/v1/eventDates"
params = {
    "start": "2026-01-24",
    "end": "2026-01-26"
}
headers = {
    "Accept": "application/json",
    "Origin": "https://www.fxstreet.com",
    "Referer": "https://www.fxstreet.com/"
}

try:
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Items: {len(data)}")
        if len(data) > 0:
            print("First item:", data[0])
    else:
        print("Response:", resp.text)
except Exception as e:
    print(f"Error: {e}")
