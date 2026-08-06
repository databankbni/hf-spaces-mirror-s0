# ⚠️ TEST-ONLY FIXTURE — DO NOT USE FOR ANALYSIS

`curated.json` in this folder contains **synthetic/fabricated Trustpilot reviews**.
They were written by hand to validate the extractor schema and pipeline logic.

**These records MUST NOT flow into `data/output/reviews_raw.jsonl` or be included
in any theme analysis, model training, or user-facing reporting.**

## Why are they here?
The real Trustpilot website is protected by Cloudflare WAF and blocks automated
scraping. The cloudscraper-based fetcher in `src/ingestion/fetchers/trustpilot.py`
attempts to bypass this; if it succeeds, real scraped data will be saved to
`data/raw/trustpilot/` and this fixture folder stays test-only.

## How to populate real data
Real Trustpilot reviews can be collected either by:
1. Running the updated fetcher (`python -m src.ingestion.run_fetcher --source trustpilot --mode smoke`)
2. Manually copying reviews from https://www.trustpilot.com/review/www.spotify.com
   into `data/raw/trustpilot/curated.json` following the schema in `docs/architecture.md`.
