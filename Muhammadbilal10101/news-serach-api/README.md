---
title: Halo SearXNG
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8080
pinned: false
license: mit
---

# Halo SearXNG (Hugging Face Space)

Self-hosted meta-search for **Halo Manager → news brief** (`fetch_news`).

Exposes a JSON HTTP API:

```http
GET /search?q=anthropic&format=json&categories=news
```

## Upload this folder to Hugging Face

1. Create a new Space: [huggingface.co/new-space](https://huggingface.co/new-space)
   - **SDK:** Docker
   - **Visibility:** Private recommended (API backend for Halo)
2. Clone the Space repo locally, then copy **all files from this `hugging_face/` folder** into the repo **root** (not nested inside another folder).
3. In Space **Settings → Secrets**, add:
   - `SEARXNG_SECRET` — random 64-char hex (`openssl rand -hex 32`)
4. Commit and push. HF builds from `Dockerfile` automatically.

Expected repo layout at Space root:

```
Dockerfile
README.md          ← this file (with YAML front matter above)
config/
  settings.yml
scripts/
  test-api.ps1
  test-api.sh
```

## After deploy

Your Space URL:

```text
https://<username>-<space-name>.hf.space
```

Test in browser or:

```powershell
.\scripts\test-api.ps1
```

```bash
bash scripts/test-api.sh
```

Manual curl:

```bash
curl "https://<username>-<space-name>.hf.space/search?q=anthropic&format=json&categories=news"
```

You should get JSON with a `results` array.

## Halo integration

In Halo `.env`:

```env
SEARXNG_BASE_URL=https://<username>-<space-name>.hf.space
```

Wire `fetch_news` to:

```http
GET /search?q={query}&format=json&categories=news
```

## Config notes

| Setting | Why |
|--------|-----|
| `app_port: 8080` | SearXNG listens on 8080 (HF default is 7860) |
| `search.formats` includes `json` | Required — without it, `format=json` returns **403** |
| `server.limiter: false` | Avoids bot blocking for Halo server-to-server calls |
| `SEARXNG_SECRET` | Set in HF Secrets — do not commit a real key |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Space stuck on Building / 503 | Confirm `app_port: 8080` in README YAML, SearXNG on 8080, `bind_address: 0.0.0.0` |
| `format=json` → 403 | Ensure `json` is under `search.formats` in `config/settings.yml` |
| Empty results | Try a broader query or drop `categories=news` |
| Cold starts | Free HF Spaces sleep when idle — use paid hardware or a VPS for production |

Logs: Space **Logs** tab, or locally `docker logs` when testing the image.

## Local test (before upload)

From this folder:

```bash
docker build -t halo-searxng-hf .
docker run --rm -p 8080:8080 -e SEARXNG_HOSTNAME=localhost -e SEARXNG_SECRET=dev-secret-key-change-me halo-searxng-hf
```

Then open http://localhost:8080 or run `.\scripts\test-api.ps1`.
