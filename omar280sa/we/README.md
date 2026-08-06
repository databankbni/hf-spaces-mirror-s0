---
title: Personal Image Upload Service
emoji: 🖼️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.19.0
app_file: app.py
pinned: false
---
# Personal Image Upload Service

A tiny, reliable tool: upload an image, it gets compressed to WebP
(targeting ~100 KB), uploaded to Cloudinary, and you get a direct URL back.

No auth, no database, no Docker, no Telegram/webhooks — just a single
FastAPI app with a plain HTML/CSS/JS front end.

---

## 1. Requirements

- Python 3.11
- A Cloudinary account (free tier works) — you can add up to 3 for
  automatic failover

---

## 2. Install

```bash
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Configure Cloudinary (environment variables)

Credentials are **never** stored in code or `settings.json` — only in
environment variables. At minimum, set account 1. Accounts 2 and 3 are
optional and used as automatic fallbacks if account 1 fails.

```bash
export CLOUDINARY_CLOUD_NAME_1="your_cloud_name"
export CLOUDINARY_API_KEY_1="your_api_key"
export CLOUDINARY_API_SECRET_1="your_api_secret"

# Optional second account
export CLOUDINARY_CLOUD_NAME_2="..."
export CLOUDINARY_API_KEY_2="..."
export CLOUDINARY_API_SECRET_2="..."

# Optional third account
export CLOUDINARY_CLOUD_NAME_3="..."
export CLOUDINARY_API_KEY_3="..."
export CLOUDINARY_API_SECRET_3="..."
```

On Windows (PowerShell):

```powershell
$env:CLOUDINARY_CLOUD_NAME_1="your_cloud_name"
$env:CLOUDINARY_API_KEY_1="your_api_key"
$env:CLOUDINARY_API_SECRET_1="your_api_secret"
```

Tip: for local development you can put these in a `.env` file and load
them with `export $(cat .env | xargs)` before running the server, or
use a tool like `direnv`.

---

## 4. Adjust default settings (optional)

Edit `settings.json` — no restart required, it's read fresh on every request:

```json
{
    "quality": 80,
    "target_size": 100,
    "max_width": 1200,
    "format": "webp"
}
```

- `quality` — starting WebP quality (1-100) before compression kicks in
- `target_size` — desired max output size in KB
- `max_width` — images wider than this get downscaled (never upscaled)

The web UI lets you override `quality`, `target_size`, and `max_width`
per upload via the sliders/fields; if you don't touch them, the values
in `settings.json` are used.

---

## 5. Run

```bash
uvicorn app:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

---

## 6. How it works

1. You pick an image and hit Upload.
2. The server saves it to a temp file.
3. `compress.py` converts it to WebP, resizes it if too wide, and steps
   quality down (in increments of 5, down to a floor of 20) until it's
   at or under the target size.
4. `upload.py` uploads the compressed file to Cloudinary, trying each
   configured account in order until one succeeds.
5. The temp files are deleted, and you get back a JSON response with
   the final URL, which account it went through, and the final size.
6. Copy the URL with one click.

---

## 7. API

### `GET /`
Serves the upload page.

### `POST /upload`
Multipart form fields:

| Field         | Required | Description                          |
|---------------|----------|---------------------------------------|
| `file`        | yes      | The image file                        |
| `quality`     | no       | Overrides `settings.json`             |
| `target_size` | no       | Overrides `settings.json` (KB)        |
| `max_width`   | no       | Overrides `settings.json` (px)        |

Response:

```json
{
    "success": true,
    "url": "https://res.cloudinary.com/.../image.webp",
    "provider": "Cloudinary #2",
    "size_kb": 84.5
}
```

On failure:

```json
{
    "success": false,
    "error": "All Cloudinary accounts failed. Details: ..."
}
```

---

## 8. Project structure

```
project/
  app.py            # FastAPI routes
  compress.py        # WebP conversion + compression logic
  upload.py          # Cloudinary upload with account failover
  config.py          # settings.json + Cloudinary account loading
  settings.json       # default quality/target_size/max_width/format
  requirements.txt
  templates/
    index.html
  static/
    style.css
    script.js
```

---

## 9. Notes

- Temp files are always cleaned up, even if compression or upload fails.
- A failed or invalid upload never crashes the server — it just
  returns a JSON error.
- If no Cloudinary accounts are configured, `/upload` will return a
  clear error instead of crashing.
