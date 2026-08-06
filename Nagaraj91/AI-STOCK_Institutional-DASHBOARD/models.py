from typing import TypedDict, Optional, Dict, Any, List

class TechnicalData(TypedDict):
    current_price: float
    high_52w: float
    low_52w: float
    avg_volume: float
    beta: float
    trend: str
    ema_20: float
    ema_50: float
    ema_200: float
    macd: float
    macd_signal: float
    rsi: float
    adx: float
    bollinger_upper: float
    bollinger_lower: float
    support_1: float
    resistance_1: float
    trend_strength: str

class FundamentalData(TypedDict):
    market_cap: float
    revenue: float
    net_income: float
    eps: float
    roe: float
    roce: float
    debt_to_equity: float
    current_ratio: float
    quick_ratio: float
    operating_margin: float
    net_margin: float
    free_cash_flow: float
    price_to_book: float
    peg_ratio: float
    ev_ebitda: float
    dividend_yield: float
    industry: str
    sector: str

class ValuationData(TypedDict):
    dcf_intrinsic_value: Optional[float]
    relative_pe: float
    industry_pe: Optional[float]
    margin_of_safety: Optional[float]
    valuation_status: str # Undervalued, Fairly Valued, Overvalued

class ScoreData(TypedDict):
    fundamental_score: float
    technical_score: float
    valuation_score: float
    health_score: float
    growth_score: float
    overall_score: float

class FullReportData(TypedDict):
    ticker: str
    technicals: TechnicalData
    fundamentals: FundamentalData
    valuation: ValuationData
    scores: ScoreData
    news: List[str]
