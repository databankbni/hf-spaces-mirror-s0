from models import TechnicalData, FundamentalData, ValuationData, ScoreData

def generate_scores(tech: TechnicalData, fund: FundamentalData, val: ValuationData) -> ScoreData:
    """
    Generates a 0-100 score for various categories.
    """
    # 1. Fundamental Score (Max 30)
    fund_score = 15 # base
    if fund["roe"] > 0.15: fund_score += 5
    if fund["net_margin"] > 0.10: fund_score += 5
    if fund["debt_to_equity"] < 1.0 and fund["debt_to_equity"] > 0: fund_score += 5
    
    # 2. Technical Score (Max 20)
    tech_score = 10
    if tech["trend"] == "Bullish": tech_score += 5
    if tech["rsi"] > 40 and tech["rsi"] < 70: tech_score += 2
    if tech["macd"] > tech["macd_signal"]: tech_score += 3
    
    # 3. Valuation Score (Max 15)
    val_score = 7
    if val["valuation_status"] == "Undervalued": val_score += 8
    elif val["valuation_status"] == "Fairly Valued": val_score += 4
    
    # 4. Financial Health (Max 10)
    health_score = 5
    if fund["current_ratio"] > 1.5: health_score += 3
    if fund["free_cash_flow"] > 0: health_score += 2
    
    # 5. Growth (Max 10)
    growth_score = 5
    if fund["peg_ratio"] > 0 and fund["peg_ratio"] < 1: growth_score += 5
    
    overall = fund_score + tech_score + val_score + health_score + growth_score + 15 # giving base 15 for News/Sector proxy
    
    return {
        "fundamental_score": min(fund_score / 30 * 100, 100),
        "technical_score": min(tech_score / 20 * 100, 100),
        "valuation_score": min(val_score / 15 * 100, 100),
        "health_score": min(health_score / 10 * 100, 100),
        "growth_score": min(growth_score / 10 * 100, 100),
        "overall_score": min(overall, 100)
    }
