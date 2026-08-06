# ⚠️ TEST-ONLY FIXTURE — DO NOT USE FOR ANALYSIS

`comments_sample_p1.json` in this folder contains **fabricated YouTube comments**.
They were written by hand to validate the YouTube extractor schema and pipeline logic.

**These records MUST NOT flow into `data/output/reviews_raw.jsonl` or be included
in any theme analysis, model training, or user-facing reporting.**

## Why are they here?
The YouTube fetcher requires a valid `YOUTUBE_API_KEY` in `.env`.
Once the key is present, run:

```bash
python -m src.ingestion.run_fetcher --source youtube --mode smoke
```

This will call the real YouTube Data API v3 and write real comment JSON files
to `data/raw/youtube/` (e.g. `comments_<video_id>_p1.json`).

## Verification
After a successful real fetch, `data/raw/youtube/` should contain files whose
`items[].snippet.topLevelComment.id` values are real YouTube comment IDs
(alphanumeric strings starting with `Ug`), **not** the placeholder IDs in this
fixture file.
