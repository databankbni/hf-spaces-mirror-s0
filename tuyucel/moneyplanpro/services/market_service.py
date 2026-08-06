import re
import requests
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.cache import cache
from utils.network import SafeRequest
from services.twelve_data_service import twelve_data_service
from dotenv import load_dotenv

load_dotenv()

# --- PRO GÜNCELLEME SIKLIĞI (SANİYE) ---
TTL_MARKET = 60
# --------------------------------------

DATE_FMT_TR = '%d/%m/%Y'

TOP_FUND_CATALOG = {
    "TCD": "Tacirler Portföy Değişken Fon",
    "AFT": "Ak Portföy Yeni Teknolojiler Yabancı Hisse",
    "YAY": "Yapı Kredi Portföy Yeni Teknolojiler Yabancı Hisse",
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
    "MPK": "Mükafaat Portföy Katılım Fonu",
    "IIH": "İstanbul Portföy Üçüncü Hisse Senedi Fonu",
}

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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
        cache_key = "market_summary_live_only_v1"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Never manufacture a price. Missing providers remain absent so the
        # client can show an honest "data unavailable" state.
        res = {}
        
        try:
            self._update_from_mynet(res)
            self._update_from_yahoo(res)
            self._calculate_gram_gold_if_needed(res)
        except Exception as e:
            print(f"Error in get_market_summary: {e}")

        # Cache'le ve döndür
        cache.set(cache_key, res, ttl_seconds=TTL_MARKET)
        return res

    def _update_from_mynet(self, res):
        """Mynet verilerini al ve sonuç kümesini güncelle."""
        mynet_data = self._fetch_all_from_mynet()
        if mynet_data:
            for k, val in mynet_data.items():
                if val["price"] > 0:
                    res[k] = val

    def _update_from_yahoo(self, res):
        """Fill only missing summary fields from a live secondary source."""
        symbol_map = {
            "bist100": "XU100.IS",
            "dolar": "TRY=X",
            "euro": "EURTRY=X",
            "bitcoin": "BTC-USD",
            "ons_altin": "GC=F",
        }
        symbols_to_check = [
            (key, symbol)
            for key, symbol in symbol_map.items()
            if key not in res
        ]

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

    def _calculate_gram_gold_if_needed(self, res):
        """Gram Altın anlık hesaplamasını yap (Eğer Mynet'ten gelmediyse)."""
        if "gram_altin" not in res:
            u_p = res.get("dolar", {}).get("price")
            o_p = res.get("ons_altin", {}).get("price")
            if (
                isinstance(u_p, (int, float))
                and isinstance(o_p, (int, float))
                and u_p > 0
                and o_p > 0
            ):
                res["gram_altin"] = {
                    "price": round((o_p / 31.1035) * u_p, 2),
                    "change_percent": res["ons_altin"].get(
                        "change_percent", 0.0
                    ),
                    "source": (
                        "Calculated from Yahoo Finance USD/TRY and gold ounce"
                    ),
                }

    def _fetch_all_from_mynet(self):
        """Mynet ana sayfasındaki tüm verileri tek regex taramasıyla alır."""
        try:
            headers = {"User-Agent": DEFAULT_USER_AGENT}
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
                            "change_percent": float(change_str),
                            "source": "Mynet",
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
                "User-Agent": DEFAULT_USER_AGENT,
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
                        "change_percent": round(((p - pre) / pre * 100), 2),
                        "source": "Yahoo Finance",
                    }
        except Exception:
            pass
        return None

    def get_calendar(self, country_code: str = "ALL"):
        from database import get_db_connection
        from datetime import datetime
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query, params = self._build_calendar_query(country_code)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            conn.close()

            formatted = self._format_calendar_rows(rows)
            if (
                len(formatted) < 5
                and self._is_fxstreet_calendar_enabled()
            ):
                return self._apply_calendar_fallback(formatted, country_code)
            return formatted
        except Exception as e:
            print(f"Calendar DB Error: {e}")
            if self._is_fxstreet_calendar_enabled():
                return self._generate_fallback_calendar(country_code)
            return []

    @staticmethod
    def _is_fxstreet_calendar_enabled():
        """The unlicensed fallback stays inert until explicitly enabled."""
        from services.feature_flag_service import FeatureFlagService

        return FeatureFlagService.is_enabled_sync(
            "financial_calendar_fxstreet",
            default=False,
        )

    def _build_calendar_query(self, country_code):
        """Takvim sorgusunu ülke koduna göre inşa eder."""
        from datetime import datetime, timezone, timedelta
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
        return query, params

    def _format_calendar_rows(self, rows):
        """Veritabanı satırlarını API formatına dönüştürür."""
        from datetime import datetime
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
            
            flag_code = flag_map.get(row["country_id"], "us")
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
                "country_id": row["country_id"],
                "flag_url": flag_url,
                "currency": row["currency"]
            })
        return formatted

    def _apply_calendar_fallback(self, formatted, country_code):
        """Append the optional FXStreet fallback and sort the result."""
        from datetime import datetime

        formatted.extend(self._generate_fallback_calendar(country_code))

        def sort_key(item):
            try:
                return datetime.strptime(
                    f"{datetime.now().year} {item['date']} {item['time']}",
                    "%Y %d %B %H:%M",
                )
            except Exception:
                return datetime.now()

        formatted.sort(key=sort_key)
        return formatted

    def _generate_fallback_calendar(self, country_code):
        """
        Fetch FXStreet calendar data only when the dedicated release flag is on.

        This legacy web endpoint is intentionally disabled by default. It must
        not be enabled in production before API licensing and credentials are
        confirmed.
        """
        try:
            from datetime import datetime, timedelta

            start_date = datetime.now()
            end_date = start_date + timedelta(days=7)
            url = (
                "https://calendar-api.fxstreet.com/en/api/v1/eventDates/"
                f"{start_date.strftime('%Y-%m-%d')}/"
                f"{end_date.strftime('%Y-%m-%d')}"
            )
            headers = {
                "Accept": "application/json",
                "Origin": "https://www.fxstreet.com",
                "Referer": "https://www.fxstreet.com/",
                "User-Agent": "Mozilla/5.0",
            }

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"FXStreet API Error: {response.status_code}")
                return []

            events = []
            for item in response.json():
                event = self._parse_fxstreet_event(item, country_code)
                if event:
                    events.append(event)
            return events
        except Exception as error:
            print(f"FXStreet Integration Error: {error}")
            return []

    def _parse_fxstreet_event(self, item, filter_country):
        """Convert a single FXStreet event to the client calendar format."""
        from datetime import datetime, timedelta

        country_code = item.get("countryCode", "US")
        if (
            filter_country
            and filter_country.upper() != "ALL"
            and filter_country.upper() != country_code
        ):
            return None

        country_ids = {
            "US": 5,
            "TR": 63,
            "EU": 72,
            "EMU": 72,
            "GB": 12,
            "UK": 12,
            "DE": 4,
            "CA": 6,
            "JP": 37,
            "AU": 7,
            "CN": 51,
            "RU": 56,
        }
        months_tr = [
            "Ocak",
            "Şubat",
            "Mart",
            "Nisan",
            "Mayıs",
            "Haziran",
            "Temmuz",
            "Ağustos",
            "Eylül",
            "Ekim",
            "Kasım",
            "Aralık",
        ]
        date_value = item.get("dateUtc", "")
        if not date_value:
            return None

        try:
            event_time = (
                datetime.strptime(date_value, "%Y-%m-%dT%H:%M:%SZ")
                + timedelta(hours=3)
            )
            volatility = item.get("volatility", "LOW")
            impact = {
                "HIGH": "High",
                "MEDIUM": "Medium",
            }.get(volatility, "Low")
            return {
                "id": item.get("id"),
                "date": f"{event_time.day} {months_tr[event_time.month - 1]}",
                "time": event_time.strftime("%H:%M"),
                "title": item.get("name"),
                "impact": impact,
                "actual": str(item.get("actual") or ""),
                "forecast": str(item.get("consensus") or ""),
                "previous": str(item.get("previous") or ""),
                "unit": item.get("unit", ""),
                "country_id": country_ids.get(country_code, 0),
                "flag_url": (
                    f"https://flagcdn.com/w40/{country_code.lower()}.png"
                ),
                "currency": item.get("currencyCode", ""),
            }
        except Exception:
            return None

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
        """Fetches historical data from free sources (InvestPy and Yahoo)."""
        try:
            # 1. InvestPy Source
            history = self._get_history_from_investpy(symbol, period)
            if history:
                return history
        except Exception as e:
            print(f"InvestPy Error ({symbol}): {e}")

        # 2. Yahoo Finance Fallback
        return self._get_history_from_yahoo(symbol, period, interval)

    def _get_history_from_investpy(self, symbol, period):
        import investpy
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime(DATE_FMT_TR)
        days_back = self._get_days_back(period)
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
            df = self._fetch_currency_from_investpy(symbol, start_date, end_date)
        
        if df is not None and not df.empty:
            return [{
                "date": date.isoformat(), "open": float(row['Open']), "high": float(row['High']),
                "low": float(row['Low']), "close": float(row['Close']), "volume": float(row['Volume'])
            } for date, row in df.iterrows()]
        return None

    def _get_days_back(self, period):
        mapping = {"3mo": 90, "1y": 365, "5y": 365 * 5}
        return mapping.get(period, 30)

    def _fetch_currency_from_investpy(self, symbol, start_date, end_date):
        import investpy
        cross = symbol
        if symbol == "USD": cross = "USD/TRY"
        elif symbol == "EUR": cross = "EUR/TRY"
        elif symbol == "GBP": cross = "GBP/TRY"
        try:
            return investpy.get_currency_cross_historical_data(currency_cross=cross, from_date=start_date, to_date=end_date)
        except (ValueError, RuntimeError, requests.exceptions.RequestException):
            return None

    def _get_history_from_yahoo(self, symbol, period, interval):
        try:
            import yfinance as yf
            y_sym = self._get_yahoo_symbol(symbol)
            df = yf.Ticker(y_sym).history(period=period, interval=interval)
            if not df.empty:
                return [{
                    "date": date.isoformat(), "open": float(row['Open']), "high": float(row['High']),
                    "low": float(row['Low']), "close": float(row['Close']), "volume": float(row['Volume'])
                } for date, row in df.iterrows()]
        except (ImportError, ValueError, RuntimeError, requests.exceptions.RequestException):
            pass
        return []

    def get_asset_detail(self, symbol):
        if self._is_tefas_fund(symbol):
            tefas_data = self._get_tefas_data(symbol)
            if tefas_data: return tefas_data
            
        from services.ta_service import ta_service

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
        except Exception: pass

        ta_data = ta_service.get_analysis(symbol)
        if ta_data:
            return {
                "symbol": symbol, "name": symbol, "price": ta_data.get("price", 0.0),
                "change_percent": ta_data.get("change", 0.0), "volume": ta_data.get("volume", 0),
                "high_24h": ta_data.get("high", 0), "low_24h": ta_data.get("low", 0),
                "open_24h": ta_data.get("open", 0), "source": "TradingView TA"
            }
        return {"symbol": symbol, "data_status": "unavailable"}

    def _fetch_tefas_direct(self, symbol, start_date=None, timeout=10):
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
                except Exception:
                    try: d_start = datetime.strptime(start_date, DATE_FMT_TR)
                    except Exception: pass
            d_end = datetime.now()
            payload = {
                "fontip": "YAT", "sfontip": "", "bastarih": d_start.strftime("%d.%m.%Y"),
                "bittarih": d_end.strftime("%d.%m.%Y"), "fonkod": symbol.upper()
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
                "Origin": "https://www.tefas.gov.tr",
                "User-Agent": DEFAULT_USER_AGENT,
                "X-Requested-With": "XMLHttpRequest"
            }
            resp = requests.post(url, data=payload, headers=headers, timeout=timeout)
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
                 except Exception: pass
             result = crawler.fetch(start=start_date, name=symbol, columns=["code", "date", "price"])
             if result is not None and not result.empty:
                 df = result.copy()
                 df['date'] = pd.to_datetime(df['date'])
                 df.set_index('date', inplace=True)
                 df.rename(columns={'price': 'Close'}, inplace=True)
                 for col in ['Open', 'High', 'Low']: df[col] = df['Close']
                 return df
        except Exception: pass
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
            except Exception: pass
        except Exception: pass
        return None

    def _get_tefas_data(self, symbol, direct_only=False):
        from datetime import datetime, timedelta
        start_date_limit = (datetime.now() - timedelta(days=7)).strftime(DATE_FMT_TR)
        if direct_only:
            df = self._fetch_tefas_direct(
                symbol,
                start_date=start_date_limit,
                timeout=4,
            )
        else:
            df = self._fetch_fund_from_investpy(
                symbol,
                start_date=start_date_limit,
            )

        full_name = TOP_FUND_CATALOG.get(
            symbol.upper(),
            f"{symbol} Yatırım Fonu",
        )

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
            except Exception:
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
        
        # Crypto handling (Yahoo needs -USD suffix)
        crypto_common = ["BTC", "ETH", "SOL", "ADA", "XRP", "DOT", "DOGE", "AVAX"]
        if s in crypto_common: return f"{s}-USD"
        if s == "BTCUSD": return "BTC-USD"
        
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
        except Exception: return ta_results or []

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
        except Exception: pass

        if ta_data:
            clean_tr = [s.replace(".IS", "") for s in tr_stocks]
            for item in ta_data:
                sym = item.get("symbol")
                if sym in tr_stocks or sym in clean_tr: item["country"] = "Turkey"
                elif sym in us_stocks: item["country"] = "USA"
                elif sym in de_stocks: item["country"] = "Germany"
                elif sym in uk_stocks: item["country"] = "UK"
                else: item["country"] = "Global"
        
        return [
            item
            for item in (ta_data or [])
            if item.get("price", 0) > 0
        ]

    def get_commodity_markets(self):
        cache_key = "commodity_markets_live_only_v1"
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
        
        live_data = [item for item in ta_data if item.get("price", 0) > 0]
        cache.set(cache_key, live_data, ttl_seconds=300)
        return live_data

    def get_etf_markets(self):
        from services.ta_service import ta_service
        symbols = ["SPY", "QQQ", "VOO", "GLD", "SLV", "VTI", "IVV", "ARKK"]
        return [
            item
            for item in ta_service.get_multiple_analysis(symbols)
            if item.get("price", 0) > 0
        ]

    def get_bond_markets(self):
        from services.ta_service import ta_service
        symbols = ["TLT", "BND", "AGG", "SHY", "IEF", "LQD", "HYG"]
        return [
            item
            for item in ta_service.get_multiple_analysis(symbols)
            if item.get("price", 0) > 0
        ]

    def get_top_funds(self):
        cache_key = "tefas_top_funds_live_only_v1"
        cached = cache.get(cache_key)
        if cached:
            return cached

        symbols = list(TOP_FUND_CATALOG)
        live_results = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_sym = {
                executor.submit(self._get_tefas_data, symbol, True): symbol
                for symbol in symbols
            }
            for future in as_completed(future_to_sym):
                symbol = future_to_sym[future]
                try:
                    result = future.result()
                    if result and result.get("price", 0) > 0:
                        live_results[symbol] = result
                except Exception:
                    pass

        results = [
            live_results[symbol]
            for symbol in symbols
            if symbol in live_results
        ]
        cache.set(cache_key, results, ttl_seconds=900)
        return results

    def _fetch_batch_details(self, symbols):
        results = []
        with ThreadPoolExecutor(max_workers=1) as executor:
            future_to_sym = {executor.submit(self.get_asset_detail, sym): sym for sym in symbols}
            for future in future_to_sym:
                try:
                    res = future.result()
                    if res and res.get("price", 0) > 0: results.append(res)
                except Exception: pass
        return results

market_provider = MarketDataProvider()
