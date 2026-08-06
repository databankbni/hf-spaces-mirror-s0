# Godena's registry is the open Git repo — no external database

Godena does **not** depend on any hosted database. The registry is `data/agents_snapshot.json` — an open, versioned index of real agents and services that ships inside this repo and loads into memory at startup. This is deliberate:

- **Unkillable.** No project to pause, no host to bill, no key to expire. If GitHub + the Space are up, search works. There is no separate database to go down.
- **Open by definition.** The registry is public and forkable — the data is as open as the code. Anyone can inspect, audit, or fork it.
- **Fast + free.** A few hundred KB in memory; searches never touch an external DB.

## How the index grows
- **Harvesters** (`seeders/`) pull real, verifiable entries from free public APIs — Hugging Face (AI Spaces), GitHub (agent repos), OpenStreetMap (real businesses with websites). Idempotent, real-URL-only, no fakes. Committed to the repo.
- **Community** — open a PR adding real agents to `data/agents_snapshot.json`, or POST to `/api/register`.
- Capped at ~1,200 in the in-repo snapshot for memory safety; larger runs live in the harvest output and can be paginated/sharded later.

## Reputation & ratings
The rating loop (`RATE 1-5`) and reputation scoring run in the app. For a launch/pre-scale stage, ratings that need durable write storage are the one thing a git-native registry doesn't persist across restarts — when durable per-agent write history is needed at scale, the drop-in is **Neon Postgres (free tier, auto-resumes on connect)** or Turso/libSQL. This is a scale decision, not a dependency: search and discovery never require it.

## Bottom line
The database question is closed: **Godena is git-native.** The open index is the product's source of truth, and it can't be paused, deleted, or held hostage.
