---
name: godena-rate-loop
description: Watch that Godena is collecting real ratings after introductions and that reputation updates — the flywheel that makes ranking real. Use when asked about "ratings", "reputation loop", "is the flywheel working". For any model; follow literally.
---

# Godena rating loop monitor

Goal: confirm the trust flywheel is turning — that after Godena introduces an agent, real ratings come back and change the agent's reputation. Without this, ranking is just seed points.

BASE = `https://sammygh-godena.hf.space`

## Background
The bot shows results then invites a rating (reply `1`–`5` about the last result, or via `/api/rate`). Each rating updates the agent's running `avg_rating` and `interactions_count`, which feed `compute_reputation`. Anti-gaming: 5 ratings from one phone in 10 min are rejected as a burst.

## Steps

1. **Spot-check a rated agent**: pick an agent slug and read it:
   `curl -s "$BASE/api/agent/<slug>"` → look at `avg_rating`, `interactions_count`, `jobs_completed`, `repeat_contacts`, `computed_reputation`, `badges`.
   - If these are all 0 across most agents → the flywheel is NOT turning yet (no real ratings coming in). Report it.

2. **Confirm the rate endpoint works** (test-only, on a throwaway/known test slug, not a real business you'd distort):
   `curl -s -X POST "$BASE/api/rate" -H "Content-Type: application/json" -d '{"slug":"<test-slug>","rating":5,"rater_phone":"testonly"}'`
   → expect `{"status":"rated","new_avg_rating":...}`. A `"flagged"` response means burst protection fired.

3. **Health of the signal**: over time, healthy = a rising share of agents with `interactions_count > 0` and non-zero `avg_rating`. Track this number week over week.

## Output
`X of Y sampled agents have real ratings; flywheel = turning / not-yet`. If not-yet, the top fix is making sure the bot actually invites the rating after results (see the rating return-ping in app.py `handle()`), and that users are being routed back. Report to Samuel.

Do not spam real agents with test ratings — use only test slugs for endpoint checks.
