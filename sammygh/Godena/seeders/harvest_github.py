"""Harvest real AI agents/frameworks from GitHub by topic, sorted by stars
(public search API). Each repo -> agent with its real homepage or repo URL.
Run: python seeders/harvest_github.py"""
import json, time, urllib.request, urllib.parse
from _common import slugify, merge

TOPICS = [
    "ai-agents", "llm-agent", "mcp-server", "autonomous-agents", "ai-agent",
    "rag", "llm", "chatbot", "langchain", "agent-based-model", "generative-ai",
    "prompt-engineering", "vector-database", "ai-tools", "openai", "llmops",
    "text-to-speech", "text-to-image", "computer-vision", "nlp",
]

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "godena-harvester",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def harvest():
    out, seen = [], set()
    for topic in TOPICS:
        q = urllib.parse.quote(f"topic:{topic}")
        try:
            data = fetch(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=40")
        except Exception as e:
            print(f"  github {topic}: {e}")
            time.sleep(3)
            continue
        for repo in data.get("items", []):
            full = repo.get("full_name") or ""
            if not full or full in seen:
                continue
            seen.add(full)
            stars = int(repo.get("stargazers_count") or 0)
            if stars < 100:
                continue
            homepage = (repo.get("homepage") or "").strip()
            url = homepage if homepage.startswith("http") else repo.get("html_url")
            name = repo["name"].replace("-", " ").replace("_", " ").strip().title().replace(" ", "_")[:60]
            desc = (repo.get("description") or "").lower()
            out.append({
                "name": name,
                "slug": slugify(full),
                "skill_primary": "coding",
                "skill_tags": ["ai", "agent", "framework", "opensource"] + [w for w in desc.split() if len(w) > 3][:4],
                "website": url,
                "source": "platform_agents",
                "reputation_score": min(8 + stars // 2000, 13),
            })
        time.sleep(2)  # be gentle with the unauthenticated rate limit
    return out

if __name__ == "__main__":
    cands = harvest()
    added, total = merge(cands)
    print(f"GitHub: {len(cands)} candidates, {added} added, snapshot now {total}")
