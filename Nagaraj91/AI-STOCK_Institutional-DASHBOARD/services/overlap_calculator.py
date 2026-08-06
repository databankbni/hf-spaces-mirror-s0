from typing import List, Dict, Any
from services.mutual_fund_analysis import extract_holdings
import yfinance as yf

def calculate_overlap(resolved_tickers: Dict[str, str]) -> Dict[str, Any]:
    """
    Calculates the portfolio overlap between N mutual funds.
    """
    if len(resolved_tickers) < 2:
        return {"error": "Need at least 2 funds for overlap analysis."}
        
    funds_data = {}
    all_stocks = set()
    
    # 1. Fetch holdings for all funds
    for name, ticker in resolved_tickers.items():
        # Pass the extracted name to the extractor so it can trigger the MoneyControl fallback
        holdings = extract_holdings(ticker, fund_name=name)
        # Use the name resolved by our LLM, it is much cleaner than yfinance's internal mutual fund tickers
        display_name = name
            
        funds_data[display_name] = holdings
        all_stocks.update(holdings.keys())
        
    fund_names = list(funds_data.keys())
    
    # 2. Check pairwise overlaps
    overlaps = []
    
    for i in range(len(fund_names)):
        for j in range(i + 1, len(fund_names)):
            fund_a = fund_names[i]
            fund_b = fund_names[j]
            
            holdings_a = funds_data[fund_a]
            holdings_b = funds_data[fund_b]
            
            # Find common stocks
            common_stocks = set(holdings_a.keys()).intersection(set(holdings_b.keys()))
            
            # Calculate weight overlap
            overlap_score = 0.0
            common_details = []
            
            for stock in common_stocks:
                weight_a = holdings_a[stock]
                weight_b = holdings_b[stock]
                
                # The true overlap of a single position is the MIN of the two weights
                # E.g., if Fund A has 5% Reliance and Fund B has 3% Reliance, the overlap is 3%
                min_weight = min(weight_a, weight_b)
                if min_weight > 0:
                    overlap_score += min_weight
                    common_details.append({
                        "stock": stock,
                        "weight_a": weight_a,
                        "weight_b": weight_b,
                        "overlap": min_weight
                    })
            
            overlaps.append({
                "fund_a": fund_a,
                "fund_b": fund_b,
                "overlap_percentage": round(overlap_score, 2),
                "common_stocks": sorted(common_details, key=lambda x: x['overlap'], reverse=True)
            })
            
    return {
        "status": "success",
        "funds_compared": fund_names,
        "pairwise_overlaps": overlaps
    }
