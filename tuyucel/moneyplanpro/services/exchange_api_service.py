import os
import requests
from utils.cache import cache
from dotenv import load_dotenv

load_dotenv()

class ExchangeApiService:
    def __init__(self):
        self.api_key = os.getenv("EXCHANGEAPI_TOKEN")
        self.base_url = f"https://v6.exchangerate-api.com/v6/{self.api_key}/latest"
        self.TTL = 86400  # 24 saat (Free tier günde 1 kez güncelleniyor)

    def get_try_rates(self):
        """TRY bazlı tüm kurları getirir ve TradingView formatına benzetir."""
        cache_key = "exchangerate_api_try_v1"
        cached = cache.get(cache_key)
        if cached:
            return cached

        if not self.api_key:
            print("EXCHANGEAPI_TOKEN not found in environment")
            return []

        try:
            # TRY'yi baz alarak tüm karşılıkları çek
            url = f"{self.base_url}/TRY"
            response = requests.get(url, timeout=10)
            data = response.json()

            if data.get("result") == "success":
                conversion_rates = data.get("conversion_rates", {})
                
                # Bizim desteklediğimiz kurlar
                target_symbols = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR"]
                results = []

                for sym in target_symbols:
                    # API'den gelen 1 TRY = X USD. Bize 1 USD = X TRY lazım.
                    # Bu yüzden 1 / rate yapıyoruz.
                    rate_to_try = conversion_rates.get(sym)
                    if rate_to_try:
                        price = round(1 / rate_to_try, 4)
                        results.append({
                            "symbol": sym,
                            "name": f"{sym}/TRY",
                            "price": price,
                            "change_percent": 0.0,  # Free tier anlık değişim vermez
                            "recommendation": "NEUTRAL",
                            "volume": 0,
                            "market_cap": 0,
                            "logo_url": f"https://s3-symbol-logo.tradingview.com/country/{sym[:2].lower()}.svg"
                        })
                
                if results:
                    cache.set(cache_key, results, ttl_seconds=self.TTL)
                return results

        except Exception as e:
            print(f"ExchangeRate-API Error: {e}")
            
        return []

exchange_api_service = ExchangeApiService()
