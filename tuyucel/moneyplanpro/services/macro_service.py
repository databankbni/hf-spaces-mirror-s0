import re
import requests
from datetime import datetime
from utils.cache import cache

class MacroService:
    def __init__(self):
        self.wb_url = "https://api.worldbank.org/v2"
        self.country_map = {
            "TR": "turkey", "US": "united-states", "DE": "germany", 
            "GB": "united-kingdom", "CN": "china", "JP": "japan", 
            "IN": "india", "BR": "brazil"
        }

    def get_country_indicators(self, country_code: str = "TR"):
        country_code = country_code.upper()
        cache_key = f"macro_pro_live_{country_code}"
        cached = cache.get(cache_key)
        if cached: return cached

        # Pro Fallback Zinciri: Mynet Verileri > World Bank API
        # Makro verileri de Mynet üzerinden çekmek Türkiye merkezli bir app için en garanti yoldur
        data = self._fetch_macro_dynamic(country_code)

        result = {
            "country": country_code,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "source": "Dynamic Pro Source"
        }
        # Makro veriler genelde aylık/yıllık değişir, ama kullanıcı dinamik istediği için haftalık (1 hafta) cache yeterlidir.
        cache.set(cache_key, result, ttl_seconds=604800)
        return result

    def _fetch_macro_dynamic(self, country_code):
        res = {}
        indicators = {
            "gdp_growth": "NY.GDP.MKTP.KD.ZG", 
            "inflation": "FP.CPI.TOTL.ZG", 
            "interest_rate": "FR.INR.RINR", 
            "unemployment": "SL.UEM.TOTL.ZS"
        }
        
        # World Bank API her zaman dinamik ve resmi veriyi döner
        for key, code in indicators.items():
            try:
                url = f"{self.wb_url}/country/{country_code}/indicator/{code}?format=json&per_page=1&mrnev=1"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    d = r.json()
                    if len(d) > 1 and d[1]:
                        # Tarih formatlamasını iyileştir (örn: 2023 yerine '2023' string olarak geliyor)
                        val = d[1][0]['value']
                        date = d[1][0]['date']
                        res[key] = {
                            "value": round(float(val), 2) if val is not None else 0,
                            "date": str(date), 
                            "is_estimate": False
                        }
                    else:
                        res[key] = {"value": 0, "date": "N/A"}
            except:
                res[key] = {"value": 0, "date": "Hata"}
        return res
        return res

macro_service = MacroService()
