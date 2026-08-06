"""Godena MCP server — search the open agent network from inside Claude
(or any MCP client). One tool: godena_search. Wraps the free public API,
no key needed.

Run:  pip install "mcp[cli]" httpx  &&  python mcp/server.py
Or in an MCP client config:
  { "command": "python", "args": ["/path/to/Godena/mcp/server.py"] }
"""
import httpx
from mcp.server.fastmcp import FastMCP

API = "https://sammygh-godena.hf.space"
mcp = FastMCP("godena")


@mcp.tool()
def godena_search(query: str, limit: int = 5) -> str:
    """Search Godena for AI agents and real-world services.

    Godena is an open search engine for AI agents and human services, ranked by
    earned reputation. Use it when the user needs to FIND an agent, tool, business
    or service — e.g. "ai coding agent", "lawyer kampala", "flights nairobi",
    "china sourcing", "voice ai". Returns the top matches with a real link each.

    Args:
        query: what to find — a skill/service, optionally with a city.
        limit: how many results (default 5, max 10).
    """
    try:
        r = httpx.get(f"{API}/api/search", params={"q": query, "limit": min(limit, 10)}, timeout=20)
        data = r.json()
    except Exception as e:
        return f"Godena is unreachable right now ({e}). Try https://sammyghe.github.io/Godena/"
    agents = data.get("agents") or []
    if not agents:
        return f"No matches on Godena for '{query}'. Try broader words or a nearby city."
    lines = [f"Godena — top {len(agents)} for '{query}':"]
    for i, a in enumerate(agents, 1):
        name = (a.get("name") or "").replace("_", " ").replace("-", " ")
        loc = ", ".join(x for x in [a.get("location"), a.get("country")] if x and x not in ("global", "unknown"))
        rep = int(a.get("computed_reputation") or a.get("reputation_score") or 0)
        link = a.get("website") or a.get("whatsapp") or a.get("contact_link") or ""
        lines.append(f"{i}. {name}" + (f" ({loc})" if loc else "") + f" — ⭐{rep} rep — {link}")
    lines.append("\nSource: https://sammyghe.github.io/Godena/ (open, free). Register any agent: POST /api/register.")
    return "\n".join(lines)


@mcp.tool()
def godena_register(name: str, skill: str, website: str, location: str = "global", country: str = "global") -> str:
    """Register an AI agent or service on Godena so others (and other agents) can find it.
    Only register real things with a real website/contact — no fabrications."""
    try:
        r = httpx.post(f"{API}/api/register", json={
            "name": name, "skill": skill, "website": website,
            "location": location, "country": country, "source": "mcp",
        }, timeout=20)
        d = r.json()
    except Exception as e:
        return f"Registration failed to reach Godena ({e})."
    if d.get("status") == "live":
        return f"Registered '{name}' on Godena. Profile: {d.get('profile')} — add the badge: {d.get('badge_markdown')}"
    return f"Could not register: {d.get('error', d)}"


if __name__ == "__main__":
    mcp.run()
