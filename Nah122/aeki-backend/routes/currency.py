"""
Currency & Gold Rates API
- Exchange rates: ExchangeRate-API (free tier, USD base)
- Gold prices: NBE (National Bank of Ethiopia) scraper
  https://nbe.gov.et/exchange/gold-purchasing-rate/
"""

from fastapi import APIRouter
from datetime import datetime
import requests
import os
from bs4 import BeautifulSoup

router = APIRouter()

EXCHANGE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "911b9d222d13b16a5087b4f6")

# Target currencies to show
TARGET_CURRENCIES = {
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
    "SAR": "Saudi Riyal",
    "AED": "UAE Dirham",
    "CNY": "Chinese Yuan",
    "JPY": "Japanese Yen",
}


@router.get("/rates")
def get_exchange_rates():
    """
    Live ETB exchange rates from ExchangeRate-API
    Source: https://exchangerate-api.com (free tier)
    API Key env: EXCHANGE_RATE_API_KEY
    """
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return {
                "error": f"Exchange rate API returned {response.status_code}",
                "rates": [],
                "timestamp": datetime.utcnow().isoformat()
            }

        data = response.json()

        if data.get("result") != "success":
            return {
                "error": data.get("error-type", "Unknown API error"),
                "rates": [],
                "timestamp": datetime.utcnow().isoformat()
            }

        rates = data["conversion_rates"]
        etb_rate = rates.get("ETB", 0)

        result = []
        for code, name in TARGET_CURRENCIES.items():
            if code in rates and rates[code] > 0:
                # How many ETB per 1 unit of this currency
                to_etb = (1 / rates[code]) * etb_rate
                result.append({
                    "code": code,
                    "name": name,
                    "rate_to_etb": round(to_etb, 2),
                    "usd_rate": round(rates[code], 4),
                })

        return {
            "base": "ETB",
            "rates": result,
            "usd_to_etb": round(etb_rate, 2),
            "last_updated": data.get("time_last_update_utc", ""),
            "source": "ExchangeRate-API",
            "source_url": "https://www.exchangerate-api.com",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "error": str(e),
            "rates": [],
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/gold")
def get_gold_rates():
    """
    Gold purchasing rates from National Bank of Ethiopia (NBE)
    Source: https://nbe.gov.et/exchange/gold-purchasing-rate/
    Scraped live from NBE website
    """
    try:
        url = "https://nbe.gov.et/exchange/gold-purchasing-rate/"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            return {
                "error": f"NBE website returned {response.status_code}",
                "rates": [],
                "applicable_date": "",
                "timestamp": datetime.utcnow().isoformat()
            }

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the applicable date
        applicable_date = ""
        date_elem = soup.find(string=lambda t: t and "Applicable on" in t)
        if date_elem:
            applicable_date = date_elem.strip().replace("Applicable on", "").strip()

        # Find the table
        table = soup.find("table")
        if not table:
            return {
                "error": "Could not find gold rate table on NBE website",
                "rates": [],
                "applicable_date": applicable_date,
                "timestamp": datetime.utcnow().isoformat()
            }

        rows = table.find_all("tr")
        gold_rates = []

        for row in rows[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) >= 4:
                try:
                    karat = cols[0].get_text(strip=True)
                    purity = cols[1].get_text(strip=True)
                    usd_gram = cols[2].get_text(strip=True).replace(",", "")
                    birr_gram = cols[3].get_text(strip=True).replace(",", "")

                    gold_rates.append({
                        "karat": int(karat) if karat.isdigit() else karat,
                        "purity_level": purity,
                        "usd_per_gram": float(usd_gram) if usd_gram else 0,
                        "birr_per_gram": float(birr_gram) if birr_gram else 0,
                    })
                except (ValueError, IndexError):
                    continue

        return {
            "applicable_date": applicable_date,
            "rates": gold_rates,
            "source": "National Bank of Ethiopia (NBE)",
            "source_url": "https://nbe.gov.et/exchange/gold-purchasing-rate/",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "error": str(e),
            "rates": [],
            "applicable_date": "",
            "timestamp": datetime.utcnow().isoformat()
        }


import clickhouse_connect
import logging

_logger = logging.getLogger(__name__)

TARGET_BANKS_LIST = [
    "Commercial Bank of Ethiopia",
    "Awash Bank",
    "Bank of Abyssinia",
    "Abay Bank",
    "Zemen Bank",
    "Buna Bank",
    "Nib International Bank",
    "Berhan Bank SC",
]

def _ch():
    from database.clickhouse_client import get_clickhouse_client
    return get_clickhouse_client().client


@router.get("/bank-rates")
def get_bank_exchange_rates():
    """
    Latest exchange rates for the 8 target Ethiopian banks.
    Sourced from daily scrape of banksethiopia.com.
    Returns rates grouped by bank, showing all currencies.
    """
    try:
        client = _ch()
        # Get the latest date available
        latest = client.query(
            "SELECT max(date) FROM bank_exchange_rates"
        ).result_rows
        if not latest or not latest[0][0]:
            return {"banks": [], "date": None, "source": "banksethiopia.com", "timestamp": datetime.utcnow().isoformat()}

        latest_date = latest[0][0]
        banks_filter = "', '".join(TARGET_BANKS_LIST)

        rows = client.query(f"""
            SELECT bank_name, currency_code, currency_name, buying, selling, difference
            FROM bank_exchange_rates
            WHERE date = '{latest_date}'
              AND bank_name IN ('{banks_filter}')
            ORDER BY bank_name, currency_code
        """).result_rows

        # Group by bank
        banks: dict = {}
        for r in rows:
            bank = r[0]
            if bank not in banks:
                banks[bank] = {"bank_name": bank, "currencies": []}
            banks[bank]["currencies"].append({
                "code": r[1],
                "name": r[2],
                "buying": r[3],
                "selling": r[4],
                "difference": r[5],
            })

        # Preserve the order of TARGET_BANKS_LIST
        ordered = []
        for name in TARGET_BANKS_LIST:
            if name in banks:
                ordered.append(banks[name])

        return {
            "banks": ordered,
            "date": str(latest_date),
            "source": "banksethiopia.com",
            "source_url": "https://banksethiopia.com/ethiopian-birr-exchange-rate/",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        _logger.warning(f"bank-rates unavailable: {e}")
        return {"banks": [], "date": None, "source": "banksethiopia.com", "timestamp": datetime.utcnow().isoformat()}


@router.get("/bank-rates/weekly")
def get_weekly_performance():
    """
    Weekly top/underperforming bank performance tables.
    """
    try:
        client = _ch()
        latest = client.query(
            "SELECT max(week_end) FROM bank_weekly_performance"
        ).result_rows
        if not latest or not latest[0][0]:
            return {"top": [], "underperforming": [], "week_end": None, "timestamp": datetime.utcnow().isoformat()}

        week_end = latest[0][0]
        rows = client.query(f"""
            SELECT bank_name, category, max_buying, max_selling, min_buying, min_selling, week_start, week_end
            FROM bank_weekly_performance
            WHERE week_end = '{week_end}'
            ORDER BY category, max_buying DESC
        """).result_rows

        top, under = [], []
        seen: set = set()
        for r in rows:
            key = (r[0], r[1])  # (bank_name, category)
            if key in seen:
                continue  # skip duplicates — keep first (highest max_buying)
            seen.add(key)
            entry = {
                "bank_name": r[0],
                "max_buying": float(r[2]),
                "max_selling": float(r[3]),
                "min_buying": float(r[4]),
                "min_selling": float(r[5]),
                "week_start": str(r[6]),
                "week_end": str(r[7]),
            }
            if r[1] == "top":
                top.append(entry)
            else:
                under.append(entry)

        return {
            "top": top,
            "underperforming": under,
            "week_end": str(week_end),
            "source": "banksethiopia.com",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        _logger.warning(f"bank-rates/weekly unavailable: {e}")
        return {"top": [], "underperforming": [], "week_end": None, "timestamp": datetime.utcnow().isoformat()}


@router.get("/bank-rates/history")
def get_bank_rate_history(bank: str = "Commercial Bank of Ethiopia", currency: str = "USD", days: int = 30):
    """
    Historical exchange rates for a specific bank + currency over N days.
    """
    try:
        client = _ch()
        rows = client.query(f"""
            SELECT date, buying, selling, difference
            FROM bank_exchange_rates
            WHERE bank_name = '{bank}'
              AND currency_code = '{currency}'
              AND date >= today() - INTERVAL {days} DAY
            ORDER BY date ASC
        """).result_rows
        return {
            "bank": bank,
            "currency": currency,
            "history": [{"date": str(r[0]), "buying": r[1], "selling": r[2], "difference": r[3]} for r in rows],
            "days": days,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        _logger.warning(f"bank-rates/history unavailable: {e}")
        return {"bank": bank, "currency": currency, "history": [], "days": days, "timestamp": datetime.utcnow().isoformat()}
