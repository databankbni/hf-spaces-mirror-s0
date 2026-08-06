import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_us_price(ticker: str, days: int = 365) -> pd.DataFrame:
    """미국 주식 가격 데이터 조회"""
    end = datetime.today()
    start = end - timedelta(days=days)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"데이터를 찾을 수 없습니다: {ticker}")
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index)
    return df[["open", "high", "low", "close", "volume"]].dropna()


def get_us_info(ticker: str) -> dict:
    """종목 기본 정보 반환"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name": info.get("longName", ticker),
            "market": info.get("exchange", "NASDAQ/NYSE"),
            "sector": info.get("sector", "-"),
            "industry": info.get("industry", "-"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
        }
    except Exception:
        return {"name": ticker, "market": "US"}
