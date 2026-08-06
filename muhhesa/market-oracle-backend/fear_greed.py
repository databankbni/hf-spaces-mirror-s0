import requests

def fetch_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            fg_data = data.get('fear_and_greed', {})
            return {
                "status": "success",
                "score": round(fg_data.get('score', 0)),
                "rating": fg_data.get('rating', 'neutral').replace('_', ' ').title(),
                "previous_1_month": round(fg_data.get('previous_1_month', 0)),
                "previous_1_year": round(fg_data.get('previous_1_year', 0))
            }
        else:
            return {"status": "error", "error": f"HTTP {res.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
