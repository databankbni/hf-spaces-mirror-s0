# Phase 1.1 — Fetcher: Runbook

> **What this is:** Step-by-step instructions for running, validating, and troubleshooting the Fetcher sub-phase of the Spotify Review Discovery Engine ingestion pipeline.

---

## Quick Start

### 1. Install dependencies

```bash
cd c:\Users\Abhishek kapoor\Spotify
pip install -r requirements.txt
```

### 2. Set up Reddit credentials (one-time)

Reddit's public endpoints now require free OAuth app credentials for programmatic access.

1. Go to **https://www.reddit.com/prefs/apps**
2. Scroll down → **"Create App"**
3. Fill in:
   - **Name:** `SpotifyReviewEngine`
   - **Type:** `script`
   - **Redirect URI:** `http://localhost:8080`
4. Click **"Create App"**
5. Copy the **client_id** (short string directly under the app name) and **client_secret** (labeled "secret")
6. Create a `.env` file in the project root:

```
# c:\Users\Abhishek kapoor\Spotify\.env
REDDIT_CLIENT_ID=paste_your_client_id_here
REDDIT_CLIENT_SECRET=paste_your_client_secret_here
```

> **Note:** This is a read-only "script" app — no user login, no password needed. The `.env` file is gitignored.

### 3. Validate config (dry run — no HTTP calls)

```bash
python -m src.ingestion.run_fetcher --mode smoke --dry-run
```

Expected output:
```
[DRY RUN] Configuration:
  Mode:    smoke
  Sources: ['play_store', 'app_store', 'reddit']
  Caps:    play_store=50, app_store=50, reddit=50
  Cutoff:  2026-02-20 (4 months back)
  Output:  .../data/raw

No HTTP calls made (--dry-run). Remove flag to run.
```

### 3. Run smoke test (50 records/source)

```bash
python -m src.ingestion.run_fetcher --mode smoke
```

**Expected time:** 3–8 minutes (Reddit is the bottleneck due to 2 s rate-limit delays)

**Expected output:**
```
==========================================================
  FETCH SUMMARY  |  mode=smoke  |  elapsed=187.3s
==========================================================
  Source            Collected     Cap  Fill %
  ------------------------------------------------------
  ✓ play_store             42      50   84.0%
  ✓ app_store              50      50  100.0%
  ✓ reddit                 38      50   76.0%
  ------------------------------------------------------
  TOTAL                   130
==========================================================

  Raw files saved to: .../data/raw
```

> **Note:** Play Store and Reddit may return fewer than 50 if:
> - The continuation token expires early (Play Store)
> - Fewer than 50 relevant posts exist within 4 months for some query pairs (Reddit)
> Both are expected and fine. The data is still valid.

### 4. Inspect raw output

```bash
# Check what was saved
ls data/raw/play_store/
ls data/raw/app_store/
ls data/raw/reddit/

# Peek at a file
python -c "import json; data=json.load(open('data/raw/play_store/page_1.json')); print(len(data), 'records'); print(list(data[0].keys()))"
```

### 5. Run full fetch (when smoke test passes)

```bash
python -m src.ingestion.run_fetcher --mode full
```

**Expected time:** 30–90 minutes (mostly Reddit rate-limiting)

---

## CLI Reference

```
usage: python -m src.ingestion.run_fetcher [-h] [--mode {smoke,full}]
                                           [--sources SOURCES]
                                           [--dry-run] [--verbose]

optional arguments:
  --mode {smoke,full}   'smoke' = 50/source (default), 'full' = production caps
  --sources SOURCES     Comma-separated: play_store,app_store,reddit (default: all)
  --dry-run             Print config and exit; no HTTP calls
  --verbose             Enable DEBUG logging (shows every page fetch)
```

**Examples:**
```bash
# Only Reddit, smoke mode
python -m src.ingestion.run_fetcher --mode smoke --sources reddit

# Only Play Store + App Store, full mode
python -m src.ingestion.run_fetcher --mode full --sources play_store,app_store

# Debug-level logging for troubleshooting
python -m src.ingestion.run_fetcher --mode smoke --verbose 2>&1 | tee logs/fetcher_debug.log
```

---

## Output Files

### `data/raw/play_store/`

| File | Contents |
|------|----------|
| `page_1.json` | First batch of raw reviews from `google-play-scraper` |
| `page_2.json` | Second batch (if pagination continued) |
| … | … |

Each file is a **JSON array** of review dicts. See [sample-output.md](./sample-output.md) for annotated examples.

### `data/raw/app_store/`

| File | Contents |
|------|----------|
| `page_us_1.json` | Page 1 of US App Store RSS feed |
| `page_gb_1.json` | Page 1 of UK App Store RSS feed |
| … | … |

Each file is the raw RSS/JSON feed response (includes `feed.entry[]` array).

### `data/raw/reddit/`

| File | Contents |
|------|----------|
| `search_spotify_discover_weekly_p1.json` | Search results for "discover weekly" in r/spotify |
| `comments_abc123.json` | Raw comments listing for post ID `abc123` |
| … | … |

---

## Caps Reference

| Source | Smoke | Full |
|--------|------:|-----:|
| Play Store | 50 | 1,500 |
| App Store | 50 | 500 |
| Reddit | 50 | 1,000 |

Caps are defined in [`src/ingestion/config.py`](../../src/ingestion/config.py) and can be adjusted without code changes.

---

## Troubleshooting

### Play Store returns 0 records

**Cause:** `google-play-scraper` hit Google's anti-bot detection.

**Fix:**
1. Wait 10–15 minutes and retry.
2. Try with `--verbose` to see the exact error.
3. Update the library: `pip install --upgrade google-play-scraper`.

### App Store returns very few records

**Cause:** Each country's RSS feed is limited (often 50 entries).

**Expected:** With 5 countries, up to 250 unique reviews. After cross-country dedup, may be less. This is normal.

**Fix if still too few:** Add more country codes in `config.py` → `APP_STORE_COUNTRIES`.

### Reddit is very slow

**Cause:** 2-second mandatory delay between all requests (rate-limit compliance).

**Expected:** In smoke mode with 3 subreddits × 8 terms, up to 48 search pages = ~96–192 seconds minimum just for delays.

**Fix:** In smoke mode, Reddit stops as soon as 50 records are collected — it won't exhaust all query combinations.

### Reddit returns 0 records

**Possible causes:**
1. Reddit returning a redirect to login page (EC-1.1.19) — look for `"Redirect detected"` in logs
2. All posts were outside the 4-month window
3. Rate limit was hit and all retries failed

**Fix:** Run with `--verbose` and look for specific error messages. Try manually: `curl "https://www.reddit.com/r/spotify/search.json?q=discover&restrict_sr=1&sort=new&limit=10&t=year" -H "User-Agent: test/1.0"`

### `ModuleNotFoundError: google_play_scraper`

```bash
pip install google-play-scraper
```

### `ModuleNotFoundError: aiohttp`

```bash
pip install aiohttp
```

---

## What Happens Next

Once the smoke test passes:

1. ✅ **Phase 1.1 (Fetcher)** — *you are here* — raw data in `data/raw/`
2. 🔜 **Phase 1.2 (Extractor)** — parse raw files into unified schema
3. 🔜 **Phase 1.3 (Cleaner)** — dedup, date enforcement, encoding fix
4. 🔜 **Phase 1.4 (Chunker)** — pass-through stub
5. 🔜 **Phase 1.6 (Output Writer)** — write `reviews_raw.jsonl` + `meta.json`
