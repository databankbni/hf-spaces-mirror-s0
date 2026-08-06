# Problem Statement: Spotify Review Discovery Engine (Data Collection Phase)

## Project Context
This is Phase 1 (Ingestion) of an AI-powered Review Discovery Engine being built as part of a
Product Management Growth-Team assignment. The chosen product is **Spotify**.

Spotify has a sophisticated recommendation system, but a significant share of listening still
comes from repeat playlists, familiar artists, and previously discovered tracks. The strategic
goal is to increase meaningful music discovery and reduce repetitive listening behavior.

Before proposing any solution, we are building an AI-powered system that analyzes user feedback
at scale (App Store reviews, Play Store reviews, Reddit discussions, community forums) to surface
why users struggle to discover new music.

## Objective of This Task
Scrape and structure 4 months of recent user feedback about Spotify from the sources below into a
single clean, structured dataset that can later be cleaned, chunked, embedded, and used in a RAG
(Retrieval-Augmented Generation) pipeline.

## Data Sources to Collect

1. **Google Play Store reviews**
   - App: Spotify — package ID `com.spotify.music`
   - Time range: last 4 months from today
   - Cap: max 1,500 reviews (prioritize most recent + most helpful/highest engagement if the
     source supports sorting)

2. **Apple App Store reviews**
   - App: Spotify
   - Time range: last 4 months from today
   - Cap: max 500 reviews
   - Use the public App Store Customer Reviews RSS/JSON feed where possible (no auth required):
     `https://itunes.apple.com/{country}/rss/customerreviews/id={appId}/sortby=mostrecent/json`

3. **Reddit**
   - Subreddits: r/spotify, r/musicsuggestions, r/WeAreTheMusicMakers
   - Search terms / topics: "discover weekly," "recommendations," "same songs," "repeat,"
     "stuck in a loop," "algorithm," "new music," "music discovery"
   - Time range: last 4 months from today
   - Cap: max 1,000 posts/comments combined
   - Use Reddit's public read-only JSON search endpoints where possible (no auth required for
     public subreddit search), e.g.:
     `https://www.reddit.com/r/spotify/search.json?q=discover&restrict_sr=1&sort=new&limit=100`

## Output Schema
Combine all sources into a single structured file: `reviews_raw.jsonl` (one JSON object per line)
or `reviews_raw.csv`, with the following fields:

```
{
  "source": "play_store | app_store | reddit",
  "text": "full review/post/comment text",
  "rating": "1-5 star rating if available, else null",
  "date": "ISO 8601 date of the review/post",
  "url": "permalink to the review/post if available, else null",
  "subreddit_or_thread": "only for reddit entries, else null"
}
```

Also save a small `meta.json` summarizing the collection run:
```
{
  "fetched_at": "timestamp of this run",
  "date_range": "start_date to end_date",
  "counts": {"play_store": N, "app_store": N, "reddit": N},
  "total": N
}
```

## Why This Data Matters (Analytical Questions to Keep in Mind)
The collected data should be rich enough to eventually help answer:
- Why do users struggle to discover new music?
- What are the most common frustrations with recommendations?
- What listening behaviors are users trying to achieve?
- What causes users to repeatedly listen to the same content?
- Which user segments experience different discovery challenges?
- What unmet needs emerge consistently across reviews?

If a source returns very little content relevant to discovery/recommendation themes (e.g., mostly
unrelated complaints like billing or playback bugs), flag this so the search terms or sources can
be adjusted.

## Constraints
- Respect robots.txt and platform rate limits; do not bypass anti-bot measures.
- Do not access any authenticated/login-walled content.
- Store raw fetched data and a per-source meta.json with fetched_at, source, and item count for
  provenance — this will be needed later for citation in the RAG chatbot.
- No PII beyond what's publicly visible in reviews/posts should be collected (e.g., no scraping
  of reviewer profile pages beyond the username already shown publicly).

## Deliverable of This Task
A single combined `reviews_raw.jsonl` (or `.csv`) file containing all collected reviews/posts
across the three sources, plus a `meta.json` summary, ready to be handed off to the next phase
(cleaning, chunking, embedding with BGE, vector indexing, and theme clustering).