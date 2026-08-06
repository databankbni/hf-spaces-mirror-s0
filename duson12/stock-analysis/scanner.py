import requests
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from analysis.indicators import add_indicators
from analysis.recommender import recommend


def _grade(latest, prev3):
    if pd.isna(latest):
        return "N/A"
    count = sum(1 for v in prev3 if not pd.isna(v) and latest > v)
    if count == 3:
        return "A+"
    elif count == 2:
        return "A"
    elif count == 1:
        return "B"
    else:
        return "C"


def get_financial_grades(ticker_yf: str):
    try:
        tk = yf.Ticker(ticker_yf)
        fin = tk.quarterly_financials
        if fin is None or fin.empty:
            return None

        fin = fin.iloc[:, :4]
        quarters = [str(c)[:7] for c in fin.columns]

        def row_values(keywords):
            for kw in keywords:
                matches = [i for i in fin.index if kw.lower() in str(i).lower()]
                if matches:
                    return fin.loc[matches[0]].tolist()
            return [None] * 4

        rev  = row_values(["Total Revenue", "Revenue"])
        oper = row_values(["Operating Income", "Operating Revenue"])
        net  = row_values(["Net Income"])

        if all(v is None for v in rev + oper + net):
            return None

        return {
            "quarters":        quarters,
            "revenue":         rev,
            "operating":       oper,
            "net":             net,
            "grade_revenue":   _grade(rev[0],  rev[1:4]),
            "grade_operating": _grade(oper[0], oper[1:4]),
            "grade_net":       _grade(net[0],  net[1:4]),
        }
    except Exception:
        return None


def _get_signal(code: str):
    """국내 종목 기술적 분석 신호 + 점수 반환 (signal, score)"""
    try:
        end   = datetime.today()
        start = end - timedelta(days=365)
        df = fdr.DataReader(code, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if df.empty or len(df) < 30:
            return "N/A", 0.0
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                 "Close": "close", "Volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df = add_indicators(df)
        rec = recommend(df)
        return rec.signal, rec.score
    except Exception:
        return "N/A", 0.0


def _get_signal_us(sym: str):
    """미국 종목 기술적 분석 신호 + 점수 반환 (signal, score)"""
    try:
        df = yf.Ticker(sym).history(period="1y", auto_adjust=True)
        if df.empty or len(df) < 30:
            return "N/A", 0.0
        df.columns = [str(c).lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df = add_indicators(df)
        rec = recommend(df)
        return rec.signal, rec.score
    except Exception:
        return "N/A", 0.0


def get_us_top(n: int = 1000) -> pd.DataFrame:
    """미국(NASDAQ+NYSE+AMEX) 시가총액 상위 N개 — 나스닥 스크리너 API 사용,
    실패 시 S&P500 리스트로 대체"""
    try:
        r = requests.get(
            "https://api.nasdaq.com/api/screener/stocks",
            params={"tableonly": "true", "limit": "25", "download": "true"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=30)
        rows = r.json()["data"]["rows"]
        df = pd.DataFrame(rows)
        df["Marcap"] = pd.to_numeric(df["marketCap"], errors="coerce")
        df = df.dropna(subset=["Marcap"])
        df = df[df["Marcap"] > 0]
        df["Code"] = (df["symbol"].astype(str).str.strip()
                      .str.replace("/", "-", regex=False)
                      .str.replace(".", "-", regex=False)
                      .str.replace("^", "-", regex=False))
        df["Name"] = (df["name"].astype(str)
                      .str.replace(r"\s+(Class [A-C]\s+)?(Common Stock|Capital Stock|Ordinary Shares?|"
                                   r"American Depositary Shares?|Depositary Shares?|Common Shares?)"
                                   r"(\s+each.*)?$",
                                   "", regex=True)
                      .str.strip())
        df["Market"] = "US"
        # 같은 회사의 중복 클래스(예: GOOG/GOOGL)는 그대로 두되, 워런트/유닛 티커는 제외
        df = df[~df["Code"].str.endswith(("-W", "-U", "-R"))]
        df = df.sort_values("Marcap", ascending=False).head(n)
        return df[["Code", "Name", "Marcap", "Market"]].reset_index(drop=True)
    except Exception:
        try:
            sp = fdr.StockListing("S&P500")
            sp = sp.rename(columns={"Symbol": "Code"})[["Code", "Name"]].dropna()
            sp["Code"] = sp["Code"].astype(str).str.replace(".", "-", regex=False)
            sp["Marcap"] = 0
            sp["Market"] = "US"
            return sp.head(n).reset_index(drop=True)
        except Exception as e:
            st.error(f"미국 종목 리스트 조회 실패: {e}")
            return pd.DataFrame()


def get_krx_top(n: int = 500) -> pd.DataFrame:
    try:
        kospi  = fdr.StockListing("KOSPI")[["Code", "Name", "Marcap"]].dropna()
        kosdaq = fdr.StockListing("KOSDAQ")[["Code", "Name", "Marcap"]].dropna()
        kospi["Market"]  = "KOSPI"
        kosdaq["Market"] = "KOSDAQ"
        all_stocks = pd.concat([kospi, kosdaq], ignore_index=True)
        all_stocks["Marcap"] = pd.to_numeric(all_stocks["Marcap"], errors="coerce")
        return all_stocks.sort_values("Marcap", ascending=False).head(n).reset_index(drop=True)
    except Exception as e:
        st.error(f"종목 리스트 조회 실패: {e}")
        return pd.DataFrame()


def _fetch_one(row):
    """단일 종목 재무등급 + 기술적 신호 조회 (병렬 워커용)"""
    market = row["Market"]
    if market == "US":
        code = str(row["Code"]).strip()
        grades = get_financial_grades(code)
        if grades is None:
            return None
        signal, score = _get_signal_us(code)
    else:
        code   = str(row["Code"]).zfill(6)
        suffix = ".KS" if market == "KOSPI" else ".KQ"
        grades = get_financial_grades(code + suffix)
        if grades is None:
            return None
        signal, score = _get_signal(code)

    gr  = grades["grade_revenue"]
    go_ = grades["grade_operating"]
    gn  = grades["grade_net"]

    return {
        "Code":            code,
        "Name":            row["Name"],
        "Market":          market,
        "매출 등급":       gr,
        "영업이익 등급":   go_,
        "당기순이익 등급": gn,
        "매매 신호":       signal,
        "신호 점수":       int(round(score)),
        "전체 A+":         (gr == "A+" and go_ == "A+" and gn == "A+"),
        "순이익 A+":       (gn == "A+"),
    }


def scan_stocks(n: int = 500, progress_bar=None, status_text=None, max_workers: int = 10,
                market: str = "KR"):
    """병렬로 상위 N개 종목 스캔 후 재무등급 + 매매신호 DataFrame 반환
    market: "KR"(KOSPI+KOSDAQ) 또는 "US"(NASDAQ+NYSE 시총 상위)"""
    stocks = get_us_top(n) if market == "US" else get_krx_top(n)
    if stocks.empty:
        return pd.DataFrame()

    rows    = [row for _, row in stocks.iterrows()]
    total   = len(rows)
    results = []
    done    = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, row): row for row in rows}
        for future in as_completed(futures):
            done += 1
            row = futures[future]
            if status_text:
                status_text.text(f"조회 중 ({done}/{total}): {row['Name']}")
            if progress_bar:
                progress_bar.progress(done / total)
            result = future.result()
            if result:
                results.append(result)

    return pd.DataFrame(results)
