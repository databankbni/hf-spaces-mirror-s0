---
title: DIM AI API
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# DIM AI API

FastAPI backend for the Supabase/Postgres/open-source RAG migration.

## Setup

From the repository root:

```bash
pnpm api:setup
pnpm supabase:start
pnpm api:test
pnpm api:dev
```

Smoke check:

```bash
pnpm api:health
```

## Remote API Smoke

For the current cloud demo, the frontend can point at the Hugging Face Space API and use the cloud Supabase database behind it. This path does not require local Docker, Colima, or `supabase start`.

Health:

```bash
curl --fail https://makhlugjafarov-dim-ai-api.hf.space/health
```

Query:

```bash
curl --fail -X POST https://makhlugjafarov-dim-ai-api.hf.space/api/query \
  -H "Content-Type: application/json" \
  --data '{
    "question": "Səfəvi dövləti haqqında qısa izah ver",
    "history": [],
    "locale": "az",
    "filters": { "subject": "history", "grade": 8, "limit": 3 },
    "subject": "history"
  }'
```

Expected result: `database` is `ok` on `/health`; `/api/query` returns an Azerbaijani answer, a numeric `confidence`, and citations for strong in-corpus questions. Weak-context questions may return low-confidence raw citations, so the frontend must suppress citation cards when confidence is below its weak-context threshold.

## Environment

Copy the example if you want a local `.env`:

```bash
cd apps/api
cp .env.example .env
```

Important variables:

- `DIM_AI_API_DATABASE_URL`: Supabase/Postgres connection string.
- `DIM_AI_API_SUPABASE_URL`: Supabase API URL.
- `DIM_AI_API_SUPABASE_JWT_SECRET`: required before protected user routes are production-ready.
- `DIM_AI_API_SUPABASE_SERVICE_ROLE_KEY`: backend/admin only, never exposed to the browser.
- `DIM_AI_API_EMBEDDING_MODEL_ID`: currently `bge-m3-dim-v1`.

## Ingestion Dry Run

The current ingestion pipeline can validate a local manifest, parse text/PDF sources, preserve page numbers, chunk content, and emit a quality report.

Real corpus files are ignored by git:

```text
data/books/manifest.yaml
data/books/*.pdf
data/books/derived/
```

Run:

```bash
pnpm ingest:dry-run
```

Load into local Supabase with the canonical BGE-M3 embedding contract:

```bash
pnpm ingest:load
```

The first embedding run may download `BAAI/bge-m3` model files from Hugging Face. It does not require auth for local development, but unauthenticated downloads can be slower or rate limited.

Run a retrieval smoke query after loading the corpus:

```bash
pnpm rag:smoke
```

For scanned PDFs, run OCR first. Example:

```bash
ocrmypdf --skip-text --deskew --clean -l aze+eng+rus \
  --sidecar data/books/derived/book.txt \
  data/books/source.pdf \
  data/books/derived/book.ocr.pdf
```

Then point `data/books/manifest.yaml` at the OCR PDF or sidecar-derived source.

Alternatively, point the manifest at the raw scanned PDF with `ocr.enabled: "auto"` or `true`.
When text coverage is below `expected.min_text_coverage_ratio` (or `0.8` by default), the ingestion parser uses OCRmyPDF/Tesseract to create ignored artifacts under `data/books/derived/` and parses the generated `.ocr.pdf`.
If `parser.text_extraction` is `ocr_done`, the parser trusts the configured PDF and skips OCR preparation.

## Supabase MCP

Local Supabase exposes MCP at `http://127.0.0.1:54321/mcp`.

This Codex session can reach it over HTTP JSON-RPC even though no native `mcp__supabase__...` tool namespace is currently registered. Useful checks:

```bash
curl -X POST http://127.0.0.1:54321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

```bash
curl -X POST http://127.0.0.1:54321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_tables","arguments":{"schemas":["public"],"verbose":false}}}'
```

## Tests

```bash
pnpm api:test
```

Current coverage includes:

- settings/env parsing
- redacted structured logging
- Supabase JWT verifier skeleton
- database health checks
- API health route
- ingestion manifest validation
- dry-run parser/chunker/report behavior

## Security Notes

- Keep service-role keys server-side only.
- Never log BYOK keys, authorization headers, JWTs, or raw provider secrets.
- User routes should use `app.auth.supabase_auth.get_current_user`.
- Corpus ingestion is admin-only; do not expose it as a public user route.
