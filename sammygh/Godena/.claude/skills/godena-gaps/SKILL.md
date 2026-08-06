---
name: godena-gaps
description: Read Godena's unmet-demand map and turn it into the next seed list — what people search for that returns nothing. Use weekly, or when asked "what should we add to Godena", "demand map", "godena gaps". For any model; follow literally.
---

# Godena demand gaps → next seed list

Goal: find what users search for that Godena can't answer, and produce a concrete list of agents to add next. This is the to-do list that keeps the network useful.

BASE = `https://sammygh-godena.hf.space`

## Steps

1. **Pull the live gap log:**
   `curl -s -m 25 "$BASE/api/gaps?limit=30"`
   Each entry is `{query, searches}` — a search that returned nothing, and how many times.
   (Note: the gap log is in-memory and resets when the Space restarts, so recent gaps matter most.)

2. **Sanity-check the top gaps** by re-running each as a search to confirm it's still empty:
   `curl -s -m 20 "$BASE/api/search?q=<query>&limit=3"` → confirm `"count":0`.

3. **Group the confirmed gaps** into: (a) a skill/category with no coverage, (b) a location with no coverage, (c) an AI-agent category with no coverage.

4. **Produce the seed list**: for each top gap, list 3–10 REAL agents/businesses to add — with a real, verifiable contact each (WhatsApp/phone/website). Do NOT invent entries. If you can't verify a real contact, leave it out.

5. **Hand off** the seed list to the `godena-seed` skill (or to Samuel for approval on named brands).

## Output
A short table: `gap query | searches | proposed real agents to add (with source of the contact)`. Flag any gap you could not fill with verifiable real data.
