import yfinance as yf
from typing import Dict, Any, List

def extract_holdings(ticker: str, fund_name: str = "") -> Dict[str, float]:
    """
    Attempts to extract stock holdings and their portfolio weights for a mutual fund.
    Returns a dictionary of {Stock_Name: Weight_Percentage}.
    Note: yfinance often lacks portfolio data for Indian Mutual Funds, so this will 
    gracefully return {} for unsupported funds, while working perfectly for US ETFs.
    """
    fund = yf.Ticker(ticker)
    
    # Try different yfinance attributes for holdings
    # 1. Check if it's stored in 'info'
    holdings = fund.info.get('holdings', [])
    
    # 2. Check if it's stored in 'funds_data' object (for US ETFs)
    if not holdings and hasattr(fund, 'funds_data') and fund.funds_data:
        try:
            holdings = fund.funds_data.top_holdings
            if holdings is not None and len(holdings) > 0:
                # Top holdings is usually a DataFrame or dict depending on yfinance version
                # Usually it has 'holdingName' or index as stock name, and 'holdingPercent' as weight
                if hasattr(holdings, 'to_dict'):
                    holdings_dict_raw = holdings.to_dict(orient='index')
                    result = {}
                    for symbol, data in holdings_dict_raw.items():
                        name = data.get('holdingName', symbol)
                        weight = data.get('holdingPercent', 0)
                        result[name] = weight * 100
                    return result
        except Exception as e:
            print(f"Failed to parse funds_data for {ticker}: {e}")

    # Fallback parsing for 'info' list of dicts
    holdings_dict = {}
    if isinstance(holdings, list):
        for h in holdings:
            name = h.get('holdingName') or h.get('symbol')
            weight = h.get('holdingPercent', 0)
            if name:
                holdings_dict[name] = weight * 100 # usually decimal in info
                
    return holdings_dict

def analyze_mutual_fund(ticker: str) -> Dict[str, Any]:
    """
    Extracts Mutual Fund specific metrics.
    """
    fund = yf.Ticker(ticker)
    info = fund.info
    
    aum = info.get('totalAssets', 0)
    nav = info.get('navPrice', 0)
    expense_ratio = info.get('annualReportExpenseRatio', 0)
    ytd_return = info.get('ytdReturn', 0)
    three_year_return = info.get('threeYearAverageReturn', 0)
    five_year_return = info.get('fiveYearAverageReturn', 0)
    category = info.get('category', 'Unknown')
    
    return {
        "nav": nav,
        "aum": aum,
        "expense_ratio": expense_ratio * 100 if expense_ratio else 0, # convert to %
        "ytd_return": ytd_return * 100 if ytd_return else 0,
        "three_year_return": three_year_return * 100 if three_year_return else 0,
        "five_year_return": five_year_return * 100 if five_year_return else 0,
        "category": category,
        "holdings": extract_holdings(ticker)
    }
