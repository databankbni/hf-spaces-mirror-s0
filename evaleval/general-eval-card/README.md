---
title: Eval Cards
emoji: 📋
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 3000
short_description: Standardized evaluation cards for AI models and benchmarks
tags:
  - evaluation
  - benchmarks
  - ai-safety
  - visualization
---

# Eval Cards

A Next.js application for **viewing** AI evaluations. It is the reader frontend of the
Eval Cards platform: it does not author or store evaluation data itself — it renders a
materialised warehouse **view layer** produced upstream by the `eval_card_backend`
pipeline, and deploys to the Hugging Face Space `evaleval/eval-cards` (Docker runtime).

## Project Goals

The Eval Cards project aims to:
- **Standardize AI evaluation reporting** across different AI systems and models
- **Facilitate transparency** by providing detailed evaluation cards for AI systems
- **Enable comparative analysis** of AI capabilities and risks
- **Support research and policy** by consolidating evaluation data in an accessible format
- **Promote responsible AI development** through comprehensive risk assessment

## Architecture

This app is a **read-only consumer** of a snapshot. The producer (`eval_card_backend`)
canonicalizes raw evaluation data into a typed Parquet warehouse plus a Stage J view
layer (`*.parquet` view tables + JSON sidecars), and the frontend reads that snapshot at
runtime via DuckDB — it performs no identity resolution or aggregation of its own. The
view-layer column names match this app's TypeScript interfaces by contract (declared in
`lib/view-data.ts`).

Data is selected by the `DATA_BACKEND` env var. The current path is `DATA_BACKEND=v2`,
which reads a snapshot pointed at by `SNAPSHOT_URL` (a local `file://` path in dev, or an
`https://huggingface.co/datasets/.../resolve/<rev>/warehouse/<snapshot_id>` URL in prod).

## Run locally

This repo uses **pnpm** (pinned via `packageManager: pnpm@10.25.0`).

```bash
pnpm install
```

Run the dev server against a local Stage J snapshot (produced by `eval_card_backend canonicalise`):

```bash
DATA_BACKEND=v2 SNAPSHOT_URL=file:///abs/path/to/warehouse/<snapshot_id> pnpm dev
```

Build for production and run:

```bash
pnpm build          # runs scripts/cache-hf-data.mjs + scripts/build-eval-matrices.mjs, then next build
DATA_BACKEND=v2 SNAPSHOT_URL=<file:// or HF resolve URL> pnpm start
```

Run the test suite (Vitest):

```bash
pnpm test                  # full suite
pnpm test -- tests/<file>.test.ts   # a single test
```

## Configuration

| Env var | Purpose |
| --- | --- |
| `DATA_BACKEND` | Selects the data source. `v2` (a.k.a. `stage-j`) is the current view-layer backend. |
| `SNAPSHOT_URL` | **Required when `DATA_BACKEND=v2`** — points at a Stage J snapshot directory (`file://…` locally, or an HF `…/resolve/<rev>/warehouse/<snapshot_id>` URL in prod). |
| `SIDECAR_CACHE_DIR` / `SIDECAR_CACHE_TTL_SECONDS` / `SIDECAR_CACHE_PURGE` / `SIDECAR_BUILD_ID` | Tuning for the JSON-sidecar fetch cache. |
| `HF_DATA_*` (`HF_DATA_LOCAL_DIR`, `HF_DATA_OFFLINE`, `HF_DATA_CACHE_TTL_MS`, …) | Knobs for the legacy v1 Hugging Face data path; not used by the v2 backend. |

## Docker (recommended for Hugging Face Spaces)

A `Dockerfile` is included for deploying this app as a dynamic service on Hugging Face Spaces (Docker runtime).

Build the image locally:

```bash
docker build -t ai-eval-dashboard .
```

Run the container (expose port 3000):

```bash
docker run -p 3000:3000 -e HF_TOKEN="$HF_TOKEN" \
  -e DATA_BACKEND=v2 -e SNAPSHOT_URL="<HF resolve URL>" ai-eval-dashboard
```

Visit `http://localhost:3000` to verify.

### Deploy to Hugging Face Spaces

1. Create a new Space at https://huggingface.co/new-space and choose **Docker** as the runtime.
2. Push this repository to the Space Git (or upload files through the UI). The Space builds the Docker image using the included `Dockerfile` and serves the app on port 3000.

Notes:
- If your build needs native dependencies (e.g. `sharp`), the Docker image may require extra apt packages; update the Dockerfile accordingly.

## Background: evaluation framework

The evaluation categories surfaced in the cards trace to established standards — risk
categories from **NIST AI 600-1** (AI Risk Management Framework) and capability
categories from the **OECD AI Classification Framework** — for consistency with
international AI governance standards and interoperability with other evaluation systems.
