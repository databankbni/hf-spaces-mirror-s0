import os
import requests
import json
import time
from utils.cache import cache
from services.settings_service import settings_service

class TwelveDataService:
    def __init__(self):
        self.base_url = "https://api.twelvedata.com"
        self.TTL = 60 # 1 minute cache for individual symbols
        self.master_list_path = "backend/data/twelve_symbols.json"
        
        # Ensure data directory exists
        os.makedirs("backend/data", exist_ok=True)

    @property
    def api_key(self):
        return settings_service.get_value("TWELVEAPI_TOKEN")

    def sync_symbols(self):
        """
        Sync symbols from Twelve Data once a day.
        """
        if not self.api_key: return False
        
        try:
            symbols_data = {}
            countries = ["Turkey", "United States", "Germany", "United Kingdom"]
            
            for country in countries:
                print(f"Fetching stocks for {country}...")
                url = f"{self.base_url}/stocks?country={country}&apikey={self.api_key}"
                res = requests.get(url, timeout=60).json()
                if res.get("status") == "ok":
                    for item in res.get("data", []):
                        sym = item["symbol"]
                        symbols_data[sym] = {
                            "name": item["name"],
                            "currency": item["currency"],
                            "exchange": item["exchange"],
                            "mic_code": item["mic_code"],
                            "country": item["country"],
                            "type": item["type"]
                        }

            print("Fetching Forex pairs...")
            url = f"{self.base_url}/forex_pairs?apikey={self.api_key}"
            res = requests.get(url, timeout=60).json()
            if res.get("status") == "ok":
                for item in res.get("data", []):
                    sym = item["symbol"]
                    symbols_data[sym] = {
                        "name": item["currency_base"],
                        "currency": item["currency_quote"],
                        "type": "Forex"
                    }

            print("Fetching Commodities...")
            url = f"{self.base_url}/commodities?apikey={self.api_key}"
            res = requests.get(url, timeout=60).json()
            if res.get("status") == "ok":
                for item in res.get("data", []):
                    sym = item["symbol"]
                    symbols_data[sym] = {
                        "name": item["name"],
                        "type": "Commodity"
                    }

            # Save to disk
            with open(self.master_list_path, "w", encoding="utf-8") as f:
                json.dump(symbols_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Twelve Data Sync Error: {e}")
            return False

    def get_quotes(self, symbols: list):
        if not self.api_key: return {}

        results = {}
        to_fetch = []
        sym_map = {}

        # 1. Check Cache first
        for s in symbols:
            cache_key = f"td_quote_{s.upper()}"
            cached_val = cache.get(cache_key)
            if cached_val:
                results[s] = cached_val
            else:
                to_fetch.append(s)

        if not to_fetch:
            return results

        # 2. Prepare symbols for API
        formatted_symbols = []
        master = {}
        if os.path.exists(self.master_list_path):
            try:
                with open(self.master_list_path, "r", encoding="utf-8") as f:
                    master = json.load(f)
            except: pass

        for s in to_fetch:
            orig = s.upper().strip()
            target = orig
            
            if orig in master:
                m = master[orig]
                if m.get("mic_code"):
                    target = f"{orig}:{m['mic_code']}"
                elif m.get("type") == "Forex" and "/" not in orig:
                    target = f"{orig}/TRY"
            elif orig in ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR"]:
                target = f"{orig}/TRY"
            
            formatted_symbols.append(target)
            sym_map[target] = s

        try:
            sym_str = ",".join(formatted_symbols)
            url = f"{self.base_url}/quote?symbol={sym_str}&apikey={self.api_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if "status" in data and data["status"] == "error":
                print(f"Twelve Data API Error: {data}")
                return results # Return whatever we have from cache

            if isinstance(data, dict):
                if "symbol" in data:
                    item_data = self._parse_quote(data)
                    if item_data:
                        orig_sym = sym_map.get(formatted_symbols[0], symbols[0])
                        results[orig_sym] = item_data
                        cache.set(f"td_quote_{orig_sym.upper()}", item_data, ttl_seconds=self.TTL)
                else:
                    for s_target, quote_data in data.items():
                        if isinstance(quote_data, dict) and quote_data.get("status") != "error":
                            item_data = self._parse_quote(quote_data)
                            if item_data:
                                orig_sym = sym_map.get(s_target, s_target)
                                results[orig_sym] = item_data
                                cache.set(f"td_quote_{orig_sym.upper()}", item_data, ttl_seconds=self.TTL)
            return results
        except Exception as e:
            print(f"Twelve Data API Exception: {e}")
            return results

    def _parse_quote(self, q):
        try:
            return {
                "symbol": q.get("symbol"),
                "name": q.get("name") or q.get("symbol"),
                "price": float(q.get("price") or q.get("close") or 0.0),
                "change_percent": float(q.get("percent_change") or 0.0),
                "volume": int(q.get("volume") or 0),
                "high": float(q.get("high") or 0.0),
                "low": float(q.get("low") or 0.0),
                "close": float(q.get("close") or 0.0),
                "source": "TwelveData"
            }
        except Exception:
            return None

twelve_data_service = TwelveDataService()
