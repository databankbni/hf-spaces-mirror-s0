from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
import urllib.request
import urllib.parse
import json
import os

def search_yahoo_finance(query: str) -> str:
    """Uses Yahoo Finance Search API to find the exact ticker symbol."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if 'quotes' in data and len(data['quotes']) > 0:
                # Prefer .NS or .BO if it's an Indian query, otherwise just take the first match
                for quote in data['quotes']:
                    sym = quote.get('symbol', '')
                    if sym.endswith('.NS') or sym.endswith('.BO'):
                        return sym
                return data['quotes'][0].get('symbol', query)
    except Exception:
        pass
    return query # Fallback to original query if search fails

def resolve_tickers(query: str, model_type: str = "OpenAI (ChatGPT)") -> dict:
    """
    Takes a natural language query and resolves it to a Dictionary mapping name to verified Yahoo Finance ticker.
    """
    sys_prompt = SystemMessage(content="""
    You are an intelligent entity extraction assistant.
    The user will provide a natural language query asking about one or more stocks/mutual funds.
    Your job is to identify ALL primary company or fund names and return them as a JSON list of strings.
    
    RULES:
    1. Return the core, concise name of the company/fund to maximize search engine hits. 
       - Remove words like "Direct", "Growth", "Plan", "Fund", "ETF", "FOF" from mutual funds!
       - e.g., "Parag Parikh Flexi Cap Fund Direct Growth" -> "Parag Parikh Flexi Cap"
       - e.g., "Quant Elss Tax Saver Fund direct Growth" -> "Quant ELSS Tax Saver"
    2. Return ONLY a valid JSON list of strings. No markdown, no explanations.
    
    Examples:
    User: "Analyze Reliance" -> Output: ["Reliance Industries"]
    User: "Compare Apple and Microsoft" -> Output: ["Apple", "Microsoft"]
    User: "Parag Parikh Flexi Cap Fund Direct Growth, Quant Elss Tax Saver" -> Output: ["Parag Parikh Flexi Cap", "Quant ELSS Tax Saver"]
    """)
    
    # Initialize lightweight model for fast resolution
    if model_type == "OpenAI (ChatGPT)":
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    else:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)
        
    messages = [sys_prompt, HumanMessage(content=query)]
    response = llm.invoke(messages)
    
    try:
        # Parse the JSON list
        raw_output = response.content.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3]
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3]
            
        entity_names = json.loads(raw_output.strip())
        if not isinstance(entity_names, list):
            entity_names = [entity_names]
    except Exception:
        # Fallback if LLM fails to return JSON
        entity_names = [response.content.strip()]
        
    resolved_dict = {}
    for name in entity_names:
        resolved_dict[name] = search_yahoo_finance(name)
        
    return resolved_dict
