"""
Sala AI - Google Search Brand/Competitor Monitoring
Searches Google (via Custom Search API) for given keywords and classifies
the sentiment of each result snippet, so the admin dashboard can show
how sala.lk / products / competitors are showing up in search results.
"""

import os
import requests

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CSE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

# Simple keyword-based sentiment classifier.
# This is a lightweight fallback with no extra API calls / cost.
# If you already have an LLM-based sentiment classifier (e.g. in analytics/),
# swap the body of this function to call that instead.
_POSITIVE_WORDS = [
    "best", "great", "excellent", "quality", "reliable", "recommend",
    "trusted", "affordable", "genuine", "top", "good", "fast", "efficient",
]
_NEGATIVE_WORDS = [
    "worst", "bad", "scam", "fake", "poor", "complaint", "issue", "problem",
    "broken", "delay", "fraud", "warning", "avoid", "disappointed",
]


def _classify_sentiment(snippet: str) -> str:
    """Classifies a search-result snippet as 'positive', 'negative', or 'neutral'."""
    if not snippet:
        return "neutral"
    text = snippet.lower()
    pos_hits = sum(1 for w in _POSITIVE_WORDS if w in text)
    neg_hits = sum(1 for w in _NEGATIVE_WORDS if w in text)
    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    return "neutral"


def monitor_keywords(keywords: list[str], results_per_keyword: int = 5) -> dict:
    """
    Searches Google for each keyword and returns results with AI-classified sentiment.
    keywords: list of search terms (e.g. brand name, competitor name)
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CSE_ID:
        return {"error": "Google Search API not configured", "results": []}

    all_results = []

    for keyword in keywords:
        try:
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_SEARCH_API_KEY,
                    "cx": GOOGLE_SEARCH_CSE_ID,
                    "q": keyword,
                    "num": results_per_keyword,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("items", []):
                snippet = item.get("snippet", "")
                all_results.append({
                    "keyword": keyword,
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": snippet,
                    "sentiment": _classify_sentiment(snippet),
                })
        except Exception as e:
            print(f"[Google Search failed for '{keyword}'] {e}")
            continue

    return {"results": all_results}