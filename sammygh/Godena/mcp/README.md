# Godena MCP server

Search the open agent network — AI agents and real-world services — from inside Claude or any MCP client.

## Tools
- `godena_search(query, limit=5)` — find agents/services ranked by reputation.
- `godena_register(name, skill, website, location, country)` — add a real agent.

## Install
```bash
pip install "mcp[cli]" httpx
```

## Use in Claude Desktop / Claude Code
Add to your MCP config:
```json
{
  "mcpServers": {
    "godena": { "command": "python", "args": ["/absolute/path/to/Godena/mcp/server.py"] }
  }
}
```
Then ask Claude: *"search Godena for an AI coding agent"* or *"find a lawyer in Kampala on Godena."*

No API key. Backed by the free public API at `https://sammygh-godena.hf.space`.

## Submit to registries (grows reach + gets ecosystem visibility)
- Smithery — https://smithery.ai/new
- PulseMCP — https://www.pulsemcp.com/submit
- mcp-get / awesome-mcp-servers PRs
- Glama — https://glama.ai/mcp/servers (auto-indexes public repos)

Source: https://github.com/sammyghe/Godena · Web: https://sammyghe.github.io/Godena/
