import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta


def get_kr_stock_list() -> pd.DataFrame:
    """KRX 전체 종목 리스트 반환"""
    krx = fdr.StockListing("KRX")
    return krx[["Code", "Name", "Market"]].dropna()


def get_kr_price(ticker: str, days: int = 365) -> pd.DataFrame:
    """국내 주식 가격 데이터 조회"""
    end = datetime.today()
    start = end - timedelta(days=days)
    df = fdr.DataReader(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    if df.empty:
        raise ValueError(f"데이터를 찾을 수 없습니다: {ticker}")
    df.index = pd.to_datetime(df.index)
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]].dropna()


def get_kr_info(ticker: str) -> dict:
    """종목 기본 정보 반환"""
    listing = fdr.StockListing("KRX")
    row = listing[listing["Code"] == ticker]
    if row.empty:
        return {"name": ticker, "market": "KRX"}
    r = row.iloc[0]
    return {
        "name": r.get("Name", ticker),
        "market": r.get("Market", "KRX"),
        "sector": r.get("Sector", "-"),
        "industry": r.get("Industry", "-"),
    }
