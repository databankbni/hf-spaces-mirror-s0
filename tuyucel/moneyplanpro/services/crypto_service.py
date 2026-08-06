from datetime import datetime, timezone

import requests

from utils.cache import cache
from services.settings_service import settings_service


class CryptoService:
    COMMON_COIN_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "USDT": "tether",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "ADA": "cardano",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "DOT": "polkadot",
        "POL": "matic-network",
        "ZEC": "zcash",
        "FDUSD": "first-digital-usd",
    }
    PERIOD_DAYS = {
        "1d": 1,
        "1wk": 7,
        "1mo": 30,
        "3mo": 90,
        "1y": 365,
        "ytd": 365,
        "max": 365,
    }
    BASE_URL = "https://api.coingecko.com/api/v3"

    def _headers(self):
        api_key = settings_service.get_value("COINGECKO_API_KEY")
        return {"x-cg-demo-api-key": api_key} if api_key else {}

    def _request_json(self, path, params=None, timeout=10):
        response = requests.get(
            f"{self.BASE_URL}{path}",
            params=params,
            headers=self._headers(),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize_symbol(symbol):
        normalized = symbol.upper().strip()
        if normalized.endswith("USDT") and normalized != "USDT":
            normalized = normalized[:-4]
        return normalized

    def is_crypto_identifier(self, symbol):
        raw = symbol.lower().strip()
        normalized = self._normalize_symbol(symbol)
        return (
            normalized in self.COMMON_COIN_IDS
            or raw in self.COMMON_COIN_IDS.values()
            or symbol.upper().strip().endswith("USDT")
        )

    def _resolve_coin_id(self, symbol):
        raw = symbol.lower().strip()
        if raw in self.COMMON_COIN_IDS.values():
            return raw

        normalized = self._normalize_symbol(symbol)
        cache_key = f"coingecko_coin_id_{normalized}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        coin_id = self.COMMON_COIN_IDS.get(normalized)
        if not coin_id:
            search = self._request_json("/search", {"query": normalized})
            coins = search.get("coins", [])
            exact = next(
                (
                    coin
                    for coin in coins
                    if coin.get("symbol", "").upper() == normalized
                ),
                None,
            )
            coin_id = exact.get("id") if exact else None

        if coin_id:
            cache.set(cache_key, coin_id, ttl_seconds=86400)
        return coin_id

    def _get_market_chart(self, coin_id, days):
        cache_key = f"coingecko_chart_{coin_id}_{days}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        chart = self._request_json(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": "usd", "days": days},
        )
        cache.set(cache_key, chart, ttl_seconds=900)
        return chart

    def get_top_coins(self, limit=50):
        """
        Binance API (US Kısıtlaması) yerine CoinGecko Markets API kullanılır.
        """
        cache_key = f"crypto_gecko_top_{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            # CoinGecko Markets (Resim, Fiyat, Değişim hepsi tek endpointte)
            params = {
                "vs_currency": "usd",
                "order": "volume_desc", # Hacme göre sırala
                "per_page": limit,
                "page": 1,
                "sparkline": "false"
            }
            # Demo API (Rate limit: 30 calls/min)
            data = self._request_json("/coins/markets", params)
            results = []
            for item in data:
                results.append({
                    "id": item['id'],
                    "symbol": item['symbol'].upper(),
                    "name": item['name'],
                    "price": float(item['current_price'] or 0),
                    "change_24h": float(item['price_change_percentage_24h'] or 0),
                    "market_cap": float(item['market_cap'] or 0),
                    "volume": float(item['total_volume'] or 0),
                    "image": item['image'],
                    "source": "CoinGecko",
                })

            cache.set(cache_key, results, ttl_seconds=900)
            return results

        except Exception as e:
            print(f"CoinGecko Error: {e}")
            
        return []

    def get_ticker_summary(self, limit=5):
        """Return the compact crypto-only payload used by the market ticker."""
        coins = self.get_top_coins(limit=50)
        preferred_symbols = ("BTC", "ETH", "SOL", "BNB", "XRP")
        coins_by_symbol = {coin.get("symbol"): coin for coin in coins}
        selected = [
            coins_by_symbol[symbol]
            for symbol in preferred_symbols
            if symbol in coins_by_symbol
        ]
        if len(selected) < limit:
            selected.extend(
                coin for coin in coins
                if coin not in selected
            )

        return {
            "items": [
                {
                    "id": coin["id"],
                    "symbol": f"{coin['symbol']}/USD",
                    "price": coin["price"],
                    "change_percent": coin["change_24h"],
                }
                for coin in selected[:limit]
                if coin.get("price", 0) > 0
            ],
            "source": "CoinGecko",
            "cache_minutes": 15,
        }

    def get_fear_greed_index(self):
        """
        Kripto Korku ve Açgözlülük Endeksini getirir.
        Cache: 1 saat
        """
        cache_key = "crypto_fear_greed"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            import requests
            resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and "data" in data and len(data["data"]) > 0:
                    result = {
                        "value": int(data["data"][0]["value"]),
                        "classification": data["data"][0]["value_classification"],
                        "timestamp": data["data"][0]["timestamp"]
                    }
                    cache.set(cache_key, result, ttl_seconds=3600)
                    return result
        except Exception as e:
            print(f"Fear & Greed Error: {e}")
        
        return {
            "data_status": "unavailable",
            "source": "Alternative.me",
        }

    def get_asset_detail(self, symbol):
        """
        CoinGecko üzerinden fiyat, hacim ve yıllık aralık bilgisi getirir.
        """
        try:
            coin_id = self._resolve_coin_id(symbol)
            if not coin_id:
                return {
                    "symbol": self._normalize_symbol(symbol),
                    "data_status": "unavailable",
                    "source": "CoinGecko",
                }

            cache_key = f"coingecko_detail_{coin_id}"
            cached = cache.get(cache_key)
            if cached:
                return cached

            detail = self._request_json(
                f"/coins/{coin_id}",
                {
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
            market = detail.get("market_data", {})
            yearly_prices = [
                float(point[1])
                for point in self._get_market_chart(coin_id, 365).get("prices", [])
                if len(point) >= 2 and point[1] is not None
            ]
            result = {
                "id": coin_id,
                "symbol": self._normalize_symbol(symbol),
                "name": detail.get("name") or self._normalize_symbol(symbol),
                "category": "crypto",
                "price": float(market.get("current_price", {}).get("usd") or 0),
                "change_percent": float(
                    market.get("price_change_percentage_24h") or 0
                ),
                "volume": float(market.get("total_volume", {}).get("usd") or 0),
                "market_cap": float(market.get("market_cap", {}).get("usd") or 0),
                "high_24h": float(market.get("high_24h", {}).get("usd") or 0),
                "low_24h": float(market.get("low_24h", {}).get("usd") or 0),
                "high_52w": max(yearly_prices) if yearly_prices else 0,
                "low_52w": min(yearly_prices) if yearly_prices else 0,
                "image": detail.get("image", {}).get("large"),
                "currency": "USD",
                "source": "CoinGecko",
            }
            cache.set(cache_key, result, ttl_seconds=900)
            return result

        except Exception as e:
            print(f"Asset Detail Error ({symbol}): {e}")
            return {
                "symbol": self._normalize_symbol(symbol),
                "data_status": "unavailable",
                "source": "CoinGecko",
            }

    def get_history(self, symbol, period="1mo", interval="1d"):
        """
        CoinGecko üzerinden ücretsiz tarihsel fiyat verisi getirir.
        """
        cache_key = f"coingecko_history_{self._normalize_symbol(symbol)}_{period}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            coin_id = self._resolve_coin_id(symbol)
            if not coin_id:
                return []

            days = self.PERIOD_DAYS.get(period, 30)
            chart = self._get_market_chart(coin_id, days)
            prices = chart.get("prices", [])
            volumes = chart.get("total_volumes", [])
            formatted = []
            for index, point in enumerate(prices):
                if len(point) < 2 or point[1] is None:
                    continue
                price = float(point[1])
                volume = (
                    float(volumes[index][1])
                    if index < len(volumes) and len(volumes[index]) >= 2
                    else 0.0
                )
                formatted.append({
                    "date": datetime.fromtimestamp(
                        point[0] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "close": price,
                    "high": price,
                    "low": price,
                    "open": price,
                    "volume": volume,
                    "source": "CoinGecko",
                })

            cache.set(cache_key, formatted, ttl_seconds=900)
            return formatted
        except Exception as e:
            print(f"Crypto History Error ({symbol}): {e}")
        return []

crypto_service = CryptoService()
