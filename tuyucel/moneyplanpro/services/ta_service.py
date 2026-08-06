from tradingview_ta import TA_Handler, Interval, Exchange
from utils.cache import cache

class TradingViewService:
    def __init__(self):
        # 15 dakikalık cache (Analizler anlık değişmez)
        self.TTL = 900 

    def get_multiple_analysis(self, symbols):
        """
        Optimize Edilmiş Çoklu Analiz (Batch Request)
        Sembolleri screener'larına göre gruplayıp kütüphanenin 'get_multiple_analysis' fonksiyonunu kullanır.
        """
        from tradingview_ta import get_multiple_analysis as tv_batch_get
        
        # 1. Sembolleri Grupla
        groups = {
            "turkey": [],
            "america": [],
            "crypto": [],
            "forex": [],
            "cfd": [],
            "germany": [],
            "uk": []
        }
        
        symbol_map = {} 
        
        for sym in symbols:
            clean, screener, exchange = self._classify_symbol(sym)
            if screener in groups:
                formatted_sym = f"{exchange}:{clean}"
                groups[screener].append(formatted_sym)
                symbol_map[formatted_sym] = sym 
        
        results = []
        
        # 2. Her Grup İçin Batch İstek At
        for screener, sym_list in groups.items():
            if not sym_list: continue
            
            try:
                batch_res = tv_batch_get(
                    screener=screener,
                    interval=Interval.INTERVAL_1_DAY,
                    symbols=sym_list
                )
                
                if batch_res:
                    for clean_sym, analysis in batch_res.items():
                        orig_sym = symbol_map.get(clean_sym, clean_sym)
                        if analysis:
                            formatted = self._format_analysis(orig_sym, analysis)
                            if formatted: results.append(formatted)
                        # Missing provider data is omitted. A zero placeholder
                        # would be indistinguishable from a real market price.
                            
            except Exception as e:
                print(f"TA Batch Error ({screener}): {e}")

        results.sort(key=lambda x: x.get("volume", 0) or 0, reverse=True)
        return results

    def _classify_symbol(self, symbol):
        """Sembolü analiz eder: (CleanSymbol, Screener, Exchange)"""
        s = symbol.upper().strip()
        # Temiz sembol (Mapping için)
        c = s.replace(".IS", "").replace("USDT", "").replace("/TRY", "").replace("TRY", "")
        
        # 1. CRYPTO
        crypto_list = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "DOT", "LINK", "MATIC"]
        if c in crypto_list or "USDT" in s:
            return (s if s.endswith("USDT") else f"{c}USDT"), "crypto", "BINANCE"
            
        # 2. BIST (Turkey)
        if s.endswith(".IS") or s in ["XU100", "XU030", "GARAN", "THYAO", "ASELS", "EREGL", "SISE"]:
            return c, "turkey", "BIST"
            
        # 3. FOREX (Pairs like USD/TRY or USD)
        fx_list = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR"]
        if c in fx_list or "TRY" in s:
            return (f"{c}TRY" if "TRY" not in s else s), "forex", "FX_IDC"

        # 4. COMMODITIES / CFD (Special handling for metals and energy)
        # We use FX_IDC for XAU/XAG and common CFD names for others.
        commodities = {
            "XAU/USD": ("XAUUSD", "forex", "FX_IDC"),
            "XAG/USD": ("XAGUSD", "forex", "FX_IDC"),
            "LCO/USD": ("UKOIL", "cfd", "TVC"),
            "WTI/USD": ("USOIL", "cfd", "TVC"),
            "PLATINUM": ("PLATINUM", "cfd", "TVC"),
            "PALLADIUM": ("PALLADIUM", "cfd", "TVC"),
            "COPPER": ("COPPER", "cfd", "TVC"),
            "NATURAL_GAS": ("NATGAS", "cfd", "TVC"),
            "CORN": ("CORN", "cfd", "TVC"),
            "WHEAT": ("WHEAT", "cfd", "TVC"),
            "SOYBEAN": ("SOYBEAN", "cfd", "TVC"),
            "COFFEE": ("COFFEE", "cfd", "TVC"),
            "SUGAR": ("SUGAR", "cfd", "TVC"),
            "COTTON": ("COTTON", "cfd", "TVC"),
            "GOLD": ("GOLD", "cfd", "TVC"),
            "SILVER": ("SILVER", "cfd", "TVC")
        }
        
        if s in commodities:
            return commodities[s]
        if c in commodities:
            return commodities[c]
            
        # 5. GERMANY
        if s in ["SAP", "SIE", "ALV", "DTE", "BMW", "VOW3", "BAS", "AIR", "DDAIF"]:
            return s, "germany", "XETR"
            
        # 6. UK
        if s in ["SHEL", "HSBA", "AZN", "ULVR", "BP.", "BARC", "VOD", "LLOY", "NG."]:
            return s, "uk", "LSE"
            
        # 7. AMERICA (Stocks, ETFs, Bonds)
        nyse_list = ["KO", "PEP", "MCD", "V", "MA", "JPM", "DIS", "BRK.B", "SPY", "VOO", 
                     "GLD", "SLV", "VTI", "IVV", "AGG", "LQD", "HYG"]
        
        exchange = "NYSE" if s in nyse_list else "NASDAQ"
        return s, "america", exchange

    def _format_analysis(self, symbol, analysis):
        """Analysis objesini dict'e çevirir"""
        try:
            # Extract indicators safely
            indicators = analysis.indicators
            price = float(indicators.get("close") or 0.0)
            change = float(indicators.get("change") or 0.0)
            
            return {
                "symbol": symbol,
                "name": symbol, 
                "price": price,
                "change_percent": round(change, 2), # % Change
                "recommendation": (analysis.summary.get("RECOMMENDATION") or "NEUTRAL").upper(),
                "volume": float(indicators.get("volume") or 0.0),
                "market_cap": 0,
                "logo_url": f"https://s3-symbol-logo.tradingview.com/{symbol.lower()}.svg",
                "source": "TradingView Technical Analysis",
            }
        except Exception:
            return None

    def get_analysis(self, symbol):
        """Tekli Analiz (Eski Yöntem - Detay Sayfası İçin)"""
        cache_key = f"ta_analysis_v5_{symbol}"
        cached = cache.get(cache_key)
        if cached: return cached

        try:
            clean, screener, final_exchange = self._classify_symbol(symbol)
            
            handler = TA_Handler(
                symbol=clean,
                screener=screener,
                exchange=final_exchange,
                interval=Interval.INTERVAL_1_DAY
            )
            
            analysis = handler.get_analysis()
            
            result = {
                "symbol": symbol,
                "price": analysis.indicators.get("close"),
                "open": analysis.indicators.get("open"),
                "high": analysis.indicators.get("high"),
                "low": analysis.indicators.get("low"),
                "volume": analysis.indicators.get("volume"),
                "change": analysis.indicators.get("change"),
                "recommendation": analysis.summary.get("RECOMMENDATION"),
                "score": {
                    "buy": analysis.summary.get("BUY"),
                    "sell": analysis.summary.get("SELL"),
                    "neutral": analysis.summary.get("NEUTRAL")
                },
                "indicators": {
                    "rsi": analysis.indicators.get("RSI"),
                    "macd": analysis.indicators.get("MACD.macd"),
                    "ema20": analysis.indicators.get("EMA20"),
                },
                "timestamp": analysis.time.isoformat()
            }
            
            cache.set(cache_key, result, ttl_seconds=self.TTL)
            return result

        except Exception:
            return None

ta_service = TradingViewService()
