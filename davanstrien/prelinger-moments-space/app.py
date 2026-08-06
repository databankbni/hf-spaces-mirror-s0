"""Prelinger moments — timestamped search over VLM-captioned archival film.

The dataset is the API; this is thin client #1 over it. Search runs server-side
in DuckDB against a single parquet, results are plain HTML, and playback is a
`<video>` pointed at the public bucket.

Served by `gradio.Server` (a FastAPI subclass) rather than Gradio Blocks: the
page is hand-written HTML/CSS/JS, so nothing rewrites the stylesheet or injects
component styling over it. Spaces still runs it under the gradio SDK.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from gradio import Server

import render
import search
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("moments")

HERE = Path(__file__).parent

SUGGESTIONS = [
    "children washing hands",
    "atomic explosion",
    "traffic at night",
    "woman typing",
    "cattle in dust",
    "family at dinner",
]

app = Server()
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


# --- data -------------------------------------------------------------------

DATA = None
BACKENDS: list = []
BY_NAME: dict = {}
LOAD_ERROR: str | None = None

try:
    DATA = store.load()
except Exception as exc:  # most likely: private dataset, no HF_TOKEN secret
    log.exception("could not load the dataset")
    LOAD_ERROR = f"{type(exc).__name__}: {exc}"

# --- query embedding --------------------------------------------------------
#
# The query vector is computed HERE, not through a hosted inference call. Local
# bge-m3 reproduces the corpus vectors (which were built with TEI on a Job) to
# cosine 0.99999, so the swap is exact — and it means a public visitor costs
# nothing, needs no token, and cannot spend anyone's quota. One short query is
# ~0.2-0.5s on Space CPU, against a ~3s vector scan; it is not the bottleneck.
#
# Loading happens on a background thread so the page serves immediately on a
# cold boot. Until the weights land, `embed_query` raises and /api/search falls
# back to keyword — the same path a provider outage used to take.

EMBED_MODEL = os.environ.get("MOMENTS_EMBED_MODEL", "BAAI/bge-m3")
LOAD_ATTEMPTS = 3
# 12 shown, drawn from a bigger pool: 12 divides every column count the opening
# grid uses (2/3/4/6), so the last row is never short.
OPENING_N = 12
OPENING_POOL = 240
# bge-m3 accepts 8k tokens. A search box does not: without a cap, distinct
# multi-kilobyte queries are a cheap way to make one CPU Space do a lot of work.
MAX_QUERY_CHARS = 400
_model = None
# One DuckDB connection and one model instance are shared by every request, and
# neither is safe to use concurrently — searches are serialised on this lock.
# The handler is a plain `def` so FastAPI runs it in a worker thread: the event
# loop stays free to serve the page and static files while a search is running.
_search_lock = threading.Lock()


def _load_embedder() -> None:
    """Load the weights, retrying: one 503 mid-download would otherwise leave
    the Space advertising semantic search and silently serving keyword results
    for the life of the process."""
    global _model
    for attempt in range(1, LOAD_ATTEMPTS + 1):
        try:
            from sentence_transformers import SentenceTransformer

            t0 = time.perf_counter()
            model = SentenceTransformer(EMBED_MODEL, device="cpu")
            model.encode("warm up", normalize_embeddings=True)
            _model = model  # published only once warmed: readers see None or ready
            log.info("query embedder ready in %.0fs", time.perf_counter() - t0)
            return
        except Exception:
            log.exception("query embedder load failed (attempt %d/%d)", attempt, LOAD_ATTEMPTS)
            if attempt < LOAD_ATTEMPTS:
                time.sleep(30 * attempt)
    log.error("query embedder unavailable after %d attempts — keyword search only",
              LOAD_ATTEMPTS)


threading.Thread(target=_load_embedder, name="embed-load", daemon=True).start()


@lru_cache(maxsize=512)  # lru_cache does not cache exceptions, so misses retry
def _embed_cached(text: str) -> tuple[float, ...]:
    if _model is None:
        raise RuntimeError("query embedder still loading")
    vec = _model.encode(text, normalize_embeddings=True)
    return tuple(float(x) for x in np.asarray(vec).ravel())


def embed_query(text: str) -> list[float]:
    return list(_embed_cached(text))


if DATA is not None:
    BACKENDS = search.build(DATA, embed_query=embed_query)
    BY_NAME = {b.blurb: b for b in BACKENDS}
    # A pool drawn once, shuffled per visit. Re-querying DuckDB on every page
    # load would put the homepage on the same shared connection as search —
    # which is exactly the concurrency the search lock exists to prevent — for
    # no benefit: picking 12 of 240 in Python is already a different opening
    # every time.
    SAMPLE_POOL = search.sample(DATA, n=OPENING_POOL)
    DECADES = ["any decade", *DATA.decades, "undated"]
else:
    SAMPLE_POOL, DECADES = [], ["any decade"]


def opening_html() -> str:
    """A fresh dozen moments for each visitor."""
    if not SAMPLE_POOL:
        return ""
    return render.opening(random.sample(SAMPLE_POOL, min(OPENING_N, len(SAMPLE_POOL))))


# --- page -------------------------------------------------------------------


def _options(values: list[str], selected: str) -> str:
    return "".join(
        f'<option value="{v}"{" selected" if v == selected else ""}>{v}</option>'
        for v in values
    )


def page() -> str:
    shell = (HERE / "index.html").read_text()
    if DATA is None:
        body = (
            '<header class="masthead"><h1>Prelinger moments</h1>'
            f"<p>Could not read <code>{store.DATASET_ID}</code>. While the dataset "
            "is private this Space needs an <code>HF_TOKEN</code> secret with read "
            f"access.</p><p class='stamp'>{LOAD_ERROR}</p></header>"
        )
        return shell.replace("<!--BODY-->", body)

    modes = list(BY_NAME)
    mode_select = (
        '<select id="mode" aria-label="Search mode">' + _options(modes, modes[0]) + "</select>"
        if len(modes) > 1
        else ""
    )
    chips = "".join(f'<button type="button" class="chip">{s}</button>' for s in SUGGESTIONS)
    body = f"""
<header class="masthead">
  <h1>Prelinger moments</h1>
  <p>{DATA.n_films:,} public-domain films from the
  <a href="https://archive.org/details/prelinger" target="_blank" rel="noopener">Prelinger
  Archives</a>, annotated minute by minute with
  <a class="nb" href="https://huggingface.co/NemoStation/Marlin-2B" target="_blank" rel="noopener">Marlin-2B</a>
  — an open video model trained for dense captioning and temporal grounding. This Space
  searches the {DATA.n_moments:,} descriptions it produced; results play from the moment
  described.</p>
</header>

<form id="search" autocomplete="off">
  <input id="q" name="q" type="search" placeholder="children washing hands"
         aria-label="Search the captions" enterkeyhint="search"
         maxlength="{MAX_QUERY_CHARS}">
  <div class="suggest">{chips}</div>
  <div class="facets">
    <select id="decade" aria-label="Decade">{_options(DECADES, "any decade")}</select>
    <label class="check"><input type="checkbox" id="spread" checked>
      <span>at most two moments per film</span></label>
    {mode_select}
  </div>
</form>

<div class="stage" id="stage" hidden>
  <div class="screen">
    <video id="player" controls playsinline preload="metadata"></video>
    <button type="button" id="stage-play" aria-label="Play">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>
    </button>
  </div>
  <p class="stage-meta" id="stage-meta"></p>
  <div id="stage-list"></div>
</div>

<main id="results" aria-live="polite">{opening_html()}</main>

<footer class="about">
  <h2>Why this exists</h2>

  <p>Film archives are hard to search. Describing moving images is slow, skilled work,
  so for most collections it never happens: an item carries a title, a date, maybe a
  reel number, and nothing about what is on screen. Where there is a proper catalogue
  record it describes the whole film — enough to find <em>a 1950s film about road
  safety</em>, not <em>the moment a car hits a lamppost</em>.</p>

  <p>A model can describe what is on screen. It cannot say who these people are, where
  this was shot, or why the film was made — that is what cataloguers know and a model
  has no way to supply. But describing the images is the part that scales, and doing it
  automatically makes collections searchable that would otherwise stay dark, while
  leaving human description for the context and interpretation that actually needs it.</p>

  <p>Every ~60 seconds of these 1,864 public-domain films was described by
  <a class="nb" href="https://huggingface.co/NemoStation/Marlin-2B" target="_blank" rel="noopener">Marlin-2B</a>,
  a small video model, run on
  <a href="https://huggingface.co/docs/huggingface_hub/guides/jobs" target="_blank" rel="noopener">Hugging Face Jobs</a>
  with a <a href="https://huggingface.co/datasets/uv-scripts/video" target="_blank" rel="noopener">public recipe</a>
  — 23,148 described moments for about $10 of GPU time. Embedding those descriptions is
  what lets you search by meaning rather than by the exact words the model happened to
  use: <em>children washing hands</em> finds the scene even when the description says
  <em>a girl rinses her fingers under a tap</em>.</p>

  <p>The descriptions and their vectors are published as a dataset,
  <a href="https://huggingface.co/datasets/davanstrien/prelinger-moments" target="_blank" rel="noopener">davanstrien/prelinger-moments</a>.
  <strong>This page is one client over it, not the thing itself</strong> — every search
  here is a query anyone can run:</p>

  <pre><code>hf datasets sql "SELECT title, chunk_start, events_text, video_url
  FROM 'hf://datasets/davanstrien/prelinger-moments/data/*.parquet'
  WHERE events_text ILIKE '%atomic%' LIMIT 20"</code></pre>

  <p>Semantic search embeds your query with the same model used on the captions, in this
  Space, on CPU — no external calls. The films stream from a public
  <a href="https://huggingface.co/docs/hub/storage-buckets" target="_blank" rel="noopener">bucket</a>.</p>

  <p class="caveat">The descriptions are model output and nobody has checked them: a 2B
  model on scratchy 1930s film gets things wrong. Good for finding, not for citing. The
  recipe runs over any collection of videos, including yours.</p>
</footer>
"""
    return shell.replace("<!--BODY-->", body)


@app.get("/", response_class=HTMLResponse)
async def index():
    return page()


def _decade(value: str) -> int | None:
    """The UI only ever sends '1950s' or 'any decade', but this endpoint is
    public: `?decade=9abc` must not be a 500."""
    try:
        return int(value[:4]) if value and value[0].isdigit() else None
    except ValueError:
        return None


@app.get("/api/search")
def api_search(  # sync on purpose: FastAPI runs it in a worker thread
    q: str = "",
    decade: str = "any decade",
    spread: str = "1",
    mode: str = "",
):
    if DATA is None:
        return JSONResponse({"html": "", "ms": 0})
    if not q.strip():
        return JSONResponse({"html": opening_html(), "ms": 0})

    query = search.Query(
        text=q.strip()[:MAX_QUERY_CHARS],
        limit=60,
        decade=_decade(decade),
        undated=decade == "undated",
        per_film=2 if spread in ("1", "true", "on") else None,
    )
    backend = BY_NAME.get(mode) or BACKENDS[0]
    t0 = time.perf_counter()
    with _search_lock:  # shared model + shared DuckDB connection
        try:
            hits = backend.search(query)
        except Exception as exc:  # embedder still loading — keyword still works
            log.warning("%s search failed, falling back to keyword: %s", backend.name, exc)
            backend = BY_NAME["keyword"]
            hits = backend.search(query)
    ms = (time.perf_counter() - t0) * 1000
    log.info("%r -> %d hits in %.0f ms (%s)", query.text, len(hits), ms, backend.name)
    return JSONResponse({"html": render.results(hits, query.text, ms), "ms": ms})


if __name__ == "__main__":
    app.launch(show_error=True)
