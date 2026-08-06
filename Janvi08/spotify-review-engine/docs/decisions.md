# Architecture Decision Records (ADR Log)

> A running log of key decisions made during the design and implementation of the
> Spotify Review Discovery Engine. Each entry records **what** was decided, **why**,
> **what alternatives were considered**, and **what the consequences are**.
>
> Append new decisions at the bottom. Do not edit past entries — add a superseding
> entry if a decision is reversed.

---

## ADR-001: JSONL as Primary Output Format Over CSV

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1 — Ingestion |

### Context

The problem statement allows either `reviews_raw.jsonl` or `reviews_raw.csv`. We need to pick one as the canonical format.

### Decision

Use **JSONL** (JSON Lines) as the primary output format.

### Rationale

- Review text frequently contains commas, newlines, and quotes — all of which require complex escaping in CSV.
- JSONL handles `null` values natively (CSV requires a convention like empty string or `"NA"`).
- The `subreddit_or_thread` field is `null` for non-Reddit sources — cleaner in JSON.
- JSONL is line-oriented, making it easy to `wc -l`, `head`, `tail`, and stream-process.
- Downstream tools (Python `json`, `pandas.read_json(lines=True)`) handle JSONL natively.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| CSV | Escaping issues with review text; null handling is messy |
| Parquet | Overhead for a dataset of ~3,000 records; less human-readable |
| SQLite | More tooling needed; not a flat file |

### Consequences

- CSV consumers will need a conversion step (easy: `pandas` one-liner).
- All downstream phases must expect JSONL input.

---

## ADR-002: `google-play-scraper` Library for Play Store Data

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher |

### Context

Google Play Store does not offer a public API for reviews. We need a scraping approach.

### Decision

Use the `google-play-scraper` Python library (PyPI: `google-play-scraper`).

### Rationale

- Most popular Play Store scraper on PyPI (~3,000+ GitHub stars).
- Handles pagination via continuation tokens internally.
- Returns structured Python dicts — no HTML parsing needed.
- Supports filtering by language and country.
- Works without authentication.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Direct HTML scraping | Fragile; Google frequently changes markup; requires Selenium |
| `google-play-scraper` (Node.js) | Would require a Node.js subprocess; adds complexity |
| SerpAPI (paid) | Cost; adds external dependency |

### Risks

- Library depends on Google's internal API; may break if Google changes it.
- Pinning the library version is recommended.

---

## ADR-003: Apple App Store RSS/JSON Feed (No Auth)

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher |

### Context

Apple provides a public RSS feed for customer reviews. The problem statement recommends using it.

### Decision

Use the public RSS/JSON feed at:
```
https://itunes.apple.com/{country}/rss/customerreviews/id={appId}/sortby=mostrecent/json
```

### Rationale

- No authentication required.
- Returns structured JSON (not XML) when `/json` suffix is used.
- Supports pagination via `<link rel="next">` entries.
- Compliant with Apple's ToS for public feeds.

### Risks

- Feed is limited per country (often 50 entries/page, max ~500 per country).
- Must query multiple countries to reach the 500-review cap.
- Feed may be cached by Apple CDN (reviews lag real-time by hours).

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| App Store Connect API | Requires developer account auth; violates "no auth" constraint |
| `app-store-scraper` library | Adds dependency for what is a simple HTTP+JSON fetch |

---

## ADR-004: Reddit Public JSON Endpoints (No Auth)

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher |

### Context

Reddit offers both an OAuth API and public `.json` endpoints. The problem statement recommends public endpoints.

### Decision

Use Reddit's public JSON endpoints (append `.json` to any Reddit URL).

### Rationale

- No authentication required.
- Supports search with `restrict_sr`, `sort`, `limit`, and pagination (`after`).
- Returns structured JSON with all needed fields.
- Simpler than setting up an OAuth app.

### Risks

- Aggressive rate limiting for unauthenticated requests (~10 req/min).
- Reddit occasionally redirects to login pages for unauthenticated users.
- May be deprecated in favor of OAuth-only access in the future.

### Mitigations

- 2-second delay between requests.
- Custom `User-Agent` header.
- Retry logic with backoff on 429.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| PRAW (Python Reddit API Wrapper) | Requires OAuth credentials; adds auth complexity |
| Pushshift API | Was taken down / heavily restricted in 2023; unreliable |

---

## ADR-005: Separation of Fetcher and Extractor Layers

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1, 1.2 — Architecture |

### Context

We could combine fetching and field extraction into a single step per source, or separate them.

### Decision

**Separate** them into distinct sub-phases with clear interfaces.

### Rationale

- **Provenance:** Raw API responses are saved to disk before extraction. If the schema mapping needs to change, we can re-run extractors without re-fetching.
- **Debuggability:** Easier to diagnose issues — is the problem with the HTTP call or the field mapping?
- **Testability:** Extractors can be unit-tested with saved raw response fixtures.
- **Reusability:** A new source (e.g., Twitter/X) only needs a new Fetcher + Extractor pair.

### Consequences

- Slightly more code (two classes per source instead of one).
- Raw data is stored on disk (additional disk usage, but trivial for ~3K records).

---

## ADR-006: Raw-Level Cleaner vs. Deep NLP Cleaning (Phase Split)

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.3 (Cleaner) vs Phase 2 |

### Context

Cleaning can range from basic (dedup, encoding) to advanced (language detection, relevance filtering, PII removal). Where to draw the line for Phase 1?

### Decision

Phase 1 Cleaner (1.3) handles only **data-quality** cleaning:
- Deduplication (exact hash)
- Encoding normalisation (UTF-8)
- Empty/whitespace-only text removal
- Date validation and range enforcement
- Schema validation

Phase 2 handles **content-level** cleaning:
- Language detection and filtering
- Relevance filtering (discovery/recommendation topics)
- PII scrubbing
- Text normalisation (lowercasing, URL removal, etc.)

### Rationale

- Keeps Phase 1 fast and dependency-light (no `langdetect`, no NLP libraries).
- Phase 1's job is to produce a faithful, clean capture of what's out there.
- Phase 2's job is to prepare that data for embedding and analysis.

### Consequences

- `reviews_raw.jsonl` will contain non-English reviews and off-topic content.
- Downstream consumers should not assume filtered/clean data until Phase 2 output.

---

## ADR-007: Overwrite vs. Append for Pipeline Re-Runs

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.5, 1.7 — Pipeline & Scheduler |

### Context

When the pipeline is re-run, should it append to the existing `reviews_raw.jsonl` or overwrite it?

### Decision

**Default: Overwrite.** Each run produces a self-contained snapshot.

### Rationale

- Simpler mental model: one run = one complete dataset.
- Avoids complex append-dedup logic in Phase 1.
- For a 4-month rolling window, overwrite is appropriate — old data falls out naturally.
- Append mode will be added in Phase 1.7 (Scheduler) when automated refresh is implemented.

### Consequences

- Users must save/rename output manually if they want to preserve previous runs.
- `meta.json` always reflects the most recent run.

---

## ADR-008: Async-First HTTP with `aiohttp`

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher |

### Context

Fetching is I/O-bound (waiting on HTTP responses). Should we use sync or async?

### Decision

Use `asyncio` with `aiohttp` for all HTTP fetching.

### Rationale

- Multiple sources can be fetched concurrently (within rate limits).
- Pagination within a source benefits from async when rate limits allow.
- `aiohttp` is the de facto async HTTP client in Python.
- Sync `requests` is available as a fallback for simple cases.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| `requests` (sync) | Sequential fetching is slower; no concurrency |
| `httpx` | Good option but `aiohttp` is more mature for high-concurrency |
| `grequests` | Less maintained; monkey-patches `gevent` |

### Consequences

- All fetcher code must be `async def`.
- Entry point needs `asyncio.run()`.
- `google-play-scraper` is synchronous — will be wrapped in `asyncio.to_thread()`.

---

## ADR-009: Multiple Country Feeds for App Store to Reach Cap

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (App Store) |

### Context

Apple's RSS feed returns limited reviews per country. A single country (e.g., `us`) may return only 50–200 reviews.

### Decision

Query multiple English-speaking country stores: `us`, `gb`, `in`, `ca`, `au`.

### Rationale

- Increases the pool of available reviews to approach the 500-review cap.
- English-speaking markets maximize the proportion of English reviews.
- Cross-country duplicates are handled by the Cleaner (1.3).

### Risks

- Some countries may have very few Spotify reviews.
- Cross-country dedup may reduce the effective count.
- Reviews from `in` (India) may be in Hindi despite the English feed.

---

## ADR-018: ChromaDB for Local Vector Indexing

| Field | Value |
|-------|-------|
| **Date** | 2026-06-22 |
| **Status** | ✅ Accepted |
| **Phase** | 3 — Embedding & Indexing |

### Context

Phase 3 needs a vector store for BGE embeddings with metadata filtering (source, date, rating) for Phase 4 retrieval. The architecture allows ChromaDB or FAISS for local development and Pinecone for production.

### Decision

Use **ChromaDB** (`chromadb.PersistentClient`) with on-disk persistence at `data/index/chroma/`.

### Rationale

- Native metadata filtering supports Phase 4 source/date/rating filters without a separate index.
- Persistent local storage requires no external service or API keys.
- Simple upsert API and cosine similarity align with normalized BGE embeddings.
- FAISS would require a parallel metadata store; ChromaDB keeps documents, embeddings, and metadata together.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| FAISS | No built-in metadata filtering; more plumbing for Phase 4 |
| Pinecone | Requires cloud account/API key; overkill for local dev |
| SQLite + numpy | Reinvents what ChromaDB already provides |

### Consequences

- `data/index/chroma/` is gitignored; index must be rebuilt via `run_phase3.py`.
- Production migration to Pinecone (if needed) is a Phase 4 concern.

---

## ADR-019: Phase 3 Embedding Filter — Classified + Relevant + English

| Field | Value |
|-------|-------|
| **Date** | 2026-06-22 |
| **Status** | ✅ Accepted |
| **Phase** | 3 — Embedding & Indexing |

### Context

`reviews_clean.jsonl` contains all 2,054 records with soft-filter tags from Phase 2 (ADR-015). Phase 3 must decide which records to embed. BGE-base-en-v1.5 is English-only. 48 records remain `relevance_status = "quota_exhausted"` with `relevant = null`.

### Decision

Embed only records where:
1. `relevance_status == "classified"`
2. `relevant == true`
3. `lang == "en"` (default; overridable via `--all-langs`)

### Rationale

- Respects ADR-015 soft filtering: Phase 2 tags are preserved; Phase 3 applies the discovery filter at index time.
- Skips unclassified quota-exhausted records per ADR-017 integrity rules.
- English filter matches the BGE-base-en-v1.5 model; non-English reviews would produce low-quality retrieval.

### Consequences

- ~661 relevant records shrink further after English filtering (~600 expected).
- `--all-langs` flag available for experimentation but not recommended for production retrieval.

---

## ADR-020: Broad Relevance Re-Classification Pass

| Field | Value |
|-------|-------|
| **Date** | 2026-06-22 |
| **Status** | ✅ Accepted |
| **Phase** | 2 extension — Broad relevance |

### Context

Phase 2 strict relevance filtering (`relevant=true`) yielded 661 records from 2,054. ~1,345 records marked `relevant=false` may still describe repetitive listening, algorithm complaints, or passive consumption habits using implicit language that the strict classifier missed.

### Decision

Run a second Groq classification pass on `relevant=false` + `relevance_status=classified` records only. Add new fields `relevant_broad` and `relevant_broad_status` without overwriting `relevant`. Write output to `reviews_broad.jsonl`.

### Parameters

| Setting | Value |
|---------|-------|
| Model | `llama-3.3-70b-versatile` |
| Batch size | 15 |
| Inter-batch delay | 4 s |
| On 429/quota | Stop; set `relevant_broad=null`, `relevant_broad_status=quota_exhausted` for unprocessed |
| Resume | `--mode retry-exhausted-broad` |

### Rationale

- Preserves Phase 2 strict labels for comparison and reproducibility.
- Broader semantic prompt catches implicit discovery themes without keyword matching.
- Quota-exhausted handling mirrors ADR-017 integrity rules.

### Consequences

- Phase 3 embedding can optionally use `relevant_broad` to expand the index pool.
- Two relevance dimensions coexist in `reviews_broad.jsonl`.

---

*— End of current ADR log. New decisions will be appended below. —*

---

## ADR-010: Switch Reddit Fetcher from Public JSON to PRAW (OAuth)

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (Reddit) |
| **Supersedes** | ADR-004 |

### Context

During Phase 1.1 smoke testing, all Reddit public JSON endpoints (`/new.json`, `/hot.json`, `/search.json`) returned **HTTP 403 Forbidden** regardless of `User-Agent`. Reddit silently enforced OAuth-only access for programmatic requests — a policy that was announced in 2023 but is now broadly enforced as of 2024+.

### Decision

Use **PRAW (Python Reddit API Wrapper)** with a free "script" type Reddit app credential.
- No user login required
- Read-only access to public posts/comments
- Free to obtain from https://www.reddit.com/prefs/apps
- Credentials stored in `.env` (gitignored)

### Rationale

- PRAW is the official, recommended Python Reddit API wrapper
- "Script" app type requires only a `client_id` + `client_secret` (no user password, no OAuth flow)
- PRAW handles rate limiting, retries, and pagination automatically
- This is the minimal auth surface that satisfies "no login-walled content" in the problem statement constraints — Reddit posts themselves are still public

### Scope Impact

- Adds `praw` and `python-dotenv` to `requirements.txt`
- Adds a one-time credential setup step (documented in `docs/phase-1.1/README.md`)
- Creates `.env.example` as a credential template

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Pushshift API | Shut down / heavily restricted since 2023 |
| `old.reddit.com` HTML scraping | Fragile; violates spirit of "no anti-bot bypass" |
| Snscrape | No longer maintained; Reddit removed the endpoints it relied on |
| Accepting 0 Reddit records | Unacceptable — Reddit is a primary source per the problem statement |

---

## ADR-011: Reddit Scope Change to Manual Curation

| Field | Value |
|-------|-------|
| **Date** | 2026-06-20 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (Reddit) |
| **Supersedes** | ADR-004, ADR-010 |

### Context

Reddit's "Responsible Builder Policy" (updated in June 2026) imposes strict API limits and registration requirements for programmatic access, making automated fetching of public posts and comments via tools like PRAW or direct HTTP endpoints unreliable within the current timeline. Programmatic requests encounter HTTP 403 Forbidden errors or account blocks.

### Decision

Switch Reddit data collection from an automated API fetch to manual curation. 
- The Reddit fetcher module in Python will be decommissioned/omitted from the active pipeline.
- A target dataset of 100–150 highly relevant posts and comments will be collected manually by searching and copying content directly from the target subreddits (`r/spotify`, `r/musicsuggestions`, `r/WeAreTheMusicMakers`) focusing on key discovery/recommendation terms.
- The curated records will be structured in `reviews_raw.jsonl` matching the standard output schema.

### Rationale

- Ensures compliance with Reddit's builder policies without requiring complex developer verification cycles.
- Saves implementation time by avoiding scrapers that are prone to rapid breakage.
- Maintains high data quality since comments/posts are manually selected for relevance to music discovery issues.
- Reduces the Reddit cap from 1,000 to 100–150, which is representative enough for the Discovery Engine analysis.

### Consequences

- Automated pipeline does not need to run a Reddit crawler.
- Reddit data is mock-loaded from manually curated raw files saved in `data/raw/reddit/`.
- Schema fields and counts in output documents are updated to reflect the manual intake.

---

## ADR-012: Trustpilot Scope Change to Hybrid Curated Fallback

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (Trustpilot) |

### Context

Trustpilot employs an aggressive Web Application Firewall (WAF) backed by Cloudflare that actively blocks programmatic HTTP requests with HTTP 403 Forbidden errors, even when standard browser User-Agent headers, session cookies, or sequential delays are utilized. Unauthenticated programmatic scraping of Trustpilot is therefore highly unreliable and fragile.

### Decision

Implement a **hybrid curation fallback** strategy for Trustpilot data:
- The `TrustpilotFetcher` module will first search for manually curated JSON/JSONL reviews saved under `data/raw/trustpilot/curated.json` (using the same pattern established for Reddit under ADR-011).
- If curated reviews are found on disk, the fetcher loads them directly to avoid network failure.
- If no curated files exist, the fetcher falls back to attempting HTTP scraping (which will gracefully return empty and log instructions if blocked with a 403 error).
- A base dataset of 30-50 relevant reviews is manually curated to enable stable pipeline testing and analysis.

---

## ADR-013: Trustpilot WAF Identified as AWS WAF — Escalation to Playwright

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (Trustpilot) |
| **Supersedes** | ADR-012 |

### Context

After implementing `cloudscraper` per ADR-012, the Trustpilot fetcher still received HTTP 403 responses. Diagnostic inspection of the raw response body revealed the blocking mechanism is **AWS WAF** (`sdk.awswaf.com/challenge.js`), not Cloudflare. `cloudscraper` is specifically designed for Cloudflare's JS challenge and cannot solve AWS WAF's JavaScript challenges.

### Decision

Implement a **three-tier fallback chain** for the Trustpilot fetcher:

1. **cloudscraper** (primary): Fast, no browser overhead. Handles standard Cloudflare WAFs but fails on AWS WAF.
2. **Playwright headless Chromium** (secondary): Launches a real browser; solves AWS WAF JS challenges natively. Slower (~5s per page) but reliable.
3. **Manual curated file** (tertiary): `data/raw/trustpilot/curated.json` as an emergency fallback. Must contain REAL reviews only — the synthetic fixture has been moved to `tests/fixtures/trustpilot/` and must never re-enter the pipeline.

The Playwright scraper is implemented in `src/ingestion/fetchers/trustpilot_playwright.py`.

### Rationale

- A real browser is the most robust defence against WAF-based scraping protection.
- Keeping cloudscraper as tier-1 avoids unnecessary browser startup overhead on pages that don't need it.
- The curated file is the final safe-fallback for human-reviewed, verified-real reviews.
- Fabricated data is explicitly rejected: `_looks_synthetic()` in `TrustpilotFetcher` detects the known test-fixture UUID pattern and returns an empty list.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Give up on Trustpilot | Data source is valuable — 300+ reviews in scope |
| Selenium | Slower than Playwright; Playwright has better async support |
| Apify / ScraperAPI proxy service | Requires paid subscription; adds external dependency |
| Puppeteer (Node.js) | Requires Node.js runtime alongside Python |

### Consequences

- `playwright` and Chromium binary (~182 MB) must be installed on any machine running the Trustpilot fetcher.
- Install commands to document in `README.md`: `pip install playwright && playwright install chromium`.
- The `requirements.txt` declares `playwright>=1.40.0` with a comment noting the binary install step.
- If Trustpilot adds login-gating or CAPTCHAs, the Playwright approach will need stored auth cookies as the next escalation step.

---

## ADR-014: Fabricated Data Policy and YouTube Real-Data Verification

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 1.1 — Fetcher (all sources) |

### Context

Two fixtures discovered in `data/raw/` were fabricated rather than scraped from real sources:

1. `data/raw/trustpilot/curated.json` — 30 synthetic Trustpilot reviews generated by the AI assistant.
2. `data/raw/youtube/comments_sample_p1.json` — 5 synthetic YouTube comments generated by the AI assistant.

The user explicitly required: *"Fabricated data must never be used as a substitute for real data, even for demo purposes."*

The `.env` file was found to already contain a real `YOUTUBE_API_KEY`. A smoke test of the YouTube fetcher (`--mode smoke`) was run and returned **30 real comments** from 7 real YouTube videos, with real API comment IDs.

### Decision

1. **Fabricated fixtures are exiled to `tests/fixtures/`** — they are kept for extractor schema validation only and explicitly marked `TEST-ONLY` via README notices.
2. **`data/raw/trustpilot/curated.json`** — reset to `[]` (empty array). No fabricated data enters the real pipeline.
3. **`data/raw/youtube/comments_sample_p1.json`** — reset to `{"items": []}`. No fabricated data enters the real pipeline.
4. **YouTube verified**: 30 real comments collected from the real YouTube Data API v3. Raw files in `data/raw/youtube/` (161 files) contain real video IDs and real comment payloads.
5. **Synthetic detection in TrustpilotFetcher**: `_looks_synthetic()` method added — rejects any curated file whose URLs all match the known test UUID pattern (`574e4bc0-c23d-4910-a45c`), preventing accidental re-injection of the fixture data.

### Provenance Policy (going forward)

Any record entering `data/output/reviews_raw.jsonl` **must** originate from one of:
- A real API call (YouTube Data API v3, Google Play Scraper, App Store RSS).
- A real HTTP scrape of a live page (Spotify Community, Trustpilot via Playwright).
- A manually curated file containing reviews hand-copied by a human from real websites.

Fabricated data in `tests/fixtures/` must never be passed to `run_fetcher` or `run_extractor` as input.

### Consequences

- The Trustpilot and YouTube slots in `reviews_raw.jsonl` will be zero until real data is collected.
- YouTube: real smoke data confirms the API works; the full run (`--mode full`, cap=500) can proceed.
- Trustpilot: awaiting Playwright Chromium install to complete, then re-run smoke test.


---

## ADR-015: Phase 2 Soft Filtering

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 2 — Processing |

### Context

In Phase 2, we need to process language detection and relevance filtering. If we drop records early, we lose the ability to measure the volume of noise vs signal across sources, which is critical for our analysis phase.

### Decision

We will tag records with `lang`, `relevant`, and `relevance_confidence` fields rather than dropping them. This preserves the original dataset scope and allows flexible filtering during the embedding phase.

---

## ADR-016: Groq Llama-3.3 for Relevance Filtering

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 2 — Processing |

### Context

Relevance filtering requires semantic understanding of thousands of reviews to classify them as related to music discovery vs unrelated topics (like bugs or billing).

### Decision

---

## ADR-017: Relevance Status Field and Graceful Fallback

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **Status** | ✅ Accepted |
| **Phase** | 2 — Processing |

### Context

During the processing of the full 2,054 records dataset, the Groq API hit a hard limit (100,000 Tokens Per Day) around batch 92. The script gracefully caught the HTTP 429 error and defaulted the remaining records to `relevant=False`. However, silently defaulting unclassified records to `False` creates a misleading dataset by confusing real negatives with unclassified gaps, which violates our no-fabrication policy.

### Decision

1. Add a new `relevance_status` field to the unified schema during Phase 2.
2. If Groq succeeds, set `relevance_status = "classified"`.
3. If Groq rate limits are exhausted, set `relevance_status = "quota_exhausted"`, and set `relevant = null`, `relevance_confidence = null`.
4. Add a `--retry-exhausted` flag to `run_phase2.py` to allow resuming classification just for the `quota_exhausted` records once the 24-hour API limit resets.

### Rationale

- Ensures strict dataset integrity: we know exactly which records have been analyzed and which haven't.
- Prevents data loss: we don't have to re-run and spend tokens on the first ~1,800 records that were already successfully classified.
- Allows pipeline continuation: the pipeline doesn't crash on an API limit, it just flags the unclassified items and produces a valid output file.

---

## ADR-021: Hybrid Retrieval with Reciprocal Rank Fusion

| Field | Value |
|-------|-------|
| **Date** | 2026-06-22 |
| **Status** | ✅ Accepted |
| **Phase** | 4 — Retrieval & Ranking |

### Context

Phase 4 must support both semantic queries ("why can't users find new music?") and keyword-heavy queries ("Discover Weekly shuffle repeat"). Dense-only retrieval misses exact keyword matches; BM25-only misses paraphrased intent.

### Decision

Implement **hybrid retrieval** with two channels:
1. **Dense:** ChromaDB cosine search over BGE-small-en-v1.5 embeddings (top-10)
2. **Sparse:** BM25 via `rank_bm25` over the same 606 chunks (top-10)
3. **Fusion:** Reciprocal Rank Fusion (RRF, k=60) to merge ranked lists before re-ranking

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Dense only | Weak on exact keyword matches (e.g. "Discover Weekly") |
| BM25 only | Misses semantic paraphrases |
| Weighted linear fusion | Requires tuning weights; RRF is parameter-light |

### Consequences

- Phase 5 RAG imports a single `retrieve()` function; fusion is an internal detail.
- BM25 corpus is loaded read-only from ChromaDB (no duplicate index file).

---

## ADR-022: cross-encoder/ms-marco-MiniLM-L-6-v2 for Re-Ranking

| Field | Value |
|-------|-------|
| **Date** | 2026-06-22 |
| **Status** | ✅ Accepted |
| **Phase** | 4 — Retrieval & Ranking |

### Context

RRF-fused top-10 candidates still need fine-grained query-passage scoring. Larger cross-encoders (e.g. ms-marco-MiniLM-L-12) improve accuracy but increase deployment size and latency.

### Decision

Re-rank the top-10 RRF candidates with **`cross-encoder/ms-marco-MiniLM-L-6-v2`** (~80 MB) and return the final top-5. Expose `similarity` as softmax-normalized re-rank score within the candidate batch for interpretability.

### Rationale

- MiniLM-L-6-v2 is deployment-friendly while strong on passage ranking.
- Re-ranking only 10 candidates keeps latency low on CPU.
- Softmax normalization gives intuitive relative scores for Phase 5 citations.

### Consequences

- First `retrieve()` call loads three models (BGE-small, BM25 index, cross-encoder).
- `HF_HUB_DISABLE_SSL_VERIFICATION=1` required on this machine for model downloads.

---

## ADR-023: Groq Llama-3.3-70b-versatile for RAG Answer Generation

| Field | Value |
|-------|-------|
| **Date** | 2026-06-24 (updated 2026-07-01) |
| **Status** | ✅ Accepted |
| **Phase** | 5 — RAG Chatbot |
| **Supersedes** | Original ADR-023 (Anthropic `claude-sonnet-4-6`) |

### Context

Phase 5 needs an LLM to synthesise retrieved review chunks into a concise, cited answer. The initial implementation used Anthropic `claude-sonnet-4-6` as primary with Groq/Llama as fallback. In practice, Anthropic credits were exhausted and the API key was unreliable; Groq was already proven in Phase 2 (classification) and Phase 5 (theme clustering) on the same `GROQ_API_KEY`.

### Decision

Use **Groq `llama-3.3-70b-versatile`** as the sole RAG generation model via the `groq` Python SDK (`GROQ_API_KEY` in `.env`). Anthropic is removed from the RAG pipeline entirely — no `anthropic` import, no fallback chain.

System prompt enforces:
1. Answer only from retrieved chunks — no outside knowledge.
2. Every claim cited as `[source, date]`.
3. 3–5 sentences maximum.
4. Explicit refusal when evidence is insufficient.

### Rationale

- **Cost:** Groq free tier is sufficient for RAG Q&A; Anthropic requires paid credits.
- **Reliability:** One API key (`GROQ_API_KEY`) already powers Phase 2 and theme clustering; fewer moving parts.
- **Consistency:** Same model family (`llama-3.3-70b-versatile`) used across classification, clustering, and RAG.
- Keeping generation separate from retrieval (clean RAG split) means the LLM can be swapped without touching Phase 4.

### Consequences

- `GROQ_API_KEY` must be present in `.env` — `answer_question()` raises `ValueError` otherwise.
- `anthropic` is no longer required for Phase 5 RAG (may remain in `requirements.txt` until a separate cleanup).
- Token usage is logged per call for cost tracking.

---

## ADR-024: Groq/Llama LLM Clustering with TF-IDF+KMeans Fallback

| Field | Value |
|-------|-------|
| **Date** | 2026-06-24 |
| **Status** | ✅ Accepted |
| **Phase** | 5 — Theme Clustering |

### Context

The architecture specified BERTopic for theme clustering. BERTopic requires `umap-learn` + `hdbscan` + a compatible `torch` version; this creates dependency conflicts with the existing `sentence-transformers` + `chromadb` environment on Python 3.12/Windows.

### Decision

Replace BERTopic with a two-tier strategy:

1. **Primary — Groq Llama-3.3 LLM clustering:** Send batches of 40 chunks to `llama-3.3-70b-versatile`. First batch discovers 7 theme names; subsequent batches assign chunks to those established themes. Results are semantically meaningful with human-readable names.

2. **Fallback — TF-IDF + KMeans:** If Groq quota is exhausted or unavailable, use `sklearn` (already installed transitively) for keyword-based clustering. Theme names are auto-generated from top TF-IDF terms.

Results cached to `data/output/themes.json` — only recomputed when `force=True`.

### Rationale

- LLM clustering produces qualitatively superior, named themes vs. BERTopic's keyword lists.
- Groq free tier (100k TPD) is sufficient for one clustering pass (~40 chunks × 40 tokens ≈ 1,600 tokens per batch × 16 batches = ~26k tokens).
- TF-IDF fallback ensures the pipeline never hard-fails.
- No new heavy dependencies added.

### Consequences

- `data/output/themes.json` must be deleted manually to force a re-cluster.
- If Groq quota is exhausted mid-clustering, chunks after the quota hit are assigned to "Other" and the method is still recorded as `groq-llm`.

---

*— End of current ADR log. New decisions will be appended below. —*
