import requests

url = "https://tuyucel-moneyplanpro.hf.space/api/v1/market/calendar"
try:
    resp = requests.get(url, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Items count: {len(data)}")
        if len(data) > 0:
            print("First item:", data[0])
    else:
        print("Response:", resp.text)
except Exception as e:
    print(f"Error: {e}")
