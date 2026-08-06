import yfinance as yf
from models import FundamentalData

def analyze_fundamentals(ticker: str) -> FundamentalData:
    stock = yf.Ticker(ticker)
    info = stock.info
    
    # Safely get values
    def get_safe(key: str, default: float = 0.0) -> float:
        val = info.get(key)
        return float(val) if val is not None else default
        
    market_cap = get_safe('marketCap')
    revenue = get_safe('totalRevenue')
    net_income = get_safe('netIncomeToCommon')
    eps = get_safe('trailingEps')
    roe = get_safe('returnOnEquity')
    
    # ROCE approximation if not direct
    ebitda = get_safe('ebitda')
    total_assets = get_safe('totalAssets')
    total_liab = get_safe('totalLiab')
    capital_employed = total_assets - (total_liab - get_safe('totalDebt'))
    roce = (ebitda / capital_employed) if capital_employed > 0 else 0.0
    
    debt_to_equity = get_safe('debtToEquity') / 100.0  # yfinance returns as percentage
    current_ratio = get_safe('currentRatio')
    quick_ratio = get_safe('quickRatio')
    operating_margin = get_safe('operatingMargins')
    net_margin = get_safe('profitMargins')
    free_cash_flow = get_safe('freeCashflow')
    price_to_book = get_safe('priceToBook')
    peg_ratio = get_safe('pegRatio')
    ev_ebitda = get_safe('enterpriseToEbitda')
    dividend_yield = get_safe('dividendYield')
    
    industry = info.get('industry', 'Unknown')
    sector = info.get('sector', 'Unknown')
    
    return {
        "market_cap": market_cap,
        "revenue": revenue,
        "net_income": net_income,
        "eps": eps,
        "roe": roe,
        "roce": roce,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "free_cash_flow": free_cash_flow,
        "price_to_book": price_to_book,
        "peg_ratio": peg_ratio,
        "ev_ebitda": ev_ebitda,
        "dividend_yield": dividend_yield,
        "industry": industry,
        "sector": sector
    }
