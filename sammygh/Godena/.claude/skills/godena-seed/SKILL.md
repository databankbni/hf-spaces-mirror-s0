---
name: godena-seed
description: Add real agents/businesses to Godena via the public API, idempotently and with no fake data. Use weekly or when asked to "seed", "add agents", "populate Godena", "add businesses/AI agents". For any model; follow literally.
---

# Godena seeding (add real agents)

Goal: grow the network by adding REAL agents/services. Every entry must have a real, verifiable contact. Idempotent — re-running never duplicates.

BASE = `https://sammygh-godena.hf.space`

## Input
A seed list (from `godena-gaps`, an OSM export, an AI-agent registry, or a verified business list). Each item needs at minimum: `name`, `skill`, `location`, `country`, and ONE real contact (`whatsapp` or `phone` or `website`).

## The hard rule
**No fakes.** If you cannot verify a real contact for an entry, skip it. For named brands (airlines, banks, telcos), use only the official public contact; if unsure, skip. A wrong number is worse than no listing.

## Steps (per agent)

1. **Register** via POST:
   ```
   curl -s -X POST "$BASE/api/register" -H "Content-Type: application/json" -d '{
     "name":"Grace_Legal_Nairobi","skill":"legal","location":"nairobi","country":"kenya",
     "whatsapp":"https://wa.me/254712345678","source":"seed"
   }'
   ```
   - `{"status":"live", ...}` → added.
   - `{"error":"name exists"}` → already there, skip (idempotent — this is fine).

2. **For AI agents** (HuggingFace/MCP/GPT-store/etc.), set `"skill":"ai"` plus the real skill (e.g. `coding`), a real `website`, and `"source"` to one of the AI sources (e.g. `huggingface_v3`, `mcp_smithery`, `replicate`, `openai_gpt_store`).

3. **Verify it landed**: `curl -s "$BASE/api/search?q=<skill>+<location>&limit=3"` and confirm the new agent appears.

4. **Batch**: loop the list, print `added / skipped(dup) / skipped(no-verifiable-contact)` counts at the end.

## Output
A summary: `N added, M duplicates skipped, K skipped for unverifiable contact`. List anything skipped for no-real-contact so a human can chase the real detail.
