import requests
from utils.cache import cache
from services.settings_service import settings_service

class FmpService:
    def __init__(self):
        self.base_url = "https://financialmodelingprep.com/api/v3"
        # 1 saatlik liste cache'i (Listeler çok sık değişmez)
        self.LIST_TTL = 3600 
        # 5 dakikalık fiyat cache'i (Limit 250 olduğu için her saniye soramayız)
        self.PRICE_TTL = 300 

    @property
    def api_key(self):
        return settings_service.get_value("FMP_API_KEY")

    def get_stocks_dynamic(self):
        """
        Statik liste yerine, borsadaki en popüler hisseleri dinamik çeker (Score Modeli).
        1. BIST (Istanbul) -> Top 30 (Market Cap)
        2. NASDAQ/NYSE -> Top 20 (Teknoloji Devleri)
        """
        cache_key = "fmp_dynamic_stocks_v1"
        cached = cache.get(cache_key)
        if cached: return cached

        all_stocks = []

        # 1. BIST Güzellikleri (Turkey)
        # exchange=IST (FMP'de Istanbul kodu IST veya OTHERS olabilir, bazen Euronext. 
        # Garanti olması için 'stock-screener' kullanıyoruz, country='TR' filtresi güvenli.)
        bist_data = self._fetch_screener(limit=30, country="TR")
        all_stocks.extend(bist_data)

        # 2. Global Devler (US)
        # Sadece Mega-Cap (Piyasa değeri çok yüksek) olanları al
        us_data = self._fetch_screener(limit=20, country="US", marketCapMoreThan=100000000000)
        all_stocks.extend(us_data)

        # 3. Sıralama (Score Modeli: Hacim)
        # User isteği: Hacime göre sırala
        all_stocks = bist_data + us_data
        
        # --- FALLBACK ---
        if not all_stocks:
            fallback_symbols = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", # US Tech
                "THYAO.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS", "ASELS.IS", # BIST
                "KCHOL.IS", "BIMAS.IS", "TUPRS.IS", "SISE.IS", "SAHOL.IS" 
            ]
            all_stocks = self._fetch_quotes_batch(fallback_symbols)
        # ----------------

        sorted_stocks = sorted(
            all_stocks, 
            key=lambda x: x.get('volume', 0) or 0, 
            reverse=True
        )

        cache.set(cache_key, sorted_stocks, ttl_seconds=self.LIST_TTL)
        return sorted_stocks

    def get_history(self, symbol, period="1mo"):
        """
        FMP Tarihsel Veri (Charts İçin)
        Endpoint: /historical-price-full/{symbol}
        Limit: Ücretsiz tier için kısıtlı olabilir (son 5 yıl genelde açık)
        """
        if not self.api_key:
            return []

        # Cache süresi uzun tutulmalı (Limit koruması)
        cache_key = f"fmp_history_{symbol}_{period}"
        cached = cache.get(cache_key)
        if cached: return cached

        try:
            # FMP Sembol temizliği (THYAO -> THYAO.IS gerekir mi? FMP genelde .IS ister)
            # App sembolü standardımız: THYAO (ama FMP .IS ister)
            fmp_symbol = symbol
            if not any(x in symbol for x in [".", "USD", "="]) and len(symbol) <= 5:
                 # Basit heuristik: BIST hissesi ise ve uzantısı yoksa ekle
                 # Ama global hisse (AAPL) ise ekleme.
                 # En garantisi: get_quote içinde raw_symbol dönüyorduk, onu kullanmak lazım ama burada symbol string geliyor.
                 # Şimdilik popüler BIST kontrolü:
                 if symbol in ["THYAO", "GARAN", "AKBNK", "EREGL", "ASELS", "BIMAS"]:
                     fmp_symbol = f"{symbol}.IS"

            # Timeseries endpoint
            url = f"{self.base_url}/historical-price-full/{fmp_symbol}?apikey={self.api_key}&serietype=line"
            if period == "1d": # Intraday paralıdır, günlük dönelim
                pass # Default daily
            
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                historical = data.get("historical", [])
                
                # Formatla: [{date:..., close:...}]
                formatted = []
                for item in historical[:100]: # Son 100 gün yeterli (Grafik performansı için)
                    formatted.append({
                        "date": item["date"], # FMP "YYYY-MM-DD" döner
                        "open": item.get("open"),
                        "high": item.get("high"),
                        "low": item.get("low"),
                        "close": item.get("close"),
                        "volume": item.get("volume")
                    })
                
                # FMP veriyi tersten (En yeni en üstte) verebilir, grafiği bozmamak için tarih sırasına sok
                formatted.sort(key=lambda x: x["date"])
                
                cache.set(cache_key, formatted, ttl_seconds=14400) # 4 Saat cache
                return formatted
            return []
        except Exception as e:
            print(f"FMP History Error: {e}")
            return []

    def get_commodities(self):
        """Emtia Listesi (Quote Endpoint üzerinden Batch)"""
        # Altın, Gümüş, Petrol, Doğalgaz
        symbols = ["GCUSD", "SIUSD", "ZGUSD", "CLUSD", "NGUSD", "HGUSD"] # FMP Sembolleri
        return self._fetch_quotes_batch(symbols)

    def get_forex(self):
        """Döviz Kurları (Forex Endpoint)"""
        symbols = ["USDTRY", "EURTRY", "GBPTRY", "EURUSD", "GBPUSD"]
        return self._fetch_quotes_batch(symbols)

    def get_quote(self, symbol):
        """Tekil Sembol Verisi (Yedekli Yapı İçin)"""
        res = self._fetch_quotes_batch([symbol])
        if res: return res[0]
        return None

    def _fetch_screener(self, limit=20, country=None, marketCapMoreThan=None):
        """
        Hisse Tarayıcı (Screener): Dinamik liste oluşturur.
        """
        if not self.api_key:
            return []
        try:
            url = f"{self.base_url}/stock-screener?limit={limit}&apikey={self.api_key}"
            if country: url += f"&country={country}"
            if marketCapMoreThan: url += f"&marketCapMoreThan={marketCapMoreThan}"
            
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [self._map_fmp_to_app(item) for item in data]
            return []
        except Exception as e:
            print(f"FMP Screener Error: {e}")
            return []

    def _fetch_quotes_batch(self, symbols_list):
        """
        Batch Request: Virgülle ayırıp tek seferde sorar (1 Kredi harcar).
        """
        if not self.api_key:
            return []
        str_syms = ",".join(symbols_list)
        # Cache Check yapmıyoruz çünkü üst metodlar zaten cacheleyecek veya anlık gerekebilir.
        # Ama yine de 60sn cache koyabiliriz.
        
        try:
            url = f"{self.base_url}/quote/{str_syms}?apikey={self.api_key}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [self._map_fmp_to_app(item) for item in data]
            return []
        except Exception as e:
            print(f"FMP Batch Error: {e}")
            return []

    def _map_fmp_to_app(self, item):
        """FMP verisini bizim App formatına çevirir"""
        symbol = item.get('symbol', 'UNK')
        
        # BIST sembol düzeltmesi (THYAO.IS -> THYAO) - Frontend temiz görünsün
        clean_symbol = symbol.replace(".IS", "")
        
        return {
            "symbol": clean_symbol, # THYAO
            "raw_symbol": symbol,   # THYAO.IS (API için lazım olabilir)
            "name": item.get('companyName') or item.get('name') or clean_symbol,
            "price": float(item.get('price') or 0.0),
            "change_percent": float(item.get('changesPercentage') or 0.0),
            "volume": float(item.get('volume') or 0.0),
            "market_cap": float(item.get('marketCap') or 0.0),
            "high_24h": float(item.get('dayHigh') or 0.0),
            "low_24h": float(item.get('dayLow') or 0.0),
            "exchange": item.get('exchangeShortName', ''),
            "logo_url": f"https://financialmodelingprep.com/image-stock/{symbol}.png" 
            # FMP logosu bedavadır ve publictir.
        }

fmp_service = FmpService()
