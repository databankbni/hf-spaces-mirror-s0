---
name: godena-weekly
description: The weekly Godena operating cycle — liveness, demand gaps, seeding, verification, rating-loop health, and a status update, in one run. Use weekly, or when asked to "run godena ops", "godena weekly", "operate godena". For any model; runs the other godena-* skills in order.
---

# Godena weekly operating cycle

Run the five ops skills in this exact order and produce one report. Each skill is self-contained in `.claude/skills/` — follow them literally.

1. **`godena-liveness`** — is the product actually serving? Check `/health` (note the `database` field: "connected" vs snapshot fallback) and 3 live searches. If DB is offline: escalate to Samuel to resume Supabase, but note that search still works via snapshot.
2. **`godena-gaps`** — pull `/api/gaps`, confirm the top gaps, produce the next seed list (real agents only).
3. **`godena-seed`** — add the seed list via `/api/register` (idempotent; skip anything without a verifiable real contact). Skip if DB offline.
4. **`godena-verify`** — reachability-test a batch of ~20 listings; flag dead links/contacts.
5. **`godena-rate-loop`** — sample agents for `interactions_count`/`avg_rating`; report whether the flywheel is turning.

Then fetch **`/api/stats`** and write the weekly line into the report:

```
GODENA WEEKLY — <date>
Mode: db-connected | snapshot-fallback
Agents total: N (rated: R, claimed: C, snapshot: S)
Top gaps: ...
Seeded this week: N added / M dup / K skipped-unverifiable
Verify: X dead of Y checked
Flywheel: turning / not-yet (x% agents rated)
Escalations for Samuel: ...
```

If a strategy folder exists at `Desktop\Godena-strategy`, append the block to `STATE.md`. The one hard rule everywhere: **no fake data.**
