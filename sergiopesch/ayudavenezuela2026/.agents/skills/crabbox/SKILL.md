---
name: crabbox
description: Run AyudaVenezuela2026 checks in disposable Crabbox runners.
---

# Crabbox

Use Crabbox when a change needs clean remote proof, browser QA, performance evidence, or a long-running validation loop.

## Project Jobs

- Fast deterministic app build proof: `crabbox job run build`
- Live trusted-data refresh proof: `crabbox job run refresh-data`
- Full browser and imagery QA: `crabbox job run qa-e2e`
- Map performance proof: `crabbox job run perf-map`

Before a long session, prefer a warm runner when available:

```bash
crabbox warmup
crabbox job run --id <lease-or-slug> build
crabbox job run --id <lease-or-slug> qa-e2e
crabbox stop <lease-or-slug>
```

If a reused runner shows stale files, sync sanity failures, missing browser dependencies, or unexpected data drift, stop it and rerun on a fresh lease before debugging product code.

When reporting results, include the exact Crabbox job or command, the run status, and any collected artifact path under `.crabbox-artifacts/`.
