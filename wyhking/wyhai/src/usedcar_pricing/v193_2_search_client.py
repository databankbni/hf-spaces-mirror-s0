from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
from dataclasses import dataclass
from typing import Any


PRIMARY_SEARCH_PROVIDER = "auto"
DEFAULT_PROVIDER_CHAIN = ["tavily", "exa", "brave_llm_context", "brave", "bing", "serpapi", "searxng"]
SEARCH_CLIENT_VERSION = "v195_enterprise_search_gateway_v1"


@dataclass
class SearchResult:
    provider: str
    query_text: str
    result_rank: int
    title: str
    url: str
    snippet: str
    raw_result_json: dict[str, Any]
    search_time: str


@dataclass
class SearchResponse:
    provider: str
    query_text: str
    status: str
    results: list[SearchResult]
    latency_ms: int
    error: str = ""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _request_json(url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    data = None
    method = "GET"
    merged_headers = {"User-Agent": "usedcar-pricing-v193.2/1.0"}
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(url, headers=merged_headers, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _request_text(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> str:
    merged_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
    }
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(url, headers=merged_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_html_fragment(value: str) -> str:
    text = urllib.parse.unquote(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


class OpenSearchClient:
    def __init__(
        self,
        provider: str | None = None,
        *,
        searxng_base_url: str | None = None,
        tavily_api_key: str | None = None,
        exa_api_key: str | None = None,
        brave_api_key: str | None = None,
        bing_api_key: str | None = None,
        serpapi_api_key: str | None = None,
        provider_chain: list[str] | None = None,
        timeout: float | None = None,
    ) -> None:
        self.provider = (provider or os.environ.get("SEARCH_PROVIDER") or PRIMARY_SEARCH_PROVIDER).strip().lower()
        self.searxng_base_url = (searxng_base_url or os.environ.get("SEARXNG_BASE_URL") or "http://localhost:8080").rstrip("/")
        self.tavily_api_key = tavily_api_key if tavily_api_key is not None else os.environ.get("TAVILY_API_KEY", "")
        self.exa_api_key = exa_api_key if exa_api_key is not None else os.environ.get("EXA_API_KEY", "")
        self.brave_api_key = brave_api_key if brave_api_key is not None else os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self.bing_api_key = bing_api_key if bing_api_key is not None else os.environ.get("BING_SEARCH_API_KEY", os.environ.get("AZURE_BING_SEARCH_KEY", ""))
        self.serpapi_api_key = serpapi_api_key if serpapi_api_key is not None else os.environ.get("SERPAPI_API_KEY", "")
        chain_env = os.environ.get("WEB_SEARCH_PROVIDER_CHAIN") or os.environ.get("SEARCH_PROVIDER_CHAIN") or ""
        self._provider_chain = provider_chain or [item.strip().lower() for item in chain_env.split(",") if item.strip()]
        self.timeout = float(timeout if timeout is not None else os.environ.get("WEB_EVIDENCE_SEARCH_TIMEOUT", "8"))

    def provider_chain(self, provider: str | None = None) -> list[str]:
        first = (provider or self.provider or PRIMARY_SEARCH_PROVIDER).strip().lower()
        if first == "auto":
            configured = self._provider_chain or DEFAULT_PROVIDER_CHAIN
            if os.environ.get("WEB_SEARCH_ALLOW_DDG", "").strip().lower() in {"1", "true", "yes", "on"}:
                configured = [*configured, "duckduckgo_html"]
            return list(dict.fromkeys(configured))
        chain = [first]
        for fallback in self._provider_chain or DEFAULT_PROVIDER_CHAIN:
            if fallback not in chain:
                chain.append(fallback)
        if (
            os.environ.get("WEB_SEARCH_ALLOW_DDG", "").strip().lower() in {"1", "true", "yes", "on"}
            and "duckduckgo_html" not in chain
        ):
            chain.append("duckduckgo_html")
        return chain

    def search(self, query_text: str, *, provider: str | None = None, max_results: int = 5) -> SearchResponse:
        last_response: SearchResponse | None = None
        primary_failure: SearchResponse | None = None
        for candidate_provider in self.provider_chain(provider):
            response = self._search_one(candidate_provider, query_text, max_results=max_results)
            if response.status == "OK" and response.results:
                return response
            if primary_failure is None and candidate_provider == (provider or self.provider):
                primary_failure = response
            last_response = response
        if primary_failure is not None and (last_response is None or last_response.status == "SEARCH_PROVIDER_UNAVAILABLE_NO_KEY"):
            return primary_failure
        return last_response or SearchResponse(provider=provider or self.provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE", results=[], latency_ms=0)

    def _search_one(self, provider: str, query_text: str, *, max_results: int) -> SearchResponse:
        start = time.time()
        try:
            if provider == "searxng":
                results = SearXNGSearchClient(self.searxng_base_url, timeout=self.timeout).search_results(query_text, max_results=max_results)
            elif provider == "tavily":
                if not self.tavily_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_tavily(query_text, max_results=max_results)
            elif provider == "exa":
                if not self.exa_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_exa(query_text, max_results=max_results)
            elif provider == "brave_llm_context":
                if not self.brave_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_brave_llm_context(query_text, max_results=max_results)
            elif provider == "brave":
                if not self.brave_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_brave(query_text, max_results=max_results)
            elif provider == "bing":
                if not self.bing_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_bing(query_text, max_results=max_results)
            elif provider == "serpapi":
                if not self.serpapi_api_key:
                    return SearchResponse(provider=provider, query_text=query_text, status="SEARCH_PROVIDER_UNAVAILABLE_NO_KEY", results=[], latency_ms=0)
                results = self._search_serpapi(query_text, max_results=max_results)
            elif provider in {"duckduckgo", "duckduckgo_html", "ddg"}:
                results = self._search_duckduckgo_html(query_text, max_results=max_results)
            else:
                return SearchResponse(provider=provider, query_text=query_text, status="UNKNOWN_SEARCH_PROVIDER", results=[], latency_ms=0)
            status = "OK" if results else "SEARCH_EMPTY_RESULT"
            return SearchResponse(provider=provider, query_text=query_text, status=status, results=results, latency_ms=int((time.time() - start) * 1000))
        except json.JSONDecodeError as error:
            return SearchResponse(
                provider=provider,
                query_text=query_text,
                status="SEARCH_NON_JSON_RESPONSE",
                results=[],
                latency_ms=int((time.time() - start) * 1000),
                error=f"JSONDecodeError: {str(error)[:300]}",
            )
        except (TimeoutError, socket.timeout) as error:
            return SearchResponse(
                provider=provider,
                query_text=query_text,
                status="SEARCH_TIMEOUT",
                results=[],
                latency_ms=int((time.time() - start) * 1000),
                error=f"{type(error).__name__}: {str(error)[:300]}",
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError) as error:
            status = "SEARCH_TIMEOUT" if "timed out" in str(error).lower() else "SEARCH_PROVIDER_UNAVAILABLE"
            return SearchResponse(
                provider=provider,
                query_text=query_text,
                status=status,
                results=[],
                latency_ms=int((time.time() - start) * 1000),
                error=f"{type(error).__name__}: {str(error)[:300]}",
            )

    def _search_tavily(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        raw = _request_json(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.tavily_api_key}"},
            body={
                "query": query_text,
                "max_results": min(max_results, 20),
                "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "advanced"),
                "include_answer": False,
                "include_raw_content": False,
                "country": os.environ.get("TAVILY_COUNTRY", "china"),
            },
            timeout=self.timeout,
        )
        items = raw.get("results") or []
        return [
            SearchResult(
                provider="tavily",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(items[:max_results])
        ]

    def _search_exa(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        raw = _request_json(
            "https://api.exa.ai/search",
            headers={"x-api-key": self.exa_api_key},
            body={"query": query_text, "numResults": max_results},
            timeout=self.timeout,
        )
        items = raw.get("results") or []
        return [
            SearchResult(
                provider="exa",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("text") or item.get("summary") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(items[:max_results])
        ]

    def _search_brave_llm_context(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query_text})
        raw = _request_json(
            f"https://api.search.brave.com/res/v1/llm/context?{params}",
            headers={"Accept": "application/json", "X-Subscription-Token": self.brave_api_key},
            timeout=self.timeout,
        )
        raw_items = raw.get("results") or raw.get("web_results") or raw.get("contexts") or []
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("results") or []
        if not isinstance(raw_items, list):
            raw_items = []
        return [
            SearchResult(
                provider="brave_llm_context",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("title") or item.get("name") or ""),
                url=str(item.get("url") or item.get("link") or ""),
                snippet=str(item.get("description") or item.get("snippet") or item.get("content") or item.get("text") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(raw_items[:max_results])
            if isinstance(item, dict)
        ]

    def _search_brave(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query_text, "count": max_results})
        raw = _request_json(
            f"https://api.search.brave.com/res/v1/web/search?{params}",
            headers={"Accept": "application/json", "X-Subscription-Token": self.brave_api_key},
            timeout=self.timeout,
        )
        items = ((raw.get("web") or {}).get("results") or [])[:max_results]
        return [
            SearchResult(
                provider="brave",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("description") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(items)
        ]

    def _search_bing(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query_text, "count": max_results, "mkt": os.environ.get("BING_MKT", "zh-CN")})
        raw = _request_json(
            f"https://api.bing.microsoft.com/v7.0/search?{params}",
            headers={"Ocp-Apim-Subscription-Key": self.bing_api_key},
            timeout=self.timeout,
        )
        items = ((raw.get("webPages") or {}).get("value") or [])[:max_results]
        return [
            SearchResult(
                provider="bing",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(items)
        ]

    def _search_serpapi(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        params = urllib.parse.urlencode(
            {
                "engine": "google",
                "q": query_text,
                "api_key": self.serpapi_api_key,
                "num": max_results,
                "hl": "zh-cn",
                "gl": "cn",
            }
        )
        raw = _request_json(f"https://serpapi.com/search.json?{params}", timeout=self.timeout)
        items = (raw.get("organic_results") or [])[:max_results]
        return [
            SearchResult(
                provider="serpapi",
                query_text=query_text,
                result_rank=idx + 1,
                title=str(item.get("title") or ""),
                url=str(item.get("link") or ""),
                snippet=str(item.get("snippet") or ""),
                raw_result_json=item,
                search_time=_now_iso(),
            )
            for idx, item in enumerate(items)
        ]

    def _search_duckduckgo_html(self, query_text: str, *, max_results: int) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query_text, "kl": "cn-zh"})
        html = _request_text(f"https://duckduckgo.com/html/?{params}", timeout=self.timeout)
        results: list[SearchResult] = []
        title_matches = list(re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S))
        for index, title_match in enumerate(title_matches):
            url = title_match.group(1)
            parsed = urllib.parse.urlparse(url)
            if parsed.path.startswith("/l/"):
                query = urllib.parse.parse_qs(parsed.query)
                url = query.get("uddg", [url])[0]
            end = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(html)
            block = html[title_match.end() : end]
            snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', block, flags=re.S)
            snippet = ""
            if snippet_match:
                snippet = snippet_match.group(1) or snippet_match.group(2) or ""
            results.append(
                SearchResult(
                    provider="duckduckgo_html",
                    query_text=query_text,
                    result_rank=len(results) + 1,
                    title=_clean_html_fragment(title_match.group(2)),
                    url=_clean_html_fragment(url),
                    snippet=_clean_html_fragment(snippet),
                    raw_result_json={"html_fallback": True},
                    search_time=_now_iso(),
                )
            )
            if len(results) >= max_results:
                break
        return results


class SearXNGSearchClient:
    """Local SearXNG JSON search client.

    SearXNG is a self-hosted metasearch service. It is not an LLM and does not
    decide prices; this client only normalizes search result metadata.
    """

    def __init__(self, base_url: str | None = None, *, timeout: float = 8.0) -> None:
        self.base_url = (base_url or os.environ.get("SEARXNG_BASE_URL") or "http://localhost:8080").rstrip("/")
        self.timeout = timeout

    def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({"q": query, "format": "json"})
        raw = _request_json(f"{self.base_url}/search?{params}", timeout=self.timeout)
        items = raw.get("results") or []
        normalized: list[dict[str, Any]] = []
        for item in items[:max_results]:
            engine = item.get("engine") or ""
            if not engine and isinstance(item.get("engines"), list) and item.get("engines"):
                engine = item.get("engines")[0]
            normalized.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "content": str(item.get("content") or item.get("snippet") or ""),
                    "engine": str(engine or ""),
                    "score": item.get("score"),
                    "provider": "searxng",
                    "query_text": query,
                }
            )
        return normalized

    def search_results(self, query: str, max_results: int = 10) -> list[SearchResult]:
        rows = self.search(query, max_results=max_results)
        return [
            SearchResult(
                provider="searxng",
                query_text=query,
                result_rank=idx + 1,
                title=row["title"],
                url=row["url"],
                snippet=row["content"],
                raw_result_json=row,
                search_time=_now_iso(),
            )
            for idx, row in enumerate(rows)
        ]
