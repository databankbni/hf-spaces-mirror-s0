import json
import sys
import os
from langchain_core.tools import tool
import yfinance as yf

# Ensure services can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.technical_analysis import analyze_technicals
from services.fundamental_analysis import analyze_fundamentals
from services.valuation_service import analyze_valuation
from services.scoring_engine import generate_scores

@tool
def get_comprehensive_analysis(ticker: str) -> str:
    """
    Fetch a complete institutional-grade data dump for a stock.
    Includes technicals, fundamentals, valuation, and scoring.
    """
    try:
        tech = analyze_technicals(ticker)
        fund = analyze_fundamentals(ticker)
        val = analyze_valuation(fund, tech["current_price"])
        scores = generate_scores(tech, fund, val)
        
        # Fetch news
        stock = yf.Ticker(ticker)
        news_items = stock.news
        news = [item.get('title', 'Headline Unavailable') for item in news_items[:5] if isinstance(item, dict)] if news_items else []
        
        data = {
            "technicals": tech,
            "fundamentals": fund,
            "valuation": val,
            "scores": scores,
            "news": news
        }
        return json.dumps(data, indent=2)
    except Exception as e:
        return f"Error analyzing {ticker}: {str(e)}"

research_tools = [get_comprehensive_analysis]
