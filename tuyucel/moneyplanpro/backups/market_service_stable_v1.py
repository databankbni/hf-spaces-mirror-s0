import re
import requests
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor
from utils.cache import cache
from utils.network import SafeRequest
from services.twelve_data_service import twelve_data_service
from dotenv import load_dotenv

load_dotenv()

# --- PRO GÜNCELLEME SIKLIĞI (SANİYE) ---
TTL_MARKET = 60
# --------------------------------------

DATE_FMT_TR = '%d/%m/%Y'

# Kullanıcının sağladığı "Gerçekçi Fallback" değerleri (Ocak 2026 Projeksiyonu/Güncel)
FALLBACK_DATA = {
    "bist100": {"price": 12200.0, "change_percent": 0.5},
    "dolar": {"price": 43.04, "change_percent": 0.1},
    "euro": {"price": 50.09, "change_percent": -0.05},
    "bitcoin": {"price": 90000.0, "change_percent": 1.2},
    "gram_altin": {"price": 4500.0, "change_percent": 0.3},
    "ons_altin": {"price": 3250.0, "change_percent": 0.2} # Ons Altın tahmini
}

class MarketDataProvider:
    def __init__(self):
        self.mynet_url = "https://finans.mynet.com/"
        self.yahoo_base = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def get_market_summary(self):
        """
        %100 Dinamik ve Hibrit Yaklaşım: 
        1. Mynet (BIST, TR Varlıklar - En hızlı)
        2. Yahoo (Global Varlıklar - Fallback)
        3. Fallback (Sıfır dönmemesi için gerçekçi veriler)
        """
        cache_key = "market_summary_ultimate_v3"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Başlangıçta fallback değerlerini kopyala
        res = {k: v.copy() for k, v in FALLBACK_DATA.items()}
        
        try:
            # Tüm verileri tek bir Mynet isteği ile çekmeye çalış (En verimli yol)
            mynet_data = self._fetch_all_from_mynet()
            if mynet_data:
                for k in mynet_data:
                    if mynet_data[k]["price"] > 0:
                        res[k] = mynet_data[k]
            
            # Eğer bazı veriler hala 0 veya güncellenmemişse global olanları Yahoo'dan dene
            symbols_to_check = []
            if res["bitcoin"]["price"] == FALLBACK_DATA["bitcoin"]["price"]: symbols_to_check.append(("bitcoin", "BTC-USD"))
            if res["ons_altin"]["price"] == FALLBACK_DATA["ons_altin"]["price"]: symbols_to_check.append(("ons_altin", "GC=F"))
            
            if symbols_to_check:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = {executor.submit(self._fetch_yahoo, sym): key for key, sym in symbols_to_check}
                    for future in futures:
                        key = futures[future]
                        try:
                            val = future.result()
                            if val and val["price"] > 0:
                                res[key] = val
                        except Exception:
                            pass

            # Gram Altın anlık hesaplama (Eğer Mynet'ten gelmediyse)
            if res["gram_altin"]["price"] == FALLBACK_DATA["gram_altin"]["price"]:
                u_p = res["dolar"]["price"]
                o_p = res["ons_altin"]["price"]
                if u_p > 0 and o_p > 0:
                    res["gram_altin"] = {
                        "price": round((o_p / 31.1035) * u_p, 2),
                        "change_percent": res["ons_altin"]["change_percent"]
                    }

        except Exception as e:
            print(f"Error in get_market_summary: {e}")

        # Cache'le ve döndür
        cache.set(cache_key, res, ttl_seconds=TTL_MARKET)
        return res

    def _fetch_all_from_mynet(self):
        """Mynet ana sayfasındaki tüm verileri tek regex taramasıyla alır."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            resp = requests.get(self.mynet_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            
            html = resp.text
            extracted = {}
            
            mappings = [
                ("XU100", "bist100"),
                ("USDTRY", "dolar"),
                ("EURTRY", "euro"),
                ("GAUTRY", "gram_altin"),
                ("BTCUSD", "bitcoin")
            ]
            
            for mynet_id, local_key in mappings:
                p_match = re.search(fr'dynamic-price-{mynet_id}[^>]*>([^<]+)</span>', html)
                c_match = re.search(fr'dynamic-direction-{mynet_id}[^>]*>([^<]+)</span>', html)
                
                if p_match:
                    price_str = p_match.group(1).replace(".", "").replace(",", ".").replace("%", "").strip()
                    change_str = "0"
                    if c_match:
                        change_str = c_match.group(1).replace("%", "").replace(",", ".").strip()
                    
                    try:
                        extracted[local_key] = {
                            "price": float(price_str),
                            "change_percent": float(change_str)
                        }
                    except Exception:
                        pass
            
            return extracted
        except Exception as e:
            print(f"Mynet fetch error: {e}")
            return None

    def _fetch_yahoo(self, symbol):
        """Yahoo Finance API (Fallback)"""
        try:
            url = f"{self.yahoo_base}{symbol}?interval=1m&range=1d"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                meta = data['chart']['result'][0]['meta']
                p = meta.get('regularMarketPrice')
                pre = meta.get('previousClose')
                
                if p and pre:
                    return {
                        "price": round(p, 2),
                        "change_percent": round(((p - pre) / pre * 100), 2)
                    }
        except Exception:
            pass
        return None

    def get_calendar(self, country_code: str = "ALL"):
        from database import get_db_connection
        from datetime import datetime, timezone, timedelta
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            tz_tr = timezone(timedelta(hours=3))
            now_tr = datetime.now(tz_tr)
            start_of_day = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
            now_str = start_of_day.strftime('%Y-%m-%d %H:%M:%S')
            
            query = "SELECT * FROM calendar_events WHERE date_time >= ?"
            params = [now_str]

            if country_code and country_code.upper() != "ALL":
                id_map = {
                    "TR": [63, 32], "US": [5], "USA": [5], "EU": [72], "GBP": [12],
                    "GB": [12], "DE": [4, 17], "CA": [6], "JP": [37], "AU": [7, 25],
                    "NZ": [35], "CH": [110, 39, 36]
                }
                target_ids = id_map.get(country_code.upper())
                if target_ids:
                    placeholders = ",".join(["?"] * len(target_ids))
                    query += f" AND country_id IN ({placeholders})"
                    params.extend(target_ids)
            
            query += " ORDER BY date_time ASC LIMIT 100"
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            conn.close()
            
            formatted = []
            months_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                       "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
            
            flag_map = {
                5: "us", 63: "tr", 32: "tr", 72: "eu", 12: "gb", 4: "de", 6: "ca",
                37: "jp", 7: "au", 35: "nz", 110: "ch", 39: "ch", 36: "ch", 51: "cn",
                160: "in", 14: "in", 17: "de", 25: "au", 10: "it", 22: "fr", 26: "es",
                21: "nl", 56: "ru"
            }

            for row in rows:
                dt = datetime.fromisoformat(row["date_time"])
                formatted_date = f"{dt.day} {months_tr[dt.month-1]}"
                
                c_id = row["country_id"]
                flag_code = flag_map.get(c_id, "us")
                flag_url = f"https://flagcdn.com/w40/{flag_code}.png"

                formatted.append({
                    "id": row["id"],
                    "date": formatted_date,
                    "time": dt.strftime('%H:%M'),
                    "title": row["title"],
                    "impact": row["impact"],
                    "actual": row["actual"],
                    "forecast": row["forecast"],
                    "previous": row["previous"],
                    "unit": row["unit"],
                    "country_id": c_id,
                    "flag_url": flag_url,
                    "currency": row["currency"]
                })
            return formatted
        except Exception as e:
            print(f"Calendar DB Error: {e}")
            return []

    def save_calendar_events(self, events: list):
        from database import get_db_connection
        from datetime import datetime
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            for ev in events:
                dt_str = ev.get("date_time") or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO calendar_events 
                    (event_id, date_time, country_id, currency, title, impact, actual, forecast, previous, unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(ev.get("event_id", "")), dt_str, ev.get("country_id", 0),
                    ev.get("currency", ""), ev.get("short_name") or ev.get("title") or "Olay",
                    ev.get("importance") or ev.get("impact") or "Medium",
                    ev.get("actual", "-"), ev.get("forecast", "-"),
                    ev.get("previous", "-"), ev.get("unit", "")
                ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving events: {e}")
            return False
    
    def get_history(self, symbol, period="1mo", interval="1d"):
        try:
            import investpy
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime(DATE_FMT_TR)
            days_back = 30
            if period == "3mo": days_back = 90
            elif period == "1y": days_back = 365
            elif period == "5y": days_back = 365 * 5
            start_date = (datetime.now() - timedelta(days=days_back)).strftime(DATE_FMT_TR)

            df = None
            if ".IS" in symbol or symbol in ["THYAO", "GARAN", "AKBNK", "EREGL"]:
                clean = symbol.replace(".IS", "")
                df = investpy.get_stock_historical_data(stock=clean, country='turkey', from_date=start_date, to_date=end_date)
            elif self._is_tefas_fund(symbol):
                df = self._fetch_fund_from_investpy(symbol, start_date, end_date)
            elif symbol in ["AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "NVDA", "META"]:
                df = investpy.get_stock_historical_data(stock=symbol, country='united states', from_date=start_date, to_date=end_date)
            elif "TRY" in symbol or symbol in ["USD", "EUR", "GBP", "CHF", "JPY"]: 
                 cross = symbol
                 if symbol == "USD": cross = "USD/TRY"
                 elif symbol == "EUR": cross = "EUR/TRY"
                 elif symbol == "GBP": cross = "GBP/TRY"
                 try:
                     df = investpy.get_currency_cross_historical_data(currency_cross=cross, from_date=start_date, to_date=end_date)
                 except: pass
            
            if df is not None and not df.empty:
                return [{
                    "date": date.isoformat(), "open": float(row['Open']), "high": float(row['High']),
                    "low": float(row['Low']), "close": float(row['Close']), "volume": float(row['Volume'])
                } for date, row in df.iterrows()]
        except Exception as e:
            print(f"InvestPy Error ({symbol}): {e}")

        from services.fmp_service import fmp_service
        history = fmp_service.get_history(symbol, period)
        if history: return history
        
        try:
            import yfinance as yf
            y_sym = self._get_yahoo_symbol(symbol)
            df = yf.Ticker(y_sym).history(period=period, interval=interval)
            if not df.empty:
                return [{
                    "date": date.isoformat(), "open": float(row['Open']), "high": float(row['High']),
                    "low": float(row['Low']), "close": float(row['Close']), "volume": float(row['Volume'])
                } for date, row in df.iterrows()]
        except: pass
        return []

    def get_asset_detail(self, symbol):
        if self._is_tefas_fund(symbol):
            tefas_data = self._get_tefas_data(symbol)
            if tefas_data: return tefas_data
            
        from services.fmp_service import fmp_service
        from services.ta_service import ta_service
        fmp_data = fmp_service.get_quote(symbol)
        if fmp_data and fmp_data.get("price", 0) > 0: return fmp_data

        try:
            import yfinance as yf
            y_sym = self._get_yahoo_symbol(symbol)
            tk = yf.Ticker(y_sym)
            fi = tk.fast_info
            price = float(fi.last_price) if hasattr(fi, 'last_price') else 0.0
            if price > 0:
                info = tk.info
                return {
                    "symbol": symbol, "name": info.get('longName') or symbol, "price": price,
                    "change_percent": 0.0, "volume": info.get('volume', 0),
                    "market_cap": info.get('marketCap', 0), "high_24h": info.get('dayHigh', 0),
                    "low_24h": info.get('dayLow', 0), "high_52w": info.get('fiftyTwoWeekHigh', 0),
                    "low_52w": info.get('fiftyTwoWeekLow', 0), "description": info.get('longBusinessSummary', ""),
                    "logo_url": "", "currency": "USD"
                }
        except: pass

        ta_data = ta_service.get_analysis(symbol)
        if ta_data:
            return {
                "symbol": symbol, "name": symbol, "price": ta_data.get("price", 0.0),
                "change_percent": ta_data.get("change", 0.0), "volume": ta_data.get("volume", 0),
                "high_24h": ta_data.get("high", 0), "low_24h": ta_data.get("low", 0),
                "open_24h": ta_data.get("open", 0), "source": "TradingView TA"
            }
        return {"price": 0.0}

    def _fetch_tefas_direct(self, symbol, start_date=None):
        """
        TEFAS Resmi Sitesinden Direkt Veri Çekme (Libraryless Fallback)
        Endpoint: https://www.tefas.gov.tr/api/DB/BindHistoryInfo
        """
        try:
            url = "https://www.tefas.gov.tr/api/DB/BindHistoryInfo"
            from datetime import datetime
            d_start = datetime.now()
            if start_date:
                try: d_start = datetime.strptime(start_date, "%Y-%m-%d")
                except:
                    try: d_start = datetime.strptime(start_date, DATE_FMT_TR)
                    except: pass
            d_end = datetime.now()
            payload = {
                "fontip": "YAT", "sfontip": "", "bastarih": d_start.strftime("%d.%m.%Y"),
                "bittarih": d_end.strftime("%d.%m.%Y"), "fonkod": symbol.upper()
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
                "Origin": "https://www.tefas.gov.tr",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }
            resp = requests.post(url, data=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                     import pandas as pd
                     df = pd.DataFrame(data["data"])
                     if df['TARIH'].astype(str).str.contains("/Date").any():
                         df['date'] = df['TARIH'].astype(str).str.extract(r'(\d+)').astype(float) / 1000
                         df['date'] = pd.to_datetime(df['date'], unit='s')
                     else:
                         df['date'] = pd.to_datetime(df['TARIH'], format='%d.%m.%Y', errors='coerce')
                     df.set_index('date', inplace=True)
                     df.rename(columns={'FIYAT': 'Close'}, inplace=True)
                     return df
        except Exception as e:
            print(f"Direct TEFAS Fetch Error ({symbol}): {e}")
        return None

    def _fetch_from_tefas_crawler(self, symbol, start_date=None):
        df_direct = self._fetch_tefas_direct(symbol, start_date)
        if df_direct is not None: return df_direct
        try:
             from tefas import Crawler
             import pandas as pd
             from datetime import datetime, timedelta
             crawler = Crawler()
             if not start_date:
                 start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
             else:
                 try:
                    d = datetime.strptime(start_date, DATE_FMT_TR)
                    start_date = d.strftime("%Y-%m-%d")
                 except: pass
             result = crawler.fetch(start=start_date, name=symbol, columns=["code", "date", "price"])
             if result is not None and not result.empty:
                 df = result.copy()
                 df['date'] = pd.to_datetime(df['date'])
                 df.set_index('date', inplace=True)
                 df.rename(columns={'price': 'Close'}, inplace=True)
                 for col in ['Open', 'High', 'Low']: df[col] = df['Close']
                 return df
        except: pass
        return None

    def _fetch_fund_from_investpy(self, symbol, start_date=None, end_date=None):
        df_crawler = self._fetch_from_tefas_crawler(symbol, start_date)
        if df_crawler is not None: return df_crawler
        try:
            import investpy
            from datetime import datetime, timedelta
            try:
                search_results = investpy.search_quotes(text=symbol, products=['funds'], countries=['turkey'], n_results=1)
                if search_results:
                    if not start_date or not end_date:
                        end_date = datetime.now().strftime(DATE_FMT_TR)
                        start_date = (datetime.now() - timedelta(days=7)).strftime(DATE_FMT_TR)
                    return search_results.retrieve_historical_data(from_date=start_date, to_date=end_date)
            except: pass
        except: pass
        return None

    def _get_tefas_data(self, symbol):
        from datetime import datetime, timedelta
        start_date_limit = (datetime.now() - timedelta(days=7)).strftime(DATE_FMT_TR)
        df = self._fetch_fund_from_investpy(symbol, start_date=start_date_limit)
        
        # Fon isimleri için manuel mapping (Premium görünüm için)
        FUND_NAME_MAP = {
            "TCD": "Tacirler Portföy Değişken Fon",
            "AFT": "Ak Portföy Yeni Teknolojiler Yabancı Hisse",
            "YAY": "Yapı Kredi Por. Yeni Teknolojiler Yab. Hisse",
            "TTE": "İş Portföy BIST Teknoloji Ağırlıklı Hisse",
            "IPB": "İstanbul Portföy Birinci Değişken Fon",
            "AES": "Ak Portföy Petrol Yabancı BYF Fon Sepeti",
            "IDH": "İş Portföy İhracatçı Şirketler Hisse Senedi",
            "KZL": "Kuveyt Türk Portföy Altın Katılım Fonu",
            "MAC": "Marmara Capital Portföy Hisse Senedi Fonu",
            "GMR": "Global MD Portföy Birinci Hisse Senedi Fonu",
            "TCA": "Ziraat Portföy Altın Katılım Fonu",
            "ZJ1": "Ziraat Portföy Birinci Kira Sertifikası Katılım",
            "HMB": "HSBC Portföy Çoklu Varlık Değişken Fon",
            "MPK": "Mükafaat Portföy Katılım Katılım Fonu",
            "IIH": "İstanbul Portföy Üçüncü Hisse Senedi Fonu",
            "KUB": "Kuveyt Türk Sürdürülebilirlik Katılım Fonu",
            "GSP": "Azimut Portföy Sky Hisse Senedi Fonu",
            "HKH": "Hedef Portföy Katılım Hisse Senedi Fonu",
            "TI3": "İş Portföy İşte Kadın Hisse Senedi Fonu",
            "DBH": "Deniz Portföy Eurobond (USD) Borçlanma Araçları"
        }
        
        full_name = FUND_NAME_MAP.get(symbol.upper(), f"{symbol} Yatırım Fonu")

        if df is not None and not df.empty:
            last_row = df.iloc[-1]
            ret_rate = 0.0
            if len(df) >= 2:
                prev_close = float(df.iloc[-2]['Close'])
                last_close = float(df.iloc[-1]['Close'])
                if prev_close > 0: ret_rate = ((last_close - prev_close) / prev_close) * 100
            return {
                "symbol": symbol,
                "code": symbol,
                "name": full_name,
                "title": full_name,
                "short_name": full_name,
                "price": float(last_row['Close']),
                "change_percent": round(ret_rate, 2),
                "daily_return": round(ret_rate, 2),
                "source": "TEFAS/Robust",
                "type": "Yatırım Fonu"
            }
        return None

    def _is_tefas_fund(self, symbol):
        cache_key = "tefas_fund_list"
        cached_list = cache.get(cache_key)
        if not cached_list:
            try:
                import investpy
                df_funds = investpy.get_funds(country='turkey')
                if df_funds is not None and not df_funds.empty:
                    cached_list = set(df_funds['symbol'].str.upper().tolist())
                    cache.set(cache_key, cached_list, ttl_seconds=86400)
            except:
                cached_list = {"TCD", "AFT", "YAY", "TTE", "IPB", "AES", "IDH", "KZL", "IPJ", 
                              "KUB", "TI3", "KRS", "PPF", "HKH", "AYA", "MAC", "GMR", "TCA", "ZJ1", "IIH"}
        return symbol in cached_list

    def _get_yahoo_symbol(self, symbol):
        s = symbol.upper().strip()
        if s == "BIST100" or s == "XU100": return "XU100.IS"
        if s == "USD": return "TRY=X"
        if s == "EUR": return "EURTRY=X"
        if s == "GBP": return "GBPTRY=X"
        if s == "GAU" or s == "GRAM_ALTIN": return "GC=F"
        if s == "ONS" or s == "ONS_ALTIN": return "GC=F"
        if s == "BRENT": return "BZ=F"
        tr_stocks = ["THYAO", "GARAN", "AKBNK", "EREGL", "ASELS", "SISE", "BIMAS"]
        if s in tr_stocks: return f"{s}.IS"
        return s

    def get_tcmb_currencies(self):
        symbols = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR"]
        from services.ta_service import ta_service
        ta_results = ta_service.get_multiple_analysis(symbols)
        has_zeros = any(item.get("price", 0) <= 0 for item in ta_results) if ta_results else True
        if not has_zeros and len(ta_results) == len(symbols): return ta_results
        try:
            from services.exchange_api_service import exchange_api_service
            api_rates = exchange_api_service.get_try_rates()
            if not ta_results: return api_rates or []
            api_map = {item["symbol"]: item for item in api_rates}
            final_results = []
            processed = set()
            for item in ta_results:
                sym = item["symbol"]
                if item.get("price", 0) <= 0 and sym in api_map: final_results.append(api_map[sym])
                else: final_results.append(item)
                processed.add(sym)
            for sym in symbols:
                if sym not in processed and sym in api_map: final_results.append(api_map[sym])
            return final_results
        except: return ta_results or []

    def get_stock_markets(self):
        from services.ta_service import ta_service
        tr_stocks = ["THYAO.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS", "ASELS.IS", "BIMAS.IS", 
                     "TUPRS.IS", "KCHOL.IS", "SISE.IS", "SAHOL.IS", "PETKM.IS", "FROTO.IS", "TOASO.IS", "TCELL.IS"]
        us_stocks = ["AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "NVDA", "META", "NFLX", "AMD", 
                     "INTC", "KO", "PEP", "MCD", "V", "MA", "JPM", "DIS", "BRK.B"]
        de_stocks = ["SAP", "SIE", "ALV", "DTE", "BMW", "VOW3", "BAS", "AIR", "DDAIF"]
        uk_stocks = ["SHEL", "HSBA", "AZN", "ULVR", "BP.", "BARC", "VOD", "LLOY", "NG."]
        all_symbols = tr_stocks + us_stocks + de_stocks + uk_stocks
        ta_data = ta_service.get_multiple_analysis(all_symbols)
        
        # Twelve Data Fallback for US Stocks
        try:
            from services.twelve_data_service import twelve_data_service
            top_us = ["AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "NVDA", "META", "NFLX"]
            td_data = twelve_data_service.get_quotes(top_us)
            if td_data:
                for item in ta_data:
                    sym = item.get("symbol")
                    if sym in td_data:
                        td_item = td_data[sym]
                        item["price"] = td_item["price"]
                        item["change_percent"] = td_item["change_percent"]
                        item["source"] = "TwelveData"
        except: pass

        if ta_data:
            clean_tr = [s.replace(".IS", "") for s in tr_stocks]
            for item in ta_data:
                sym = item.get("symbol")
                if sym in tr_stocks or sym in clean_tr: item["country"] = "Turkey"
                elif sym in us_stocks: item["country"] = "USA"
                elif sym in de_stocks: item["country"] = "Germany"
                elif sym in uk_stocks: item["country"] = "UK"
                else: item["country"] = "Global"
        
        return ta_data if ta_data else []

    def get_commodity_markets(self):
        cache_key = "commodity_markets_ultimate_v7"
        cached = cache.get(cache_key)
        if cached: return cached
        from services.ta_service import ta_service
        symbols = [
            "XAU/USD", "XAG/USD", "LCO/USD", "WTI/USD", "PLATINUM", "PALLADIUM", 
            "COPPER", "NATURAL_GAS", "CORN", "WHEAT", "SOYBEAN", 
            "COFFEE", "SUGAR", "COTTON"
        ] 
        ta_data = ta_service.get_multiple_analysis(symbols)
        
        # Twelve Data Fallback for Commodities
        has_zeros = any(item.get("price", 0) <= 0 for item in ta_data) if ta_data else True
        if has_zeros:
            missing = [s for s in symbols if not any(item["symbol"] == s and item.get("price", 0) > 0 for item in ta_data)]
            if missing:
                from services.twelve_data_service import twelve_data_service
                td_data = twelve_data_service.get_quotes(missing[:7])
                if td_data:
                    for i, item in enumerate(ta_data):
                        sym = item["symbol"]
                        if sym in td_data and item.get("price", 0) <= 0:
                            ta_data[i] = td_data[sym]
        
        cache.set(cache_key, ta_data, ttl_seconds=300)
        return ta_data if ta_data else []

    def get_etf_markets(self):
        from services.ta_service import ta_service
        symbols = ["SPY", "QQQ", "VOO", "GLD", "SLV", "VTI", "IVV", "ARKK"]
        return ta_service.get_multiple_analysis(symbols)

    def get_bond_markets(self):
        from services.ta_service import ta_service
        symbols = ["TLT", "BND", "AGG", "SHY", "IEF", "LQD", "HYG"]
        return ta_service.get_multiple_analysis(symbols)

    def get_top_funds(self):
        symbols = ["TCD", "AFT", "YAY", "TTE", "IPB", "AES", "IDH", "KZL", "MAC", "GMR", "TCA", "ZJ1", "HMB", "MPK", "IIH"]
        results = self._fetch_batch_details(symbols)
        return results if results else []

    def _fetch_batch_details(self, symbols):
        results = []
        with ThreadPoolExecutor(max_workers=1) as executor:
            future_to_sym = {executor.submit(self.get_asset_detail, sym): sym for sym in symbols}
            for future in future_to_sym:
                try:
                    res = future.result()
                    if res and res.get("price", 0) > 0: results.append(res)
                except: pass
        return results

market_provider = MarketDataProvider()
