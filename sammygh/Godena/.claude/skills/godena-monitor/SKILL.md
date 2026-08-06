---
name: godena-monitor
description: Read-only exposure dashboard for Godena — GitHub stars/traffic, web visitors, directory & MCP-registry listings, mentions, search rank. Use weekly or when asked "how is Godena doing", "godena exposure", "godena metrics", "is anyone using it". For any model; read-only, follow literally.
---

# Godena exposure monitor (read-only)

Goal: one honest dashboard of whether anyone is finding/using Godena. Compare to last week. Never fabricate numbers — if a source is unavailable, write "n/a".

## Baseline (2026-07-07): 1 star, 0 forks, 0 repo views/14d, 0 topics(now 14), no referrers, ~0 real web visitors.

## Steps (all read-only)

1. **GitHub** (authed `gh`):
   `gh api repos/sammyghe/Godena --jq '{stars:.stargazers_count,forks:.forks_count,watchers:.subscribers_count}'`
   `gh api repos/sammyghe/Godena/traffic/views --jq '{views:.count,uniques:.uniques}'`  (ignore `clones` — mostly CI/our own)
   `gh api repos/sammyghe/Godena/traffic/popular/referrers`  (who links to us)

2. **Product live + index size:** `curl -s https://sammygh-godena.hf.space/api/stats` (agents count) and `curl -s -o /dev/null -w "%{http_code}" https://sammyghe.github.io/Godena/` (site 200?).

3. **Web visitors:** read the analytics dashboard (Cloudflare/GoatCounter) once it's connected. If not connected yet → "analytics not set up (Samuel action)".

4. **Directory / registry listings** (has it been accepted?): check each from `godena-submit`'s tracker — is Godena live on There's-An-AI-For-That, aiagentsdirectory, Smithery, PulseMCP, Glama? Mark ✅/⏳/❌.

5. **Mentions / search rank** (spot-check, WebSearch if available): search `Godena AI agent search` and `site:github.com Godena` — does it surface? Any X/HN/Reddit mentions?

## Output (append to `Desktop\Godena-strategy\STATE.md`)
```
GODENA EXPOSURE — <date>
GitHub: stars N (+Δ) · forks N · views/14d N (uniques U)
Web: visitors N/week (+Δ) · site 200 · agents 8300
Listings: TAAFT ✅/❌ · Smithery ✅/❌ · PulseMCP ✅/❌ · ...
Mentions: <found / none>
Verdict: green (growing) / flat / needs a push
Next: <top 1-2 actions for godena-submit/content/outreach>
```
The only metrics that decide Path A vs B: **return visitors + searches/day.** Watch those hardest.
