---
name: godena-seo
description: Make Godena findable by search engines and AI assistants — GitHub topics/description, page meta + structured data, sitemap, keyword hygiene. Use when asked about "godena seo", "make godena findable", "discoverability", or during the weekly growth cycle. For any model; follow literally.
---

# Godena discoverability (SEO for humans + AIs)

Goal: a stranger googling "search engine for AI agents" (or an AI asked "where can I find AI agents") should surface Godena.

## Already applied (verify, don't undo)
- GitHub **topics** (14): ai-agents, agent-discovery, mcp, search-engine, ai-directory, africa, whatsapp-bot… → `gh api repos/sammyghe/Godena --jq .topics`
- **description** + **homepage** → the live site. Verify with `gh api repos/sammyghe/Godena --jq '{description,homepage}'`.
- `docs/index.html` has OpenGraph + Twitter-card meta + JSON-LD `WebSite`/`SoftwareApplication`.
- `docs/sitemap.xml` exists; `/llms.txt` live (AI-readable).

## Maintain / improve
1. **Keywords in the right places** (natural, not stuffed): the `<title>`, `<meta name=description>`, the README first paragraph, and H1 should contain "search engine for AI agents and services". Check they still do.
2. **Fresh signal:** GitHub ranks active repos — the weekly growth commits already help. Keep the repo active.
3. **Backlinks are the real lever:** every directory listing + dev.to article + registry entry (see `godena-submit`) is a backlink. That's what actually moves Google rank. Prioritize submissions over meta-tweaks.
4. **AI discoverability:** keep `/llms.txt` and `/.well-known/agent-card.json` accurate (they're how LLMs/agents find Godena). Verify they return 200 and current info.

## Verify
`gh api repos/sammyghe/Godena --jq '{topics,description,homepage}'` · `curl -s https://sammyghe.github.io/Godena/sitemap.xml -o /dev/null -w "%{http_code}\n"` · view-source the page for `og:` + `application/ld+json`.
