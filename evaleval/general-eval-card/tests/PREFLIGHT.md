# Frontend preflight — correctness checks before a deploy

Run these before pushing a meaningful frontend change to the HF Space. They are
**opt-in and non-blocking** — nothing here gates `git push` or the default
`pnpm test`; they're a correctness gate you choose to run.

Guiding principle, learned the hard way: **"the page returns 200 / an SVG exists /
no console error" ≠ correct.** A model page can render cleanly and still be wrong —
a folded id 404s its data, a redirect points the wrong way, or a chart silently
shows only the current model. These checks assert content, not just liveness.

## How to run

```bash
export SNAPSHOT_URL="https://huggingface.co/datasets/evaleval/card_backend/resolve/main/warehouse/<id>"
#   (or file:///abs/path/to/warehouse/<id>)

# 1. Server-free data-contract checks (fast). Self-skips if SNAPSHOT_URL is unset.
pnpm test:integrity        # tests/redirect-integrity.test.ts (vitest)

# 2. Live-server page + chart-content checks (Playwright boots its own dev server).
pnpm test:e2e              # tests/e2e/frontend-preflight.spec.ts
```

Both need `SNAPSHOT_URL`. `test:e2e` starts `pnpm dev` against it automatically
(and reuses an already-running server on the port). Set `PORT` to override 3211.

## What each layer asserts

**`test:integrity` (vitest, server-free)** — against the warehouse snapshot:
- redirect map has 0 self-redirects, 0 chains/loops, every target is an addressable route;
- direction is folded→group (no addressable id is a redirect KEY — catches an inverted map);
- every redirect key is a known folded `raw_model_id`;
- no `raw_model_id` belongs to >1 group (the resolver's `LIMIT 1` fallback is unambiguous);
- no `models_view` row has NULL `raw_model_ids`.

**`test:e2e` (Playwright, live server)** — against the running app + `/api/comparison-index` ground truth:
- model / eval / developer pages render with HTTP <400, no client error text, no console errors —
  **including the regression sets**: folded model ids (from `raw_model_ids`) and percent-encoded
  developer names (e.g. `Mistral AI`);
- **100% of folded model ids resolve** (cheap status sweep — not a sample);
- comparison charts render real **peer bars** — counted in the DOM via `data-model-bar` /
  `data-bar-current`, NOT via `#n/m` badges (those come from the peer-*ranks* sidecar) or the
  "No peer scores" string (which never fires on the silent single-bar failure). Catches the
  "chart shows only the current model" bug. Also: 0 "Unknown Model" labels; the current model is
  not rendered as its own peer.

## The bug taxonomy these were built to catch

1. Folded model ids 404 — lookup didn't match `raw_model_ids`.
2. Inverted redirect map 301'd working group URLs to dead leaves.
3. Percent-encoded developer names (`Mistral%20AI`) 404'd (decoded-vs-encoded mismatch).
4. Comparison charts showed only the current model (peer lookup keyed on a non-matching id).
5. Peer bars showed "Unknown Model" (label read a field that isn't on the score rows).

The chart checks depend on the inert `data-model-bar` / `data-bar-current` attributes in
`components/benchmark-detail.tsx` — keep them.

## Known limitations (spot-check manually when touching the relevant code)

- The chart check only inspects the DEFAULT-rendered metric tab; a break isolated to a
  non-default tab isn't exercised.
- Eval/benchmark detail pages get liveness-only checking — their leaderboard content isn't
  asserted against the index the way model charts are.
- Error-marker strings are hardcoded UI copy; update them here if the copy changes.
- **Redirect preservation** (old/pre-rework URLs that used to redirect): not gated here. The
  warehouse-derived map only covers ids the producer folds into `raw_model_ids`; old base→variant
  spellings that aren't folded will 404. That's a stale-bookmark concern with an upstream
  (registry alias) fix, not a frontend gate.

## Enforcement

There is no CI today (this repo is an HF Space — deploy is `git push`; HF builds the Dockerfile
and does not run tests). So these are run by hand, by convention, like the `scripts/verify-*.mjs`
family. If we add hosted CI later (e.g. mirror to GitHub), `test:integrity` is the cheap,
server-free job to wire in first; `test:e2e` belongs in a separate, explicitly-owned job.
