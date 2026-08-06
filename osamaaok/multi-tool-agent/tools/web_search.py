import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))


def web_search(query, max_results=3):
    """
    Searches the web via Tavily and returns a clean, combined text block
    of the top results' content, ready to hand to an LLM as context.
    """
    try:
        response = tavily_client.search(query=query, max_results=max_results)
    except Exception as e:
        return f"Web search failed: {str(e)}"

    results = response.get("results", [])
    if not results:
        return "No web search results found."

    combined = []
    for i, result in enumerate(results, start=1):
        title = result.get("title", "Untitled")
        content = result.get("content", "")
        url = result.get("url", "")
        combined.append(f"[Source {i}: {title}]\n{content}\n(URL: {url})")

    return "\n\n".join(combined)


if __name__ == "__main__":
    result = web_search("current weather in Lahore")
    print(result)