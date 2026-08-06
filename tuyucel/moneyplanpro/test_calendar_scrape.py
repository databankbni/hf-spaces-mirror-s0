import requests
import re
from datetime import datetime

url = "https://finans.mynet.com/ekonomik-takvim/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        content = resp.text
        # Look for some data structure or table
        # Mynet usually has a table with class "calendar-table" or similar
        print(content[:500])
        
        # Simple regex check for data
        matches = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL)
        print(f"Found {len(matches)} rows")
except Exception as e:
    print(e)
