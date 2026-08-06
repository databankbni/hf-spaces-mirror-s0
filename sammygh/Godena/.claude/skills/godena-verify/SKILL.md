---
name: godena-verify
description: The "check" loop — test Godena listings for reachability and flag/demote dead or fake ones. Use when asked to "verify agents", "check listings", "clean up Godena", "quality check". For any model; follow literally.
---

# Godena verification (the check loop)

Goal: keep trust high by making sure listed agents are actually reachable and real. A dead contact returned as a live result is the fastest way to lose users.

BASE = `https://sammygh-godena.hf.space`

## Steps

1. **Pick a batch** to check: e.g. the top results for the 20 most common searches, or a category you're auditing:
   `curl -s "$BASE/api/search?q=<skill>+<location>&limit=5"` — collect the agents and their `slug`, contact, `website`, `source`.

2. **Test each contact** (read-only, do not message anyone):
   - `website` present → `curl -s -o /dev/null -w "%{http_code}" -m 15 "<website>"`. 200/301/302 = reachable; 000/404/5xx = dead.
   - `whatsapp` like `wa.me/<digits>` → check the number is a plausible E.164 (country code + 7–12 digits). (Do not send a message.)
   - AI-agent `website` → confirm it resolves and is the real product page, not a placeholder.

3. **Named-brand check** (airlines, banks, telcos): confirm the contact matches the brand's OFFICIAL public channel. If it's an unofficial/unknown number presented as the brand → this is a fake-data violation. Flag it hard.

4. **Record findings** — do NOT delete data. Produce a list of `slug | issue (dead link / dead number / unofficial brand contact / placeholder)`. For confirmed-dead or fake entries, hand the list to Samuel (or, if a demote/flag endpoint exists, apply the lowest-severity action). Prefer flagging over deleting.

## Output
`checked N, reachable X, dead Y, suspected-fake Z`, plus the flagged list with the specific issue for each. Never invent a "fix" — only report verifiable problems.
