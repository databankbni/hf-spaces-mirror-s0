from models import ValuationData, FundamentalData

def analyze_valuation(fundamentals: FundamentalData, current_price: float) -> ValuationData:
    """
    Very basic DCF and Relative Valuation estimation.
    In a real institutional platform, this would use multi-stage models.
    """
    eps = fundamentals["eps"]
    peg = fundamentals["peg_ratio"]
    
    # 1. Graham Number (Intrinsic Value proxy)
    # Fair Value = sqrt(22.5 * EPS * BVPS)
    # BVPS = current_price / price_to_book
    bvps = current_price / fundamentals["price_to_book"] if fundamentals["price_to_book"] > 0 else 0
    graham_value = 0.0
    if eps > 0 and bvps > 0:
        graham_value = (22.5 * eps * bvps) ** 0.5
        
    # Relative Valuation Status
    valuation_status = "Fairly Valued"
    pe = current_price / eps if eps > 0 else 0
    
    if pe > 0:
        if peg > 1.5 or fundamentals["ev_ebitda"] > 15:
            valuation_status = "Overvalued"
        elif peg < 1.0 and peg > 0:
            valuation_status = "Undervalued"
    else:
        valuation_status = "Overvalued (Negative EPS)"
        
    margin_of_safety = ((graham_value - current_price) / graham_value) if graham_value > 0 else 0.0

    return {
        "dcf_intrinsic_value": graham_value,
        "relative_pe": pe,
        "industry_pe": None, # Complex to fetch real-time without paid API
        "margin_of_safety": margin_of_safety,
        "valuation_status": valuation_status
    }
