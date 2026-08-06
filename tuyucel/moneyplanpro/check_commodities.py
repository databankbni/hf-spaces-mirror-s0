import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def fetch_commodities():
    api_key = os.getenv("TWELVEAPI_TOKEN")
    url = f"https://api.twelvedata.com/commodities?apikey={api_key}"
    try:
        res = requests.get(url, timeout=30).json()
        if res.get("status") == "ok":
            print(f"Found {len(res.get('data', []))} commodities")
            for item in res.get("data", [])[:5]:
                print(item)
        else:
            print(f"Error: {res}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_commodities()
