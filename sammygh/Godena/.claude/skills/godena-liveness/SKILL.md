---
name: godena-liveness
description: Daily check that Godena is actually serving results (not just "up"), and keep it awake. Use when asked "is Godena live", "check Godena", "godena health", or as a daily job. Written for any model, including cheap ones — follow the steps literally.
---

# Godena liveness check

Goal: confirm Godena really works end to end (search returns real agents), not just that the server responds. Report RED or GREEN with one line of evidence.

BASE = `https://sammygh-godena.hf.space`

## Steps (run in order)

1. **Server up?** Run:
   `curl -s -m 45 "$BASE/health"`
   - Contains `"Godena is live"` → server OK, continue.
   - No response / error → RED: "Space asleep or down." Hit `$BASE/` once more to wake it, wait 30s, retry. Still failing → escalate.

2. **Search actually returns data?** Run:
   `curl -s -m 25 "$BASE/api/search?q=lawyer+kampala&limit=3"`
   - `"count"` is 1–3 with agents → GREEN. Done.
   - `"count":0` → the database is asleep. This is the common failure.

3. **If count is 0**, check the database hostname:
   `curl -s -m 12 "https://dns.google/resolve?name=rgsykquesbiozrhvkvle.supabase.co&type=A"`
   - `"Status":3` (NXDOMAIN) → the Supabase project is PAUSED. RED. → Escalate to Samuel: "Supabase project paused, needs resume in dashboard. Data is safe." See `Desktop\Godena-strategy\RECOVERY.md`.
   - `"Status":0` with an IP but search still 0 → the Space is missing its `SUPABASE_KEY` secret. RED. → Escalate: "Space needs SUPABASE_KEY set."

4. **Keep-alive:** confirm the `Keep Alive` GitHub Action ran in the last hour:
   `gh run list --repo sammyghe/Godena --workflow keepalive.yml --limit 1`
   - If it hasn't run or is failing → note it; trigger once with `gh workflow run keepalive.yml --repo sammyghe/Godena`.

## Report format
`GREEN — search returns N results` OR `RED — <reason> — <action taken / escalation>`.

Do not change code or data in this skill. It is read-only + keep-alive only.
