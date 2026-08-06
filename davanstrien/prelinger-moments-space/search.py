"""Search layer.

One interface, several backends. Today only text retrieval is wired up; the
embedding columns (emb_caption / emb_scene / emb_events) arrive in a later pass
and light up `VectorBackend` + `HybridBackend` without the UI changing shape.

    backends = build(store)          # whatever the data supports, best first
    hits = backends[0].search(Query("children washing hands"))

Every backend returns the same `Hit` list, so the renderer never asks how a
result was found.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from store import Store, parse_events, query_terms, rank_events

log = logging.getLogger(__name__)

# How many matching events a result shows (and therefore considers for its
# jump target). Kept here so render.py and Hit.jump cannot disagree.
MAX_SHOWN_EVENTS = 5

SELECT_COLS = """
    moment_id, identifier, title, year, date, ia_url, video_url, thumb_url,
    chunk_start, chunk_end, scene, caption, events
"""


@dataclass
class Query:
    text: str
    limit: int = 60
    decade: int | None = None
    undated: bool = False          # decade filter set to "undated"
    per_film: int | None = 2       # spread results across films; None = no cap


@dataclass
class Hit:
    moment_id: str
    identifier: str
    title: str
    year: int | None
    ia_url: str
    video_url: str
    thumb_url: str
    chunk_start: float
    chunk_end: float
    scene: str
    events: list[dict]
    matched: list[dict]            # events mentioning the query, best first
    score: float = 0.0

    @property
    def jump(self) -> float:
        """Where clicking this result should start the film.

        The earliest matching event rather than the best-scoring one: the list
        is shown in film order, so this is the timestamp the reader's eye lands
        on first. Predictable beats optimal here.
        """
        if not self.matched:
            return self.chunk_start
        return min(e["start"] for e in self.matched[:MAX_SHOWN_EVENTS])


class Backend(Protocol):
    name: str
    blurb: str

    def search(self, q: Query) -> list[Hit]: ...


# --- shared SQL plumbing ----------------------------------------------------


def _filters(q: Query) -> tuple[str, list]:
    clauses, params = [], []
    if q.undated:
        clauses.append("year IS NULL")
    elif q.decade is not None:
        clauses.append("year BETWEEN ? AND ?")
        params += [q.decade, q.decade + 9]
    return (" AND ".join(clauses), params)


def _per_film_cap(q: Query) -> str:
    if not q.per_film:
        return ""
    return (
        "QUALIFY row_number() OVER "
        f"(PARTITION BY identifier ORDER BY score DESC) <= {int(q.per_film)}"
    )


def _to_hits(rows: list[tuple], cols: list[str], terms: list[str]) -> list[Hit]:
    hits = []
    for row in rows:
        r = dict(zip(cols, row))
        events = parse_events(r["events"])
        hits.append(
            Hit(
                moment_id=r["moment_id"],
                identifier=r["identifier"],
                title=r["title"] or r["identifier"],
                year=r["year"],
                ia_url=r["ia_url"],
                video_url=r["video_url"],
                thumb_url=r["thumb_url"],
                chunk_start=r["chunk_start"],
                chunk_end=r["chunk_end"],
                scene=r["scene"] or "",
                events=events,
                matched=rank_events(events, terms),
                score=float(r.get("score") or 0.0),
            )
        )
    return hits


# --- text -------------------------------------------------------------------


class TextBackend:
    """BM25 over the caption (which contains both scene prose and event lines).

    Falls back to an AND-of-LIKEs if the FTS extension could not be built, so
    the Space still works on a machine with no network at boot.
    """

    name = "text"
    blurb = "keyword"

    def __init__(self, store: Store):
        self.store = store

    def search(self, q: Query) -> list[Hit]:
        terms = query_terms(q.text)
        where, params = _filters(q)
        con = self.store.con

        if self.store.fts:
            sql = f"""
                WITH scored AS (
                    SELECT {SELECT_COLS},
                           fts_main_moments.match_bm25(moment_id, ?) AS score
                    FROM moments
                )
                SELECT {SELECT_COLS}, score FROM scored
                WHERE score IS NOT NULL {f"AND {where}" if where else ""}
                {_per_film_cap(q)}
                ORDER BY score DESC
                LIMIT {int(q.limit)}
            """
            args = [q.text, *params]
        else:
            needles = terms or [q.text.strip().lower()]
            like = " AND ".join(["lower(caption) LIKE ?"] * len(needles))
            sql = f"""
                SELECT {SELECT_COLS}, 1.0 AS score FROM moments
                WHERE {like} {f"AND {where}" if where else ""}
                {_per_film_cap(q)}
                ORDER BY identifier, chunk_start
                LIMIT {int(q.limit)}
            """
            args = [f"%{n}%" for n in needles] + params

        cur = con.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return _to_hits(cur.fetchall(), cols, terms)


# --- vector (arrives with the embedding columns) ----------------------------


class VectorBackend:
    """Cosine similarity against one of the three embedding columns.

    Not reachable until the columns exist. The query vector is computed in-process
    by the app's local bge-m3 (see app.embed_query), so the whole search path —
    query embedding included — makes **no external calls**: it is DuckDB over a
    single parquet, which is what makes the dataset usable as an API by anything
    that can run `hf datasets sql`.
    """

    name = "vector"
    blurb = "meaning"

    def __init__(self, store: Store, columns=("emb_caption",), embed_query=None):
        self.store = store
        self.columns = tuple(columns)
        self._embed = embed_query

    def embed(self, text: str) -> list[float]:
        if self._embed is None:
            raise NotImplementedError(
                "no query embedder wired up — set search.VectorBackend(embed_query=...)"
            )
        return self._embed(text)

    def search(self, q: Query) -> list[Hit]:
        vec = self.embed(q.text)
        where, params = _filters(q)
        # `list_cosine_similarity`, not `array_cosine_similarity`: parquet
        # vectors bind as FLOAT[] LIST, and the ARRAY variant refuses to bind
        # without an explicit ::FLOAT[1024] cast on the column.
        #
        # The best of the three views rather than one of them: emb_caption
        # carries recall, emb_scene the setting, emb_events the action. A query
        # is usually aimed at one of those and GREATEST lets it find its own,
        # in a single scan.
        sims = [f"list_cosine_similarity({c}, ?::FLOAT[])" for c in self.columns]
        expr = sims[0] if len(sims) == 1 else f"greatest({', '.join(sims)})"
        sql = f"""
            WITH scored AS (
                SELECT {SELECT_COLS}, {expr} AS score
                FROM moments
                WHERE {self.columns[0]} IS NOT NULL
            )
            SELECT {SELECT_COLS}, score FROM scored
            WHERE score IS NOT NULL {f"AND {where}" if where else ""}
            {_per_film_cap(q)}
            ORDER BY score DESC
            LIMIT {int(q.limit)}
        """
        cur = self.store.con.execute(sql, [*([vec] * len(self.columns)), *params])
        cols = [d[0] for d in cur.description]
        return _to_hits(cur.fetchall(), cols, query_terms(q.text))


class HybridBackend:
    """Reciprocal-rank fusion of any two backends. Rank-based, so it needs no
    calibration between BM25 scores and cosine similarities."""

    name = "hybrid"
    blurb = "both"

    def __init__(self, backends: list[Backend], k: int = 60):
        self.backends = backends
        self.k = k

    def search(self, q: Query) -> list[Hit]:
        wide = Query(**{**q.__dict__, "limit": q.limit * 3})
        pooled: dict[str, Hit] = {}
        fused: dict[str, float] = {}
        for backend in self.backends:
            for rank, hit in enumerate(backend.search(wide)):
                pooled.setdefault(hit.moment_id, hit)
                fused[hit.moment_id] = fused.get(hit.moment_id, 0.0) + 1.0 / (
                    self.k + rank + 1
                )
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        out, per_film = [], {}
        for moment_id, score in ranked:
            hit = pooled[moment_id]
            # Re-apply the cap after fusion: each backend capped its own list,
            # so the union can still stack up on one film.
            if q.per_film:
                seen = per_film.get(hit.identifier, 0)
                if seen >= q.per_film:
                    continue
                per_film[hit.identifier] = seen + 1
            hit.score = score
            out.append(hit)
            if len(out) >= q.limit:
                break
        return out


def sample(store: Store, n: int = 12) -> list[Hit]:
    """A spread of moments for the empty state — one per film, drawn at random.

    `random()` rather than `hash(moment_id)`: the hash is stable, so every boot
    surfaced the same films forever. The caller draws a pool from this once and
    shuffles it per visit (see app.opening_html).
    """
    cur = store.con.execute(
        f"""
        SELECT {SELECT_COLS}, 0.0 AS score FROM moments
        QUALIFY row_number() OVER (PARTITION BY identifier ORDER BY chunk_start) = 1
        ORDER BY random()
        LIMIT {int(n)}
        """
    )
    cols = [d[0] for d in cur.description]
    return _to_hits(cur.fetchall(), cols, [])


# --- registry ---------------------------------------------------------------


def build(store: Store, embed_query=None) -> list[Backend]:
    """Whichever backends the current dataset can support."""
    text = TextBackend(store)
    backends: list[Backend] = [text]
    if store.embedding_columns and embed_query is not None:
        vector = VectorBackend(store, store.embedding_columns, embed_query)
        backends = [HybridBackend([text, vector]), text, vector]
    elif store.embedding_columns:
        log.info(
            "embedding columns present (%s) but no query embedder configured",
            ", ".join(store.embedding_columns),
        )
    return backends
