# Godena — Operations Runbook

One page so any model (including cheap ones) or teammate can keep Godena running with zero prior context. Detailed step-by-step tasks live in `.claude/skills/godena-*/`.

## What Godena is
An open agent network: people text a need over WhatsApp/Telegram, Godena returns the top 3 matching agents/services ranked by reputation, then steps back. FastAPI on HuggingFace Spaces + Supabase Postgres.

## Live endpoints
- App: `https://sammygh-godena.hf.space`
- Health: `GET /health` → should return `{"status":"Godena is live", ...}`
- Search: `GET /api/search?q=lawyer+kampala&limit=3`
- Gaps (unmet demand): `GET /api/gaps`
- WhatsApp: +256761966728 · Telegram: @GodenaBot

## The reliability model (READ THIS — it's why it died before)
Both tiers are free and go idle:
- The HuggingFace Space **sleeps** when it gets no traffic.
- The Supabase project **auto-pauses** after ~7 days idle, which deprovisions its API hostname (search then returns 0 even though data is intact).
The fix already in place: the `Keep Alive` GitHub Action (`.github/workflows/keepalive.yml`) pings `/health` and runs a search every ~10 min. This keeps the Space awake, and the search keeps Supabase warm.
- **Backup:** also register an external pinger (cron-job.org or UptimeRobot, free) on `/health` every 10 min — GitHub disables cron workflows after 60 days of repo inactivity.
- If search returns 0 across the board: the Supabase project (`rgsykquesbiozrhvkvle`, "godena") is likely paused. Resume it in the Supabase dashboard; data is intact (3,300+ agents). See `Desktop\Godena-strategy\RECOVERY.md`.

## The daily/weekly jobs (run these skills)
| When | Skill | Does |
|------|-------|------|
| Daily | `godena-liveness` | Confirms the app + DB are actually serving results; nudges keep-alive |
| Weekly | `godena-gaps` | Reads unmet demand and produces the next seed list |
| Weekly | `godena-seed` | Adds real agents (from a source list) via the API — never fakes |
| Weekly | `godena-verify` | Tests listings for reachability; flags/demotes dead or fake ones |
| Ongoing | `godena-rate-loop` | Watches that ratings are being collected and averages update |

## The one hard rule
**No fake data.** Never invent a contact, rating, or agent. Named brands (airlines, banks, telcos) get only their real, official, publicly verifiable contact — otherwise mark unofficial or leave out. Fake data is worse than an empty result and breaks the whole trust model.

## Escalate to Samuel when
- Search is 0 and the Supabase project won't resume.
- A secret needs setting on the HF Space (needs an HF token he controls).
- Anything requires spending money (Supabase Pro, WhatsApp Cloud API, a domain).
