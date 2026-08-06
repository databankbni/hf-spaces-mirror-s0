from typing import Tuple, Dict, Any
import os
import json
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from tools import get_comprehensive_analysis
from dashboard_models import DashboardInsights

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache
# Enable SQLite Caching for all LLM calls to drastically save tokens on repeated queries
set_llm_cache(SQLiteCache(database_path=".langchain.db"))

def get_llm(model_type: str):
    if model_type == "OpenAI (ChatGPT)":
        key = os.getenv("OPENAI_API_KEY")
        # Use gpt-4o for final structured output
        return ChatOpenAI(model="gpt-4o", api_key=key, temperature=0)
    else:
        key = os.getenv("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=key, temperature=0)

def run_dashboard_workflow(ticker: str, model_type: str) -> Tuple[Dict[str, Any], DashboardInsights]:
    """
    A deterministic, optimized Python workflow that:
    1. Fetches raw data purely in Python (no LLM routing/hallucinations).
    2. Passes the raw JSON to the LLM to generate textual AI insights.
    Returns: (raw_data_dict, ai_insights_pydantic)
    """
    
    # 1. Deterministic Data Fetch
    # We call the underlying tool directly instead of using an Agent to route it
    raw_data_json = get_comprehensive_analysis.invoke({"ticker": ticker})
    
    # Check for errors in fetch
    if raw_data_json.startswith("Error"):
        raise Exception(raw_data_json)
        
    raw_data_dict = json.loads(raw_data_json)
    
    # 2. Setup LLM
    structured_llm = get_llm(model_type).with_structured_output(DashboardInsights)
    
    # 3. Generate Report
    sys_prompt = SystemMessage(content="""You are a Senior Architect building an institutional dashboard.
Given the fetched financial data, generate deep, professional AI interpretations.
Focus heavily on cross-referencing metrics to find contradictions or strong correlations.
DO NOT regurgitate raw numbers unless explicitly making a point.
IMPORTANT: If 'competitors' or 'news' is missing from the raw data and you do not definitively know them, output an empty list/string rather than inventing 'Company A' or generic news.
""")
    messages = [sys_prompt, HumanMessage(content=raw_data_json)]
    
    insights = structured_llm.invoke(messages)
    
    return raw_data_dict, insights
