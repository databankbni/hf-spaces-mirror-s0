import requests
import pandas as pd
from datetime import datetime, timedelta

def check_tefas(symbol):
    print(f"Checking {symbol}...")
    url = "https://www.tefas.gov.tr/api/DB/BindHistoryInfo"
    d_start = datetime.now() - timedelta(days=7)
    d_end = datetime.now()
    
    payload = {
        "fontip": "YAT",
        "sfontip": "",
        "bastarih": d_start.strftime("%d.%m.%Y"),
        "bittarih": d_end.strftime("%d.%m.%Y"),
        "fonkod": symbol.upper()
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
        "Origin": "https://www.tefas.gov.tr",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data and data["data"]:
                row = data["data"][0]
                print(f"SUCCESS: {symbol} - Date: {row['TARIH']}, Price: {row['FIYAT']}")
                return True
            else:
                print(f"EMPTY: {symbol} - No data returned.")
        else:
            print(f"FAIL: {symbol} - Status {resp.status_code}")
    except Exception as e:
        print(f"ERROR: {symbol} - {e}")
    return False

if __name__ == "__main__":
    check_tefas("TCD")
    check_tefas("AFT")
