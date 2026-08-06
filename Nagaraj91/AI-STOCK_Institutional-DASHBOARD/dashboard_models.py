from pydantic import BaseModel, Field
from typing import List, Optional

# --- Dashboard Pydantic Models for LLM Output ---
# These models are optimized to ONLY extract textual AI interpretations. 
# Raw numerical data (like PE, support, margin) is read directly from Python.

class SummaryTab(BaseModel):
    action: str = Field(description="BUY, HOLD, or SELL")
    confidence: int = Field(description="0 to 100")
    risk_level: str = Field(description="Low, Medium, or High")
    expected_return: str = Field(description="e.g. +15% over 12 months")
    action_plan: str = Field(description="Brief strategy")

class TechnicalTab(BaseModel):
    trend: str = Field(description="Bullish, Bearish, Neutral")
    pattern_recognition: str = Field(description="e.g. Double Bottom, None")
    educational_note: str = Field(description="Explain what these technicals mean")
    ai_interpretation: str = Field(description="How to interpret this for the stock")

class FundamentalTab(BaseModel):
    educational_note: str
    ai_interpretation: str

class HealthTab(BaseModel):
    cash_flow_health: str = Field(description="Strong, Weak, etc.")
    debt_trend: str
    educational_note: str
    ai_interpretation: str

class GrowthTab(BaseModel):
    forecast: str
    educational_note: str
    ai_interpretation: str

class ValuationTab(BaseModel):
    valuation_status: str = Field(description="Undervalued, Fairly Valued, Overvalued")
    educational_note: str
    ai_interpretation: str

class OwnershipTab(BaseModel):
    promoter_trend: str = Field(description="Increasing, Decreasing, Stable")
    institutional_trend: str
    educational_note: str
    ai_interpretation: str

class NewsTab(BaseModel):
    sentiment: str = Field(description="Positive, Neutral, Negative")
    ai_summary: str

class SectorTab(BaseModel):
    industry_outlook: str
    macro_trends: str
    ai_interpretation: str

class RiskTab(BaseModel):
    top_risks: List[str]
    mitigation: str
    educational_note: str

class PeerTab(BaseModel):
    competitors: List[str]
    ai_interpretation: str

class ScenarioTab(BaseModel):
    educational_note: str

class ReasoningTab(BaseModel):
    positive_factors: List[str]
    negative_factors: List[str]
    neutral_factors: List[str]
    decision_tree: str

class DashboardInsights(BaseModel):
    """
    The master schema for the AI insights.
    """
    summary: SummaryTab
    technical: TechnicalTab
    fundamental: FundamentalTab
    health: HealthTab
    growth: GrowthTab
    valuation: ValuationTab
    ownership: OwnershipTab
    news: NewsTab
    sector: SectorTab
    risk: RiskTab
    peer: PeerTab
    scenario: ScenarioTab
    reasoning: ReasoningTab
