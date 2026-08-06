# Architecture: Spotify Review Discovery Engine

> **Version:** 1.0 — Phase 1 (Ingestion) Detailed Design
> **Last updated:** 2026-06-20
> **Scope:** Full pipeline overview with deep-dive into Phase 1

---

## High-Level Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SPOTIFY REVIEW DISCOVERY ENGINE                      │
│                                                                         │
│  Phase 1          Phase 2         Phase 3        Phase 4        Phase 5 │
│ ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────┐   ┌───────┐│
│ │INGESTION │──▸│PROCESSING │──▸│EMBEDDING │──▸│RETRIEVAL │──▸│ RAG   ││
│ │& STORAGE │   │& CLEANING │   │& INDEXING│   │& RANKING │   │CHATBOT││
│ └──────────┘   └───────────┘   └──────────┘   └──────────┘   └───────┘│
│                                                                         │
│  reviews_raw     reviews_       chunks +        vector          Q&A +   │
│  .jsonl +        clean.jsonl    embeddings      search          themes  │
│  meta.json                      (BGE)           index                   │
└─────────────────────────────────────────────────────────────────────────┘
```

| Phase | Name | Primary Output | Status |
|-------|------|----------------|--------|
| 1 | Ingestion & Storage | `reviews_raw.jsonl`, `meta.json` | **Current focus** |
| 2 | Processing & Cleaning | `reviews_clean.jsonl` | Future |
| 3 | Embedding & Indexing | Vector store (BGE embeddings) | Future |
| 4 | Retrieval & Ranking | Search API / ranked results | Future |
| 5 | RAG Chatbot & Analysis | Conversational Q&A + theme reports | Future |

---

## Directory Structure (Target State for Phase 1)

```
Spotify/
├── docs/
│   ├── problemstatement.md
│   └── architecture.md            ← this file
├── src/
│   └── ingestion/
│       ├── __init__.py
│       ├── config.py              ← centralised constants & settings
│       ├── fetchers/
│       │   ├── __init__.py
│       │   ├── base_fetcher.py    ← abstract base class
│       │   ├── play_store.py      ← Google Play Store fetcher
│       │   ├── app_store.py       ← Apple App Store fetcher
│       │   └── reddit.py          ← Reddit fetcher
│       ├── extractors/
│       │   ├── __init__.py
│       │   ├── base_extractor.py  ← abstract base class
│       │   ├── play_store.py      ← Play Store field extractor
│       │   ├── app_store.py       ← App Store field extractor
│       │   └── reddit.py          ← Reddit field extractor
│       ├── cleaners/
│       │   ├── __init__.py
│       │   └── raw_cleaner.py     ← light pre-clean (dedup, encoding)
│       ├── chunkers/              ← placeholder for Phase 2
│       │   ├── __init__.py
│       │   └── text_chunker.py
│       ├── scheduler.py           ← optional refresh / cron logic
│       └── pipeline.py            ← orchestrator (runs full ingestion)
├── data/
│   ├── raw/                       ← per-source raw API responses (provenance)
│   │   ├── play_store/
│   │   ├── app_store/
│   │   └── reddit/
│   └── output/
│       ├── reviews_raw.jsonl      ← ★ primary deliverable
│       └── meta.json              ← ★ collection summary
├── tests/
│   └── ingestion/
│       ├── test_fetchers.py
│       ├── test_extractors.py
│       └── test_cleaners.py
├── requirements.txt
└── README.md
```

---

## Phase 1: Ingestion & Storage — Detailed Sub-Phase Breakdown

### Data Flow Within Phase 1

```
                  Phase 1 Internal Flow
                  ═════════════════════

  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │  1.1 FETCHER │───▸│1.2 EXTRACTOR │───▸│ 1.3 CLEANER  │
  │              │    │              │    │  (raw-level)  │
  │ HTTP calls   │    │ Parse JSON/  │    │ Dedup, encode │
  │ per source   │    │ HTML → dict  │    │ validate      │
  └──────────────┘    └──────────────┘    └──────┬───────┘
                                                 │
                                                 ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ 1.6 META     │◂───│1.5 PIPELINE  │◂───│ 1.4 CHUNKER  │
  │  WRITER      │    │ ORCHESTRATOR │    │ (stub/future)│
  │              │    │              │    │              │
  │ meta.json    │    │ Runs 1.1→1.4 │    │ Pass-through │
  │ per-source + │    │ per source,  │    │ for Phase 1  │
  │ combined     │    │ merges output│    │              │
  └──────────────┘    └──────────────┘    └──────────────┘

  ┌──────────────┐
  │1.7 SCHEDULER │  (optional — manual trigger first,
  │              │   cron-based refresh later)
  └──────────────┘
```

---

### Sub-Phase 1.1 — Fetcher

**Responsibility:** Make HTTP requests to each data source and retrieve raw API/RSS responses. Handle pagination, rate limiting, retries, and time-range filtering at the request level.

#### Design

| Aspect | Detail |
|--------|--------|
| Pattern | Strategy pattern — one concrete fetcher per source, all inheriting `BaseFetcher` |
| Concurrency | `asyncio` + `aiohttp` for I/O-bound HTTP calls; configurable concurrency limit per source |
| Rate limiting | Per-source configurable delay (e.g., Reddit: 2 s between requests to respect API guidelines) |
| Retry | Exponential backoff with jitter; max 3 retries; log failures |
| Raw storage | Save every raw API response to `data/raw/{source}/page_{n}.json` for provenance |

#### Source-Specific Fetcher Details

**1.1.1 — Play Store Fetcher (`fetchers/play_store.py`)**

| Item | Value |
|------|-------|
| Library | `google-play-scraper` (Python) |
| Method | `reviews()` with `sort=Sort.NEWEST`, `count=1500` |
| Pagination | Library handles continuation tokens internally |
| Time filter | Post-fetch filter: discard reviews older than 4 months from `datetime.now()` |
| Cap | 1,500 reviews max |
| Rate limit | ~1 s delay between pagination batches |
| Raw output | List of dicts as returned by the library → saved to `data/raw/play_store/` |

**1.1.2 — App Store Fetcher (`fetchers/app_store.py`)**

| Item | Value |
|------|-------|
| Endpoint | `https://itunes.apple.com/{country}/rss/customerreviews/id={appId}/sortby=mostrecent/json` |
| Countries | `us`, `gb`, `in`, `ca`, `au` (top English-speaking markets to reach 500 cap) |
| Pagination | RSS feed pages via `<link rel="next">` entries in the JSON |
| Time filter | Post-fetch filter on `updated.label` field |
| Cap | 500 reviews max (across all country feeds combined) |
| App ID | Spotify iOS App ID: `324684580` |
| Rate limit | 1 s between page fetches |
| Raw output | Full JSON feed pages → saved to `data/raw/app_store/` |

**1.1.3 — Reddit Fetcher (Manual Curation)**

| Item | Value |
|------|-------|
| Method | Manual curation (due to Reddit API access restrictions) |
| Subreddits | `spotify`, `musicsuggestions`, `WeAreTheMusicMakers` |
| Search terms | `discover weekly`, `recommendations`, `same songs`, `repeat`, `stuck in a loop`, `algorithm`, `new music`, `music discovery` |
| Time filter | Manually verified to be within the last 4 months |
| Cap | 100–150 posts/comments combined |
| Raw output | Manually curated JSON/JSONL entries representing raw posts/comments → saved to `data/raw/reddit/` |

**1.1.4 — Spotify Community Forum Fetcher (`fetchers/spotify_community.py`)**

| Item | Value |
|------|-------|
| Base URL | `https://community.spotify.com` |
| Method | Standard HTTP GET + HTML parsing (public, no authentication) |
| Target Boards | "Recommendations", "Discover Weekly", "Algorithm", "Music Discovery" |
| Pagination | Query parameter `?page=X` |
| Time filter | Post-fetch date parsing from HTML (discard posts older than 4 months) |
| Cap | 500 threads/replies max |
| Rate limit | 1 s delay between page requests |
| Raw output | HTML listing pages or parsed thread structures → saved to `data/raw/spotify_community/` |

**1.1.5 — Trustpilot Fetcher (`fetchers/trustpilot.py`)**

| Item | Value |
|------|-------|
| Target URL | `https://www.trustpilot.com/review/www.spotify.com` |
| Method | Standard HTTP GET + HTML parsing (public, no authentication) |
| Pagination | Query parameter `?page=X` |
| Time filter | Post-fetch review date parsing (discard reviews older than 4 months) |
| Cap | 300 reviews max |
| Rate limit | 1–2 s delay between page requests |
| Raw output | HTML listing pages → saved to `data/raw/trustpilot/` |

**1.1.6 — YouTube Comments Fetcher (`fetchers/youtube.py`)**

| Item | Value |
|------|-------|
| Endpoint | YouTube Data API v3 (`commentThreads.list` endpoint) |
| Method | HTTP GET with free Google Cloud API key |
| Input Videos | 5–10 relevant videos (e.g. about "Spotify Wrapped", "Spotify algorithm", "Spotify Discover Weekly") |
| Pagination | `nextPageToken` from the API response |
| Time filter | Post-fetch date filter on `publishedAt` to keep only the last 4 months |
| Cap | 500 comments max combined |
| Rate limit | Request spacing to respect free tier API quota limits |
| Raw output | JSON list of comment threads → saved to `data/raw/youtube/` |

#### `BaseFetcher` Interface

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseFetcher(ABC):
    """Abstract base for all source fetchers."""

    @abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw data from source. Returns list of raw response dicts."""
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Return canonical source identifier (e.g., 'play_store')."""
        ...
```

---

### Sub-Phase 1.2 — Extractor

**Responsibility:** Parse the raw API/RSS response dicts from each fetcher and extract/normalise them into the **unified output schema** defined in the problem statement.

#### Design

| Aspect | Detail |
|--------|--------|
| Pattern | One extractor per source, inheriting `BaseExtractor` |
| Input | Raw response dicts from the fetcher |
| Output | List of dicts conforming to the unified schema |
| Date handling | All dates normalised to ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`) using `dateutil.parser` |
| Null handling | Missing fields set to `null` (e.g., Reddit posts have no `rating`) |

#### Unified Output Schema (per record)

```json
{
  "source": "play_store | app_store | reddit | spotify_community | trustpilot | youtube",
  "text": "full review/post/comment text",
  "rating": 4,
  "date": "2026-03-15T10:30:00Z",
  "url": "https://...",
  "thread_or_context": "r/spotify"
}
```

#### Source-Specific Field Mappings

**Play Store:**

| Output Field | Raw Field |
|--------------|-----------|
| `source` | `"play_store"` (constant) |
| `text` | `content` |
| `rating` | `score` (int 1–5) |
| `date` | `at` (datetime object → ISO string) |
| `url` | Constructed: `https://play.google.com/store/apps/details?id=com.spotify.music&reviewId={reviewId}` |
| `thread_or_context` | `null` |

**App Store:**

| Output Field | Raw Field |
|--------------|-----------|
| `source` | `"app_store"` (constant) |
| `text` | `entry[].content.label` |
| `rating` | `entry[].im:rating.label` (string → int) |
| `date` | `entry[].updated.label` (ISO string) |
| `url` | `entry[].link.attributes.href` |
| `thread_or_context` | `null` |

**Reddit:**

| Output Field | Raw Field |
|--------------|-----------|
| `source` | `"reddit"` (constant) |
| `text` | `data.selftext` (post) or `data.body` (comment) |
| `rating` | `null` (Reddit has no star ratings) |
| `date` | `data.created_utc` (Unix timestamp → ISO string) |
| `url` | `"https://www.reddit.com" + data.permalink` |
| `thread_or_context` | `"r/" + data.subreddit` |

**Spotify Community Forum:**

| Output Field | Raw Field / Logic |
|--------------|-------------------|
| `source` | `"spotify_community"` (constant) |
| `text` | Post body message (parsed from HTML tag) |
| `rating` | `null` (No star ratings on the forum) |
| `date` | Post publish date (parsed from HTML metadata or tag → ISO string) |
| `url` | Thread or post permalink (constructed from base URL + post path) |
| `thread_or_context` | Forum thread title (parsed from page title or thread header HTML) |

**Trustpilot:**

| Output Field | Raw Field / Logic |
|--------------|-------------------|
| `source` | `"trustpilot"` (constant) |
| `text` | Review content text (parsed from review card HTML) |
| `rating` | Review rating (parsed from rating stars class/metadata e.g., 1–5) |
| `date` | Review date (parsed from datetime attribute or text → ISO string) |
| `url` | Permalinks are usually not parsed, so `null` or constructed review link if available |
| `thread_or_context` | `null` |

**YouTube Comments:**

| Output Field | Raw Field / Logic |
|--------------|-------------------|
| `source` | `"youtube"` (constant) |
| `text` | `snippet.topLevelComment.snippet.textOriginal` or `textDisplay` |
| `rating` | `null` (YouTube comments have no star ratings) |
| `date` | `snippet.topLevelComment.snippet.publishedAt` (ISO string) |
| `url` | Constructed permalink: `"https://www.youtube.com/watch?v=" + videoId + "&lc=" + commentId` |
| `thread_or_context` | Video title (fetched during the video lookup step) |

#### `BaseExtractor` Interface

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseExtractor(ABC):
    """Abstract base for all source extractors."""

    @abstractmethod
    def extract(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform raw API data into unified schema dicts."""
        ...
```

---

### Sub-Phase 1.3 — Cleaner (Raw-Level)

**Responsibility:** Apply lightweight cleaning to the extracted records **before** writing `reviews_raw.jsonl`. This is *not* the deep NLP cleaning of Phase 2 — it is data-quality assurance at the ingestion boundary.

#### Operations

| Operation | Description |
|-----------|-------------|
| **Deduplication** | Remove exact-text duplicates within each source and across sources. Key: `(source, text_hash)` where `text_hash = sha256(text.strip().lower())` |
| **Encoding normalisation** | Ensure all text is valid UTF-8; strip stray null bytes, BOM markers, and non-printable control characters |
| **Empty-text removal** | Drop records where `text` is empty or whitespace-only after stripping |
| **Date validation** | Confirm `date` parses as a valid ISO 8601 string; drop records with unparseable dates |
| **Date-range enforcement** | Final safety check — discard any record with `date` outside the 4-month window |
| **Schema validation** | Validate each record against the required schema fields; log and drop malformed records |
| **Relevance flagging** | *(Log-only, no dropping)* — Log a warning if a source returns < 10 % of its cap, suggesting search terms or source may need adjustment |

#### Output

- Cleaned records passed downstream (still in-memory dicts at this point)
- Cleaning summary logged: `{total_input, duplicates_removed, empty_removed, date_invalid, total_output}`

---

### Sub-Phase 1.4 — Chunker (Stub for Phase 1, Active in Phase 2)

**Responsibility (future):** Split long review texts into smaller, semantically coherent chunks suitable for embedding. In Phase 1, this is a **pass-through stub**.

#### Phase 1 Behavior

```python
class TextChunker:
    """Pass-through in Phase 1. Will chunk text for embedding in Phase 2."""

    def chunk(self, records: list[dict]) -> list[dict]:
        # Phase 1: return records as-is
        return records
```

#### Phase 2 Design (Preview)

| Parameter | Value |
|-----------|-------|
| Strategy | Sentence-boundary chunking with overlap |
| Max chunk size | 512 tokens (aligned with BGE-base model context) |
| Overlap | 50 tokens |
| Library | `langchain.text_splitter.RecursiveCharacterTextSplitter` or `tiktoken` for token counting |
| Metadata | Each chunk inherits all parent record fields + adds `chunk_index` and `chunk_total` |

---

### Sub-Phase 1.5 — Pipeline Orchestrator

**Responsibility:** Coordinate the execution of all sub-phases in sequence for each source, merge results, and write final outputs.

#### Orchestration Flow

```python
async def run_pipeline():
    """Main entry point for Phase 1 ingestion."""

    all_records = []

    for source in [PlayStore, AppStore, Reddit, SpotifyCommunity, Trustpilot, YouTube]:
        # 1.1 Fetch
        fetcher = source.Fetcher(config)
        raw_data = await fetcher.fetch()

        # 1.2 Extract
        extractor = source.Extractor()
        records = extractor.extract(raw_data)

        # 1.3 Clean (raw-level)
        cleaner = RawCleaner()
        records = cleaner.clean(records)

        # 1.4 Chunk (pass-through in Phase 1)
        chunker = TextChunker()
        records = chunker.chunk(records)

        all_records.extend(records)

    # Cross-source deduplication
    all_records = deduplicate_cross_source(all_records)

    # 1.6 Write outputs
    write_jsonl(all_records, "data/output/reviews_raw.jsonl")
    write_meta(all_records, "data/output/meta.json")
```

#### Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| One source fails completely | Log error, continue with remaining sources, note failure in `meta.json` |
| Partial fetch failure (e.g., page 5 of 10 fails) | Retry up to 3×, then proceed with data collected so far; log partial count |
| Rate limit hit (HTTP 429) | Respect `Retry-After` header; exponential backoff |
| All sources fail | Exit with non-zero code; write `meta.json` with `"status": "failed"` |

---

### Sub-Phase 1.6 — Output Writer

**Responsibility:** Serialize the final list of cleaned records to disk in the required formats.

#### `reviews_raw.jsonl`

- One JSON object per line, UTF-8 encoded
- Fields: `source`, `text`, `rating`, `date`, `url`, `thread_or_context`
- Sorted by `date` descending (most recent first)

#### `meta.json`

```json
{
  "fetched_at": "2026-06-20T18:30:00Z",
  "date_range": "2026-02-20 to 2026-06-20",
  "counts": {
    "play_store": 1247,
    "app_store": 412,
    "reddit": 120,
    "spotify_community": 450,
    "trustpilot": 280,
    "youtube": 485
  },
  "total": 2994,
  "status": "success",
  "errors": [],
  "duration_seconds": 187
}
```

#### Per-Source `meta.json` (Provenance)

Each source also gets its own meta file at `data/raw/{source}/meta.json`:

```json
{
  "fetched_at": "2026-06-20T18:25:00Z",
  "source": "play_store",
  "raw_count": 1500,
  "after_date_filter": 1300,
  "after_dedup": 1247,
  "pages_fetched": 15,
  "errors": []
}
```

---

### Sub-Phase 1.7 — Scheduler / Refresh

**Responsibility:** Enable periodic re-runs of the ingestion pipeline to keep the dataset fresh.

#### Phase 1 Approach (Manual)

For Phase 1, the pipeline is triggered **manually** via CLI:

```bash
python -m src.ingestion.pipeline --run
```

Optional CLI arguments:

| Flag | Description | Default |
|------|-------------|---------|
| `--sources` | Comma-separated list of sources to fetch | `play_store,app_store,reddit,spotify_community,trustpilot,youtube` |
| `--months` | Number of months to look back | `4` |
| `--output-dir` | Directory for output files | `data/output/` |
| `--dry-run` | Validate config and print plan without fetching | `false` |

#### Future Scheduler Design (Phase 1.7+)

| Aspect | Detail |
|--------|--------|
| Tool | `APScheduler` (Python) or OS-level cron |
| Frequency | Weekly refresh recommended |
| Dedup strategy | Append-only with hash-based dedup against existing `reviews_raw.jsonl` |
| Staleness detection | Compare `meta.json.fetched_at` against current date; warn if > 7 days stale |
| Notification | Log to file + optional webhook / email on failure |

---

## Phase 2–5: Overview (Future Phases)

### Phase 2 — Processing & Deep Cleaning

| Step | Description |
|------|-------------|
| Language detection | Filter to English-only (`langdetect` or `fasttext`) |
| Text normalisation | Lowercase, remove URLs, strip emojis (configurable), normalise whitespace |
| Relevance filtering | Keyword + lightweight classifier to keep only discovery/recommendation-related reviews |
| PII scrubbing | Regex-based removal of emails, phone numbers, etc. |
| Output | `reviews_clean.jsonl` |

### Phase 3 — Embedding & Indexing

| Step | Description |
|------|-------------|
| Chunking | Activate Phase 1.4 chunker (sentence-boundary, 512 tokens, 50-token overlap) |
| Embedding | BGE-base-en-v1.5 via `sentence-transformers` |
| Vector store | ChromaDB or FAISS for local dev; Pinecone for production |
| Metadata indexing | Source, date, rating stored alongside vectors for filtered retrieval |

### Phase 4 — Retrieval & Ranking

| Step | Description |
|------|-------------|
| Semantic search | Cosine similarity over BGE embeddings |
| Hybrid search | Combine dense (vector) + sparse (BM25) retrieval |
| Re-ranking | Cross-encoder re-ranker for top-k refinement |
| Filters | Date range, source, rating, subreddit filters |

### Phase 5 — RAG Chatbot & Theme Analysis

| Step | Description |
|------|-------------|
| LLM | GPT-4o / Claude / open-source (configurable) |
| Prompt engineering | System prompt grounded in retrieved review chunks |
| Citation | Every answer cites source reviews with URLs |
| Theme clustering | BERTopic or LLM-based theme extraction |
| Dashboard | Streamlit or Gradio UI for interactive exploration |

---

## Technology Stack (Phase 1)

| Category | Tool / Library |
|----------|---------------|
| Language | Python 3.11+ |
| HTTP client | `aiohttp` (async) + `requests` (fallback sync) |
| Play Store | `google-play-scraper` |
| App Store | Direct HTTP to RSS/JSON feed |
| Reddit | Manual curation (due to API policy changes) |
| Spotify Community | `beautifulsoup4` + `lxml` + `aiohttp` HTML scraping |
| Trustpilot | `beautifulsoup4` + `lxml` + `aiohttp` HTML scraping |
| YouTube Comments | `google-api-python-client` / YouTube Data API v3 |
| Data model | `pydantic` for schema validation |
| Date parsing | `python-dateutil` |
| Hashing (dedup) | `hashlib` (SHA-256) |
| CLI | `argparse` or `click` |
| Logging | Python `logging` module (structured JSON logs) |
| Testing | `pytest` + `pytest-asyncio` |
| Linting | `ruff` |

---

## Constraints & Compliance Checklist

| Constraint | How It's Addressed |
|------------|-------------------|
| Respect `robots.txt` | Fetchers check `robots.txt` before scraping; use only public API/RSS endpoints |
| Rate limiting | Per-source configurable delays; exponential backoff on 429 |
| No authenticated content | All endpoints are public/unauthenticated |
| Raw data provenance | Every raw API response saved to `data/raw/{source}/` with per-source `meta.json` |
| No PII beyond public | No profile-page scraping; only publicly visible review/post data collected |
| Flagging low-relevance sources | Cleaner logs warning if a source returns < 10 % of its cap |

---

## Key Design Decisions

1. **JSONL over CSV** — Chosen as the primary format because JSON handles nested/null fields cleanly and avoids CSV quoting issues with review text containing commas, newlines, etc.

2. **Async-first fetching** — Network I/O is the bottleneck; async allows concurrent pagination within rate limits.

3. **Separation of Fetcher and Extractor** — Raw API responses are saved before extraction. This allows re-running extractors without re-fetching if the schema mapping needs to change.

4. **Pass-through Chunker** — Included in Phase 1 architecture to establish the pipeline interface, but does no work until Phase 2. This avoids a disruptive refactor later.

5. **Per-source provenance files** — `data/raw/{source}/meta.json` ensures every record can be traced back to its original API call, supporting the citation requirement of the future RAG chatbot.
