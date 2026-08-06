# Godena — Multi-Model Handoff Queue

Standing task board so any model, in any session, picks up cold. **Protocol every session:**
1. Run the `godena-liveness` skill (`.claude/skills/godena-liveness/`).
2. Read this file, take the top task in YOUR lane.
3. Do it (tasks are sized ≤ 1 session, idempotent, resumable).
4. Update this file + `Desktop\Godena-strategy\STATE.md`.

## Model lanes
| Lane | Model | Owns |
|---|---|---|
| Final planning, audits, pivots | **Fable 5** (rare) | Strategy, quarterly review, this system's design |
| Orchestration, hard builds | **Opus 4.8** | This queue's execution, MCP polish, cross-cutting fixes |
| Build sprints | **Sonnet** | Search perf, endpoints, harvest expansion, SEO/analytics code |
| Ops + harvest + submissions | **Haiku** (cheap) | `godena-weekly` (product ops), run harvesters |
| **Growth + exposure** | **Haiku** (cheap) | `godena-growth-operator` agent — monitor, SEO, content, submissions, outreach (drafts only) |

## Live facts
- Web: https://sammyghe.github.io/Godena/ · API: https://sammygh-godena.hf.space
- Registry: **git-native** — `data/agents_snapshot.json`, ~8,300 real agents (AI models/tools + human services), cap 12,000. **Supabase dropped entirely** — do not re-add it as a dependency; `USE_SUPABASE=1` is opt-in only if a future decision reverses this.
- Repo auto-deploys to the HF Space on push to `main`. GitHub topics/description/homepage set (SEO pass done 2026-07-07).
- Growth engine: `.claude/skills/godena-{growth,monitor,seo,submit,content,outreach}` + `.claude/agents/godena-growth-operator.md`. Baseline exposure (2026-07-07): 1 star, 0 real web visitors — analytics not yet connected (see Blocked list).

## QUEUE (top = do next)

### Haiku (product ops)
- [ ] Weekly: run `godena-weekly`; append the report to STATE.md.
- [ ] Run harvesters monthly (`seeders/harvest_hf.py`, `harvest_github.py`, `harvest_osm.py`); commit the grown snapshot.

### Haiku (growth — run `godena-growth-operator` weekly)
- [ ] `godena-monitor` — real exposure dashboard (GitHub traffic, web visitors, listings, mentions).
- [ ] `godena-submit` — advance directory/MCP-registry submissions (Smithery, PulseMCP, Glama, There's-An-AI-For-That, aiagentsdirectory — tracker in the skill).
- [ ] `godena-content` + `godena-outreach` — draft the week's posts/outreach into `POSTS.md` using real monitor numbers. Samuel approves + sends.

### Sonnet (build)
- [ ] **PERF — TOP PRIORITY: bucket index.** At 8.3k, search scans the whole snapshot every query (~1s on the free HF CPU; ~40ms locally). Build `SNAPSHOT_BY_SKILL = {skill_primary: [agents]}` at load. In `search_agents`, when `skill_words` present, gather candidates only from the relevant skill buckets (map via skill_kws) + a bounded name pass, instead of merging all `SNAPSHOT_AGENTS`. Target <300ms. Test locally: `SUPABASE_KEY=x python -c "import app; app.search_agents('video ai')"` — results must stay identical. `USE_SUPABASE` unset = git-native path.
- [x] SKILL_SYNONYMS (+30 keys) + relevance ranking — DONE.
- [x] harvest_osm.py (8 African cities) — DONE.
- [ ] Optional (only if DB ever returns): `searches` table for a persistent gap map.

### Opus 4.8 (orchestrate)
- [ ] Verify the MCP server end-to-end in a real Claude client once published to a registry.

### Blocked on Samuel (surface every session)
- [ ] **Analytics** — create a free GoatCounter account (goatcounter.com, ~1 min, no card), code = `godena`, so `docs/index.html`'s snippet goes live. This turns on real visitor tracking — the key Path-A/B metric.
- [ ] Create **@GodenaHQ** (or next available) on X + fire the pinned tweet (`Godena-strategy/POSTS.md`).
- [ ] Set existing `TELEGRAM_TOKEN` on the Space → messaging live.
- [ ] Anthropic Console w/ `info@maji-safi.com` → submit (answers in `ANTHROPIC_APPLICATION.md`).
- [ ] YC submit by **Jul 27, 8pm PT** (`YC_APPLICATION.md`).
- [ ] Approve + post launch drafts (`POSTS.md`).
