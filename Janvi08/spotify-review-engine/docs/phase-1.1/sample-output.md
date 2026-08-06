# Phase 1.1 — Sample Raw Output (Annotated)

> These are representative examples of what the raw JSON files look like **before** the Extractor (Phase 1.2) normalises them into the unified schema. Fields that are unused or will be discarded are noted.

---

## Play Store — `data/raw/play_store/page_1.json`

The file is a **JSON array**; each element is one review as returned by `google-play-scraper`.

```json
[
  {
    "reviewId": "gp:AOqpTOFtR3vKxyz1234",   // → used to build url
    "userName": "MusicLover99",               // public username
    "userImage": "https://lh3...",            // not collected further
    "content": "Spotify's Discover Weekly used to be amazing but now it just keeps recommending the same artists. I haven't heard anything new in months.",
                                              // → becomes text
    "score": 2,                               // → becomes rating (1-5)
    "thumbsUpCount": 47,                      // not in our schema
    "reviewCreatedVersion": "8.9.12.545",     // not in our schema
    "at": "2026-05-10 14:23:01",             // datetime object → becomes date
    "replyContent": null,                     // developer reply — not used
    "repliedAt": null
  },
  ...
]
```

**Extractor mapping:**

| Raw field | → | Schema field |
|-----------|---|-------------|
| `content` | → | `text` |
| `score` | → | `rating` |
| `at` (datetime) | → | `date` (ISO 8601 string) |
| `reviewId` | → | part of constructed `url` |
| _(constant)_ | → | `source = "play_store"` |
| _(absent)_ | → | `subreddit_or_thread = null` |

---

## App Store — `data/raw/app_store/page_us_1.json`

The file is the full RSS/JSON feed response. The relevant data is nested under `feed.entry[]`.

```json
{
  "feed": {
    "author": { "name": { "label": "iTunes Store" }, ... },
    "entry": [
      {
        "author": {
          "uri": { "label": "..." },
          "name": { "label": "DiscoveryFan" }   // public username
        },
        "updated": {
          "label": "2026-04-22T08:15:00-07:00"  // → becomes date
        },
        "im:rating": {
          "label": "1"                           // string → int → becomes rating
        },
        "im:version": { "label": "8.9.4" },     // not used
        "id": { "label": "123456789" },
        "title": {
          "label": "Discovery is broken"         // not in our schema (text is richer)
        },
        "content": {
          "label": "Every week Discover Weekly gives me the same 5 artists. It completely ignores my recent listening.",
                                                 // → becomes text
          "attributes": { "type": "text" }
        },
        "im:contentType": { ... },               // not used
        "link": {
          "attributes": {
            "rel": "related",
            "href": "https://apps.apple.com/..."  // → becomes url
          }
        }
      },
      ...
    ],
    "link": [
      { "attributes": { "rel": "next", "href": "https://itunes.apple.com/us/rss/.../page=2/json" } },
      ...
    ]
  }
}
```

**Important edge cases in raw output:**
- `entry` may be a **single dict** (not an array) if only one review exists on the page → Extractor wraps it.
- `im:rating` may be absent → `rating = null`.
- `content.label` may contain HTML entities (`&amp;`, `&#39;`) → Extractor calls `html.unescape()`.

---

## Reddit — `data/raw/reddit/search_spotify_discover_weekly_p1.json`

Standard Reddit listing JSON for a search result page.

```json
{
  "kind": "Listing",
  "data": {
    "after": "t3_abc123",           // pagination token for next page
    "children": [
      {
        "kind": "t3",               // t3 = post
        "data": {
          "id": "xyz789",
          "author": "musicnerd42",
          "title": "Discover Weekly is just recycling the same music",
          "selftext": "I've noticed that for the past 3 months, my Discover Weekly playlist has been rotating the same ~50 songs. Has anyone else experienced this? My listening history is very diverse but Spotify seems to think I only like indie rock.",
                                    // → becomes text (if empty, use title)
          "created_utc": 1716300000.0,   // Unix timestamp → ISO 8601 date
          "score": 234,             // upvotes minus downvotes
          "url": "https://www.reddit.com/r/spotify/comments/xyz789/...",
          "permalink": "/r/spotify/comments/xyz789/discover_weekly_is_just/",
          "subreddit": "spotify",   // → becomes subreddit_or_thread
          "num_comments": 47,
          "is_self": true           // true = text post, false = link post
        }
      },
      ...
    ]
  }
}
```

**Reddit — `data/raw/reddit/comments_xyz789.json`**

Comment fetch returns a 2-element array: `[post_listing, comments_listing]`.

```json
[
  { "kind": "Listing", "data": { "children": [{ "kind": "t3", "data": { ... post ... } }] } },
  {
    "kind": "Listing",
    "data": {
      "children": [
        {
          "kind": "t1",             // t1 = comment (skip "more" kind)
          "data": {
            "id": "cmt001",
            "author": "audiophile99",
            "body": "Same here. I think the algorithm got worse after they removed the ability to like individual songs in playlists.",
                                    // → becomes text
            "created_utc": 1716305000.0,
            "score": 89,
            "permalink": "/r/spotify/comments/xyz789/.../cmt001/"
          }
        },
        {
          "kind": "more",           // ← SKIPPED (EC-1.2.15)
          "data": { "count": 15, "children": [...] }
        }
      ]
    }
  }
]
```

**Edge cases visible in raw output:**
- `selftext = "[removed]"` or `"[deleted]"` → Extractor drops the record (EC-1.2.14).
- `kind = "more"` objects → Extractor skips these (EC-1.2.15).
- `created_utc` is a float, not a string → Extractor converts via `datetime.fromtimestamp()`.
- Link posts have `selftext = ""` → Extractor falls back to `title` for text (EC-1.2.17).
