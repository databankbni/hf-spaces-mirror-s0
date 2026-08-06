import requests
from utils.cache import cache

class FawazAhmedCurrencyService:
    def __init__(self):
        self.base_url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/try.json"
        self.fallback_url = "https://latest.currency-api.pages.dev/v1/currencies/try.json"
        self.TTL = 86400  # 24 saat

    def get_try_rates(self):
        """CDN üzerinden limitsiz ve anahtarsız TRY kurlarını çeker."""
        cache_key = "fawaz_ahmed_api_try_v1"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Bizim desteklediğimiz kurlar
        target_symbols = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR"]
        
        for url in [self.base_url, self.fallback_url]:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # Data yapısı: {"date": "...", "try": {"usd": 0.033, ...}}
                    try_rates = data.get("try", {})
                    
                    results = []
                    for sym in target_symbols:
                        # Bu API'de kurlar 1 TRY = X USD formatında
                        rate_to_try = try_rates.get(sym.lower())
                        if rate_to_try:
                            price = round(1 / rate_to_try, 4)
                            results.append({
                                "symbol": sym,
                                "name": f"{sym}/TRY",
                                "price": price,
                                "change_percent": 0.0,
                                "recommendation": "NEUTRAL",
                                "volume": 0,
                                "market_cap": 0,
                                "logo_url": f"https://s3-symbol-logo.tradingview.com/country/{sym[:2].lower()}.svg"
                            })
                    
                    if results:
                        cache.set(cache_key, results, ttl_seconds=self.TTL)
                        return results
            except Exception as e:
                print(f"FawazAhmed API error ({url}): {e}")
                continue
                
        return []

fawaz_currency_service = FawazAhmedCurrencyService()
