---
title: Prelinger moments
emoji: 🎞️
colorFrom: gray
colorTo: yellow
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
pinned: false
short_description: Timestamped search over VLM-captioned Prelinger films
---

# Prelinger moments

Search inside public-domain archival film. Every minute-long chunk of every film
has been described second by second by a video VLM (Marlin-2B), so a query lands
on a *moment* — film plus timestamp — not just a title. Clicking a timestamp
streams that film from that second.

Thin client #1 over [`davanstrien/prelinger-moments`](https://huggingface.co/datasets/davanstrien/prelinger-moments)
— 23,148 moments from 1,864 films. The dataset is the API; this Space adds no
state of its own.

## How it works

| | |
| --- | --- |
| data | one parquet, pulled at boot, held in DuckDB |
| search | keyword (BM25), meaning (cosine over three embedding columns), or both (RRF) |
| playback | `<video>` pointed at the public bucket — range requests make a mid-film seek free |
| state | none |

## Search layer

`search.py` exposes one `Backend` interface returning one `Hit` shape, so the
renderer never asks how a result was found.

| mode | how | cost |
| --- | --- | --- |
| keyword | BM25 over the caption (DuckDB `fts`) | ~25 ms |
| meaning | `greatest()` of cosine against `emb_caption`, `emb_scene`, `emb_events` | ~290 ms to embed the query + ~400 ms to scan |
| both | reciprocal-rank fusion of the two — rank-based, so no score calibration | ~650 ms |

Vector search takes the best of the three views rather than one of them:
`emb_caption` carries recall, `emb_scene` the setting, `emb_events` the action,
and a query usually aims at one of those. Cost is linear in columns — searching
`emb_caption` alone is ~140 ms if that trade is ever worth making.

Query embeddings are computed **in this Space** by a local `BAAI/bge-m3` on CPU
(~0.2-0.5s, LRU-cached), loaded on a background thread so the page serves
immediately on a cold boot. Until the weights land — or if they fail to — search
falls back to keyword rather than erroring.

So the whole search path makes **no external calls**: no hosted inference, no
per-visitor token spend, nothing to rate-limit. Local bge-m3 reproduces the
dataset's vectors (built with TEI on a Job) to cosine 0.99999, so results are
identical either way.

## Configuration

| variable | meaning |
| --- | --- |
| `MOMENTS_DATASET` | dataset repo to read (default `davanstrien/prelinger-moments`) |
| `MOMENTS_PARQUET` | local parquet glob, for development |
| `MOMENTS_EMBED_MODEL` | query embedder (default `BAAI/bge-m3`, must match the dataset's) |
| `HF_TOKEN` | required only while the dataset is private (read scope); not used for inference |

## Why `gradio.Server` and not Blocks

The page is hand-written HTML/CSS/JS served by `gradio.Server` (a FastAPI
subclass): `index.html` for the shell, `static/app.css`, `static/app.js`, and one
`/api/search` endpoint returning rendered HTML. Spaces still runs it under the
gradio SDK.

Blocks was the original approach and cost more than it gave. Gradio 6 rewrites
every selector passed to `css=` to sit under `.gradio-container… .contain`, so
rules aimed at the shell silently match nothing; Buttons land in a Row with
`flex: 1 1 0` and divide the width regardless of content; and its component
styling reaches raw markup inside `gr.HTML`, so `<button>`/`<img>` resets had to
be fought with `!important` — and lost anyway on at least one real Android
device while passing in emulation. The UI here only ever needed a text input,
six links, two selects and a checkbox, so the framework was carrying no weight.

There is no `!important` in `app.css`. If a rule does not win, that is a bug in
the file rather than a fight with a framework.

## Caveats

- Captions are model output. They describe what the model saw, which is not
  always what is there.
- Roughly a quarter of films carry no usable date, so the decade filter has an
  explicit *undated* bucket rather than quietly dropping them.
- Timestamps are chunk-relative offsets remapped to global film seconds; they
  are good to a second or two, not to a frame.
